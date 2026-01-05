"""Tests for weld.core.weld_dir module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from weld.core.weld_dir import get_weld_dir


@pytest.mark.unit
class TestGetWeldDir:
    """Tests for get_weld_dir function."""

    def test_returns_weld_dir_path(self, tmp_path: Path) -> None:
        """Returns .weld directory under repo root."""
        repo_root = tmp_path / "my-repo"
        repo_root.mkdir()

        result = get_weld_dir(repo_root)

        assert result == repo_root / ".weld"

    def test_does_not_create_directory(self, tmp_path: Path) -> None:
        """Does not create the .weld directory."""
        repo_root = tmp_path / "my-repo"
        repo_root.mkdir()

        result = get_weld_dir(repo_root)

        assert not result.exists()

    def test_returns_existing_weld_dir(self, tmp_path: Path) -> None:
        """Works with existing .weld directory."""
        repo_root = tmp_path / "my-repo"
        repo_root.mkdir()
        weld_dir = repo_root / ".weld"
        weld_dir.mkdir()

        result = get_weld_dir(repo_root)

        assert result == weld_dir
        assert result.exists()

    def test_auto_detects_repo_root(self, tmp_path: Path) -> None:
        """Auto-detects repo root when not provided."""
        repo_root = tmp_path / "my-repo"
        repo_root.mkdir()

        with patch("weld.core.weld_dir.get_repo_root", return_value=repo_root):
            result = get_weld_dir()

        assert result == repo_root / ".weld"

    def test_with_none_repo_root(self, tmp_path: Path) -> None:
        """Handles None repo_root by auto-detecting."""
        repo_root = tmp_path / "my-repo"
        repo_root.mkdir()

        with patch("weld.core.weld_dir.get_repo_root", return_value=repo_root):
            result = get_weld_dir(None)

        assert result == repo_root / ".weld"

    def test_returns_path_object(self, tmp_path: Path) -> None:
        """Returns a Path object."""
        repo_root = tmp_path / "my-repo"
        repo_root.mkdir()

        result = get_weld_dir(repo_root)

        assert isinstance(result, Path)

    def test_nested_repo_structure(self, tmp_path: Path) -> None:
        """Works with nested directory structure."""
        repo_root = tmp_path / "projects" / "my-repo"
        repo_root.mkdir(parents=True)

        result = get_weld_dir(repo_root)

        assert result == repo_root / ".weld"
        assert result.parent == repo_root
