"""Async subprocess runner for weld command execution."""

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from weld.telegram.errors import TelegramRunError

logger = logging.getLogger(__name__)

# Default timeout for command execution (10 minutes)
DEFAULT_TIMEOUT = 600

# Timeout for prompt responses (5 minutes)
# This is separate from command timeout - prompts always get full 5 minutes
PROMPT_TIMEOUT = 300.0

# Graceful shutdown timeout before SIGKILL
GRACEFUL_SHUTDOWN_TIMEOUT = 5.0

# Registry of active runs: run_id -> (Process, input_queue)
_active_runs: dict[int, tuple[asyncio.subprocess.Process, asyncio.Queue[str]]] = {}

# Chunk type for distinguishing stdout from stderr
ChunkType = Literal["stdout", "stderr", "prompt"]

# Prompt types for distinguishing interaction styles
PromptType = Literal["select", "yes_no", "confirm", "arrow_menu"]

# Patterns to detect interactive prompts
# Each pattern is a tuple of (compiled_regex, option_extractor_function, prompt_type)
# The extractor takes the match and returns a list of valid options
PROMPT_PATTERNS: list[tuple[re.Pattern[str], Callable[[re.Match[str]], list[str]], PromptType]] = [
    # Select [1/2/3] style prompts (weld implement menu)
    (
        re.compile(r"Select \[([^\]]+)\].*:"),
        lambda m: [opt.strip() for opt in m.group(1).split("/")],
        "select",
    ),
    # (y/n) style prompts - case insensitive options
    (
        re.compile(r"\(y/n\)\s*[:\?]?\s*$", re.IGNORECASE),
        lambda m: ["y", "n"],
        "yes_no",
    ),
    # [Y/n] style prompts - capital is default
    (
        re.compile(r"\[Y/n\]\s*[:\?]?\s*$"),
        lambda m: ["Y", "n", "y", ""],  # Y is default, empty string = default
        "yes_no",
    ),
    # [y/N] style prompts - capital is default
    (
        re.compile(r"\[y/N\]\s*[:\?]?\s*$"),
        lambda m: ["y", "N", "n", ""],  # N is default, empty string = default
        "yes_no",
    ),
    # Continue? / Proceed? / Apply? style prompts at end of line
    (
        re.compile(r"(Continue|Proceed|Apply|Confirm)\s*\?\s*$", re.IGNORECASE),
        lambda m: ["y", "n", "yes", "no"],
        "confirm",
    ),
    # Arrow menu pattern: "> [x] Item" or "> [ ] Item" (simple-term-menu)
    # This detects when a menu is being displayed and awaiting arrow key input
    (
        re.compile(r"^\s*>\s*\[[x ]\]\s+.+", re.MULTILINE),
        lambda m: ["enter", "up", "down", "q"],  # Arrow menu navigation
        "arrow_menu",
    ),
]


@dataclass
class PromptInfo:
    """Information about a detected interactive prompt."""

    text: str  # The full prompt text
    options: list[str]  # Available options (e.g., ["1", "2", "3"])
    prompt_type: PromptType  # Type of prompt (select, yes_no, confirm, arrow_menu)


def detect_prompt(text: str) -> PromptInfo | None:
    """Detect if text contains an interactive prompt.

    Checks against multiple prompt patterns including:
    - Select [N/N/N] style menus
    - (y/n), [Y/n], [y/N] confirmation prompts
    - Continue?, Proceed?, Apply? questions
    - Arrow-key menu indicators (> [x] Item)

    Args:
        text: Output text to check

    Returns:
        PromptInfo if a prompt is detected, None otherwise
    """
    for pattern, extractor, prompt_type in PROMPT_PATTERNS:
        match = pattern.search(text)
        if match:
            options = extractor(match)
            return PromptInfo(text=text, options=options, prompt_type=prompt_type)
    return None


async def send_input(run_id: int, response: str) -> bool:
    """Send input to a running command's stdin.

    Args:
        run_id: The run identifier
        response: The input to send (will have newline appended)

    Returns:
        True if input was sent, False if no such run exists
    """
    run_info = _active_runs.get(run_id)
    if run_info is None:
        logger.warning(f"Run {run_id}: No active process to send input to")
        return False

    proc, input_queue = run_info
    if proc.returncode is not None:
        logger.warning(f"Run {run_id}: Process already terminated")
        return False

    await input_queue.put(response)
    return True


async def execute_run(
    run_id: int,
    command: str,
    args: list[str] | None = None,
    cwd: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> AsyncIterator[tuple[ChunkType, str]]:
    """Execute a weld command asynchronously with streaming output.

    Uses asyncio.subprocess for non-blocking execution with proper timeout handling.
    Supports interactive prompts - when a prompt is detected, yields ("prompt", data)
    and waits for input via send_input().

    Args:
        run_id: Unique identifier for this run (for logging/tracking)
        command: The weld subcommand to execute (e.g., "plan", "research")
        args: Additional arguments to pass to the command
        cwd: Working directory for command execution
        timeout: Maximum execution time in seconds (default 600s/10min)

    Yields:
        Tuples of (chunk_type, data) where chunk_type is "stdout", "stderr", or "prompt"
        and data is the string content. For "prompt", data contains the prompt text.

    Raises:
        TelegramRunError: If command fails to start, times out, or returns non-zero

    Example:
        async for chunk_type, data in execute_run(1, "plan", ["--dry-run"], cwd=Path("/project")):
            if chunk_type == "stdout":
                print(data, end="")
            elif chunk_type == "prompt":
                # Show prompt to user and get response
                response = await get_user_response(data)
                await send_input(run_id, response)
    """
    cmd = ["weld", command]
    if args:
        cmd.extend(args)

    logger.info(f"Run {run_id}: Starting command: {' '.join(cmd)} in {cwd or 'current dir'}")

    proc: asyncio.subprocess.Process | None = None
    input_queue: asyncio.Queue[str] = asyncio.Queue()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.debug(f"Run {run_id}: Process started with PID {proc.pid}")

        # Register process and input queue for interaction
        _active_runs[run_id] = (proc, input_queue)

        # Track when streams are exhausted
        stdout_done = False
        stderr_done = False
        # Buffer for accumulating output to detect prompts
        output_buffer = ""

        async def read_chunk(
            stream: asyncio.StreamReader | None,
            stream_type: ChunkType,
        ) -> tuple[ChunkType, str] | None:
            """Try to read a chunk from a stream, return None if EOF."""
            if stream is None:
                return None
            try:
                chunk = await asyncio.wait_for(stream.read(4096), timeout=0.1)
                if not chunk:
                    return None
                return (stream_type, chunk.decode("utf-8", errors="replace"))
            except TimeoutError:
                return ("_timeout", "")  # type: ignore[return-value]

        start_time = asyncio.get_event_loop().time()

        while not (stdout_done and stderr_done):
            # Check overall timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.error(f"Run {run_id}: Command timed out after {timeout} seconds")
                raise TimeoutError(f"Command timed out after {timeout} seconds")

            # Try to read from stdout
            if not stdout_done and proc.stdout:
                result = await read_chunk(proc.stdout, "stdout")
                if result is None:
                    stdout_done = True
                elif result[0] != "_timeout":
                    _chunk_type, data = result
                    output_buffer += data

                    # Check for prompt
                    prompt_info = detect_prompt(output_buffer)
                    if prompt_info:
                        logger.info(f"Run {run_id}: Detected prompt: {prompt_info.options}")
                        yield ("prompt", output_buffer)
                        output_buffer = ""

                        # Wait for user input with dedicated prompt timeout (5 minutes)
                        # This is separate from command timeout - prompts always get full time
                        try:
                            response = await asyncio.wait_for(
                                input_queue.get(), timeout=PROMPT_TIMEOUT
                            )
                            logger.info(f"Run {run_id}: Received input: {response}")
                            if proc.stdin:
                                proc.stdin.write(f"{response}\n".encode())
                                await proc.stdin.drain()
                        except TimeoutError:
                            logger.error(
                                f"Run {run_id}: Prompt response timeout after "
                                f"{PROMPT_TIMEOUT} seconds, cancelling run"
                            )
                            raise TimeoutError(
                                f"Prompt not answered within {int(PROMPT_TIMEOUT // 60)} minutes"
                            ) from None
                    else:
                        yield result

            # Try to read from stderr
            if not stderr_done and proc.stderr:
                result = await read_chunk(proc.stderr, "stderr")
                if result is None:
                    stderr_done = True
                elif result[0] != "_timeout":
                    yield result

            # If process exited, drain remaining output
            if proc.returncode is not None:
                if proc.stdout and not stdout_done:
                    remaining = await proc.stdout.read()
                    if remaining:
                        yield ("stdout", remaining.decode("utf-8", errors="replace"))
                    stdout_done = True
                if proc.stderr and not stderr_done:
                    remaining = await proc.stderr.read()
                    if remaining:
                        yield ("stderr", remaining.decode("utf-8", errors="replace"))
                    stderr_done = True

        # Wait for process to complete
        try:
            return_code = await asyncio.wait_for(proc.wait(), timeout=10.0)
        except TimeoutError:
            logger.warning(f"Run {run_id}: Process did not exit cleanly, terminating")
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                logger.error(f"Run {run_id}: Process did not terminate, killing")
                proc.kill()
                await proc.wait()
            raise TelegramRunError(f"Run {run_id}: Command did not exit cleanly") from None

        logger.info(f"Run {run_id}: Command completed with return code {return_code}")

        if return_code != 0:
            raise TelegramRunError(f"Run {run_id}: Command failed with exit code {return_code}")

    except FileNotFoundError:
        raise TelegramRunError(f"Run {run_id}: weld executable not found") from None

    except TimeoutError as e:
        logger.error(f"Run {run_id}: {e}")
        if proc is not None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        raise TelegramRunError(f"Run {run_id}: {e}") from None

    except asyncio.CancelledError:
        logger.warning(f"Run {run_id}: Execution cancelled")
        if proc is not None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        raise

    except TelegramRunError:
        raise

    except Exception as e:
        logger.exception(f"Run {run_id}: Unexpected error: {e}")
        if proc is not None and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        raise TelegramRunError(f"Run {run_id}: {e}") from e

    finally:
        # Always unregister the run
        _active_runs.pop(run_id, None)


@dataclass
class ArrowMenuItem:
    """A parsed menu item from simple-term-menu style output."""

    text: str  # The menu item text
    checked: bool  # Whether the item is checked [x] vs [ ]
    selected: bool  # Whether this is the currently selected item (has > prefix)


def parse_arrow_menu(text: str) -> list[ArrowMenuItem]:
    """Parse arrow menu items from simple-term-menu style output.

    Extracts menu items from output containing lines like:
        > [x] Selected checked item
          [ ] Unselected unchecked item
          [x] Unselected checked item

    The > prefix indicates the currently selected (cursor) item.
    [x] indicates a checked item, [ ] indicates unchecked.

    Args:
        text: Output text containing arrow menu lines

    Returns:
        List of ArrowMenuItem with text, checked state, and selected state.
        Returns empty list if no menu items found.

    Example:
        >>> text = '''
        ... > [x] Step 1: Initialize
        ...   [ ] Step 2: Configure
        ...   [x] Step 3: Complete
        ... '''
        >>> items = parse_arrow_menu(text)
        >>> items[0].text
        'Step 1: Initialize'
        >>> items[0].checked
        True
        >>> items[0].selected
        True
    """
    # Pattern matches:
    # - Optional leading whitespace
    # - Optional > (selected indicator) with optional whitespace
    # - [x] or [ ] checkbox
    # - The menu item text
    pattern = re.compile(r"^(\s*)(>)?\s*\[([ x])\]\s+(.+)$", re.MULTILINE)

    items: list[ArrowMenuItem] = []
    for match in pattern.finditer(text):
        selected_marker = match.group(2)  # ">" or None
        checkbox_state = match.group(3)  # "x" or " "
        item_text = match.group(4).rstrip()

        items.append(
            ArrowMenuItem(
                text=item_text,
                checked=checkbox_state == "x",
                selected=selected_marker == ">",
            )
        )

    return items


async def cancel_run(run_id: int) -> bool:
    """Cancel a running command by sending SIGTERM, then SIGKILL if needed.

    Implements graceful shutdown: sends SIGTERM first, waits up to 5 seconds
    for the process to exit, then sends SIGKILL if still running.

    Args:
        run_id: The run identifier to cancel

    Returns:
        True if a process was found and cancelled, False if no such run exists
        or it has already completed.

    Note:
        This handles the race condition where a process completes naturally
        between the cancel request and execution - in that case, returns False.
    """
    run_info = _active_runs.get(run_id)

    if run_info is None:
        logger.debug(f"Run {run_id}: No active process found to cancel")
        return False

    proc, _ = run_info

    # Check if process already terminated (race with natural completion)
    if proc.returncode is not None:
        logger.debug(f"Run {run_id}: Process already terminated with code {proc.returncode}")
        _active_runs.pop(run_id, None)
        return False

    logger.info(f"Run {run_id}: Sending SIGTERM to process {proc.pid}")
    proc.terminate()

    try:
        await asyncio.wait_for(proc.wait(), timeout=GRACEFUL_SHUTDOWN_TIMEOUT)
        logger.info(f"Run {run_id}: Process terminated gracefully")
    except TimeoutError:
        logger.warning(
            f"Run {run_id}: Process did not terminate after {GRACEFUL_SHUTDOWN_TIMEOUT}s, "
            "sending SIGKILL"
        )
        proc.kill()
        await proc.wait()
        logger.info(f"Run {run_id}: Process killed")

    # Cleanup handled by finally block in execute_run, but be defensive
    _active_runs.pop(run_id, None)
    return True
