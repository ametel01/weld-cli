"""Tests for validation utilities."""

from pathlib import Path

import pytest

from weld.validation import ValidationError, validate_path_within_repo, validate_run_id


class TestPathValidation:
    """Tests for path validation."""

    def test_valid_path_within_repo(self, tmp_path: Path) -> None:
        """Path inside repo should be accepted."""
        sub_path = tmp_path / "subdir" / "file.txt"
        result = validate_path_within_repo(sub_path, tmp_path)
        assert result.is_relative_to(tmp_path)

    def test_relative_path_within_repo(self, tmp_path: Path) -> None:
        """Relative path that resolves inside repo should be accepted."""
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()
        file_path = sub_dir / ".." / "other" / "file.txt"
        result = validate_path_within_repo(file_path, tmp_path)
        assert result.is_relative_to(tmp_path)

    def test_path_escape_rejected(self, tmp_path: Path) -> None:
        """Path traversal attempt should be rejected."""
        escape_path = tmp_path / ".." / "outside"
        with pytest.raises(ValidationError, match="outside repository"):
            validate_path_within_repo(escape_path, tmp_path)

    def test_absolute_path_outside_repo(self, tmp_path: Path) -> None:
        """Absolute path outside repo should be rejected."""
        outside_path = Path("/etc/passwd")
        with pytest.raises(ValidationError, match="outside repository"):
            validate_path_within_repo(outside_path, tmp_path)


class TestRunIdValidation:
    """Tests for run ID validation."""

    def test_valid_run_id(self) -> None:
        """Valid run ID should be accepted."""
        result = validate_run_id("20260104-120000-my-feature")
        assert result == "20260104-120000-my-feature"

    def test_valid_run_id_with_numbers(self) -> None:
        """Run ID with numbers in slug should be accepted."""
        result = validate_run_id("20260104-120000-feature-123")
        assert result == "20260104-120000-feature-123"

    def test_invalid_run_id_format(self) -> None:
        """Invalid format should be rejected."""
        with pytest.raises(ValidationError, match="Invalid run ID"):
            validate_run_id("invalid-format")

    def test_invalid_run_id_uppercase(self) -> None:
        """Uppercase in slug should be rejected."""
        with pytest.raises(ValidationError, match="Invalid run ID"):
            validate_run_id("20260104-120000-MyFeature")

    def test_invalid_run_id_missing_slug(self) -> None:
        """Missing slug should be rejected."""
        with pytest.raises(ValidationError, match="Invalid run ID"):
            validate_run_id("20260104-120000")

    def test_invalid_run_id_wrong_date_format(self) -> None:
        """Wrong date format should be rejected."""
        with pytest.raises(ValidationError, match="Invalid run ID"):
            validate_run_id("2026-01-04-120000-feature")
