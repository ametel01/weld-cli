"""Plan file parser for extracting phases and steps.

Parses markdown plan files with the format:
- ## Phase N: Title
- ### Step N.N: Title
- **COMPLETE** suffix marks completion
"""

import contextlib
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Regex patterns - handle both "Step 1" and "Step 1.1" formats
# Note: Title group uses non-greedy match to exclude trailing **COMPLETE**
PHASE_PATTERN = re.compile(r"^## Phase (\d+):\s*(.+?)(?:\s*\*\*COMPLETE\*\*)?$")
STEP_PATTERN = re.compile(r"^### Step (\d+(?:\.\d+)?):\s*(.+?)(?:\s*\*\*COMPLETE\*\*)?$")


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

    def get_phase_by_number(self, number: int) -> Phase | None:
        """Find a phase by its number.

        Args:
            number: Phase number (1-based)

        Returns:
            Phase if found, None otherwise
        """
        for phase in self.phases:
            if phase.number == number:
                return phase
        return None

    def get_step_by_number(self, number: str) -> tuple[Phase, Step] | None:
        """Find a step by its number string.

        Args:
            number: Step number (e.g., "1", "1.1", "2.3")

        Returns:
            Tuple of (phase, step) if found, None otherwise
        """
        for phase in self.phases:
            for step in phase.steps:
                if step.number == number:
                    return (phase, step)
        return None


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

            # Save previous phase (only if we had one)
            # NOTE: Must save phase content BEFORE clearing buffer
            if current_phase:
                if not current_phase.steps:
                    current_phase.content = "\n".join(content_buffer).strip()
                plan.phases.append(current_phase)

            content_buffer = []

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
    all_complete = all(p.is_complete or all(s.is_complete for s in p.steps) for p in plan.phases)
    if plan.phases and all_complete:
        warnings.append("All phases and steps are already marked complete.")

    # Warning: Phase numbers not sequential
    if plan.phases:
        phase_nums = [p.number for p in plan.phases]
        expected = list(range(1, len(plan.phases) + 1))
        if phase_nums != expected:
            warnings.append(
                f"Phase numbers not sequential: found {phase_nums}, expected {expected}"
            )

    return ValidationResult(
        valid=len(errors) == 0,
        plan=plan if len(errors) == 0 else None,
        errors=errors,
        warnings=warnings,
    )


def atomic_write(path: Path, content: str) -> None:
    """Write content to file atomically using temp file + rename.

    This ensures the file is never in a partially-written state.
    Uses try/finally to guarantee fd is closed even on failure.
    """
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, content.encode())
    except Exception:
        os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
    os.close(fd)
    try:
        os.rename(tmp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
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
