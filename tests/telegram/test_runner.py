"""Tests for Telegram bot async subprocess runner."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from weld.telegram.errors import TelegramRunError
from weld.telegram.runner import (
    DEFAULT_TIMEOUT,
    GRACEFUL_SHUTDOWN_TIMEOUT,
    ArrowMenuItem,
    PromptInfo,
    _active_runs,
    cancel_run,
    detect_prompt,
    execute_run,
    parse_arrow_menu,
    send_input,
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

        _active_runs[1] = (mock_proc, asyncio.Queue())

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

        _active_runs[1] = (mock_proc, asyncio.Queue())

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

        _active_runs[1] = (mock_proc, asyncio.Queue())

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

        _active_runs[1] = (mock_proc, asyncio.Queue())
        _active_runs[2] = (MagicMock(), asyncio.Queue())  # Another run that shouldn't be affected

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


@pytest.mark.unit
class TestDetectPromptSelect:
    """Tests for detect_prompt with Select [N/N/N] style prompts."""

    def test_select_prompt_simple(self) -> None:
        """detect_prompt finds Select [1/2] style prompt."""
        text = "Select [1/2]: "
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "select"
        assert result.options == ["1", "2"]

    def test_select_prompt_three_options(self) -> None:
        """detect_prompt finds Select [1/2/3] style prompt."""
        text = "Choose an option Select [1/2/3]: "
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "select"
        assert result.options == ["1", "2", "3"]

    def test_select_prompt_many_options(self) -> None:
        """detect_prompt handles many options in Select prompt."""
        text = "Select [a/b/c/d/e]: "
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "select"
        assert result.options == ["a", "b", "c", "d", "e"]

    def test_select_prompt_with_leading_text(self) -> None:
        """detect_prompt finds Select prompt even with leading text."""
        text = "Step 1 of 3: Select your option Select [yes/no/skip]: "
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "select"
        assert result.options == ["yes", "no", "skip"]

    def test_select_prompt_captures_full_text(self) -> None:
        """detect_prompt captures the full prompt text."""
        text = "What would you like to do? Select [1/2]: "
        result = detect_prompt(text)
        assert result is not None
        assert result.text == text


@pytest.mark.unit
class TestDetectPromptYesNo:
    """Tests for detect_prompt with yes/no style prompts."""

    def test_yn_lowercase_parentheses(self) -> None:
        """detect_prompt finds (y/n) style prompt."""
        text = "Continue? (y/n): "
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "yes_no"
        assert "y" in result.options
        assert "n" in result.options

    def test_yn_parentheses_question_mark(self) -> None:
        """detect_prompt finds (y/n)? style prompt."""
        text = "Save changes? (y/n)?"
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "yes_no"

    def test_yn_parentheses_no_colon(self) -> None:
        """detect_prompt finds (y/n) without trailing punctuation."""
        text = "Proceed (y/n) "
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "yes_no"

    def test_yn_uppercase_default_yes(self) -> None:
        """detect_prompt finds [Y/n] with default yes."""
        text = "Install dependencies? [Y/n]: "
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "yes_no"
        assert "Y" in result.options
        assert "" in result.options  # Empty string for default

    def test_yn_uppercase_default_no(self) -> None:
        """detect_prompt finds [y/N] with default no."""
        text = "Skip validation? [y/N]: "
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "yes_no"
        assert "N" in result.options
        assert "" in result.options  # Empty string for default


@pytest.mark.unit
class TestDetectPromptConfirm:
    """Tests for detect_prompt with Continue?/Proceed?/Apply? style prompts."""

    def test_continue_prompt(self) -> None:
        """detect_prompt finds 'Continue?' at end of text."""
        text = "Changes staged. Continue?"
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "confirm"
        assert "y" in result.options
        assert "n" in result.options

    def test_proceed_prompt(self) -> None:
        """detect_prompt finds 'Proceed?' at end of text."""
        text = "All checks passed. Proceed?"
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "confirm"

    def test_apply_prompt(self) -> None:
        """detect_prompt finds 'Apply?' at end of text."""
        text = "Review complete. Apply?"
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "confirm"

    def test_confirm_prompt(self) -> None:
        """detect_prompt finds 'Confirm?' at end of text."""
        text = "Are you sure you want to delete this file? Confirm?"
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "confirm"

    def test_confirm_case_insensitive(self) -> None:
        """detect_prompt is case-insensitive for confirm prompts."""
        for word in ["continue", "CONTINUE", "Continue", "PROCEED", "apply", "CONFIRM"]:
            text = f"Ready. {word}?"
            result = detect_prompt(text)
            assert result is not None, f"Failed to detect '{word}?'"
            assert result.prompt_type == "confirm"

    def test_confirm_not_in_middle_of_text(self) -> None:
        """detect_prompt only matches confirm words at end of text."""
        # Continue in middle should not match
        text = "Please continue reading this message about our system."
        result = detect_prompt(text)
        assert result is None


@pytest.mark.unit
class TestDetectPromptArrowMenu:
    """Tests for detect_prompt with arrow menu (simple-term-menu) style prompts."""

    def test_arrow_menu_checked_selected(self) -> None:
        """detect_prompt finds arrow menu with checked and selected item."""
        text = "> [x] Step 1: Initialize project"
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "arrow_menu"
        assert "enter" in result.options
        assert "up" in result.options
        assert "down" in result.options

    def test_arrow_menu_unchecked_selected(self) -> None:
        """detect_prompt finds arrow menu with unchecked selected item."""
        text = "> [ ] Step 2: Configure settings"
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "arrow_menu"

    def test_arrow_menu_multiple_items(self) -> None:
        """detect_prompt finds arrow menu in multiline menu output."""
        text = """> [x] Step 1: Initialize
  [ ] Step 2: Configure
  [x] Step 3: Complete"""
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "arrow_menu"

    def test_arrow_menu_with_leading_whitespace(self) -> None:
        """detect_prompt handles leading whitespace in arrow menu."""
        text = "    > [x] Selected item"
        result = detect_prompt(text)
        assert result is not None
        assert result.prompt_type == "arrow_menu"


@pytest.mark.unit
class TestDetectPromptNoMatch:
    """Tests for detect_prompt when no prompt is present."""

    def test_no_prompt_plain_text(self) -> None:
        """detect_prompt returns None for plain text."""
        result = detect_prompt("This is just regular output text.")
        assert result is None

    def test_no_prompt_partial_select(self) -> None:
        """detect_prompt returns None for incomplete Select pattern."""
        result = detect_prompt("Select [1/2")  # Missing closing bracket
        assert result is None

    def test_no_prompt_brackets_no_options(self) -> None:
        """detect_prompt returns None for brackets without options."""
        result = detect_prompt("Status [OK]")  # Not a Select prompt
        assert result is None

    def test_no_prompt_empty_text(self) -> None:
        """detect_prompt returns None for empty text."""
        result = detect_prompt("")
        assert result is None

    def test_no_prompt_yn_in_word(self) -> None:
        """detect_prompt returns None when y/n is part of a word."""
        result = detect_prompt("Syncing files...")
        assert result is None

    def test_no_prompt_checkbox_without_arrow(self) -> None:
        """detect_prompt returns None for checkbox-like text without arrow menu format."""
        result = detect_prompt("[x] Task completed")
        assert result is None


@pytest.mark.unit
class TestParseArrowMenu:
    """Tests for parse_arrow_menu function."""

    def test_parse_single_selected_checked_item(self) -> None:
        """parse_arrow_menu parses single selected checked item."""
        text = "> [x] Step 1: Initialize"
        items = parse_arrow_menu(text)
        assert len(items) == 1
        assert items[0].text == "Step 1: Initialize"
        assert items[0].checked is True
        assert items[0].selected is True

    def test_parse_single_unselected_unchecked_item(self) -> None:
        """parse_arrow_menu parses single unselected unchecked item."""
        text = "  [ ] Step 2: Configure"
        items = parse_arrow_menu(text)
        assert len(items) == 1
        assert items[0].text == "Step 2: Configure"
        assert items[0].checked is False
        assert items[0].selected is False

    def test_parse_multiple_items(self) -> None:
        """parse_arrow_menu parses multiple menu items."""
        text = """> [x] Step 1: Initialize
  [ ] Step 2: Configure
  [x] Step 3: Complete"""
        items = parse_arrow_menu(text)
        assert len(items) == 3

        assert items[0].text == "Step 1: Initialize"
        assert items[0].checked is True
        assert items[0].selected is True

        assert items[1].text == "Step 2: Configure"
        assert items[1].checked is False
        assert items[1].selected is False

        assert items[2].text == "Step 3: Complete"
        assert items[2].checked is True
        assert items[2].selected is False

    def test_parse_menu_with_header(self) -> None:
        """parse_arrow_menu ignores non-menu text."""
        text = """Choose a step to execute:

> [x] Phase 1: Setup
  [ ] Phase 2: Build
  [ ] Phase 3: Deploy

Press Enter to select."""
        items = parse_arrow_menu(text)
        assert len(items) == 3
        assert items[0].text == "Phase 1: Setup"
        assert items[1].text == "Phase 2: Build"
        assert items[2].text == "Phase 3: Deploy"

    def test_parse_menu_with_varying_whitespace(self) -> None:
        """parse_arrow_menu handles different leading whitespace."""
        text = """  > [x] Item 1
    [ ] Item 2
      [x] Item 3"""
        items = parse_arrow_menu(text)
        assert len(items) == 3

    def test_parse_menu_item_with_special_characters(self) -> None:
        """parse_arrow_menu handles items with special characters."""
        text = "> [x] Step 1: Initialize project (with --force)"
        items = parse_arrow_menu(text)
        assert len(items) == 1
        assert items[0].text == "Step 1: Initialize project (with --force)"

    def test_parse_menu_item_with_colon(self) -> None:
        """parse_arrow_menu handles items with colons."""
        text = "> [ ] config: Set up configuration files"
        items = parse_arrow_menu(text)
        assert len(items) == 1
        assert items[0].text == "config: Set up configuration files"

    def test_parse_empty_text(self) -> None:
        """parse_arrow_menu returns empty list for empty text."""
        items = parse_arrow_menu("")
        assert items == []

    def test_parse_no_menu_items(self) -> None:
        """parse_arrow_menu returns empty list when no menu items present."""
        text = "This is just regular output without any menu items."
        items = parse_arrow_menu(text)
        assert items == []

    def test_parse_returns_arrow_menu_items(self) -> None:
        """parse_arrow_menu returns ArrowMenuItem instances."""
        text = "> [x] Test item"
        items = parse_arrow_menu(text)
        assert len(items) == 1
        assert isinstance(items[0], ArrowMenuItem)

    def test_parse_strips_trailing_whitespace(self) -> None:
        """parse_arrow_menu strips trailing whitespace from item text."""
        text = "> [x] Item with trailing spaces   "
        items = parse_arrow_menu(text)
        assert items[0].text == "Item with trailing spaces"


@pytest.mark.asyncio
@pytest.mark.unit
class TestSendInput:
    """Tests for send_input function."""

    async def test_send_input_to_nonexistent_run(self) -> None:
        """send_input returns False when run doesn't exist."""
        result = await send_input(99999, "response")
        assert result is False

    async def test_send_input_to_terminated_process(self) -> None:
        """send_input returns False when process already terminated."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0  # Already exited
        mock_queue: asyncio.Queue[str] = asyncio.Queue()

        _active_runs[1] = (mock_proc, mock_queue)

        result = await send_input(1, "response")
        assert result is False

    async def test_send_input_to_active_process(self) -> None:
        """send_input queues input for active process."""
        mock_proc = MagicMock()
        mock_proc.returncode = None  # Still running
        input_queue: asyncio.Queue[str] = asyncio.Queue()

        _active_runs[1] = (mock_proc, input_queue)

        result = await send_input(1, "my response")
        assert result is True

        # Verify response was queued
        queued_response = await input_queue.get()
        assert queued_response == "my response"

    async def test_send_input_multiple_responses(self) -> None:
        """send_input can queue multiple responses."""
        mock_proc = MagicMock()
        mock_proc.returncode = None
        input_queue: asyncio.Queue[str] = asyncio.Queue()

        _active_runs[1] = (mock_proc, input_queue)

        await send_input(1, "first")
        await send_input(1, "second")
        await send_input(1, "third")

        assert await input_queue.get() == "first"
        assert await input_queue.get() == "second"
        assert await input_queue.get() == "third"


@pytest.mark.unit
class TestPromptInfo:
    """Tests for PromptInfo dataclass."""

    def test_prompt_info_creation(self) -> None:
        """PromptInfo can be created with all fields."""
        info = PromptInfo(
            text="Select [1/2]: ",
            options=["1", "2"],
            prompt_type="select",
        )
        assert info.text == "Select [1/2]: "
        assert info.options == ["1", "2"]
        assert info.prompt_type == "select"

    def test_prompt_info_equality(self) -> None:
        """PromptInfo instances are equal if all fields match."""
        info1 = PromptInfo(text="test", options=["a", "b"], prompt_type="yes_no")
        info2 = PromptInfo(text="test", options=["a", "b"], prompt_type="yes_no")
        assert info1 == info2

    def test_prompt_info_all_types(self) -> None:
        """PromptInfo accepts all valid prompt types."""
        for ptype in ["select", "yes_no", "confirm", "arrow_menu"]:
            info = PromptInfo(text="test", options=[], prompt_type=ptype)  # type: ignore[arg-type]
            assert info.prompt_type == ptype
