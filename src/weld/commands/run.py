"""Run command implementation."""

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
    get_weld_dir,
    write_research_prompt,
)
from ..output import get_output_context
from ..services import GitError, get_repo_root


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
