"""Tests for document review engine."""

import pytest

from weld.core.doc_review_engine import strip_preamble


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
