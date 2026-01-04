"""Step command implementations."""

import json
import re

import typer
from rich.console import Console

from ..config import TaskType, load_config
from ..core import (
    create_iter_directory,
    create_step_directory,
    generate_fix_prompt,
    generate_impl_prompt,
    get_run_dir,
    get_weld_dir,
    parse_steps,
    run_step_review,
)
from ..models import Status, Step
from ..services import GitError, capture_diff, get_repo_root, run_checks, write_checks, write_diff

console = Console()


def step_select(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
) -> None:
    """Select a step from the plan."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find plan file
    plan_final = run_dir / "plan" / "plan.final.md"
    plan_raw = run_dir / "plan" / "plan.raw.md"
    plan_path = plan_final if plan_final.exists() else plan_raw

    if not plan_path.exists():
        console.print("[red]Error: No plan found[/red]")
        raise typer.Exit(1)

    # Parse steps
    steps, _ = parse_steps(plan_path.read_text())

    # Find requested step
    step = next((s for s in steps if s.n == n), None)
    if not step:
        console.print(f"[red]Error: Step {n} not found. Available: {[s.n for s in steps]}[/red]")
        raise typer.Exit(1)

    # Create step directory
    step_dir = create_step_directory(run_dir, step)

    # Write step.json
    (step_dir / "step.json").write_text(step.model_dump_json(indent=2))

    # Generate implementation prompt
    impl_prompt = generate_impl_prompt(step, config.checks.command)
    prompt_path = step_dir / "prompt" / "impl.prompt.md"
    prompt_path.write_text(impl_prompt)

    # Get configured model for implementation
    model_cfg = config.get_task_model(TaskType.IMPLEMENTATION)
    model_info = f" ({model_cfg.model})" if model_cfg.model else ""

    console.print(f"[green]Selected step {n}: {step.title}[/green]")
    console.print(f"\n[bold]Target model:[/bold] {model_cfg.provider}{model_info}")
    console.print(f"[bold]Prompt file:[/bold] {prompt_path}")
    console.print("\n" + "=" * 60)
    console.print(impl_prompt)
    console.print("=" * 60)
    console.print("\n[bold]Next step:[/bold] Start implementation loop:")
    console.print(f"  weld step loop --run {run} --n {n} --wait")


def step_snapshot(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    iter: int = typer.Option(1, "--iter", "-i", help="Iteration number"),
) -> None:
    """Capture current diff and checks for a step iteration."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find step directory
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    if not step_dirs:
        console.print(f"[red]Error: Step {n} not selected yet[/red]")
        raise typer.Exit(1)

    step_dir = step_dirs[0]

    # Create iteration directory
    iter_dir = create_iter_directory(step_dir, iter)

    # Capture diff
    diff, nonempty = capture_diff(repo_root)
    write_diff(iter_dir / "diff.patch", diff)

    if not nonempty:
        console.print("[yellow]No changes detected[/yellow]")
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
    console.print("[cyan]Running checks...[/cyan]")
    checks_output, exit_code = run_checks(config.checks.command, repo_root)
    write_checks(iter_dir / "checks.txt", checks_output)

    console.print(f"[green]Snapshot captured for iteration {iter}[/green]")
    console.print(f"  Diff: {len(diff)} bytes")
    console.print(f"  Checks exit code: {exit_code}")


def step_review_cmd(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    iter: int = typer.Option(1, "--iter", "-i", help="Iteration number"),
) -> None:
    """Run Codex review on step implementation."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find step
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    if not step_dirs:
        console.print(f"[red]Error: Step {n} not found[/red]")
        raise typer.Exit(1)

    step_dir = step_dirs[0]
    iter_dir = step_dir / "iter" / f"{iter:02d}"

    # Load step
    step = Step.model_validate(json.loads((step_dir / "step.json").read_text()))

    # Load diff and checks
    diff = (iter_dir / "diff.patch").read_text() if (iter_dir / "diff.patch").exists() else ""
    checks = (iter_dir / "checks.txt").read_text() if (iter_dir / "checks.txt").exists() else ""

    # Parse checks exit code
    exit_match = re.search(r"exit_code:\s*(\d+)", checks)
    checks_exit = int(exit_match.group(1)) if exit_match else -1

    # Run review
    console.print("[cyan]Running Codex review...[/cyan]")

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
        console.print("[bold green]Review passed![/bold green]")
    else:
        console.print(
            f"[red]Review found {status.issue_count} issues ({status.blocker_count} blockers)[/red]"
        )


def step_fix_prompt(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    iter: int = typer.Option(..., "--iter", "-i", help="Current iteration"),
) -> None:
    """Generate fix prompt for next iteration."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)

    # Find step
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    if not step_dirs:
        console.print(f"[red]Error: Step {n} not found[/red]")
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
    fix_path.write_text(fix_prompt)

    console.print(f"[green]Fix prompt written to:[/green] {fix_path}")
    console.print(f"[bold]Target model:[/bold] {model_cfg.provider}{model_info}")
    console.print("\n" + "=" * 60)
    console.print(fix_prompt)
    console.print("=" * 60)


def step_loop(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    max: int | None = typer.Option(None, "--max", "-m", help="Max iterations"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for user between iterations"),
) -> None:
    """Run implement-review-fix loop for a step."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find or select step
    steps_dir = run_dir / "steps"
    step_dirs = (
        [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]
        if steps_dir.exists()
        else []
    )

    if not step_dirs:
        # Auto-select step
        console.print(f"[yellow]Step {n} not selected, selecting now...[/yellow]")
        step_select(run=run, n=n)
        step_dirs = [
            d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")
        ]

    step_dir = step_dirs[0]

    # Load step
    step = Step.model_validate(json.loads((step_dir / "step.json").read_text()))

    # Print initial prompt with model info
    impl_model_cfg = config.get_task_model(TaskType.IMPLEMENTATION)
    impl_model_info = f" ({impl_model_cfg.model})" if impl_model_cfg.model else ""
    review_model_cfg = config.get_task_model(TaskType.IMPLEMENTATION_REVIEW)
    review_model_info = f" ({review_model_cfg.model})" if review_model_cfg.model else ""

    impl_prompt_path = step_dir / "prompt" / "impl.prompt.md"
    console.print(
        f"\n[bold]Implementation model:[/bold] {impl_model_cfg.provider}{impl_model_info}"
    )
    console.print(f"[bold]Review model:[/bold] {review_model_cfg.provider}{review_model_info}")
    console.print(f"[bold]Implementation prompt:[/bold] {impl_prompt_path}")
    console.print("\n" + "=" * 60)
    console.print(impl_prompt_path.read_text())
    console.print("=" * 60 + "\n")

    # Run loop
    from ..core import run_step_loop

    result = run_step_loop(
        run_dir=run_dir,
        step=step,
        config=config,
        repo_root=repo_root,
        max_iterations=max,
        wait_mode=wait,
    )

    if result.success:
        console.print(
            f"\n[bold green]Step {n} completed in {result.iterations} iteration(s)![/bold green]"
        )
        console.print("\n[bold]Next step:[/bold] Commit your changes:")
        console.print(f"  weld commit --run {run} -m 'Implement step {n}' --staged")
        raise typer.Exit(0)
    else:
        console.print(
            f"\n[bold red]Step {n} did not pass after {result.iterations} iterations[/bold red]"
        )
        raise typer.Exit(10)
