"""Tests for lock manager."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

from weld.core.lock_manager import (
    LockError,
    acquire_lock,
    get_current_lock,
    is_stale_lock,
    release_lock,
    update_heartbeat,
)
from weld.models import Lock


@pytest.fixture
def weld_dir(tmp_path: Path) -> Path:
    """Create temporary .weld directory."""
    d = tmp_path / ".weld"
    d.mkdir()
    return d


class TestAcquireLock:
    """Tests for acquire_lock function."""

    def test_acquire_creates_lock_file(self, weld_dir: Path) -> None:
        """Acquiring lock creates lock file."""
        lock = acquire_lock(weld_dir, "run-123", "step loop")
        assert lock.pid == os.getpid()
        assert lock.run_id == "run-123"
        assert (weld_dir / "active.lock").exists()

    def test_acquire_clears_stale_lock(self, weld_dir: Path) -> None:
        """Acquiring clears stale lock from dead process."""
        # Create lock with PID that's not running
        fake_lock = Lock(
            pid=99999,  # Almost certainly not running
            run_id="other-run",
            command="other command",
        )
        (weld_dir / "active.lock").write_text(fake_lock.model_dump_json())

        # Should succeed because 99999 is not running (stale)
        lock = acquire_lock(weld_dir, "new-run", "new command")
        assert lock.run_id == "new-run"

    def test_acquire_fails_if_locked_by_other(self, weld_dir: Path) -> None:
        """Cannot acquire if another process holds active lock."""
        # Create lock with different PID and mock it as running
        fake_lock = Lock(
            pid=99999,
            run_id="other-run",
            command="other command",
        )
        (weld_dir / "active.lock").write_text(fake_lock.model_dump_json())

        # Mock _is_pid_running to return True for 99999
        with (
            mock.patch("weld.core.lock_manager._is_pid_running", return_value=True),
            pytest.raises(LockError, match="Run already in progress"),
        ):
            acquire_lock(weld_dir, "new-run", "new command")

    def test_acquire_same_pid_updates_lock(self, weld_dir: Path) -> None:
        """Same process can re-acquire/update lock."""
        acquire_lock(weld_dir, "run-1", "cmd-1")
        lock2 = acquire_lock(weld_dir, "run-2", "cmd-2")
        assert lock2.run_id == "run-2"


class TestReleaseLock:
    """Tests for release_lock function."""

    def test_release_removes_lock_file(self, weld_dir: Path) -> None:
        """Releasing lock removes lock file."""
        acquire_lock(weld_dir, "run-123", "test")
        assert (weld_dir / "active.lock").exists()
        release_lock(weld_dir)
        assert not (weld_dir / "active.lock").exists()

    def test_release_ignores_other_pids_lock(self, weld_dir: Path) -> None:
        """Cannot release lock held by different PID."""
        fake_lock = Lock(pid=99999, run_id="other", command="other")
        (weld_dir / "active.lock").write_text(fake_lock.model_dump_json())
        release_lock(weld_dir)  # Should do nothing
        assert (weld_dir / "active.lock").exists()


class TestIsStale:
    """Tests for is_stale_lock function."""

    def test_dead_pid_is_stale(self) -> None:
        """Lock with dead PID is stale."""
        lock = Lock(pid=99999, run_id="test", command="test")
        # PID 99999 is almost certainly not running
        assert is_stale_lock(lock) is True

    def test_old_heartbeat_is_stale(self) -> None:
        """Lock with old heartbeat is stale."""
        lock = Lock(
            pid=os.getpid(),  # Our PID, so not dead
            run_id="test",
            command="test",
            last_heartbeat=datetime.now() - timedelta(hours=2),
        )
        assert is_stale_lock(lock, timeout_seconds=3600) is True

    def test_fresh_lock_not_stale(self) -> None:
        """Fresh lock is not stale."""
        lock = Lock(pid=os.getpid(), run_id="test", command="test")
        assert is_stale_lock(lock) is False


class TestUpdateHeartbeat:
    """Tests for update_heartbeat function."""

    def test_updates_heartbeat_timestamp(self, weld_dir: Path) -> None:
        """Heartbeat timestamp is updated."""
        lock = acquire_lock(weld_dir, "run-123", "test")
        original_heartbeat = lock.last_heartbeat

        # Wait a tiny bit to ensure time difference
        import time

        time.sleep(0.01)

        update_heartbeat(weld_dir)
        updated = get_current_lock(weld_dir)

        assert updated is not None
        assert updated.last_heartbeat > original_heartbeat

    def test_ignores_other_pids_lock(self, weld_dir: Path) -> None:
        """Cannot update heartbeat on lock held by different PID."""
        fake_lock = Lock(pid=99999, run_id="other", command="other")
        (weld_dir / "active.lock").write_text(fake_lock.model_dump_json())
        original_heartbeat = fake_lock.last_heartbeat

        update_heartbeat(weld_dir)  # Should do nothing

        current = get_current_lock(weld_dir)
        assert current is not None
        assert current.last_heartbeat == original_heartbeat


class TestGetCurrentLock:
    """Tests for get_current_lock function."""

    def test_returns_none_if_no_lock_file(self, weld_dir: Path) -> None:
        """Returns None if no lock file exists."""
        assert get_current_lock(weld_dir) is None

    def test_returns_lock_if_valid(self, weld_dir: Path) -> None:
        """Returns Lock object if valid lock file exists."""
        acquire_lock(weld_dir, "run-123", "test")
        retrieved = get_current_lock(weld_dir)
        assert retrieved is not None
        assert retrieved.run_id == "run-123"

    def test_returns_none_if_corrupted(self, weld_dir: Path) -> None:
        """Returns None if lock file is corrupted."""
        (weld_dir / "active.lock").write_text("not valid json")
        assert get_current_lock(weld_dir) is None
