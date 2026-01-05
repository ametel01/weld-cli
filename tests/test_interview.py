"""Tests for interview workflow functionality."""

from pathlib import Path

import pytest
from rich.console import Console

from weld.core.interview_engine import (
    generate_interview_prompt,
    run_interview_loop,
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
