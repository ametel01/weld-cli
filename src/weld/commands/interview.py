"""Interview CLI command for specification refinement."""

from pathlib import Path
from typing import Annotated

import typer

from ..core import get_weld_dir
from ..core.interview_engine import run_interview_loop
from ..output import get_output_context
from ..services import GitError, get_repo_root, track_session_activity


def interview(
    file: Path = typer.Argument(..., help="Markdown file to refine"),
    focus: str | None = typer.Option(
        None,
        "--focus",
        "-f",
        help="Topic to focus questions on",
    ),
    track: Annotated[
        bool,
        typer.Option("--track", help="Track session activity for this command"),
    ] = False,
) -> None:
    """Interactively refine a specification through Q&A."""
    ctx = get_output_context()

    if not file.exists():
        ctx.console.print(f"[red]Error: File not found: {file}[/red]")
        raise typer.Exit(1) from None

    if file.suffix != ".md":
        ctx.console.print(
            "[yellow]Warning: File is not markdown - interview may not work well[/yellow]"
        )

    # Get repo root and weld dir for session tracking
    try:
        repo_root = get_repo_root()
        weld_dir = get_weld_dir(repo_root)
    except GitError:
        repo_root = None
        weld_dir = None

    def _run_interview() -> bool:
        return run_interview_loop(
            file,
            focus,
            console=ctx.console,
            dry_run=ctx.dry_run,
        )

    try:
        if track and weld_dir and repo_root and weld_dir.exists():
            with track_session_activity(weld_dir, repo_root, "interview"):
                modified = _run_interview()
        else:
            modified = _run_interview()

        if modified:
            ctx.console.print("[green]Document updated[/green]")
        else:
            ctx.console.print("No changes made")
    except KeyboardInterrupt:
        ctx.console.print("\n[yellow]Interview cancelled[/yellow]")
        raise typer.Exit(0) from None
