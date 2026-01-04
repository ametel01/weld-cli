"""Commit handling for weld runs."""

import json
from pathlib import Path

from ..config import WeldConfig
from ..services import (
    TranscriptResult,
    commit_file,
    has_staged_changes,
    run_transcript_gist,
    stage_all,
)


class CommitError(Exception):
    """Commit operation failed."""

    pass


def build_commit_message(
    subject: str,
    run_id: str,
    gist_url: str,
    config: WeldConfig,
    step_summary: str | None = None,
) -> str:
    """Build commit message with trailers.

    Args:
        subject: Commit subject line
        run_id: Run identifier
        gist_url: Transcript gist URL
        config: Weld configuration
        step_summary: Optional step summary to include

    Returns:
        Formatted commit message with trailers
    """
    lines = [subject, ""]

    if step_summary:
        lines.append(step_summary)
        lines.append("")

    # Trailers
    lines.append(f"{config.git.commit_trailer_key}: {gist_url}")

    if config.git.include_run_trailer:
        lines.append(f"Weld-Run: .weld/runs/{run_id}")

    return "\n".join(lines)


def ensure_transcript_gist(
    run_dir: Path,
    config: WeldConfig,
    cwd: Path,
) -> TranscriptResult:
    """Ensure transcript gist exists, creating if needed.

    Args:
        run_dir: Path to run directory
        config: Weld configuration
        cwd: Working directory for transcript tool

    Returns:
        TranscriptResult with gist URL
    """
    transcript_file = run_dir / "commit" / "transcript.json"

    # Check if already exists
    if transcript_file.exists():
        data = json.loads(transcript_file.read_text())
        result = TranscriptResult.model_validate(data)
        if result.gist_url:
            return result

    # Create gist
    result = run_transcript_gist(
        exec_path=config.claude.transcripts.exec,
        visibility=config.claude.transcripts.visibility,
        cwd=cwd,
    )

    # Save result
    transcript_file.parent.mkdir(parents=True, exist_ok=True)
    transcript_file.write_text(result.model_dump_json(indent=2))

    return result


def do_commit(
    run_dir: Path,
    message: str,
    config: WeldConfig,
    repo_root: Path,
    stage_all_changes: bool = False,
) -> str:
    """Perform commit and return SHA.

    Args:
        run_dir: Path to run directory
        message: Commit subject line
        config: Weld configuration
        repo_root: Repository root path
        stage_all_changes: If True, stage all changes before committing

    Returns:
        New commit SHA

    Raises:
        CommitError: If no staged changes or transcript gist fails
    """
    # Stage if requested
    if stage_all_changes:
        stage_all(cwd=repo_root)

    # Verify staged changes exist
    if not has_staged_changes(cwd=repo_root):
        raise CommitError("No staged changes to commit")

    # Ensure transcript gist
    transcript = ensure_transcript_gist(run_dir, config, repo_root)
    if not transcript.gist_url:
        raise CommitError("Failed to get transcript gist URL")

    # Build message
    run_id = run_dir.name
    full_message = build_commit_message(
        subject=message,
        run_id=run_id,
        gist_url=transcript.gist_url,
        config=config,
    )

    # Write message file
    message_file = run_dir / "commit" / "message.txt"
    message_file.parent.mkdir(parents=True, exist_ok=True)
    message_file.write_text(full_message)

    # Commit
    sha = commit_file(message_file, cwd=repo_root)

    # Update summary
    summary_file = run_dir / "summary.md"
    summary = f"# Run: {run_id}\n\n"
    summary += f"- Commit: {sha}\n"
    summary += f"- Transcript: {transcript.gist_url}\n"
    summary_file.write_text(summary)

    return sha
