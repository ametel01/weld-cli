"""Tests for discover workflow functionality."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from weld.core.discover_engine import generate_discover_prompt, get_discover_dir
from weld.models import DiscoverMeta


@pytest.mark.unit
class TestDiscoverMeta:
    """Tests for DiscoverMeta model."""

    def test_create_discover_meta(self) -> None:
        """Can create DiscoverMeta with required fields."""
        meta = DiscoverMeta(
            discover_id="20260104-120000-discover",
            config_hash="abc123",
            output_path=Path("/tmp/output.md"),
        )
        assert meta.discover_id == "20260104-120000-discover"
        assert meta.config_hash == "abc123"
        assert meta.output_path == Path("/tmp/output.md")
        assert meta.used_by_runs == []
        assert meta.partial is False

    def test_discover_meta_defaults(self) -> None:
        """DiscoverMeta has sensible defaults."""
        meta = DiscoverMeta(
            discover_id="test-discover",
            config_hash="hash",
            output_path=Path("out.md"),
        )
        assert isinstance(meta.created_at, datetime)
        assert meta.used_by_runs == []
        assert meta.partial is False

    def test_discover_meta_serialization(self) -> None:
        """DiscoverMeta can be serialized to JSON."""
        meta = DiscoverMeta(
            discover_id="test-discover",
            config_hash="hash",
            output_path=Path("out.md"),
        )
        json_str = meta.model_dump_json()
        assert "test-discover" in json_str
        assert "hash" in json_str


@pytest.mark.unit
class TestGenerateDiscoverPrompt:
    """Tests for generate_discover_prompt function."""

    def test_includes_architecture_section(self) -> None:
        """Prompt includes system architecture guidance."""
        prompt = generate_discover_prompt()
        assert "System Architecture" in prompt
        assert "High-Level Design" in prompt

    def test_includes_directory_section(self) -> None:
        """Prompt includes codebase structure section."""
        prompt = generate_discover_prompt()
        assert "Codebase Structure" in prompt
        assert "Directory Layout" in prompt

    def test_includes_key_files_section(self) -> None:
        """Prompt includes key files section."""
        prompt = generate_discover_prompt()
        assert "Key Files" in prompt
        assert "file:line references" in prompt

    def test_default_focus_areas(self) -> None:
        """Uses default focus when none specified."""
        prompt = generate_discover_prompt()
        assert "Analyze the entire codebase holistically" in prompt

    def test_custom_focus_areas(self) -> None:
        """Uses custom focus areas when specified."""
        prompt = generate_discover_prompt("Focus on the API layer and authentication.")
        assert "Focus on the API layer and authentication" in prompt
        assert "Analyze the entire codebase holistically" not in prompt


@pytest.mark.unit
class TestGetDiscoverDir:
    """Tests for get_discover_dir function."""

    def test_creates_discover_dir(self, tmp_path: Path) -> None:
        """Creates discover directory if it doesn't exist."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        discover_dir = get_discover_dir(weld_dir)

        assert discover_dir.exists()
        assert discover_dir.is_dir()
        assert discover_dir.name == "discover"

    def test_returns_existing_discover_dir(self, tmp_path: Path) -> None:
        """Returns existing discover directory."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        existing = weld_dir / "discover"
        existing.mkdir()
        (existing / "test.txt").write_text("existing")

        discover_dir = get_discover_dir(weld_dir)

        assert discover_dir == existing
        assert (discover_dir / "test.txt").exists()

    def test_discover_dir_path(self, tmp_path: Path) -> None:
        """Discover dir is at .weld/discover."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        discover_dir = get_discover_dir(weld_dir)

        assert discover_dir == weld_dir / "discover"


@pytest.mark.unit
class TestDiscoverMetaSerialization:
    """Tests for DiscoverMeta JSON round-trip."""

    def test_meta_roundtrip_to_file(self, tmp_path: Path) -> None:
        """DiscoverMeta can be written and read back from file."""
        meta = DiscoverMeta(
            discover_id="20260105-120000-discover",
            config_hash="abc123def456",  # pragma: allowlist secret
            output_path=Path("architecture.md"),
            used_by_runs=["run-1"],
        )

        meta_path = tmp_path / "meta.json"
        meta_path.write_text(meta.model_dump_json(indent=2))

        loaded = json.loads(meta_path.read_text())

        assert loaded["discover_id"] == "20260105-120000-discover"
        assert loaded["config_hash"] == "abc123def456"  # pragma: allowlist secret
        assert loaded["output_path"] == "architecture.md"
        assert loaded["used_by_runs"] == ["run-1"]
        assert loaded["partial"] is False
