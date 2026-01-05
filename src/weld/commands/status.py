"""Status command for run overview."""

import typer

from ..core import get_run_dir, get_weld_dir
from ..models import Meta
from ..output import get_output_context
from ..services.git import GitError, get_repo_root


def status(
    run: str | None = typer.Option(
        None,
        "--run",
        "-r",
        help="Run ID (defaults to most recent)",
    ),
) -> None:
    """Show current run status and next action."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)

    # If no run specified, find most recent
    if run is None:
        runs_dir = weld_dir / "runs"
        if not runs_dir.exists():
            ctx.error("No runs found. Start with: weld run start --spec <file>")
            raise typer.Exit(1) from None

        runs = sorted(runs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if not runs:
            ctx.error("No runs found")
            raise typer.Exit(1) from None
        run = runs[0].name

    run_dir = get_run_dir(weld_dir, run)
    meta_path = run_dir / "meta.json"

    if not meta_path.exists():
        ctx.error(f"Run not found: {run}")
        raise typer.Exit(1) from None

    meta = Meta.model_validate_json(meta_path.read_text())

    # Determine current phase
    research_dir = run_dir / "research"
    plan_dir = run_dir / "plan"
    steps_dir = run_dir / "steps"

    ctx.console.print(f"\n[bold]Run:[/bold] {run}")
    ctx.console.print(f"[bold]Branch:[/bold] {meta.branch}")
    ctx.console.print(f"[bold]Created:[/bold] {meta.created_at.strftime('%Y-%m-%d %H:%M')}")

    if meta.abandoned:
        ctx.console.print("[yellow]Status: ABANDONED[/yellow]")
        return

    # Check phases
    if research_dir.exists() and not (research_dir / "research.md").exists():
        ctx.console.print("[yellow]Status: Awaiting research[/yellow]")
        ctx.console.print(f"  Next: weld research import --run {run} --file <research.md>")
        return

    if not (plan_dir / "plan.md").exists() and not (plan_dir / "plan.raw.md").exists():
        ctx.console.print("[yellow]Status: Awaiting plan[/yellow]")
        ctx.console.print(f"  Next: weld plan import --run {run} --file <plan.md>")
        return

    # Check steps
    if steps_dir.exists():
        step_dirs = sorted(d for d in steps_dir.iterdir() if d.is_dir())
        completed = sum(1 for s in step_dirs if (s / "completed").exists())
        skipped = sum(1 for s in step_dirs if (s / "skipped").exists())
        total = len(step_dirs)
        ctx.console.print(f"[bold]Steps:[/bold] {completed}/{total} completed")
        if skipped:
            ctx.console.print(f"  ({skipped} skipped)")

        # Find next incomplete, non-skipped step
        incomplete = [
            s for s in step_dirs if not (s / "completed").exists() and not (s / "skipped").exists()
        ]
        if incomplete:
            next_step = incomplete[0]
            # Extract step number from directory name (e.g., "01-setup" -> 1)
            step_num = int(next_step.name.split("-")[0])
            ctx.console.print(f"  Next: weld step loop --run {run} --n {step_num}")
            return

    ctx.console.print("[green]Status: Ready to commit[/green]")
    ctx.console.print(f"  Next: weld commit --run {run}")
