"""Tests for Telegram bot handlers and utilities."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from weld.telegram.bot import (
    _escape_markdown,
    _sanitize_command_args,
    cancel_command,
    commit_command,
    create_bot,
    create_prompt_keyboard,
    doctor_command,
    fetch_command,
    handle_prompt_callback,
    implement_command,
    interview_command,
    plan_command,
    push_command,
    run_consumer,
    status_command,
    use_command,
)
from weld.telegram.config import TelegramConfig, TelegramProject
from weld.telegram.state import Run, StateStore, UserContext


@pytest.fixture
def mock_message() -> MagicMock:
    """Create a mock Telegram message."""
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = 12345
    message.chat = MagicMock()
    message.chat.id = 67890
    message.message_id = 100
    message.answer = AsyncMock()
    return message


@pytest.fixture
def mock_command() -> MagicMock:
    """Create a mock CommandObject."""
    command = MagicMock()
    command.args = None
    return command


@pytest.fixture
async def state_store():
    """Create an in-memory state store for testing."""
    async with StateStore(":memory:") as store:
        yield store


@pytest.fixture
def telegram_config(tmp_path: Path) -> TelegramConfig:
    """Create a test Telegram config with projects."""
    project_path = tmp_path / "testproject"
    project_path.mkdir()
    return TelegramConfig(
        bot_token="123456:ABC",
        projects=[
            TelegramProject(
                name="testproject",
                path=project_path,
                description="Test project",
            )
        ],
    )


@pytest.fixture
def mock_queue_manager() -> MagicMock:
    """Create a mock QueueManager."""
    manager = MagicMock()
    manager.enqueue = AsyncMock(return_value=1)
    manager.queue_size = MagicMock(return_value=0)
    manager.cancel_pending = AsyncMock(return_value=0)
    return manager


@pytest.fixture
def mock_bot() -> AsyncMock:
    """Create a mock Bot."""
    bot = AsyncMock()
    bot.send_message = AsyncMock(return_value=MagicMock(message_id=100))
    bot.send_document = AsyncMock()
    bot.get_file = AsyncMock()
    bot.download_file = AsyncMock()
    bot.edit_message_text = AsyncMock()
    return bot


@pytest.mark.unit
class TestCreatePromptKeyboard:
    """Tests for create_prompt_keyboard function."""

    def test_creates_keyboard_with_options(self) -> None:
        """Creates keyboard with provided options."""
        keyboard = create_prompt_keyboard(42, ["1", "2", "3"])
        assert keyboard.inline_keyboard is not None
        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 3

    def test_buttons_have_correct_callback_data(self) -> None:
        """Buttons have correct callback_data format."""
        keyboard = create_prompt_keyboard(42, ["1", "2"])
        buttons = keyboard.inline_keyboard[0]
        assert buttons[0].callback_data == "prompt:42:1"
        assert buttons[1].callback_data == "prompt:42:2"

    def test_known_options_have_labels(self) -> None:
        """Known options (1, 2, 3) have human-readable labels."""
        keyboard = create_prompt_keyboard(1, ["1", "2", "3"])
        buttons = keyboard.inline_keyboard[0]
        assert "Attribute to session" in buttons[0].text
        assert "Separate commit" in buttons[1].text
        assert "Cancel" in buttons[2].text

    def test_unknown_options_use_value_as_label(self) -> None:
        """Unknown options use the option value as label."""
        keyboard = create_prompt_keyboard(1, ["a", "b"])
        buttons = keyboard.inline_keyboard[0]
        assert buttons[0].text == "a"
        assert buttons[1].text == "b"

    def test_empty_options_creates_empty_row(self) -> None:
        """Empty options list creates keyboard with empty row."""
        keyboard = create_prompt_keyboard(1, [])
        assert keyboard.inline_keyboard == [[]]


@pytest.mark.asyncio
@pytest.mark.unit
class TestHandlePromptCallback:
    """Tests for handle_prompt_callback function."""

    async def test_ignores_non_prompt_callback(self) -> None:
        """Ignores callbacks that don't start with 'prompt:'."""
        callback = MagicMock()
        callback.data = "other:data"
        callback.answer = AsyncMock()

        await handle_prompt_callback(callback)

        callback.answer.assert_not_called()

    async def test_ignores_empty_data(self) -> None:
        """Ignores callbacks with empty data."""
        callback = MagicMock()
        callback.data = None
        callback.answer = AsyncMock()

        await handle_prompt_callback(callback)

        callback.answer.assert_not_called()

    async def test_ignores_invalid_format(self) -> None:
        """Ignores callbacks with invalid format (wrong number of parts)."""
        callback = MagicMock()
        callback.data = "prompt:only_two"
        callback.answer = AsyncMock()

        await handle_prompt_callback(callback)

        callback.answer.assert_not_called()

    async def test_ignores_invalid_run_id(self) -> None:
        """Ignores callbacks with non-numeric run_id."""
        callback = MagicMock()
        callback.data = "prompt:notanumber:1"
        callback.answer = AsyncMock()

        await handle_prompt_callback(callback)

        callback.answer.assert_not_called()

    async def test_sends_input_and_acknowledges(self) -> None:
        """Sends input to process and acknowledges callback."""
        callback = MagicMock()
        callback.data = "prompt:42:2"
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.edit_text = AsyncMock()

        with patch("weld.telegram.bot.send_input", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = True
            await handle_prompt_callback(callback)

            mock_send.assert_called_once_with(42, "2")
            callback.answer.assert_called_once()
            assert "Selected option 2" in str(callback.answer.call_args)

    async def test_shows_alert_when_command_not_running(self) -> None:
        """Shows alert when command is no longer running."""
        callback = MagicMock()
        callback.data = "prompt:42:1"
        callback.answer = AsyncMock()

        with patch("weld.telegram.bot.send_input", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = False
            await handle_prompt_callback(callback)

            callback.answer.assert_called_once()
            assert callback.answer.call_args[1].get("show_alert") is True


@pytest.mark.unit
class TestEscapeMarkdown:
    """Tests for _escape_markdown function."""

    def test_escapes_asterisk(self) -> None:
        """Escapes asterisk character."""
        assert _escape_markdown("*bold*") == "\\*bold\\*"

    def test_escapes_underscore(self) -> None:
        """Escapes underscore character."""
        assert _escape_markdown("_italic_") == "\\_italic\\_"

    def test_escapes_backtick(self) -> None:
        """Escapes backtick character."""
        assert _escape_markdown("`code`") == "\\`code\\`"

    def test_escapes_bracket(self) -> None:
        """Escapes square bracket character."""
        assert _escape_markdown("[link]") == "\\[link]"

    def test_escapes_multiple_chars(self) -> None:
        """Escapes multiple special characters in same string."""
        text = "*bold* and _italic_ and `code`"
        escaped = _escape_markdown(text)
        assert "\\*" in escaped
        assert "\\_" in escaped
        assert "\\`" in escaped

    def test_plain_text_unchanged(self) -> None:
        """Plain text without special chars is unchanged."""
        text = "Hello world"
        assert _escape_markdown(text) == text

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert _escape_markdown("") == ""


@pytest.mark.unit
class TestCreateBot:
    """Tests for create_bot function."""

    def test_creates_bot_with_valid_token(self) -> None:
        """Creates bot and dispatcher with valid token."""
        bot, dp = create_bot("123456:ABCdef")
        assert bot is not None
        assert dp is not None

    def test_raises_on_empty_token(self) -> None:
        """Raises ValueError on empty token."""
        with pytest.raises(ValueError, match="cannot be empty"):
            create_bot("")

    def test_raises_on_whitespace_token(self) -> None:
        """Raises ValueError on whitespace-only token."""
        with pytest.raises(ValueError, match="cannot be empty"):
            create_bot("   ")

    def test_raises_on_missing_colon(self) -> None:
        """Raises ValueError when token has no colon."""
        with pytest.raises(ValueError, match="missing colon"):
            create_bot("123456ABCdef")  # pragma: allowlist secret

    def test_raises_on_non_numeric_id(self) -> None:
        """Raises ValueError when bot ID is not numeric."""
        with pytest.raises(ValueError, match="must be numeric"):
            create_bot("abc:DEFghi")

    def test_raises_on_missing_hash(self) -> None:
        """Raises ValueError when token hash is empty."""
        with pytest.raises(ValueError, match="missing token hash"):
            create_bot("123456:")

    def test_strips_whitespace_from_token(self) -> None:
        """Strips leading/trailing whitespace from token."""
        bot, _ = create_bot("  123456:ABCdef  ")
        assert bot is not None


@pytest.mark.unit
class TestSanitizeCommandArgs:
    """Tests for _sanitize_command_args function."""

    def test_empty_string_returns_empty(self) -> None:
        """Empty string returns empty string."""
        assert _sanitize_command_args("") == ""

    def test_none_handled(self) -> None:
        """None-like empty values handled."""
        assert _sanitize_command_args("   ") == ""

    def test_removes_null_bytes(self) -> None:
        """Removes null bytes from args."""
        assert _sanitize_command_args("hello\0world") == "helloworld"

    def test_normalizes_em_dash_to_double_hyphen(self) -> None:
        """Normalizes em-dash (—) to double hyphen (--)."""
        assert _sanitize_command_args("—option") == "--option"

    def test_normalizes_en_dash_to_double_hyphen(self) -> None:
        """Normalizes en-dash to double hyphen (--)."""
        assert _sanitize_command_args("\u2013option") == "--option"

    def test_removes_semicolon(self) -> None:
        """Removes semicolon to prevent command chaining."""
        assert _sanitize_command_args("arg1; rm -rf") == "arg1 rm -rf"

    def test_removes_ampersand(self) -> None:
        """Removes ampersand to prevent background execution."""
        assert _sanitize_command_args("arg1 && arg2") == "arg1  arg2"

    def test_removes_pipe(self) -> None:
        """Removes pipe to prevent command piping."""
        assert _sanitize_command_args("arg1 | arg2") == "arg1  arg2"

    def test_removes_dollar(self) -> None:
        """Removes dollar sign to prevent variable expansion."""
        assert _sanitize_command_args("$HOME") == "HOME"

    def test_removes_backtick(self) -> None:
        """Removes backtick to prevent command substitution."""
        assert _sanitize_command_args("`whoami`") == "whoami"

    def test_removes_parentheses(self) -> None:
        """Removes parentheses to prevent subshell."""
        assert _sanitize_command_args("(echo hi)") == "echo hi"

    def test_removes_braces(self) -> None:
        """Removes braces to prevent brace expansion."""
        assert _sanitize_command_args("{a,b}") == "a,b"

    def test_removes_redirects(self) -> None:
        """Removes redirect characters."""
        # Note: result is stripped, so leading space is removed
        assert _sanitize_command_args("> file") == "file"
        assert _sanitize_command_args("< input") == "input"
        assert _sanitize_command_args("echo > file") == "echo  file"

    def test_removes_newlines(self) -> None:
        """Removes newlines to prevent multi-line injection."""
        assert _sanitize_command_args("arg1\narg2") == "arg1arg2"
        assert _sanitize_command_args("arg1\rarg2") == "arg1arg2"

    def test_preserves_safe_characters(self) -> None:
        """Preserves alphanumeric, space, dash, underscore, dot, slash."""
        safe_args = "my-file_name.md /path/to/file"
        assert _sanitize_command_args(safe_args) == safe_args

    def test_preserves_quotes(self) -> None:
        """Preserves quote characters."""
        assert _sanitize_command_args('"quoted"') == '"quoted"'
        assert _sanitize_command_args("'single'") == "'single'"

    def test_strips_result(self) -> None:
        """Strips leading/trailing whitespace from result."""
        assert _sanitize_command_args("  args  ") == "args"


@pytest.mark.asyncio
@pytest.mark.unit
class TestUseCommand:
    """Tests for use_command function."""

    async def test_shows_no_project_when_none_selected(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows available projects when no project selected."""
        mock_command.args = None

        await use_command(mock_message, mock_command, state_store, telegram_config)

        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "No project selected" in response
        assert "testproject" in response

    async def test_shows_current_project(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows current project when one is selected."""
        mock_command.args = None

        # Set up existing context
        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        await use_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Current project" in response
        assert "testproject" in response

    async def test_switches_to_valid_project(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Switches to specified valid project."""
        mock_command.args = "testproject"

        await use_command(mock_message, mock_command, state_store, telegram_config)

        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "Switched to project" in response
        assert "testproject" in response

        # Verify context was updated
        context = await state_store.get_context(12345)
        assert context is not None
        assert context.current_project == "testproject"

    async def test_rejects_unknown_project(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Rejects switch to unknown project."""
        mock_command.args = "nonexistent"

        await use_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Unknown project" in response
        assert "nonexistent" in response

    async def test_blocks_switch_during_run(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Blocks project switch while command is running."""
        mock_command.args = "testproject"

        # Set up running context
        context = UserContext(user_id=12345, current_project="other", conversation_state="running")
        await state_store.upsert_context(context)

        await use_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Cannot switch" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None

        await use_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_shows_message_when_no_projects_configured(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Shows helpful message when no projects are configured."""
        mock_command.args = None
        empty_config = TelegramConfig(bot_token="123:ABC", projects=[])

        await use_command(mock_message, mock_command, state_store, empty_config)

        response = mock_message.answer.call_args[0][0]
        assert "No projects configured" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestStatusCommand:
    """Tests for status_command function."""

    async def test_shows_no_project_when_none_selected(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows 'None selected' when no project context."""
        await status_command(mock_message, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "None selected" in response

    async def test_shows_current_project(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows current project in status."""
        context = UserContext(user_id=12345, current_project="myproject")
        await state_store.upsert_context(context)

        await status_command(mock_message, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "myproject" in response

    async def test_shows_running_command(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows currently running command."""
        run = Run(
            user_id=12345,
            project_name="myproject",
            command="weld doctor",
            status="running",
        )
        await state_store.create_run(run)

        await status_command(mock_message, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "weld doctor" in response
        assert "running" in response

    async def test_shows_queue_size(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows queue size when items pending."""
        mock_queue_manager.queue_size.return_value = 3

        await status_command(mock_message, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "3 pending" in response

    async def test_shows_empty_queue(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows empty queue message when nothing pending."""
        mock_queue_manager.queue_size.return_value = 0

        await status_command(mock_message, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Empty" in response

    async def test_shows_recent_completed_runs(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows recent completed/failed runs in history."""
        run = Run(
            user_id=12345,
            project_name="myproject",
            command="weld plan",
            status="completed",
        )
        await state_store.create_run(run)

        await status_command(mock_message, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Recent" in response
        assert "weld plan" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None

        await status_command(mock_message, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestCancelCommand:
    """Tests for cancel_command function."""

    async def test_nothing_to_cancel(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows message when nothing to cancel."""
        await cancel_command(mock_message, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Nothing to cancel" in response

    async def test_cancels_active_run(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Cancels active running command."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld plan",
            status="running",
        )
        run_id = await state_store.create_run(run)

        await cancel_command(mock_message, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Cancelled active run" in response

        # Verify run status updated
        updated_run = await state_store.get_run(run_id)
        assert updated_run is not None
        assert updated_run.status == "cancelled"

    async def test_clears_pending_queue(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Clears pending items from queue."""
        mock_queue_manager.cancel_pending.return_value = 5

        # Create pending runs
        for i in range(5):
            run = Run(
                user_id=12345,
                project_name="proj",
                command=f"weld cmd{i}",
                status="pending",
            )
            await state_store.create_run(run)

        await cancel_command(mock_message, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "cleared" in response
        assert "5" in response or "pending" in response

    async def test_resets_user_context_to_idle(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Resets user context state to idle after cancel."""
        context = UserContext(
            user_id=12345,
            current_project="proj",
            conversation_state="running",
        )
        await state_store.upsert_context(context)

        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld plan",
            status="running",
        )
        await state_store.create_run(run)

        await cancel_command(mock_message, state_store, mock_queue_manager)

        updated_context = await state_store.get_context(12345)
        assert updated_context is not None
        assert updated_context.conversation_state == "idle"

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None

        await cancel_command(mock_message, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestEnqueueWeldCommand:
    """Tests for weld command enqueueing (via doctor_command as example)."""

    async def test_requires_project_context(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Requires project to be selected before running command."""
        mock_command.args = None

        await doctor_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "No project selected" in response

    async def test_enqueues_command_successfully(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Enqueues command when project is selected."""
        mock_command.args = None

        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await doctor_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Queued" in response
        assert "weld doctor" in response

    async def test_shows_queue_position(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows position when not first in queue."""
        mock_command.args = None
        mock_queue_manager.enqueue.return_value = 3

        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await doctor_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "3 in queue" in response

    async def test_shows_next_up_when_first(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows 'next up' when first in queue."""
        mock_command.args = None
        mock_queue_manager.enqueue.return_value = 1

        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await doctor_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "next up" in response

    async def test_sanitizes_command_args(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Sanitizes command arguments."""
        mock_command.args = "file.md; rm -rf /"

        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await plan_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        # Semicolon should be removed
        assert ";" not in response
        assert "file.md" in response

    async def test_handles_enqueue_failure(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Handles queue failure gracefully."""
        mock_command.args = None
        mock_queue_manager.enqueue.side_effect = Exception("Queue error")

        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await doctor_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Failed to queue" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestWeldCommandHandlers:
    """Tests for specific weld command handlers."""

    async def test_plan_command_enqueues(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """plan_command enqueues weld plan."""
        mock_command.args = "spec.md"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await plan_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "weld plan" in response
        assert "spec.md" in response

    async def test_interview_command_enqueues(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """interview_command enqueues weld interview."""
        mock_command.args = None
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await interview_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "weld interview" in response

    async def test_implement_command_enqueues(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """implement_command enqueues weld implement."""
        mock_command.args = "plan.md --phase 1"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await implement_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "weld implement" in response
        assert "plan.md" in response

    async def test_commit_command_enqueues(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """commit_command enqueues weld commit."""
        mock_command.args = "-m 'test commit'"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await commit_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "weld commit" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestFetchCommand:
    """Tests for fetch_command function."""

    async def test_requires_path_argument(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Shows usage when no path provided."""
        mock_command.args = ""

        await fetch_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "Usage" in response
        assert "/fetch" in response

    async def test_rejects_path_not_found(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Rejects non-existent file path."""
        mock_command.args = "/nonexistent/file.txt"

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            from weld.telegram.files import PathNotFoundError

            mock_validate.side_effect = PathNotFoundError("file.txt")
            await fetch_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "not found" in response

    async def test_rejects_path_outside_project(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Rejects path outside registered projects."""
        mock_command.args = "/etc/passwd"

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            from weld.telegram.files import PathNotAllowedError

            mock_validate.side_effect = PathNotAllowedError("/etc/passwd")
            await fetch_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "denied" in response

    async def test_rejects_directory_fetch(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Rejects fetching directories."""
        mock_command.args = str(tmp_path)

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = tmp_path
            await fetch_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "Cannot fetch directories" in response

    async def test_sends_file_via_telegram(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Sends file via Telegram when within size limit."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, world!")
        mock_command.args = str(test_file)

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = test_file
            await fetch_command(mock_message, mock_command, telegram_config, mock_bot)

        mock_bot.send_document.assert_called_once()

    async def test_falls_back_to_gist_for_large_files(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Falls back to gist for files larger than 50MB."""
        mock_command.args = "/path/to/large.txt"

        # Create a mock path object that reports large file size
        mock_path = MagicMock()
        mock_path.is_dir.return_value = False
        mock_stat_result = MagicMock()
        mock_stat_result.st_size = 100 * 1024 * 1024  # 100MB
        mock_path.stat.return_value = mock_stat_result

        with (
            patch("weld.telegram.bot.validate_fetch_path") as mock_validate,
            patch("weld.telegram.bot._fetch_via_gist", new_callable=AsyncMock) as mock_gist,
        ):
            mock_validate.return_value = mock_path

            await fetch_command(mock_message, mock_command, telegram_config, mock_bot)

            mock_gist.assert_called_once()

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = "file.txt"

        await fetch_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestPushCommand:
    """Tests for push_command function."""

    async def test_requires_reply_to_message(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Requires command to be reply to a message."""
        mock_command.args = "dest.txt"
        mock_message.reply_to_message = None

        await push_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "Reply to a document" in response

    async def test_requires_document_in_reply(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Requires replied message to contain a document."""
        mock_command.args = "dest.txt"
        mock_message.reply_to_message = MagicMock()
        mock_message.reply_to_message.document = None

        await push_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "does not contain a document" in response

    async def test_requires_path_argument(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Shows usage when no path provided."""
        mock_command.args = ""
        mock_message.reply_to_message = MagicMock()
        mock_message.reply_to_message.document = MagicMock()
        mock_message.reply_to_message.document.file_name = "original.txt"

        await push_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "Usage" in response
        assert "/push" in response

    async def test_rejects_path_outside_project(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Rejects path outside registered projects."""
        mock_command.args = "/etc/passwd"
        mock_message.reply_to_message = MagicMock()
        mock_message.reply_to_message.document = MagicMock()

        with patch("weld.telegram.bot.validate_push_path") as mock_validate:
            from weld.telegram.files import PathNotAllowedError

            mock_validate.side_effect = PathNotAllowedError("/etc/passwd")
            await push_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "denied" in response

    async def test_rejects_oversized_files(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Rejects files larger than 50MB."""
        mock_command.args = str(tmp_path / "dest.txt")
        mock_message.reply_to_message = MagicMock()
        mock_message.reply_to_message.document = MagicMock()
        mock_message.reply_to_message.document.file_size = 100 * 1024 * 1024  # 100MB

        with patch("weld.telegram.bot.validate_push_path") as mock_validate:
            mock_validate.return_value = tmp_path / "dest.txt"
            await push_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "too large" in response

    async def test_downloads_and_saves_file(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Downloads file and saves to destination."""
        dest_path = tmp_path / "dest.txt"
        mock_command.args = str(dest_path)
        mock_message.reply_to_message = MagicMock()
        mock_message.reply_to_message.document = MagicMock()
        mock_message.reply_to_message.document.file_size = 100
        mock_message.reply_to_message.document.file_id = "file123"

        # Mock file download
        mock_file = MagicMock()
        mock_file.file_path = "/path/to/file"
        mock_bot.get_file.return_value = mock_file

        mock_file_content = MagicMock()
        mock_file_content.read.return_value = b"File content"
        mock_bot.download_file.return_value = mock_file_content

        with patch("weld.telegram.bot.validate_push_path") as mock_validate:
            mock_validate.return_value = dest_path
            await push_command(mock_message, mock_command, telegram_config, mock_bot)

        assert dest_path.exists()
        assert dest_path.read_bytes() == b"File content"

        response = mock_message.answer.call_args[0][0]
        assert "Saved to" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = "file.txt"

        await push_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestRunConsumer:
    """Tests for run_consumer function."""

    async def test_rejects_run_without_id(
        self,
        state_store: StateStore,
        mock_bot: AsyncMock,
    ) -> None:
        """Rejects run that has no id set."""
        run = Run(user_id=1, project_name="proj", command="weld doctor")
        # run.id is None

        from weld.telegram.format import MessageEditor

        editor = MessageEditor(mock_bot)

        await run_consumer(run, 12345, editor, Path("/tmp"), state_store, mock_bot)

        # Should return early without doing anything
        mock_bot.send_message.assert_not_called()

    async def test_marks_run_as_running(
        self,
        state_store: StateStore,
        mock_bot: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Marks run as running and sends initial status."""
        run = Run(user_id=1, project_name="proj", command="weld doctor")
        run_id = await state_store.create_run(run)
        run.id = run_id

        from weld.telegram.format import MessageEditor

        editor = MessageEditor(mock_bot)

        with patch("weld.telegram.bot.execute_run") as mock_execute:
            # Empty generator that completes immediately
            async def empty_gen():
                return
                yield  # type: ignore

            mock_execute.return_value = empty_gen()
            await run_consumer(run, 12345, editor, tmp_path, state_store, mock_bot)

        # Verify run was marked as running then completed
        updated_run = await state_store.get_run(run_id)
        assert updated_run is not None
        assert updated_run.status == "completed"

    async def test_handles_invalid_command_format(
        self,
        state_store: StateStore,
        mock_bot: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Handles invalid command format (not starting with 'weld')."""
        run = Run(user_id=1, project_name="proj", command="invalid command")
        run_id = await state_store.create_run(run)
        run.id = run_id

        from weld.telegram.format import MessageEditor

        editor = MessageEditor(mock_bot)

        await run_consumer(run, 12345, editor, tmp_path, state_store, mock_bot)

        updated_run = await state_store.get_run(run_id)
        assert updated_run is not None
        assert updated_run.status == "failed"
        assert "Invalid command format" in (updated_run.error or "")

    async def test_accumulates_output(
        self,
        state_store: StateStore,
        mock_bot: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Accumulates stdout/stderr output."""
        run = Run(user_id=1, project_name="proj", command="weld doctor")
        run_id = await state_store.create_run(run)
        run.id = run_id

        from weld.telegram.format import MessageEditor

        editor = MessageEditor(mock_bot)

        with patch("weld.telegram.bot.execute_run") as mock_execute:

            async def gen_with_output():
                yield ("stdout", "Hello ")
                yield ("stdout", "World!")

            mock_execute.return_value = gen_with_output()
            await run_consumer(run, 12345, editor, tmp_path, state_store, mock_bot)

        updated_run = await state_store.get_run(run_id)
        assert updated_run is not None
        assert updated_run.result is not None
        assert "Hello" in updated_run.result
        assert "World" in updated_run.result

    async def test_handles_execution_error(
        self,
        state_store: StateStore,
        mock_bot: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Marks run as failed when execution raises error."""
        run = Run(user_id=1, project_name="proj", command="weld doctor")
        run_id = await state_store.create_run(run)
        run.id = run_id

        from weld.telegram.format import MessageEditor

        editor = MessageEditor(mock_bot)

        with patch("weld.telegram.bot.execute_run") as mock_execute:

            async def gen_with_error():
                yield ("stdout", "Starting...")
                raise RuntimeError("Command failed")

            mock_execute.return_value = gen_with_error()
            await run_consumer(run, 12345, editor, tmp_path, state_store, mock_bot)

        updated_run = await state_store.get_run(run_id)
        assert updated_run is not None
        assert updated_run.status == "failed"
        assert "Command failed" in (updated_run.error or "")

    async def test_shows_prompt_with_keyboard(
        self,
        state_store: StateStore,
        mock_bot: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Shows interactive prompt with keyboard when detected."""
        run = Run(user_id=1, project_name="proj", command="weld commit")
        run_id = await state_store.create_run(run)
        run.id = run_id

        from weld.telegram.format import MessageEditor

        editor = MessageEditor(mock_bot)

        with (
            patch("weld.telegram.bot.execute_run") as mock_execute,
            patch("weld.telegram.bot.detect_prompt") as mock_detect,
        ):
            mock_detect.return_value = MagicMock(options=["1", "2", "3"])

            async def gen_with_prompt():
                yield ("prompt", "Select an option:\n1. Option A\n2. Option B")

            mock_execute.return_value = gen_with_prompt()
            await run_consumer(run, 12345, editor, tmp_path, state_store, mock_bot)

        # Should have sent a message with keyboard
        calls = mock_bot.send_message.call_args_list
        # Look for a call with reply_markup (the keyboard)
        keyboard_calls = [c for c in calls if c.kwargs.get("reply_markup") is not None]
        assert len(keyboard_calls) >= 1

    async def test_truncates_large_output(
        self,
        state_store: StateStore,
        mock_bot: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Truncates output buffer when it exceeds max size."""
        run = Run(user_id=1, project_name="proj", command="weld doctor")
        run_id = await state_store.create_run(run)
        run.id = run_id

        from weld.telegram.format import MessageEditor

        editor = MessageEditor(mock_bot)

        # Generate output larger than MAX_OUTPUT_BUFFER (3000)
        large_output = "x" * 5000

        with patch("weld.telegram.bot.execute_run") as mock_execute:

            async def gen_large_output():
                yield ("stdout", large_output)

            mock_execute.return_value = gen_large_output()
            await run_consumer(run, 12345, editor, tmp_path, state_store, mock_bot)

        updated_run = await state_store.get_run(run_id)
        assert updated_run is not None
        assert updated_run.result is not None
        # Result should be truncated
        assert len(updated_run.result) < 5000
        assert "..." in updated_run.result
