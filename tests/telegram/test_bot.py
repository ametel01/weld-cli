"""Tests for Telegram bot handlers and utilities."""

import asyncio
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from weld.telegram.bot import (
    FILE_COMMAND_MAX_SIZE,
    PaginationState,
    _active_tails,
    _create_cat_pagination_keyboard,
    _escape_markdown,
    _sanitize_command_args,
    cancel_command,
    cat_command,
    commit_command,
    create_bot,
    create_download_keyboard,
    create_prompt_keyboard,
    detect_output_files,
    doctor_command,
    fetch_command,
    file_command,
    find_command,
    get_pagination_state,
    grep_command,
    handle_cat_pagination_callback,
    handle_fetch_callback,
    handle_prompt_callback,
    head_command,
    implement_command,
    interview_command,
    logs_command,
    ls_command,
    plan_command,
    push_command,
    remove_pagination_state,
    run_consumer,
    runs_command,
    set_pagination_state,
    status_command,
    tail_command,
    tree_command,
    use_command,
    weld_command,
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
def git_project_config(tmp_path: Path) -> TelegramConfig:
    """Create a test Telegram config with a git repository project.

    This fixture creates a proper git repo with:
    - Initial commit
    - .gitignore file that ignores node_modules/ and *.log files
    - Sample source files
    """
    import subprocess

    project_path = tmp_path / "gitproject"
    project_path.mkdir()

    # Initialize git repo
    subprocess.run(
        ["git", "init"],
        cwd=project_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=project_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=project_path,
        capture_output=True,
        check=True,
    )

    # Create .gitignore
    gitignore = project_path / ".gitignore"
    gitignore.write_text("node_modules/\n*.log\nbuild/\n")

    # Create source files
    src_dir = project_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("# Main module\ndef main():\n    print('Hello')\n")
    (src_dir / "utils.py").write_text("# Utils\ndef helper():\n    return 42\n")

    # Create test files
    tests_dir = project_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text("# Tests\ndef test_main():\n    assert True\n")

    # Create files that should be ignored
    node_modules = project_path / "node_modules"
    node_modules.mkdir()
    (node_modules / "package.json").write_text("{}")

    (project_path / "debug.log").write_text("debug output")

    # Create README
    (project_path / "README.md").write_text("# Project\n\nDescription here.\n")

    # Stage and commit tracked files
    subprocess.run(
        ["git", "add", ".gitignore", "src/", "tests/", "README.md"],
        cwd=project_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=project_path,
        capture_output=True,
        check=True,
    )

    return TelegramConfig(
        bot_token="123456:ABC",
        projects=[
            TelegramProject(
                name="gitproject",
                path=project_path,
                description="Git test project",
            )
        ],
    )


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

    def test_creates_keyboard_with_select_options(self) -> None:
        """Creates keyboard with provided select options."""
        keyboard = create_prompt_keyboard(42, ["1", "2", "3"], "select")
        assert keyboard.inline_keyboard is not None
        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 3

    def test_buttons_have_correct_callback_data(self) -> None:
        """Buttons have correct callback_data format."""
        keyboard = create_prompt_keyboard(42, ["1", "2"], "select")
        buttons = keyboard.inline_keyboard[0]
        assert buttons[0].callback_data == "prompt:42:1"
        assert buttons[1].callback_data == "prompt:42:2"

    def test_select_options_use_value_as_label(self) -> None:
        """Select options use the option value as label."""
        keyboard = create_prompt_keyboard(1, ["1", "2", "3"], "select")
        buttons = keyboard.inline_keyboard[0]
        assert buttons[0].text == "1"
        assert buttons[1].text == "2"
        assert buttons[2].text == "3"

    def test_yes_no_creates_two_buttons(self) -> None:
        """yes_no prompt type creates Yes/No buttons."""
        keyboard = create_prompt_keyboard(1, ["y", "n"], "yes_no")
        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 2
        buttons = keyboard.inline_keyboard[0]
        assert "Yes" in buttons[0].text
        assert "No" in buttons[1].text
        assert buttons[0].callback_data == "prompt:1:y"
        assert buttons[1].callback_data == "prompt:1:n"

    def test_confirm_creates_yes_no_buttons(self) -> None:
        """confirm prompt type creates Yes/No buttons."""
        keyboard = create_prompt_keyboard(1, ["y", "n"], "confirm")
        assert len(keyboard.inline_keyboard) == 1
        buttons = keyboard.inline_keyboard[0]
        assert "Yes" in buttons[0].text
        assert "No" in buttons[1].text

    def test_arrow_menu_extracts_items(self) -> None:
        """arrow_menu parses menu items from prompt text."""
        prompt_text = """> [x] Step 1: Initialize
  [ ] Step 2: Configure
  [x] Step 3: Complete"""
        keyboard = create_prompt_keyboard(1, [], "arrow_menu", prompt_text=prompt_text)
        # 3 menu items + 1 cancel button = 4 rows
        assert len(keyboard.inline_keyboard) == 4
        # Check first item (selected and checked)
        assert "Step 1: Initialize" in keyboard.inline_keyboard[0][0].text
        assert "▶" in keyboard.inline_keyboard[0][0].text  # selected indicator
        assert "☑" in keyboard.inline_keyboard[0][0].text  # checked indicator
        # Check second item (unchecked)
        assert "Step 2: Configure" in keyboard.inline_keyboard[1][0].text
        assert "☐" in keyboard.inline_keyboard[1][0].text  # unchecked indicator
        # Check callback data uses 1-indexed positions
        assert keyboard.inline_keyboard[0][0].callback_data == "prompt:1:1"
        assert keyboard.inline_keyboard[1][0].callback_data == "prompt:1:2"
        # Check cancel button
        assert "Cancel" in keyboard.inline_keyboard[3][0].text
        assert keyboard.inline_keyboard[3][0].callback_data == "prompt:1:q"

    def test_arrow_menu_fallback_with_no_items(self) -> None:
        """arrow_menu shows navigation buttons if no items parsed."""
        keyboard = create_prompt_keyboard(1, [], "arrow_menu", prompt_text="")
        # Should have 2 rows: navigation and action buttons
        assert len(keyboard.inline_keyboard) == 2
        # Navigation row
        assert "Up" in keyboard.inline_keyboard[0][0].text
        assert "Down" in keyboard.inline_keyboard[0][1].text
        # Action row
        assert "Select" in keyboard.inline_keyboard[1][0].text
        assert "Quit" in keyboard.inline_keyboard[1][1].text

    def test_empty_options_creates_empty_row(self) -> None:
        """Empty options list creates keyboard with empty row for select type."""
        keyboard = create_prompt_keyboard(1, [], "select")
        assert keyboard.inline_keyboard == [[]]

    def test_arrow_menu_truncates_long_labels(self) -> None:
        """arrow_menu truncates labels longer than 40 characters."""
        prompt_text = "> [x] This is a very long menu item text that exceeds forty characters limit"
        keyboard = create_prompt_keyboard(1, [], "arrow_menu", prompt_text=prompt_text)
        # First item + cancel button = 2 rows
        assert len(keyboard.inline_keyboard) == 2
        label = keyboard.inline_keyboard[0][0].text
        # Should be truncated with ...
        assert "..." in label
        # Should still include checkbox prefix
        assert "☑" in label


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
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows 'None selected' when no project context."""
        mock_command.args = ""
        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "None selected" in response

    async def test_shows_current_project(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows current project in status."""
        mock_command.args = ""
        context = UserContext(user_id=12345, current_project="myproject")
        await state_store.upsert_context(context)

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "myproject" in response

    async def test_shows_running_command(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows currently running command."""
        mock_command.args = ""
        run = Run(
            user_id=12345,
            project_name="myproject",
            command="weld doctor",
            status="running",
        )
        await state_store.create_run(run)

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "weld doctor" in response
        assert "running" in response

    async def test_shows_queue_size(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows queue size when items pending."""
        mock_command.args = ""
        mock_queue_manager.queue_size.return_value = 3

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "3 pending" in response

    async def test_shows_empty_queue(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows empty queue message when nothing pending."""
        mock_command.args = ""
        mock_queue_manager.queue_size.return_value = 0

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Empty" in response

    async def test_shows_recent_completed_runs(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows recent completed/failed runs in history."""
        mock_command.args = ""
        run = Run(
            user_id=12345,
            project_name="myproject",
            command="weld plan",
            status="completed",
        )
        await state_store.create_run(run)

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Recent" in response
        assert "weld plan" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Handles message with no from_user."""
        mock_command.args = ""
        mock_message.from_user = None

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

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
        telegram_config: TelegramConfig,
    ) -> None:
        """Requires project to be selected before running command."""
        mock_command.args = None

        await doctor_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "No project selected" in response

    async def test_enqueues_command_successfully(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Enqueues command when project is selected."""
        mock_command.args = None

        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await doctor_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "Queued" in response
        assert "weld doctor" in response

    async def test_shows_queue_position(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows position when not first in queue."""
        mock_command.args = None
        mock_queue_manager.enqueue.return_value = 3

        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await doctor_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "3 in queue" in response

    async def test_shows_next_up_when_first(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows 'next up' when first in queue."""
        mock_command.args = None
        mock_queue_manager.enqueue.return_value = 1

        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await doctor_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "next up" in response

    async def test_sanitizes_command_args(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Sanitizes command arguments."""
        mock_command.args = "file.md; rm -rf /"

        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await plan_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

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
        telegram_config: TelegramConfig,
    ) -> None:
        """Handles queue failure gracefully."""
        mock_command.args = None
        mock_queue_manager.enqueue.side_effect = Exception("Queue error")

        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await doctor_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

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
        telegram_config: TelegramConfig,
    ) -> None:
        """plan_command enqueues weld plan."""
        mock_command.args = "spec.md"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await plan_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "weld plan" in response
        assert "spec.md" in response

    async def test_interview_command_enqueues(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """interview_command enqueues weld interview."""
        mock_command.args = None
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await interview_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "weld interview" in response

    async def test_implement_command_enqueues(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """implement_command enqueues weld implement."""
        mock_command.args = "plan.md --phase 1"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await implement_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "weld implement" in response
        assert "plan.md" in response

    async def test_commit_command_enqueues(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """commit_command enqueues weld commit."""
        mock_command.args = "-m 'test commit'"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await commit_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "weld commit" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestWeldCommand:
    """Tests for weld_command function (generic /weld handler)."""

    async def test_shows_usage_when_no_args(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows usage help when no subcommand provided."""
        mock_command.args = ""

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "Usage" in response
        assert "/weld <subcommand>" in response

    async def test_shows_usage_when_whitespace_only(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows usage when args is whitespace only."""
        mock_command.args = "   "

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "Usage" in response

    async def test_requires_project_context(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Requires project to be selected before running."""
        mock_command.args = "research spec.md"

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "No project selected" in response

    async def test_enqueues_subcommand_with_args(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Enqueues weld command with subcommand and arguments."""
        mock_command.args = "research spec.md"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "weld research" in response
        assert "spec.md" in response
        assert "Queued" in response

    async def test_enqueues_subcommand_without_args(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Enqueues weld command with subcommand only."""
        mock_command.args = "discover"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "weld discover" in response
        assert "Queued" in response

    async def test_blocks_telegram_subcommand(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Blocks the telegram subcommand for safety."""
        mock_command.args = "telegram serve"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "not allowed" in response
        # Queue should not have been called
        mock_queue_manager.enqueue.assert_not_called()

    async def test_rejects_invalid_subcommand_format(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Rejects subcommand with invalid characters."""
        mock_command.args = "sub;cmd"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "Invalid subcommand" in response
        mock_queue_manager.enqueue.assert_not_called()

    async def test_accepts_subcommand_with_dashes(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Accepts subcommand with dashes and underscores."""
        mock_command.args = "my-custom_cmd"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        # Underscores are escaped for Telegram Markdown
        assert "weld my-custom" in response
        assert "cmd" in response
        assert "Queued" in response

    async def test_sanitizes_command_arguments(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Sanitizes arguments to prevent injection."""
        mock_command.args = "review file.py; rm -rf /"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        # Semicolon should be sanitized out
        assert ";" not in response
        assert "file.py" in response

    async def test_shows_queue_position(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows position when not first in queue."""
        mock_command.args = "init"
        mock_queue_manager.enqueue.return_value = 3
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "3 in queue" in response

    async def test_shows_next_up_when_first(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows 'next up' when first in queue."""
        mock_command.args = "init"
        mock_queue_manager.enqueue.return_value = 1
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "next up" in response

    async def test_handles_enqueue_failure(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Handles queue failure gracefully."""
        mock_command.args = "review"
        mock_queue_manager.enqueue.side_effect = Exception("Queue error")
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "Failed to queue" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = "discover"

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_subcommand_is_lowercased(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Subcommand is converted to lowercase."""
        mock_command.args = "DISCOVER"
        context = UserContext(user_id=12345, current_project="proj")
        await state_store.upsert_context(context)

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        response = mock_message.answer.call_args[0][0]
        assert "weld discover" in response


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

            # Use realistic error message that matches actual exception
            mock_validate.side_effect = PathNotFoundError("Path does not exist: file.txt")
            await fetch_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "does not exist" in response

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

            # Use realistic error message that matches actual exception
            mock_validate.side_effect = PathNotAllowedError(
                "Path '/etc/passwd' is not within any registered project"
            )
            await fetch_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "not within any registered project" in response

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

            # Use realistic error message that matches actual exception
            mock_validate.side_effect = PathNotAllowedError(
                "Path '/etc/passwd' is not within any registered project"
            )
            await push_command(mock_message, mock_command, telegram_config, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "not within any registered project" in response

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


@pytest.mark.asyncio
@pytest.mark.unit
class TestDocumentHandler:
    """Tests for document_handler function (automatic file uploads)."""

    @pytest.fixture
    def mock_document_message(self, mock_message: MagicMock) -> MagicMock:
        """Create a mock message with document attachment."""
        mock_message.document = MagicMock()
        mock_message.document.file_name = "spec.md"
        mock_message.document.file_size = 1000
        mock_message.document.file_id = "file_abc123"
        # Ensure it's not a reply (replies are handled by /push command)
        mock_message.reply_to_message = None
        return mock_message

    async def test_requires_user_context(
        self,
        mock_document_message: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Requires user to have project context."""
        from weld.telegram.bot import document_handler

        # Don't set up user context - should trigger "No project selected"
        await document_handler(mock_document_message, state_store, telegram_config, mock_bot)

        # Should show "No project selected" message
        response = mock_document_message.answer.call_args[0][0]
        assert "No project selected" in response

    async def test_rejects_file_too_large(
        self,
        mock_document_message: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Rejects files larger than 50MB."""
        from weld.telegram.bot import document_handler

        # Large file check happens before user context check
        mock_document_message.document.file_size = 100 * 1024 * 1024  # 100MB

        await document_handler(mock_document_message, state_store, telegram_config, mock_bot)

        response = mock_document_message.answer.call_args[0][0]
        assert "too large" in response.lower()

    async def test_rejects_disallowed_file_extension(
        self,
        mock_document_message: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Rejects file types not in allowed list."""
        from weld.telegram.bot import document_handler

        # Extension check happens before user context check
        mock_document_message.document.file_name = "virus.exe"

        await document_handler(mock_document_message, state_store, telegram_config, mock_bot)

        response = mock_document_message.answer.call_args[0][0]
        assert "not allowed" in response.lower()

    async def test_saves_allowed_file(
        self,
        mock_document_message: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Downloads and saves file with allowed extension."""
        from weld.telegram.bot import document_handler

        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        # Mock file download
        mock_file = MagicMock()
        mock_file.file_path = "/path/to/file"
        mock_bot.get_file.return_value = mock_file

        mock_file_content = MagicMock()
        mock_file_content.read.return_value = b"# Spec content"
        mock_bot.download_file.return_value = mock_file_content

        await document_handler(mock_document_message, state_store, telegram_config, mock_bot)

        # Should have downloaded file
        mock_bot.get_file.assert_called_once()
        mock_bot.download_file.assert_called_once()

        # Check success message
        response = mock_document_message.answer.call_args[0][0]
        assert "saved" in response.lower() or "Saved" in response

    async def test_handles_no_document(
        self,
        mock_message: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Silently returns when message has no document."""
        from weld.telegram.bot import document_handler

        mock_message.document = None
        mock_message.reply_to_message = None
        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        # Should not raise, just return silently
        await document_handler(mock_message, state_store, telegram_config, mock_bot)

        # No error message should be sent
        mock_message.answer.assert_not_called()

    async def test_handles_no_user(
        self,
        mock_document_message: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Sends error message when message has no from_user."""
        from weld.telegram.bot import document_handler

        mock_document_message.from_user = None

        await document_handler(mock_document_message, state_store, telegram_config, mock_bot)

        # Handler sends "Unable to identify user" message
        response = mock_document_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_handles_download_failure(
        self,
        mock_document_message: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Handles Telegram file download failures gracefully."""
        from weld.telegram.bot import document_handler

        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        # Mock download failure
        mock_bot.get_file.side_effect = Exception("Download failed")

        await document_handler(mock_document_message, state_store, telegram_config, mock_bot)

        response = mock_document_message.answer.call_args[0][0]
        assert "failed" in response.lower()

    async def test_accepts_various_allowed_extensions(
        self,
        mock_document_message: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Accepts various allowed file extensions."""
        from weld.telegram.bot import document_handler

        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        mock_file = MagicMock()
        mock_file.file_path = "/path/to/file"
        mock_bot.get_file.return_value = mock_file

        mock_file_content = MagicMock()
        mock_file_content.read.return_value = b"content"
        mock_bot.download_file.return_value = mock_file_content

        allowed_files = ["spec.md", "config.yaml", "data.json", "plan.txt"]

        for filename in allowed_files:
            mock_document_message.document.file_name = filename
            mock_document_message.answer.reset_mock()
            mock_bot.get_file.reset_mock()
            mock_bot.download_file.reset_mock()

            await document_handler(mock_document_message, state_store, telegram_config, mock_bot)

            # Should process the file (not reject)
            if mock_document_message.answer.called:
                response = mock_document_message.answer.call_args[0][0]
                assert "not allowed" not in response.lower(), f"Failed for {filename}"

    async def test_ignores_reply_messages(
        self,
        mock_document_message: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Silently ignores documents that are replies (handled by /push)."""
        from weld.telegram.bot import document_handler

        mock_document_message.reply_to_message = MagicMock()  # Has a reply

        await document_handler(mock_document_message, state_store, telegram_config, mock_bot)

        # Should return silently without sending any message
        mock_document_message.answer.assert_not_called()


@pytest.mark.unit
class TestFindUploadedFile:
    """Tests for _find_uploaded_file function."""

    def test_finds_exact_match(self, tmp_path: Path) -> None:
        """Finds file with exact name match."""
        from weld.telegram.bot import _find_uploaded_file

        uploads_dir = tmp_path / ".weld" / "telegram" / "uploads"
        uploads_dir.mkdir(parents=True)
        test_file = uploads_dir / "spec.md"
        test_file.write_text("content")

        result = _find_uploaded_file(uploads_dir, "spec.md")
        assert result == test_file

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """Returns None when file doesn't exist."""
        from weld.telegram.bot import _find_uploaded_file

        uploads_dir = tmp_path / ".weld" / "telegram" / "uploads"
        uploads_dir.mkdir(parents=True)

        result = _find_uploaded_file(uploads_dir, "nonexistent.md")
        assert result is None

    def test_returns_none_when_dir_not_exists(self, tmp_path: Path) -> None:
        """Returns None when uploads directory doesn't exist."""
        from weld.telegram.bot import _find_uploaded_file

        uploads_dir = tmp_path / "nonexistent"

        result = _find_uploaded_file(uploads_dir, "spec.md")
        assert result is None

    def test_finds_file_with_numeric_suffix(self, tmp_path: Path) -> None:
        """Finds file with numeric conflict suffix."""
        from weld.telegram.bot import _find_uploaded_file

        uploads_dir = tmp_path / ".weld" / "telegram" / "uploads"
        uploads_dir.mkdir(parents=True)
        # Create files with conflict suffixes
        (uploads_dir / "spec.1.md").write_text("first")
        (uploads_dir / "spec.2.md").write_text("second")

        # Should find one of the suffixed files
        result = _find_uploaded_file(uploads_dir, "spec.md")
        assert result is not None
        assert "spec" in result.name

    def test_prefers_exact_match_over_suffix(self, tmp_path: Path) -> None:
        """Prefers exact filename match over suffixed versions."""
        from weld.telegram.bot import _find_uploaded_file

        uploads_dir = tmp_path / ".weld" / "telegram" / "uploads"
        uploads_dir.mkdir(parents=True)
        exact = uploads_dir / "spec.md"
        exact.write_text("exact match")
        (uploads_dir / "spec.1.md").write_text("suffixed")

        result = _find_uploaded_file(uploads_dir, "spec.md")
        assert result == exact

    def test_handles_file_without_extension(self, tmp_path: Path) -> None:
        """Handles files without extension."""
        from weld.telegram.bot import _find_uploaded_file

        uploads_dir = tmp_path / ".weld" / "telegram" / "uploads"
        uploads_dir.mkdir(parents=True)
        test_file = uploads_dir / "Makefile"
        test_file.write_text("content")

        result = _find_uploaded_file(uploads_dir, "Makefile")
        assert result == test_file


@pytest.mark.asyncio
@pytest.mark.unit
class TestReplyToDocumentInjection:
    """Tests for reply-to-document file path auto-injection in commands."""

    async def test_injects_file_path_when_reply_to_document(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Injects uploaded file path when command replies to document."""
        # Set up context
        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        # Set up reply to document
        mock_command.args = "--force"
        mock_message.reply_to_message = MagicMock()
        mock_message.reply_to_message.document = MagicMock()
        mock_message.reply_to_message.document.file_name = "spec.md"

        # Create the uploaded file in the expected location
        project_path = telegram_config.projects[0].path
        uploads_dir = project_path / ".weld" / "telegram" / "uploads"
        uploads_dir.mkdir(parents=True)
        (uploads_dir / "spec.md").write_text("content")

        await plan_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        # Verify the command was enqueued with injected path
        response = mock_message.answer.call_args[0][0]
        assert "Queued" in response
        # The injected path should appear in the command
        assert ".weld/telegram/uploads/spec.md" in response or "spec.md" in response

    async def test_shows_error_when_uploaded_file_not_found(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows error when reply-to document file not found."""
        # Set up context
        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        # Set up reply to document (but don't create the file)
        mock_command.args = ""
        mock_message.reply_to_message = MagicMock()
        mock_message.reply_to_message.document = MagicMock()
        mock_message.reply_to_message.document.file_name = "missing.md"

        await plan_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        # Should show error about file not found
        response = mock_message.answer.call_args[0][0]
        assert "cannot find" in response.lower() or "not found" in response.lower()

    async def test_no_injection_without_reply(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Does not inject path when not a reply to document."""
        # Set up context
        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        mock_command.args = "myspec.md"
        mock_message.reply_to_message = None

        await plan_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        # Should just use provided args, not inject anything
        response = mock_message.answer.call_args[0][0]
        assert "Queued" in response
        assert "myspec.md" in response

    async def test_weld_command_also_supports_injection(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Generic /weld command also supports file path injection."""
        # Set up context
        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        # Set up reply to document
        mock_command.args = "research"
        mock_message.reply_to_message = MagicMock()
        mock_message.reply_to_message.document = MagicMock()
        mock_message.reply_to_message.document.file_name = "research.md"

        # Create the uploaded file
        project_path = telegram_config.projects[0].path
        uploads_dir = project_path / ".weld" / "telegram" / "uploads"
        uploads_dir.mkdir(parents=True)
        (uploads_dir / "research.md").write_text("content")

        await weld_command(
            mock_message, mock_command, state_store, mock_queue_manager, telegram_config
        )

        # Verify command was queued with injected path
        response = mock_message.answer.call_args[0][0]
        assert "Queued" in response
        assert "weld research" in response


@pytest.mark.unit
class TestDetectOutputFiles:
    """Tests for detect_output_files function."""

    def test_detects_saved_to_pattern(self, tmp_path: Path) -> None:
        """Detects 'saved to' pattern in output."""

        output = "Plan saved to: spec_PLAN.md"
        test_file = tmp_path / "spec_PLAN.md"
        test_file.write_text("content")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 1
        assert result[0].name == "spec_PLAN.md"

    def test_detects_saving_to_pattern(self, tmp_path: Path) -> None:
        """Detects 'saving to' pattern in output."""

        output = "Saving to output.txt"
        test_file = tmp_path / "output.txt"
        test_file.write_text("content")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 1
        assert result[0].name == "output.txt"

    def test_detects_created_pattern(self, tmp_path: Path) -> None:
        """Detects 'created' pattern in output."""

        output = "Created: new_file.json"
        test_file = tmp_path / "new_file.json"
        test_file.write_text("{}")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 1
        assert result[0].name == "new_file.json"

    def test_detects_wrote_pattern(self, tmp_path: Path) -> None:
        """Detects 'wrote' pattern in output."""

        output = "Wrote to config.yaml"
        test_file = tmp_path / "config.yaml"
        test_file.write_text("key: value")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 1
        assert result[0].name == "config.yaml"

    def test_detects_written_pattern(self, tmp_path: Path) -> None:
        """Detects 'written to' pattern in output."""

        output = "File written to result.txt"
        test_file = tmp_path / "result.txt"
        test_file.write_text("result")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 1
        assert result[0].name == "result.txt"

    def test_detects_output_colon_pattern(self, tmp_path: Path) -> None:
        """Detects 'output:' pattern in output."""

        output = "Output: report.md"
        test_file = tmp_path / "report.md"
        test_file.write_text("# Report")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 1
        assert result[0].name == "report.md"

    def test_detects_generated_pattern(self, tmp_path: Path) -> None:
        """Detects 'generated' pattern in output."""

        output = "Generated: docs.html"
        test_file = tmp_path / "docs.html"
        test_file.write_text("<html>")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 1
        assert result[0].name == "docs.html"

    def test_detects_writing_to_pattern(self, tmp_path: Path) -> None:
        """Detects 'writing to' pattern in output."""

        output = "Writing to data.csv"
        test_file = tmp_path / "data.csv"
        test_file.write_text("a,b,c")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 1
        assert result[0].name == "data.csv"

    def test_detects_plan_saved_to_pattern(self, tmp_path: Path) -> None:
        """Detects weld-specific 'plan saved to' pattern."""

        output = "Plan saved to implementation_PLAN.md"
        test_file = tmp_path / "implementation_PLAN.md"
        test_file.write_text("# Plan")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 1
        assert result[0].name == "implementation_PLAN.md"

    def test_handles_quoted_paths(self, tmp_path: Path) -> None:
        """Handles paths in single or double quotes (without spaces)."""

        # Quoted paths work when filename has no spaces
        output = 'Saved to: "output.md"'
        test_file = tmp_path / "output.md"
        test_file.write_text("content")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 1
        assert result[0].name == "output.md"

    def test_handles_single_quoted_paths(self, tmp_path: Path) -> None:
        """Handles paths in single quotes."""

        output = "Created 'result.json'"
        test_file = tmp_path / "result.json"
        test_file.write_text("{}")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 1
        assert result[0].name == "result.json"

    def test_filters_urls(self) -> None:
        """Filters out URLs from detection."""

        output = "Output: https://example.com/file.md"
        result = detect_output_files(output)
        assert len(result) == 0

    def test_filters_http_urls(self) -> None:
        """Filters out HTTP URLs."""

        output = "Saved to http://example.com/data.json"
        result = detect_output_files(output)
        assert len(result) == 0

    def test_filters_ftp_urls(self) -> None:
        """Filters out FTP URLs."""

        output = "Created ftp://server.com/file.txt"
        result = detect_output_files(output)
        assert len(result) == 0

    def test_filters_unknown_extensions(self) -> None:
        """Filters out paths without recognized extensions."""

        output = "Saved to binary.exe"
        result = detect_output_files(output)
        assert len(result) == 0

    def test_filters_no_extension(self) -> None:
        """Filters out paths without any extension."""

        output = "Created Makefile"
        result = detect_output_files(output)
        assert len(result) == 0

    def test_filters_nonexistent_files_with_cwd(self, tmp_path: Path) -> None:
        """Filters out non-existent files when cwd is provided."""

        output = "Saved to nonexistent.md"
        # Don't create the file
        result = detect_output_files(output, tmp_path)
        assert len(result) == 0

    def test_returns_paths_without_validation_when_no_cwd(self) -> None:
        """Returns paths without existence check when cwd is None."""

        output = "Saved to any_file.md"
        result = detect_output_files(output, cwd=None)
        # Without cwd, file existence isn't checked
        assert len(result) == 1
        assert result[0] == Path("any_file.md")

    def test_deduplicates_paths(self, tmp_path: Path) -> None:
        """Deduplicates duplicate path references."""

        output = "Saved to file.md\nOutput: file.md"
        test_file = tmp_path / "file.md"
        test_file.write_text("content")

        result = detect_output_files(output, tmp_path)
        # Should only appear once despite matching twice
        assert len(result) == 1

    def test_multiple_files_detected(self, tmp_path: Path) -> None:
        """Detects multiple different files in output."""

        output = "Created first.md\nSaved to second.json\nWrote to third.txt"
        (tmp_path / "first.md").write_text("1")
        (tmp_path / "second.json").write_text("{}")
        (tmp_path / "third.txt").write_text("3")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 3
        names = [p.name for p in result]
        assert "first.md" in names
        assert "second.json" in names
        assert "third.txt" in names

    def test_handles_relative_paths(self, tmp_path: Path) -> None:
        """Resolves relative paths against cwd."""

        subdir = tmp_path / "subdir"
        subdir.mkdir()
        test_file = subdir / "nested.md"
        test_file.write_text("content")

        output = "Saved to subdir/nested.md"
        result = detect_output_files(output, tmp_path)
        assert len(result) == 1
        assert result[0] == test_file.resolve()

    def test_case_insensitive_patterns(self, tmp_path: Path) -> None:
        """Pattern matching is case insensitive."""

        output = "SAVED TO upper.md"
        test_file = tmp_path / "upper.md"
        test_file.write_text("content")

        result = detect_output_files(output, tmp_path)
        assert len(result) == 1

    def test_empty_output(self) -> None:
        """Handles empty output string."""

        result = detect_output_files("")
        assert len(result) == 0

    def test_output_with_no_file_patterns(self) -> None:
        """Returns empty list when no patterns match."""

        output = "Processing complete. No files were generated."
        result = detect_output_files(output)
        assert len(result) == 0

    def test_accepted_extensions(self, tmp_path: Path) -> None:
        """Tests various accepted file extensions."""

        extensions = [".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".py", ".js", ".ts"]

        for ext in extensions:
            filename = f"file{ext}"
            test_file = tmp_path / filename
            test_file.write_text("content")

            output = f"Created {filename}"
            result = detect_output_files(output, tmp_path)
            assert len(result) == 1, f"Failed for extension {ext}"
            # Clean up for next iteration
            test_file.unlink()


@pytest.mark.unit
class TestCreateDownloadKeyboard:
    """Tests for create_download_keyboard function."""

    def test_creates_keyboard_with_download_button(self, tmp_path: Path) -> None:
        """Creates keyboard with Download button."""

        keyboard = create_download_keyboard("output.md", tmp_path)
        assert keyboard is not None
        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 1
        assert "Download" in keyboard.inline_keyboard[0][0].text
        assert keyboard.inline_keyboard[0][0].callback_data == "fetch:output.md"

    def test_returns_relative_path_in_callback(self, tmp_path: Path) -> None:
        """Uses relative path in callback data when possible."""

        absolute_path = str(tmp_path / "subdir" / "file.md")
        keyboard = create_download_keyboard(absolute_path, tmp_path)
        assert keyboard is not None
        callback = keyboard.inline_keyboard[0][0].callback_data
        assert callback == "fetch:subdir/file.md"

    def test_returns_none_for_long_paths(self, tmp_path: Path) -> None:
        """Returns None when path exceeds callback data limit."""

        # Create a path that will exceed 64 bytes when added to "fetch:" prefix
        long_name = "a" * 60 + ".md"  # "fetch:" (6 bytes) + 63 bytes = 69 bytes > 64
        keyboard = create_download_keyboard(long_name, tmp_path)
        assert keyboard is None

    def test_handles_short_relative_path(self, tmp_path: Path) -> None:
        """Handles short relative paths."""

        keyboard = create_download_keyboard("x.md", tmp_path)
        assert keyboard is not None
        assert keyboard.inline_keyboard[0][0].callback_data == "fetch:x.md"

    def test_button_has_emoji(self, tmp_path: Path) -> None:
        """Download button includes emoji indicator."""

        keyboard = create_download_keyboard("file.md", tmp_path)
        assert keyboard is not None
        assert "📥" in keyboard.inline_keyboard[0][0].text


@pytest.mark.asyncio
@pytest.mark.unit
class TestHandleFetchCallback:
    """Tests for handle_fetch_callback function."""

    @pytest.fixture
    def mock_callback(self) -> MagicMock:
        """Create mock callback query."""
        callback = MagicMock()
        callback.from_user = MagicMock()
        callback.from_user.id = 12345
        callback.message = MagicMock()
        callback.message.chat = MagicMock()
        callback.message.chat.id = 67890
        callback.answer = AsyncMock()
        return callback

    async def test_ignores_non_fetch_callback(self, mock_callback: MagicMock) -> None:
        """Ignores callbacks not starting with 'fetch:'."""

        mock_callback.data = "prompt:1:2"

        await handle_fetch_callback(mock_callback, MagicMock(), AsyncMock(), MagicMock())

        mock_callback.answer.assert_not_called()

    async def test_ignores_empty_data(self, mock_callback: MagicMock) -> None:
        """Ignores callback with no data."""

        mock_callback.data = None

        await handle_fetch_callback(mock_callback, MagicMock(), AsyncMock(), MagicMock())

        mock_callback.answer.assert_not_called()

    async def test_rejects_empty_file_path(
        self, mock_callback: MagicMock, state_store: StateStore
    ) -> None:
        """Shows alert for empty file path."""

        mock_callback.data = "fetch:"

        await handle_fetch_callback(mock_callback, MagicMock(), AsyncMock(), state_store)

        mock_callback.answer.assert_called_once()
        assert "Invalid" in str(mock_callback.answer.call_args)

    async def test_rejects_no_user(self, mock_callback: MagicMock) -> None:
        """Shows alert when user cannot be identified."""

        mock_callback.data = "fetch:file.md"
        mock_callback.from_user = None

        await handle_fetch_callback(mock_callback, MagicMock(), AsyncMock(), MagicMock())

        mock_callback.answer.assert_called_once()
        assert "identify user" in str(mock_callback.answer.call_args)

    async def test_rejects_no_project_context(
        self, mock_callback: MagicMock, state_store: StateStore
    ) -> None:
        """Shows alert when user has no project selected."""

        mock_callback.data = "fetch:file.md"
        # No context set up

        await handle_fetch_callback(mock_callback, MagicMock(), AsyncMock(), state_store)

        mock_callback.answer.assert_called_once()
        assert "project" in str(mock_callback.answer.call_args).lower()

    async def test_rejects_unknown_project(
        self,
        mock_callback: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows alert when user's project is not found in config."""

        mock_callback.data = "fetch:file.md"
        context = UserContext(user_id=12345, current_project="unknownproject")
        await state_store.upsert_context(context)

        await handle_fetch_callback(mock_callback, telegram_config, AsyncMock(), state_store)

        mock_callback.answer.assert_called_once()
        assert "not found" in str(mock_callback.answer.call_args).lower()

    async def test_rejects_path_outside_project(
        self,
        mock_callback: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Shows alert when path escapes project boundary."""

        mock_callback.data = "fetch:../../../etc/passwd"
        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        await handle_fetch_callback(mock_callback, telegram_config, mock_bot, state_store)

        mock_callback.answer.assert_called()
        assert "denied" in str(mock_callback.answer.call_args).lower()

    async def test_rejects_nonexistent_file(
        self,
        mock_callback: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Shows alert when file does not exist."""

        mock_callback.data = "fetch:nonexistent.md"
        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        await handle_fetch_callback(mock_callback, telegram_config, mock_bot, state_store)

        mock_callback.answer.assert_called()
        assert "not found" in str(mock_callback.answer.call_args).lower()

    async def test_rejects_oversized_file(
        self,
        mock_callback: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Shows alert when file exceeds size limit."""

        mock_callback.data = "fetch:large.md"
        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        # Create large file
        project_path = telegram_config.projects[0].path
        large_file = project_path / "large.md"
        # Write more than 50MB (50 * 1024 * 1024 bytes)
        large_file.write_bytes(b"x" * (51 * 1024 * 1024))

        try:
            await handle_fetch_callback(mock_callback, telegram_config, mock_bot, state_store)

            mock_callback.answer.assert_called()
            assert "large" in str(mock_callback.answer.call_args).lower()
        finally:
            large_file.unlink()

    async def test_sends_file_successfully(
        self,
        mock_callback: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Sends file and acknowledges success."""

        mock_callback.data = "fetch:download_me.md"
        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        # Create file to download
        project_path = telegram_config.projects[0].path
        test_file = project_path / "download_me.md"
        test_file.write_text("# Download content")

        try:
            await handle_fetch_callback(mock_callback, telegram_config, mock_bot, state_store)

            # Should have sent document
            mock_bot.send_document.assert_called_once()
            # Should acknowledge
            mock_callback.answer.assert_called()
            assert "sent" in str(mock_callback.answer.call_args).lower()
        finally:
            test_file.unlink()

    async def test_sends_nested_file(
        self,
        mock_callback: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Sends file from subdirectory."""

        mock_callback.data = "fetch:subdir/nested.md"
        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        # Create nested file
        project_path = telegram_config.projects[0].path
        subdir = project_path / "subdir"
        subdir.mkdir(exist_ok=True)
        test_file = subdir / "nested.md"
        test_file.write_text("Nested content")

        try:
            await handle_fetch_callback(mock_callback, telegram_config, mock_bot, state_store)

            mock_bot.send_document.assert_called_once()
            mock_callback.answer.assert_called()
        finally:
            test_file.unlink()
            subdir.rmdir()

    async def test_handles_send_failure(
        self,
        mock_callback: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
        mock_bot: AsyncMock,
    ) -> None:
        """Shows alert when file send fails."""

        mock_callback.data = "fetch:fail.md"
        context = UserContext(user_id=12345, current_project="testproject")
        await state_store.upsert_context(context)

        # Create file
        project_path = telegram_config.projects[0].path
        test_file = project_path / "fail.md"
        test_file.write_text("content")

        # Make send fail
        mock_bot.send_document.side_effect = Exception("Network error")

        try:
            await handle_fetch_callback(mock_callback, telegram_config, mock_bot, state_store)

            mock_callback.answer.assert_called()
            assert "Failed" in str(mock_callback.answer.call_args)
        finally:
            test_file.unlink()


@pytest.mark.asyncio
@pytest.mark.unit
class TestRunsCommand:
    """Tests for runs_command function."""

    async def test_shows_recent_runs(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Shows recent runs with default limit."""
        mock_command.args = None

        # Create some runs
        for i in range(3):
            run = Run(
                user_id=12345,
                project_name="proj",
                command=f"weld cmd{i}",
                status="completed",
            )
            await state_store.create_run(run)

        await runs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "Recent runs" in response
        assert "weld cmd" in response
        assert "Showing 3 run" in response

    async def test_shows_no_runs_message(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Shows message when no runs found."""
        mock_command.args = None

        await runs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "No runs found" in response

    async def test_respects_count_argument(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Respects count argument to limit displayed runs."""
        mock_command.args = "2"

        # Create 5 runs
        for i in range(5):
            run = Run(
                user_id=12345,
                project_name="proj",
                command=f"weld cmd{i}",
                status="completed",
            )
            await state_store.create_run(run)

        await runs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "Showing 2 run" in response

    async def test_filters_by_failed_status(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Filters to show only failed runs."""
        mock_command.args = "--failed"

        # Create mixed runs
        completed_run = Run(
            user_id=12345,
            project_name="proj",
            command="weld success",
            status="completed",
        )
        await state_store.create_run(completed_run)

        failed_run = Run(
            user_id=12345,
            project_name="proj",
            command="weld fail",
            status="failed",
            error="Something went wrong",
        )
        await state_store.create_run(failed_run)

        await runs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "failed only" in response
        assert "weld fail" in response
        assert "weld success" not in response

    async def test_filters_by_today(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Filters to show only runs from today."""
        mock_command.args = "--today"

        # Create a run (will be from "today" since started_at defaults to now)
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld today",
            status="completed",
        )
        await state_store.create_run(run)

        await runs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "today" in response
        assert "weld today" in response

    async def test_shows_error_snippet_for_failed_runs(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Shows error snippet for failed runs."""
        mock_command.args = None

        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld fail",
            status="failed",
            error="Connection timeout",
        )
        await state_store.create_run(run)

        await runs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "Connection timeout" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = None

        await runs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_caps_count_at_50(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Caps count at 50 to avoid huge messages."""
        mock_command.args = "100"

        # Create one run
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="completed",
        )
        await state_store.create_run(run)

        await runs_command(mock_message, mock_command, state_store)

        # Should work without error (limit applied internally)
        response = mock_message.answer.call_args[0][0]
        assert "Recent runs" in response

    async def test_shows_status_emojis(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Shows correct status emojis."""
        mock_command.args = None

        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="completed",
        )
        await state_store.create_run(run)

        await runs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        # Completed runs show checkmark
        assert "✓" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestLogsCommand:
    """Tests for logs_command function."""

    async def test_shows_usage_without_args(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Shows usage when no run_id provided."""
        mock_command.args = None

        await logs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "Usage" in response
        assert "/logs" in response

    async def test_shows_run_not_found(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Shows error for non-existent run."""
        mock_command.args = "99999"

        await logs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "not found" in response

    async def test_shows_run_logs(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Shows logs for completed run."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="completed",
            result="Test output here",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        await logs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "Logs" in response
        assert "Test output here" in response

    async def test_shows_error_in_logs(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Shows error output in logs."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld fail",
            status="failed",
            error="Error message here",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        await logs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "ERROR" in response
        assert "Error message here" in response

    async def test_shows_no_output_for_pending_run(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Shows no output message for pending run."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="pending",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        await logs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "no output" in response

    async def test_rejects_invalid_run_id(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Rejects non-numeric run_id."""
        mock_command.args = "abc"

        await logs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "Invalid run ID" in response

    async def test_respects_user_ownership(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Only shows logs for runs owned by user."""
        # Create run for different user
        run = Run(
            user_id=99999,  # Different user
            project_name="proj",
            command="weld test",
            status="completed",
            result="Secret output",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        await logs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "not found" in response
        assert "Secret output" not in response

    async def test_handles_page_argument(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Handles page number argument for pagination."""
        # Create run with large output
        large_output = "x" * 10000  # Large enough to paginate
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="completed",
            result=large_output,
        )
        run_id = await state_store.create_run(run)
        mock_command.args = f"{run_id} 1"

        await logs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "page" in response.lower()

    async def test_rejects_invalid_page_argument(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Rejects invalid page argument."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="completed",
            result="output",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = f"{run_id} invalid"

        await logs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "Invalid page" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = "1"

        await logs_command(mock_message, mock_command, state_store)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_handles_all_argument(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
    ) -> None:
        """Handles 'all' argument for file download."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="completed",
            result="test output",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = f"{run_id} all"

        # Mock answer_document since it will create a temp file
        mock_message.answer_document = AsyncMock()

        await logs_command(mock_message, mock_command, state_store)

        # Should call answer_document for file upload
        mock_message.answer_document.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
class TestTailCommand:
    """Tests for tail_command function."""

    async def test_shows_usage_without_args(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_bot: AsyncMock,
    ) -> None:
        """Shows usage when no run_id provided."""
        mock_command.args = None

        await tail_command(mock_message, mock_command, state_store, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "Usage" in response
        assert "/tail" in response

    async def test_shows_run_not_found(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_bot: AsyncMock,
    ) -> None:
        """Shows error for non-existent run."""
        mock_command.args = "99999"

        await tail_command(mock_message, mock_command, state_store, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "not found" in response

    async def test_rejects_non_running_run(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_bot: AsyncMock,
    ) -> None:
        """Rejects tailing completed run."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="completed",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        await tail_command(mock_message, mock_command, state_store, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "not running" in response

    async def test_rejects_invalid_run_id(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_bot: AsyncMock,
    ) -> None:
        """Rejects non-numeric run_id."""
        mock_command.args = "abc"

        await tail_command(mock_message, mock_command, state_store, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "Invalid run ID" in response

    async def test_respects_user_ownership(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_bot: AsyncMock,
    ) -> None:
        """Only allows tailing runs owned by user."""
        run = Run(
            user_id=99999,  # Different user
            project_name="proj",
            command="weld test",
            status="running",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        await tail_command(mock_message, mock_command, state_store, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "not found" in response

    async def test_prevents_multiple_concurrent_tails(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_bot: AsyncMock,
    ) -> None:
        """Prevents multiple concurrent tails per user."""
        # Create two running runs
        run1 = Run(
            user_id=12345,
            project_name="proj",
            command="weld cmd1",
            status="running",
        )
        run1_id = await state_store.create_run(run1)

        run2 = Run(
            user_id=12345,
            project_name="proj",
            command="weld cmd2",
            status="running",
        )
        run2_id = await state_store.create_run(run2)

        # Simulate existing tail by adding to _active_tails
        mock_task = MagicMock()
        _active_tails[12345] = (run1_id, mock_task)

        try:
            mock_command.args = str(run2_id)

            await tail_command(mock_message, mock_command, state_store, mock_bot)

            response = mock_message.answer.call_args[0][0]
            assert "Already tailing" in response
            assert "/tail stop" in response
        finally:
            # Clean up
            _active_tails.pop(12345, None)

    async def test_stop_command_stops_active_tail(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_bot: AsyncMock,
    ) -> None:
        """Stop command cancels active tail."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="running",
        )
        run_id = await state_store.create_run(run)

        # Create a mock task
        mock_task = MagicMock()
        _active_tails[12345] = (run_id, mock_task)

        try:
            mock_command.args = "stop"

            await tail_command(mock_message, mock_command, state_store, mock_bot)

            response = mock_message.answer.call_args[0][0]
            assert "Stopping tail" in response
            mock_task.cancel.assert_called_once()
        finally:
            # Clean up
            _active_tails.pop(12345, None)

    async def test_stop_command_when_no_active_tail(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_bot: AsyncMock,
    ) -> None:
        """Stop command shows message when no active tail."""
        mock_command.args = "stop"

        # Ensure no active tail for this user
        _active_tails.pop(12345, None)

        await tail_command(mock_message, mock_command, state_store, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "No active tail" in response

    async def test_starts_tail_for_running_run(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_bot: AsyncMock,
    ) -> None:
        """Starts tail task for running run."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="running",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        # Ensure no existing tail
        _active_tails.pop(12345, None)

        await tail_command(mock_message, mock_command, state_store, mock_bot)

        # Should have registered a tail task
        assert 12345 in _active_tails
        tail_run_id, task = _active_tails[12345]
        assert tail_run_id == run_id

        # Clean up the task
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        _active_tails.pop(12345, None)

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_bot: AsyncMock,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = "1"

        await tail_command(mock_message, mock_command, state_store, mock_bot)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_shows_current_tail_status_without_args(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_bot: AsyncMock,
    ) -> None:
        """Shows current tail status when called without args."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="running",
        )
        run_id = await state_store.create_run(run)

        # Simulate active tail
        mock_task = MagicMock()
        _active_tails[12345] = (run_id, mock_task)

        try:
            mock_command.args = ""

            await tail_command(mock_message, mock_command, state_store, mock_bot)

            response = mock_message.answer.call_args[0][0]
            assert "Currently tailing" in response
            assert str(run_id) in response
        finally:
            _active_tails.pop(12345, None)


@pytest.mark.asyncio
@pytest.mark.unit
class TestStatusWithRunId:
    """Tests for status_command with run_id argument."""

    async def test_shows_run_details(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows detailed info for specific run."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="completed",
            result="Test passed",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        # Response uses escaped markdown: Run \#1 becomes Run \\#1
        assert f"Run \\#{run_id}" in response
        assert "completed" in response
        assert "weld test" in response
        assert "proj" in response

    async def test_shows_run_not_found(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows error for non-existent run."""
        mock_command.args = "99999"

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "not found" in response

    async def test_respects_user_ownership(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Only shows details for runs owned by user."""
        run = Run(
            user_id=99999,  # Different user
            project_name="proj",
            command="weld secret",
            status="completed",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "not found" in response
        assert "secret" not in response

    async def test_shows_error_for_failed_run(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows error info for failed run."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld fail",
            status="failed",
            error="Connection timeout",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Error" in response
        assert "Connection timeout" in response

    async def test_shows_result_for_completed_run(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows result for completed run."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="completed",
            result="All tests passed",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Result" in response
        assert "All tests passed" in response

    async def test_shows_duration_for_running(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows ongoing duration for running run."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld long",
            status="running",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Duration" in response
        assert "ongoing" in response

    async def test_shows_status_emojis(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows correct status emojis."""
        run = Run(
            user_id=12345,
            project_name="proj",
            command="weld test",
            status="completed",
        )
        run_id = await state_store.create_run(run)
        mock_command.args = str(run_id)

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        # Completed runs show checkmark emoji
        assert "✅" in response

    async def test_rejects_invalid_run_id(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Rejects non-numeric run_id."""
        mock_command.args = "abc"

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        assert "Invalid run ID" in response

    async def test_falls_back_to_general_status_without_args(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        mock_queue_manager: MagicMock,
    ) -> None:
        """Shows general status when no run_id provided."""
        mock_command.args = ""

        await status_command(mock_message, mock_command, state_store, mock_queue_manager)

        response = mock_message.answer.call_args[0][0]
        # General status shows project info
        assert "Project" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestLsCommand:
    """Tests for ls_command function."""

    async def test_requires_project_context(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Requires user to select a project first."""
        mock_command.args = ""

        await ls_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "No project selected" in response
        assert "/use" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = ""

        await ls_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_lists_project_root(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Lists project root directory by default."""
        # Set up project context
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        # Create test files in project directory
        project_path = telegram_config.projects[0].path
        (project_path / "file1.py").write_text("# python file")
        (project_path / "file2.txt").write_text("text file")
        (project_path / "subdir").mkdir()

        mock_command.args = ""

        await ls_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "testproject" in response
        assert "file1.py" in response
        assert "file2.txt" in response
        assert "subdir" in response

    async def test_lists_subdirectory(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Lists specified subdirectory."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        project_path = telegram_config.projects[0].path
        subdir = project_path / "src"
        subdir.mkdir()
        (subdir / "main.py").write_text("# main")

        mock_command.args = "src"

        await ls_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "main.py" in response

    async def test_shows_hidden_files_with_all_flag(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows hidden files when --all flag is provided."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        project_path = telegram_config.projects[0].path
        (project_path / ".hidden").write_text("secret")
        (project_path / "visible.txt").write_text("public")

        mock_command.args = "--all"

        await ls_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert ".hidden" in response
        assert "visible.txt" in response

    async def test_hides_hidden_files_by_default(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Hides files starting with dot by default."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        project_path = telegram_config.projects[0].path
        (project_path / ".hidden").write_text("secret")
        (project_path / "visible.txt").write_text("public")

        mock_command.args = ""

        await ls_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert ".hidden" not in response
        assert "visible.txt" in response

    async def test_rejects_path_outside_project(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Rejects paths that traverse outside project boundary."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        mock_command.args = "../.."

        await ls_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "outside project" in response

    async def test_handles_nonexistent_path(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Reports error for non-existent paths."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        mock_command.args = "nonexistent"

        await ls_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "not found" in response

    async def test_rejects_file_path(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Rejects listing a file (not directory)."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        project_path = telegram_config.projects[0].path
        (project_path / "file.txt").write_text("content")

        mock_command.args = "file.txt"

        await ls_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Not a directory" in response

    async def test_shows_file_sizes(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows file sizes in human-readable format."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        project_path = telegram_config.projects[0].path
        (project_path / "small.txt").write_text("a")  # 1 byte

        mock_command.args = ""

        await ls_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        # Size should include B (bytes)
        assert "B" in response

    async def test_handles_empty_directory(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Reports empty directory appropriately."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        project_path = telegram_config.projects[0].path
        empty_dir = project_path / "empty"
        empty_dir.mkdir()

        mock_command.args = "empty"

        await ls_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "empty" in response.lower()

    async def test_shows_summary_counts(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows count of directories and files in summary."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        project_path = telegram_config.projects[0].path
        (project_path / "file1.txt").write_text("a")
        (project_path / "file2.txt").write_text("b")
        (project_path / "dir1").mkdir()

        mock_command.args = ""

        await ls_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "1 dir" in response
        assert "2 files" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestTreeCommand:
    """Tests for tree_command function."""

    async def test_requires_project_context(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Requires user to select a project first."""
        mock_command.args = ""

        await tree_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "No project selected" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = ""

        await tree_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_shows_tree_structure(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows tree structure from git ls-files."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        project_path = telegram_config.projects[0].path
        (project_path / "file.txt").write_text("content")

        mock_command.args = ""

        # Mock git ls-files output
        with patch("weld.telegram.bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="src/main.py\nsrc/utils/helper.py\n"
            )

            await tree_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "testproject" in response
        # Tree should show file structure
        assert "src" in response or "main.py" in response

    async def test_respects_depth_parameter(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Respects depth parameter to limit tree depth."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        mock_command.args = "2"

        with patch("weld.telegram.bot.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="a/b/c/d/e.txt\n")

            await tree_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        # With depth 2, should show a/b but not deeper
        assert "testproject" in response

    async def test_rejects_depth_too_large(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Rejects depth values that exceed limit."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        mock_command.args = "15"

        await tree_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "cannot exceed" in response

    async def test_rejects_depth_zero(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Rejects depth value of zero."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        mock_command.args = "0"

        await tree_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "at least 1" in response

    async def test_handles_path_outside_project(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Rejects paths outside project boundary."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        mock_command.args = "../.."

        await tree_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "outside project" in response

    async def test_handles_nonexistent_path(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Reports error for non-existent paths."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        mock_command.args = "nonexistent"

        await tree_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "not found" in response

    async def test_handles_git_timeout(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Handles git command timeout gracefully."""
        import subprocess

        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        mock_command.args = ""

        with patch("weld.telegram.bot.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 30)

            await tree_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "timed out" in response

    async def test_handles_no_tracked_files(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        telegram_config: TelegramConfig,
    ) -> None:
        """Reports when no tracked files found."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="testproject")
        )

        # Create a file so directory isn't empty
        project_path = telegram_config.projects[0].path
        (project_path / "untracked.txt").write_text("content")

        mock_command.args = ""

        with patch("weld.telegram.bot.subprocess.run") as mock_run:
            # Return empty list from git ls-files
            mock_run.return_value = MagicMock(returncode=0, stdout="")

            await tree_command(mock_message, mock_command, state_store, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "No tracked files" in response or "gitignore" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestCatCommand:
    """Tests for cat_command function."""

    async def test_requires_path_argument(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows usage when no path provided."""
        mock_command.args = ""

        await cat_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Usage" in response
        assert "/cat" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = "file.txt"

        await cat_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_displays_file_content(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Displays file content with syntax highlighting."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello world')")
        mock_command.args = str(test_file)

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = test_file

            await cat_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "test.py" in response
        assert "print" in response
        assert "hello world" in response

    async def test_uses_syntax_highlighting(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Uses appropriate syntax highlighting for file type."""
        test_file = tmp_path / "script.py"
        test_file.write_text("x = 1")
        mock_command.args = str(test_file)

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = test_file

            await cat_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        # Response should include python code block
        assert "```python" in response or "```py" in response

    async def test_rejects_directory(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Rejects viewing directories."""
        mock_command.args = str(tmp_path)

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = tmp_path

            await cat_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Cannot view directories" in response

    async def test_rejects_binary_files(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Rejects binary files based on extension."""
        test_file = tmp_path / "image.png"
        test_file.write_bytes(b"\x89PNG\r\n")
        mock_command.args = str(test_file)

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = test_file

            await cat_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "binary" in response.lower()
        assert "/fetch" in response

    async def test_handles_path_validation_error(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Handles path validation errors."""
        mock_command.args = "/etc/passwd"

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            from weld.telegram.files import PathNotAllowedError

            mock_validate.side_effect = PathNotAllowedError("Not within project")

            await cat_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Error" in response

    async def test_paginates_large_files(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Paginates files larger than threshold."""
        test_file = tmp_path / "large.txt"
        # Create content that exceeds pagination threshold (4000 chars)
        large_content = "x" * 5000
        test_file.write_text(large_content)
        mock_command.args = str(test_file)

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = test_file

            await cat_command(mock_message, mock_command, telegram_config)

        # Check that message was sent with reply_markup (pagination keyboard)
        call_kwargs = mock_message.answer.call_args[1]
        assert "reply_markup" in call_kwargs

    async def test_small_files_not_paginated(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Small files are sent without pagination."""
        test_file = tmp_path / "small.txt"
        test_file.write_text("short content")
        mock_command.args = str(test_file)

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = test_file

            await cat_command(mock_message, mock_command, telegram_config)

        # Check that message was sent without reply_markup
        call_kwargs = mock_message.answer.call_args[1] if mock_message.answer.call_args[1] else {}
        assert "reply_markup" not in call_kwargs


@pytest.mark.asyncio
@pytest.mark.unit
class TestCatPaginationCallback:
    """Tests for cat pagination callback handling."""

    async def test_handles_close_action(self) -> None:
        """Handles close action by removing state and deleting message."""
        from aiogram.types import Message

        callback = MagicMock()
        callback.data = "cat:abc123:close"
        callback.answer = AsyncMock()
        # Use spec=Message so isinstance() check passes
        callback.message = MagicMock(spec=Message)
        callback.message.delete = AsyncMock()

        # Set up pagination state
        state = PaginationState(
            file_path=Path("/tmp/test.txt"),
            lines=["line1", "line2"],
            current_page=0,
            total_pages=1,
            lines_per_page=50,
        )
        set_pagination_state("abc123", state)

        await handle_cat_pagination_callback(callback)

        callback.answer.assert_called_once_with("Closed")
        callback.message.delete.assert_called_once()
        assert get_pagination_state("abc123") is None

    async def test_handles_page_navigation(self) -> None:
        """Handles navigation to different page."""
        from aiogram.types import Message

        callback = MagicMock()
        callback.data = "cat:xyz789:1"  # Navigate to page 2 (0-indexed)
        callback.answer = AsyncMock()
        # Use spec=Message so isinstance() check passes
        callback.message = MagicMock(spec=Message)
        callback.message.edit_text = AsyncMock()

        # Set up pagination state with multiple pages
        lines = [f"line{i}" for i in range(100)]
        state = PaginationState(
            file_path=Path("/tmp/test.txt"),
            lines=lines,
            current_page=0,
            total_pages=2,
            lines_per_page=50,
        )
        set_pagination_state("xyz789", state)

        await handle_cat_pagination_callback(callback)

        callback.message.edit_text.assert_called_once()
        # State should be updated to page 1
        updated_state = get_pagination_state("xyz789")
        assert updated_state is not None
        assert updated_state.current_page == 1

        # Cleanup
        remove_pagination_state("xyz789")

    async def test_handles_expired_session(self) -> None:
        """Handles expired pagination session."""
        callback = MagicMock()
        callback.data = "cat:expired123:0"
        callback.answer = AsyncMock()
        callback.message = MagicMock()
        callback.message.delete = AsyncMock()

        # Don't set up any state (simulating expired)
        await handle_cat_pagination_callback(callback)

        callback.answer.assert_called_once()
        # Should show alert about expired session
        call_kwargs = callback.answer.call_args[1]
        assert call_kwargs.get("show_alert") is True

    async def test_handles_noop_action(self) -> None:
        """Handles no-op action (page indicator button) - returns early without response.

        The noop callback_data has only 2 parts (cat:noop), so the handler
        returns early before the noop check since it expects 3 parts.
        """
        callback = MagicMock()
        callback.data = "cat:noop"
        callback.answer = AsyncMock()

        await handle_cat_pagination_callback(callback)

        # Function returns early for 2-part callback data, no answer sent
        callback.answer.assert_not_called()

    async def test_handles_invalid_page_number(self) -> None:
        """Handles invalid page number in callback."""
        callback = MagicMock()
        callback.data = "cat:test123:999"  # Invalid page
        callback.answer = AsyncMock()

        # Set up state with only 2 pages
        state = PaginationState(
            file_path=Path("/tmp/test.txt"),
            lines=["a", "b"],
            current_page=0,
            total_pages=2,
            lines_per_page=1,
        )
        set_pagination_state("test123", state)

        await handle_cat_pagination_callback(callback)

        # Should show alert for invalid page
        call_kwargs = callback.answer.call_args[1]
        assert call_kwargs.get("show_alert") is True

        # Cleanup
        remove_pagination_state("test123")


@pytest.mark.unit
class TestCatPaginationKeyboard:
    """Tests for cat pagination keyboard creation."""

    def test_creates_keyboard_with_navigation(self) -> None:
        """Creates keyboard with navigation buttons."""
        keyboard = _create_cat_pagination_keyboard("abc", 1, 3)

        # Should have 2 rows: navigation and close
        assert len(keyboard.inline_keyboard) == 2

        # Navigation row should have prev, page indicator, next
        nav_row = keyboard.inline_keyboard[0]
        assert len(nav_row) >= 2

    def test_hides_prev_on_first_page(self) -> None:
        """Hides previous button on first page."""
        keyboard = _create_cat_pagination_keyboard("abc", 0, 3)

        nav_row = keyboard.inline_keyboard[0]
        button_texts = [b.text for b in nav_row]

        # Should not have Prev button
        assert not any("Prev" in text for text in button_texts)

    def test_hides_next_on_last_page(self) -> None:
        """Hides next button on last page."""
        keyboard = _create_cat_pagination_keyboard("abc", 2, 3)  # Last page (0-indexed)

        nav_row = keyboard.inline_keyboard[0]
        button_texts = [b.text for b in nav_row]

        # Should not have Next button
        assert not any("Next" in text for text in button_texts)

    def test_shows_page_indicator(self) -> None:
        """Shows current page number in indicator."""
        keyboard = _create_cat_pagination_keyboard("abc", 1, 5)

        nav_row = keyboard.inline_keyboard[0]
        # Find page indicator button
        page_text = None
        for btn in nav_row:
            if "/" in btn.text and btn.callback_data == "cat:noop":
                page_text = btn.text
                break

        assert page_text is not None
        assert "2/5" in page_text  # 1-indexed display

    def test_close_button_present(self) -> None:
        """Close button is present on all pages."""
        keyboard = _create_cat_pagination_keyboard("abc", 0, 3)

        # Close button should be in second row
        close_row = keyboard.inline_keyboard[1]
        assert len(close_row) == 1
        assert "Close" in close_row[0].text
        assert close_row[0].callback_data is not None
        assert "close" in close_row[0].callback_data


@pytest.mark.asyncio
@pytest.mark.unit
class TestHeadCommand:
    """Tests for head_command function."""

    async def test_requires_path_argument(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows usage when no path provided."""
        mock_command.args = ""

        await head_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Usage" in response
        assert "/head" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = "file.txt"

        await head_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_shows_first_20_lines_by_default(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Shows first 20 lines by default."""
        test_file = tmp_path / "test.txt"
        lines = [f"line {i}" for i in range(50)]
        test_file.write_text("\n".join(lines))
        mock_command.args = str(test_file)

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = test_file

            await head_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "line 0" in response
        assert "line 19" in response
        assert "1-20" in response  # Line range indicator

    async def test_respects_custom_line_count(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Respects custom line count argument."""
        test_file = tmp_path / "test.txt"
        lines = [f"line {i}" for i in range(50)]
        test_file.write_text("\n".join(lines))
        mock_command.args = f"{test_file} 5"

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = test_file

            await head_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "line 0" in response
        assert "line 4" in response
        assert "1-5" in response

    async def test_handles_file_shorter_than_requested(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Shows entire file when shorter than requested lines."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line 1\nline 2\nline 3")
        mock_command.args = f"{test_file} 50"

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = test_file

            await head_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "line 1" in response
        assert "line 3" in response
        # Should show total lines, not requested
        assert "3 lines" in response

    async def test_rejects_negative_line_count(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Rejects negative line count."""
        mock_command.args = "file.txt -5"

        await head_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "positive integer" in response

    async def test_rejects_zero_line_count(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Rejects zero line count."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        mock_command.args = f"{test_file} 0"

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = test_file

            await head_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "positive integer" in response

    async def test_rejects_non_numeric_line_count(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Rejects non-numeric line count."""
        mock_command.args = "file.txt abc"

        await head_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Invalid line count" in response

    async def test_rejects_directory(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Rejects viewing directories."""
        mock_command.args = str(tmp_path)

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = tmp_path

            await head_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Cannot view directories" in response

    async def test_rejects_binary_files(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Rejects binary files based on extension."""
        test_file = tmp_path / "image.jpg"
        test_file.write_bytes(b"\xff\xd8\xff")
        mock_command.args = str(test_file)

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = test_file

            await head_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "binary" in response.lower()
        assert "/fetch" in response

    async def test_uses_syntax_highlighting(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Uses appropriate syntax highlighting for file type."""
        test_file = tmp_path / "code.js"
        test_file.write_text("const x = 1;")
        mock_command.args = str(test_file)

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            mock_validate.return_value = test_file

            await head_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "```javascript" in response or "```js" in response

    async def test_handles_path_validation_error(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Handles path validation errors."""
        mock_command.args = "/etc/shadow"

        with patch("weld.telegram.bot.validate_fetch_path") as mock_validate:
            from weld.telegram.files import PathNotAllowedError

            mock_validate.side_effect = PathNotAllowedError("Not within project")

            await head_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Error" in response


@pytest.mark.unit
class TestFindCommand:
    """Tests for find_command function."""

    async def test_requires_project_context(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Requires user to select a project first."""
        mock_command.args = "*.py"

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "No project selected" in response
        assert "/use" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = "*.py"

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_shows_usage_without_pattern(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Shows usage message when no pattern provided."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = ""

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "Usage:" in response
        assert "/find" in response

    async def test_finds_python_files(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Finds Python files matching *.py pattern."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "*.py"

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "main.py" in response
        assert "utils.py" in response
        # Note: underscores are escaped in Markdown V2 format
        assert "test\\_main.py" in response or "test_main.py" in response

    async def test_finds_files_with_prefix_pattern(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Finds files matching test_* prefix pattern."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "test_*"

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        # Note: underscores are escaped in Markdown V2 format
        assert "test\\_main.py" in response or "test_main.py" in response
        # Verify files that don't start with test_ are not included
        # (utils.py doesn't start with test_)
        assert "utils.py" not in response

    async def test_respects_gitignore(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Does not include files matching .gitignore patterns."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "*.json"

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        # node_modules/package.json should be ignored
        assert "package.json" not in response
        assert "No files matching" in response

    async def test_ignores_log_files(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Does not include *.log files per .gitignore."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "*.log"

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "debug.log" not in response
        assert "No files matching" in response

    async def test_recursive_pattern_with_double_star(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Finds files recursively with **/*.py pattern."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "**/*.py"

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "main.py" in response
        assert "utils.py" in response
        # Note: underscores are escaped in Markdown V2 format
        assert "test\\_main.py" in response or "test_main.py" in response

    async def test_rejects_path_traversal(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Rejects patterns with path traversal attempts."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "../*.py"

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "path traversal" in response.lower()

    async def test_rejects_too_long_pattern(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Rejects patterns that are too long."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "a" * 250  # Exceeds 200 char limit

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "too long" in response.lower()

    async def test_shows_match_count(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Shows count of matched files in output."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "*.py"

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "file" in response.lower()
        assert "found" in response.lower()

    async def test_handles_unknown_project(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Handles when user's selected project doesn't exist."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="nonexistent")
        )
        mock_command.args = "*.py"

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "not found" in response.lower()

    async def test_results_are_sorted(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Results are returned in sorted order."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "*.py"

        await find_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        # Find positions of files in output
        main_pos = response.find("main.py")
        utils_pos = response.find("utils.py")
        # src/main.py should come before src/utils.py alphabetically
        assert main_pos < utils_pos


@pytest.mark.unit
class TestGrepCommand:
    """Tests for grep_command function."""

    async def test_requires_project_context(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Requires user to select a project first."""
        mock_command.args = "TODO"

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "No project selected" in response
        assert "/use" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = "TODO"

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_shows_usage_without_pattern(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Shows usage message when no pattern provided."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = ""

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "Usage:" in response
        assert "/grep" in response

    async def test_finds_literal_string(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Finds literal string in file contents."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "Hello"

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "main.py" in response
        assert "Hello" in response

    async def test_finds_regex_pattern(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Finds content matching regex pattern."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = '"def .*"'

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "main.py" in response or "utils.py" in response or "test_main.py" in response

    async def test_searches_in_specific_path(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Searches only in specified path."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "def tests/"

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        # Should find test_main in tests/ (underscores escaped in Markdown V2)
        assert "test\\_main.py" in response or "test_main.py" in response
        # Should not find src files
        assert "src/main.py" not in response

    async def test_respects_gitignore(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Does not search in files matching .gitignore patterns."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        # Search for content that exists in ignored node_modules
        mock_command.args = "package"

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        # Should not find package.json in node_modules
        assert "package.json" not in response
        assert "No matches" in response

    async def test_rejects_invalid_regex(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Rejects invalid regex patterns."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "[invalid("

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "Invalid regex" in response

    async def test_rejects_path_traversal(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Rejects search paths with path traversal."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "test ../etc/"

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "path traversal" in response.lower()

    async def test_rejects_too_long_pattern(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Rejects patterns that are too long."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "a" * 550  # Exceeds 500 char limit

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "too long" in response.lower()

    async def test_shows_line_numbers(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Shows line numbers in search results."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "def"

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        # Should have line numbers like "2:" or similar
        import re

        assert re.search(r"\d+:", response) is not None

    async def test_shows_match_count(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Shows count of matches and files in output."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "def"

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "match" in response.lower()
        assert "file" in response.lower()

    async def test_handles_quoted_pattern_with_spaces(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Handles double-quoted patterns containing spaces."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = '"Main module"'

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "main.py" in response

    async def test_handles_single_quoted_pattern(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Handles single-quoted patterns."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "'Main module'"

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "main.py" in response

    async def test_handles_unclosed_quote(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Reports error for unclosed quotes."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = '"unclosed'

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "Unclosed quote" in response

    async def test_handles_nonexistent_path(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Reports error for non-existent search path."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "test nonexistent/"

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "not found" in response.lower()

    async def test_handles_unknown_project(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Handles when user's selected project doesn't exist."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(
            UserContext(user_id=user_id, current_project="nonexistent")
        )
        mock_command.args = "test"

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        assert "not found" in response.lower()

    async def test_groups_results_by_file(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        state_store: StateStore,
        git_project_config: TelegramConfig,
    ) -> None:
        """Groups search results by file in output."""
        user_id = mock_message.from_user.id
        await state_store.upsert_context(UserContext(user_id=user_id, current_project="gitproject"))
        mock_command.args = "def"

        await grep_command(mock_message, mock_command, state_store, git_project_config)

        response = mock_message.answer.call_args[0][0]
        # File names should appear as headers
        # Look for the bold markdown format used for file names
        assert "main.py" in response
        assert "utils.py" in response


@pytest.mark.asyncio
@pytest.mark.unit
class TestFileCommand:
    """Tests for file_command function."""

    async def test_shows_usage_when_no_args(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows usage message when no arguments provided."""
        mock_command.args = ""

        await file_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Usage" in response
        assert "/file" in response

    async def test_shows_usage_when_only_whitespace(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Shows usage message when args is only whitespace."""
        mock_command.args = "   "

        await file_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Usage" in response

    async def test_rejects_path_with_traversal(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Rejects paths containing .. path traversal."""
        mock_command.args = "../etc/passwd content"

        await file_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert ".." in response
        assert "traversal" in response.lower()

    async def test_rejects_path_outside_project(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Rejects absolute paths outside registered projects."""
        mock_command.args = "/etc/passwd some content"

        with patch("weld.telegram.bot.validate_push_path") as mock_validate:
            from weld.telegram.files import PathNotAllowedError

            mock_validate.side_effect = PathNotAllowedError(
                "Path '/etc/passwd' is not within any registered project"
            )
            await file_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "not within any registered project" in response

    async def test_rejects_oversized_content(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Rejects content larger than FILE_COMMAND_MAX_SIZE."""
        # Create content just over the limit (4KB + 1)
        oversized_content = "x" * (FILE_COMMAND_MAX_SIZE + 1)
        mock_command.args = f"test.txt {oversized_content}"

        with patch("weld.telegram.bot.validate_push_path") as mock_validate:
            mock_validate.return_value = tmp_path / "test.txt"
            await file_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "too large" in response.lower()
        assert "4KB" in response
        assert "/push" in response  # Suggests alternative

    async def test_creates_new_file(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Creates new file with inline content."""
        dest_path = tmp_path / "newfile.txt"
        mock_command.args = f"{dest_path} Hello, world!"

        with patch("weld.telegram.bot.validate_push_path") as mock_validate:
            mock_validate.return_value = dest_path
            await file_command(mock_message, mock_command, telegram_config)

        assert dest_path.exists()
        assert dest_path.read_text() == "Hello, world!"

        response = mock_message.answer.call_args[0][0]
        assert "Created" in response

    async def test_overwrites_existing_file(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Overwrites existing file and indicates this in response."""
        dest_path = tmp_path / "existing.txt"
        dest_path.write_text("old content")
        mock_command.args = f"{dest_path} new content"

        with patch("weld.telegram.bot.validate_push_path") as mock_validate:
            mock_validate.return_value = dest_path
            await file_command(mock_message, mock_command, telegram_config)

        assert dest_path.read_text() == "new content"

        response = mock_message.answer.call_args[0][0]
        assert "Overwrote" in response

    async def test_creates_parent_directories(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Creates parent directories if they don't exist."""
        dest_path = tmp_path / "deep" / "nested" / "file.txt"
        mock_command.args = f"{dest_path} nested content"

        with patch("weld.telegram.bot.validate_push_path") as mock_validate:
            mock_validate.return_value = dest_path
            await file_command(mock_message, mock_command, telegram_config)

        assert dest_path.exists()
        assert dest_path.read_text() == "nested content"

    async def test_handles_empty_content(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Creates empty file when no content provided."""
        dest_path = tmp_path / "empty.txt"
        mock_command.args = str(dest_path)  # Path only, no content

        with patch("weld.telegram.bot.validate_push_path") as mock_validate:
            mock_validate.return_value = dest_path
            await file_command(mock_message, mock_command, telegram_config)

        assert dest_path.exists()
        assert dest_path.read_text() == ""

        response = mock_message.answer.call_args[0][0]
        assert "0 bytes" in response

    async def test_handles_no_user(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
    ) -> None:
        """Handles message with no from_user."""
        mock_message.from_user = None
        mock_command.args = "file.txt content"

        await file_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Unable to identify user" in response

    async def test_handles_unicode_content(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Handles UTF-8 content correctly."""
        dest_path = tmp_path / "unicode.txt"
        mock_command.args = f"{dest_path} Hello 世界 🌍"

        with patch("weld.telegram.bot.validate_push_path") as mock_validate:
            mock_validate.return_value = dest_path
            await file_command(mock_message, mock_command, telegram_config)

        assert dest_path.exists()
        assert dest_path.read_text() == "Hello 世界 🌍"

    async def test_reports_size_in_bytes(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Reports file size in bytes in response."""
        dest_path = tmp_path / "sized.txt"
        content = "Test content"  # 12 bytes
        mock_command.args = f"{dest_path} {content}"

        with patch("weld.telegram.bot.validate_push_path") as mock_validate:
            mock_validate.return_value = dest_path
            await file_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "12 bytes" in response

    async def test_handles_write_error(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Reports error when file write fails."""
        dest_path = tmp_path / "fail.txt"
        mock_command.args = f"{dest_path} content"

        with (
            patch("weld.telegram.bot.validate_push_path") as mock_validate,
            patch("pathlib.Path.write_text") as mock_write,
        ):
            mock_validate.return_value = dest_path
            mock_write.side_effect = OSError("Permission denied")
            await file_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Failed to write" in response

    async def test_handles_directory_creation_error(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Reports error when parent directory creation fails."""
        dest_path = tmp_path / "deep" / "file.txt"
        mock_command.args = f"{dest_path} content"

        with (
            patch("weld.telegram.bot.validate_push_path") as mock_validate,
            patch("pathlib.Path.mkdir") as mock_mkdir,
        ):
            mock_validate.return_value = dest_path
            mock_mkdir.side_effect = OSError("Cannot create directory")
            await file_command(mock_message, mock_command, telegram_config)

        response = mock_message.answer.call_args[0][0]
        assert "Failed to create directory" in response

    async def test_exact_size_limit_accepted(
        self,
        mock_message: MagicMock,
        mock_command: MagicMock,
        telegram_config: TelegramConfig,
        tmp_path: Path,
    ) -> None:
        """Content exactly at size limit is accepted."""
        dest_path = tmp_path / "exact.txt"
        # Create content exactly at the limit
        exact_content = "x" * FILE_COMMAND_MAX_SIZE
        mock_command.args = f"{dest_path} {exact_content}"

        with patch("weld.telegram.bot.validate_push_path") as mock_validate:
            mock_validate.return_value = dest_path
            await file_command(mock_message, mock_command, telegram_config)

        assert dest_path.exists()
        response = mock_message.answer.call_args[0][0]
        assert "Created" in response
