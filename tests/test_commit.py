"""Tests for commit command covering edge cases and helper functions."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from weld.cli import app
from weld.commands.commit import (
    CommitGroup,
    _generate_commit_prompt,
    _normalize_entry,
    _parse_commit_groups,
    _update_changelog,
)

# Sample responses for various test scenarios
MULTI_COMMIT_RESPONSE = """<commit>
<files>
src/feature.py
tests/test_feature.py
</files>
<commit_message>
Add feature implementation

Implements the new feature with full test coverage.
</commit_message>
<changelog_entry>
### Added
- New feature with tests
</changelog_entry>
</commit>

<commit>
<files>
docs/README.md
</files>
<commit_message>
Update documentation
</commit_message>
<changelog_entry>
### Changed
- Updated README with feature docs
</changelog_entry>
</commit>"""

EMPTY_FILES_RESPONSE = """<commit>
<files>
</files>
<commit_message>
Empty files commit
</commit_message>
<changelog_entry>
</changelog_entry>
</commit>"""

MISSING_MESSAGE_RESPONSE = """<commit>
<files>
test.py
</files>
<commit_message>
</commit_message>
<changelog_entry>
</changelog_entry>
</commit>"""

NO_FILES_TAG_RESPONSE = """<commit>
<commit_message>
Missing files tag
</commit_message>
<changelog_entry>
</changelog_entry>
</commit>"""


@pytest.mark.unit
class TestParseCommitGroups:
    """Tests for _parse_commit_groups function edge cases."""

    def test_parses_multiple_commits(self) -> None:
        """Should parse multiple commit blocks correctly."""
        groups = _parse_commit_groups(MULTI_COMMIT_RESPONSE)

        assert len(groups) == 2
        expected_msg = (
            "Add feature implementation\n\nImplements the new feature with full test coverage."
        )
        assert groups[0].message == expected_msg
        assert groups[0].files == ["src/feature.py", "tests/test_feature.py"]
        assert "New feature" in groups[0].changelog_entry
        assert groups[1].message == "Update documentation"
        assert groups[1].files == ["docs/README.md"]

    def test_skips_empty_files_block(self) -> None:
        """Should skip commit blocks with empty files."""
        groups = _parse_commit_groups(EMPTY_FILES_RESPONSE)

        assert len(groups) == 0

    def test_skips_empty_message_block(self) -> None:
        """Should skip commit blocks with empty message."""
        groups = _parse_commit_groups(MISSING_MESSAGE_RESPONSE)

        assert len(groups) == 0

    def test_skips_missing_files_tag(self) -> None:
        """Should skip commit blocks missing files tag entirely."""
        groups = _parse_commit_groups(NO_FILES_TAG_RESPONSE)

        assert len(groups) == 0

    def test_handles_garbage_response(self) -> None:
        """Should return empty list for garbage response."""
        groups = _parse_commit_groups("This is not XML at all")

        assert groups == []

    def test_handles_empty_response(self) -> None:
        """Should return empty list for empty response."""
        groups = _parse_commit_groups("")

        assert groups == []


@pytest.mark.unit
class TestNormalizeEntry:
    """Tests for _normalize_entry function."""

    def test_normalizes_bullet_points(self) -> None:
        """Should normalize bullet points to lowercase."""
        entry = "### Added\n- New Feature Here"
        normalized = _normalize_entry(entry)

        assert normalized == "- new feature here"

    def test_ignores_headers(self) -> None:
        """Should not include headers in output."""
        entry = "### Added\n### Changed\n- Some change"
        normalized = _normalize_entry(entry)

        assert "added" not in normalized
        assert "changed" not in normalized
        assert "- some change" in normalized

    def test_handles_empty_entry(self) -> None:
        """Should handle empty entry."""
        normalized = _normalize_entry("")

        assert normalized == ""


@pytest.mark.unit
class TestUpdateChangelog:
    """Tests for _update_changelog function edge cases."""

    def test_returns_false_for_empty_entry(self, tmp_path: Path) -> None:
        """Should return False when entry is empty."""
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [Unreleased]\n")

        result = _update_changelog(tmp_path, "")

        assert result is False
        # File unchanged
        assert changelog.read_text() == "# Changelog\n\n## [Unreleased]\n"

    def test_returns_false_for_missing_file(self, tmp_path: Path) -> None:
        """Should return False when CHANGELOG.md doesn't exist."""
        result = _update_changelog(tmp_path, "### Added\n- Test entry")

        assert result is False

    def test_returns_false_for_missing_unreleased_section(self, tmp_path: Path) -> None:
        """Should return False when [Unreleased] section is missing."""
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [1.0.0]\n- Release\n")

        result = _update_changelog(tmp_path, "### Added\n- Test entry")

        assert result is False

    def test_detects_duplicate_entry(self, tmp_path: Path) -> None:
        """Should return False when entry already exists."""
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [Unreleased]\n\n### Added\n- Test entry\n\n## [1.0.0]\n"
        )
        original = changelog.read_text()

        result = _update_changelog(tmp_path, "### Added\n- Test entry")

        assert result is False
        assert changelog.read_text() == original

    def test_detects_duplicate_case_insensitive(self, tmp_path: Path) -> None:
        """Should detect duplicates case-insensitively."""
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(
            "# Changelog\n\n## [Unreleased]\n\n### Added\n- TEST ENTRY\n\n## [1.0.0]\n"
        )
        original = changelog.read_text()

        result = _update_changelog(tmp_path, "### Added\n- test entry")

        assert result is False
        assert changelog.read_text() == original

    def test_updates_changelog_successfully(self, tmp_path: Path) -> None:
        """Should update changelog and return True for valid new entry."""
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [Unreleased]\n\n## [1.0.0]\n- Release\n")

        result = _update_changelog(tmp_path, "### Added\n- New feature")

        assert result is True
        content = changelog.read_text()
        assert "### Added" in content
        assert "- New feature" in content


@pytest.mark.unit
class TestGenerateCommitPrompt:
    """Tests for _generate_commit_prompt function."""

    def test_includes_diff(self) -> None:
        """Should include diff in prompt."""
        prompt = _generate_commit_prompt("+ new line", ["test.py"], "")

        assert "+ new line" in prompt

    def test_includes_staged_files(self) -> None:
        """Should include staged files list."""
        prompt = _generate_commit_prompt("diff", ["file1.py", "file2.py"], "")

        assert "- file1.py" in prompt
        assert "- file2.py" in prompt

    def test_includes_changelog_context(self) -> None:
        """Should include current changelog content."""
        prompt = _generate_commit_prompt("diff", ["test.py"], "### Added\n- Previous")

        assert "### Added" in prompt
        assert "- Previous" in prompt


@pytest.mark.cli
class TestCommitDryRun:
    """Tests for commit command dry run mode."""

    def test_dry_run_shows_info(self, runner: CliRunner, initialized_weld: Path) -> None:
        """Dry run should show info without making changes."""
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        result = runner.invoke(app, ["--dry-run", "commit"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "Stage all: False" in result.stdout
        assert "Auto-split: True" in result.stdout

    def test_dry_run_shows_auto_split_disabled(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """Dry run should show auto-split: False when --no-split is used."""
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        result = runner.invoke(app, ["--dry-run", "commit", "--no-split"])

        assert result.exit_code == 0
        assert "Auto-split: False" in result.stdout

    def test_dry_run_shows_transcript_info(self, runner: CliRunner, initialized_weld: Path) -> None:
        """Dry run should mention transcript upload."""
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        result = runner.invoke(app, ["--dry-run", "commit"])

        assert "transcript gist" in result.stdout.lower()

    def test_dry_run_with_skip_transcript(self, runner: CliRunner, initialized_weld: Path) -> None:
        """Dry run with --skip-transcript should not mention transcript."""
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        result = runner.invoke(app, ["--dry-run", "commit", "--skip-transcript"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        # Should not mention transcript upload
        assert "transcript gist" not in result.stdout.lower()


@pytest.mark.cli
class TestCommitNoSplit:
    """Tests for commit --no-split flag."""

    def _multi_commit_response(self) -> str:
        """Return mock Claude response with multiple commits."""
        return MULTI_COMMIT_RESPONSE

    def test_no_split_merges_multiple_commits(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """--no-split should merge multiple commit groups into one."""
        # Create files that would match the mock response
        (initialized_weld / "src").mkdir()
        (initialized_weld / "src" / "feature.py").write_text("# feature")
        (initialized_weld / "tests").mkdir()
        (initialized_weld / "tests" / "test_feature.py").write_text("# test")
        (initialized_weld / "docs").mkdir()
        (initialized_weld / "docs" / "README.md").write_text("# docs")
        subprocess.run(["git", "add", "."], cwd=initialized_weld, check=True)

        with patch("weld.commands.commit.run_claude", return_value=self._multi_commit_response()):
            result = runner.invoke(
                app, ["commit", "--no-split", "--skip-transcript", "--skip-changelog"]
            )

        assert result.exit_code == 0
        assert "Merged into single commit" in result.stdout
        assert "Created 1 commit(s)" in result.stdout

    def test_no_split_uses_first_message(self, runner: CliRunner, initialized_weld: Path) -> None:
        """--no-split should use the first commit's message."""
        (initialized_weld / "src").mkdir()
        (initialized_weld / "src" / "feature.py").write_text("# feature")
        (initialized_weld / "tests").mkdir()
        (initialized_weld / "tests" / "test_feature.py").write_text("# test")
        (initialized_weld / "docs").mkdir()
        (initialized_weld / "docs" / "README.md").write_text("# docs")
        subprocess.run(["git", "add", "."], cwd=initialized_weld, check=True)

        with patch("weld.commands.commit.run_claude", return_value=self._multi_commit_response()):
            result = runner.invoke(
                app, ["commit", "--no-split", "--skip-transcript", "--skip-changelog"]
            )

        assert result.exit_code == 0

        # Check git log for the message
        log_result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=initialized_weld,
            capture_output=True,
            text=True,
        )
        assert "Add feature implementation" in log_result.stdout


@pytest.mark.cli
class TestCommitEditFlag:
    """Tests for commit --edit flag."""

    def _single_commit_response(self) -> str:
        """Return mock Claude response with single commit."""
        return """<commit>
<files>
test.txt
</files>
<commit_message>
Initial commit message
</commit_message>
<changelog_entry>
</changelog_entry>
</commit>"""

    def test_edit_opens_editor(self, runner: CliRunner, initialized_weld: Path) -> None:
        """--edit should open the editor for commit message."""
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        # Mock only the editor subprocess call by checking args
        original_run = subprocess.run

        def mock_editor_only(args, *a, **kw):
            # Only intercept editor calls (vi, vim, nano, etc.)
            editors = ("vi", "vim", "nano", "emacs", "code")
            if isinstance(args, list) and args and args[0] in editors:
                result = MagicMock()
                result.returncode = 0
                return result
            # Pass through all other subprocess calls (git, etc.)
            return original_run(args, *a, **kw)

        with (
            patch("weld.commands.commit.run_claude", return_value=self._single_commit_response()),
            patch("weld.commands.commit.subprocess.run", mock_editor_only),
        ):
            result = runner.invoke(
                app, ["commit", "--edit", "--skip-transcript", "--skip-changelog"]
            )

        assert result.exit_code == 0
        assert "Committed:" in result.stdout

    def test_edit_editor_failure_exits(self, runner: CliRunner, initialized_weld: Path) -> None:
        """--edit should exit if editor returns non-zero."""
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        original_run = subprocess.run

        def mock_editor_fail(args, *a, **kw):
            editors = ("vi", "vim", "nano", "emacs", "code")
            if isinstance(args, list) and args and args[0] in editors:
                result = MagicMock()
                result.returncode = 1
                return result
            return original_run(args, *a, **kw)

        with (
            patch("weld.commands.commit.run_claude", return_value=self._single_commit_response()),
            patch("weld.commands.commit.subprocess.run", mock_editor_fail),
        ):
            result = runner.invoke(
                app, ["commit", "--edit", "--skip-transcript", "--skip-changelog"]
            )

        assert result.exit_code == 24
        assert "Editor exited" in result.stdout

    def test_edit_empty_message_exits(self, runner: CliRunner, initialized_weld: Path) -> None:
        """--edit should exit if user clears the commit message."""
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        original_run = subprocess.run

        def mock_editor_clear(args, *a, **kw):
            editors = ("vi", "vim", "nano", "emacs", "code")
            if isinstance(args, list) and args and args[0] in editors:
                # Clear the file content to simulate user deleting message
                if len(args) > 1:
                    edit_path = Path(args[1])
                    edit_path.write_text("")
                result = MagicMock()
                result.returncode = 0
                return result
            return original_run(args, *a, **kw)

        with (
            patch("weld.commands.commit.run_claude", return_value=self._single_commit_response()),
            patch("weld.commands.commit.subprocess.run", mock_editor_clear),
        ):
            result = runner.invoke(
                app, ["commit", "--edit", "--skip-transcript", "--skip-changelog"]
            )

        assert result.exit_code == 24
        assert "empty" in result.stdout.lower()


@pytest.mark.cli
class TestCommitChangelogAlreadyStaged:
    """Tests for commit when CHANGELOG.md is already staged.

    The commit command does `unstage_all()` then `stage_files(group.files)` for each group.
    We mock `is_file_staged` to directly test both branches.
    """

    def _single_commit_response(self) -> str:
        """Return mock Claude response with changelog entry."""
        return """<commit>
<files>
test.txt
</files>
<commit_message>
Add test file
</commit_message>
<changelog_entry>
### Added
- New test file
</changelog_entry>
</commit>"""

    def test_does_not_restage_changelog_when_already_staged(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """Should not run git add on CHANGELOG.md if is_file_staged returns True."""
        # Create CHANGELOG.md
        changelog = initialized_weld / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [Unreleased]\n\n## [1.0.0]\n")
        subprocess.run(["git", "add", "CHANGELOG.md"], cwd=initialized_weld, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add changelog"],
            cwd=initialized_weld,
            check=True,
            capture_output=True,
        )

        # Create and stage test file
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        # Track whether run_git("add", "CHANGELOG.md") was called
        add_changelog_called = False
        from weld.services import git as git_module

        original_run_git = git_module.run_git

        def tracking_run_git(*args, **kwargs):
            nonlocal add_changelog_called
            if args == ("add", "CHANGELOG.md"):
                add_changelog_called = True
            return original_run_git(*args, **kwargs)

        with (
            patch("weld.commands.commit.run_claude", return_value=self._single_commit_response()),
            patch("weld.commands.commit.run_git", side_effect=tracking_run_git),
            # Mock is_file_staged to return True for CHANGELOG.md
            patch("weld.commands.commit.is_file_staged", return_value=True),
        ):
            result = runner.invoke(app, ["commit", "--skip-transcript"])

        assert result.exit_code == 0
        assert "Updated CHANGELOG.md" in result.stdout
        # Should not have called run_git("add", "CHANGELOG.md") since is_file_staged=True
        assert not add_changelog_called

    def test_stages_changelog_when_not_already_staged(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """Should run git add on CHANGELOG.md if is_file_staged returns False."""
        # Create CHANGELOG.md
        changelog = initialized_weld / "CHANGELOG.md"
        changelog.write_text("# Changelog\n\n## [Unreleased]\n\n## [1.0.0]\n")
        subprocess.run(["git", "add", "CHANGELOG.md"], cwd=initialized_weld, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add changelog"],
            cwd=initialized_weld,
            check=True,
            capture_output=True,
        )

        # Create and stage test file
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        # Track whether run_git("add", "CHANGELOG.md") was called
        add_changelog_called = False
        from weld.services import git as git_module

        original_run_git = git_module.run_git

        def tracking_run_git(*args, **kwargs):
            nonlocal add_changelog_called
            if args == ("add", "CHANGELOG.md"):
                add_changelog_called = True
            return original_run_git(*args, **kwargs)

        with (
            patch("weld.commands.commit.run_claude", return_value=self._single_commit_response()),
            patch("weld.commands.commit.run_git", side_effect=tracking_run_git),
            # Mock is_file_staged to return False for CHANGELOG.md
            patch("weld.commands.commit.is_file_staged", return_value=False),
        ):
            result = runner.invoke(app, ["commit", "--skip-transcript"])

        assert result.exit_code == 0
        assert "Updated CHANGELOG.md" in result.stdout
        # Should have called run_git("add", "CHANGELOG.md") since is_file_staged=False
        assert add_changelog_called


@pytest.mark.cli
class TestCommitNoDiffContent:
    """Tests for commit when staged diff is empty."""

    def test_exits_when_staged_diff_empty(self, runner: CliRunner, initialized_weld: Path) -> None:
        """Should exit with code 20 when staged diff returns empty."""
        # Stage a file but mock get_diff to return empty
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        with patch("weld.commands.commit.get_diff", return_value=""):
            result = runner.invoke(app, ["commit"])

        assert result.exit_code == 20
        assert "No diff content" in result.stdout


@pytest.mark.cli
class TestCommitTranscriptGistNoUrl:
    """Tests for commit when transcript gist returns no URL."""

    def _single_commit_response(self) -> str:
        """Return mock Claude response."""
        return """<commit>
<files>
test.txt
</files>
<commit_message>
Test commit
</commit_message>
<changelog_entry>
</changelog_entry>
</commit>"""

    def test_warns_when_gist_url_is_none(self, runner: CliRunner, initialized_weld: Path) -> None:
        """Should show warning when transcript gist URL is None."""
        test_file = initialized_weld / "test.txt"
        test_file.write_text("content")
        subprocess.run(["git", "add", "test.txt"], cwd=initialized_weld, check=True)

        with (
            patch("weld.commands.commit.run_claude", return_value=self._single_commit_response()),
            patch("weld.commands.commit.run_transcript_gist") as mock_transcript,
        ):
            from weld.services.transcripts import TranscriptResult

            mock_transcript.return_value = TranscriptResult(gist_url=None, raw_output="")
            result = runner.invoke(app, ["commit", "--skip-changelog"])

        assert result.exit_code == 0
        assert "Could not get transcript gist URL" in result.stdout
        assert "Committed:" in result.stdout


@pytest.mark.unit
class TestCommitGroup:
    """Tests for CommitGroup class."""

    def test_creates_commit_group(self) -> None:
        """Should create CommitGroup with all fields."""
        group = CommitGroup(
            message="Test message",
            files=["file1.py", "file2.py"],
            changelog_entry="### Added\n- Test",
        )

        assert group.message == "Test message"
        assert group.files == ["file1.py", "file2.py"]
        assert group.changelog_entry == "### Added\n- Test"

    def test_default_changelog_entry(self) -> None:
        """Should default changelog_entry to empty string."""
        group = CommitGroup(message="Test", files=["file.py"])

        assert group.changelog_entry == ""
