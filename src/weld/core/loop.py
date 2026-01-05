"""Implement-review-fix loop runner for weld.

This module implements the core iteration loop that drives the
human-in-the-loop development workflow. Each iteration:
1. Captures the current diff
2. Runs configured checks (tests, linting)
3. Submits for AI review
4. Either passes or generates a fix prompt for the next iteration
"""

from pathlib import Path

from rich.console import Console

from ..config import WeldConfig
from ..models import Status, Step
from ..services import capture_diff, write_diff
from ..services.checks import run_checks, write_checks_results
from .lock_manager import update_heartbeat
from .review_engine import run_step_review
from .step_processor import create_iter_directory, generate_fix_prompt, get_step_dir

console = Console()


class LoopResult:
    """Result of the step implementation loop.

    Captures the outcome of running the implement-review-fix loop,
    including whether the step ultimately passed and how many
    iterations were required.

    Attributes:
        success: True if the step passed AI review before max iterations.
        iterations: Number of review iterations that were executed.
        final_status: Status from the last iteration, or None if no iterations ran.

    Example:
        >>> result = run_step_loop(run_dir, step, config, repo_root)
        >>> if result.success:
        ...     print(f"Passed in {result.iterations} iterations")
        ... else:
        ...     print(f"Failed after {result.iterations} iterations")
    """

    def __init__(
        self,
        success: bool,
        iterations: int,
        final_status: Status | None,
    ) -> None:
        """Initialize loop result.

        Args:
            success: Whether the step passed review.
            iterations: Number of iterations run.
            final_status: Final status from last iteration.
        """
        self.success = success
        self.iterations = iterations
        self.final_status = final_status


def run_step_loop(
    run_dir: Path,
    step: Step,
    config: WeldConfig,
    repo_root: Path,
    max_iterations: int | None = None,
    wait_mode: bool = False,
    weld_dir: Path | None = None,
    stream: bool = True,
) -> LoopResult:
    """Run the implement-review-fix loop for a step.

    Args:
        run_dir: Path to run directory
        step: Step to implement
        config: Weld configuration
        repo_root: Repository root path
        max_iterations: Override max iterations from config
        wait_mode: If True, wait for user input before each iteration
        weld_dir: Path to .weld directory for heartbeat updates
        stream: If True, stream review output to stdout in real-time

    Returns:
        LoopResult with success status and iteration count
    """
    max_iter = max_iterations or config.loop.max_iterations
    step_dir = get_step_dir(run_dir, step)
    status: Status | None = None

    for iteration in range(1, max_iter + 1):
        # Update heartbeat at the start of each iteration
        if weld_dir:
            update_heartbeat(weld_dir)

        console.print(f"\n[bold blue]Iteration {iteration}/{max_iter}[/bold blue]")

        if wait_mode:
            console.print("[yellow]Waiting for implementation... Press Enter when ready.[/yellow]")
            input()

        iter_dir = create_iter_directory(step_dir, iteration)

        # Capture diff
        diff, diff_nonempty = capture_diff(repo_root)
        write_diff(iter_dir / "diff.patch", diff)

        if not diff_nonempty:
            console.print("[yellow]No changes detected. Skipping review.[/yellow]")
            status = Status.model_validate(
                {
                    "pass": False,
                    "checks_exit_code": -1,
                    "diff_nonempty": False,
                }
            )
            (iter_dir / "status.json").write_text(status.model_dump_json(by_alias=True, indent=2))
            continue

        # Run checks (fail-fast for iteration, full run for review input)
        checks_summary = run_checks(config.checks, repo_root, fail_fast=True)

        # Run remaining checks for review context (if fail-fast stopped early)
        if checks_summary.first_failure:
            checks_summary = run_checks(config.checks, repo_root, fail_fast=False)

        # Write per-category output files and summary
        write_checks_results(iter_dir, checks_summary)

        # Build combined output for review prompt (use configured order)
        category_order = config.checks.order or list(checks_summary.categories.keys())
        checks_output = "\n\n".join(
            f"=== {name} (exit {checks_summary.categories[name].exit_code}) ===\n"
            f"{checks_summary.categories[name].output}"
            for name in category_order
            if name in checks_summary.categories
        )
        checks_exit = checks_summary.get_exit_code()

        # Run review
        console.print("[cyan]Running review...[/cyan]\n")
        review_md, issues, status = run_step_review(
            step=step,
            diff=diff,
            checks_output=checks_output,
            checks_exit_code=checks_exit,
            config=config,
            cwd=repo_root,
            stream=stream,
        )
        # Update heartbeat after review (can be a long operation)
        if weld_dir:
            update_heartbeat(weld_dir)
        # Enrich status with checks summary
        status.checks_summary = checks_summary

        # Write results
        (iter_dir / "review.md").write_text(review_md)
        (iter_dir / "issues.json").write_text(issues.model_dump_json(by_alias=True, indent=2))
        (iter_dir / "status.json").write_text(status.model_dump_json(by_alias=True, indent=2))

        if status.pass_:
            console.print("[bold green]Step passed![/bold green]")
            return LoopResult(success=True, iterations=iteration, final_status=status)

        # Generate fix prompt
        console.print(
            f"[red]Found {status.issue_count} issues ({status.blocker_count} blockers)[/red]"
        )

        if iteration < max_iter:
            fix_prompt = generate_fix_prompt(step, issues.model_dump(by_alias=True), iteration)
            fix_path = step_dir / "prompt" / f"fix.iter{iteration + 1:02d}.md"
            fix_path.parent.mkdir(parents=True, exist_ok=True)
            fix_path.write_text(fix_prompt)

            console.print(f"\n[bold]Fix prompt written to:[/bold] {fix_path}")
            console.print("\n" + "=" * 60)
            console.print(fix_prompt)
            console.print("=" * 60 + "\n")

    console.print(f"[bold red]Max iterations ({max_iter}) reached[/bold red]")
    return LoopResult(success=False, iterations=max_iter, final_status=status)
