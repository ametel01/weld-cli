"""Async subprocess runner for weld command execution."""

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

from weld.telegram.errors import TelegramRunError

logger = logging.getLogger(__name__)

# Default timeout for command execution (10 minutes)
DEFAULT_TIMEOUT = 600

# Graceful shutdown timeout before SIGKILL
GRACEFUL_SHUTDOWN_TIMEOUT = 5.0

# Registry of active runs: run_id -> Process
_active_runs: dict[int, asyncio.subprocess.Process] = {}

# Chunk type for distinguishing stdout from stderr
ChunkType = Literal["stdout", "stderr"]


async def execute_run(
    run_id: int,
    command: str,
    args: list[str] | None = None,
    cwd: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> AsyncIterator[tuple[ChunkType, str]]:
    """Execute a weld command asynchronously with streaming output.

    Uses asyncio.subprocess for non-blocking execution with proper timeout handling.

    Args:
        run_id: Unique identifier for this run (for logging/tracking)
        command: The weld subcommand to execute (e.g., "plan", "research")
        args: Additional arguments to pass to the command
        cwd: Working directory for command execution
        timeout: Maximum execution time in seconds (default 600s/10min)

    Yields:
        Tuples of (chunk_type, data) where chunk_type is "stdout" or "stderr"
        and data is the string content read from that stream.

    Raises:
        TelegramRunError: If command fails to start, times out, or returns non-zero

    Example:
        async for chunk_type, data in execute_run(1, "plan", ["--dry-run"], cwd=Path("/project")):
            if chunk_type == "stdout":
                print(data, end="")
            else:
                print(f"[stderr] {data}", end="", file=sys.stderr)
    """
    cmd = ["weld", command]
    if args:
        cmd.extend(args)

    logger.info(f"Run {run_id}: Starting command: {' '.join(cmd)} in {cwd or 'current dir'}")

    proc: asyncio.subprocess.Process | None = None

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.debug(f"Run {run_id}: Process started with PID {proc.pid}")

        # Register process for cancellation
        _active_runs[run_id] = proc

        # Track when streams are exhausted
        stdout_done = False
        stderr_done = False

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
    proc = _active_runs.get(run_id)

    if proc is None:
        logger.debug(f"Run {run_id}: No active process found to cancel")
        return False

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
