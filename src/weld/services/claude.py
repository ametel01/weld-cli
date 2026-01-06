"""Claude CLI integration for weld."""

import json
import subprocess
import sys
from pathlib import Path

from ..constants import CLAUDE_TIMEOUT


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


def _run_streaming(
    cmd: list[str],
    cwd: Path | None,
    timeout: int,
) -> str:
    """Run command with streaming output to stdout.

    Args:
        cmd: Command and arguments to run
        cwd: Working directory
        timeout: Timeout in seconds

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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        raise ClaudeError(f"Claude executable not found: {cmd[0]}") from None

    output_parts: list[str] = []
    start_time = time.monotonic()

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
                        sys.stdout.write(text)
                        sys.stdout.flush()

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
                sys.stdout.write(text)
                sys.stdout.flush()

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

    cmd = [exec_path, "-p", prompt, "--output-format", "text"]
    if model:
        cmd.extend(["--model", model])
    if skip_permissions:
        cmd.append("--dangerously-skip-permissions")

    try:
        if stream:
            # Use stream-json for real-time streaming
            stream_cmd = [exec_path, "-p", prompt, "--verbose", "--output-format", "stream-json"]
            if model:
                stream_cmd.extend(["--model", model])
            if skip_permissions:
                stream_cmd.append("--dangerously-skip-permissions")
            return _run_streaming(stream_cmd, cwd, timeout)
        else:
            result = subprocess.run(
                cmd,
                cwd=cwd,
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
