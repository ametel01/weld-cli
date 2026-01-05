"""Plan command implementations."""

import json
from pathlib import Path

import typer
from rich.console import Console

from ..config import TaskType, load_config
from ..core import (
    LockError,
    acquire_lock,
    generate_codex_review_prompt,
    get_run_dir,
    get_weld_dir,
    parse_steps,
    release_lock,
)
from ..services import CodexError, GitError, extract_revised_plan, get_repo_root, run_codex

console = Console()


def plan_import(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    file: Path = typer.Option(..., "--file", "-f", help="Plan file from Claude"),
) -> None:
    """Import Claude's plan output."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)

    if not run_dir.exists():
        console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    if not file.exists():
        console.print(f"[red]Error: Plan file not found: {file}[/red]")
        raise typer.Exit(1)

    # Acquire lock for plan import
    try:
        acquire_lock(weld_dir, run, f"plan import --file {file}")
    except LockError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    try:
        plan_content = file.read_text()

        # Write verbatim output
        (run_dir / "plan" / "output.md").write_text(plan_content)

        # Parse and validate
        steps, warnings = parse_steps(plan_content)

        # Update meta with warnings
        meta_path = run_dir / "meta.json"
        meta = json.loads(meta_path.read_text())
        meta["plan_parse_warnings"] = warnings
        meta_path.write_text(json.dumps(meta, indent=2, default=str))

        # Write normalized plan
        (run_dir / "plan" / "plan.raw.md").write_text(plan_content)

        console.print(f"[green]Imported plan with {len(steps)} steps[/green]")
        if warnings:
            for w in warnings:
                console.print(f"[yellow]Warning: {w}[/yellow]")

        console.print("\n[bold]Next step:[/bold] Review plan with Codex:")
        console.print(f"  weld plan review --run {run} --apply")
    finally:
        release_lock(weld_dir)


def plan_review(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    apply: bool = typer.Option(False, "--apply", help="Apply revised plan"),
) -> None:
    """Run Codex review on the plan."""
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

    # Load plan
    plan_raw = run_dir / "plan" / "plan.raw.md"
    if not plan_raw.exists():
        console.print("[red]Error: No plan imported yet. Run 'weld plan import' first.[/red]")
        raise typer.Exit(1)

    # Acquire lock for plan review
    try:
        acquire_lock(weld_dir, run, "plan review")
    except LockError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    try:
        plan_content = plan_raw.read_text()

        # Generate Codex prompt
        codex_prompt = generate_codex_review_prompt(plan_content)
        (run_dir / "plan" / "codex.prompt.md").write_text(codex_prompt)

        # Get model config for plan review task
        model_cfg = config.get_task_model(TaskType.PLAN_REVIEW)
        model_info = f" ({model_cfg.model})" if model_cfg.model else ""
        console.print(f"[cyan]Running {model_cfg.provider} plan review{model_info}...[/cyan]")

        try:
            codex_output = run_codex(
                prompt=codex_prompt,
                exec_path=model_cfg.exec or config.codex.exec,
                sandbox=config.codex.sandbox,
                model=model_cfg.model,
                cwd=repo_root,
            )
            (run_dir / "plan" / "codex.output.md").write_text(codex_output)

            if apply:
                revised = extract_revised_plan(codex_output)
                (run_dir / "plan" / "plan.final.md").write_text(revised)
                console.print("[green]Revised plan saved to plan.final.md[/green]")

            console.print("[green]Plan review complete[/green]")
            console.print("\n[bold]Next step:[/bold] Select a step to implement:")
            console.print(f"  weld step select --run {run} --n 1")

        except CodexError as e:
            console.print(f"[red]Codex error: {e}[/red]")
            raise typer.Exit(12) from None
    finally:
        release_lock(weld_dir)
