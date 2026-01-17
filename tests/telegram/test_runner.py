"""Tests for Telegram bot async subprocess runner."""

import asyncio
from unittest.mock import MagicMock

import pytest

from weld.telegram.runner import (
    GRACEFUL_SHUTDOWN_TIMEOUT,
    _active_runs,
    cancel_run,
)


@pytest.fixture(autouse=True)
def clear_active_runs():
    """Clear the active runs registry before and after each test."""
    _active_runs.clear()
    yield
    _active_runs.clear()


@pytest.mark.asyncio
@pytest.mark.unit
class TestCancelRun:
    """Tests for cancel_run function."""

    async def test_cancel_nonexistent_run_returns_false(self) -> None:
        """cancel_run returns False when run_id doesn't exist."""
        result = await cancel_run(99999)
        assert result is False

    async def test_cancel_already_terminated_returns_false(self) -> None:
        """cancel_run returns False when process already terminated."""
        # Create a mock process that appears already terminated
        mock_proc = MagicMock()
        mock_proc.returncode = 0  # Already exited
        mock_proc.pid = 12345

        _active_runs[1] = mock_proc

        result = await cancel_run(1)
        assert result is False
        # Should have been cleaned up
        assert 1 not in _active_runs

    async def test_cancel_graceful_termination(self) -> None:
        """cancel_run sends SIGTERM and waits for graceful exit."""
        mock_proc = MagicMock()
        mock_proc.returncode = None  # Still running
        mock_proc.pid = 12345
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()

        # wait() returns quickly (graceful shutdown)
        async def mock_wait():
            mock_proc.returncode = 0

        mock_proc.wait = mock_wait

        _active_runs[1] = mock_proc

        result = await cancel_run(1)

        assert result is True
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_not_called()
        assert 1 not in _active_runs

    @pytest.mark.slow
    async def test_cancel_force_kill_after_timeout(self) -> None:
        """cancel_run sends SIGKILL if process doesn't exit after SIGTERM."""
        mock_proc = MagicMock()
        mock_proc.returncode = None  # Still running
        mock_proc.pid = 12345
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()

        kill_called = False

        async def mock_wait():
            nonlocal kill_called
            if not kill_called:
                # First call (after terminate) - never complete, will be cancelled by wait_for
                await asyncio.sleep(GRACEFUL_SHUTDOWN_TIMEOUT + 10)
            # After kill, complete immediately
            mock_proc.returncode = -9

        def mock_kill():
            nonlocal kill_called
            kill_called = True

        mock_proc.wait = mock_wait
        mock_proc.kill = mock_kill

        _active_runs[1] = mock_proc

        result = await cancel_run(1)

        assert result is True
        mock_proc.terminate.assert_called_once()
        assert kill_called  # kill was called
        assert 1 not in _active_runs

    async def test_cancel_removes_from_registry(self) -> None:
        """cancel_run removes the run from _active_runs."""
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.pid = 12345
        mock_proc.terminate = MagicMock()

        async def mock_wait():
            mock_proc.returncode = 0

        mock_proc.wait = mock_wait

        _active_runs[1] = mock_proc
        _active_runs[2] = MagicMock()  # Another run that shouldn't be affected

        await cancel_run(1)

        assert 1 not in _active_runs
        assert 2 in _active_runs  # Other run should still be there


@pytest.mark.asyncio
@pytest.mark.unit
class TestActiveRunsRegistry:
    """Tests for _active_runs registry behavior."""

    async def test_registry_is_module_level_dict(self) -> None:
        """_active_runs is a module-level dictionary."""
        assert isinstance(_active_runs, dict)

    async def test_registry_cleared_by_fixture(self) -> None:
        """Registry is empty at start of each test (via fixture)."""
        assert len(_active_runs) == 0

    async def test_can_register_multiple_runs(self) -> None:
        """Multiple runs can be registered simultaneously."""
        mock_proc1 = MagicMock()
        mock_proc2 = MagicMock()

        _active_runs[1] = mock_proc1
        _active_runs[2] = mock_proc2

        assert len(_active_runs) == 2
        assert _active_runs[1] is mock_proc1
        assert _active_runs[2] is mock_proc2

    async def test_graceful_shutdown_timeout_is_reasonable(self) -> None:
        """GRACEFUL_SHUTDOWN_TIMEOUT is a reasonable value (not too short, not too long)."""
        assert GRACEFUL_SHUTDOWN_TIMEOUT >= 1.0  # At least 1 second
        assert GRACEFUL_SHUTDOWN_TIMEOUT <= 30.0  # At most 30 seconds
