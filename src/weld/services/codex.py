"""Codex integration for weld."""

import json
import subprocess
from pathlib import Path

from ..constants import CODEX_TIMEOUT
from ..models import Issues
from .streaming import run_streaming_subprocess


class CodexError(Exception):
    """Codex invocation failed."""

    pass


def _extract_text_from_codex_json(line: str) -> str | None:
    """Extract text content from a Codex JSONL line.

    Codex CLI with --json emits JSONL events. Agent messages appear in
    item.agent_message events with content array.

    Args:
        line: A single line from Codex JSON output

    Returns:
        Extracted text or None if line doesn't contain text content
    """
    try:
        data = json.loads(line)

        # Handle item.agent_message events
        if data.get("type") == "item.agent_message":
            content = data.get("content", [])
            if isinstance(content, list):
                texts = [
                    item.get("text", "") for item in content if item.get("type") == "output_text"
                ]
                if texts:
                    return "".join(texts)

        # Handle turn.completed with final message
        if data.get("type") == "turn.completed":
            message = data.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                texts = [
                    item.get("text", "") for item in content if item.get("type") == "output_text"
                ]
                if texts:
                    return "".join(texts)

        return None
    except json.JSONDecodeError:
        return None


def run_codex(
    prompt: str,
    exec_path: str = "codex",
    sandbox: str = "read-only",
    model: str | None = None,
    cwd: Path | None = None,
    timeout: int | None = None,
    stream: bool = False,
) -> str:
    """Run codex with prompt and return output.

    Args:
        prompt: The prompt to send to Codex
        exec_path: Path to codex executable
        sandbox: Sandbox mode (read-only, network-only, etc.)
        model: Model to use (e.g., o3, gpt-4o). If None, uses codex default.
        cwd: Working directory
        timeout: Optional timeout in seconds (default: 600)
        stream: If True, stream output to stdout in real-time

    Returns:
        Codex stdout output

    Raises:
        CodexError: If codex fails, returns non-zero, or times out
    """
    timeout = timeout or CODEX_TIMEOUT

    cmd = [exec_path, "-p", prompt, "--sandbox", sandbox]
    if model:
        cmd.extend(["--model", model])

    try:
        if stream:
            # Use --json for streaming JSONL output
            # See: https://developers.openai.com/codex/cli/reference/
            stream_cmd = [*cmd, "--json"]

            return run_streaming_subprocess(
                cmd=stream_cmd,
                text_extractor=_extract_text_from_codex_json,
                cwd=cwd,
                timeout=timeout,
                error_class=CodexError,
                service_name="Codex",
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
                raise CodexError(f"Codex failed: {result.stderr}")
            return result.stdout
    except subprocess.TimeoutExpired as e:
        raise CodexError(f"Codex timed out after {timeout} seconds") from e
    except FileNotFoundError:
        raise CodexError(f"Codex executable not found: {exec_path}") from None


def parse_review_json(review_md: str) -> Issues:
    """Parse issues JSON from last line of review.

    The review format expects a JSON object on the last line with
    format: {"pass": bool, "issues": [...]}

    Args:
        review_md: Full review markdown output

    Returns:
        Parsed Issues model

    Raises:
        CodexError: If parsing fails
    """
    lines = review_md.strip().split("\n")
    if not lines:
        raise CodexError("Empty review output")

    last_line = lines[-1].strip()
    try:
        data = json.loads(last_line)
        return Issues.model_validate(data)
    except json.JSONDecodeError as e:
        raise CodexError(f"Invalid JSON in review last line: {e}") from e
    except Exception as e:
        raise CodexError(f"Failed to parse issues: {e}") from e


def extract_revised_plan(codex_output: str) -> str:
    """Extract 'Revised Plan' section from codex output.

    Looks for a section starting with "## Revised Plan" or "# Revised Plan"
    and extracts all content until the next top-level header.

    Args:
        codex_output: Full codex output

    Returns:
        Extracted revised plan content

    Raises:
        CodexError: If no 'Revised Plan' section found
    """
    lines = codex_output.split("\n")
    in_section = False
    section_lines: list[str] = []

    for line in lines:
        if (
            line.strip().lower().startswith("## revised plan")
            or line.strip().lower() == "# revised plan"
        ):
            in_section = True
            continue
        if in_section:
            # Stop at next h1/h2 header
            if line.startswith("# ") or line.startswith("## "):
                break
            section_lines.append(line)

    if not section_lines:
        raise CodexError("No 'Revised Plan' section found in codex output")

    return "\n".join(section_lines).strip()
