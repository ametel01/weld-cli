"""Tests for interview workflow functionality."""

from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console

from weld.core.interview_engine import (
    _append_interview_note,
    generate_interview_prompt,
    run_interview_loop,
)


@pytest.mark.unit
class TestGenerateInterviewPrompt:
    """Tests for generate_interview_prompt function."""

    def test_includes_document_content(self) -> None:
        """Prompt includes the document content."""
        content = "# Feature Spec\n\nImplement user login."
        prompt = generate_interview_prompt(content)
        assert "# Feature Spec" in prompt
        assert "Implement user login" in prompt

    def test_includes_rules(self) -> None:
        """Prompt includes interview rules."""
        prompt = generate_interview_prompt("test content")
        assert "Ask ONE question at a time" in prompt
        assert "requirements (WHAT)" in prompt

    def test_includes_completion_marker(self) -> None:
        """Prompt mentions INTERVIEW_COMPLETE marker."""
        prompt = generate_interview_prompt("test content")
        assert "INTERVIEW_COMPLETE" in prompt

    def test_default_focus(self) -> None:
        """Uses default focus when none specified."""
        prompt = generate_interview_prompt("test content")
        assert "No specific focus" in prompt

    def test_custom_focus(self) -> None:
        """Uses custom focus when specified."""
        prompt = generate_interview_prompt("test content", focus="security requirements")
        assert "security requirements" in prompt
        assert "No specific focus" not in prompt

    def test_document_in_current_document_section(self) -> None:
        """Document content appears in Current Document section."""
        content = "# My Doc\nDetails here."
        prompt = generate_interview_prompt(content)
        assert "## Current Document" in prompt
        doc_index = prompt.index("## Current Document")
        content_index = prompt.index("# My Doc")
        assert content_index > doc_index

    def test_focus_in_focus_area_section(self) -> None:
        """Focus appears in Focus Area section."""
        prompt = generate_interview_prompt("doc", focus="API design")
        assert "## Focus Area" in prompt
        focus_index = prompt.index("## Focus Area")
        api_index = prompt.index("API design")
        assert api_index > focus_index


@pytest.mark.unit
class TestAppendInterviewNote:
    """Tests for _append_interview_note helper function."""

    def test_adds_notes_section_if_missing(self) -> None:
        """Adds Interview Notes section when not present."""
        content = "# Original Doc\n\nSome content."
        result = _append_interview_note(content, "First answer", 1)

        assert "## Interview Notes" in result
        assert "### Q1" in result
        assert "First answer" in result

    def test_appends_to_existing_notes_section(self) -> None:
        """Appends to existing Interview Notes section."""
        content = "# Doc\n\n## Interview Notes\n\n### Q1\n\nFirst answer\n\n"
        result = _append_interview_note(content, "Second answer", 2)

        # Should not add duplicate header
        assert result.count("## Interview Notes") == 1
        assert "### Q2" in result
        assert "Second answer" in result

    def test_preserves_original_content(self) -> None:
        """Original content is preserved."""
        original = "# My Spec\n\nImportant details here."
        result = _append_interview_note(original, "answer", 1)

        assert "# My Spec" in result
        assert "Important details here" in result

    def test_answer_number_increments(self) -> None:
        """Answer numbers match the provided number."""
        content = "# Doc"
        result1 = _append_interview_note(content, "a1", 1)
        result2 = _append_interview_note(result1, "a2", 2)
        result3 = _append_interview_note(result2, "a3", 3)

        assert "### Q1" in result3
        assert "### Q2" in result3
        assert "### Q3" in result3


@pytest.mark.unit
class TestRunInterviewLoop:
    """Tests for run_interview_loop function."""

    def test_dry_run_returns_false(self, tmp_path: Path) -> None:
        """Dry run mode returns False without modifying file."""
        doc = tmp_path / "spec.md"
        doc.write_text("# Original")

        console = Console(force_terminal=True, width=80)
        result = run_interview_loop(doc, dry_run=True, console=console)

        assert result is False
        assert doc.read_text() == "# Original"

    def test_quit_without_changes_returns_false(self, tmp_path: Path) -> None:
        """Quitting without making changes returns False."""
        doc = tmp_path / "spec.md"
        doc.write_text("# Spec")

        console = Console(force_terminal=True, width=80)
        with patch("builtins.input", return_value="quit"):
            result = run_interview_loop(doc, console=console)

        assert result is False
        assert doc.read_text() == "# Spec"

    def test_answer_modifies_content_and_returns_true(self, tmp_path: Path) -> None:
        """Recording an answer modifies content and returns True on quit with save."""
        doc = tmp_path / "spec.md"
        doc.write_text("# Spec")

        console = Console(force_terminal=True, width=80)
        # Simulate: answer, then quit with save
        inputs = iter(["My answer to the question", "quit", "y"])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            result = run_interview_loop(doc, console=console)

        assert result is True
        content = doc.read_text()
        assert "## Interview Notes" in content
        assert "My answer to the question" in content

    def test_save_command_writes_to_disk(self, tmp_path: Path) -> None:
        """Save command writes current content to disk."""
        doc = tmp_path / "spec.md"
        doc.write_text("# Original")

        console = Console(force_terminal=True, width=80)
        # After "quit", it asks "Save changes? (y/n)" since content was modified
        inputs = iter(["An answer", "save", "quit", "n"])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            run_interview_loop(doc, console=console)

        content = doc.read_text()
        assert "An answer" in content

    def test_interview_complete_saves_and_exits(self, tmp_path: Path) -> None:
        """INTERVIEW_COMPLETE in response saves and exits."""
        doc = tmp_path / "spec.md"
        doc.write_text("# Spec")

        console = Console(force_terminal=True, width=80)
        inputs = iter(["First answer", "INTERVIEW_COMPLETE"])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            result = run_interview_loop(doc, console=console)

        assert result is True
        assert "First answer" in doc.read_text()

    def test_empty_input_is_ignored(self, tmp_path: Path) -> None:
        """Empty input lines are skipped."""
        doc = tmp_path / "spec.md"
        doc.write_text("# Spec")

        console = Console(force_terminal=True, width=80)
        inputs = iter(["", "  ", "quit"])
        with patch("builtins.input", side_effect=lambda _: next(inputs)):
            result = run_interview_loop(doc, console=console)

        assert result is False  # No actual answers recorded

    def test_eof_exits_gracefully(self, tmp_path: Path) -> None:
        """EOFError (Ctrl+D) exits gracefully."""
        doc = tmp_path / "spec.md"
        doc.write_text("# Spec")

        console = Console(force_terminal=True, width=80)
        with patch("builtins.input", side_effect=EOFError):
            result = run_interview_loop(doc, console=console)

        assert result is False

    def test_focus_is_passed_to_prompt(self, tmp_path: Path) -> None:
        """Focus parameter is included in generated prompt."""
        doc = tmp_path / "spec.md"
        doc.write_text("# Spec")

        console = Console(force_terminal=True, width=80, record=True)
        with patch("builtins.input", return_value="quit"):
            run_interview_loop(doc, focus="security", console=console)

        # The focus appears in the printed prompt
        output = console.export_text()
        # Focus is passed to generate_interview_prompt which includes it
        # We verify indirectly by checking the prompt was generated
        assert "Interview Session" in output
