"""Tests for session tracker service."""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from weld.models.session import TrackedSession
from weld.services.session_tracker import (
    SNAPSHOT_EXCLUDES,
    SessionRegistry,
    _should_exclude_path,
    compute_changes,
    get_file_snapshot,
    get_registry,
    track_session_activity,
)


class TestSessionRegistry:
    """Tests for SessionRegistry class."""

    def test_loads_empty_registry(self, tmp_path: Path) -> None:
        """Should handle non-existent registry file."""
        registry_path = tmp_path / "sessions" / "registry.jsonl"
        registry = SessionRegistry(registry_path)
        assert registry.sessions == {}

    def test_saves_and_loads_sessions(self, tmp_path: Path) -> None:
        """Should persist sessions to JSONL and reload."""
        registry_path = tmp_path / "sessions" / "registry.jsonl"
        registry = SessionRegistry(registry_path)

        # Record activity
        registry.record_activity(
            session_id="test-123",
            session_file="/path/to/session.jsonl",
            command="implement",
            files_created=["new.py"],
            files_modified=["existing.py"],
        )

        # Create new registry instance to verify persistence
        registry2 = SessionRegistry(registry_path)
        assert "test-123" in registry2.sessions
        session = registry2.get("test-123")
        assert session is not None
        assert session.session_file == "/path/to/session.jsonl"
        assert len(session.activities) == 1
        assert session.activities[0].command == "implement"

    def test_record_activity_creates_session(self, tmp_path: Path) -> None:
        """Should create new session on first activity."""
        registry = SessionRegistry(tmp_path / "registry.jsonl")

        registry.record_activity(
            session_id="new-session",
            session_file="/path/session.jsonl",
            command="research",
            files_created=["research.md"],
            files_modified=[],
        )

        session = registry.get("new-session")
        assert session is not None
        assert session.session_id == "new-session"
        assert len(session.activities) == 1

    def test_record_activity_appends_to_existing(self, tmp_path: Path) -> None:
        """Should append activity to existing session."""
        registry = SessionRegistry(tmp_path / "registry.jsonl")

        # First activity
        registry.record_activity(
            session_id="existing",
            session_file="/path/session.jsonl",
            command="research",
            files_created=["research.md"],
            files_modified=[],
        )

        # Second activity
        registry.record_activity(
            session_id="existing",
            session_file="/path/session.jsonl",
            command="plan",
            files_created=["plan.md"],
            files_modified=[],
        )

        session = registry.get("existing")
        assert session is not None
        assert len(session.activities) == 2
        assert session.activities[0].command == "research"
        assert session.activities[1].command == "plan"

    def test_record_activity_updates_last_activity(self, tmp_path: Path) -> None:
        """Should update last_activity timestamp on new activity."""
        registry = SessionRegistry(tmp_path / "registry.jsonl")

        registry.record_activity(
            session_id="test",
            session_file="/path/session.jsonl",
            command="research",
            files_created=[],
            files_modified=[],
        )

        session = registry.get("test")
        assert session is not None
        first_timestamp = session.last_activity

        # Small delay
        time.sleep(0.01)

        registry.record_activity(
            session_id="test",
            session_file="/path/session.jsonl",
            command="plan",
            files_created=[],
            files_modified=[],
        )

        session = registry.get("test")
        assert session is not None
        second_timestamp = session.last_activity
        assert second_timestamp > first_timestamp

    def test_prune_session_removes(self, tmp_path: Path) -> None:
        """Should remove session from registry."""
        registry = SessionRegistry(tmp_path / "registry.jsonl")

        registry.record_activity(
            session_id="to-prune",
            session_file="/path/session.jsonl",
            command="implement",
            files_created=["file.py"],
            files_modified=[],
        )

        assert "to-prune" in registry.sessions

        registry.prune_session("to-prune")

        assert "to-prune" not in registry.sessions
        assert registry.get("to-prune") is None

    def test_prune_nonexistent_session_no_error(self, tmp_path: Path) -> None:
        """Should not error when pruning non-existent session."""
        registry = SessionRegistry(tmp_path / "registry.jsonl")
        registry.prune_session("does-not-exist")  # Should not raise

    def test_skips_corrupted_jsonl_lines(self, tmp_path: Path) -> None:
        """Should skip corrupted lines and continue loading valid ones."""
        registry_path = tmp_path / "sessions" / "registry.jsonl"
        registry_path.parent.mkdir(parents=True)

        # Create JSONL with one valid and one corrupted line
        now = datetime.now(UTC)
        valid_session = TrackedSession(
            session_id="valid",
            session_file="/path/valid.jsonl",
            first_seen=now,
            last_activity=now,
            activities=[],
        )

        content = (
            valid_session.model_dump_json() + "\n"
            "this is not valid json\n"
            '{"also": "not a valid session"}\n'
        )
        registry_path.write_text(content)

        # Should load valid session and skip corrupted ones
        registry = SessionRegistry(registry_path)
        assert "valid" in registry.sessions
        assert len(registry.sessions) == 1

    def test_handles_empty_file(self, tmp_path: Path) -> None:
        """Should handle empty registry file."""
        registry_path = tmp_path / "registry.jsonl"
        registry_path.write_text("")

        registry = SessionRegistry(registry_path)
        assert registry.sessions == {}

    def test_handles_blank_lines(self, tmp_path: Path) -> None:
        """Should skip blank lines in registry."""
        registry_path = tmp_path / "registry.jsonl"

        now = datetime.now(UTC)
        session = TrackedSession(
            session_id="test",
            session_file="/path/test.jsonl",
            first_seen=now,
            last_activity=now,
        )

        content = "\n\n" + session.model_dump_json() + "\n\n"
        registry_path.write_text(content)

        registry = SessionRegistry(registry_path)
        assert "test" in registry.sessions


class TestGetRegistry:
    """Tests for get_registry function."""

    def test_returns_registry_for_weld_dir(self, tmp_path: Path) -> None:
        """Should return registry pointing to sessions subdirectory."""
        registry = get_registry(tmp_path)
        assert registry.registry_path == tmp_path / "sessions" / "registry.jsonl"


class TestShouldExcludePath:
    """Tests for _should_exclude_path function."""

    def test_excludes_git_directory(self) -> None:
        """Should exclude .git directory."""
        path = Path("/repo/.git/objects/abc")
        assert _should_exclude_path(path) is True

    def test_excludes_venv_directory(self) -> None:
        """Should exclude .venv directory."""
        path = Path("/repo/.venv/lib/python/site-packages")
        assert _should_exclude_path(path) is True

    def test_excludes_node_modules(self) -> None:
        """Should exclude node_modules directory."""
        path = Path("/repo/node_modules/package/index.js")
        assert _should_exclude_path(path) is True

    def test_excludes_egg_info_suffix(self) -> None:
        """Should exclude directories ending in .egg-info."""
        path = Path("/repo/my_package.egg-info/PKG-INFO")
        assert _should_exclude_path(path) is True

    def test_excludes_coverage_file(self) -> None:
        """Should exclude .coverage file/directory."""
        path = Path("/repo/.coverage")
        assert _should_exclude_path(path) is True

    def test_allows_regular_file(self) -> None:
        """Should not exclude regular source files."""
        path = Path("/repo/src/main.py")
        assert _should_exclude_path(path) is False

    def test_allows_test_file(self) -> None:
        """Should not exclude test files."""
        path = Path("/repo/tests/test_main.py")
        assert _should_exclude_path(path) is False


class TestGetFileSnapshot:
    """Tests for get_file_snapshot function."""

    def test_captures_files_with_mtime(self, tmp_path: Path) -> None:
        """Should capture files with their modification times."""
        # Create test files
        (tmp_path / "file1.py").write_text("content1")
        (tmp_path / "file2.py").write_text("content2")

        snapshot = get_file_snapshot(tmp_path)

        assert "file1.py" in snapshot
        assert "file2.py" in snapshot
        assert isinstance(snapshot["file1.py"], float)

    def test_excludes_git_directory(self, tmp_path: Path) -> None:
        """Should exclude .git directory."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git config")
        (tmp_path / "source.py").write_text("code")

        snapshot = get_file_snapshot(tmp_path)

        assert "source.py" in snapshot
        assert ".git/config" not in snapshot

    def test_excludes_venv(self, tmp_path: Path) -> None:
        """Should exclude .venv directory."""
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        (venv_dir / "bin" / "python").parent.mkdir(parents=True)
        (venv_dir / "bin" / "python").write_text("#!/bin/python")
        (tmp_path / "app.py").write_text("code")

        snapshot = get_file_snapshot(tmp_path)

        assert "app.py" in snapshot
        assert any(".venv" in key for key in snapshot) is False

    def test_excludes_egg_info(self, tmp_path: Path) -> None:
        """Should exclude .egg-info directories."""
        egg_dir = tmp_path / "mypackage.egg-info"
        egg_dir.mkdir()
        (egg_dir / "PKG-INFO").write_text("package info")
        (tmp_path / "mypackage.py").write_text("code")

        snapshot = get_file_snapshot(tmp_path)

        assert "mypackage.py" in snapshot
        assert any(".egg-info" in key for key in snapshot) is False

    def test_captures_nested_files(self, tmp_path: Path) -> None:
        """Should capture files in subdirectories."""
        src_dir = tmp_path / "src" / "package"
        src_dir.mkdir(parents=True)
        (src_dir / "module.py").write_text("code")

        snapshot = get_file_snapshot(tmp_path)

        assert "src/package/module.py" in snapshot

    def test_returns_empty_for_empty_dir(self, tmp_path: Path) -> None:
        """Should return empty dict for empty directory."""
        snapshot = get_file_snapshot(tmp_path)
        assert snapshot == {}


class TestComputeChanges:
    """Tests for compute_changes function."""

    def test_detects_created_files(self) -> None:
        """Should detect newly created files."""
        before = {"existing.py": 1000.0}
        after = {"existing.py": 1000.0, "new.py": 1001.0}

        created, modified = compute_changes(before, after)

        assert created == ["new.py"]
        assert modified == []

    def test_detects_modified_files(self) -> None:
        """Should detect modified files by mtime change."""
        before = {"file.py": 1000.0}
        after = {"file.py": 1001.0}

        created, modified = compute_changes(before, after)

        assert created == []
        assert modified == ["file.py"]

    def test_detects_both_created_and_modified(self) -> None:
        """Should detect both created and modified files."""
        before = {"existing.py": 1000.0}
        after = {"existing.py": 1001.0, "new.py": 1002.0}

        created, modified = compute_changes(before, after)

        assert created == ["new.py"]
        assert modified == ["existing.py"]

    def test_ignores_unchanged_files(self) -> None:
        """Should ignore files with unchanged mtime."""
        before = {"file.py": 1000.0}
        after = {"file.py": 1000.0}

        created, modified = compute_changes(before, after)

        assert created == []
        assert modified == []

    def test_ignores_deleted_files(self) -> None:
        """Should not report deleted files (not in after snapshot)."""
        before = {"deleted.py": 1000.0, "kept.py": 1000.0}
        after = {"kept.py": 1000.0}

        created, modified = compute_changes(before, after)

        assert created == []
        assert modified == []

    def test_handles_empty_snapshots(self) -> None:
        """Should handle empty before/after snapshots."""
        created, modified = compute_changes({}, {})
        assert created == []
        assert modified == []

        created, modified = compute_changes({}, {"new.py": 1000.0})
        assert created == ["new.py"]
        assert modified == []


class TestTrackSessionActivity:
    """Tests for track_session_activity context manager."""

    def test_no_session_no_tracking(self, tmp_path: Path) -> None:
        """Should yield without tracking if no session detected."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        repo_root = tmp_path

        with patch("weld.services.session_tracker.detect_current_session", return_value=None):
            with track_session_activity(weld_dir, repo_root, "implement"):
                (repo_root / "new.py").write_text("code")

            # No registry should be created
            registry = get_registry(weld_dir)
            assert registry.sessions == {}

    def test_records_created_files(self, tmp_path: Path) -> None:
        """Should record files created during context."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        repo_root = tmp_path

        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"user"}')

        with patch(
            "weld.services.session_tracker.detect_current_session",
            return_value=session_file,
        ):
            with track_session_activity(weld_dir, repo_root, "implement"):
                (repo_root / "created.py").write_text("new code")

            registry = get_registry(weld_dir)
            session = registry.get("session")
            assert session is not None
            assert "created.py" in session.activities[0].files_created

    def test_records_modified_files(self, tmp_path: Path) -> None:
        """Should record files modified during context."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        repo_root = tmp_path

        # Create file before context
        existing = repo_root / "existing.py"
        existing.write_text("original")

        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"user"}')

        with patch(
            "weld.services.session_tracker.detect_current_session",
            return_value=session_file,
        ):
            with track_session_activity(weld_dir, repo_root, "implement"):
                time.sleep(0.01)  # Ensure mtime changes
                existing.write_text("modified")

            registry = get_registry(weld_dir)
            session = registry.get("session")
            assert session is not None
            assert "existing.py" in session.activities[0].files_modified

    def test_no_changes_no_record(self, tmp_path: Path) -> None:
        """Should not record activity if no files changed."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        repo_root = tmp_path

        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"user"}')

        with patch(
            "weld.services.session_tracker.detect_current_session",
            return_value=session_file,
        ):
            with track_session_activity(weld_dir, repo_root, "implement"):
                pass  # No file changes

            registry = get_registry(weld_dir)
            assert registry.sessions == {}

    def test_marks_incomplete_on_exception(self, tmp_path: Path) -> None:
        """Should mark activity as incomplete if exception occurs."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        repo_root = tmp_path

        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"user"}')

        with patch(
            "weld.services.session_tracker.detect_current_session",
            return_value=session_file,
        ):
            try:
                with track_session_activity(weld_dir, repo_root, "implement"):
                    (repo_root / "file.py").write_text("partial")
                    raise RuntimeError("Simulated failure")
            except RuntimeError:
                pass

            registry = get_registry(weld_dir)
            session = registry.get("session")
            assert session is not None
            assert session.activities[0].completed is False

    def test_records_command_name(self, tmp_path: Path) -> None:
        """Should record the command name in activity."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        repo_root = tmp_path

        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"user"}')

        with patch(
            "weld.services.session_tracker.detect_current_session",
            return_value=session_file,
        ):
            with track_session_activity(weld_dir, repo_root, "research"):
                (repo_root / "research.md").write_text("findings")

            registry = get_registry(weld_dir)
            session = registry.get("session")
            assert session is not None
            assert session.activities[0].command == "research"


class TestSnapshotExcludes:
    """Tests for SNAPSHOT_EXCLUDES constant."""

    def test_contains_common_directories(self) -> None:
        """Should contain commonly excluded directories."""
        assert ".git" in SNAPSHOT_EXCLUDES
        assert ".weld" in SNAPSHOT_EXCLUDES
        assert ".venv" in SNAPSHOT_EXCLUDES
        assert "node_modules" in SNAPSHOT_EXCLUDES
        assert "__pycache__" in SNAPSHOT_EXCLUDES

    def test_contains_egg_info_pattern(self) -> None:
        """Should contain .egg-info for suffix matching."""
        assert ".egg-info" in SNAPSHOT_EXCLUDES


class TestSessionTrackingEdgeCases:
    """Tests for session tracking error handling and edge cases."""

    def test_logs_debug_when_no_session_detected(self, tmp_path: Path, caplog) -> None:
        """Should log debug message when no Claude session detected."""
        import logging

        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        repo_root = tmp_path

        with (
            caplog.at_level(logging.DEBUG),
            patch(
                "weld.services.session_tracker.detect_current_session",
                return_value=None,
            ),
            track_session_activity(weld_dir, repo_root, "implement"),
        ):
            pass

        assert "No Claude session detected" in caplog.text
        assert "skipping tracking for implement" in caplog.text

    def test_continues_when_pre_snapshot_fails(self, tmp_path: Path, caplog) -> None:
        """Should continue command execution if pre-command snapshot fails."""
        import logging

        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        repo_root = tmp_path

        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"user"}')

        command_executed = False

        with (
            caplog.at_level(logging.ERROR),
            patch(
                "weld.services.session_tracker.detect_current_session",
                return_value=session_file,
            ),
            patch(
                "weld.services.session_tracker.get_file_snapshot",
                side_effect=OSError("Permission denied"),
            ),
            track_session_activity(weld_dir, repo_root, "implement"),
        ):
            command_executed = True

        # Command should still execute
        assert command_executed is True
        # Should log error about snapshot failure
        assert "Failed to capture pre-command snapshot" in caplog.text
        # No registry should be created
        registry = get_registry(weld_dir)
        assert len(registry.sessions) == 0

    def test_continues_when_post_snapshot_fails(self, tmp_path: Path, caplog) -> None:
        """Should continue if post-command snapshot fails."""
        import logging

        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        repo_root = tmp_path

        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"user"}')

        command_executed = False
        snapshot_call_count = 0

        def mock_snapshot(_repo_root):
            nonlocal snapshot_call_count
            snapshot_call_count += 1
            if snapshot_call_count == 1:
                # First call (pre-command) succeeds
                return {"existing.py": 1000.0}
            # Second call (post-command) fails
            raise OSError("Disk error")

        with (
            caplog.at_level(logging.ERROR),
            patch(
                "weld.services.session_tracker.detect_current_session",
                return_value=session_file,
            ),
            patch(
                "weld.services.session_tracker.get_file_snapshot",
                side_effect=mock_snapshot,
            ),
            track_session_activity(weld_dir, repo_root, "implement"),
        ):
            command_executed = True
            (repo_root / "new.py").write_text("content")

        # Command should still execute
        assert command_executed is True
        # Should log error about save failure
        assert "Failed to save session activity" in caplog.text
        # No registry entry created due to post-snapshot failure
        registry = get_registry(weld_dir)
        assert len(registry.sessions) == 0

    def test_continues_when_registry_save_fails(self, tmp_path: Path, caplog) -> None:
        """Should continue if registry save operation fails."""
        import logging

        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        repo_root = tmp_path

        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"user"}')

        command_executed = False

        with (
            caplog.at_level(logging.ERROR),
            patch(
                "weld.services.session_tracker.detect_current_session",
                return_value=session_file,
            ),
            patch(
                "weld.services.session_tracker.SessionRegistry.save",
                side_effect=OSError("Disk full"),
            ),
            track_session_activity(weld_dir, repo_root, "implement"),
        ):
            command_executed = True
            (repo_root / "new.py").write_text("content")

        # Command should still execute
        assert command_executed is True
        # Should log error about save failure
        assert "Failed to save session activity" in caplog.text

    def test_tracks_incomplete_even_with_save_error(self, tmp_path: Path, caplog) -> None:
        """Should attempt to save incomplete status even if save fails."""
        import logging

        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        repo_root = tmp_path

        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type":"user"}')

        with (
            caplog.at_level(logging.ERROR),
            patch(
                "weld.services.session_tracker.detect_current_session",
                return_value=session_file,
            ),
            patch(
                "weld.services.session_tracker.SessionRegistry.save",
                side_effect=OSError("Disk full"),
            ),
        ):
            try:
                with track_session_activity(weld_dir, repo_root, "implement"):
                    (repo_root / "partial.py").write_text("incomplete")
                    raise RuntimeError("Command failed")
            except RuntimeError:
                pass

        # Should attempt to save (and fail) with completed=False
        assert "Failed to save session activity" in caplog.text


class TestFileSnapshotTimeout:
    """Tests for file snapshot timeout behavior in large repositories."""

    def test_snapshot_completes_without_timeout(self, tmp_path: Path) -> None:
        """Should complete snapshot when repo is small."""
        # Create small repo with few files
        for i in range(10):
            (tmp_path / f"file{i}.txt").write_text("content")

        snapshot = get_file_snapshot(tmp_path, timeout=1)

        # Should capture all files
        assert len(snapshot) == 10
        for i in range(10):
            assert f"file{i}.txt" in snapshot

    def test_snapshot_returns_partial_on_timeout(self, tmp_path: Path, caplog) -> None:
        """Should return partial snapshot if timeout exceeded."""
        # Create many files to trigger timeout
        for i in range(100):
            (tmp_path / f"file{i}.txt").write_text("content")

        with caplog.at_level(logging.WARNING):
            # Use very short timeout to force timeout
            snapshot = get_file_snapshot(tmp_path, timeout=0.001)

        # Should return dict (possibly partial)
        assert isinstance(snapshot, dict)

        # Should log warning about timeout
        assert "File snapshot timed out" in caplog.text
        assert "Using partial snapshot for tracking" in caplog.text

    def test_snapshot_logs_files_scanned_count(self, tmp_path: Path, caplog) -> None:
        """Should log number of files scanned when timeout occurs."""
        # Create many files to increase chance of timeout
        for i in range(500):
            (tmp_path / f"file{i}.txt").write_text("content")

        with caplog.at_level(logging.WARNING):
            snapshot = get_file_snapshot(tmp_path, timeout=0.001)

        # Should return dict
        assert isinstance(snapshot, dict)

        # If timeout occurred, should log count of files scanned
        if "File snapshot timed out" in caplog.text:
            assert "files scanned" in caplog.text
        # Otherwise, all files were scanned before timeout (fast system)
        # Either outcome is valid

    def test_snapshot_excludes_common_directories(self, tmp_path: Path) -> None:
        """Should still exclude common directories even with timeout."""
        # Create files in excluded directories
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("git config")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "package.json").write_text("{}")

        # Create normal file
        (tmp_path / "normal.txt").write_text("content")

        snapshot = get_file_snapshot(tmp_path, timeout=5)

        # Should only include normal file
        assert "normal.txt" in snapshot
        assert ".git/config" not in snapshot
        assert "node_modules/package.json" not in snapshot
