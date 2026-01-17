"""Tests for Telegram bot async subprocess runner."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from weld.telegram.errors import TelegramRunError
from weld.telegram.runner import (
    DEFAULT_TIMEOUT,
    GRACEFUL_SHUTDOWN_TIMEOUT,
    _active_runs,
    cancel_run,
    execute_run,
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


@pytest.mark.asyncio
@pytest.mark.unit
class TestExecuteRun:
    """Tests for execute_run function."""

    async def test_execute_run_with_echo_command(self) -> None:
        """execute_run can run a command and capture stdout."""
        with patch("weld.telegram.runner.asyncio.create_subprocess_exec") as mock_create_subprocess:
            # Create a mock process
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.returncode = None

            # Create mock streams
            stdout_content = b"Hello, World!\n"
            mock_stdout = MagicMock()
            read_count = 0

            async def mock_stdout_read(size: int) -> bytes:
                nonlocal read_count
                if read_count == 0:
                    read_count += 1
                    return stdout_content
                return b""

            mock_stdout.read = mock_stdout_read

            mock_stderr = MagicMock()

            async def mock_stderr_read(size: int) -> bytes:
                return b""

            mock_stderr.read = mock_stderr_read

            mock_proc.stdout = mock_stdout
            mock_proc.stderr = mock_stderr

            async def mock_wait() -> int:
                mock_proc.returncode = 0
                return 0

            mock_proc.wait = mock_wait

            async def create_proc(*args, **kwargs):
                return mock_proc

            mock_create_subprocess.side_effect = create_proc

            # Collect output
            output_chunks: list[tuple[str, str]] = []
            async for chunk_type, data in execute_run(1, "echo", ["Hello"]):
                output_chunks.append((chunk_type, data))

            # Verify we got stdout output matching our mock
            assert len(output_chunks) > 0
            stdout_chunks = [(t, d) for t, d in output_chunks if t == "stdout"]
            assert len(stdout_chunks) > 0
            assert any("Hello, World!" in data for _, data in stdout_chunks)
            # Run should be cleaned up
            assert 1 not in _active_runs

    async def test_execute_run_registers_and_unregisters_process(self) -> None:
        """execute_run registers process in _active_runs and cleans up after."""
        with patch("weld.telegram.runner.asyncio.create_subprocess_exec") as mock_create_subprocess:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.returncode = None

            # Empty streams that immediately report EOF
            mock_stdout = MagicMock()

            async def mock_stdout_read(size: int) -> bytes:
                return b""

            mock_stdout.read = mock_stdout_read

            mock_stderr = MagicMock()

            async def mock_stderr_read(size: int) -> bytes:
                return b""

            mock_stderr.read = mock_stderr_read

            mock_proc.stdout = mock_stdout
            mock_proc.stderr = mock_stderr

            registered_during_run = False

            async def mock_wait() -> int:
                nonlocal registered_during_run
                # Check if registered during execution
                registered_during_run = 1 in _active_runs
                mock_proc.returncode = 0
                return 0

            mock_proc.wait = mock_wait

            async def create_proc(*args, **kwargs):
                return mock_proc

            mock_create_subprocess.side_effect = create_proc

            async for _ in execute_run(1, "test"):
                pass

            assert registered_during_run
            assert 1 not in _active_runs

    async def test_execute_run_raises_on_nonzero_exit(self) -> None:
        """execute_run raises TelegramRunError on non-zero exit code."""
        with patch("weld.telegram.runner.asyncio.create_subprocess_exec") as mock_create_subprocess:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.returncode = None

            mock_stdout = MagicMock()

            async def mock_stdout_read(size: int) -> bytes:
                return b""

            mock_stdout.read = mock_stdout_read

            mock_stderr = MagicMock()

            async def mock_stderr_read(size: int) -> bytes:
                return b""

            mock_stderr.read = mock_stderr_read

            mock_proc.stdout = mock_stdout
            mock_proc.stderr = mock_stderr

            async def mock_wait() -> int:
                mock_proc.returncode = 1
                return 1

            mock_proc.wait = mock_wait

            async def create_proc(*args, **kwargs):
                return mock_proc

            mock_create_subprocess.side_effect = create_proc

            with pytest.raises(TelegramRunError) as exc_info:
                async for _ in execute_run(1, "failing-command"):
                    pass

            assert "exit code 1" in str(exc_info.value)

    async def test_execute_run_raises_on_command_not_found(self) -> None:
        """execute_run raises TelegramRunError when command not found."""
        with patch("weld.telegram.runner.asyncio.create_subprocess_exec") as mock_create_subprocess:
            mock_create_subprocess.side_effect = FileNotFoundError()

            with pytest.raises(TelegramRunError) as exc_info:
                async for _ in execute_run(1, "nonexistent"):
                    pass

            assert "not found" in str(exc_info.value)

    @pytest.mark.slow
    async def test_execute_run_timeout(self) -> None:
        """execute_run raises TelegramRunError on timeout."""
        with patch("weld.telegram.runner.asyncio.create_subprocess_exec") as mock_create_subprocess:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.returncode = None

            # Streams that simulate slow reads - wait_for wraps them,
            # so we need to actually delay. Using small delay with short timeout.
            mock_stdout = MagicMock()

            async def mock_stdout_read(size: int) -> bytes:
                # Delay longer than the overall timeout to trigger timeout check
                await asyncio.sleep(0.2)
                return b""

            mock_stdout.read = mock_stdout_read

            mock_stderr = MagicMock()

            async def mock_stderr_read(size: int) -> bytes:
                await asyncio.sleep(0.2)
                return b""

            mock_stderr.read = mock_stderr_read

            mock_proc.stdout = mock_stdout
            mock_proc.stderr = mock_stderr
            mock_proc.terminate = MagicMock()
            mock_proc.kill = MagicMock()

            async def mock_wait() -> int:
                mock_proc.returncode = -15
                return -15

            mock_proc.wait = mock_wait

            async def create_proc(*args, **kwargs):
                return mock_proc

            mock_create_subprocess.side_effect = create_proc

            # Short timeout (0.1s) with reads that take 0.2s each
            # After first read timeout check, elapsed >= timeout triggers
            with pytest.raises(TelegramRunError) as exc_info:
                async for _ in execute_run(1, "slow-command", timeout=0.1):
                    pass

            assert "timed out" in str(exc_info.value).lower()

    async def test_execute_run_handles_cancellation(self) -> None:
        """execute_run handles asyncio.CancelledError properly."""
        with patch("weld.telegram.runner.asyncio.create_subprocess_exec") as mock_create_subprocess:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.returncode = None
            mock_proc.terminate = MagicMock()
            mock_proc.kill = MagicMock()

            mock_stdout = MagicMock()

            async def mock_read_cancelled(size: int) -> bytes:
                # Raise CancelledError to simulate task cancellation
                raise asyncio.CancelledError()

            mock_stdout.read = mock_read_cancelled

            mock_stderr = MagicMock()

            async def mock_stderr_read_cancelled(size: int) -> bytes:
                raise asyncio.CancelledError()

            mock_stderr.read = mock_stderr_read_cancelled

            mock_proc.stdout = mock_stdout
            mock_proc.stderr = mock_stderr

            async def mock_wait() -> int:
                mock_proc.returncode = -15
                return -15

            mock_proc.wait = mock_wait

            async def create_proc(*args, **kwargs):
                return mock_proc

            mock_create_subprocess.side_effect = create_proc

            with pytest.raises(asyncio.CancelledError):
                async for _ in execute_run(1, "cancelled-command"):
                    pass

            # Process should have been terminated
            mock_proc.terminate.assert_called()
            # Run should be cleaned up from registry
            assert 1 not in _active_runs

    async def test_execute_run_captures_stderr(self) -> None:
        """execute_run captures stderr output separately."""
        with patch("weld.telegram.runner.asyncio.create_subprocess_exec") as mock_create_subprocess:
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.returncode = None

            # Stdout returns nothing
            mock_stdout = MagicMock()

            async def mock_stdout_read(size: int) -> bytes:
                return b""

            mock_stdout.read = mock_stdout_read

            # Stderr returns error message
            mock_stderr = MagicMock()
            stderr_read_count = 0

            async def mock_stderr_read(size: int) -> bytes:
                nonlocal stderr_read_count
                if stderr_read_count == 0:
                    stderr_read_count += 1
                    return b"Error message\n"
                return b""

            mock_stderr.read = mock_stderr_read

            mock_proc.stdout = mock_stdout
            mock_proc.stderr = mock_stderr

            async def mock_wait() -> int:
                mock_proc.returncode = 0
                return 0

            mock_proc.wait = mock_wait

            async def create_proc(*args, **kwargs):
                return mock_proc

            mock_create_subprocess.side_effect = create_proc

            output_chunks: list[tuple[str, str]] = []
            async for chunk_type, data in execute_run(1, "error-command"):
                output_chunks.append((chunk_type, data))

            # Should have captured stderr
            stderr_chunks = [(t, d) for t, d in output_chunks if t == "stderr"]
            assert len(stderr_chunks) > 0
            assert any("Error" in data for _, data in stderr_chunks)

    async def test_default_timeout_is_reasonable(self) -> None:
        """DEFAULT_TIMEOUT is a reasonable value for command execution."""
        assert DEFAULT_TIMEOUT >= 60  # At least 1 minute
        assert DEFAULT_TIMEOUT <= 3600  # At most 1 hour
