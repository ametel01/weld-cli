"""Commit command implementation."""

import typer

from ..config import load_config
from ..core import get_weld_dir, log_command
from ..output import get_output_context
from ..services import (
    GitError,
    TranscriptError,
    commit_file,
    get_repo_root,
    has_staged_changes,
    run_transcript_gist,
    stage_all,
)


def commit(
    message: str = typer.Option(..., "-m", help="Commit message"),
    all: bool = typer.Option(False, "--all", "-a", help="Stage all changes"),
    skip_transcript: bool = typer.Option(False, "--skip-transcript", help="Skip transcript upload"),
) -> None:
    """Create commit with transcript trailer."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)

    # Check if weld is initialized
    if not weld_dir.exists():
        ctx.error("Weld not initialized. Run 'weld init' first.")
        raise typer.Exit(1) from None

    config = load_config(weld_dir)

    # Stage if requested
    if all:
        stage_all(cwd=repo_root)

    # Verify staged changes exist
    if not has_staged_changes(cwd=repo_root):
        ctx.error("No staged changes to commit")
        raise typer.Exit(20) from None

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would create commit:")
        ctx.console.print(f"  Message: {message}")
        ctx.console.print(f"  Stage all: {all}")
        if not skip_transcript:
            ctx.console.print("  Would upload transcript gist and add trailer")
        return

    # Build commit message with transcript trailer
    commit_msg = message
    gist_url = None

    if not skip_transcript:
        ctx.console.print("[cyan]Uploading transcript...[/cyan]")
        try:
            result = run_transcript_gist(
                exec_path=config.claude.transcripts.exec,
                visibility=config.claude.transcripts.visibility,
                cwd=repo_root,
            )
            if result.gist_url:
                gist_url = result.gist_url
                commit_msg = f"{message}\n\n{config.git.commit_trailer_key}: {gist_url}"
            else:
                ctx.console.print("[yellow]Warning: Could not get transcript gist URL[/yellow]")
        except TranscriptError as e:
            ctx.console.print(f"[yellow]Warning: Transcript upload failed: {e}[/yellow]")

    # Write message to temp file and commit
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(commit_msg)
        msg_file = Path(f.name)

    try:
        sha = commit_file(msg_file, cwd=repo_root)
    except GitError as e:
        msg_file.unlink()
        ctx.error(f"Commit failed: {e}")
        raise typer.Exit(22) from None
    finally:
        if msg_file.exists():
            msg_file.unlink()

    ctx.success(f"Committed: {sha[:8]}")
    if gist_url:
        ctx.console.print(f"  Transcript: {gist_url}")

    # Log to history
    log_command(weld_dir, "commit", "", sha)
