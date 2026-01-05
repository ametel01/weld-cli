"""Step command implementations."""

import json
import re

import typer

from ..config import TaskType, load_config
from ..core import (
    LockError,
    acquire_lock,
    create_iter_directory,
    create_step_directory,
    generate_fix_prompt,
    generate_impl_prompt,
    get_run_dir,
    get_weld_dir,
    parse_steps,
    release_lock,
    run_step_review,
)
from ..models import Status, Step
from ..output import get_output_context
from ..services import GitError, capture_diff, get_repo_root, write_diff
from ..services.checks import run_checks, write_checks_results


def step_select(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
) -> None:
    """Select a step from the plan."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find plan file
    plan_final = run_dir / "plan" / "plan.final.md"
    plan_raw = run_dir / "plan" / "plan.raw.md"
    plan_path = plan_final if plan_final.exists() else plan_raw

    if not plan_path.exists():
        ctx.console.print("[red]Error: No plan found[/red]")
        raise typer.Exit(1)

    # Parse steps
    steps, _ = parse_steps(plan_path.read_text())

    # Find requested step
    step = next((s for s in steps if s.n == n), None)
    if not step:
        available = [s.n for s in steps]
        ctx.console.print(f"[red]Error: Step {n} not found. Available: {available}[/red]")
        raise typer.Exit(1)

    # Get configured model for implementation
    model_cfg = config.get_task_model(TaskType.IMPLEMENTATION)
    model_info = f" ({model_cfg.model})" if model_cfg.model else ""

    # Generate implementation prompt (read-only, needed for dry-run display)
    impl_prompt = generate_impl_prompt(step, config.checks)

    if ctx.dry_run:
        ctx.console.print(f"[cyan][DRY RUN][/cyan] Would select step {n}: {step.title}")
        ctx.console.print(f"  Target model: {model_cfg.provider}{model_info}")
        ctx.console.print("\n[cyan][DRY RUN][/cyan] Would create:")
        ctx.console.print(f"  Step directory: steps/{n:02d}-{step.title[:20]}...")
        ctx.console.print("  step.json, impl.prompt.md")
        ctx.console.print("\n" + "=" * 60)
        ctx.console.print(impl_prompt)
        ctx.console.print("=" * 60)
        return

    # Create step directory
    step_dir = create_step_directory(run_dir, step)

    # Write step.json
    (step_dir / "step.json").write_text(step.model_dump_json(indent=2))

    prompt_path = step_dir / "prompt" / "impl.prompt.md"
    prompt_path.write_text(impl_prompt)

    ctx.console.print(f"[green]Selected step {n}: {step.title}[/green]")
    ctx.console.print(f"\n[bold]Target model:[/bold] {model_cfg.provider}{model_info}")
    ctx.console.print(f"[bold]Prompt file:[/bold] {prompt_path}")
    ctx.console.print("\n" + "=" * 60)
    ctx.console.print(impl_prompt)
    ctx.console.print("=" * 60)
    ctx.console.print("\n[bold]Next step:[/bold] Start implementation loop:")
    ctx.console.print(f"  weld step loop --run {run} --n {n} --wait")


def step_snapshot(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    iter: int = typer.Option(1, "--iter", "-i", help="Iteration number"),
) -> None:
    """Capture current diff and checks for a step iteration."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find step directory
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    if not step_dirs:
        ctx.console.print(f"[red]Error: Step {n} not selected yet[/red]")
        raise typer.Exit(1)

    step_dir = step_dirs[0]

    if ctx.dry_run:
        # Still capture diff to show info, but don't write
        diff, nonempty = capture_diff(repo_root)
        ctx.console.print("[cyan][DRY RUN][/cyan] Would capture snapshot:")
        ctx.console.print(f"  Step {n}, iteration {iter}")
        ctx.console.print(f"  Diff size: {len(diff)} bytes")
        ctx.console.print(f"  Has changes: {nonempty}")
        ctx.console.print("\n[cyan][DRY RUN][/cyan] Would create:")
        ctx.console.print(f"  Iteration directory: iter/{iter:02d}/")
        ctx.console.print("  diff.patch, checks output files, status.json")
        return

    # Create iteration directory
    iter_dir = create_iter_directory(step_dir, iter)

    # Capture diff
    diff, nonempty = capture_diff(repo_root)
    write_diff(iter_dir / "diff.patch", diff)

    if not nonempty:
        ctx.console.print("[yellow]No changes detected[/yellow]")
        status = Status.model_validate(
            {
                "pass": False,
                "checks_exit_code": -1,
                "diff_nonempty": False,
            }
        )
        (iter_dir / "status.json").write_text(status.model_dump_json(by_alias=True, indent=2))
        raise typer.Exit(0)

    # Run checks
    ctx.console.print("[cyan]Running checks...[/cyan]")
    checks_summary = run_checks(config.checks, repo_root, fail_fast=True)

    # Write per-category output files and summary
    write_checks_results(iter_dir, checks_summary)

    ctx.console.print(f"[green]Snapshot captured for iteration {iter}[/green]")
    ctx.console.print(f"  Diff: {len(diff)} bytes")
    ctx.console.print(f"  Checks exit code: {checks_summary.get_exit_code()}")


def step_review_cmd(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    iter: int = typer.Option(1, "--iter", "-i", help="Iteration number"),
) -> None:
    """Run Codex review on step implementation."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find step
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    if not step_dirs:
        ctx.console.print(f"[red]Error: Step {n} not found[/red]")
        raise typer.Exit(1)

    step_dir = step_dirs[0]
    iter_dir = step_dir / "iter" / f"{iter:02d}"

    # Load step
    step = Step.model_validate(json.loads((step_dir / "step.json").read_text()))

    # Get model config for display
    model_cfg = config.get_task_model(TaskType.IMPLEMENTATION_REVIEW)
    model_info = f" ({model_cfg.model})" if model_cfg.model else ""

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would run Codex review:")
        ctx.console.print(f"  Step {n}, iteration {iter}")
        ctx.console.print(f"  Model: {model_cfg.provider}{model_info}")
        ctx.console.print("\n[cyan][DRY RUN][/cyan] Would:")
        ctx.console.print("  1. Load diff and checks from iteration directory")
        ctx.console.print("  2. Run Codex review")
        ctx.console.print("  3. Write codex.review.md, codex.issues.json, status.json")
        return

    # Load diff and checks
    diff = (iter_dir / "diff.patch").read_text() if (iter_dir / "diff.patch").exists() else ""
    checks = (iter_dir / "checks.txt").read_text() if (iter_dir / "checks.txt").exists() else ""

    # Parse checks exit code
    exit_match = re.search(r"exit_code:\s*(\d+)", checks)
    checks_exit = int(exit_match.group(1)) if exit_match else -1

    # Run review
    ctx.console.print("[cyan]Running Codex review...[/cyan]")

    review_md, issues, status = run_step_review(
        step=step,
        diff=diff,
        checks_output=checks,
        checks_exit_code=checks_exit,
        config=config,
        cwd=repo_root,
    )

    # Write results
    (iter_dir / "codex.review.md").write_text(review_md)
    (iter_dir / "codex.issues.json").write_text(issues.model_dump_json(by_alias=True, indent=2))
    (iter_dir / "status.json").write_text(status.model_dump_json(by_alias=True, indent=2))

    if status.pass_:
        ctx.console.print("[bold green]Review passed![/bold green]")
    else:
        ctx.console.print(
            f"[red]Review found {status.issue_count} issues ({status.blocker_count} blockers)[/red]"
        )


def step_fix_prompt(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    iter: int = typer.Option(..., "--iter", "-i", help="Current iteration"),
) -> None:
    """Generate fix prompt for next iteration."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)

    # Find step
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    if not step_dirs:
        ctx.console.print(f"[red]Error: Step {n} not found[/red]")
        raise typer.Exit(1)

    step_dir = step_dirs[0]
    iter_dir = step_dir / "iter" / f"{iter:02d}"

    # Load step and issues
    step = Step.model_validate(json.loads((step_dir / "step.json").read_text()))
    issues = json.loads((iter_dir / "codex.issues.json").read_text())

    # Generate fix prompt
    config = load_config(weld_dir)
    model_cfg = config.get_task_model(TaskType.FIX_GENERATION)
    model_info = f" ({model_cfg.model})" if model_cfg.model else ""

    fix_prompt = generate_fix_prompt(step, issues, iter)
    fix_path = step_dir / "prompt" / f"fix.prompt.iter{iter + 1:02d}.md"

    if ctx.dry_run:
        ctx.console.print(f"[cyan][DRY RUN][/cyan] Would generate fix prompt for step {n}")
        ctx.console.print(f"  Current iteration: {iter}")
        ctx.console.print(f"  Target model: {model_cfg.provider}{model_info}")
        ctx.console.print(f"  Would write: {fix_path}")
        ctx.console.print("\n" + "=" * 60)
        ctx.console.print(fix_prompt)
        ctx.console.print("=" * 60)
        return

    fix_path.write_text(fix_prompt)

    ctx.console.print(f"[green]Fix prompt written to:[/green] {fix_path}")
    ctx.console.print(f"[bold]Target model:[/bold] {model_cfg.provider}{model_info}")
    ctx.console.print("\n" + "=" * 60)
    ctx.console.print(fix_prompt)
    ctx.console.print("=" * 60)


def step_loop(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    max: int | None = typer.Option(None, "--max", "-m", help="Max iterations"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for user between iterations"),
) -> None:
    """Run implement-review-fix loop for a step."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Get model info for display
    impl_model_cfg = config.get_task_model(TaskType.IMPLEMENTATION)
    impl_model_info = f" ({impl_model_cfg.model})" if impl_model_cfg.model else ""
    review_model_cfg = config.get_task_model(TaskType.IMPLEMENTATION_REVIEW)
    review_model_info = f" ({review_model_cfg.model})" if review_model_cfg.model else ""

    if ctx.dry_run:
        ctx.console.print(f"[cyan][DRY RUN][/cyan] Would run step loop for step {n}")
        ctx.console.print(f"  Implementation model: {impl_model_cfg.provider}{impl_model_info}")
        ctx.console.print(f"  Review model: {review_model_cfg.provider}{review_model_info}")
        ctx.console.print(f"  Max iterations: {max or 'unlimited'}")
        ctx.console.print(f"  Wait mode: {wait}")
        ctx.console.print("\n[cyan][DRY RUN][/cyan] Would:")
        ctx.console.print("  1. Select step if not already selected")
        ctx.console.print("  2. Run implement-review-fix loop until pass or max iterations")
        ctx.console.print("  3. Capture diff and run checks each iteration")
        ctx.console.print("  4. Generate fix prompts if review fails")
        return

    # Acquire lock for the duration of the loop
    try:
        acquire_lock(weld_dir, run, f"step loop --n {n}")
    except LockError as e:
        ctx.console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None

    try:
        # Find or select step
        steps_dir = run_dir / "steps"
        step_dirs = (
            [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]
            if steps_dir.exists()
            else []
        )

        if not step_dirs:
            # Auto-select step
            ctx.console.print(f"[yellow]Step {n} not selected, selecting now...[/yellow]")
            step_select(run=run, n=n)
            step_dirs = [
                d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")
            ]

        step_dir = step_dirs[0]

        # Load step
        step = Step.model_validate(json.loads((step_dir / "step.json").read_text()))

        impl_prompt_path = step_dir / "prompt" / "impl.prompt.md"
        ctx.console.print(
            f"\n[bold]Implementation model:[/bold] {impl_model_cfg.provider}{impl_model_info}"
        )
        ctx.console.print(
            f"[bold]Review model:[/bold] {review_model_cfg.provider}{review_model_info}"
        )
        ctx.console.print(f"[bold]Implementation prompt:[/bold] {impl_prompt_path}")
        ctx.console.print("\n" + "=" * 60)
        ctx.console.print(impl_prompt_path.read_text())
        ctx.console.print("=" * 60 + "\n")

        # Run loop
        from ..core import run_step_loop

        result = run_step_loop(
            run_dir=run_dir,
            step=step,
            config=config,
            repo_root=repo_root,
            max_iterations=max,
            wait_mode=wait,
            weld_dir=weld_dir,  # Pass for heartbeat updates
        )

        if result.success:
            msg = f"Step {n} completed in {result.iterations} iteration(s)!"
            ctx.console.print(f"\n[bold green]{msg}[/bold green]")
            ctx.console.print("\n[bold]Next step:[/bold] Commit your changes:")
            ctx.console.print(f"  weld commit --run {run} -m 'Implement step {n}' --staged")
            raise typer.Exit(0)
        else:
            ctx.console.print(
                f"\n[bold red]Step {n} did not pass after {result.iterations} iterations[/bold red]"
            )
            raise typer.Exit(10)
    finally:
        release_lock(weld_dir)
