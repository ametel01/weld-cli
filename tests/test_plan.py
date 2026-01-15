"""Tests for plan command functionality."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from weld.cli import app
from weld.commands.plan import generate_plan_prompt, get_plan_dir

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})


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

    def test_includes_planning_rules(self) -> None:
        """Prompt includes planning rules section."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "## Planning Rules" in prompt
        assert "Monotonic phases" in prompt
        assert "Artifact-driven" in prompt
        assert "Execution ready" in prompt

    def test_includes_phase_structure(self) -> None:
        """Prompt includes phase structure description."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "**Phase structure:**" in prompt
        assert "## Phase <N>: <Title>" in prompt

    def test_includes_phase_validation(self) -> None:
        """Prompt includes phase-level validation section."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "### Phase Validation" in prompt
        assert "<command to verify phase>" in prompt

    def test_includes_step_structure(self) -> None:
        """Prompt includes step structure description."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "### Step <N>: <Title>" in prompt
        assert "Every step MUST have ALL four sections" in prompt

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
        assert "**CORRECT - Output like this instead:**" in prompt
        assert "## Phase 1: CSS Utility Extensions" in prompt
        assert "### Step 1: Add subtitle contrast utility" in prompt
        assert "### Step 2: Add link underline animation" in prompt

    def test_example_shows_wrong_format(self) -> None:
        """Example demonstrates wrong format to avoid."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "**WRONG - Do NOT output like this:**" in prompt
        assert "## Phase 2: Component Styling" in prompt

    def test_includes_output_checklist(self) -> None:
        """Prompt includes output format checklist."""
        prompt = generate_plan_prompt("content", "spec.md")
        assert "## REMINDER: Output Format Checklist" in prompt
        assert "Every phase has `## Phase N: Title` heading" in prompt
        assert "Every step has `### Step N: Title` heading" in prompt

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
        assert "## CRITICAL: Required Output Format" in prompt
        assert "EXACT structure" in prompt
        assert "Every step MUST have ALL four sections" in prompt


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


@pytest.mark.cli
class TestPlanInputValidation:
    """Tests for plan command input validation."""

    def test_plan_spec_not_found(self, tmp_path: Path) -> None:
        """Fails early with helpful hint when spec file doesn't exist."""
        result = runner.invoke(app, ["plan", str(tmp_path / "missing.md")])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()
        assert "ls" in result.output

    def test_plan_spec_is_directory(self, tmp_path: Path) -> None:
        """Fails with helpful hint when spec path is a directory."""
        result = runner.invoke(app, ["plan", str(tmp_path)])

        assert result.exit_code == 1
        assert "directory" in result.output.lower()
        assert "example.md" in result.output

    def test_plan_spec_wrong_extension(self, tmp_path: Path) -> None:
        """Fails with helpful hint when spec file is not markdown."""
        txt_file = tmp_path / "spec.txt"
        txt_file.write_text("content")

        result = runner.invoke(app, ["plan", str(txt_file)])

        assert result.exit_code == 1
        assert "markdown" in result.output.lower()
        assert ".md" in result.output

    def test_plan_output_is_directory(self, tmp_path: Path) -> None:
        """Fails early when output path is an existing directory."""
        spec = tmp_path / "spec.md"
        spec.write_text("# Spec")
        out_dir = tmp_path / "output"
        out_dir.mkdir()

        result = runner.invoke(app, ["plan", str(spec), "-o", str(out_dir)])

        assert result.exit_code == 1
        assert "directory" in result.output.lower()
        assert "--output" in result.output

    def test_plan_output_wrong_extension(self, tmp_path: Path) -> None:
        """Fails early when output path doesn't have .md extension."""
        spec = tmp_path / "spec.md"
        spec.write_text("# Spec")
        out_path = tmp_path / "plan.txt"

        result = runner.invoke(app, ["plan", str(spec), "-o", str(out_path)])

        assert result.exit_code == 1
        assert "markdown" in result.output.lower()
        assert ".md" in result.output
