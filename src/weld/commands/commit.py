"""Commit and transcript command implementations."""

import typer
from rich.console import Console

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
from ..services import GitError, get_repo_root

console = Console()


def transcript_gist(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
) -> None:
    """Generate transcript gist."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    console.print("[cyan]Generating transcript gist...[/cyan]")
    result = ensure_transcript_gist(run_dir, config, repo_root)

    if result.gist_url:
        console.print(f"[green]Gist URL:[/green] {result.gist_url}")
        if result.preview_url:
            console.print(f"[green]Preview:[/green] {result.preview_url}")
    else:
        console.print("[red]Failed to generate gist[/red]")
        raise typer.Exit(21)

    if result.warnings:
        for w in result.warnings:
            console.print(f"[yellow]Warning: {w}[/yellow]")


def commit(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    message: str = typer.Option(..., "-m", help="Commit message"),
    all: bool = typer.Option(False, "--all", "-a", help="Stage all changes"),
    staged: bool = typer.Option(True, "--staged", help="Commit staged changes only"),
) -> None:
    """Create commit with transcript trailer."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    if not run_dir.exists():
        console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    # Acquire lock for commit
    try:
        acquire_lock(weld_dir, run, f"commit -m '{message[:30]}...'")
    except LockError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    try:
        sha = do_commit(
            run_dir=run_dir,
            message=message,
            config=config,
            repo_root=repo_root,
            stage_all_changes=all,
        )
        console.print(f"[bold green]Committed:[/bold green] {sha[:8]}")
    except CommitError as e:
        if "No staged changes" in str(e):
            console.print("[red]Error: No staged changes to commit[/red]")
            raise typer.Exit(20) from None
        elif "gist" in str(e).lower():
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(21) from None
        else:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(22) from None
    finally:
        release_lock(weld_dir)


def list_runs_cmd() -> None:
    """List all runs."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    runs = list_runs(weld_dir)

    if not runs:
        console.print("[yellow]No runs found[/yellow]")
        return

    console.print("[bold]Runs:[/bold]")
    for r in runs:
        console.print(f"  {r}")
