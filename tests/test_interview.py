"""Tests for interview workflow functionality.

The interview workflow has two steps:
1. Generate questionnaire: `weld interview spec.md`
2. Apply answers: `weld interview apply questionnaire.md`
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from weld.cli import app
from weld.core.interview_engine import (
    _extract_markdown,
    _extract_source_path,
    apply_questionnaire,
    generate_interview_prompt,
    generate_questionnaire,
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
    """Tests for generate_interview_prompt function (legacy compatibility)."""

    def test_includes_document_content(self, tmp_path: Path) -> None:
        """Prompt includes the document content."""
        doc_path = tmp_path / "spec.md"
        content = "# Feature Spec\n\nImplement user login."
        prompt = generate_interview_prompt(doc_path, content)
        assert "# Feature Spec" in prompt
        assert "Implement user login" in prompt

    def test_includes_document_path(self, tmp_path: Path) -> None:
        """Prompt includes the document path."""
        doc_path = tmp_path / "spec.md"
        prompt = generate_interview_prompt(doc_path, "test content")
        assert str(doc_path) in prompt

    def test_includes_questionnaire_instructions(self, tmp_path: Path) -> None:
        """Prompt includes questionnaire format instructions."""
        doc_path = tmp_path / "spec.md"
        prompt = generate_interview_prompt(doc_path, "test content")
        assert "questionnaire" in prompt.lower()
        assert "[ ]" in prompt  # Checkbox format

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


@pytest.mark.unit
class TestExtractMarkdown:
    """Tests for _extract_markdown helper."""

    def test_plain_text_unchanged(self) -> None:
        """Plain text is returned unchanged."""
        text = "# Heading\n\nContent here."
        assert _extract_markdown(text) == text.strip()

    def test_strips_markdown_fence(self) -> None:
        """Strips ```markdown ... ``` fences."""
        text = "```markdown\n# Heading\n\nContent\n```"
        assert _extract_markdown(text) == "# Heading\n\nContent"

    def test_strips_plain_fence(self) -> None:
        """Strips ``` ... ``` fences."""
        text = "```\n# Heading\n\nContent\n```"
        assert _extract_markdown(text) == "# Heading\n\nContent"


@pytest.mark.unit
class TestExtractSourcePath:
    """Tests for _extract_source_path helper."""

    def test_extracts_absolute_path(self) -> None:
        """Extracts absolute path from questionnaire header."""
        content = """# Interview Questionnaire

**Source:** /home/user/project/spec.md
**Generated:** 2024-01-24

## Q1: Test?
"""
        path = _extract_source_path(content)
        assert path == Path("/home/user/project/spec.md")

    def test_extracts_relative_path(self) -> None:
        """Extracts relative path from questionnaire header."""
        content = "**Source:** ../specs/spec.md\n\n## Q1"
        path = _extract_source_path(content)
        assert path == Path("../specs/spec.md")

    def test_returns_none_if_missing(self) -> None:
        """Returns None if Source header is missing."""
        content = "# Questionnaire\n\n## Q1: Test?"
        assert _extract_source_path(content) is None


@pytest.mark.unit
class TestGenerateQuestionnaire:
    """Tests for generate_questionnaire function."""

    def test_dry_run_returns_none(self, tmp_path: Path) -> None:
        """Dry run mode returns None without invoking Claude."""
        doc = tmp_path / "spec.md"
        doc.write_text("# Original")

        console = Console(force_terminal=True, width=80, record=True)
        result = generate_questionnaire(doc, dry_run=True, console=console)

        assert result is None
        output = console.export_text()
        assert "DRY RUN" in output

    @patch("weld.core.interview_engine.run_claude")
    def test_invokes_claude_and_saves_questionnaire(
        self, mock_claude: MagicMock, tmp_path: Path
    ) -> None:
        """Invokes Claude and saves the generated questionnaire."""
        mock_claude.return_value = """# Interview Questionnaire

**Source:** {doc_path}
**Generated:** 2024-01-24 12:00:00

## Q1: Test Question

- [ ] Option A
- [ ] Option B
"""

        doc = tmp_path / "spec.md"
        doc.write_text("# My Spec")

        output_dir = tmp_path / "interviews"
        console = Console(force_terminal=True, width=80, record=True)

        result = generate_questionnaire(doc, output_dir=output_dir, console=console)

        assert result is not None
        assert result.exists()
        assert "spec-interview-" in result.name
        assert result.suffix == ".md"

        # Check content was written
        content = result.read_text()
        assert "Interview Questionnaire" in content

    @patch("weld.core.interview_engine.run_claude")
    def test_passes_focus_to_prompt(self, mock_claude: MagicMock, tmp_path: Path) -> None:
        """Focus parameter is included in the prompt."""
        mock_claude.return_value = "# Questionnaire"

        doc = tmp_path / "spec.md"
        doc.write_text("# Spec")

        generate_questionnaire(doc, focus="security", output_dir=tmp_path)

        call_kwargs = mock_claude.call_args.kwargs
        prompt = call_kwargs["prompt"]
        assert "security" in prompt


@pytest.mark.unit
class TestApplyQuestionnaire:
    """Tests for apply_questionnaire function."""

    def test_no_answers_selected_returns_false(self, tmp_path: Path) -> None:
        """Returns False and warns if no answers are selected."""
        # Create source spec
        spec = tmp_path / "spec.md"
        spec.write_text("# Original Spec")

        # Create questionnaire without any [x] marks
        questionnaire = tmp_path / "questionnaire.md"
        questionnaire.write_text(f"""# Interview Questionnaire

**Source:** {spec}

## Q1: Test?

- [ ] Option A
- [ ] Option B
""")

        console = Console(force_terminal=True, width=80, record=True)
        result = apply_questionnaire(questionnaire, console=console)

        assert result is False
        output = console.export_text()
        assert "No answers selected" in output

    def test_missing_source_raises_error(self, tmp_path: Path) -> None:
        """Raises ValueError if Source header is missing."""
        questionnaire = tmp_path / "questionnaire.md"
        questionnaire.write_text("# Questionnaire\n\n## Q1")

        with pytest.raises(ValueError) as exc_info:
            apply_questionnaire(questionnaire)

        assert "Could not find source" in str(exc_info.value)

    def test_source_not_found_raises_error(self, tmp_path: Path) -> None:
        """Raises ValueError if source file doesn't exist."""
        questionnaire = tmp_path / "questionnaire.md"
        questionnaire.write_text(f"""**Source:** {tmp_path / "nonexistent.md"}

## Q1

- [x] Option A
""")

        with pytest.raises(ValueError) as exc_info:
            apply_questionnaire(questionnaire)

        assert "not found" in str(exc_info.value)

    @patch("weld.core.interview_engine.run_claude")
    def test_applies_answers_to_spec(self, mock_claude: MagicMock, tmp_path: Path) -> None:
        """Applies answered questionnaire to update spec."""
        # Create source spec
        spec = tmp_path / "spec.md"
        spec.write_text("# Original Spec")

        # Claude returns updated content
        mock_claude.return_value = "# Updated Spec\n\nWith new content."

        # Create questionnaire with answers
        questionnaire = tmp_path / "questionnaire.md"
        questionnaire.write_text(f"""# Interview Questionnaire

**Source:** {spec}

## Q1: Authentication?

- [x] Option A - JWT tokens
- [ ] Option B - Sessions
""")

        console = Console(force_terminal=True, width=80, record=True)
        result = apply_questionnaire(questionnaire, console=console)

        assert result is True
        assert spec.read_text() == "# Updated Spec\n\nWith new content."


@pytest.mark.cli
class TestInterviewCommand:
    """Tests for interview CLI command."""

    def test_interview_help(self) -> None:
        """Shows help text with subcommands."""
        result = runner.invoke(app, ["interview", "--help"])
        assert result.exit_code == 0
        assert "generate" in result.output.lower()
        assert "apply" in result.output.lower()

    def test_interview_generate_help(self) -> None:
        """Shows help for generate subcommand."""
        result = runner.invoke(app, ["interview", "generate", "--help"])
        assert result.exit_code == 0
        assert "questionnaire" in result.output.lower()
        assert "--focus" in result.output

    def test_interview_apply_help(self) -> None:
        """Shows help for apply subcommand."""
        result = runner.invoke(app, ["interview", "apply", "--help"])
        assert result.exit_code == 0
        assert "questionnaire" in result.output.lower()

    def test_generate_file_not_found(self, tmp_path: Path) -> None:
        """Fails with exit code 1 when file not found."""
        result = runner.invoke(app, ["interview", "generate", str(tmp_path / "nonexistent.md")])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_generate_non_markdown_error(self, tmp_path: Path) -> None:
        """Fails early for non-markdown files."""
        txt_file = tmp_path / "spec.txt"
        txt_file.write_text("Some content")

        result = runner.invoke(app, ["interview", "generate", str(txt_file)])

        assert result.exit_code == 1
        assert "markdown" in result.output.lower()

    @patch("weld.commands.interview.generate_questionnaire")
    def test_generate_creates_questionnaire(
        self,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Generate command creates questionnaire."""
        output_path = tmp_path / "questionnaire.md"
        mock_generate.return_value = output_path

        spec = tmp_path / "spec.md"
        spec.write_text("# Spec")

        result = runner.invoke(app, ["interview", "generate", str(spec)])

        assert result.exit_code == 0
        mock_generate.assert_called_once()

    @patch("weld.commands.interview.generate_questionnaire")
    def test_generate_with_focus(
        self,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Focus parameter is passed to generator."""
        mock_generate.return_value = tmp_path / "q.md"

        spec = tmp_path / "spec.md"
        spec.write_text("# Spec")

        result = runner.invoke(app, ["interview", "generate", str(spec), "--focus", "security"])

        assert result.exit_code == 0
        call_kwargs = mock_generate.call_args.kwargs
        assert call_kwargs["focus"] == "security"

    def test_generate_dry_run(self, tmp_path: Path) -> None:
        """Dry run shows what would happen."""
        spec = tmp_path / "spec.md"
        spec.write_text("# Spec")

        result = runner.invoke(app, ["--dry-run", "interview", "generate", str(spec)])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output

    @patch("weld.commands.interview.generate_questionnaire")
    def test_generate_claude_error(
        self,
        mock_generate: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Handles ClaudeError with exit code 21."""
        from weld.services import ClaudeError

        mock_generate.side_effect = ClaudeError("Claude failed")

        spec = tmp_path / "spec.md"
        spec.write_text("# Spec")

        result = runner.invoke(app, ["interview", "generate", str(spec)])

        assert result.exit_code == 21

    @patch("weld.commands.interview.apply_questionnaire")
    def test_apply_updates_spec(
        self,
        mock_apply: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Apply command updates the spec."""
        mock_apply.return_value = True

        questionnaire = tmp_path / "questionnaire.md"
        questionnaire.write_text("# Questionnaire")

        result = runner.invoke(app, ["interview", "apply", str(questionnaire)])

        assert result.exit_code == 0
        assert "updated" in result.output.lower()
        mock_apply.assert_called_once()

    @patch("weld.commands.interview.apply_questionnaire")
    def test_apply_no_changes(
        self,
        mock_apply: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Apply command shows message when no changes made."""
        mock_apply.return_value = False

        questionnaire = tmp_path / "questionnaire.md"
        questionnaire.write_text("# Questionnaire")

        result = runner.invoke(app, ["interview", "apply", str(questionnaire)])

        assert result.exit_code == 0
        assert "no changes" in result.output.lower()

    def test_apply_file_not_found(self, tmp_path: Path) -> None:
        """Apply fails when questionnaire not found."""
        result = runner.invoke(app, ["interview", "apply", str(tmp_path / "nonexistent.md")])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
