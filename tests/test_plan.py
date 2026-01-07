"""Tests for plan command functionality."""

from pathlib import Path

import pytest

from weld.commands.plan import generate_plan_prompt, get_plan_dir


@pytest.mark.unit
class TestGeneratePlanPrompt:
    """Tests for generate_plan_prompt function."""

    def test_includes_spec_content(self) -> None:
        """Prompt includes the specification content."""
        prompt = generate_plan_prompt("Build a widget parser", "spec.md")
        assert "Build a widget parser" in prompt

    def test_includes_spec_name(self) -> None:
        """Prompt includes specification filename."""
        prompt = generate_plan_prompt("content", "my-feature.md")
        assert "my-feature.md" in prompt

    def test_includes_implementation_plan_request(self) -> None:
        """Prompt includes Implementation Plan Request header."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "# Implementation Plan Request" in prompt

    def test_includes_planning_principles(self) -> None:
        """Prompt includes planning principles section."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "## Planning Principles" in prompt
        assert "highest-leverage" in prompt
        assert "exact steps" in prompt
        assert "failure modes" in prompt

    def test_includes_phase_structure(self) -> None:
        """Prompt includes phase structure description."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "### Phase Structure" in prompt
        assert "## Phase <number>:" in prompt
        assert "logical milestone" in prompt

    def test_includes_phase_validation(self) -> None:
        """Prompt includes phase-level validation section."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "### Phase Validation" in prompt
        assert "verify the entire phase" in prompt

    def test_includes_step_structure(self) -> None:
        """Prompt includes step structure description."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "### Step Structure" in prompt
        assert "### Step <number>:" in prompt
        assert "Step numbers restart at 1 within each phase" in prompt

    def test_includes_step_sections(self) -> None:
        """Prompt includes required step sections."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "#### Goal" in prompt
        assert "#### Files" in prompt
        assert "#### Validation" in prompt
        assert "#### Failure modes" in prompt

    def test_includes_concrete_example(self) -> None:
        """Prompt includes a concrete example plan."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "## Example" in prompt
        assert "## Phase 1: Data Models" in prompt
        assert "### Step 1: Create user model" in prompt
        assert "### Step 2: Add validation logic" in prompt
        assert "## Phase 2: Core Logic" in prompt

    def test_example_shows_step_restart(self) -> None:
        """Example demonstrates step numbering restarts per phase."""
        prompt = generate_plan_prompt("content", "spec.md")
        # Phase 2 should have Step 1, not Step 3
        assert "## Phase 2:" in prompt
        # Verify the note about step numbering is present
        assert "Step numbering restarts at 1 for each phase" in prompt

    def test_includes_phase_guidelines(self) -> None:
        """Prompt includes phase guidelines."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "**Phase guidelines:**" in prompt
        assert "logical milestone" in prompt
        assert "incremental" in prompt
        assert "completable and testable" in prompt
        assert "Phase Validation section" in prompt

    def test_includes_step_guidelines(self) -> None:
        """Prompt includes step guidelines."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "**Step guidelines:**" in prompt
        assert "Step numbers restart at 1 within each new phase" in prompt
        assert "independently verifiable" in prompt
        assert "atomic and focused" in prompt
        assert "Order steps by dependency" in prompt

    def test_spec_appears_in_specification_section(self) -> None:
        """Specification content appears under Specification header."""
        prompt = generate_plan_prompt("My custom spec content", "feature.md")
        assert "## Specification: feature.md" in prompt
        # Verify content follows the header
        spec_index = prompt.index("## Specification:")
        content_index = prompt.index("My custom spec content")
        assert content_index > spec_index

    def test_multiline_spec_content(self) -> None:
        """Handles multiline specification content."""
        spec = """# Feature Title

## Overview
This is a detailed specification.

## Requirements
- Requirement 1
- Requirement 2
"""
        prompt = generate_plan_prompt(spec, "spec.md")
        assert "# Feature Title" in prompt
        assert "## Overview" in prompt
        assert "- Requirement 1" in prompt

    def test_special_characters_in_spec(self) -> None:
        """Handles special characters in specification."""
        spec = "Use `backticks` and **bold** and $variables"
        prompt = generate_plan_prompt(spec, "spec.md")
        assert "`backticks`" in prompt
        assert "**bold**" in prompt
        assert "$variables" in prompt

    def test_output_format_section_exists(self) -> None:
        """Prompt includes Output Format section."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "## Output Format" in prompt
        assert "phased implementation plan" in prompt
        assert "MUST follow this exact structure" in prompt


@pytest.mark.unit
class TestGetPlanDir:
    """Tests for get_plan_dir function."""

    def test_creates_plan_dir(self, tmp_path: Path) -> None:
        """Creates plan directory if it doesn't exist."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        plan_dir = get_plan_dir(weld_dir)

        assert plan_dir.exists()
        assert plan_dir.is_dir()
        assert plan_dir.name == "plan"

    def test_returns_existing_plan_dir(self, tmp_path: Path) -> None:
        """Returns existing plan directory."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        existing = weld_dir / "plan"
        existing.mkdir()
        (existing / "test.txt").write_text("existing")

        plan_dir = get_plan_dir(weld_dir)

        assert plan_dir == existing
        assert (plan_dir / "test.txt").exists()

    def test_plan_dir_path(self, tmp_path: Path) -> None:
        """Plan dir is at .weld/plan."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        plan_dir = get_plan_dir(weld_dir)

        assert plan_dir == weld_dir / "plan"
