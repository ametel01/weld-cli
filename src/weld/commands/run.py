"""Run command implementation."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from ..config import TaskType, load_config
from ..core import (
    create_meta,
    create_run_directory,
    create_spec_ref,
    generate_plan_prompt,
    generate_run_id,
    get_weld_dir,
)
from ..services import GitError, get_repo_root

console = Console()


def run_start(
    spec: Path = typer.Option(..., "--spec", "-s", help="Path to spec file"),
    name: str | None = typer.Option(None, "--name", "-n", help="Run name slug"),
) -> None:
    """Start a new weld run."""
    # Validate spec exists
    if not spec.exists():
        console.print(f"[red]Error: Spec file not found: {spec}[/red]")
        raise typer.Exit(1)

    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    if not weld_dir.exists():
        console.print("[red]Error: Weld not initialized. Run 'weld init' first.[/red]")
        raise typer.Exit(1)

    config = load_config(weld_dir)

    # Generate run ID
    run_id = generate_run_id(slug=name, spec_path=spec)

    # Create run directory and metadata (fast, idempotent - no locking needed)
    run_dir = create_run_directory(weld_dir, run_id)

    # Create metadata
    meta = create_meta(run_id, repo_root, config)
    (run_dir / "meta.json").write_text(meta.model_dump_json(indent=2))

    # Create spec reference
    spec_ref = create_spec_ref(spec)
    (run_dir / "inputs" / "spec.ref.json").write_text(spec_ref.model_dump_json(indent=2))

    # Generate plan prompt
    spec_content = spec.read_text()
    plan_prompt = generate_plan_prompt(spec_content, spec)

    # Get configured model for plan generation
    model_cfg = config.get_task_model(TaskType.PLAN_GENERATION)
    model_info = f" ({model_cfg.model})" if model_cfg.model else ""

    prompt_path = run_dir / "plan" / "plan.prompt.md"
    prompt_path.write_text(plan_prompt)

    # Output
    console.print(Panel(f"[bold]Run created:[/bold] {run_id}", style="green"))
    console.print(f"\n[bold]Target model:[/bold] {model_cfg.provider}{model_info}")
    console.print(f"[bold]Prompt file:[/bold] {prompt_path}")
    console.print("\n" + "=" * 60)
    console.print(plan_prompt)
    console.print("=" * 60)
    console.print(f"\n[bold]Next step:[/bold] Copy prompt to {model_cfg.provider}, then run:")
    console.print(f"  weld plan import --run {run_id} --file <plan_output.md>")
