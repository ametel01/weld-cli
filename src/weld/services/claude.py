"""Claude CLI integration for weld."""

import json
import subprocess
import sys
from pathlib import Path

from rich.console import Console

from ..constants import CLAUDE_TIMEOUT

# Prefix for streaming output
STREAM_PREFIX = "claude>"
STREAM_PREFIX_STYLE = "cyan bold"


class ClaudeError(Exception):
    """Claude invocation failed."""

    pass


def _extract_text_from_stream_json(line: str) -> str | None:
    """Extract text content from a stream-json line.

    Claude CLI stream-json format emits JSON objects, one per line.
    Text content appears in objects with structure:
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}]}}

    Args:
        line: A single line from stream-json output

    Returns:
        Extracted text or None if line doesn't contain text content
    """
    try:
        data = json.loads(line)

        # Handle assistant message format
        if data.get("type") == "assistant":
            message = data.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                texts = [item.get("text", "") for item in content if item.get("type") == "text"]
                if texts:
                    return "".join(texts)

        # Handle direct content format (alternative structure)
        content = data.get("content")
        if isinstance(content, list):
            texts = [item.get("text", "") for item in content if item.get("type") == "text"]
            if texts:
                return "".join(texts)

        return None
    except json.JSONDecodeError:
        return None


def _write_with_prefix(
    text: str,
    console: Console,
    at_line_start: bool,
) -> bool:
    """Write text to stdout with claude> prefix on new lines.

    Args:
        text: Text to write
        console: Rich console for styled output
        at_line_start: Whether we're at the start of a line

    Returns:
        Whether we end at the start of a new line (after a newline)
    """
    if not text:
        return at_line_start

    # Split text to handle newlines
    parts = text.split("\n")

    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1

        # Print prefix only if at start of line AND there's actual content
        if at_line_start and part:
            console.print(f"[{STREAM_PREFIX_STYLE}]{STREAM_PREFIX}[/] ", end="")
            if console.file:
                console.file.flush()  # Ensure prefix appears before text
            at_line_start = False

        # Print the text part
        if part:
            sys.stdout.write(part)
            sys.stdout.flush()

        # Handle newline (except for trailing empty part from split)
        if not is_last:
            sys.stdout.write("\n")
            sys.stdout.flush()
            at_line_start = True

    return at_line_start


def _run_streaming(
    cmd: list[str],
    cwd: Path | None,
    timeout: int,
    stdin_input: str | None = None,
) -> str:
    """Run command with streaming output to stdout.

    Args:
        cmd: Command and arguments to run
        cwd: Working directory
        timeout: Timeout in seconds
        stdin_input: Optional input to send via stdin

    Returns:
        Full output text

    Raises:
        ClaudeError: If command fails or times out
    """
    import select
    import time

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdin=subprocess.PIPE if stdin_input else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        raise ClaudeError(f"Claude executable not found: {cmd[0]}") from None

    # Send stdin input if provided, then close stdin
    if stdin_input and proc.stdin:
        proc.stdin.write(stdin_input)
        proc.stdin.close()

    output_parts: list[str] = []
    start_time = time.monotonic()
    console = Console()
    at_line_start = True  # Track if we're at the start of a line

    try:
        assert proc.stdout is not None
        assert proc.stderr is not None

        # Use select for timeout-aware reading on Unix
        # Fall back to blocking read with periodic timeout checks on other platforms
        stdout_fd = proc.stdout.fileno()
        buffer = ""

        while True:
            # Check timeout
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise ClaudeError(f"Claude timed out after {timeout} seconds")

            remaining = timeout - elapsed

            # Use select to wait for data with timeout
            try:
                readable, _, _ = select.select([stdout_fd], [], [], min(remaining, 1.0))
            except (ValueError, OSError):
                # File descriptor closed or invalid
                break

            if readable:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    # EOF
                    break
                buffer += chunk

                # Process complete lines
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    text = _extract_text_from_stream_json(line.strip())
                    if text:
                        output_parts.append(text)
                        at_line_start = _write_with_prefix(text, console, at_line_start)
                        # Each JSON line is a discrete message - ensure newline after each
                        if not at_line_start:
                            sys.stdout.write("\n")
                            sys.stdout.flush()
                            output_parts.append("\n")
                            at_line_start = True

            # Check if process has exited
            if proc.poll() is not None:
                # Read any remaining data
                remaining_data = proc.stdout.read()
                if remaining_data:
                    buffer += remaining_data
                break

        # Process any remaining buffer content
        if buffer.strip():
            text = _extract_text_from_stream_json(buffer.strip())
            if text:
                output_parts.append(text)
                at_line_start = _write_with_prefix(text, console, at_line_start)
                # Remaining buffer is also a discrete message - ensure newline after it
                if not at_line_start:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    output_parts.append("\n")
                    at_line_start = True

        # Ensure output ends with a newline for clean terminal state
        if not at_line_start:
            sys.stdout.write("\n")
            sys.stdout.flush()
            output_parts.append("\n")

        # Wait for process to complete
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

        if proc.returncode != 0:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise ClaudeError(f"Claude failed: {stderr}")

        return "".join(output_parts)

    except ClaudeError:
        raise
    except Exception as e:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise ClaudeError(f"Streaming failed: {e}") from e


def run_claude(
    prompt: str,
    exec_path: str = "claude",
    model: str | None = None,
    cwd: Path | None = None,
    timeout: int | None = None,
    stream: bool = False,
    skip_permissions: bool = False,
) -> str:
    """Run Claude CLI with prompt and return output.

    Args:
        prompt: The prompt to send to Claude
        exec_path: Path to claude executable
        model: Model to use (e.g., claude-sonnet-4-20250514). If None, uses default.
        cwd: Working directory
        timeout: Optional timeout in seconds (default: 600)
        stream: If True, stream output to stdout in real-time
        skip_permissions: If True, add --dangerously-skip-permissions for write operations

    Returns:
        Claude stdout output

    Raises:
        ClaudeError: If claude fails, returns non-zero, or times out
    """
    timeout = timeout or CLAUDE_TIMEOUT

    # Build base command - use stdin for prompt to avoid "Argument list too long" errors
    cmd = [exec_path, "--output-format", "text"]
    if model:
        cmd.extend(["--model", model])
    if skip_permissions:
        cmd.append("--dangerously-skip-permissions")

    try:
        if stream:
            # Use stream-json for real-time streaming
            stream_cmd = [exec_path, "--verbose", "--output-format", "stream-json"]
            if model:
                stream_cmd.extend(["--model", model])
            if skip_permissions:
                stream_cmd.append("--dangerously-skip-permissions")
            return _run_streaming(stream_cmd, cwd, timeout, stdin_input=prompt)
        else:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                raise ClaudeError(f"Claude failed: {result.stderr}")
            return result.stdout
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"Claude timed out after {timeout} seconds") from e
    except FileNotFoundError:
        raise ClaudeError(f"Claude executable not found: {exec_path}") from None
