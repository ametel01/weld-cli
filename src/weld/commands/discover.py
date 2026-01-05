"""Discover workflow CLI commands."""

from datetime import datetime
from pathlib import Path

import typer

from ..config import load_config
from ..core import get_weld_dir
from ..core.discover_engine import generate_discover_prompt, get_discover_dir
from ..core.run_manager import hash_config
from ..models import DiscoverMeta
from ..output import get_output_context
from ..services import GitError, get_repo_root

discover_app = typer.Typer(help="Discover workflow commands")


@discover_app.command("prompt")
def discover_prompt(
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Path to write discover output",
    ),
    focus: str | None = typer.Option(
        None,
        "--focus",
        "-f",
        help="Specific areas to focus on",
    ),
) -> None:
    """Analyze codebase and generate architecture documentation prompt."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    config = load_config(repo_root)

    # Generate discover ID
    discover_id = datetime.now().strftime("%Y%m%d-%H%M%S-discover")

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would write prompt to:")
        ctx.console.print(f"  .weld/discover/{discover_id}/prompt.md")
        ctx.console.print(f"  .weld/discover/{discover_id}/meta.json")
        ctx.console.print(f"\nOutput path: {output}")
        return

    # Create discover directory and subdirectory
    discover_dir = get_discover_dir(weld_dir)
    artifact_dir = discover_dir / discover_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Generate and write prompt
    prompt = generate_discover_prompt(focus)
    prompt_path = artifact_dir / "prompt.md"
    prompt_path.write_text(prompt)

    # Create and save metadata
    meta = DiscoverMeta(
        discover_id=discover_id,
        config_hash=hash_config(config),
        output_path=output,
    )
    meta_path = artifact_dir / "meta.json"
    meta_path.write_text(meta.model_dump_json(indent=2))

    ctx.console.print(
        f"[green]Discover prompt written to .weld/discover/{discover_id}/prompt.md[/green]"
    )
    ctx.console.print(f"\nOutput will be written to: {output}")
    ctx.console.print("\n[bold]Next steps:[/bold]")
    ctx.console.print("  1. Copy prompt.md content to Claude")
    ctx.console.print("  2. Save response to the output path")
    ctx.console.print(f"  3. The output at {output} can be used as input to 'weld run --spec'")


def _get_discover_artifacts(weld_dir: Path) -> list[Path]:
    """Get list of discover artifacts sorted by modification time (newest first).

    Args:
        weld_dir: Path to .weld directory

    Returns:
        List of artifact directories, empty list if none exist
    """
    discover_dir = weld_dir / "discover"
    if not discover_dir.exists():
        return []

    artifacts = [p for p in discover_dir.iterdir() if p.is_dir()]
    return sorted(artifacts, key=lambda p: p.stat().st_mtime, reverse=True)


@discover_app.command("show")
def discover_show(
    discover_id: str | None = typer.Option(
        None,
        "--id",
        help="Discover ID (defaults to most recent)",
    ),
) -> None:
    """Show discover prompt content."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    artifacts = _get_discover_artifacts(weld_dir)

    if not artifacts:
        ctx.console.print("[red]Error: No discover artifacts found[/red]")
        raise typer.Exit(1)

    # Find the specific or most recent discover
    if discover_id:
        discover_dir = get_discover_dir(weld_dir)
        artifact_dir = discover_dir / discover_id
        if not artifact_dir.exists():
            ctx.console.print(f"[red]Error: Discover not found: {discover_id}[/red]")
            raise typer.Exit(1)
    else:
        # Use most recent
        artifact_dir = artifacts[0]

    prompt_path = artifact_dir / "prompt.md"
    if prompt_path.exists():
        ctx.console.print(prompt_path.read_text())
    else:
        ctx.console.print("[red]Error: Prompt file not found[/red]")
        raise typer.Exit(1)


@discover_app.command("list")
def discover_list() -> None:
    """List all discover artifacts."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    artifacts = _get_discover_artifacts(weld_dir)

    if not artifacts:
        ctx.console.print("No discover artifacts found.")
        return

    ctx.console.print("[bold]Discover artifacts:[/bold]\n")
    for artifact in artifacts:
        prompt_path = artifact / "prompt.md"
        status = "[green]ready[/green]" if prompt_path.exists() else "[yellow]pending[/yellow]"
        ctx.console.print(f"  {artifact.name}  {status}")
