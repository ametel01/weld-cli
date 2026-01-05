"""Claude integration for weld."""

import json
import subprocess
from pathlib import Path

from ..constants import CLAUDE_TIMEOUT
from ..models import Issues
from .streaming import run_streaming_subprocess


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


def run_claude(
    prompt: str,
    exec_path: str = "claude",
    model: str | None = None,
    cwd: Path | None = None,
    timeout: int | None = None,
    stream: bool = False,
) -> str:
    """Run Claude CLI with prompt and return output.

    Args:
        prompt: The prompt to send to Claude
        exec_path: Path to claude executable
        model: Model to use (e.g., claude-sonnet-4-20250514). If None, uses default.
        cwd: Working directory
        timeout: Optional timeout in seconds (default: 600)
        stream: If True, stream output to stdout in real-time

    Returns:
        Claude stdout output

    Raises:
        ClaudeError: If claude fails, returns non-zero, or times out
    """
    timeout = timeout or CLAUDE_TIMEOUT

    cmd = [exec_path, "-p", prompt, "--output-format", "text"]
    if model:
        cmd.extend(["--model", model])

    try:
        if stream:
            # Use --output-format stream-json for real-time streaming
            # Claude CLI doesn't support streaming text output directly in print mode
            # See: https://github.com/anthropics/claude-code/issues/733
            # Note: --verbose is required when using stream-json with --print
            stream_cmd = [exec_path, "-p", prompt, "--verbose", "--output-format", "stream-json"]
            if model:
                stream_cmd.extend(["--model", model])

            return run_streaming_subprocess(
                cmd=stream_cmd,
                text_extractor=_extract_text_from_stream_json,
                cwd=cwd,
                timeout=timeout,
                error_class=ClaudeError,
                service_name="Claude",
            )
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


def parse_review_json(review_md: str) -> Issues:
    """Parse issues JSON from last line of review.

    The review format expects a JSON object on the last line with
    format: {"pass": bool, "issues": [...]}

    Args:
        review_md: Full review markdown output

    Returns:
        Parsed Issues model

    Raises:
        ClaudeError: If parsing fails
    """
    lines = review_md.strip().split("\n")
    if not lines:
        raise ClaudeError("Empty review output")

    last_line = lines[-1].strip()
    try:
        data = json.loads(last_line)
        return Issues.model_validate(data)
    except json.JSONDecodeError as e:
        raise ClaudeError(f"Invalid JSON in review last line: {e}") from e
    except Exception as e:
        raise ClaudeError(f"Failed to parse issues: {e}") from e
