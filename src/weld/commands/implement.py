"""Implement command for interactive plan execution.

Provides an arrow-key navigable menu for selecting phases/steps
from a plan file, executes Claude to implement them, and marks
completed items with **COMPLETE** in the plan file.

Supports both interactive mode (default) and non-interactive mode
via --step or --phase flags for CI/automation.
"""

import signal
import sys
from pathlib import Path
from types import FrameType
from typing import Annotated

import typer
from rich.panel import Panel
from simple_term_menu import TerminalMenu

from ..config import WeldConfig, load_config
from ..core import get_weld_dir, mark_phase_complete, mark_step_complete, validate_plan
from ..core.plan_parser import Phase, Plan, Step
from ..output import OutputContext, get_output_context
from ..services import ClaudeError, GitError, get_repo_root, run_claude, track_session_activity


class GracefulExit(Exception):
    """Raised when user requests graceful shutdown via Ctrl+C."""


def _handle_interrupt(signum: int, frame: FrameType | None) -> None:
    """Handle Ctrl+C gracefully."""
    raise GracefulExit()


def implement(
    plan_file: Annotated[
        Path,
        typer.Argument(
            help="Markdown plan file to implement",
        ),
    ],
    step: Annotated[
        str | None,
        typer.Option(
            "--step",
            "-s",
            help="Step number to implement non-interactively (e.g., '1.1')",
        ),
    ] = None,
    phase: Annotated[
        int | None,
        typer.Option(
            "--phase",
            "-p",
            help="Phase number to implement non-interactively (all steps sequentially)",
        ),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress Claude streaming output",
        ),
    ] = False,
    timeout: Annotated[
        int | None,
        typer.Option(
            "--timeout",
            "-t",
            help="Timeout in seconds for Claude (default: from config)",
        ),
    ] = None,
) -> None:
    """Execute plan phases and steps with AI assistance.

    File changes are automatically tracked for commit grouping.
    When you run 'weld commit', files will be grouped by the Claude
    Code session that created them, with transcript URLs attached.

    Use --step to execute a specific step (e.g., --step 1.2)
    Use --phase to execute all steps in a phase (e.g., --phase 1)
    Without options, shows interactive menu to select phase/step.
    """
    ctx = get_output_context()

    # --- Validate environment ---

    # JSON mode incompatibility check
    if ctx.json_mode and step is None and phase is None:
        ctx.error(
            "Interactive mode not supported with --json. Use --step or --phase.",
            next_action="weld implement plan.md --step 1.1",
        )
        raise typer.Exit(1)

    # TTY check for interactive mode
    if step is None and phase is None and not sys.stdin.isatty():
        ctx.error(
            "Interactive mode requires a terminal. Use --step or --phase for non-interactive.",
            next_action="weld implement plan.md --step 1.1",
        )
        raise typer.Exit(1)

    # Ensure we're in a git repo
    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    if not weld_dir.exists():
        ctx.error("Weld not initialized.", next_action="weld init")
        raise typer.Exit(1)

    # --- Validate and parse plan ---

    validation = validate_plan(plan_file)

    for error in validation.errors:
        ctx.error(error)
    if not validation.valid:
        raise typer.Exit(23)  # Parse error

    plan = validation.plan
    assert plan is not None  # Guaranteed by valid=True

    for warning in validation.warnings:
        ctx.console.print(f"[yellow]Warning: {warning}[/yellow]")

    # --- Load config ---

    config = load_config(repo_root)
    effective_timeout = timeout if timeout is not None else config.claude.timeout

    # --- Dry run handling ---

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would implement from plan:")
        ctx.console.print(f"  Plan file: {plan_file}")
        if step:
            ctx.console.print(f"  Mode: Non-interactive (step {step})")
        elif phase:
            ctx.console.print(f"  Mode: Non-interactive (phase {phase})")
        else:
            ctx.console.print("  Mode: Interactive menu")
        return

    # --- Route to interactive or non-interactive mode ---

    # Always track implement command
    with track_session_activity(weld_dir, repo_root, "implement"):
        if step is not None or phase is not None:
            exit_code = _implement_non_interactive(
                ctx=ctx,
                plan=plan,
                step_number=step,
                phase_number=phase,
                config=config,
                repo_root=repo_root,
                weld_dir=weld_dir,
                quiet=quiet,
                timeout=effective_timeout,
            )
            raise typer.Exit(exit_code)

        exit_code = _implement_interactive(
            ctx=ctx,
            plan=plan,
            config=config,
            repo_root=repo_root,
            weld_dir=weld_dir,
            quiet=quiet,
            timeout=effective_timeout,
        )
        raise typer.Exit(exit_code)


def _implement_interactive(
    ctx: OutputContext,
    plan: Plan,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
    quiet: bool,
    timeout: int,
) -> int:
    """Run interactive implementation loop with menu.

    Returns exit code (0 for success/quit, 21 for Claude failure).
    """
    # Set up signal handler for graceful Ctrl+C
    original_handler = signal.signal(signal.SIGINT, _handle_interrupt)

    try:
        ctx.console.print(Panel(f"[bold]Implementing:[/bold] {plan.path.name}", style="green"))

        while True:
            # Get all items for menu display (including complete ones)
            all_items = plan.get_all_items()
            complete_count, total_count = plan.count_complete()

            # Check if all done
            if complete_count == total_count and total_count > 0:
                ctx.console.print("\n[green]✓ All phases and steps are complete![/green]")
                return 0

            # Build menu with visual indicators
            menu_items = _build_menu_display(plan)
            menu_items.append("─" * 40)  # Separator
            menu_items.append("[q] Exit")

            # Display progress header
            ctx.console.print(f"\n[bold]Progress: {complete_count}/{total_count} complete[/bold]")

            # Show menu
            terminal_menu = TerminalMenu(
                menu_items,
                cursor_index=_find_first_incomplete_index(all_items),
                clear_screen=False,
                cycle_cursor=True,
            )
            selection = terminal_menu.show()

            # Handle exit (show() returns int for single-select, None on escape/ctrl-c)
            if not isinstance(selection, int) or selection >= len(all_items):
                ctx.console.print("\n[yellow]Implementation paused. Progress saved.[/yellow]")
                return 0

            # Get selected item
            phase, step = all_items[selection]

            # Handle selection of completed item
            if step and step.is_complete:
                ctx.console.print(f"\n[yellow]Step {step.number} is already complete.[/yellow]")
                continue
            if step is None and phase.is_complete:
                ctx.console.print(f"\n[yellow]Phase {phase.number} is already complete.[/yellow]")
                continue

            # Execute based on selection type
            if step:
                # Single step selected
                success = _execute_step(
                    ctx=ctx,
                    plan=plan,
                    step=step,
                    config=config,
                    repo_root=repo_root,
                    weld_dir=weld_dir,
                    quiet=quiet,
                    timeout=timeout,
                )
                if not success:
                    ctx.console.print(
                        "[yellow]Step not marked complete. Fix issues and retry.[/yellow]"
                    )
            else:
                # Phase selected - execute all incomplete steps sequentially
                success = _execute_phase_steps(
                    ctx=ctx,
                    plan=plan,
                    phase=phase,
                    config=config,
                    repo_root=repo_root,
                    weld_dir=weld_dir,
                    quiet=quiet,
                    timeout=timeout,
                )
                if not success:
                    ctx.console.print("[yellow]Phase execution stopped. Progress saved.[/yellow]")

    except GracefulExit:
        ctx.console.print("\n[yellow]Interrupted. Progress has been saved.[/yellow]")
        return 0

    finally:
        # Restore original signal handler
        signal.signal(signal.SIGINT, original_handler)


def _implement_non_interactive(
    ctx: OutputContext,
    plan: Plan,
    step_number: str | None,
    phase_number: int | None,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
    quiet: bool,
    timeout: int,
) -> int:
    """Non-interactive implementation of specific step or phase.

    Returns exit code.
    """
    if step_number:
        # Find specific step using helper method
        result = plan.get_step_by_number(step_number)
        if not result:
            ctx.error(f"Step {step_number} not found in plan")
            return 1

        phase, step = result
        if step.is_complete:
            ctx.console.print(f"[yellow]Step {step_number} already complete[/yellow]")
            return 0

        success = _execute_step(
            ctx=ctx,
            plan=plan,
            step=step,
            config=config,
            repo_root=repo_root,
            weld_dir=weld_dir,
            quiet=quiet,
            timeout=timeout,
        )
        return 0 if success else 21

    if phase_number:
        # Find specific phase using helper method
        phase = plan.get_phase_by_number(phase_number)
        if not phase:
            ctx.error(f"Phase {phase_number} not found in plan")
            return 1

        success = _execute_phase_steps(
            ctx=ctx,
            plan=plan,
            phase=phase,
            config=config,
            repo_root=repo_root,
            weld_dir=weld_dir,
            quiet=quiet,
            timeout=timeout,
        )
        return 0 if success else 21

    # Should not reach here
    return 1


def _build_menu_display(plan: Plan) -> list[str]:
    """Build menu display strings with visual indicators.

    Format:
      ✓ Phase 1: Setup [2/2 complete]
          ✓ Step 1.1: Create files
          ✓ Step 1.2: Configure
      ○ Phase 2: Implementation [0/3 complete]
          ○ Step 2.1: Write code
          ○ Step 2.2: Add tests
          ○ Step 2.3: Document
    """
    items: list[str] = []

    for phase in plan.phases:
        # Phase header with progress
        check = "✓" if phase.is_complete else "○"
        if phase.steps:
            complete = sum(1 for s in phase.steps if s.is_complete)
            total = len(phase.steps)
            items.append(
                f"{check} Phase {phase.number}: {phase.title} [{complete}/{total} complete]"
            )
        else:
            items.append(f"{check} Phase {phase.number}: {phase.title}")

        # Steps indented under phase
        for step in phase.steps:
            step_check = "✓" if step.is_complete else "○"
            items.append(f"    {step_check} Step {step.number}: {step.title}")

    return items


def _find_first_incomplete_index(items: list[tuple[Phase, Step | None]]) -> int:
    """Find index of first incomplete item for initial cursor position."""
    for i, (phase, step) in enumerate(items):
        if step and not step.is_complete:
            return i
        if step is None and not phase.is_complete:
            return i
    return 0


def _execute_step(
    ctx: OutputContext,
    plan: Plan,
    step: Step,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
    quiet: bool,
    timeout: int,
) -> bool:
    """Execute Claude to implement a single step.

    Marks step complete on success. Returns True if succeeded.
    """
    prompt = f"""## Implement Step {step.number}: {step.title}

{step.content}

---

## Instructions

Implement the above specification. After implementation:
1. Verify changes work by running any validation commands shown
2. Keep changes focused on this specific step only
3. Do not implement future steps or phases

When complete, confirm the implementation is done.

## Intentional Compaction

If the conversation becomes long or contains significant exploration, consider using
intentional compaction:

**What is Intentional Compaction?**
Deliberate compression of context into a minimal, high-signal representation.
Instead of dragging an ever-growing conversation forward:
1. Summarize the current state into a markdown artifact
2. Review and validate it
3. Use /compact or start a fresh context seeded with that artifact

**What to compact:**
- Relevant files and line ranges
- Verified architectural behavior
- Decisions already made
- Explicit constraints and non-goals

**What not to compact:**
- Raw logs
- Tool traces
- Full file contents
- Repetitive error explanations

Compaction converts exploration into a one-time cost instead of a recurring tax.
"""

    ctx.console.print(f"\n[bold]Implementing Step {step.number}: {step.title}[/bold]\n")

    try:
        run_claude(
            prompt=prompt,
            exec_path=config.claude.exec,
            cwd=repo_root,
            stream=not quiet,
            timeout=timeout,
            skip_permissions=True,
            max_output_tokens=config.claude.max_output_tokens,
        )
    except ClaudeError as e:
        ctx.console.print(f"\n[red]Error: Claude failed: {e}[/red]")
        return False

    # Mark step complete immediately (atomic write)
    try:
        mark_step_complete(plan, step)
    except ValueError as e:
        ctx.error(f"Failed to mark step complete: {e}")
        return False

    ctx.console.print(f"[green]✓ Step {step.number} marked complete[/green]")

    return True


def _execute_phase_steps(
    ctx: OutputContext,
    plan: Plan,
    phase: Phase,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
    quiet: bool,
    timeout: int,
) -> bool:
    """Execute all incomplete steps in a phase sequentially.

    Each step is marked complete individually (checkpoint after each).
    Returns True if all steps succeeded, False on first failure.
    """
    incomplete_steps = plan.get_incomplete_steps(phase)

    if not incomplete_steps:
        ctx.console.print(f"[yellow]All steps in Phase {phase.number} already complete[/yellow]")
        return True

    ctx.console.print(f"\n[bold]Implementing Phase {phase.number}: {phase.title}[/bold]")
    ctx.console.print(f"[dim]{len(incomplete_steps)} step(s) to implement[/dim]\n")

    for step in incomplete_steps:
        success = _execute_step(
            ctx=ctx,
            plan=plan,
            step=step,
            config=config,
            repo_root=repo_root,
            weld_dir=weld_dir,
            quiet=quiet,
            timeout=timeout,
        )

        if not success:
            ctx.error(f"Step {step.number} failed. Stopping phase execution.")
            return False

    # All steps done - mark phase complete
    try:
        mark_phase_complete(plan, phase)
    except ValueError as e:
        ctx.error(f"Failed to mark phase complete: {e}")
        return False

    ctx.console.print(f"[green]✓ Phase {phase.number} complete[/green]")

    return True
