"""Tests for diff utilities."""

import subprocess
from pathlib import Path

from weld.services.diff import capture_diff, write_diff


class TestCaptureDiff:
    """Tests for capture_diff function."""

    def test_empty_diff_returns_false(self, temp_git_repo: Path) -> None:
        """capture_diff should return (empty, False) with no changes."""
        content, nonempty = capture_diff(temp_git_repo)
        assert content == ""
        assert nonempty is False

    def test_with_changes_returns_true(self, temp_git_repo: Path) -> None:
        """capture_diff should return (diff, True) with changes."""
        (temp_git_repo / "README.md").write_text("# Changed content\n")
        content, nonempty = capture_diff(temp_git_repo)
        assert nonempty is True
        assert "Changed content" in content

    def test_staged_diff(self, temp_git_repo: Path) -> None:
        """capture_diff with staged=True should capture staged changes."""
        (temp_git_repo / "README.md").write_text("# Staged\n")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        content, nonempty = capture_diff(temp_git_repo, staged=True)
        assert nonempty is True
        assert "Staged" in content

    def test_unstaged_only(self, temp_git_repo: Path) -> None:
        """capture_diff should capture unstaged changes by default."""
        # Stage a file, then make unstaged changes
        (temp_git_repo / "test.txt").write_text("initial")
        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add test.txt"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        # Make unstaged changes
        (temp_git_repo / "test.txt").write_text("modified")
        content, nonempty = capture_diff(temp_git_repo, staged=False)
        assert nonempty is True
        assert "modified" in content


class TestWriteDiff:
    """Tests for write_diff function."""

    def test_writes_content(self, tmp_path: Path) -> None:
        """write_diff should write diff content to file."""
        output_path = tmp_path / "diff.patch"
        write_diff(output_path, "+added line\n-removed line")
        assert output_path.read_text() == "+added line\n-removed line"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        """write_diff should create parent directories."""
        output_path = tmp_path / "nested" / "dir" / "diff.patch"
        write_diff(output_path, "diff content")
        assert output_path.exists()
        assert output_path.read_text() == "diff content"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        """write_diff should overwrite existing file."""
        output_path = tmp_path / "diff.patch"
        output_path.write_text("old content")
        write_diff(output_path, "new content")
        assert output_path.read_text() == "new content"

    def test_empty_content(self, tmp_path: Path) -> None:
        """write_diff should handle empty content."""
        output_path = tmp_path / "empty.patch"
        write_diff(output_path, "")
        assert output_path.read_text() == ""
