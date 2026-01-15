"""Tests for core.validators input validation utilities."""

from pathlib import Path

import pytest

from weld.core.validators import validate_input_file, validate_output_path, validate_plan_file


class TestValidateInputFile:
    """Tests for input file validation."""

    @pytest.mark.unit
    def test_valid_markdown_file(self, tmp_path: Path) -> None:
        """Valid markdown file should pass validation."""
        md_file = tmp_path / "spec.md"
        md_file.write_text("# Spec")
        result = validate_input_file(md_file, must_be_markdown=True)
        assert result is None

    @pytest.mark.unit
    def test_file_not_found(self, tmp_path: Path) -> None:
        """Missing file should return error with hint."""
        missing = tmp_path / "missing.md"
        result = validate_input_file(missing)
        assert result is not None
        error_msg, hint = result
        assert "not found" in error_msg
        assert hint is not None and "ls" in hint

    @pytest.mark.unit
    def test_directory_instead_of_file(self, tmp_path: Path) -> None:
        """Directory path should return error with hint."""
        result = validate_input_file(tmp_path)
        assert result is not None
        error_msg, hint = result
        assert "directory" in error_msg.lower()
        assert hint is not None and "example.md" in hint

    @pytest.mark.unit
    def test_wrong_extension(self, tmp_path: Path) -> None:
        """Non-markdown file should fail when must_be_markdown=True."""
        txt_file = tmp_path / "spec.txt"
        txt_file.write_text("spec content")
        result = validate_input_file(txt_file, must_be_markdown=True)
        assert result is not None
        error_msg, hint = result
        assert "markdown" in error_msg.lower()
        assert hint is not None and ".md" in hint

    @pytest.mark.unit
    def test_any_extension_allowed(self, tmp_path: Path) -> None:
        """Any extension should pass when must_be_markdown=False."""
        txt_file = tmp_path / "spec.txt"
        txt_file.write_text("spec content")
        result = validate_input_file(txt_file, must_be_markdown=False)
        assert result is None

    @pytest.mark.unit
    def test_custom_param_name(self, tmp_path: Path) -> None:
        """Custom param name should appear in error message."""
        missing = tmp_path / "missing.md"
        result = validate_input_file(missing, param_name="specification")
        assert result is not None
        error_msg, _ = result
        assert "Specification" in error_msg


class TestValidateOutputPath:
    """Tests for output path validation."""

    @pytest.mark.unit
    def test_valid_markdown_path(self, tmp_path: Path) -> None:
        """Valid output path should pass validation."""
        out_path = tmp_path / "output.md"
        result = validate_output_path(out_path, must_be_markdown=True)
        assert result is None

    @pytest.mark.unit
    def test_existing_directory(self, tmp_path: Path) -> None:
        """Existing directory should return error with file path hint."""
        result = validate_output_path(tmp_path, must_be_markdown=True)
        assert result is not None
        error_msg, hint = result
        assert "directory" in error_msg.lower()
        assert hint is not None and "--output" in hint
        assert hint is not None and "output.md" in hint

    @pytest.mark.unit
    def test_wrong_extension(self, tmp_path: Path) -> None:
        """Non-markdown path should fail when must_be_markdown=True."""
        out_path = tmp_path / "output.txt"
        result = validate_output_path(out_path, must_be_markdown=True)
        assert result is not None
        error_msg, hint = result
        assert "markdown" in error_msg.lower()
        assert hint is not None and ".md" in hint

    @pytest.mark.unit
    def test_any_extension_allowed(self, tmp_path: Path) -> None:
        """Any extension should pass when must_be_markdown=False."""
        out_path = tmp_path / "output.txt"
        result = validate_output_path(out_path, must_be_markdown=False)
        assert result is None

    @pytest.mark.unit
    def test_nested_new_path(self, tmp_path: Path) -> None:
        """Path with non-existent parent should pass if ancestor exists."""
        out_path = tmp_path / "new_subdir" / "output.md"
        result = validate_output_path(out_path, must_be_markdown=True)
        assert result is None


class TestValidatePlanFile:
    """Tests for plan file validation."""

    @pytest.mark.unit
    def test_valid_plan_file(self, tmp_path: Path) -> None:
        """Valid plan file should pass validation."""
        plan = tmp_path / "plan.md"
        plan.write_text("## Phase 1: Setup")
        result = validate_plan_file(plan)
        assert result is None

    @pytest.mark.unit
    def test_plan_not_found(self, tmp_path: Path) -> None:
        """Missing plan file should return error."""
        missing = tmp_path / "plan.md"
        result = validate_plan_file(missing)
        assert result is not None
        error_msg, hint = result
        assert "not found" in error_msg
        assert hint is not None and "ls" in hint

    @pytest.mark.unit
    def test_directory_with_md_files(self, tmp_path: Path) -> None:
        """Directory with .md files should suggest one."""
        (tmp_path / "implementation-plan.md").write_text("# Plan")
        result = validate_plan_file(tmp_path)
        assert result is not None
        error_msg, hint = result
        assert "directory" in error_msg.lower()
        assert hint is not None and "implementation-plan.md" in hint

    @pytest.mark.unit
    def test_directory_without_md_files(self, tmp_path: Path) -> None:
        """Directory without .md files should give generic hint."""
        result = validate_plan_file(tmp_path)
        assert result is not None
        error_msg, hint = result
        assert "directory" in error_msg.lower()
        assert hint is not None and "plan.md" in hint

    @pytest.mark.unit
    def test_non_markdown_file(self, tmp_path: Path) -> None:
        """Non-markdown file should fail."""
        txt_file = tmp_path / "plan.txt"
        txt_file.write_text("Plan content")
        result = validate_plan_file(txt_file)
        assert result is not None
        error_msg, _ = result
        assert "markdown" in error_msg.lower()
