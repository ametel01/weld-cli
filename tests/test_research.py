"""Tests for research phase functionality."""

from pathlib import Path

import pytest

from weld.core.research_processor import (
    generate_research_prompt,
    get_research_content,
    import_research,
    write_research_prompt,
)


@pytest.mark.unit
class TestGenerateResearchPrompt:
    """Tests for generate_research_prompt function."""

    def test_includes_spec_content(self) -> None:
        """Prompt includes the specification content."""
        spec = "# My Feature\n\nImplement authentication."
        prompt = generate_research_prompt(spec)
        assert "# My Feature" in prompt
        assert "Implement authentication" in prompt

    def test_includes_research_instructions(self) -> None:
        """Prompt includes research structure guidance."""
        prompt = generate_research_prompt("test spec")
        assert "Architecture Analysis" in prompt
        assert "Risk Assessment" in prompt
        assert "Open Questions" in prompt

    def test_includes_dependency_mapping(self) -> None:
        """Prompt includes dependency mapping section."""
        prompt = generate_research_prompt("test spec")
        assert "Dependency Mapping" in prompt

    def test_spec_content_in_specification_section(self) -> None:
        """Spec content appears in the specification section."""
        spec = "# Feature X\n\nAdd user login."
        prompt = generate_research_prompt(spec)
        # Verify spec appears after the "## Specification" header
        assert "## Specification" in prompt
        spec_index = prompt.index("## Specification")
        assert prompt.index("# Feature X") > spec_index


@pytest.mark.unit
class TestResearchFiles:
    """Tests for research file operations."""

    def test_write_and_read_prompt(self, tmp_path: Path) -> None:
        """Can write and read research prompt."""
        research_dir = tmp_path / "research"
        research_dir.mkdir()

        prompt = "Test research prompt"
        path = write_research_prompt(research_dir, prompt)

        assert path.exists()
        assert path.read_text() == prompt

    def test_write_prompt_path(self, tmp_path: Path) -> None:
        """Prompt is written to prompt.md."""
        research_dir = tmp_path / "research"
        research_dir.mkdir()

        path = write_research_prompt(research_dir, "test")
        assert path.name == "prompt.md"

    def test_import_research(self, tmp_path: Path) -> None:
        """Can import research content."""
        research_dir = tmp_path / "research"
        research_dir.mkdir()

        content = "# Research\n\nFindings here."
        path = import_research(research_dir, content)

        assert path.name == "research.md"
        assert path.read_text() == content

    def test_get_research_content_exists(self, tmp_path: Path) -> None:
        """Returns content when research exists."""
        research_dir = tmp_path / "research"
        research_dir.mkdir()
        (research_dir / "research.md").write_text("findings")

        content = get_research_content(research_dir)
        assert content == "findings"

    def test_get_research_content_missing(self, tmp_path: Path) -> None:
        """Returns None when research doesn't exist."""
        research_dir = tmp_path / "research"
        research_dir.mkdir()

        content = get_research_content(research_dir)
        assert content is None

    def test_get_research_content_empty_dir(self, tmp_path: Path) -> None:
        """Returns None when research directory is empty."""
        research_dir = tmp_path / "research"
        research_dir.mkdir()

        content = get_research_content(research_dir)
        assert content is None

    def test_import_research_overwrites(self, tmp_path: Path) -> None:
        """Importing research overwrites existing content."""
        research_dir = tmp_path / "research"
        research_dir.mkdir()

        # First import
        import_research(research_dir, "first content")
        # Second import
        import_research(research_dir, "second content")

        content = get_research_content(research_dir)
        assert content == "second content"
