"""Implement-review-fix loop runner for weld."""

from pathlib import Path

from rich.console import Console

from .checks import run_checks, write_checks
from .config import WeldConfig
from .diff import capture_diff, write_diff
from .models import Status, Step
from .review import run_step_review
from .step import create_iter_directory, generate_fix_prompt, get_step_dir

console = Console()


class LoopResult:
    """Result of step implementation loop."""

    def __init__(
        self,
        success: bool,
        iterations: int,
        final_status: Status | None,
    ) -> None:
        """Initialize loop result.

        Args:
            success: Whether the step passed review
            iterations: Number of iterations run
            final_status: Final status from last iteration
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
) -> LoopResult:
    """Run the implement-review-fix loop for a step.

    Args:
        run_dir: Path to run directory
        step: Step to implement
        config: Weld configuration
        repo_root: Repository root path
        max_iterations: Override max iterations from config
        wait_mode: If True, wait for user input before each iteration

    Returns:
        LoopResult with success status and iteration count
    """
    max_iter = max_iterations or config.loop.max_iterations
    step_dir = get_step_dir(run_dir, step)
    status: Status | None = None

    for iteration in range(1, max_iter + 1):
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

        # Run checks
        checks_output, checks_exit = run_checks(config.checks.command, repo_root)
        write_checks(iter_dir / "checks.txt", checks_output)

        # Run review
        console.print("[cyan]Running Codex review...[/cyan]")
        review_md, issues, status = run_step_review(
            step=step,
            diff=diff,
            checks_output=checks_output,
            checks_exit_code=checks_exit,
            config=config,
            cwd=repo_root,
        )

        # Write results
        (iter_dir / "codex.review.md").write_text(review_md)
        (iter_dir / "codex.issues.json").write_text(issues.model_dump_json(by_alias=True, indent=2))
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
            fix_path = step_dir / "prompt" / f"claude.fix.prompt.iter{iteration + 1:02d}.md"
            fix_path.parent.mkdir(parents=True, exist_ok=True)
            fix_path.write_text(fix_prompt)

            console.print(f"\n[bold]Fix prompt written to:[/bold] {fix_path}")
            console.print("\n" + "=" * 60)
            console.print(fix_prompt)
            console.print("=" * 60 + "\n")

    console.print(f"[bold red]Max iterations ({max_iter}) reached[/bold red]")
    return LoopResult(success=False, iterations=max_iter, final_status=status)
