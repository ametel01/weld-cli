"""Codex integration for weld."""

import json
import subprocess
from pathlib import Path

from .models import Issues


class CodexError(Exception):
    """Codex invocation failed."""

    pass


def run_codex(
    prompt: str,
    exec_path: str = "codex",
    sandbox: str = "read-only",
    model: str | None = None,
    cwd: Path | None = None,
) -> str:
    """Run codex with prompt and return output.

    Args:
        prompt: The prompt to send to Codex
        exec_path: Path to codex executable
        sandbox: Sandbox mode (read-only, network-only, etc.)
        model: Model to use (e.g., o3, gpt-4o). If None, uses codex default.
        cwd: Working directory

    Returns:
        Codex stdout output

    Raises:
        CodexError: If codex fails or returns non-zero
    """
    cmd = [exec_path, "-p", prompt, "--sandbox", sandbox]
    if model:
        cmd.extend(["--model", model])

    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CodexError(f"Codex failed: {result.stderr}")
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
        raise CodexError(f"Invalid JSON in review last line: {e}")
    except Exception as e:
        raise CodexError(f"Failed to parse issues: {e}")


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
        if line.strip().lower().startswith("## revised plan") or line.strip().lower() == "# revised plan":
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
