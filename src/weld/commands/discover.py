"""Discover workflow CLI commands."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from ..config import load_config
from ..core import get_weld_dir
from ..core.discover_engine import generate_discover_prompt, get_discover_dir
from ..core.run_manager import create_meta, create_run_directory, hash_config
from ..models import DiscoverMeta
from ..output import get_output_context
from ..services import ClaudeError, GitError, get_repo_root, run_claude

discover_app = typer.Typer(
    help="Analyze codebase and generate architecture documentation",
    invoke_without_command=True,
)


@discover_app.callback(invoke_without_command=True)
def discover(
    ctx: typer.Context,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Path to write discover output",
        ),
    ] = None,
    focus: Annotated[
        str | None,
        typer.Option(
            "--focus",
            "-f",
            help="Specific areas to focus on",
        ),
    ] = None,
    prompt_only: Annotated[
        bool,
        typer.Option(
            "--prompt-only",
            help="Only generate prompt without running Claude",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress Claude output (only show result)",
        ),
    ] = False,
) -> None:
    """Analyze codebase and generate architecture documentation.

    Runs Claude to analyze the codebase and writes the output to --output.
    Use --prompt-only to generate the prompt without running Claude.
    """
    # If a subcommand is invoked, skip this callback
    if ctx.invoked_subcommand is not None:
        return

    # Require --output when running discover directly
    if output is None:
        out_ctx = get_output_context()
        out_ctx.console.print("[red]Error: --output is required[/red]")
        out_ctx.console.print("\nUsage: weld discover --output <path>")
        raise typer.Exit(1)

    _run_discover(output, focus, prompt_only, quiet)


def _run_discover(output: Path, focus: str | None, prompt_only: bool, quiet: bool) -> None:
    """Execute the discover workflow."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    if not weld_dir.exists():
        ctx.console.print("[red]Error: Weld not initialized. Run 'weld init' first.[/red]")
        raise typer.Exit(1)

    config = load_config(repo_root)

    # Generate run ID for discover
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-discover")

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would create discover run:")
        ctx.console.print(f"  Run ID: {run_id}")
        ctx.console.print(f"  Output: {output}")
        if not prompt_only:
            ctx.console.print("  Action: Run Claude to analyze codebase")
        return

    # Create run directory structure (so weld status works)
    run_dir = create_run_directory(weld_dir, run_id, skip_research=True)

    # Create and save metadata
    meta = create_meta(run_id, repo_root, config)
    (run_dir / "meta.json").write_text(meta.model_dump_json(indent=2))

    # Also create discover artifact directory
    discover_dir = get_discover_dir(weld_dir)
    artifact_dir = discover_dir / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Generate and write prompt
    prompt = generate_discover_prompt(focus)
    prompt_path = artifact_dir / "prompt.md"
    prompt_path.write_text(prompt)

    # Create and save discover metadata
    discover_meta = DiscoverMeta(
        discover_id=run_id,
        config_hash=hash_config(config),
        output_path=output,
    )
    meta_path = artifact_dir / "meta.json"
    meta_path.write_text(discover_meta.model_dump_json(indent=2))

    # Show run created
    ctx.console.print(Panel(f"[bold]Discover run:[/bold] {run_id}", style="green"))
    ctx.console.print(f"[dim]Prompt: .weld/discover/{run_id}/prompt.md[/dim]")

    if prompt_only:
        ctx.console.print(f"\n[bold]Prompt generated.[/bold] Output path: {output}")
        ctx.console.print("\n[bold]Next steps:[/bold]")
        ctx.console.print("  1. Copy prompt.md content to Claude")
        ctx.console.print("  2. Save response to the output path")
        ctx.console.print(f"  3. Run: weld run start --spec {output}")
        return

    # Run Claude directly with streaming
    ctx.console.print("\n[bold]Running Claude...[/bold]\n")

    # Get claude config from weld config
    claude_exec = config.claude.exec if config.claude else "claude"

    try:
        result = run_claude(
            prompt=prompt,
            exec_path=claude_exec,
            cwd=repo_root,
            stream=not quiet,
        )
    except ClaudeError as e:
        ctx.console.print(f"\n[red]Error: Claude failed: {e}[/red]")
        raise typer.Exit(1) from None

    # Ensure output directory exists
    output.parent.mkdir(parents=True, exist_ok=True)

    # Write output
    output.write_text(result)

    ctx.console.print(f"\n[green]✓ Architecture documentation written to {output}[/green]")
    ctx.console.print(f"\n[bold]Next step:[/bold] weld run start --spec {output}")


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
