"""Tests for research command functionality."""

from pathlib import Path

import pytest

from weld.commands.research import generate_research_prompt, get_research_dir


@pytest.mark.unit
class TestGenerateResearchPrompt:
    """Tests for generate_research_prompt function."""

    def test_includes_spec_content(self) -> None:
        """Prompt includes the specification content."""
        prompt = generate_research_prompt("Implement OAuth2", "spec.md")
        assert "Implement OAuth2" in prompt

    def test_includes_spec_name(self) -> None:
        """Prompt includes specification filename."""
        prompt = generate_research_prompt("content", "auth-feature.md")
        assert "auth-feature.md" in prompt

    def test_includes_research_request_header(self) -> None:
        """Prompt includes Research Request header."""
        prompt = generate_research_prompt("content", "spec.md")
        assert "# Research Request" in prompt

    def test_includes_architecture_analysis(self) -> None:
        """Prompt includes architecture analysis section."""
        prompt = generate_research_prompt("content", "spec.md")
        assert "Architecture Analysis" in prompt
        assert "existing code patterns" in prompt

    def test_includes_dependency_mapping(self) -> None:
        """Prompt includes dependency mapping section."""
        prompt = generate_research_prompt("content", "spec.md")
        assert "Dependency Mapping" in prompt
        assert "External dependencies" in prompt

    def test_includes_risk_assessment(self) -> None:
        """Prompt includes risk assessment section."""
        prompt = generate_research_prompt("content", "spec.md")
        assert "Risk Assessment" in prompt
        assert "mitigation strategies" in prompt

    def test_includes_open_questions(self) -> None:
        """Prompt includes open questions section."""
        prompt = generate_research_prompt("content", "spec.md")
        assert "Open Questions" in prompt
        assert "Ambiguities" in prompt


@pytest.mark.unit
class TestGetResearchDir:
    """Tests for get_research_dir function."""

    def test_creates_research_dir(self, tmp_path: Path) -> None:
        """Creates research directory if it doesn't exist."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        research_dir = get_research_dir(weld_dir)

        assert research_dir.exists()
        assert research_dir.is_dir()
        assert research_dir.name == "research"

    def test_returns_existing_research_dir(self, tmp_path: Path) -> None:
        """Returns existing research directory."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        existing = weld_dir / "research"
        existing.mkdir()
        (existing / "test.txt").write_text("existing")

        research_dir = get_research_dir(weld_dir)

        assert research_dir == existing
        assert (research_dir / "test.txt").exists()

    def test_research_dir_path(self, tmp_path: Path) -> None:
        """Research dir is at .weld/research."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        research_dir = get_research_dir(weld_dir)

        assert research_dir == weld_dir / "research"
