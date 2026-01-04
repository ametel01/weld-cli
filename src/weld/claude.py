"""Claude integration for weld."""

import json
import subprocess
from pathlib import Path

from .constants import CLAUDE_TIMEOUT
from .models import Issues


class ClaudeError(Exception):
    """Claude invocation failed."""

    pass


def run_claude(
    prompt: str,
    exec_path: str = "claude",
    model: str | None = None,
    cwd: Path | None = None,
    timeout: int | None = None,
) -> str:
    """Run Claude CLI with prompt and return output.

    Args:
        prompt: The prompt to send to Claude
        exec_path: Path to claude executable
        model: Model to use (e.g., claude-sonnet-4-20250514). If None, uses default.
        cwd: Working directory
        timeout: Optional timeout in seconds (default: 600)

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
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeError(f"Claude timed out after {timeout} seconds") from e
    except FileNotFoundError:
        raise ClaudeError(f"Claude executable not found: {exec_path}") from None

    if result.returncode != 0:
        raise ClaudeError(f"Claude failed: {result.stderr}")
    return result.stdout


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
