"""Tests for artifact versioning functionality."""

from pathlib import Path

import pytest

from weld.core.artifact_versioning import (
    create_version_snapshot,
    get_current_version,
    get_version_history,
    restore_version,
    update_run_meta_version,
)
from weld.models import MAX_VERSIONS, Meta


@pytest.fixture
def artifact_dir(tmp_path: Path) -> Path:
    """Create a temporary artifact directory."""
    d = tmp_path / "research"
    d.mkdir()
    return d


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """Create a temporary run directory with meta.json."""
    from datetime import datetime

    d = tmp_path / "run"
    d.mkdir()
    meta = Meta(
        run_id="test-run",
        created_at=datetime(2024, 1, 1, 0, 0, 0),
        repo_root=tmp_path,
        branch="main",
        head_sha="abc123",
        config_hash="hash123",
    )
    (d / "meta.json").write_text(meta.model_dump_json(indent=2))
    return d


class TestGetCurrentVersion:
    """Tests for get_current_version function."""

    @pytest.mark.unit
    def test_returns_0_when_no_history(self, artifact_dir: Path) -> None:
        """Returns 0 when no history directory exists."""
        assert get_current_version(artifact_dir) == 0

    @pytest.mark.unit
    def test_returns_highest_version(self, artifact_dir: Path) -> None:
        """Returns the highest version number from history."""
        history = artifact_dir / "history"
        (history / "v1").mkdir(parents=True)
        (history / "v3").mkdir()
        (history / "v2").mkdir()
        assert get_current_version(artifact_dir) == 3

    @pytest.mark.unit
    def test_ignores_non_version_directories(self, artifact_dir: Path) -> None:
        """Ignores directories that don't match vN pattern."""
        history = artifact_dir / "history"
        (history / "v1").mkdir(parents=True)
        (history / "temp").mkdir()
        (history / "backup").mkdir()
        assert get_current_version(artifact_dir) == 1

    @pytest.mark.unit
    def test_returns_0_when_history_empty(self, artifact_dir: Path) -> None:
        """Returns 0 when history directory exists but is empty."""
        history = artifact_dir / "history"
        history.mkdir()
        assert get_current_version(artifact_dir) == 0


class TestCreateVersionSnapshot:
    """Tests for create_version_snapshot function."""

    @pytest.mark.unit
    def test_creates_version_directory(self, artifact_dir: Path) -> None:
        """Creates history/v1 directory with content and meta on first snapshot."""
        (artifact_dir / "research.md").write_text("# Research v1")

        version = create_version_snapshot(
            artifact_dir,
            "research.md",
            trigger_reason="import",
        )

        assert version == 1  # First snapshot is v1
        assert (artifact_dir / "history" / "v1" / "content.md").exists()
        assert (artifact_dir / "history" / "v1" / "meta.json").exists()

    @pytest.mark.unit
    def test_returns_0_when_no_content(self, artifact_dir: Path) -> None:
        """Returns 0 when content file doesn't exist."""
        version = create_version_snapshot(
            artifact_dir,
            "research.md",
            trigger_reason="import",
        )
        assert version == 0

    @pytest.mark.unit
    def test_preserves_content(self, artifact_dir: Path) -> None:
        """Preserves the original content in the version snapshot."""
        original_content = "# Original Research\n\nThis is the original."
        (artifact_dir / "research.md").write_text(original_content)

        create_version_snapshot(artifact_dir, "research.md", "import")

        versioned_content = (artifact_dir / "history" / "v1" / "content.md").read_text()
        assert versioned_content == original_content

    @pytest.mark.unit
    def test_writes_version_metadata(self, artifact_dir: Path) -> None:
        """Writes correct version metadata to meta.json."""
        (artifact_dir / "research.md").write_text("content")

        create_version_snapshot(
            artifact_dir,
            "research.md",
            trigger_reason="import",
            review_id="review-123",
        )

        meta_path = artifact_dir / "history" / "v1" / "meta.json"
        from weld.models import VersionInfo

        info = VersionInfo.model_validate_json(meta_path.read_text())
        assert info.version == 1
        assert info.trigger_reason == "import"
        assert info.review_id == "review-123"

    @pytest.mark.unit
    def test_prunes_old_versions(self, artifact_dir: Path) -> None:
        """Keeps only MAX_VERSIONS versions."""
        (artifact_dir / "research.md").write_text("content")

        # Create MAX_VERSIONS + 2 versions
        for i in range(MAX_VERSIONS + 2):
            create_version_snapshot(artifact_dir, "research.md", f"version {i}")

        history = artifact_dir / "history"
        versions = list(history.iterdir())
        assert len(versions) == MAX_VERSIONS

    @pytest.mark.unit
    def test_keeps_newest_versions_when_pruning(self, artifact_dir: Path) -> None:
        """Prunes oldest versions, keeps newest."""
        (artifact_dir / "research.md").write_text("content")

        # Create MAX_VERSIONS + 3 versions (creates v1 through v8)
        for _ in range(MAX_VERSIONS + 3):
            create_version_snapshot(artifact_dir, "research.md", "version")

        history = artifact_dir / "history"
        version_nums = sorted(int(d.name[1:]) for d in history.iterdir())

        # Should have versions 4-8 (newest 5 versions)
        total_created = MAX_VERSIONS + 3  # 8 versions (v1-v8)
        expected_versions = list(range(total_created - MAX_VERSIONS + 1, total_created + 1))
        assert version_nums == expected_versions

    @pytest.mark.unit
    def test_supersedes_previous_version(self, artifact_dir: Path) -> None:
        """Marks previous version as superseded when creating new snapshot."""
        (artifact_dir / "research.md").write_text("content")

        create_version_snapshot(artifact_dir, "research.md", "first")
        create_version_snapshot(artifact_dir, "research.md", "second")

        from weld.models import VersionInfo

        v1_meta = artifact_dir / "history" / "v1" / "meta.json"
        v1_info = VersionInfo.model_validate_json(v1_meta.read_text())
        assert v1_info.superseded_at is not None


class TestGetVersionHistory:
    """Tests for get_version_history function."""

    @pytest.mark.unit
    def test_returns_empty_when_no_history(self, artifact_dir: Path) -> None:
        """Returns empty list when no history exists."""
        assert get_version_history(artifact_dir) == []

    @pytest.mark.unit
    def test_returns_versions_newest_first(self, artifact_dir: Path) -> None:
        """Returns versions sorted newest first."""
        (artifact_dir / "research.md").write_text("content")
        create_version_snapshot(artifact_dir, "research.md", "v1")
        create_version_snapshot(artifact_dir, "research.md", "v2")

        history = get_version_history(artifact_dir)
        assert len(history) == 2
        assert history[0].version > history[1].version

    @pytest.mark.unit
    def test_includes_trigger_reason(self, artifact_dir: Path) -> None:
        """Each version includes its trigger reason."""
        (artifact_dir / "research.md").write_text("content")
        create_version_snapshot(artifact_dir, "research.md", "first import")
        create_version_snapshot(artifact_dir, "research.md", "second import")

        history = get_version_history(artifact_dir)
        reasons = [v.trigger_reason for v in history]
        assert "first import" in reasons
        assert "second import" in reasons

    @pytest.mark.unit
    def test_skips_corrupt_meta_json(self, artifact_dir: Path) -> None:
        """Skips versions with corrupt meta.json instead of crashing."""
        (artifact_dir / "research.md").write_text("content")
        create_version_snapshot(artifact_dir, "research.md", "valid")

        # Create a corrupt version
        corrupt_dir = artifact_dir / "history" / "v2"
        corrupt_dir.mkdir()
        (corrupt_dir / "content.md").write_text("content")
        (corrupt_dir / "meta.json").write_text("not valid json {{{")

        # Should not crash, just skip the corrupt entry
        history = get_version_history(artifact_dir)
        assert len(history) == 1
        assert history[0].trigger_reason == "valid"

    @pytest.mark.unit
    def test_skips_invalid_schema(self, artifact_dir: Path) -> None:
        """Skips versions with invalid schema (valid JSON but wrong shape)."""
        (artifact_dir / "research.md").write_text("content")
        create_version_snapshot(artifact_dir, "research.md", "valid")

        # Create a version with invalid schema
        invalid_dir = artifact_dir / "history" / "v2"
        invalid_dir.mkdir()
        (invalid_dir / "content.md").write_text("content")
        (invalid_dir / "meta.json").write_text('{"wrong": "schema"}')

        history = get_version_history(artifact_dir)
        assert len(history) == 1


class TestRestoreVersion:
    """Tests for restore_version function."""

    @pytest.mark.unit
    def test_restores_old_content(self, artifact_dir: Path) -> None:
        """Restoring version copies old content to current."""
        content_file = "research.md"
        (artifact_dir / content_file).write_text("original")
        create_version_snapshot(artifact_dir, content_file, "first")

        (artifact_dir / content_file).write_text("modified")
        create_version_snapshot(artifact_dir, content_file, "second")

        # Restore version 1 (which has "original" content)
        success = restore_version(artifact_dir, 1, content_file)
        assert success
        assert (artifact_dir / content_file).read_text() == "original"

    @pytest.mark.unit
    def test_returns_false_for_missing_version(self, artifact_dir: Path) -> None:
        """Returns False when version doesn't exist."""
        success = restore_version(artifact_dir, 99, "research.md")
        assert success is False

    @pytest.mark.unit
    def test_creates_pre_restore_snapshot(self, artifact_dir: Path) -> None:
        """Creates a snapshot of current state before restoring."""
        content_file = "research.md"
        (artifact_dir / content_file).write_text("original")
        create_version_snapshot(artifact_dir, content_file, "first")

        (artifact_dir / content_file).write_text("modified")
        create_version_snapshot(artifact_dir, content_file, "second")

        (artifact_dir / content_file).write_text("latest")

        # Restore version 1
        restore_version(artifact_dir, 1, content_file)

        # Should have created a new version with "latest" content
        history = get_version_history(artifact_dir)
        # Check one of the versions has pre-restore trigger
        pre_restore_versions = [v for v in history if "pre-restore" in (v.trigger_reason or "")]
        assert len(pre_restore_versions) == 1


class TestUpdateRunMetaVersion:
    """Tests for update_run_meta_version function."""

    @pytest.mark.unit
    def test_updates_research_version(self, run_dir: Path) -> None:
        """Updates research_version field in meta.json."""
        success = update_run_meta_version(run_dir, "research", 3)

        assert success
        meta = Meta.model_validate_json((run_dir / "meta.json").read_text())
        assert meta.research_version == 3

    @pytest.mark.unit
    def test_updates_plan_version(self, run_dir: Path) -> None:
        """Updates plan_version field in meta.json."""
        success = update_run_meta_version(run_dir, "plan", 5)

        assert success
        meta = Meta.model_validate_json((run_dir / "meta.json").read_text())
        assert meta.plan_version == 5

    @pytest.mark.unit
    def test_returns_false_for_missing_meta(self, tmp_path: Path) -> None:
        """Returns False when meta.json doesn't exist."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        success = update_run_meta_version(empty_dir, "research", 1)
        assert success is False

    @pytest.mark.unit
    def test_returns_false_for_unknown_artifact_type(self, run_dir: Path) -> None:
        """Returns False for unknown artifact type."""
        success = update_run_meta_version(run_dir, "unknown", 1)
        assert success is False

    @pytest.mark.unit
    def test_handles_corrupt_meta_json(self, run_dir: Path) -> None:
        """Returns False for corrupt meta.json instead of crashing."""
        (run_dir / "meta.json").write_text("not valid json")

        success = update_run_meta_version(run_dir, "research", 1)
        assert success is False
