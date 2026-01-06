"""Tests for document review engine."""

import pytest

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
