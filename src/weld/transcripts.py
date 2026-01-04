"""Transcript gist generation for weld."""

import re
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from .constants import TRANSCRIPT_TIMEOUT


class TranscriptResult(BaseModel):
    """Result from claude-code-transcripts."""

    gist_url: str | None = None
    preview_url: str | None = None
    raw_output: str
    warnings: list[str] = Field(default_factory=list)


class TranscriptError(Exception):
    """Transcript tool failed."""

    pass


def run_transcript_gist(
    exec_path: str = "claude-code-transcripts",
    visibility: str = "secret",
    cwd: Path | None = None,
    timeout: int | None = None,
) -> TranscriptResult:
    """Run transcript tool to create gist.

    Args:
        exec_path: Path to claude-code-transcripts executable
        visibility: Gist visibility ("secret" or "public")
        cwd: Working directory
        timeout: Optional timeout in seconds (default: 60)

    Returns:
        TranscriptResult with parsed URLs and warnings

    Raises:
        TranscriptError: If transcript tool times out
    """
    timeout = timeout or TRANSCRIPT_TIMEOUT

    args = [exec_path, "--gist"]
    if visibility == "public":
        args.append("--public")

    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise TranscriptError(f"Transcript tool timed out after {timeout} seconds") from e

    output = result.stdout + result.stderr
    warnings: list[str] = []

    # Check for auto-detect warning
    if "Could not auto-detect GitHub repo" in output:
        warnings.append("Could not auto-detect GitHub repo")

    # Parse gist URL
    gist_match = re.search(r"Gist:\s*(https://gist\.github\.com/\S+)", output)
    gist_url = gist_match.group(1) if gist_match else None

    # Parse preview URL
    preview_match = re.search(r"Preview:\s*(https://\S+)", output)
    preview_url = preview_match.group(1) if preview_match else None

    return TranscriptResult(
        gist_url=gist_url,
        preview_url=preview_url,
        raw_output=output,
        warnings=warnings,
    )
