"""Tests for weld.completions module."""

import pytest

from weld.completions import complete_export_format, complete_task_type
from weld.config import TaskType


@pytest.mark.unit
class TestCompleteTaskType:
    """Tests for complete_task_type function."""

    def test_empty_prefix_returns_all_task_types(self) -> None:
        """Empty prefix should return all TaskType values."""
        result = complete_task_type("")
        expected = [t.value for t in TaskType]
        assert sorted(result) == sorted(expected)

    def test_prefix_filters_results(self) -> None:
        """Prefix should filter to matching task types only."""
        result = complete_task_type("research")
        assert "research" in result
        assert "research_review" in result
        assert "discover" not in result
        assert "implementation" not in result

    def test_prefix_case_insensitive(self) -> None:
        """Prefix matching should be case-insensitive."""
        result = complete_task_type("RESEARCH")
        assert "research" in result
        assert "research_review" in result

    def test_nonmatching_prefix_returns_empty(self) -> None:
        """Non-matching prefix should return empty list."""
        result = complete_task_type("xyz")
        assert result == []

    def test_single_match(self) -> None:
        """Prefix matching only one type returns single result."""
        result = complete_task_type("discover")
        assert result == ["discover"]

    def test_partial_prefix(self) -> None:
        """Partial prefix matches multiple related types."""
        result = complete_task_type("impl")
        assert "implementation" in result
        assert "implementation_review" in result
        assert len(result) == 2

    def test_plan_prefix(self) -> None:
        """Plan prefix matches plan-related types."""
        result = complete_task_type("plan")
        assert "plan_generation" in result
        assert "plan_review" in result
        assert len(result) == 2


@pytest.mark.unit
class TestCompleteExportFormat:
    """Tests for complete_export_format function."""

    def test_empty_prefix_returns_all_formats(self) -> None:
        """Empty prefix should return all available formats."""
        result = complete_export_format("")
        # json and toml are always available
        assert "json" in result
        assert "toml" in result
        # yaml is included if pyyaml is installed
        assert len(result) >= 2

    def test_results_are_sorted(self) -> None:
        """Results should be alphabetically sorted."""
        result = complete_export_format("")
        assert result == sorted(result)

    def test_prefix_filters_results(self) -> None:
        """Prefix should filter to matching formats only."""
        result = complete_export_format("j")
        assert result == ["json"]

    def test_toml_prefix(self) -> None:
        """Toml prefix matches toml format."""
        result = complete_export_format("t")
        assert result == ["toml"]

    def test_prefix_case_insensitive(self) -> None:
        """Prefix matching should be case-insensitive."""
        result = complete_export_format("JSON")
        assert result == ["json"]

    def test_nonmatching_prefix_returns_empty(self) -> None:
        """Non-matching prefix should return empty list."""
        result = complete_export_format("xyz")
        assert result == []

    def test_yaml_available_if_installed(self) -> None:
        """Yaml format is included if pyyaml is available."""
        try:
            import yaml  # noqa: F401

            result = complete_export_format("y")
            assert result == ["yaml"]
        except ImportError:
            # pyyaml not installed, yaml should not be in results
            result = complete_export_format("y")
            assert result == []
