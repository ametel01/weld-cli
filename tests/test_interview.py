"""Tests for interview workflow functionality."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from weld.cli import app
from weld.core.interview_engine import (
    generate_interview_prompt,
    run_interview_loop,
)

runner = CliRunner(
    env={
        "NO_COLOR": "1",
        "TERM": "dumb",
        "COLUMNS": "200",
    },
)


@pytest.mark.unit
class TestGenerateInterviewPrompt:
    """Tests for generate_interview_prompt function."""

    def test_includes_document_content(self, tmp_path: Path) -> None:
        """Prompt includes the document content."""
        doc_path = tmp_path / "spec.md"
        content = "# Feature Spec\n\nImplement user login."
        prompt = generate_interview_prompt(doc_path, content)
        assert "# Feature Spec" in prompt
        assert "Implement user login" in prompt

    def test_includes_document_path(self, tmp_path: Path) -> None:
        """Prompt includes the document path for rewriting."""
        doc_path = tmp_path / "spec.md"
        prompt = generate_interview_prompt(doc_path, "test content")
        assert str(doc_path) in prompt

    def test_includes_rules(self, tmp_path: Path) -> None:
        """Prompt includes interview rules."""
        doc_path = tmp_path / "spec.md"
        prompt = generate_interview_prompt(doc_path, "test content")
        assert "AskUserQuestion tool" in prompt
        assert "ONE question at a time" in prompt

    def test_includes_rewrite_instruction(self, tmp_path: Path) -> None:
        """Prompt instructs AI to rewrite the document when complete."""
        doc_path = tmp_path / "spec.md"
        prompt = generate_interview_prompt(doc_path, "test content")
        assert "rewrite" in prompt.lower()
        assert str(doc_path) in prompt

    def test_default_focus(self, tmp_path: Path) -> None:
        """Uses default focus when none specified."""
        doc_path = tmp_path / "spec.md"
        prompt = generate_interview_prompt(doc_path, "test content")
        assert "No specific focus" in prompt

    def test_custom_focus(self, tmp_path: Path) -> None:
        """Uses custom focus when specified."""
        doc_path = tmp_path / "spec.md"
        prompt = generate_interview_prompt(doc_path, "test content", focus="security")
        assert "security" in prompt
        assert "No specific focus" not in prompt

    def test_document_in_current_document_section(self, tmp_path: Path) -> None:
        """Document content appears in Current Document section."""
        doc_path = tmp_path / "spec.md"
        content = "# My Doc\nDetails here."
        prompt = generate_interview_prompt(doc_path, content)
        assert "## Current Document" in prompt
        doc_index = prompt.index("## Current Document")
        content_index = prompt.index("# My Doc")
        assert content_index > doc_index

    def test_focus_in_focus_area_section(self, tmp_path: Path) -> None:
        """Focus appears in Focus Area section."""
        doc_path = tmp_path / "spec.md"
        prompt = generate_interview_prompt(doc_path, "doc", focus="API design")
        assert "## Focus Area" in prompt
        focus_index = prompt.index("## Focus Area")
        api_index = prompt.index("API design")
        assert api_index > focus_index

    def test_includes_interview_scope(self, tmp_path: Path) -> None:
        """Prompt includes comprehensive interview scope."""
        doc_path = tmp_path / "spec.md"
        prompt = generate_interview_prompt(doc_path, "test content")
        assert "Technical implementation" in prompt
        assert "UI & UX" in prompt
        assert "Tradeoffs" in prompt
        assert "Security" in prompt


@pytest.mark.unit
class TestRunInterviewLoop:
    """Tests for run_interview_loop function."""

    def test_dry_run_returns_false(self, tmp_path: Path) -> None:
        """Dry run mode returns False without printing prompt."""
        doc = tmp_path / "spec.md"
        doc.write_text("# Original")

        console = Console(force_terminal=True, width=80, record=True)
        result = run_interview_loop(doc, dry_run=True, console=console)

        assert result is False
        output = console.export_text()
        assert "DRY RUN" in output

    def test_prints_prompt(self, tmp_path: Path) -> None:
        """Prints the interview prompt."""
        doc = tmp_path / "spec.md"
        doc.write_text("# My Spec\n\nDetails here.")

        console = Console(force_terminal=True, width=80, record=True)
        result = run_interview_loop(doc, console=console)

        assert result is True
        output = console.export_text()
        assert "# My Spec" in output
        assert "AskUserQuestion tool" in output

    def test_includes_focus_in_output(self, tmp_path: Path) -> None:
        """Focus parameter is included in printed prompt."""
        doc = tmp_path / "spec.md"
        doc.write_text("# Spec")

        console = Console(force_terminal=True, width=80, record=True)
        run_interview_loop(doc, focus="security requirements", console=console)

        output = console.export_text()
        assert "security requirements" in output

    def test_includes_document_path_for_rewrite(self, tmp_path: Path) -> None:
        """Prompt includes document path for AI to rewrite."""
        doc = tmp_path / "spec.md"
        doc.write_text("# Spec")

        console = Console(force_terminal=True, width=80, record=True)
        run_interview_loop(doc, console=console)

        output = console.export_text()
        assert str(doc) in output
        assert "rewrite" in output.lower()


@pytest.mark.cli
class TestInterviewCommand:
    """Tests for interview CLI command."""

    def test_interview_help(self) -> None:
        """Shows help text with options."""
        result = runner.invoke(app, ["interview", "--help"])
        assert result.exit_code == 0
        assert "file" in result.output.lower()
        assert "--focus" in result.output
        assert "--track" in result.output

    def test_interview_file_not_found(self, tmp_path: Path) -> None:
        """Fails with exit code 1 when file not found."""
        result = runner.invoke(app, ["interview", str(tmp_path / "nonexistent.md")])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_interview_non_markdown_error(self, tmp_path: Path) -> None:
        """Fails early for non-markdown files with helpful hint."""
        txt_file = tmp_path / "spec.txt"
        txt_file.write_text("Some content")

        result = runner.invoke(app, ["interview", str(txt_file)])

        # Should fail with helpful error message
        assert result.exit_code == 1
        assert "markdown" in result.output.lower()
        assert ".md" in result.output

    def test_interview_prints_prompt(self, tmp_path: Path) -> None:
        """Prints interview prompt for markdown file."""
        spec = tmp_path / "spec.md"
        spec.write_text("# Feature Spec\n\nImplement login.")

        result = runner.invoke(app, ["interview", str(spec)])

        assert result.exit_code == 0
        assert "# Feature Spec" in result.output
        assert "AskUserQuestion tool" in result.output

    def test_interview_with_focus(self, tmp_path: Path) -> None:
        """Focus parameter appears in output."""
        spec = tmp_path / "spec.md"
        spec.write_text("# API Spec")

        result = runner.invoke(app, ["interview", str(spec), "--focus", "error handling"])

        assert result.exit_code == 0
        assert "error handling" in result.output

    def test_interview_dry_run(self, tmp_path: Path) -> None:
        """Dry run shows what would happen."""
        spec = tmp_path / "spec.md"
        spec.write_text("# Spec")

        result = runner.invoke(app, ["--dry-run", "interview", str(spec)])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    @patch("weld.commands.interview.get_repo_root")
    def test_interview_outside_git_repo(
        self,
        mock_repo_root: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Works outside git repo without tracking."""
        from weld.services import GitError

        mock_repo_root.side_effect = GitError("Not a git repo")

        spec = tmp_path / "spec.md"
        spec.write_text("# Spec")

        result = runner.invoke(app, ["interview", str(spec)])

        # Should still work (tracking disabled)
        assert result.exit_code == 0
        assert "# Spec" in result.output

    @patch("weld.commands.interview.run_interview_loop")
    def test_interview_modified_shows_message(
        self,
        mock_loop: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Shows 'Document updated' when modified."""
        mock_loop.return_value = True

        spec = tmp_path / "spec.md"
        spec.write_text("# Spec")

        result = runner.invoke(app, ["interview", str(spec)])

        assert result.exit_code == 0
        assert "document updated" in result.output.lower()

    @patch("weld.commands.interview.run_interview_loop")
    def test_interview_not_modified_shows_message(
        self,
        mock_loop: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Shows 'No changes made' when not modified."""
        mock_loop.return_value = False

        spec = tmp_path / "spec.md"
        spec.write_text("# Spec")

        result = runner.invoke(app, ["interview", str(spec)])

        assert result.exit_code == 0
        assert "no changes" in result.output.lower()

    @patch("weld.commands.interview.run_interview_loop")
    def test_interview_keyboard_interrupt(
        self,
        mock_loop: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Handles KeyboardInterrupt gracefully."""
        mock_loop.side_effect = KeyboardInterrupt()

        spec = tmp_path / "spec.md"
        spec.write_text("# Spec")

        result = runner.invoke(app, ["interview", str(spec)])

        assert result.exit_code == 0
        assert "cancelled" in result.output.lower()

    @patch("weld.commands.interview.track_session_activity")
    @patch("weld.commands.interview.run_interview_loop")
    def test_interview_with_track_flag(
        self,
        mock_loop: MagicMock,
        mock_track: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """--track flag enables session tracking."""
        mock_loop.return_value = True
        # Mock the context manager
        mock_track.return_value.__enter__ = MagicMock()
        mock_track.return_value.__exit__ = MagicMock(return_value=False)

        spec = initialized_weld / "spec.md"
        spec.write_text("# Spec")

        result = runner.invoke(app, ["interview", str(spec), "--track"])

        assert result.exit_code == 0
        mock_track.assert_called_once()

    @patch("weld.commands.interview.run_interview_loop")
    def test_interview_without_track_flag(
        self,
        mock_loop: MagicMock,
        initialized_weld: Path,
    ) -> None:
        """Without --track flag, no session tracking."""
        mock_loop.return_value = True

        spec = initialized_weld / "spec.md"
        spec.write_text("# Spec")

        result = runner.invoke(app, ["interview", str(spec)])

        assert result.exit_code == 0
        # run_interview_loop should be called directly, not inside tracking context

    @patch("weld.commands.interview.get_repo_root")
    @patch("weld.commands.interview.run_interview_loop")
    def test_interview_track_outside_git(
        self,
        mock_loop: MagicMock,
        mock_repo_root: MagicMock,
        tmp_path: Path,
    ) -> None:
        """--track flag is ignored when not in git repo."""
        from weld.services import GitError

        mock_repo_root.side_effect = GitError("Not a git repo")
        mock_loop.return_value = True

        spec = tmp_path / "spec.md"
        spec.write_text("# Spec")

        # Should not fail even with --track
        result = runner.invoke(app, ["interview", str(spec), "--track"])

        assert result.exit_code == 0

    @patch("weld.commands.interview.run_interview_loop")
    def test_interview_track_without_weld_dir(
        self,
        mock_loop: MagicMock,
        temp_git_repo: Path,
    ) -> None:
        """--track flag is ignored when .weld/ doesn't exist."""
        mock_loop.return_value = True

        spec = temp_git_repo / "spec.md"
        spec.write_text("# Spec")

        # Should not fail - tracking skipped when no .weld dir
        result = runner.invoke(app, ["interview", str(spec), "--track"])

        assert result.exit_code == 0
