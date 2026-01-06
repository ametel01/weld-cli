# Implementation Plan: `weld implement <plan.md>`

**Research source:** `.claude/research/weld-implement-command.md`

## Overview

Add a new `weld implement` command that provides an interactive, arrow-key navigable menu for executing plan phases/steps with Claude, marking items complete in the plan file.

**Key design principles:**
- **Incremental checkpointing**: Mark each step complete immediately after success
- **Sequential phase execution**: When phase selected, execute steps one-by-one (not batch)
- **Graceful interruption**: Ctrl+C preserves all completed work
- **Dual mode**: Interactive (default) and non-interactive (`--step`/`--phase` flags)

---

## Phase 1: Add Dependency **COMPLETE**

### Step 1.1: Add simple-term-menu to pyproject.toml

**File:** `pyproject.toml`

**Change:** Add `simple-term-menu` to dependencies list (line ~11-16)

```toml
dependencies = [
  "typer>=0.12",
  "pydantic>=2.6",
  "rich>=13.7",
  "tomli-w>=1.0",
  "simple-term-menu>=1.6",  # ADD THIS LINE
]
```

**Validation:**
```bash
uv sync && .venv/bin/python -c "from simple_term_menu import TerminalMenu; print('OK')"
```

**Failure modes:**
- Package not found → check spelling, version constraint
- Import error → verify installation completed

---

## Phase 2: Create Plan Parser Core Module **COMPLETE**

### Step 2.1: Create plan_parser.py with data models and validation

**File:** `src/weld/core/plan_parser.py` (NEW)

**Content:**

```python
"""Plan file parser for extracting phases and steps.

Parses markdown plan files with the format:
- ## Phase N: Title
- ### Step N.N: Title
- **COMPLETE** suffix marks completion
"""

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Regex patterns - handle both "Step 1" and "Step 1.1" formats
# Note: Title group uses non-greedy match to exclude trailing **COMPLETE**
PHASE_PATTERN = re.compile(
    r"^## Phase (\d+):\s*(.+?)(?:\s*\*\*COMPLETE\*\*)?$"
)
STEP_PATTERN = re.compile(
    r"^### Step (\d+(?:\.\d+)?):\s*(.+?)(?:\s*\*\*COMPLETE\*\*)?$"
)


@dataclass
class Step:
    """A single step within a phase."""

    number: str  # "1" or "1.1"
    title: str
    content: str
    line_number: int  # 0-based index for array access
    is_complete: bool = False


@dataclass
class Phase:
    """A phase containing multiple steps."""

    number: int
    title: str
    content: str
    line_number: int  # 0-based index for array access
    steps: list[Step] = field(default_factory=list)
    is_complete: bool = False


@dataclass
class Plan:
    """A parsed plan file."""

    path: Path
    phases: list[Phase] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)

    def get_all_items(self) -> list[tuple[Phase, Step | None]]:
        """Get ALL phases/steps for menu display (including complete ones).

        Returns list of tuples: (phase, step) where step is None for phase headers.
        This provides a flat list with visual hierarchy for the menu.
        """
        items: list[tuple[Phase, Step | None]] = []
        for phase in self.phases:
            # Add phase header
            items.append((phase, None))
            # Add all steps under this phase
            for step in phase.steps:
                items.append((phase, step))
        return items

    def get_incomplete_steps(self, phase: Phase) -> list[Step]:
        """Get incomplete steps for a specific phase."""
        return [s for s in phase.steps if not s.is_complete]

    def count_complete(self) -> tuple[int, int]:
        """Return (complete_count, total_count) for progress display."""
        total = sum(len(p.steps) for p in self.phases)
        complete = sum(1 for p in self.phases for s in p.steps if s.is_complete)
        return complete, total


@dataclass
class ValidationResult:
    """Result of plan validation."""

    valid: bool
    plan: Plan | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def is_complete(line: str) -> bool:
    """Check if a header line has the COMPLETE marker at end of line."""
    return line.rstrip().endswith("**COMPLETE**")


def mark_complete(line: str) -> str:
    """Add COMPLETE marker to a header line if not already present."""
    if is_complete(line):
        return line
    return line.rstrip() + " **COMPLETE**"


def parse_plan(path: Path) -> Plan:
    """Parse a plan file into structured phases and steps.

    Args:
        path: Path to the markdown plan file

    Returns:
        Plan object with phases and steps extracted

    Raises:
        FileNotFoundError: If plan file doesn't exist
    """
    content = path.read_text()
    lines = content.split("\n")

    plan = Plan(path=path, raw_lines=lines)
    current_phase: Phase | None = None
    current_step: Step | None = None
    content_buffer: list[str] = []

    for i, line in enumerate(lines):
        phase_match = PHASE_PATTERN.match(line)
        step_match = STEP_PATTERN.match(line)

        if phase_match:
            # Save previous step content
            if current_step:
                current_step.content = "\n".join(content_buffer).strip()
            content_buffer = []

            # Save previous phase (only if we had one)
            if current_phase:
                if not current_phase.steps:
                    current_phase.content = "\n".join(content_buffer).strip()
                plan.phases.append(current_phase)

            # Start new phase
            current_phase = Phase(
                number=int(phase_match.group(1)),
                title=phase_match.group(2).strip(),
                content="",
                line_number=i,
                is_complete=is_complete(line),
            )
            current_step = None

        elif step_match and current_phase:
            # Save previous step content
            if current_step:
                current_step.content = "\n".join(content_buffer).strip()
            content_buffer = []

            # Start new step
            current_step = Step(
                number=step_match.group(1),
                title=step_match.group(2).strip(),
                content="",
                line_number=i,
                is_complete=is_complete(line),
            )
            current_phase.steps.append(current_step)

        else:
            content_buffer.append(line)

    # Save final content
    if current_step:
        current_step.content = "\n".join(content_buffer).strip()
    elif current_phase:
        current_phase.content = "\n".join(content_buffer).strip()

    # Save final phase
    if current_phase:
        plan.phases.append(current_phase)

    return plan


def validate_plan(path: Path) -> ValidationResult:
    """Parse and validate a plan file.

    Performs upfront validation before entering interactive loop.

    Args:
        path: Path to the markdown plan file

    Returns:
        ValidationResult with parsed plan (if valid) and any errors/warnings
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        plan = parse_plan(path)
    except FileNotFoundError:
        return ValidationResult(valid=False, plan=None, errors=["Plan file not found"])
    except Exception as e:
        return ValidationResult(valid=False, plan=None, errors=[f"Parse error: {e}"])

    # Error: No phases found
    if not plan.phases:
        errors.append("No phases found. Plan must have at least one '## Phase N: Title' header.")

    # Warning: All items already complete
    all_complete = all(
        p.is_complete or all(s.is_complete for s in p.steps) for p in plan.phases
    )
    if plan.phases and all_complete:
        warnings.append("All phases and steps are already marked complete.")

    # Warning: Phase numbers not sequential
    if plan.phases:
        phase_nums = [p.number for p in plan.phases]
        expected = list(range(1, len(plan.phases) + 1))
        if phase_nums != expected:
            warnings.append(f"Phase numbers not sequential: found {phase_nums}, expected {expected}")

    return ValidationResult(
        valid=len(errors) == 0,
        plan=plan if len(errors) == 0 else None,
        errors=errors,
        warnings=warnings,
    )


def atomic_write(path: Path, content: str) -> None:
    """Write content to file atomically using temp file + rename.

    This ensures the file is never in a partially-written state.
    """
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, content.encode())
        os.close(fd)
        os.rename(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def mark_step_complete(plan: Plan, step: Step) -> None:
    """Mark a single step as complete in the plan file.

    Uses atomic write for safety. Updates both in-memory plan and file.

    Args:
        plan: The parsed plan (will be modified in-place)
        step: The step to mark complete
    """
    if step.is_complete:
        return

    lines = plan.raw_lines.copy()

    # Safety check: verify line matches expected pattern
    original_line = lines[step.line_number]
    expected_prefix = f"### Step {step.number}:"
    if not original_line.startswith(expected_prefix):
        raise ValueError(
            f"Line {step.line_number + 1} does not match expected header. "
            f"Expected '{expected_prefix}...', found '{original_line[:50]}...'"
        )

    # Add completion marker
    lines[step.line_number] = mark_complete(original_line)

    # Update in-memory state
    step.is_complete = True
    plan.raw_lines = lines

    # Atomic write to file
    atomic_write(plan.path, "\n".join(lines))


def mark_phase_complete(plan: Plan, phase: Phase) -> None:
    """Mark a phase header as complete (call after all steps are done).

    Uses atomic write for safety. Updates both in-memory plan and file.

    Args:
        plan: The parsed plan (will be modified in-place)
        phase: The phase to mark complete
    """
    if phase.is_complete:
        return

    lines = plan.raw_lines.copy()

    # Safety check
    original_line = lines[phase.line_number]
    expected_prefix = f"## Phase {phase.number}:"
    if not original_line.startswith(expected_prefix):
        raise ValueError(
            f"Line {phase.line_number + 1} does not match expected header. "
            f"Expected '{expected_prefix}...', found '{original_line[:50]}...'"
        )

    lines[phase.line_number] = mark_complete(original_line)

    phase.is_complete = True
    plan.raw_lines = lines

    atomic_write(plan.path, "\n".join(lines))
```

**Validation:**
```bash
.venv/bin/python -c "from weld.core.plan_parser import parse_plan, Phase, Step; print('OK')"
```

**Failure modes:**
- Import error → check file location and `__init__.py` exports
- Syntax error → run `make check`

### Step 2.2: Export plan_parser from core package

**File:** `src/weld/core/__init__.py`

**Change:** Add imports and exports for plan_parser module

```python
# Add to imports (after existing imports)
from .plan_parser import (
    Phase,
    Plan,
    Step,
    ValidationResult,
    mark_phase_complete,
    mark_step_complete,
    parse_plan,
    validate_plan,
)

# Add to __all__ list
__all__ = [
    # ... existing exports ...
    "Phase",
    "Plan",
    "Step",
    "ValidationResult",
    "mark_phase_complete",
    "mark_step_complete",
    "parse_plan",
    "validate_plan",
]
```

**Validation:**
```bash
.venv/bin/python -c "from weld.core import parse_plan, validate_plan, Phase, Step, Plan; print('OK')"
```

---

## Phase 3: Create Implement Command **COMPLETE**

### Step 3.1: Create implement.py command file

**File:** `src/weld/commands/implement.py` (NEW)

**Content:**

```python
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
from typing import Annotated

import typer
from rich.panel import Panel
from simple_term_menu import TerminalMenu

from ..config import load_config
from ..core import get_weld_dir, validate_plan, mark_step_complete, mark_phase_complete
from ..core.plan_parser import Phase, Plan, Step
from ..output import OutputContext, get_output_context
from ..services import ClaudeError, GitError, get_repo_root, run_claude


class GracefulExit(Exception):
    """Raised when user requests graceful shutdown via Ctrl+C."""

    pass


def _handle_interrupt(signum: int, frame) -> None:
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
    """Implement phases and steps from a plan file.

    INTERACTIVE MODE (default):
    Displays an arrow-key navigable menu to select which phase or step
    to implement. Claude executes the selected item, then marks it
    **COMPLETE** in the plan file. Loop continues until all complete or quit.

    NON-INTERACTIVE MODE (--step or --phase):
    Implements a specific step or all steps in a phase without menu.
    Suitable for CI/automation and scripting.

    Examples:
        weld implement PLAN.md                    # Interactive menu
        weld implement PLAN.md --step 1.1         # Single step
        weld implement PLAN.md --phase 2          # All steps in phase 2
        weld implement PLAN.md --step 1.1 --quiet # No streaming output
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

    if step is not None or phase is not None:
        exit_code = _implement_non_interactive(
            ctx=ctx,
            plan=plan,
            step_number=step,
            phase_number=phase,
            config=config,
            repo_root=repo_root,
            quiet=quiet,
            timeout=effective_timeout,
        )
        raise typer.Exit(exit_code)

    exit_code = _implement_interactive(
        ctx=ctx,
        plan=plan,
        config=config,
        repo_root=repo_root,
        quiet=quiet,
        timeout=effective_timeout,
    )
    raise typer.Exit(exit_code)


def _implement_interactive(
    ctx: OutputContext,
    plan: Plan,
    config,
    repo_root: Path,
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

            # Handle exit
            if selection is None or selection >= len(all_items):
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
                    phase=phase,
                    step=step,
                    config=config,
                    repo_root=repo_root,
                    quiet=quiet,
                    timeout=timeout,
                )
                if not success:
                    ctx.console.print("[yellow]Step not marked complete. Fix issues and retry.[/yellow]")
            else:
                # Phase selected - execute all incomplete steps sequentially
                success = _execute_phase_steps(
                    ctx=ctx,
                    plan=plan,
                    phase=phase,
                    config=config,
                    repo_root=repo_root,
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
    config,
    repo_root: Path,
    quiet: bool,
    timeout: int,
) -> int:
    """Non-interactive implementation of specific step or phase.

    Returns exit code.
    """
    if step_number:
        # Find specific step
        for phase in plan.phases:
            for step in phase.steps:
                if step.number == step_number:
                    if step.is_complete:
                        ctx.console.print(f"[yellow]Step {step_number} already complete[/yellow]")
                        return 0
                    success = _execute_step(
                        ctx=ctx,
                        plan=plan,
                        phase=phase,
                        step=step,
                        config=config,
                        repo_root=repo_root,
                        quiet=quiet,
                        timeout=timeout,
                    )
                    return 0 if success else 21

        ctx.error(f"Step {step_number} not found in plan")
        return 1

    if phase_number:
        # Find specific phase
        for phase in plan.phases:
            if phase.number == phase_number:
                success = _execute_phase_steps(
                    ctx=ctx,
                    plan=plan,
                    phase=phase,
                    config=config,
                    repo_root=repo_root,
                    quiet=quiet,
                    timeout=timeout,
                )
                return 0 if success else 21

        ctx.error(f"Phase {phase_number} not found in plan")
        return 1

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
            items.append(f"{check} Phase {phase.number}: {phase.title} [{complete}/{total} complete]")
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
    phase: Phase,
    step: Step,
    config,
    repo_root: Path,
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
"""

    ctx.console.print(f"\n[bold]Implementing Step {step.number}: {step.title}[/bold]\n")

    claude_exec = config.claude.exec if config.claude else "claude"

    try:
        run_claude(
            prompt=prompt,
            exec_path=claude_exec,
            cwd=repo_root,
            stream=not quiet,
            timeout=timeout,
            skip_permissions=True,
        )
    except ClaudeError as e:
        ctx.console.print(f"\n[red]Error: Claude failed: {e}[/red]")
        return False

    # Mark step complete immediately (atomic write)
    mark_step_complete(plan, step)
    ctx.console.print(f"[green]✓ Step {step.number} marked complete[/green]")
    ctx.console.print("[dim]Tip: Run /compact in Claude Code to save context[/dim]")

    return True


def _execute_phase_steps(
    ctx: OutputContext,
    plan: Plan,
    phase: Phase,
    config,
    repo_root: Path,
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
            phase=phase,
            step=step,
            config=config,
            repo_root=repo_root,
            quiet=quiet,
            timeout=timeout,
        )

        if not success:
            ctx.error(f"Step {step.number} failed. Stopping phase execution.")
            return False

    # All steps done - mark phase complete
    mark_phase_complete(plan, phase)
    ctx.console.print(f"[green]✓ Phase {phase.number} complete[/green]")

    return True
```

**Validation:**
```bash
.venv/bin/python -c "from weld.commands.implement import implement; print('OK')"
```

**Failure modes:**
- Import error → check all imports exist
- Missing TerminalMenu → verify Step 1.1 completed

### Step 3.2: Register command in cli.py

**File:** `src/weld/cli.py`

**Changes:**

1. Add import (after other command imports, around line 18-25):
```python
from .commands.implement import implement
```

2. Add registration (in command registration section, around line 123-129):
```python
app.command()(implement)
```

**Validation:**
```bash
.venv/bin/weld implement --help
```

**Expected output should show:**
- `plan_file` argument (required)
- `--step/-s` option for non-interactive step execution
- `--phase/-p` option for non-interactive phase execution
- `--quiet/-q` option for suppressing streaming
- `--timeout/-t` option
- Command description with both interactive and non-interactive modes

**Failure modes:**
- Command not found → check registration order
- Import error → check implement.py syntax

---

## Phase 4: Add Tests

### Step 4.1: Create test_plan_parser.py

**File:** `tests/test_plan_parser.py` (NEW)

**Content:**

```python
"""Tests for plan file parsing."""

import pytest
from pathlib import Path

from weld.core.plan_parser import (
    parse_plan,
    validate_plan,
    mark_step_complete,
    mark_phase_complete,
    is_complete,
    mark_complete,
    PHASE_PATTERN,
    STEP_PATTERN,
)


class TestPatterns:
    """Test regex patterns for phase/step parsing."""

    @pytest.mark.unit
    def test_phase_pattern_basic(self):
        """Phase pattern matches basic format."""
        match = PHASE_PATTERN.match("## Phase 1: Setup Environment")
        assert match is not None
        assert match.group(1) == "1"
        assert match.group(2) == "Setup Environment"

    @pytest.mark.unit
    def test_phase_pattern_with_complete(self):
        """Phase pattern matches with COMPLETE marker."""
        match = PHASE_PATTERN.match("## Phase 2: Data Models **COMPLETE**")
        assert match is not None
        assert match.group(1) == "2"
        assert match.group(2) == "Data Models"

    @pytest.mark.unit
    def test_step_pattern_integer(self):
        """Step pattern matches integer step numbers."""
        match = STEP_PATTERN.match("### Step 1: Create File")
        assert match is not None
        assert match.group(1) == "1"
        assert match.group(2) == "Create File"

    @pytest.mark.unit
    def test_step_pattern_decimal(self):
        """Step pattern matches decimal step numbers (e.g., 1.1)."""
        match = STEP_PATTERN.match("### Step 1.2: Add Tests")
        assert match is not None
        assert match.group(1) == "1.2"
        assert match.group(2) == "Add Tests"

    @pytest.mark.unit
    def test_step_pattern_with_complete(self):
        """Step pattern matches with COMPLETE marker."""
        match = STEP_PATTERN.match("### Step 3.1: Review **COMPLETE**")
        assert match is not None
        assert match.group(1) == "3.1"
        assert match.group(2) == "Review"

    @pytest.mark.unit
    def test_complete_in_middle_not_matched(self):
        """COMPLETE in middle of title is NOT treated as completion marker."""
        # Edge case: **COMPLETE** appears in title, not at end
        line = "## Phase 2: **COMPLETE** Overhaul"
        assert not is_complete(line)
        match = PHASE_PATTERN.match(line)
        assert match is not None
        assert match.group(2) == "**COMPLETE** Overhaul"


class TestCompletionHelpers:
    """Test is_complete and mark_complete functions."""

    @pytest.mark.unit
    def test_is_complete_true(self):
        """Detects COMPLETE marker at end of line."""
        assert is_complete("## Phase 1: Test **COMPLETE**")
        assert is_complete("### Step 1.1: Test **COMPLETE**  ")  # trailing whitespace

    @pytest.mark.unit
    def test_is_complete_false(self):
        """Returns False when no COMPLETE marker."""
        assert not is_complete("## Phase 1: Test")
        assert not is_complete("## Phase 1: Test **COMPLETE** extra")  # not at end

    @pytest.mark.unit
    def test_mark_complete_adds_marker(self):
        """Adds COMPLETE marker to line."""
        result = mark_complete("## Phase 1: Test")
        assert result == "## Phase 1: Test **COMPLETE**"

    @pytest.mark.unit
    def test_mark_complete_idempotent(self):
        """Doesn't double-add COMPLETE marker."""
        line = "## Phase 1: Test **COMPLETE**"
        result = mark_complete(line)
        assert result == line


class TestParsePlan:
    """Test parse_plan function."""

    @pytest.mark.unit
    def test_parse_simple_plan(self, tmp_path: Path):
        """Parses plan with phases and steps."""
        plan_content = """# Test Plan

## Phase 1: Setup

### Step 1.1: Create files

Create the necessary files.

### Step 1.2: Configure

Set up configuration.

## Phase 2: Implementation

### Step 2.1: Write code

Implement the feature.
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        plan = parse_plan(plan_file)

        assert len(plan.phases) == 2
        assert plan.phases[0].number == 1
        assert plan.phases[0].title == "Setup"
        assert len(plan.phases[0].steps) == 2
        assert plan.phases[0].steps[0].number == "1.1"
        assert plan.phases[0].steps[1].number == "1.2"
        assert plan.phases[1].number == 2
        assert len(plan.phases[1].steps) == 1

    @pytest.mark.unit
    def test_parse_plan_with_complete_markers(self, tmp_path: Path):
        """Detects COMPLETE markers on phases and steps."""
        plan_content = """## Phase 1: Done **COMPLETE**

### Step 1.1: First **COMPLETE**

Done step.

### Step 1.2: Second

Not done.
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        plan = parse_plan(plan_file)

        assert plan.phases[0].is_complete
        assert plan.phases[0].steps[0].is_complete
        assert not plan.phases[0].steps[1].is_complete

    @pytest.mark.unit
    def test_get_all_items_includes_complete(self, tmp_path: Path):
        """get_all_items returns ALL items including completed ones."""
        plan_content = """## Phase 1: Test **COMPLETE**

### Step 1.1: Done **COMPLETE**

## Phase 2: Work

### Step 2.1: Todo
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        plan = parse_plan(plan_file)
        all_items = plan.get_all_items()

        # Should have: Phase 1, Step 1.1, Phase 2, Step 2.1
        assert len(all_items) == 4

    @pytest.mark.unit
    def test_count_complete(self, tmp_path: Path):
        """count_complete returns correct progress."""
        plan_content = """## Phase 1: Test

### Step 1.1: Done **COMPLETE**

### Step 1.2: Todo

## Phase 2: Work

### Step 2.1: Todo
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        plan = parse_plan(plan_file)
        complete, total = plan.count_complete()

        assert complete == 1
        assert total == 3


class TestValidatePlan:
    """Test validate_plan function."""

    @pytest.mark.unit
    def test_valid_plan(self, tmp_path: Path):
        """Valid plan returns valid=True with parsed plan."""
        plan_content = """## Phase 1: Test

### Step 1.1: Do thing
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        result = validate_plan(plan_file)

        assert result.valid
        assert result.plan is not None
        assert len(result.errors) == 0

    @pytest.mark.unit
    def test_no_phases_error(self, tmp_path: Path):
        """Plan with no phases returns error."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Empty Plan\n\nNo phases here.")

        result = validate_plan(plan_file)

        assert not result.valid
        assert result.plan is None
        assert any("No phases found" in e for e in result.errors)

    @pytest.mark.unit
    def test_all_complete_warning(self, tmp_path: Path):
        """All-complete plan returns warning."""
        plan_content = """## Phase 1: Test **COMPLETE**

### Step 1.1: Done **COMPLETE**
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        result = validate_plan(plan_file)

        assert result.valid  # Still valid
        assert any("already marked complete" in w for w in result.warnings)

    @pytest.mark.unit
    def test_file_not_found(self, tmp_path: Path):
        """Missing file returns error."""
        result = validate_plan(tmp_path / "nonexistent.md")

        assert not result.valid
        assert any("not found" in e for e in result.errors)


class TestMarkComplete:
    """Test mark_step_complete and mark_phase_complete functions."""

    @pytest.mark.unit
    def test_mark_step_complete_updates_file(self, tmp_path: Path):
        """mark_step_complete writes atomic update to file."""
        plan_content = """## Phase 1: Test

### Step 1.1: First

Content.
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        plan = parse_plan(plan_file)
        step = plan.phases[0].steps[0]

        mark_step_complete(plan, step)

        # Check file was updated
        updated = plan_file.read_text()
        assert "### Step 1.1: First **COMPLETE**" in updated

        # Check in-memory state updated
        assert step.is_complete

    @pytest.mark.unit
    def test_mark_step_complete_idempotent(self, tmp_path: Path):
        """Marking already-complete step is no-op."""
        plan_content = """## Phase 1: Test

### Step 1.1: First **COMPLETE**
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        plan = parse_plan(plan_file)
        step = plan.phases[0].steps[0]

        # Should not raise or double-mark
        mark_step_complete(plan, step)

        updated = plan_file.read_text()
        # Should have exactly one **COMPLETE**, not two
        assert updated.count("**COMPLETE**") == 1

    @pytest.mark.unit
    def test_mark_phase_complete(self, tmp_path: Path):
        """mark_phase_complete updates phase header."""
        plan_content = """## Phase 1: Test

### Step 1.1: First **COMPLETE**
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        plan = parse_plan(plan_file)
        phase = plan.phases[0]

        mark_phase_complete(plan, phase)

        updated = plan_file.read_text()
        assert "## Phase 1: Test **COMPLETE**" in updated
        assert phase.is_complete


class TestGetIncompleteSteps:
    """Test Plan.get_incomplete_steps method."""

    @pytest.mark.unit
    def test_returns_only_incomplete(self, tmp_path: Path):
        """Returns only incomplete steps for a phase."""
        plan_content = """## Phase 1: Test

### Step 1.1: Done **COMPLETE**

### Step 1.2: Todo

### Step 1.3: Also Todo
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        plan = parse_plan(plan_file)
        incomplete = plan.get_incomplete_steps(plan.phases[0])

        assert len(incomplete) == 2
        assert incomplete[0].number == "1.2"
        assert incomplete[1].number == "1.3"
```

**Validation:**
```bash
.venv/bin/pytest tests/test_plan_parser.py -v
```

**Failure modes:**
- Import error → check core/__init__.py exports
- Test failures → review implementation logic

### Step 4.2: Create test_implement.py for CLI tests

**File:** `tests/test_implement.py` (NEW)

**Content:**

```python
"""Tests for implement command."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from typer.testing import CliRunner

from weld.cli import app


runner = CliRunner()


class TestImplementCommand:
    """Test implement CLI command."""

    @pytest.mark.cli
    def test_implement_help(self):
        """Shows help text with all options."""
        result = runner.invoke(app, ["implement", "--help"])
        assert result.exit_code == 0
        assert "plan_file" in result.output.lower()
        assert "--step" in result.output
        assert "--phase" in result.output
        assert "--quiet" in result.output
        assert "--timeout" in result.output

    @pytest.mark.cli
    def test_implement_file_not_found(self, initialized_weld: Path):
        """Fails with exit code 23 when plan file doesn't exist."""
        result = runner.invoke(app, ["implement", "nonexistent.md", "--step", "1.1"])
        assert result.exit_code == 23
        assert "not found" in result.output.lower()

    @pytest.mark.cli
    def test_implement_dry_run_interactive(self, initialized_weld: Path):
        """Dry run shows interactive mode."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something

Content here.
""")
        result = runner.invoke(app, ["--dry-run", "implement", str(plan_file)])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "Interactive menu" in result.output

    @pytest.mark.cli
    def test_implement_dry_run_step(self, initialized_weld: Path):
        """Dry run shows non-interactive step mode."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: Do something
""")
        result = runner.invoke(app, ["--dry-run", "implement", str(plan_file), "--step", "1.1"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "step 1.1" in result.output.lower()

    @pytest.mark.cli
    def test_implement_empty_plan(self, initialized_weld: Path):
        """Fails with exit code 23 when plan has no phases."""
        plan_file = initialized_weld / "empty-plan.md"
        plan_file.write_text("# Empty Plan\n\nNo phases here.\n")

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])
        assert result.exit_code == 23
        assert "no phases" in result.output.lower()

    @pytest.mark.cli
    def test_implement_step_not_found(self, initialized_weld: Path):
        """Fails when specified step doesn't exist."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step
""")
        result = runner.invoke(app, ["implement", str(plan_file), "--step", "9.9"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @pytest.mark.cli
    def test_implement_phase_not_found(self, initialized_weld: Path):
        """Fails when specified phase doesn't exist."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step
""")
        result = runner.invoke(app, ["implement", str(plan_file), "--phase", "99"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_non_interactive_step(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ):
        """Non-interactive step mode marks step complete."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step

Do this first.
""")
        mock_claude.return_value = "Done."

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

        assert result.exit_code == 0
        updated = plan_file.read_text()
        assert "### Step 1.1: First step **COMPLETE**" in updated

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_step_already_complete(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ):
        """Already complete step returns success without running Claude."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step **COMPLETE**
""")

        result = runner.invoke(app, ["implement", str(plan_file), "--step", "1.1"])

        assert result.exit_code == 0
        assert "already complete" in result.output.lower()
        mock_claude.assert_not_called()

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_phase_sequential(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ):
        """Phase mode executes steps sequentially, marking each complete."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First

Do first.

### Step 1.2: Second

Do second.
""")
        mock_claude.return_value = "Done."

        result = runner.invoke(app, ["implement", str(plan_file), "--phase", "1"])

        assert result.exit_code == 0
        # Claude called twice (once per step)
        assert mock_claude.call_count == 2
        # Both steps marked complete
        updated = plan_file.read_text()
        assert "### Step 1.1: First **COMPLETE**" in updated
        assert "### Step 1.2: Second **COMPLETE**" in updated
        # Phase also marked complete
        assert "## Phase 1: Test **COMPLETE**" in updated

    @pytest.mark.cli
    @patch("weld.commands.implement.run_claude")
    def test_implement_phase_stops_on_failure(
        self,
        mock_claude: MagicMock,
        initialized_weld: Path,
    ):
        """Phase mode stops on first Claude failure."""
        from weld.services import ClaudeError

        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First

### Step 1.2: Second
""")
        # First call succeeds, second fails
        mock_claude.side_effect = [None, ClaudeError("API error")]

        result = runner.invoke(app, ["implement", str(plan_file), "--phase", "1"])

        assert result.exit_code == 21  # Claude failure
        updated = plan_file.read_text()
        # First step marked complete
        assert "### Step 1.1: First **COMPLETE**" in updated
        # Second step NOT marked complete
        assert "### Step 1.2: Second **COMPLETE**" not in updated
        # Phase NOT marked complete
        assert "## Phase 1: Test **COMPLETE**" not in updated

    @pytest.mark.cli
    @patch("weld.commands.implement.TerminalMenu")
    @patch("weld.commands.implement.run_claude")
    def test_implement_interactive_marks_complete(
        self,
        mock_claude: MagicMock,
        mock_menu: MagicMock,
        initialized_weld: Path,
    ):
        """Interactive mode marks step complete after successful implementation."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step

Do this first.
""")
        # Mock menu: select step (index 1, since phase header is 0), then exit (index 3)
        mock_menu_instance = MagicMock()
        mock_menu_instance.show.side_effect = [1, 3]  # Select Step 1.1, then exit
        mock_menu.return_value = mock_menu_instance

        mock_claude.return_value = "Done."

        result = runner.invoke(app, ["implement", str(plan_file)])

        assert result.exit_code == 0
        updated = plan_file.read_text()
        assert "**COMPLETE**" in updated

    @pytest.mark.cli
    def test_implement_json_mode_requires_step_or_phase(self, initialized_weld: Path):
        """JSON mode without --step or --phase fails."""
        plan_file = initialized_weld / "test-plan.md"
        plan_file.write_text("""## Phase 1: Test

### Step 1.1: First step
""")

        result = runner.invoke(app, ["--json", "implement", str(plan_file)])

        assert result.exit_code == 1
        assert "not supported with --json" in result.output.lower()
```

**Validation:**
```bash
.venv/bin/pytest tests/test_implement.py -v
```

---

## Phase 5: Validation and Polish

### Step 5.1: Run full test suite

**Command:**
```bash
make test
```

**Expected:** All tests pass

**Failure modes:**
- New tests fail → fix implementation
- Existing tests break → check for regressions

### Step 5.2: Run type checking

**Command:**
```bash
make typecheck
```

**Expected:** No type errors

**Failure modes:**
- Type errors in plan_parser.py → add type hints
- Type errors in implement.py → fix function signatures

### Step 5.3: Run linting

**Command:**
```bash
make check
```

**Expected:** All checks pass

**Failure modes:**
- Linting errors → run `make lint-fix`
- Format errors → run `make format`

### Step 5.4: Manual integration test

**Commands:**
```bash
# Create a test plan
cat > /tmp/test-plan.md << 'EOF'
## Phase 1: Test Phase

### Step 1.1: First Step

Create a file called `test-output.txt` with "Hello World".

#### Validation
```bash
cat test-output.txt
```

### Step 1.2: Second Step

Append " from weld" to `test-output.txt`.

#### Validation
```bash
cat test-output.txt  # Should show "Hello World from weld"
```
EOF

# Run implement command
.venv/bin/weld implement /tmp/test-plan.md
```

**Expected behavior:**
1. Menu appears with Step 1.1 and Step 1.2
2. Arrow keys navigate, Enter selects
3. Claude implements selected step
4. Step marked `**COMPLETE**` in plan file
5. Menu re-displays with remaining items
6. Exit option works

---

## Summary

| Phase | Steps | New Files | Modified Files |
|-------|-------|-----------|----------------|
| 1 | 1 | - | `pyproject.toml` |
| 2 | 2 | `src/weld/core/plan_parser.py` | `src/weld/core/__init__.py` |
| 3 | 2 | `src/weld/commands/implement.py` | `src/weld/cli.py` |
| 4 | 2 | `tests/test_plan_parser.py`, `tests/test_implement.py` | - |
| 5 | 4 | - | - |

**Total:** 5 phases, 11 steps

## Exit Codes

| Code | Meaning | Example |
|------|---------|---------|
| 0 | Success, user quit, or interrupted | Normal completion, `q` pressed, Ctrl+C |
| 1 | Input validation error | Step/phase not found, weld not initialized |
| 3 | Not a git repository | Running outside git repo |
| 21 | Claude/AI operation failed | API error, timeout |
| 23 | Plan parse/validation error | No phases found, file not found |

## Design Decisions (resolved from research)

These questions from the research document are now resolved in this plan:

1. **`/compact` handling:** → **Tip message** - prints `"Tip: Run /compact in Claude Code to save context"` after each step. Cannot be automated as it operates on outer Claude Code session.

2. **Menu structure:** → **Nested tree view with visual indicators** - shows all phases/steps with `✓`/`○` checkmarks and `[N/M complete]` progress counters.

3. **Phase-level selection:** → **Sequential execution** - when a phase is selected, all incomplete steps are executed one-by-one with checkpoints after each. Stops on first failure.

4. **Completed item handling:** → **Show warning** - selecting a completed item shows `"Step X.X is already complete."` and returns to menu. No re-execution.

5. **Non-interactive mode:** → **Implemented** - `--step` and `--phase` flags for CI/automation use cases.

6. **Signal handling:** → **Graceful shutdown** - Ctrl+C triggers `GracefulExit` exception, preserves all completed work, prints `"Interrupted. Progress has been saved."`

7. **Atomic writes:** → **Implemented** - uses temp file + rename for safe file updates.
