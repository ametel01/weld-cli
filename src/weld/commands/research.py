"""Research phase CLI commands."""

from pathlib import Path

import typer

from ..core import (
    create_version_snapshot,
    get_research_content,
    get_run_dir,
    get_weld_dir,
    import_research,
    update_run_meta_version,
)
from ..output import get_output_context
from ..services import GitError, get_repo_root

research_app = typer.Typer(help="Research phase commands")


@research_app.command("prompt")
def research_prompt(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
) -> None:
    """Display the research prompt for a run."""
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

    research_dir = run_dir / "research"

    if not research_dir.exists():
        ctx.console.print("[red]Error: Run was created with --skip-research[/red]")
        raise typer.Exit(1)

    prompt_path = research_dir / "prompt.md"
    if prompt_path.exists():
        ctx.console.print(prompt_path.read_text())
    else:
        ctx.console.print("[red]Error: Research prompt not yet generated[/red]")
        raise typer.Exit(1)


@research_app.command("import")
def research_import_cmd(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    file: Path = typer.Option(..., "--file", "-f", help="Research file from AI"),
) -> None:
    """Import AI-generated research document."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    if not file.exists():
        ctx.console.print(f"[red]Error: File not found: {file}[/red]")
        raise typer.Exit(1)

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)

    if not run_dir.exists():
        ctx.console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    research_dir = run_dir / "research"

    if not research_dir.exists():
        ctx.console.print("[red]Error: Run was created with --skip-research[/red]")
        raise typer.Exit(1)

    # Check if research already exists - create version snapshot
    existing_research = research_dir / "research.md"
    has_existing = existing_research.exists()

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would import research:")
        ctx.console.print(f"  Run: {run}")
        ctx.console.print(f"  File: {file}")
        if has_existing:
            ctx.console.print("  Previous research: would be versioned")
        ctx.console.print("\n[cyan][DRY RUN][/cyan] Would write:")
        ctx.console.print("  research/research.md")
        return

    # Create version snapshot before overwriting
    if has_existing:
        version = create_version_snapshot(
            research_dir,
            "research.md",
            trigger_reason="import",
        )
        ctx.console.print(f"Previous research saved as v{version}")
        # Update run meta with new version number (next version after import)
        update_run_meta_version(run_dir, "research", version + 1)

    content = file.read_text()
    import_research(research_dir, content)
    ctx.console.print(f"[green]Research imported to {run}/research/research.md[/green]")
    ctx.console.print("\n[bold]Next step:[/bold] Generate plan prompt:")
    ctx.console.print(f"  weld plan prompt --run {run}")


@research_app.command("show")
def research_show(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
) -> None:
    """Display the current research document."""
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

    research_dir = run_dir / "research"

    if not research_dir.exists():
        ctx.console.print("[red]Error: Run was created with --skip-research[/red]")
        raise typer.Exit(1)

    content = get_research_content(research_dir)
    if content:
        ctx.console.print(content)
    else:
        ctx.console.print(
            "[red]Error: No research document found. Run 'weld research import' first.[/red]"
        )
        raise typer.Exit(1)
