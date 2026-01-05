"""Commit and transcript command implementations."""

import typer

from ..config import load_config
from ..core import (
    CommitError,
    LockError,
    acquire_lock,
    do_commit,
    ensure_transcript_gist,
    get_run_dir,
    get_weld_dir,
    list_runs,
    release_lock,
)
from ..output import get_output_context
from ..services import GitError, get_repo_root


def transcript_gist(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
) -> None:
    """Generate transcript gist."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would generate transcript gist for run:")
        ctx.console.print(f"  Run: {run}")
        ctx.console.print(f"  Run directory: {run_dir}")
        ctx.console.print("  Would upload gist via claude-code-transcripts")
        return

    ctx.console.print("[cyan]Generating transcript gist...[/cyan]")
    result = ensure_transcript_gist(run_dir, config, repo_root)

    if result.gist_url:
        ctx.console.print(f"[green]Gist URL:[/green] {result.gist_url}")
        if result.preview_url:
            ctx.console.print(f"[green]Preview:[/green] {result.preview_url}")
    else:
        ctx.console.print("[red]Failed to generate gist[/red]")
        raise typer.Exit(21)

    if result.warnings:
        for w in result.warnings:
            ctx.console.print(f"[yellow]Warning: {w}[/yellow]")


def commit(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    message: str = typer.Option(..., "-m", help="Commit message"),
    all: bool = typer.Option(False, "--all", "-a", help="Stage all changes"),
    staged: bool = typer.Option(True, "--staged", help="Commit staged changes only"),
) -> None:
    """Create commit with transcript trailer."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)

    if not run_dir.exists():
        ctx.console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would create commit:")
        ctx.console.print(f"  Run: {run}")
        ctx.console.print(f"  Message: {message}")
        ctx.console.print(f"  Stage all: {all}")
        ctx.console.print("  Would generate transcript gist and add trailer")
        ctx.console.print("  Would create git commit")
        return

    config = load_config(weld_dir)

    # Acquire lock for commit
    try:
        acquire_lock(weld_dir, run, f"commit -m '{message[:30]}...'")
    except LockError as e:
        ctx.console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    try:
        sha = do_commit(
            run_dir=run_dir,
            message=message,
            config=config,
            repo_root=repo_root,
            stage_all_changes=all,
        )
        ctx.console.print(f"[bold green]Committed:[/bold green] {sha[:8]}")
    except CommitError as e:
        if "No staged changes" in str(e):
            ctx.console.print("[red]Error: No staged changes to commit[/red]")
            raise typer.Exit(20) from None
        elif "gist" in str(e).lower():
            ctx.console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(21) from None
        else:
            ctx.console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(22) from None
    finally:
        release_lock(weld_dir)


def list_runs_cmd() -> None:
    """List all runs."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    runs = list_runs(weld_dir)

    if not runs:
        ctx.console.print("[yellow]No runs found[/yellow]")
        return

    ctx.console.print("[bold]Runs:[/bold]")
    for r in runs:
        ctx.console.print(f"  {r}")
