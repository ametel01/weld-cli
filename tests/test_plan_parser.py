"""Tests for plan file parsing."""

from pathlib import Path

import pytest

from weld.core.plan_parser import (
    PHASE_PATTERN,
    STEP_PATTERN,
    is_complete,
    mark_complete,
    mark_phase_complete,
    mark_step_complete,
    parse_plan,
    validate_plan,
)


class TestPatterns:
    """Test regex patterns for phase/step parsing."""

    @pytest.mark.unit
    def test_phase_pattern_basic(self) -> None:
        """Phase pattern matches basic format."""
        match = PHASE_PATTERN.match("## Phase 1: Setup Environment")
        assert match is not None
        assert match.group(1) == "1"
        assert match.group(2) == "Setup Environment"

    @pytest.mark.unit
    def test_phase_pattern_with_complete(self) -> None:
        """Phase pattern matches with COMPLETE marker."""
        match = PHASE_PATTERN.match("## Phase 2: Data Models **COMPLETE**")
        assert match is not None
        assert match.group(1) == "2"
        assert match.group(2) == "Data Models"

    @pytest.mark.unit
    def test_step_pattern_integer(self) -> None:
        """Step pattern matches integer step numbers."""
        match = STEP_PATTERN.match("### Step 1: Create File")
        assert match is not None
        assert match.group(1) == "1"
        assert match.group(2) == "Create File"

    @pytest.mark.unit
    def test_step_pattern_decimal(self) -> None:
        """Step pattern matches decimal step numbers (e.g., 1.1)."""
        match = STEP_PATTERN.match("### Step 1.2: Add Tests")
        assert match is not None
        assert match.group(1) == "1.2"
        assert match.group(2) == "Add Tests"

    @pytest.mark.unit
    def test_step_pattern_with_complete(self) -> None:
        """Step pattern matches with COMPLETE marker."""
        match = STEP_PATTERN.match("### Step 3.1: Review **COMPLETE**")
        assert match is not None
        assert match.group(1) == "3.1"
        assert match.group(2) == "Review"

    @pytest.mark.unit
    def test_complete_in_middle_not_matched(self) -> None:
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
    def test_is_complete_true(self) -> None:
        """Detects COMPLETE marker at end of line."""
        assert is_complete("## Phase 1: Test **COMPLETE**")
        assert is_complete("### Step 1.1: Test **COMPLETE**  ")  # trailing whitespace

    @pytest.mark.unit
    def test_is_complete_false(self) -> None:
        """Returns False when no COMPLETE marker."""
        assert not is_complete("## Phase 1: Test")
        assert not is_complete("## Phase 1: Test **COMPLETE** extra")  # not at end

    @pytest.mark.unit
    def test_mark_complete_adds_marker(self) -> None:
        """Adds COMPLETE marker to line."""
        result = mark_complete("## Phase 1: Test")
        assert result == "## Phase 1: Test **COMPLETE**"

    @pytest.mark.unit
    def test_mark_complete_idempotent(self) -> None:
        """Doesn't double-add COMPLETE marker."""
        line = "## Phase 1: Test **COMPLETE**"
        result = mark_complete(line)
        assert result == line


class TestParsePlan:
    """Test parse_plan function."""

    @pytest.mark.unit
    def test_parse_simple_plan(self, tmp_path: Path) -> None:
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
    def test_parse_plan_with_complete_markers(self, tmp_path: Path) -> None:
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
    def test_get_all_items_includes_complete(self, tmp_path: Path) -> None:
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
    def test_count_complete(self, tmp_path: Path) -> None:
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
    def test_valid_plan(self, tmp_path: Path) -> None:
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
    def test_no_phases_error(self, tmp_path: Path) -> None:
        """Plan with no phases returns error."""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text("# Empty Plan\n\nNo phases here.")

        result = validate_plan(plan_file)

        assert not result.valid
        assert result.plan is None
        assert any("No phases found" in e for e in result.errors)

    @pytest.mark.unit
    def test_all_complete_warning(self, tmp_path: Path) -> None:
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
    def test_file_not_found(self, tmp_path: Path) -> None:
        """Missing file returns error."""
        result = validate_plan(tmp_path / "nonexistent.md")

        assert not result.valid
        assert any("not found" in e for e in result.errors)


class TestMarkComplete:
    """Test mark_step_complete and mark_phase_complete functions."""

    @pytest.mark.unit
    def test_mark_step_complete_updates_file(self, tmp_path: Path) -> None:
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
    def test_mark_step_complete_idempotent(self, tmp_path: Path) -> None:
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
    def test_mark_phase_complete(self, tmp_path: Path) -> None:
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
    def test_returns_only_incomplete(self, tmp_path: Path) -> None:
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


class TestGetPhaseByNumber:
    """Test Plan.get_phase_by_number method."""

    @pytest.mark.unit
    def test_finds_existing_phase(self, tmp_path: Path) -> None:
        """Returns phase when found."""
        plan_content = """## Phase 1: First

### Step 1.1: A

## Phase 2: Second

### Step 2.1: B
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        plan = parse_plan(plan_file)

        phase1 = plan.get_phase_by_number(1)
        assert phase1 is not None
        assert phase1.title == "First"

        phase2 = plan.get_phase_by_number(2)
        assert phase2 is not None
        assert phase2.title == "Second"

    @pytest.mark.unit
    def test_returns_none_for_missing_phase(self, tmp_path: Path) -> None:
        """Returns None when phase not found."""
        plan_content = """## Phase 1: Only Phase

### Step 1.1: A
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        plan = parse_plan(plan_file)

        assert plan.get_phase_by_number(99) is None
        assert plan.get_phase_by_number(0) is None


class TestGetStepByNumber:
    """Test Plan.get_step_by_number method."""

    @pytest.mark.unit
    def test_finds_existing_step(self, tmp_path: Path) -> None:
        """Returns (phase, step) tuple when found."""
        plan_content = """## Phase 1: First

### Step 1.1: A

### Step 1.2: B

## Phase 2: Second

### Step 2.1: C
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        plan = parse_plan(plan_file)

        result = plan.get_step_by_number("1.1")
        assert result is not None
        phase, step = result
        assert phase.number == 1
        assert step.title == "A"

        result = plan.get_step_by_number("2.1")
        assert result is not None
        phase, step = result
        assert phase.number == 2
        assert step.title == "C"

    @pytest.mark.unit
    def test_returns_none_for_missing_step(self, tmp_path: Path) -> None:
        """Returns None when step not found."""
        plan_content = """## Phase 1: Only Phase

### Step 1.1: Only Step
"""
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_content)

        plan = parse_plan(plan_file)

        assert plan.get_step_by_number("9.9") is None
        assert plan.get_step_by_number("1.2") is None
        assert plan.get_step_by_number("2.1") is None
