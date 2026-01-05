"""Run command implementation."""

from datetime import datetime
from pathlib import Path

import typer
from rich.panel import Panel

from ..config import TaskType, load_config
from ..core import (
    create_meta,
    create_run_directory,
    create_spec_ref,
    generate_plan_prompt,
    generate_research_prompt,
    generate_run_id,
    get_run_dir,
    get_weld_dir,
    write_research_prompt,
)
from ..models import Meta
from ..output import get_output_context
from ..services import GitError, get_repo_root

# Subcommand group for run operations
run_app = typer.Typer(
    help="Run management commands",
    invoke_without_command=True,
)


@run_app.callback()
def run_callback(
    ctx: typer.Context,
    spec: Path | None = typer.Option(None, "--spec", "-s", help="Path to spec file"),
    name: str | None = typer.Option(None, "--name", "-n", help="Run name slug"),
    skip_research: bool = typer.Option(
        False,
        "--skip-research",
        help="Skip research phase, generate plan directly",
    ),
) -> None:
    """Run management commands. Use --spec to start a new run."""
    if ctx.invoked_subcommand is None:
        if spec is not None:
            # Backwards compatibility: weld run --spec works like weld run start --spec
            run_start(spec=spec, name=name, skip_research=skip_research)
        else:
            # No subcommand and no --spec: show help
            import click

            click.echo(ctx.get_help())
            raise typer.Exit(0)


@run_app.command("start")
def run_start(
    spec: Path = typer.Option(..., "--spec", "-s", help="Path to spec file"),
    name: str | None = typer.Option(None, "--name", "-n", help="Run name slug"),
    skip_research: bool = typer.Option(
        False,
        "--skip-research",
        help="Skip research phase, generate plan directly",
    ),
) -> None:
    """Start a new weld run."""
    ctx = get_output_context()

    # Validate spec exists
    if not spec.exists():
        ctx.console.print(f"[red]Error: Spec file not found: {spec}[/red]")
        raise typer.Exit(1)

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    if not weld_dir.exists():
        ctx.console.print("[red]Error: Weld not initialized. Run 'weld init' first.[/red]")
        raise typer.Exit(1)

    config = load_config(weld_dir)

    # Generate run ID
    run_id = generate_run_id(slug=name, spec_path=spec)

    # Get configured model for plan generation
    model_cfg = config.get_task_model(TaskType.PLAN_GENERATION)
    model_info = f" ({model_cfg.model})" if model_cfg.model else ""

    # Read spec content
    spec_content = spec.read_text()

    # Generate appropriate prompt based on research mode
    if skip_research:
        prompt = generate_plan_prompt(spec_content, spec)
    else:
        prompt = generate_research_prompt(spec_content)

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would create run:")
        ctx.console.print(f"  Run ID: {run_id}")
        ctx.console.print(f"  Run directory: {weld_dir / 'runs' / run_id}")
        ctx.console.print(f"  Mode: {'direct planning' if skip_research else 'research-first'}")
        ctx.console.print(f"  Target model: {model_cfg.provider}{model_info}")
        ctx.console.print("\n[cyan][DRY RUN][/cyan] Would write files:")
        if skip_research:
            ctx.console.print("  meta.json, spec.ref.json, plan/plan.prompt.md")
        else:
            ctx.console.print("  meta.json, spec.ref.json, research/prompt.md")
        ctx.console.print("\n" + "=" * 60)
        ctx.console.print(prompt)
        ctx.console.print("=" * 60)
        return

    # Create run directory and metadata (fast, idempotent - no locking needed)
    run_dir = create_run_directory(weld_dir, run_id, skip_research=skip_research)

    # Create metadata
    meta = create_meta(run_id, repo_root, config)
    (run_dir / "meta.json").write_text(meta.model_dump_json(indent=2))

    # Create spec reference
    spec_ref = create_spec_ref(spec)
    (run_dir / "inputs" / "spec.ref.json").write_text(spec_ref.model_dump_json(indent=2))

    # Write prompt to appropriate location
    if skip_research:
        # Direct planning mode - write plan prompt
        prompt_path = run_dir / "plan" / "plan.prompt.md"
        prompt_path.write_text(prompt)

        # Output for direct planning
        ctx.console.print(Panel(f"[bold]Run created:[/bold] {run_id}", style="green"))
        ctx.console.print(f"\n[bold]Target model:[/bold] {model_cfg.provider}{model_info}")
        ctx.console.print(f"[bold]Prompt file:[/bold] {prompt_path}")
        ctx.console.print("\n" + "=" * 60)
        ctx.console.print(prompt)
        ctx.console.print("=" * 60)
        provider = model_cfg.provider
        ctx.console.print(f"\n[bold]Next step:[/bold] Copy prompt to {provider}, then run:")
        ctx.console.print(f"  weld plan import --run {run_id} --file <plan_output.md>")
    else:
        # Research-first mode (default) - write research prompt
        research_dir = run_dir / "research"
        prompt_path = write_research_prompt(research_dir, prompt)

        # Output for research mode
        ctx.console.print(Panel(f"[bold]Run created:[/bold] {run_id}", style="green"))
        ctx.console.print("\n[bold]Mode:[/bold] Research-first")
        ctx.console.print(f"[bold]Target model:[/bold] {model_cfg.provider}{model_info}")
        ctx.console.print(f"[bold]Prompt file:[/bold] {prompt_path}")
        ctx.console.print("\n" + "=" * 60)
        ctx.console.print(prompt)
        ctx.console.print("=" * 60)
        ctx.console.print("\n[bold]Next steps:[/bold]")
        ctx.console.print(f"  1. Copy prompt to {model_cfg.provider}")
        ctx.console.print("  2. Save response as research.md")
        ctx.console.print(f"  3. Run: weld research import --run {run_id} --file research.md")


@run_app.command("abandon")
def run_abandon(
    run: str = typer.Option(..., "--run", "-r", help="Run ID to abandon"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Mark a run as abandoned."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    meta_path = run_dir / "meta.json"

    if not meta_path.exists():
        ctx.error(f"Run not found: {run}")
        raise typer.Exit(1) from None

    meta = Meta.model_validate_json(meta_path.read_text())

    if meta.abandoned:
        ctx.console.print(f"[yellow]Run {run} is already abandoned[/yellow]")
        return

    if not force:
        confirm = typer.confirm(f"Abandon run {run}? This cannot be undone.")
        if not confirm:
            raise typer.Abort()

    meta.abandoned = True
    meta.abandoned_at = datetime.now()
    meta.updated_at = datetime.now()
    meta_path.write_text(meta.model_dump_json(indent=2))

    ctx.success(f"Run {run} marked as abandoned")


@run_app.command("continue")
def run_continue(
    run: str | None = typer.Option(None, "--run", "-r", help="Run ID to continue"),
) -> None:
    """Continue a paused run from where it left off."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)

    # If no run specified, find most recent non-abandoned
    if run is None:
        runs_dir = weld_dir / "runs"
        if not runs_dir.exists():
            ctx.error("No runs found. Start with: weld run start --spec <file>")
            raise typer.Exit(1) from None

        for run_dir in sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            meta_path = run_dir / "meta.json"
            if meta_path.exists():
                meta = Meta.model_validate_json(meta_path.read_text())
                if not meta.abandoned:
                    run = run_dir.name
                    break

        if run is None:
            ctx.error("No active runs found")
            raise typer.Exit(1) from None

    # Delegate to status to show next action
    from .status import status as status_cmd

    status_cmd(run=run)
