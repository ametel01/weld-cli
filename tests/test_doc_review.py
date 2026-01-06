"""Tests for document review engine and CLI command."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from weld.cli import app
from weld.core.doc_review_engine import generate_code_review_prompt, strip_preamble


@pytest.mark.unit
class TestStripPreamble:
    """Tests for strip_preamble function."""

    def test_strips_preamble_before_heading(self) -> None:
        """Preamble before markdown heading is stripped."""
        content = """I'll analyze the document now.
Let me start by exploring.

# My Document Title

Some content here.
"""
        result = strip_preamble(content)
        assert result == "# My Document Title\n\nSome content here.\n"

    def test_strips_preamble_before_frontmatter(self) -> None:
        """Preamble before YAML frontmatter is stripped."""
        content = """Let me correct this document.

---
title: My Document
---

Content here.
"""
        result = strip_preamble(content)
        assert result.startswith("---\ntitle: My Document")

    def test_strips_preamble_before_horizontal_rule(self) -> None:
        """Preamble before horizontal rule is stripped."""
        content = """Some AI thinking here.

***

Document content starts here.
"""
        result = strip_preamble(content)
        assert result.startswith("***")

    def test_preserves_document_starting_with_list(self) -> None:
        """Document starting with list item is preserved."""
        content = """- First item
- Second item
"""
        result = strip_preamble(content)
        assert result == content

    def test_preserves_document_starting_with_numbered_list(self) -> None:
        """Document starting with numbered list is preserved."""
        content = """1. First step
2. Second step
"""
        result = strip_preamble(content)
        assert result == content

    def test_preserves_document_starting_with_blockquote(self) -> None:
        """Document starting with blockquote is preserved."""
        content = """> Important quote
> More content
"""
        result = strip_preamble(content)
        assert result == content

    def test_preserves_document_starting_with_code_block(self) -> None:
        """Document starting with code block is preserved."""
        content = """```python
def hello():
    pass
```
"""
        result = strip_preamble(content)
        assert result == content

    def test_preserves_document_starting_with_image(self) -> None:
        """Document starting with image is preserved."""
        content = """![Alt text](image.png)

Content here.
"""
        result = strip_preamble(content)
        assert result == content

    def test_preserves_document_starting_with_link(self) -> None:
        """Document starting with link is preserved."""
        content = """[Link text](url)

Content here.
"""
        result = strip_preamble(content)
        assert result == content

    def test_returns_as_is_when_no_markdown_patterns(self) -> None:
        """Returns content as-is when no markdown patterns found."""
        content = """This is just plain text.
No markdown here.
"""
        result = strip_preamble(content)
        assert result == content

    def test_handles_empty_string(self) -> None:
        """Empty string is returned as-is."""
        assert strip_preamble("") == ""

    def test_handles_whitespace_only(self) -> None:
        """Whitespace-only string is returned as-is."""
        assert strip_preamble("   \n\n   ") == "   \n\n   "

    def test_preserves_document_starting_with_html(self) -> None:
        """Document starting with HTML tag is preserved."""
        content = """<div>
  Content
</div>
"""
        result = strip_preamble(content)
        assert result == content

    def test_strips_multiple_lines_of_preamble(self) -> None:
        """Multiple lines of preamble are all stripped."""
        content = """I'll analyze the provided technical specification.
Let me start by exploring the codebase systematically.
Now let me verify more specific details from the codebase.
Let me continue gathering more verification data:

# Document Title

Actual content.
"""
        result = strip_preamble(content)
        assert result == "# Document Title\n\nActual content.\n"


@pytest.mark.unit
class TestGenerateCodeReviewPrompt:
    """Tests for generate_code_review_prompt function."""

    def test_includes_diff_content(self) -> None:
        """Prompt includes the diff content."""
        diff = "diff --git a/file.py b/file.py\n+print('hello')"
        prompt = generate_code_review_prompt(diff, apply_mode=False)
        assert "diff --git a/file.py b/file.py" in prompt
        assert "+print('hello')" in prompt

    def test_diff_in_code_block(self) -> None:
        """Diff content is wrapped in a code block."""
        diff = "diff --git a/test.py b/test.py"
        prompt = generate_code_review_prompt(diff, apply_mode=False)
        assert "```diff" in prompt
        assert "```" in prompt

    def test_review_mode_includes_bug_category(self) -> None:
        """Review mode includes bugs category."""
        prompt = generate_code_review_prompt("diff content", apply_mode=False)
        assert "### 1. Bugs" in prompt
        assert "Off-by-one errors" in prompt
        assert "Race conditions" in prompt

    def test_review_mode_includes_security_category(self) -> None:
        """Review mode includes security vulnerabilities category."""
        prompt = generate_code_review_prompt("diff content", apply_mode=False)
        assert "### 2. Security Vulnerabilities" in prompt
        assert "Injection vulnerabilities" in prompt

    def test_review_mode_includes_missing_impl_category(self) -> None:
        """Review mode includes missing implementations category."""
        prompt = generate_code_review_prompt("diff content", apply_mode=False)
        assert "### 3. Missing Implementations" in prompt

    def test_review_mode_includes_test_issues_category(self) -> None:
        """Review mode includes test issues category."""
        prompt = generate_code_review_prompt("diff content", apply_mode=False)
        assert "### 4. Test Issues" in prompt
        assert "don't assert expected behavior" in prompt

    def test_review_mode_includes_improvements_category(self) -> None:
        """Review mode includes improvements category."""
        prompt = generate_code_review_prompt("diff content", apply_mode=False)
        assert "### 5. Improvements" in prompt

    def test_review_mode_includes_output_format(self) -> None:
        """Review mode includes structured output format."""
        prompt = generate_code_review_prompt("diff content", apply_mode=False)
        assert "## Output Format" in prompt
        assert "# Code Review Findings" in prompt
        assert "## Summary" in prompt
        assert "APPROVE / REQUEST_CHANGES / NEEDS_DISCUSSION" in prompt

    def test_review_mode_includes_verdict_options(self) -> None:
        """Review mode includes approval status section."""
        prompt = generate_code_review_prompt("diff content", apply_mode=False)
        assert "## Approval Status" in prompt

    def test_apply_mode_uses_different_template(self) -> None:
        """Apply mode uses fix template instead of review template."""
        prompt = generate_code_review_prompt("diff content", apply_mode=True)
        assert "fix them directly" in prompt
        assert "# Fixes Applied" in prompt
        # Should not have review-specific content
        assert "APPROVE / REQUEST_CHANGES" not in prompt

    def test_apply_mode_includes_fix_instructions(self) -> None:
        """Apply mode includes instructions to fix issues."""
        prompt = generate_code_review_prompt("diff content", apply_mode=True)
        assert "## Instructions" in prompt
        assert "Read the diff carefully" in prompt
        assert "Apply all necessary fixes" in prompt

    def test_apply_mode_includes_fix_guidelines(self) -> None:
        """Apply mode includes fix guidelines."""
        prompt = generate_code_review_prompt("diff content", apply_mode=True)
        assert "## Fix Guidelines" in prompt
        assert "Fix ALL issues found" in prompt
        assert "Preserve existing code style" in prompt

    def test_apply_mode_includes_output_format(self) -> None:
        """Apply mode includes output format for fixes."""
        prompt = generate_code_review_prompt("diff content", apply_mode=True)
        assert "## Output" in prompt
        assert "## Summary" in prompt
        assert "**Files fixed:**" in prompt

    def test_apply_mode_includes_manual_review_section(self) -> None:
        """Apply mode includes section for issues needing manual review."""
        prompt = generate_code_review_prompt("diff content", apply_mode=True)
        assert "## Manual Review Needed" in prompt

    def test_multiline_diff_content(self) -> None:
        """Handles multiline diff content."""
        diff = """diff --git a/src/app.py b/src/app.py
index 1234567..abcdefg 100644
--- a/src/app.py
+++ b/src/app.py
@@ -10,6 +10,7 @@ def main():
     print("starting")
+    print("new line")
     return 0
"""
        prompt = generate_code_review_prompt(diff, apply_mode=False)
        assert "src/app.py" in prompt
        assert '+    print("new line")' in prompt

    def test_empty_diff_content(self) -> None:
        """Handles empty diff content."""
        prompt = generate_code_review_prompt("", apply_mode=False)
        assert "```diff" in prompt
        # Template should still be valid


# =============================================================================
# CLI Command Tests
# =============================================================================


@pytest.mark.cli
class TestReviewCommandNotGitRepo:
    """Tests for review command when not in a git repository."""

    def test_review_diff_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """review --diff should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = runner.invoke(app, ["review", "--diff"])
            assert result.exit_code == 3
            assert "Not a git repository" in result.stdout
        finally:
            os.chdir(original)

    def test_review_document_not_git_repo(self, runner: CliRunner, tmp_path: Path) -> None:
        """review document should fail when not in a git repository."""
        original = os.getcwd()
        os.chdir(tmp_path)
        try:
            doc = tmp_path / "doc.md"
            doc.write_text("# Test Document")
            result = runner.invoke(app, ["review", str(doc)])
            assert result.exit_code == 3
            assert "Not a git repository" in result.stdout
        finally:
            os.chdir(original)


@pytest.mark.cli
class TestReviewCommandNotInitialized:
    """Tests for review command when weld is not initialized."""

    def test_review_diff_not_initialized(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """review --diff should fail when weld is not initialized."""
        # Create a change to review
        test_file = temp_git_repo / "test.py"
        test_file.write_text("print('hello')")

        result = runner.invoke(app, ["review", "--diff"])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()

    def test_review_document_not_initialized(self, runner: CliRunner, temp_git_repo: Path) -> None:
        """review document should fail when weld is not initialized."""
        doc = temp_git_repo / "doc.md"
        doc.write_text("# Test Document")

        result = runner.invoke(app, ["review", str(doc)])
        assert result.exit_code == 1
        assert "not initialized" in result.stdout.lower()


SAMPLE_DIFF = """diff --git a/test.py b/test.py
new file mode 100644
index 0000000..a1b2c3d
--- /dev/null
+++ b/test.py
@@ -0,0 +1 @@
+print('hello')
"""


@pytest.mark.cli
class TestReviewCodeDryRun:
    """Tests for review --diff in dry run mode."""

    def test_code_review_dry_run_shows_info(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review --diff --dry-run should show review info without running Claude."""
        with patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF):
            result = runner.invoke(app, ["--dry-run", "review", "--diff"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "code review" in result.stdout.lower()

    def test_code_review_dry_run_staged(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review --diff --staged --dry-run should show staged changes info."""
        with patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF):
            result = runner.invoke(app, ["--dry-run", "review", "--diff", "--staged"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "staged" in result.stdout.lower()

    def test_code_review_dry_run_apply_mode(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review --diff --apply --dry-run should show apply mode info."""
        with patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF):
            result = runner.invoke(app, ["--dry-run", "review", "--diff", "--apply"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "apply fixes" in result.stdout.lower()

    def test_code_review_dry_run_with_output(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review --diff --dry-run -o should show output path."""
        with patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF):
            result = runner.invoke(app, ["--dry-run", "review", "--diff", "-o", "findings.md"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "findings.md" in result.stdout


@pytest.mark.cli
class TestReviewCodePromptOnly:
    """Tests for review --diff with --prompt-only flag."""

    def test_code_review_prompt_only(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review --diff --prompt-only should generate prompt without running Claude."""
        with (
            patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF),
            patch("weld.commands.doc_review.run_claude") as mock_claude,
        ):
            result = runner.invoke(app, ["review", "--diff", "--prompt-only"])

        assert result.exit_code == 0
        mock_claude.assert_not_called()
        assert "Prompt generated" in result.stdout
        # Verify artifact directory created with prompt.md
        reviews_dir = initialized_weld / ".weld" / "reviews"
        assert reviews_dir.exists()
        review_dirs = list(reviews_dir.iterdir())
        assert len(review_dirs) == 1
        assert (review_dirs[0] / "prompt.md").exists()

    def test_code_review_prompt_only_apply_mode(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review --diff --apply --prompt-only shows fix instructions."""
        with (
            patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF),
            patch("weld.commands.doc_review.run_claude") as mock_claude,
        ):
            result = runner.invoke(app, ["review", "--diff", "--apply", "--prompt-only"])

        assert result.exit_code == 0
        mock_claude.assert_not_called()
        assert "fix issues" in result.stdout.lower()


@pytest.mark.cli
class TestReviewCodeFullRun:
    """Tests for review --diff full execution."""

    def test_code_review_success(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review --diff should run Claude and save findings."""
        mock_response = "# Code Review Findings\n\nNo issues found."
        with (
            patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF),
            patch("weld.commands.doc_review.run_claude", return_value=mock_response),
        ):
            result = runner.invoke(app, ["review", "--diff"])

        assert result.exit_code == 0
        assert "Review complete" in result.stdout

    def test_code_review_with_output_file(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review --diff -o should write findings to output file."""
        output_file = initialized_weld / "findings.md"

        mock_response = "# Code Review Findings\n\nNo issues found."
        with (
            patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF),
            patch("weld.commands.doc_review.run_claude", return_value=mock_response),
        ):
            result = runner.invoke(app, ["review", "--diff", "-o", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()
        assert "Code Review Findings" in output_file.read_text()

    def test_code_review_apply_mode_success(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review --diff --apply should apply fixes."""
        mock_response = "# Fixes Applied\n\nFixed 2 issues."
        with (
            patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF),
            patch("weld.commands.doc_review.run_claude", return_value=mock_response),
        ):
            result = runner.invoke(app, ["review", "--diff", "--apply"])

        assert result.exit_code == 0
        assert "Fixes applied" in result.stdout

    def test_code_review_quiet_mode(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review --diff --quiet should suppress streaming."""
        with (
            patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF),
            patch("weld.commands.doc_review.run_claude", return_value="findings") as mock,
        ):
            result = runner.invoke(app, ["review", "--diff", "--quiet"])

        assert result.exit_code == 0
        call_kwargs = mock.call_args[1]
        assert call_kwargs.get("stream") is False

    def test_code_review_claude_error(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review --diff should handle Claude errors gracefully."""
        from weld.services import ClaudeError

        with (
            patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF),
            patch("weld.commands.doc_review.run_claude", side_effect=ClaudeError("API error")),
        ):
            result = runner.invoke(app, ["review", "--diff"])

        assert result.exit_code == 1
        assert "Claude failed" in result.stdout


@pytest.mark.cli
class TestReviewDocumentDryRun:
    """Tests for document review in dry run mode."""

    def test_doc_review_dry_run_shows_info(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review document --dry-run should show review info."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project\n\nDescription here.")

        result = runner.invoke(app, ["--dry-run", "review", str(doc)])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "document review" in result.stdout.lower()

    def test_doc_review_dry_run_apply_mode(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review document --apply --dry-run should show correction mode."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project\n\nDescription here.")

        result = runner.invoke(app, ["--dry-run", "review", str(doc), "--apply"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "apply corrections" in result.stdout.lower()

    def test_doc_review_dry_run_with_output(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review document --dry-run -o should show output path."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project")

        result = runner.invoke(app, ["--dry-run", "review", str(doc), "-o", "findings.md"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        assert "findings.md" in result.stdout


@pytest.mark.cli
class TestReviewDocumentPromptOnly:
    """Tests for document review with --prompt-only flag."""

    def test_doc_review_prompt_only(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review document --prompt-only should generate prompt without Claude."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project\n\nDescription here.")

        with patch("weld.commands.doc_review.run_claude") as mock_claude:
            result = runner.invoke(app, ["review", str(doc), "--prompt-only"])

        assert result.exit_code == 0
        mock_claude.assert_not_called()
        assert "Prompt generated" in result.stdout
        # Verify artifact directory created with prompt.md
        reviews_dir = initialized_weld / ".weld" / "reviews"
        assert reviews_dir.exists()
        review_dirs = list(reviews_dir.iterdir())
        assert len(review_dirs) == 1
        assert (review_dirs[0] / "prompt.md").exists()

    def test_doc_review_prompt_only_apply_mode(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review document --apply --prompt-only shows correction instructions."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project\n\nDescription here.")

        with patch("weld.commands.doc_review.run_claude") as mock_claude:
            result = runner.invoke(app, ["review", str(doc), "--apply", "--prompt-only"])

        assert result.exit_code == 0
        mock_claude.assert_not_called()
        # Should mention saving corrected document
        assert str(doc) in result.stdout


@pytest.mark.cli
class TestReviewDocumentFullRun:
    """Tests for document review full execution."""

    def test_doc_review_success(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review document should run Claude and save findings."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project\n\nDescription here.")

        mock_response = "# Review Findings\n\n## Summary\nAll good."
        with patch("weld.commands.doc_review.run_claude", return_value=mock_response):
            result = runner.invoke(app, ["review", str(doc)])

        assert result.exit_code == 0
        assert "Review complete" in result.stdout

    def test_doc_review_with_output_file(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review document -o should write findings to output file."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project\n\nDescription here.")
        output_file = initialized_weld / "findings.md"

        mock_response = "# Review Findings\n\n## Summary\nAll good."
        with patch("weld.commands.doc_review.run_claude", return_value=mock_response):
            result = runner.invoke(app, ["review", str(doc), "-o", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()
        assert "Review Findings" in output_file.read_text()

    def test_doc_review_creates_nested_output_dirs(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review document should create parent directories for output."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project")
        output_file = initialized_weld / "output" / "nested" / "findings.md"

        mock_response = "# Review Findings"
        with patch("weld.commands.doc_review.run_claude", return_value=mock_response):
            result = runner.invoke(app, ["review", str(doc), "-o", str(output_file)])

        assert result.exit_code == 0
        assert output_file.exists()

    def test_doc_review_apply_mode_corrects_document(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review document --apply should correct the document in place."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project\n\nOld description.")

        corrected_content = "# Project\n\nCorrected description."
        with patch("weld.commands.doc_review.run_claude", return_value=corrected_content):
            result = runner.invoke(app, ["review", str(doc), "--apply"])

        assert result.exit_code == 0
        assert "corrected" in result.stdout.lower()
        # Verify document was updated
        assert doc.read_text() == corrected_content

    def test_doc_review_apply_mode_saves_original(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review document --apply should save original to artifact dir."""
        doc = initialized_weld / "README.md"
        original_content = "# Project\n\nOriginal content."
        doc.write_text(original_content)

        corrected_content = "# Project\n\nCorrected content."
        with patch("weld.commands.doc_review.run_claude", return_value=corrected_content):
            result = runner.invoke(app, ["review", str(doc), "--apply"])

        assert result.exit_code == 0
        # Find the review artifact directory
        reviews_dir = initialized_weld / ".weld" / "reviews"
        review_dirs = list(reviews_dir.iterdir())
        assert len(review_dirs) == 1
        original_file = review_dirs[0] / "original.md"
        assert original_file.exists()
        assert original_file.read_text() == original_content

    def test_doc_review_strips_preamble(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review document should strip AI preamble from response."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project")
        output_file = initialized_weld / "findings.md"

        # Simulate Claude response with preamble
        mock_response = "I'll review this document.\n\n# Review Findings\n\nAll good."
        with patch("weld.commands.doc_review.run_claude", return_value=mock_response):
            result = runner.invoke(app, ["review", str(doc), "-o", str(output_file)])

        assert result.exit_code == 0
        content = output_file.read_text()
        assert "I'll review" not in content
        assert content.startswith("# Review Findings")

    def test_doc_review_quiet_mode(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review document --quiet should suppress streaming."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project")

        with patch("weld.commands.doc_review.run_claude", return_value="findings") as mock:
            result = runner.invoke(app, ["review", str(doc), "--quiet"])

        assert result.exit_code == 0
        call_kwargs = mock.call_args[1]
        assert call_kwargs.get("stream") is False

    def test_doc_review_claude_error(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review document should handle Claude errors gracefully."""
        from weld.services import ClaudeError

        doc = initialized_weld / "README.md"
        doc.write_text("# Project")

        with patch("weld.commands.doc_review.run_claude", side_effect=ClaudeError("Timeout")):
            result = runner.invoke(app, ["review", str(doc)])

        assert result.exit_code == 1
        assert "Claude failed" in result.stdout

    def test_doc_review_with_timeout(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review document --timeout should pass timeout to Claude."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project")

        with patch("weld.commands.doc_review.run_claude", return_value="findings") as mock:
            result = runner.invoke(app, ["review", str(doc), "--timeout", "300"])

        assert result.exit_code == 0
        call_kwargs = mock.call_args[1]
        assert call_kwargs.get("timeout") == 300


@pytest.mark.cli
class TestReviewCodeArtifacts:
    """Tests for code review artifact creation."""

    def test_code_review_creates_artifact_dir(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review --diff should create artifact directory with prompt and diff."""
        with (
            patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF),
            patch("weld.commands.doc_review.run_claude", return_value="findings"),
        ):
            result = runner.invoke(app, ["review", "--diff"])

        assert result.exit_code == 0
        reviews_dir = initialized_weld / ".weld" / "reviews"
        review_dirs = list(reviews_dir.iterdir())
        assert len(review_dirs) == 1

        # Check artifact files
        artifact_dir = review_dirs[0]
        assert (artifact_dir / "prompt.md").exists()
        assert (artifact_dir / "diff.patch").exists()
        assert (artifact_dir / "findings.md").exists()

    def test_code_review_apply_saves_fixes(self, runner: CliRunner, initialized_weld: Path) -> None:
        """review --diff --apply should save fixes.md instead of findings.md."""
        with (
            patch("weld.commands.doc_review.get_diff", return_value=SAMPLE_DIFF),
            patch("weld.commands.doc_review.run_claude", return_value="# Fixes Applied"),
        ):
            result = runner.invoke(app, ["review", "--diff", "--apply"])

        assert result.exit_code == 0
        reviews_dir = initialized_weld / ".weld" / "reviews"
        review_dirs = list(reviews_dir.iterdir())
        artifact_dir = review_dirs[0]
        assert (artifact_dir / "fixes.md").exists()
        assert not (artifact_dir / "findings.md").exists()


@pytest.mark.cli
class TestReviewDocumentArtifacts:
    """Tests for document review artifact creation."""

    def test_doc_review_creates_artifact_dir(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review document should create artifact directory with prompt."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Project")

        with patch("weld.commands.doc_review.run_claude", return_value="# Findings"):
            result = runner.invoke(app, ["review", str(doc)])

        assert result.exit_code == 0
        reviews_dir = initialized_weld / ".weld" / "reviews"
        review_dirs = list(reviews_dir.iterdir())
        assert len(review_dirs) == 1

        artifact_dir = review_dirs[0]
        assert (artifact_dir / "prompt.md").exists()
        assert (artifact_dir / "findings.md").exists()

    def test_doc_review_apply_saves_corrected(
        self, runner: CliRunner, initialized_weld: Path
    ) -> None:
        """review document --apply should save corrected.md and original.md."""
        doc = initialized_weld / "README.md"
        doc.write_text("# Original")

        with patch("weld.commands.doc_review.run_claude", return_value="# Corrected"):
            result = runner.invoke(app, ["review", str(doc), "--apply"])

        assert result.exit_code == 0
        reviews_dir = initialized_weld / ".weld" / "reviews"
        review_dirs = list(reviews_dir.iterdir())
        artifact_dir = review_dirs[0]
        assert (artifact_dir / "corrected.md").exists()
        assert (artifact_dir / "original.md").exists()
        assert not (artifact_dir / "findings.md").exists()
