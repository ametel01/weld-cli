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
    """Tests for run_git function invariants."""

    def test_executes_git_command_and_returns_output(self, temp_git_repo: Path) -> None:
        """Invariant: Git commands execute and return stdout."""
        result = run_git("status", cwd=temp_git_repo)
        assert "On branch" in result

    def test_returns_stripped_stdout(self, temp_git_repo: Path) -> None:
        """Invariant: Output is stripped of leading/trailing whitespace."""
        result = run_git("rev-parse", "--short", "HEAD", cwd=temp_git_repo)
        assert len(result) >= 7  # Short SHA

    def test_raises_git_error_on_command_failure(self, temp_git_repo: Path) -> None:
        """Invariant: Failed commands raise GitError when check=True."""
        with pytest.raises(GitError, match="failed"):
            run_git("checkout", "nonexistent-branch", cwd=temp_git_repo)

    def test_returns_string_without_raising_when_check_false(self, temp_git_repo: Path) -> None:
        """Invariant: Failed commands return string when check=False."""
        result = run_git("diff", "--staged", "--quiet", cwd=temp_git_repo, check=False)
        assert isinstance(result, str)


class TestGetRepoRoot:
    """Tests for get_repo_root function invariants."""

    def test_returns_exact_repo_root_path(self, temp_git_repo: Path) -> None:
        """Invariant: Returns the exact repository root path."""
        result = get_repo_root(temp_git_repo)
        assert result == temp_git_repo

    def test_returns_parent_of_git_directory(self, temp_git_repo: Path) -> None:
        """Invariant: Returned path is the parent of .git directory."""
        result = get_repo_root(temp_git_repo)
        git_dir = result / ".git"
        assert git_dir.exists(), ".git directory must exist in repo root"
        assert git_dir.is_dir(), ".git must be a directory"
        assert git_dir.parent == result, "repo root must be parent of .git"

    def test_resolves_root_from_any_subdirectory(self, temp_git_repo: Path) -> None:
        """Invariant: Subdirectories resolve to same root."""
        subdir = temp_git_repo / "subdir"
        subdir.mkdir()
        result = get_repo_root(subdir)
        assert result == temp_git_repo

    def test_raises_git_error_outside_repository(self, tmp_path: Path) -> None:
        """Invariant: Non-repo paths raise GitError."""
        with pytest.raises(GitError, match="Not a git repository"):
            get_repo_root(tmp_path)


class TestGetCurrentBranch:
    """Tests for get_current_branch function invariants."""

    def test_returns_current_branch_name(self, temp_git_repo: Path) -> None:
        """Invariant: Returns the current branch name (master or main)."""
        result = get_current_branch(temp_git_repo)
        assert result in ["master", "main"]


class TestGetHeadSha:
    """Tests for get_head_sha function invariants."""

    def test_returns_full_40_character_sha(self, temp_git_repo: Path) -> None:
        """Invariant: SHA is always exactly 40 hex characters."""
        result = get_head_sha(temp_git_repo)
        assert len(result) == 40


class TestGetDiff:
    """Tests for get_diff function invariants."""

    def test_returns_empty_string_when_no_changes(self, temp_git_repo: Path) -> None:
        """Invariant: Clean working directory returns empty string."""
        result = get_diff(cwd=temp_git_repo)
        assert result == ""

    def test_includes_unstaged_changes_in_diff(self, temp_git_repo: Path) -> None:
        """Invariant: Unstaged changes appear in default diff."""
        (temp_git_repo / "README.md").write_text("# Changed\n")
        result = get_diff(cwd=temp_git_repo)
        assert "+# Changed" in result or "Changed" in result

    def test_includes_staged_changes_when_staged_flag_true(self, temp_git_repo: Path) -> None:
        """Invariant: Staged changes appear when staged=True."""
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
    """Tests for get_status_porcelain function invariants."""

    def test_returns_empty_for_clean_repository(self, temp_git_repo: Path) -> None:
        """Invariant: Clean repos return empty status."""
        result = get_status_porcelain(temp_git_repo)
        assert result == ""

    def test_includes_modified_files_in_status(self, temp_git_repo: Path) -> None:
        """Invariant: Modified files appear in status output."""
        (temp_git_repo / "README.md").write_text("# Modified\n")
        result = get_status_porcelain(temp_git_repo)
        assert "README.md" in result

    def test_includes_untracked_files_in_status(self, temp_git_repo: Path) -> None:
        """Invariant: Untracked files appear in status output."""
        (temp_git_repo / "new.txt").write_text("new file")
        result = get_status_porcelain(temp_git_repo)
        assert "new.txt" in result


class TestStageAll:
    """Tests for stage_all function invariants."""

    def test_stages_all_untracked_files(self, temp_git_repo: Path) -> None:
        """Invariant: Untracked files become staged after stage_all."""
        (temp_git_repo / "new.txt").write_text("new content")
        stage_all(temp_git_repo)

        result = get_status_porcelain(temp_git_repo)
        assert "A" in result or result.startswith("A")

    def test_stages_all_modified_files(self, temp_git_repo: Path) -> None:
        """Invariant: Modified files become staged after stage_all."""
        (temp_git_repo / "README.md").write_text("# Modified\n")
        stage_all(temp_git_repo)

        diff = get_diff(staged=True, cwd=temp_git_repo)
        assert "Modified" in diff


class TestCommitFile:
    """Tests for commit_file function invariants."""

    def test_creates_new_commit_with_different_sha(self, temp_git_repo: Path) -> None:
        """Invariant: commit_file creates commit with new SHA."""
        (temp_git_repo / "test.txt").write_text("test content")
        stage_all(temp_git_repo)

        msg_file = temp_git_repo / "commit_msg.txt"
        msg_file.write_text("Test commit message")

        old_sha = get_head_sha(temp_git_repo)
        new_sha = commit_file(msg_file, temp_git_repo)

        assert new_sha != old_sha
        assert len(new_sha) == 40


class TestHasStagedChanges:
    """Tests for has_staged_changes function invariants."""

    def test_returns_false_when_nothing_staged(self, temp_git_repo: Path) -> None:
        """Invariant: Returns False when no staged changes exist."""
        result = has_staged_changes(temp_git_repo)
        assert result is False

    def test_returns_true_when_changes_are_staged(self, temp_git_repo: Path) -> None:
        """Invariant: Returns True when staged changes exist."""
        (temp_git_repo / "README.md").write_text("# Changed\n")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        result = has_staged_changes(temp_git_repo)
        assert result is True

    def test_returns_false_for_unstaged_changes_only(self, temp_git_repo: Path) -> None:
        """Invariant: Returns False when only unstaged changes exist."""
        (temp_git_repo / "README.md").write_text("# Changed\n")
        result = has_staged_changes(temp_git_repo)
        assert result is False


class TestDetachedHead:
    """Tests for git operations in detached HEAD state."""

    def test_get_current_branch_detached(self, temp_git_repo: Path) -> None:
        """get_current_branch returns 'HEAD' when in detached HEAD state."""
        # Get current commit SHA
        sha = get_head_sha(temp_git_repo)

        # Detach HEAD by checking out the commit directly
        subprocess.run(
            ["git", "checkout", sha],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        result = get_current_branch(temp_git_repo)
        assert result == "HEAD"

    def test_get_head_sha_detached(self, temp_git_repo: Path) -> None:
        """get_head_sha works correctly in detached HEAD state."""
        original_sha = get_head_sha(temp_git_repo)

        # Detach HEAD
        subprocess.run(
            ["git", "checkout", original_sha],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        result = get_head_sha(temp_git_repo)
        assert result == original_sha
        assert len(result) == 40

    def test_get_repo_root_detached(self, temp_git_repo: Path) -> None:
        """get_repo_root works correctly in detached HEAD state."""
        sha = get_head_sha(temp_git_repo)

        subprocess.run(
            ["git", "checkout", sha],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        result = get_repo_root(temp_git_repo)
        assert result == temp_git_repo


class TestMergeConflicts:
    """Tests for git operations during merge conflicts."""

    def test_status_shows_conflict_markers(self, temp_git_repo: Path) -> None:
        """get_status_porcelain shows conflict markers during merge."""
        # Create and switch to a feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        # Modify README on feature branch
        (temp_git_repo / "README.md").write_text("# Feature branch content\n")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Feature change"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        # Switch back to main/master and make a conflicting change
        subprocess.run(
            ["git", "checkout", "-"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        (temp_git_repo / "README.md").write_text("# Main branch content\n")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Main change"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        # Attempt merge (will fail with conflicts)
        merge_result = subprocess.run(
            ["git", "merge", "feature"],
            cwd=temp_git_repo,
            capture_output=True,
        )
        assert merge_result.returncode != 0  # Merge should fail

        # Check status shows conflict
        status = get_status_porcelain(temp_git_repo)
        # Conflict markers: UU (unmerged, both modified) or AA/etc.
        assert "README.md" in status
        # Status should contain 'U' indicating unmerged state
        assert "U" in status

    def test_diff_during_conflict(self, temp_git_repo: Path) -> None:
        """get_diff shows conflict content during merge."""
        # Setup merge conflict (same as above)
        subprocess.run(
            ["git", "checkout", "-b", "feature2"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )
        (temp_git_repo / "README.md").write_text("# Feature2 content\n")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Feature2"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        subprocess.run(["git", "checkout", "-"], cwd=temp_git_repo, check=True, capture_output=True)
        (temp_git_repo / "README.md").write_text("# Main2 content\n")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Main2"],
            cwd=temp_git_repo,
            check=True,
            capture_output=True,
        )

        subprocess.run(["git", "merge", "feature2"], cwd=temp_git_repo, capture_output=True)

        # During conflict, git diff should still work (not raise)
        diff = get_diff(cwd=temp_git_repo)
        assert isinstance(diff, str)

        # The working directory now has conflict markers in the file
        content = (temp_git_repo / "README.md").read_text()
        assert "<<<<<<<" in content or "=======" in content
