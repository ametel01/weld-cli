"""Implement command for interactive plan execution.

Provides an arrow-key navigable menu for selecting phases/steps
from a plan file, executes Claude to implement them, and marks
completed items with **COMPLETE** in the plan file.

Supports both interactive mode (default) and non-interactive mode
via --step or --phase flags for CI/automation.
"""

import contextlib
import signal
import sys
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Annotated

import typer
from rich.panel import Panel
from rich.prompt import Confirm
from simple_term_menu import TerminalMenu

from ..completions import complete_markdown_file, complete_step_number
from ..config import TaskType, WeldConfig, load_config
from ..core import (
    apply_customization,
    generate_code_review_prompt,
    get_doc_review_dir,
    get_weld_dir,
    mark_phase_complete,
    mark_step_complete,
    validate_plan,
    validate_plan_file,
)
from ..core.plan_parser import Phase, Plan, Step
from ..output import OutputContext, get_output_context
from ..services import (
    ClaudeError,
    GitError,
    get_diff,
    get_repo_root,
    get_staged_files,
    get_status_porcelain,
    run_claude,
    run_git,
    stage_all,
    track_session_activity,
)
from ..services.session_detector import detect_current_session, get_session_id
from ..services.session_tracker import SessionRegistry, get_registry
from .commit import _commit_by_sessions, _should_exclude_from_commit, resolve_files_to_sessions


class GracefulExit(Exception):
    """Raised when user requests graceful shutdown via Ctrl+C."""


def _handle_interrupt(signum: int, frame: FrameType | None) -> None:
    """Handle Ctrl+C gracefully."""
    raise GracefulExit()


def _has_file_changes(repo_root: Path, baseline_status: str) -> bool:
    """Check if any files have changed since baseline status.

    Args:
        repo_root: Repository root path
        baseline_status: Git status output from before execution

    Returns:
        True if files were created/modified/deleted, False otherwise
    """
    try:
        current_status = get_status_porcelain(cwd=repo_root)
        return current_status != baseline_status
    except GitError:
        # If we can't get status, assume changes happened to be safe
        return True


def implement(
    plan_file: Annotated[
        Path,
        typer.Argument(
            help="Markdown plan file to implement",
            autocompletion=complete_markdown_file,
        ),
    ],
    step: Annotated[
        str | None,
        typer.Option(
            "--step",
            "-s",
            help="Step number to implement non-interactively (e.g., '1.1')",
            autocompletion=complete_step_number,
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
    auto_commit: Annotated[
        bool,
        typer.Option(
            "--auto-commit",
            help="Prompt to commit changes after each step completes",
        ),
    ] = False,
    no_review: Annotated[
        bool,
        typer.Option(
            "--no-review",
            help="Skip post-step review prompt (workaround for Claude CLI bugs)",
        ),
    ] = False,
    autopilot: Annotated[
        bool,
        typer.Option(
            "--autopilot",
            help="Execute all steps automatically with review+apply and commit after each",
        ),
    ] = False,
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

    # --- Early path validation ---

    # Validate plan file path before any other processing
    if error := validate_plan_file(plan_file, param_name="plan file"):
        ctx.error(error[0], next_action=error[1])
        raise typer.Exit(1)

    # --- Validate environment ---

    # JSON mode incompatibility check
    if ctx.json_mode and step is None and phase is None:
        ctx.error(
            "Interactive mode not supported with --json. Use --step or --phase.",
            next_action="weld implement plan.md --step 1.1",
        )
        raise typer.Exit(1)

    # TTY check for interactive mode (not needed for autopilot)
    if step is None and phase is None and not autopilot and not sys.stdin.isatty():
        ctx.error(
            "Interactive mode requires a terminal. Use --step or --phase for non-interactive.",
            next_action="weld implement plan.md --step 1.1",
        )
        raise typer.Exit(1)

    # Autopilot validation: cannot be used with --step or --phase
    if autopilot and (step is not None or phase is not None):
        ctx.error(
            "Autopilot mode executes all steps. Cannot use with --step or --phase.",
            next_action="weld implement plan.md --autopilot",
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
        if autopilot:
            ctx.console.print("  Mode: Autopilot (all steps, auto-review, auto-commit)")
        elif step:
            ctx.console.print(f"  Mode: Non-interactive (step {step})")
        elif phase:
            ctx.console.print(f"  Mode: Non-interactive (phase {phase})")
        else:
            ctx.console.print("  Mode: Interactive menu")
        return

    # --- Route to autopilot, interactive, or non-interactive mode ---

    # Always track implement command
    with track_session_activity(weld_dir, repo_root, "implement"):
        if autopilot:
            exit_code = _implement_autopilot(
                ctx=ctx,
                plan=plan,
                config=config,
                repo_root=repo_root,
                weld_dir=weld_dir,
                quiet=quiet,
                timeout=effective_timeout,
                no_review=no_review,
            )
            raise typer.Exit(exit_code)

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
                auto_commit=auto_commit,
                no_review=no_review,
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
            auto_commit=auto_commit,
            no_review=no_review,
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
    auto_commit: bool = False,
    no_review: bool = False,
) -> int:
    """Run interactive implementation loop with menu.

    Returns exit code (0 for success/quit, 21 for Claude failure).
    """
    # Set up signal handler for graceful Ctrl+C
    original_handler = signal.signal(signal.SIGINT, _handle_interrupt)

    try:
        ctx.console.print(Panel(f"[bold]Implementing:[/bold] {plan.path.name}", style="green"))

        # Load registry for auto-commit
        registry = get_registry(weld_dir) if auto_commit else None

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
                    auto_commit=auto_commit,
                    no_review=no_review,
                    registry=registry,
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
                    auto_commit=auto_commit,
                    no_review=no_review,
                    registry=registry,
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
    auto_commit: bool = False,
    no_review: bool = False,
) -> int:
    """Non-interactive implementation of specific step or phase.

    Returns exit code.
    """
    # Load registry for auto-commit
    registry = get_registry(weld_dir) if auto_commit else None

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
            auto_commit=auto_commit,
            no_review=no_review,
            registry=registry,
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
            auto_commit=auto_commit,
            registry=registry,
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
    """Find index of first incomplete item for initial cursor position.

    Prioritizes incomplete steps over phase headers. Only selects a phase
    header if it has no steps (standalone phase) and is incomplete.
    """
    for i, (phase, step) in enumerate(items):
        if step is not None and not step.is_complete:
            return i
        if step is None and len(phase.steps) == 0 and not phase.is_complete:
            # Only select phase header if it has no steps (standalone phase)
            return i
    return 0


def _prompt_and_commit_step(
    ctx: OutputContext,
    step: Step,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
    registry: SessionRegistry | None,
    session_file: Path | None = None,
) -> None:
    """Prompt user to commit changes from completed step.

    Detects uncommitted changes, prompts user for confirmation,
    and creates session-based commits if approved.

    Args:
        ctx: Output context for console/JSON/dry-run
        step: The step that just completed
        config: Weld configuration
        repo_root: Repository root path
        weld_dir: .weld directory path
        registry: Session registry for session-based commits (None if auto-commit disabled)
        session_file: Optional session file to use for transcript (if None, auto-detects)

    Implementation notes:
    - Skips prompt if no changes detected
    - Uses session-based commit splitting (default behavior)
    - Continues on errors (doesn't abort implement flow)
    - Respects dry-run mode
    """
    # Guard: registry is required for commit functionality
    if registry is None:
        ctx.console.print("[yellow]Auto-commit requires registry (should not reach here)[/yellow]")
        return

    # Check for uncommitted changes
    try:
        status = get_status_porcelain(cwd=repo_root)
    except GitError as e:
        ctx.console.print(f"[yellow]Failed to check git status: {e}[/yellow]")
        return

    if not status.strip():
        ctx.console.print("[dim]No changes to commit[/dim]")
        return

    # Dry run: just announce intent
    if ctx.dry_run:
        ctx.console.print(
            f"[cyan][DRY RUN][/cyan] Would prompt to commit changes after step {step.number}"
        )
        return

    # Prompt user
    try:
        should_commit = Confirm.ask(
            f"\nCommit changes from step {step.number}?",
            default=False,
        )
    except (KeyboardInterrupt, EOFError):
        # EOFError occurs in non-interactive environments (tests, CI)
        ctx.console.print("\n[yellow]Skipping commit[/yellow]")
        return

    if not should_commit:
        return

    # Stage all changes
    try:
        stage_all(cwd=repo_root)
    except GitError as e:
        ctx.console.print(f"[yellow]Failed to stage changes: {e}[/yellow]")
        ctx.console.print("[dim]Continuing with next step...[/dim]")
        return

    # Get staged files and filter out .weld/ files except config.toml
    try:
        staged_files = get_staged_files(cwd=repo_root)
    except GitError as e:
        ctx.console.print(f"[yellow]Failed to get staged files: {e}[/yellow]")
        ctx.console.print("[dim]Continuing with next step...[/dim]")
        return

    # Identify and unstage excluded files
    excluded_files = [f for f in staged_files if _should_exclude_from_commit(f)]
    if excluded_files:
        ctx.console.print(
            f"[dim]Excluding {len(excluded_files)} .weld/ metadata file(s) from commit[/dim]"
        )
        # Unstage the excluded files
        for f in excluded_files:
            with contextlib.suppress(GitError):
                run_git("restore", "--staged", f, cwd=repo_root)

        # Refresh staged files list after unstaging
        try:
            staged_files = get_staged_files(cwd=repo_root)
        except GitError as e:
            ctx.console.print(f"[yellow]Failed to refresh staged files: {e}[/yellow]")
            ctx.console.print("[dim]Continuing with next step...[/dim]")
            return

    if not staged_files:
        ctx.console.print("[yellow]No files to commit after filtering[/yellow]")
        ctx.console.print("[dim]Continuing with next step...[/dim]")
        return

    # Ensure current session is recorded in registry for transcript upload
    # This is necessary because track_session_activity() only records at the end,
    # but we need the session in the registry now for _commit_by_sessions() to work
    # Use provided session_file (captured before review ran) to avoid using review session,
    # or detect current session if not provided (fallback for backwards compatibility)
    if session_file is None:
        session_file = detect_current_session(repo_root)
    if session_file:
        try:
            session_id = get_session_id(session_file)
            # Record the staged files as belonging to the current session
            # Note: We use staged_files since those are the ones being committed
            registry.record_activity(
                session_id=session_id,
                session_file=str(session_file),
                command="implement",
                files_created=[],  # We don't distinguish here, all are treated as modified
                files_modified=staged_files,
                completed=True,
            )
            ctx.console.print(
                f"[dim]Recorded {len(staged_files)} file(s) to session {session_id[:8]}...[/dim]"
            )
        except Exception as e:
            ctx.console.print(f"[yellow]Warning: Failed to record session activity: {e}[/yellow]")
            # Continue anyway - commit will still work without transcript

    # Resolve to sessions
    session_files = resolve_files_to_sessions(staged_files, registry)

    # Call session-based commit
    try:
        _commit_by_sessions(
            ctx=ctx,
            session_files=session_files,
            registry=registry,
            config=config,
            repo_root=repo_root,
            weld_dir=weld_dir,
            skip_transcript=False,
            skip_changelog=False,
            skip_hooks=False,
            quiet=True,  # Suppress streaming during implement
        )
        ctx.console.print("[green]✓ Changes committed successfully[/green]")
    except Exception as e:
        ctx.console.print(f"[yellow]Commit failed: {e}[/yellow]")
        ctx.console.print("[dim]Continuing with next step...[/dim]")


def _prompt_and_review_step(
    ctx: OutputContext,
    step: Step,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
) -> None:
    """Prompt user to review changes from completed step.

    Presents two-level prompt:
    1. "Review changes from step {step.number}?" (yes/no, default=False)
    2. If yes: "Apply fixes directly to files?" (yes/no, default=False)

    Then runs appropriate review:
    - Apply yes: review with auto-fix enabled
    - Apply no: review findings only

    Args:
        ctx: Output context for console/JSON/dry-run
        step: The step that just completed
        config: Weld configuration
        repo_root: Repository root path
        weld_dir: .weld directory path

    Non-blocking: errors don't abort implement flow.

    Security: When apply_mode is enabled, Claude runs with skip_permissions=True,
    allowing it to modify any file in the repository without additional prompts.
    """
    # Dry run: just announce intent
    if ctx.dry_run:
        ctx.console.print(
            f"[cyan][DRY RUN][/cyan] Would prompt to review changes after step {step.number}"
        )
        return

    # First prompt: Review yes/no
    try:
        should_review = Confirm.ask(
            f"\nReview changes from step {step.number}?",
            default=False,
        )
    except (KeyboardInterrupt, EOFError):
        # EOFError occurs in non-interactive environments (tests, CI)
        ctx.console.print("\n[yellow]Skipping review[/yellow]")
        return

    if not should_review:
        return

    # Second prompt: Apply fixes yes/no
    try:
        should_apply = Confirm.ask(
            "Apply fixes directly to files?",
            default=False,
        )
    except (KeyboardInterrupt, EOFError):
        # EOFError occurs in non-interactive environments (tests, CI)
        ctx.console.print("\n[yellow]Skipping review[/yellow]")
        return

    # Get diff content
    try:
        diff_content = get_diff(staged=False, cwd=repo_root)
    except GitError as e:
        ctx.console.print(f"[yellow]Failed to get diff: {e}[/yellow]")
        return

    if not diff_content.strip():
        ctx.console.print("[dim]No changes to review[/dim]")
        return

    # Generate review prompt
    try:
        prompt = generate_code_review_prompt(diff_content, apply_mode=should_apply)
    except Exception as e:
        ctx.console.print(f"[yellow]Failed to generate review prompt: {e}[/yellow]")
        ctx.console.print("[dim]Continuing with next step...[/dim]")
        return

    # Create artifact directory
    mode_suffix = "fix" if should_apply else "review"
    step_safe = str(step.number).replace(".", "-")
    review_id = datetime.now().strftime(f"%Y%m%d-%H%M%S-code-{mode_suffix}-step{step_safe}")

    review_dir = get_doc_review_dir(weld_dir)
    artifact_dir = review_dir / review_id

    # Save prompt and diff artifacts
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "prompt.md").write_text(prompt)
        (artifact_dir / "diff.patch").write_text(diff_content)
    except OSError as e:
        ctx.console.print(f"[yellow]Failed to save review artifacts: {e}[/yellow]")
        ctx.console.print("[dim]Continuing with next step...[/dim]")
        return

    # Run Claude for review
    mode_label = "Reviewing and fixing" if should_apply else "Reviewing"
    ctx.console.print(Panel(f"[bold]{mode_label} step {step.number} changes[/bold]", style="blue"))

    # Get config values with defaults
    exec_path = getattr(config.claude, "exec", "claude")
    model = getattr(config.claude, "model", None)
    timeout = getattr(config.claude, "timeout", 300)
    max_tokens = getattr(config.claude, "max_output_tokens", None)

    try:
        result = run_claude(
            prompt=prompt,
            exec_path=exec_path,
            model=model,
            cwd=repo_root,
            stream=True,  # Show Claude's work
            timeout=timeout,
            skip_permissions=True,
            max_output_tokens=max_tokens,
        )
    except ClaudeError as e:
        ctx.console.print(f"[yellow]Review failed: {e}[/yellow]")
        ctx.console.print("[dim]Continuing with next step...[/dim]")
        return

    # Validate result
    if not result or not result.strip():
        ctx.console.print("[yellow]Review produced no output[/yellow]")
        ctx.console.print("[dim]Continuing with next step...[/dim]")
        return

    # Save results
    result_name = "fixes.md" if should_apply else "findings.md"
    try:
        (artifact_dir / result_name).write_text(result)
    except OSError as e:
        ctx.console.print(f"[yellow]Failed to save results: {e}[/yellow]")
        ctx.console.print("[dim]Continuing with next step...[/dim]")
        return

    if should_apply:
        ctx.console.print("[green]✓ Fixes applied[/green]")
    else:
        ctx.console.print("[green]✓ Review complete[/green]")
    ctx.console.print(f"[dim]Results: .weld/reviews/{review_id}/{result_name}[/dim]")


def _execute_step(
    ctx: OutputContext,
    plan: Plan,
    step: Step,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
    quiet: bool,
    timeout: int,
    auto_commit: bool = False,
    no_review: bool = False,
    registry: SessionRegistry | None = None,
) -> bool:
    """Execute Claude to implement a single step.

    Marks step complete on success. Returns True if succeeded.

    Smart error recovery: If Claude crashes after making file changes,
    prompts user to mark step complete anyway.
    """
    base_prompt = f"""## Implement Step {step.number}: {step.title}

{step.content}

---

## Instructions

**IMPORTANT - Check if already complete:**
Before implementing, examine the codebase to determine if this step's requirements
are already satisfied.

If you determine the step is already complete:
1. Check git status (`git status --porcelain`)
2. If worktree is clean (no changes):
   - Simply confirm the step is complete - DO NOT run tests or validation commands
   - State: "Step already complete, no changes needed"
3. If worktree is dirty (uncommitted changes):
   - Review the changes to ensure they satisfy the step requirements
   - If satisfied, state: "Step requirements met by uncommitted changes"
   - DO NOT run tests again - assume changes are valid

If the step is NOT complete:
1. Implement the specification
2. Verify changes work by running any validation commands shown
3. Keep changes focused on this specific step only
4. Do not implement future steps or phases

When complete, confirm the implementation is done.
"""

    # Apply user-configured prompt customization
    prompt = apply_customization(base_prompt, TaskType.IMPLEMENTATION, config)

    ctx.console.print(f"\n[bold]Implementing Step {step.number}: {step.title}[/bold]\n")

    # Capture baseline state for error recovery
    try:
        baseline_status = get_status_porcelain(cwd=repo_root)
    except GitError:
        baseline_status = ""

    # Execute Claude
    claude_succeeded = True
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
        claude_succeeded = False

        # Check if work was done despite error
        if _has_file_changes(repo_root, baseline_status):
            ctx.console.print("\n[yellow]Files were modified before Claude crashed.[/yellow]")
            try:
                should_mark_complete = Confirm.ask(
                    "Work appears complete. Mark step as done?",
                    default=True,
                )
            except (KeyboardInterrupt, EOFError):
                ctx.console.print("\n[yellow]Skipping step completion[/yellow]")
                return False

            if not should_mark_complete:
                return False
            # User confirmed - proceed to mark complete
            claude_succeeded = True
        else:
            # No changes detected - genuine failure
            return False

    # Mark step complete (either Claude succeeded or user confirmed recovery)
    if claude_succeeded:
        try:
            mark_step_complete(plan, step)
        except ValueError as e:
            ctx.error(f"Failed to mark step complete: {e}")
            return False

        ctx.console.print(f"[green]✓ Step {step.number} marked complete[/green]")

        # Capture current session before review (review might create new session)
        # This ensures we use the implementation session for transcripts, not the review session
        current_session = detect_current_session(repo_root)
        if current_session is None and auto_commit and registry is not None:
            ctx.console.print(
                "[yellow]Warning: Could not detect Claude session for transcripts[/yellow]"
            )
            ctx.console.print("[dim]Commit will proceed without session transcript[/dim]")

        # Prompt for review (always available, opt-in, unless --no-review)
        if not no_review:
            _prompt_and_review_step(
                ctx=ctx,
                step=step,
                config=config,
                repo_root=repo_root,
                weld_dir=weld_dir,
            )

        # Auto-commit if enabled
        if auto_commit and registry is not None:
            _prompt_and_commit_step(
                ctx=ctx,
                step=step,
                config=config,
                repo_root=repo_root,
                weld_dir=weld_dir,
                registry=registry,
                session_file=current_session,
            )

        return True
    else:
        # Step not marked complete - either no changes or user declined
        return False


def _execute_phase_steps(
    ctx: OutputContext,
    plan: Plan,
    phase: Phase,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
    quiet: bool,
    timeout: int,
    auto_commit: bool = False,
    no_review: bool = False,
    registry: SessionRegistry | None = None,
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
            auto_commit=auto_commit,
            no_review=no_review,
            registry=registry,
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


def _implement_autopilot(
    ctx: OutputContext,
    plan: Plan,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
    quiet: bool,
    timeout: int,
    no_review: bool,
) -> int:
    """Run fully automated implementation of all plan steps.

    For each incomplete step:
    1. Execute the step with Claude
    2. Run code review with --apply (auto-fix issues) unless no_review
    3. Stage and commit changes

    Stops on first Claude failure.
    Returns exit code (0 for success, 21 for Claude failure).
    """
    # Build options display
    options = ["autopilot", "auto-commit"]
    if no_review:
        options.append("no-review")
    options_str = ", ".join(options)
    ctx.console.print(
        Panel(
            f"[bold]Autopilot:[/bold] {plan.path.name}\n[dim]Options: {options_str}[/dim]",
            style="blue",
        )
    )

    # Collect all incomplete steps across all phases
    all_steps: list[tuple[Phase, Step]] = []
    for phase in plan.phases:
        for step in phase.steps:
            if not step.is_complete:
                all_steps.append((phase, step))

    if not all_steps:
        ctx.console.print("[green]All steps already complete.[/green]")
        return 0

    ctx.console.print(f"[dim]{len(all_steps)} step(s) to implement[/dim]\n")

    # Load registry for commit tracking
    registry = get_registry(weld_dir)

    # Track which phases have had all steps completed
    completed_phases: set[int] = set()

    for phase, step in all_steps:
        success = _execute_step_autopilot(
            ctx=ctx,
            plan=plan,
            phase=phase,
            step=step,
            config=config,
            repo_root=repo_root,
            weld_dir=weld_dir,
            quiet=quiet,
            timeout=timeout,
            registry=registry,
            no_review=no_review,
        )

        if not success:
            ctx.error(f"Autopilot stopped at step {step.number}.")
            return 21

        # Check if phase is now complete
        if all(s.is_complete for s in phase.steps) and phase.number not in completed_phases:
            try:
                mark_phase_complete(plan, phase)
                ctx.console.print(f"[green]Phase {phase.number} complete[/green]")
                completed_phases.add(phase.number)
            except ValueError as e:
                ctx.console.print(f"[yellow]Warning: Failed to mark phase complete: {e}[/yellow]")

    ctx.console.print("\n[green]Autopilot complete. All steps implemented.[/green]")
    return 0


def _execute_step_autopilot(
    ctx: OutputContext,
    plan: Plan,
    phase: Phase,
    step: Step,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
    quiet: bool,
    timeout: int,
    registry: SessionRegistry,
    no_review: bool,
) -> bool:
    """Execute a single step in autopilot mode.

    1. Run Claude to implement step
    2. Mark step complete
    3. Run review with --apply mode (non-blocking) unless no_review
    4. Stage and commit all changes (non-blocking)

    Returns True on success, False on Claude failure.
    """
    ctx.console.print(f"\n[bold cyan]Step {step.number}: {step.title}[/bold cyan]")

    # Capture current session before any Claude calls
    current_session = detect_current_session(repo_root)

    # Build implementation prompt (same as _execute_step)
    base_prompt = f"""## Implement Step {step.number}: {step.title}

{step.content}

---

## Instructions

**IMPORTANT - Check if already complete:**
Before implementing, examine the codebase to determine if this step's requirements
are already satisfied.

If you determine the step is already complete:
1. Check git status (`git status --porcelain`)
2. If worktree is clean (no changes):
   - Simply confirm the step is complete - DO NOT run tests or validation commands
   - State: "Step already complete, no changes needed"
3. If worktree is dirty (uncommitted changes):
   - Review the changes to ensure they satisfy the step requirements
   - If satisfied, state: "Step requirements met by uncommitted changes"
   - DO NOT run tests again - assume changes are valid

If the step is NOT complete:
1. Implement the specification
2. Verify changes work by running any validation commands shown
3. Keep changes focused on this specific step only
4. Do not implement future steps or phases

When complete, confirm the implementation is done.
"""

    # Apply user-configured prompt customization
    prompt = apply_customization(base_prompt, TaskType.IMPLEMENTATION, config)

    # Execute Claude
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
        ctx.console.print(f"[red]Claude failed: {e}[/red]")
        return False

    # Mark step complete
    try:
        mark_step_complete(plan, step)
        ctx.console.print(f"[green]Step {step.number} marked complete[/green]")
    except ValueError as e:
        ctx.error(f"Failed to mark step complete: {e}")
        return False

    # Run review with apply mode (non-blocking - errors don't stop autopilot)
    if not no_review:
        _autopilot_review_and_fix(
            ctx=ctx,
            step=step,
            config=config,
            repo_root=repo_root,
            weld_dir=weld_dir,
        )

    # Commit changes (non-blocking - errors don't stop autopilot)
    _autopilot_commit(
        ctx=ctx,
        step=step,
        config=config,
        repo_root=repo_root,
        weld_dir=weld_dir,
        registry=registry,
        session_file=current_session,
    )

    return True


def _autopilot_review_and_fix(
    ctx: OutputContext,
    step: Step,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
) -> None:
    """Run code review with auto-apply in autopilot mode.

    Non-blocking: errors are logged but don't stop autopilot.
    """
    # Get diff content
    try:
        diff_content = get_diff(staged=False, cwd=repo_root)
    except GitError as e:
        ctx.console.print(f"[yellow]Skipping review (git error): {e}[/yellow]")
        return

    if not diff_content.strip():
        ctx.console.print("[dim]No changes to review[/dim]")
        return

    # Generate review prompt with apply mode
    try:
        prompt = generate_code_review_prompt(diff_content, apply_mode=True)
    except Exception as e:
        ctx.console.print(f"[yellow]Failed to generate review prompt: {e}[/yellow]")
        return

    # Create artifact directory
    step_safe = str(step.number).replace(".", "-")
    review_id = datetime.now().strftime(f"%Y%m%d-%H%M%S-autopilot-step{step_safe}")

    review_dir = get_doc_review_dir(weld_dir)
    artifact_dir = review_dir / review_id

    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "prompt.md").write_text(prompt)
        (artifact_dir / "diff.patch").write_text(diff_content)
    except OSError as e:
        ctx.console.print(f"[yellow]Failed to save review artifacts: {e}[/yellow]")
        return

    # Run Claude for review+fix
    ctx.console.print("[dim]Running code review with auto-fix...[/dim]")

    try:
        result = run_claude(
            prompt=prompt,
            exec_path=config.claude.exec,
            cwd=repo_root,
            stream=False,  # Quiet in autopilot
            timeout=config.claude.timeout,
            skip_permissions=True,
            max_output_tokens=config.claude.max_output_tokens,
        )
    except ClaudeError as e:
        ctx.console.print(f"[yellow]Review failed: {e}[/yellow]")
        return

    # Save results
    if result and result.strip():
        try:
            (artifact_dir / "fixes.md").write_text(result)
            ctx.console.print("[green]Review fixes applied[/green]")
        except OSError as e:
            ctx.console.print(f"[yellow]Failed to save review results: {e}[/yellow]")
    else:
        ctx.console.print("[dim]Review produced no output[/dim]")


def _autopilot_commit(
    ctx: OutputContext,
    step: Step,
    config: WeldConfig,
    repo_root: Path,
    weld_dir: Path,
    registry: SessionRegistry,
    session_file: Path | None,
) -> None:
    """Commit changes automatically in autopilot mode.

    Non-blocking: errors are logged but don't stop autopilot.
    """
    # Check for uncommitted changes
    try:
        status = get_status_porcelain(cwd=repo_root)
    except GitError as e:
        ctx.console.print(f"[yellow]Failed to check git status: {e}[/yellow]")
        return

    if not status.strip():
        ctx.console.print("[dim]No changes to commit[/dim]")
        return

    # Stage all changes
    try:
        stage_all(cwd=repo_root)
    except GitError as e:
        ctx.console.print(f"[yellow]Failed to stage changes: {e}[/yellow]")
        return

    # Get staged files and filter
    try:
        staged_files = get_staged_files(cwd=repo_root)
    except GitError as e:
        ctx.console.print(f"[yellow]Failed to get staged files: {e}[/yellow]")
        return

    # Exclude .weld/ metadata files
    excluded_files = [f for f in staged_files if _should_exclude_from_commit(f)]
    if excluded_files:
        for f in excluded_files:
            with contextlib.suppress(GitError):
                run_git("restore", "--staged", f, cwd=repo_root)
        # Refresh staged files list
        try:
            staged_files = get_staged_files(cwd=repo_root)
        except GitError:
            return

    if not staged_files:
        ctx.console.print("[dim]No files to commit after filtering[/dim]")
        return

    # Record session activity for transcript upload
    if session_file:
        try:
            session_id = get_session_id(session_file)
            registry.record_activity(
                session_id=session_id,
                session_file=str(session_file),
                command="implement",
                files_created=[],
                files_modified=staged_files,
                completed=True,
            )
        except Exception as e:
            ctx.console.print(f"[yellow]Warning: Failed to record session: {e}[/yellow]")

    # Resolve to sessions and commit
    session_files = resolve_files_to_sessions(staged_files, registry)

    try:
        _commit_by_sessions(
            ctx=ctx,
            session_files=session_files,
            registry=registry,
            config=config,
            repo_root=repo_root,
            weld_dir=weld_dir,
            skip_transcript=False,
            skip_changelog=False,
            skip_hooks=False,
            quiet=True,  # Suppress streaming in autopilot
        )
        ctx.console.print(f"[green]Committed step {step.number} changes[/green]")
    except Exception as e:
        ctx.console.print(f"[yellow]Commit failed: {e}[/yellow]")
