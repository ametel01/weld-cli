"""Tests for git operations."""

import subprocess
from pathlib import Path

import pytest

from weld.services.git import (
    GitError,
    commit_file,
    get_current_branch,
    get_diff,
    get_head_sha,
    get_repo_root,
    get_status_porcelain,
    has_staged_changes,
    run_git,
    stage_all,
)


class TestRunGit:
    """Tests for run_git function."""

    def test_simple_command(self, temp_git_repo: Path) -> None:
        """run_git should execute git commands."""
        result = run_git("status", cwd=temp_git_repo)
        assert "On branch" in result

    def test_returns_stdout(self, temp_git_repo: Path) -> None:
        """run_git should return stripped stdout."""
        result = run_git("rev-parse", "--short", "HEAD", cwd=temp_git_repo)
        assert len(result) >= 7  # Short SHA

    def test_raises_on_failure(self, temp_git_repo: Path) -> None:
        """run_git with check=True should raise on failure."""
        with pytest.raises(GitError, match="failed"):
            run_git("checkout", "nonexistent-branch", cwd=temp_git_repo)

    def test_no_raise_with_check_false(self, temp_git_repo: Path) -> None:
        """run_git with check=False should not raise."""
        result = run_git("diff", "--staged", "--quiet", cwd=temp_git_repo, check=False)
        assert isinstance(result, str)


class TestGetRepoRoot:
    """Tests for get_repo_root function."""

    def test_returns_repo_root(self, temp_git_repo: Path) -> None:
        """get_repo_root should return the repository root."""
        result = get_repo_root(temp_git_repo)
        assert result == temp_git_repo

    def test_from_subdirectory(self, temp_git_repo: Path) -> None:
        """get_repo_root should work from subdirectory."""
        subdir = temp_git_repo / "subdir"
        subdir.mkdir()
        result = get_repo_root(subdir)
        assert result == temp_git_repo

    def test_raises_outside_repo(self, tmp_path: Path) -> None:
        """get_repo_root should raise outside a repo."""
        with pytest.raises(GitError, match="Not a git repository"):
            get_repo_root(tmp_path)


class TestGetCurrentBranch:
    """Tests for get_current_branch function."""

    def test_returns_branch_name(self, temp_git_repo: Path) -> None:
        """get_current_branch should return current branch."""
        result = get_current_branch(temp_git_repo)
        # Default branch may be master or main
        assert result in ["master", "main"]


class TestGetHeadSha:
    """Tests for get_head_sha function."""

    def test_returns_full_sha(self, temp_git_repo: Path) -> None:
        """get_head_sha should return full SHA."""
        result = get_head_sha(temp_git_repo)
        assert len(result) == 40  # Full SHA length


class TestGetDiff:
    """Tests for get_diff function."""

    def test_empty_diff(self, temp_git_repo: Path) -> None:
        """get_diff should return empty string with no changes."""
        result = get_diff(cwd=temp_git_repo)
        assert result == ""

    def test_unstaged_changes(self, temp_git_repo: Path) -> None:
        """get_diff should show unstaged changes."""
        (temp_git_repo / "README.md").write_text("# Changed\n")
        result = get_diff(cwd=temp_git_repo)
        assert "+# Changed" in result or "Changed" in result

    def test_staged_changes(self, temp_git_repo: Path) -> None:
        """get_diff with staged=True should show staged changes."""
        (temp_git_repo / "README.md").write_text("# Staged change\n")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        result = get_diff(staged=True, cwd=temp_git_repo)
        assert "Staged change" in result


class TestGetStatusPorcelain:
    """Tests for get_status_porcelain function."""

    def test_clean_repo(self, temp_git_repo: Path) -> None:
        """get_status_porcelain should return empty for clean repo."""
        result = get_status_porcelain(temp_git_repo)
        assert result == ""

    def test_modified_file(self, temp_git_repo: Path) -> None:
        """get_status_porcelain should show modified files."""
        (temp_git_repo / "README.md").write_text("# Modified\n")
        result = get_status_porcelain(temp_git_repo)
        assert "README.md" in result

    def test_new_file(self, temp_git_repo: Path) -> None:
        """get_status_porcelain should show new files."""
        (temp_git_repo / "new.txt").write_text("new file")
        result = get_status_porcelain(temp_git_repo)
        assert "new.txt" in result


class TestStageAll:
    """Tests for stage_all function."""

    def test_stages_new_files(self, temp_git_repo: Path) -> None:
        """stage_all should stage new files."""
        (temp_git_repo / "new.txt").write_text("new content")
        stage_all(temp_git_repo)

        result = get_status_porcelain(temp_git_repo)
        assert "A" in result or result.startswith("A")

    def test_stages_modified_files(self, temp_git_repo: Path) -> None:
        """stage_all should stage modified files."""
        (temp_git_repo / "README.md").write_text("# Modified\n")
        stage_all(temp_git_repo)

        # Check staged diff exists
        diff = get_diff(staged=True, cwd=temp_git_repo)
        assert "Modified" in diff


class TestCommitFile:
    """Tests for commit_file function."""

    def test_creates_commit(self, temp_git_repo: Path) -> None:
        """commit_file should create a commit."""
        # Make a change
        (temp_git_repo / "test.txt").write_text("test content")
        stage_all(temp_git_repo)

        # Create message file
        msg_file = temp_git_repo / "commit_msg.txt"
        msg_file.write_text("Test commit message")

        old_sha = get_head_sha(temp_git_repo)
        new_sha = commit_file(msg_file, temp_git_repo)

        assert new_sha != old_sha
        assert len(new_sha) == 40


class TestHasStagedChanges:
    """Tests for has_staged_changes function."""

    def test_no_staged_changes(self, temp_git_repo: Path) -> None:
        """has_staged_changes should return False when clean."""
        result = has_staged_changes(temp_git_repo)
        assert result is False

    def test_with_staged_changes(self, temp_git_repo: Path) -> None:
        """has_staged_changes should return True when changes staged."""
        (temp_git_repo / "README.md").write_text("# Changed\n")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        result = has_staged_changes(temp_git_repo)
        assert result is True

    def test_with_unstaged_changes(self, temp_git_repo: Path) -> None:
        """has_staged_changes should return False for unstaged only."""
        (temp_git_repo / "README.md").write_text("# Changed\n")
        result = has_staged_changes(temp_git_repo)
        assert result is False
