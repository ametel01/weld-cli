"""Bot module with aiogram dispatcher and command handlers."""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandObject
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from weld.services.gist_uploader import GistError, upload_gist
from weld.telegram.config import TelegramConfig
from weld.telegram.files import (
    FilePathError,
    PathNotAllowedError,
    PathNotFoundError,
    validate_fetch_path,
    validate_push_path,
)
from weld.telegram.format import MessageEditor, format_chunk, format_status
from weld.telegram.queue import QueueManager
from weld.telegram.runner import detect_prompt, execute_run, send_input
from weld.telegram.state import Run, StateStore, UserContext

# Pending prompt responses: run_id -> asyncio.Future
_pending_prompts: dict[int, asyncio.Future[str]] = {}

# Telegram file size limits
TELEGRAM_MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024  # 50MB for bot downloads

logger = logging.getLogger(__name__)


def create_prompt_keyboard(run_id: int, options: list[str]) -> InlineKeyboardMarkup:
    """Create inline keyboard for prompt options.

    Args:
        run_id: The run ID to associate with button callbacks
        options: List of option values (e.g., ["1", "2", "3"])

    Returns:
        InlineKeyboardMarkup with buttons for each option
    """
    # Map options to human-readable labels
    option_labels = {
        "1": "1: Attribute to session",
        "2": "2: Separate commit",
        "3": "3: Cancel",
    }

    buttons = []
    for opt in options:
        label = option_labels.get(opt, opt)
        callback_data = f"prompt:{run_id}:{opt}"
        buttons.append(InlineKeyboardButton(text=label, callback_data=callback_data))

    return InlineKeyboardMarkup(inline_keyboard=[buttons])


async def handle_prompt_callback(callback: CallbackQuery) -> None:
    """Handle callback from prompt inline keyboard button.

    Args:
        callback: The callback query from button press
    """
    if not callback.data or not callback.data.startswith("prompt:"):
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        logger.warning(f"Invalid prompt callback data: {callback.data}")
        return

    _, run_id_str, option = parts
    try:
        run_id = int(run_id_str)
    except ValueError:
        logger.warning(f"Invalid run_id in callback: {run_id_str}")
        return

    logger.info(f"Prompt callback: run_id={run_id}, option={option}")

    # Send the response to the running process
    if await send_input(run_id, option):
        # Acknowledge the callback
        await callback.answer(f"Selected option {option}")

        # Remove the keyboard from the message
        if isinstance(callback.message, Message):
            with contextlib.suppress(Exception):
                await callback.message.edit_reply_markup(reply_markup=None)
    else:
        await callback.answer("Command no longer running", show_alert=True)


def _escape_markdown(text: str) -> str:
    """Escape Markdown special characters for safe message formatting.

    Args:
        text: Text to escape

    Returns:
        Text with Markdown special characters escaped
    """
    # For basic Markdown mode, escape: * _ ` [
    for char in ("*", "_", "`", "["):
        text = text.replace(char, "\\" + char)
    return text


def create_bot(token: str) -> tuple[Bot, Dispatcher]:
    """Create and configure an aiogram Bot and Dispatcher.

    Creates a Bot instance with MarkdownV2 parse mode as default and
    a Dispatcher ready for registering handlers.

    Args:
        token: Telegram Bot API token from @BotFather.

    Returns:
        Tuple of (Bot, Dispatcher) ready for handler registration and polling.

    Raises:
        ValueError: If token is empty or invalid format.

    Example:
        bot, dp = create_bot("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")

        @dp.message(Command("start"))
        async def start_handler(message: Message):
            await message.answer("Hello!")

        await dp.start_polling(bot)
    """
    if not token or not token.strip():
        raise ValueError("Bot token cannot be empty")

    # Basic token format validation (number:alphanumeric)
    token = token.strip()
    if ":" not in token:
        raise ValueError("Invalid bot token format: missing colon separator")

    parts = token.split(":", 1)
    if not parts[0].isdigit():
        raise ValueError("Invalid bot token format: bot ID must be numeric")
    if not parts[1]:
        raise ValueError("Invalid bot token format: missing token hash")

    logger.debug("Creating bot instance")

    # Create bot with default properties
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )

    # Create dispatcher
    dp = Dispatcher()

    logger.info("Bot and dispatcher created successfully")

    return bot, dp


async def use_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    config: TelegramConfig,
) -> None:
    """Handle /use <project> command to switch project context.

    Validates the project exists in config, checks for race conditions
    (run in progress for this user), and updates the context table.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        config: TelegramConfig with registered projects

    Usage:
        /use myproject - Switch to project "myproject"
        /use          - Show current project and available projects
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    project_name = command.args.strip() if command.args else None

    # If no project specified, show current context and available projects
    if not project_name:
        context = await state_store.get_context(user_id)
        current = context.current_project if context else None

        project_names = config.list_project_names()
        if not project_names:
            await message.answer(
                "No projects configured.\nAdd projects to ~/.config/weld/telegram.toml"
            )
            return

        projects_list = "\n".join(f"  • {_escape_markdown(name)}" for name in project_names)
        if current:
            await message.answer(
                f"Current project: *{_escape_markdown(current)}*\n\n"
                f"Available projects:\n{projects_list}\n\n"
                "Usage: `/use <project>`"
            )
        else:
            await message.answer(
                "No project selected.\n\n"
                f"Available projects:\n{projects_list}\n\n"
                "Usage: `/use <project>`"
            )
        return

    # Validate project exists in config
    project = config.get_project(project_name)
    if project is None:
        escaped_name = _escape_markdown(project_name)
        project_names = config.list_project_names()
        if project_names:
            projects_list = "\n".join(f"  • {_escape_markdown(name)}" for name in project_names)
            await message.answer(
                f"Unknown project: `{escaped_name}`\n\nAvailable projects:\n{projects_list}"
            )
        else:
            await message.answer(f"Unknown project: `{escaped_name}`\n\nNo projects configured.")
        return

    # Check for race condition: don't allow context switch while run in progress
    context = await state_store.get_context(user_id)
    if context and context.conversation_state == "running":
        await message.answer(
            "Cannot switch projects while a command is running.\n"
            "Wait for the current command to complete or cancel it first."
        )
        return

    # Update context with new project
    new_context = UserContext(
        user_id=user_id,
        current_project=project_name,
        conversation_state=context.conversation_state if context else "idle",
        last_message_id=message.message_id,
        updated_at=datetime.now(UTC),
    )
    await state_store.upsert_context(new_context)

    # Also touch the project to track last access
    await state_store.touch_project(project_name)

    logger.info(f"User {user_id} switched to project '{project_name}'")
    await message.answer(f"Switched to project: *{_escape_markdown(project_name)}*")


async def status_command(
    message: Message,
    state_store: StateStore,
    queue_manager: QueueManager[int],
) -> None:
    """Handle /status command to show current run and queue state.

    Displays:
    - Current active run (if any) with project and command
    - Queue position and pending count
    - Recent completed/failed runs

    Args:
        message: Incoming Telegram message
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue state
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    chat_id = message.chat.id

    # Get current context
    context = await state_store.get_context(user_id)

    # Get active/pending runs
    running_runs = await state_store.list_runs_by_user(user_id, limit=1, status="running")
    pending_runs = await state_store.list_runs_by_user(user_id, limit=10, status="pending")

    # Build status message
    lines: list[str] = []

    # Current project
    if context and context.current_project:
        lines.append(f"*Project:* {_escape_markdown(context.current_project)}")
    else:
        lines.append("*Project:* None selected")

    lines.append("")

    # Active run
    if running_runs:
        run = running_runs[0]
        cmd_display = run.command[:50] + "..." if len(run.command) > 50 else run.command
        cmd_escaped = _escape_markdown(cmd_display)
        lines.append("*Current run:*")
        lines.append(f"  Command: `{cmd_escaped}`")
        lines.append(f"  Project: {_escape_markdown(run.project_name)}")
        lines.append("  Status: running")
    else:
        lines.append("*Current run:* None")

    lines.append("")

    # Queue status
    queue_size = queue_manager.queue_size(chat_id)
    if queue_size > 0 or pending_runs:
        lines.append(f"*Queue:* {queue_size} pending")
        if pending_runs:
            lines.append("Pending commands:")
            for i, run in enumerate(pending_runs[:5], 1):
                cmd_short = run.command[:30] + "..." if len(run.command) > 30 else run.command
                lines.append(f"  {i}. `{_escape_markdown(cmd_short)}`")
            if len(pending_runs) > 5:
                lines.append(f"  ... and {len(pending_runs) - 5} more")
    else:
        lines.append("*Queue:* Empty")

    # Recent history (last 3 completed/failed)
    recent_runs = await state_store.list_runs_by_user(user_id, limit=5)
    terminal_statuses = ("completed", "failed", "cancelled")
    completed_runs = [r for r in recent_runs if r.status in terminal_statuses][:3]

    if completed_runs:
        lines.append("")
        lines.append("*Recent:*")
        for run in completed_runs:
            status_emoji = {"completed": "✓", "failed": "✗", "cancelled": "⊘"}.get(run.status, "?")
            cmd_short = run.command[:25] + "..." if len(run.command) > 25 else run.command
            lines.append(f"  {status_emoji} `{_escape_markdown(cmd_short)}`")

    await message.answer("\n".join(lines))


async def cancel_command(
    message: Message,
    state_store: StateStore,
    queue_manager: QueueManager[int],
) -> None:
    """Handle /cancel command to abort active run and clear queue.

    Cancels the currently running command (if any) and clears all
    pending commands from the queue.

    Args:
        message: Incoming Telegram message
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    chat_id = message.chat.id

    # Track what we cancelled
    cancelled_active = False
    cancelled_pending = 0

    # Get and cancel active run
    running_runs = await state_store.list_runs_by_user(user_id, limit=1, status="running")
    if running_runs:
        run = running_runs[0]
        # Mark the run as cancelled in the database
        run.status = "cancelled"
        run.completed_at = datetime.now(UTC)
        run.error = "Cancelled by user"
        try:
            await state_store.update_run(run)
            cancelled_active = True
            logger.info(f"User {user_id} cancelled active run {run.id}")
        except Exception:
            logger.exception(f"Failed to cancel active run {run.id} for user {user_id}")

    # Cancel pending items in queue
    cancelled_pending = await queue_manager.cancel_pending(chat_id)

    # Also mark pending runs in database as cancelled
    pending_runs = await state_store.list_runs_by_user(user_id, limit=100, status="pending")
    db_cancelled_count = 0
    for run in pending_runs:
        run.status = "cancelled"
        run.completed_at = datetime.now(UTC)
        run.error = "Cancelled by user"
        try:
            await state_store.update_run(run)
            db_cancelled_count += 1
        except Exception:
            logger.exception(f"Failed to cancel pending run {run.id} for user {user_id}")
    if db_cancelled_count > 0:
        logger.info(f"User {user_id} cancelled {db_cancelled_count} pending runs in database")

    # Update user context to idle
    context = await state_store.get_context(user_id)
    if context and context.conversation_state == "running":
        context.conversation_state = "idle"
        context.updated_at = datetime.now(UTC)
        await state_store.upsert_context(context)

    # Build response
    if cancelled_active or cancelled_pending > 0 or db_cancelled_count > 0:
        parts: list[str] = []
        if cancelled_active:
            parts.append("Cancelled active run")
        total_pending = max(cancelled_pending, db_cancelled_count)
        if total_pending > 0:
            parts.append(f"cleared {total_pending} pending command(s)")
        await message.answer("✓ " + ", ".join(parts) + ".")
    else:
        await message.answer("Nothing to cancel. No active or pending runs.")


def _sanitize_command_args(args: str) -> str:
    """Sanitize command arguments to prevent shell injection.

    Removes or escapes potentially dangerous characters from user input.
    Also normalizes Unicode dashes to regular hyphens (Telegram auto-converts
    -- to em-dash).

    Args:
        args: Raw command arguments from user

    Returns:
        Sanitized argument string safe for command construction
    """
    if not args:
        return ""

    # Remove null bytes
    args = args.replace("\0", "")

    # Normalize Unicode dashes to regular hyphens
    # Telegram and other apps often auto-convert -- to em-dash or similar
    unicode_dashes = [
        "\u2014",  # Em dash
        "\u2013",  # En dash
        "\u2212",  # Minus sign
        "\u2015",  # Horizontal bar
    ]
    for dash in unicode_dashes:
        args = args.replace(dash, "--")

    # Remove shell metacharacters that could enable injection
    # Allow: alphanumeric, space, dash, underscore, dot, forward slash, quotes
    dangerous_chars = [";", "&", "|", "$", "`", "(", ")", "{", "}", "<", ">", "\n", "\r"]
    for char in dangerous_chars:
        args = args.replace(char, "")

    return args.strip()


async def _enqueue_weld_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
    weld_command: str,
) -> None:
    """Common handler for weld commands that enqueue runs.

    Validates project context, creates a run record, and enqueues it.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations
        weld_command: The weld subcommand name (e.g., "doctor", "plan")
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    chat_id = message.chat.id

    # Check project context
    context = await state_store.get_context(user_id)
    if not context or not context.current_project:
        await message.answer(
            "No project selected.\n\nUse `/use <project>` to select a project first."
        )
        return

    project_name = context.current_project

    # Build the full command string with sanitized arguments
    raw_args = command.args.strip() if command.args else ""
    args = _sanitize_command_args(raw_args)
    full_command = f"weld {weld_command} {args}" if args else f"weld {weld_command}"

    # Create run record
    run = Run(
        user_id=user_id,
        project_name=project_name,
        command=full_command,
        status="pending",
    )
    run_id = await state_store.create_run(run)

    # Enqueue the run
    try:
        position = await queue_manager.enqueue(chat_id, run_id)
    except Exception:
        # If enqueue fails, mark run as failed
        run.id = run_id
        run.status = "failed"
        run.completed_at = datetime.now(UTC)
        run.error = "Failed to enqueue command"
        try:
            await state_store.update_run(run)
        except Exception:
            logger.exception(f"Failed to update run {run_id} status to failed")
        logger.exception(f"Failed to enqueue run {run_id} for user {user_id}")
        await message.answer("Failed to queue command. Please try again.")
        return

    logger.info(
        f"User {user_id} queued '{full_command}' for project '{project_name}' "
        f"(run_id={run_id}, position={position})"
    )

    # Build response
    cmd_escaped = _escape_markdown(full_command)
    if position == 1:
        await message.answer(
            f"Queued: `{cmd_escaped}`\n"
            f"Project: *{_escape_markdown(project_name)}*\n"
            f"Position: next up"
        )
    else:
        await message.answer(
            f"Queued: `{cmd_escaped}`\n"
            f"Project: *{_escape_markdown(project_name)}*\n"
            f"Position: {position} in queue"
        )


async def doctor_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
) -> None:
    """Handle /doctor command to run weld doctor.

    Validates environment and tool availability for the selected project.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations

    Usage:
        /doctor - Run environment validation
    """
    await _enqueue_weld_command(message, command, state_store, queue_manager, "doctor")


async def plan_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
) -> None:
    """Handle /plan command to run weld plan.

    Generate or view implementation plans for the selected project.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations

    Usage:
        /plan              - Show plan help/status
        /plan <file.md>    - Generate plan from specification file
    """
    await _enqueue_weld_command(message, command, state_store, queue_manager, "plan")


async def interview_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
) -> None:
    """Handle /interview command to run weld interview.

    Interactive specification refinement for the selected project.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations

    Usage:
        /interview              - Start interactive interview
        /interview <spec.md>    - Interview about specific spec file
    """
    await _enqueue_weld_command(message, command, state_store, queue_manager, "interview")


async def implement_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
) -> None:
    """Handle /implement command to run weld implement.

    Execute implementation plans step by step for the selected project.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations

    Usage:
        /implement <plan.md>              - Execute plan interactively
        /implement <plan.md> --phase 1    - Execute specific phase
        /implement <plan.md> --step 1.2   - Execute specific step
    """
    await _enqueue_weld_command(message, command, state_store, queue_manager, "implement")


async def commit_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
) -> None:
    """Handle /commit command to run weld commit.

    Create session-based commits with transcript provenance.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations

    Usage:
        /commit                       - Commit with auto-generated message
        /commit -m "message"          - Commit with custom message
        /commit --no-session-split    - Single commit for all files
    """
    await _enqueue_weld_command(message, command, state_store, queue_manager, "commit")


async def fetch_command(
    message: Message,
    command: CommandObject,
    config: TelegramConfig,
    bot: Bot,
) -> None:
    """Handle /fetch <path> command to download a file from the project.

    Validates the path is within a registered project, checks file size,
    and sends the file via Telegram. Falls back to GitHub Gist for files
    larger than Telegram's 50MB limit.

    Args:
        message: Incoming Telegram message
        command: Parsed command with path argument
        config: TelegramConfig with registered projects
        bot: Bot instance for sending files

    Usage:
        /fetch src/main.py           - Download a file
        /fetch /absolute/path/file   - Download using absolute path
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Extract path argument
    path_arg = command.args.strip() if command.args else ""
    if not path_arg:
        await message.answer(
            "Usage: `/fetch <path>`\n\n"
            "Downloads a file from a registered project.\n"
            "Path must be within a project directory."
        )
        return

    # Validate path
    try:
        resolved_path = validate_fetch_path(path_arg, config)
    except PathNotFoundError as e:
        await message.answer(f"File not found: `{_escape_markdown(str(e))}`")
        return
    except PathNotAllowedError as e:
        await message.answer(f"Access denied: `{_escape_markdown(str(e))}`")
        return
    except FilePathError as e:
        await message.answer(f"Invalid path: `{_escape_markdown(str(e))}`")
        return

    # Check if it's a directory
    if resolved_path.is_dir():
        await message.answer("Cannot fetch directories. Specify a file path.")
        return

    # Get file size
    try:
        file_size = resolved_path.stat().st_size
    except OSError as e:
        await message.answer(f"Cannot read file: `{_escape_markdown(str(e))}`")
        return

    # Check if file is too large for Telegram
    if file_size > TELEGRAM_MAX_DOWNLOAD_SIZE:
        # Fall back to gist for large files
        logger.info(
            f"File {resolved_path} ({file_size} bytes) exceeds Telegram limit, using gist fallback"
        )
        await _fetch_via_gist(message, resolved_path)
        return

    # Send file via Telegram
    try:
        document = FSInputFile(resolved_path, filename=resolved_path.name)
        await bot.send_document(
            chat_id=message.chat.id,
            document=document,
            caption=f"`{_escape_markdown(str(resolved_path))}`",
            reply_to_message_id=message.message_id,
        )
        logger.info(f"User {user_id} fetched file: {resolved_path}")
    except Exception as e:
        logger.exception(f"Failed to send file {resolved_path}")
        await message.answer(f"Failed to send file: `{_escape_markdown(str(e))}`")


async def _fetch_via_gist(message: Message, path: Path) -> None:
    """Upload a file to GitHub Gist as fallback for large files.

    Args:
        message: Original message to reply to
        path: Path to the file to upload
    """
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        await message.answer(
            "File is too large for Telegram (>50MB) and is binary.\n"
            "Cannot upload binary files to Gist."
        )
        return
    except OSError as e:
        await message.answer(f"Failed to read file: `{_escape_markdown(str(e))}`")
        return

    try:
        # upload_gist is synchronous and does blocking I/O - run in thread pool
        result = await asyncio.to_thread(
            upload_gist,
            content=content,
            filename=path.name,
            description=f"File fetch: {path.name}",
            public=False,
        )
        await message.answer(
            f"File too large for Telegram (>50MB).\nUploaded to Gist: {result.gist_url}"
        )
    except GistError as e:
        await message.answer(
            f"File too large for Telegram and Gist upload failed:\n`{_escape_markdown(str(e))}`"
        )


async def push_command(
    message: Message,
    command: CommandObject,
    config: TelegramConfig,
    bot: Bot,
) -> None:
    """Handle /push <path> command to upload a file to the project.

    Must be used as a reply to a document message. Downloads the document
    and writes it to the specified path within a registered project.

    Args:
        message: Incoming Telegram message (should be a reply to a document)
        command: Parsed command with path argument
        config: TelegramConfig with registered projects
        bot: Bot instance for downloading files

    Usage:
        Reply to a document with:
        /push src/new_file.py        - Save document to specified path
        /push /absolute/path/file    - Save using absolute path
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Check if this is a reply to a message
    if not message.reply_to_message:
        await message.answer(
            "Reply to a document with `/push <path>` to save it.\n\n"
            "Usage:\n"
            "1. Send or forward a file to this chat\n"
            "2. Reply to that file with `/push <destination-path>`"
        )
        return

    # Check if the replied message has a document
    replied = message.reply_to_message
    if not replied.document:
        await message.answer(
            "The replied message does not contain a document.\n"
            "Reply to a file/document message to push it."
        )
        return

    # Extract path argument
    path_arg = command.args.strip() if command.args else ""
    if not path_arg:
        # Default to document's original filename if no path specified
        if replied.document.file_name:
            await message.answer(
                "Usage: `/push <path>`\n\n"
                "Specify the destination path for the file.\n"
                f"Original filename: `{_escape_markdown(replied.document.file_name)}`"
            )
        else:
            await message.answer(
                "Usage: `/push <path>`\n\nSpecify the destination path for the file."
            )
        return

    # Validate destination path
    try:
        resolved_path = validate_push_path(path_arg, config)
    except PathNotAllowedError as e:
        await message.answer(f"Access denied: `{_escape_markdown(str(e))}`")
        return
    except FilePathError as e:
        await message.answer(f"Invalid path: `{_escape_markdown(str(e))}`")
        return

    # Check file size (Telegram bot download limit is 20MB, but we allow larger via getFile)
    file_size = replied.document.file_size or 0
    if file_size > TELEGRAM_MAX_DOWNLOAD_SIZE:
        await message.answer(
            f"File too large to download ({file_size / 1024 / 1024:.1f}MB).\n"
            "Telegram bots can only download files up to 50MB."
        )
        return

    # Download the file
    try:
        file = await bot.get_file(replied.document.file_id)
        if not file.file_path:
            await message.answer("Failed to get file path from Telegram.")
            return

        # Download file content
        file_bytes = await bot.download_file(file.file_path)
        if file_bytes is None:
            await message.answer("Failed to download file from Telegram.")
            return

        content = file_bytes.read()
    except Exception as e:
        logger.exception("Failed to download file from Telegram")
        await message.answer(f"Failed to download file: `{_escape_markdown(str(e))}`")
        return

    # Ensure parent directory exists
    try:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        await message.answer(f"Failed to create directory: `{_escape_markdown(str(e))}`")
        return

    # Write file
    try:
        resolved_path.write_bytes(content)
        logger.info(f"User {user_id} pushed file to: {resolved_path}")
        await message.answer(f"Saved to: `{_escape_markdown(str(resolved_path))}`")
    except OSError as e:
        logger.exception(f"Failed to write file to {resolved_path}")
        await message.answer(f"Failed to write file: `{_escape_markdown(str(e))}`")


# Maximum output buffer size for status display (preserve last N bytes)
MAX_OUTPUT_BUFFER = 3000


async def run_consumer(
    run: Run,
    chat_id: int,
    editor: MessageEditor,
    cwd: Path,
    state_store: StateStore,
    bot: Bot,
) -> None:
    """Consume runner output stream and update status message in real-time.

    Reads output chunks from execute_run and uses MessageEditor to update
    a status message with progress. The message shows the run status and
    a tail of the most recent output. Handles interactive prompts by showing
    inline keyboard buttons.

    Args:
        run: The Run object with command details (must have id set)
        chat_id: Telegram chat ID to send/edit status messages in
        editor: MessageEditor instance for rate-limited message updates
        cwd: Working directory for command execution
        state_store: StateStore for persisting run status updates
        bot: Bot instance for sending messages with inline keyboards

    Note:
        - Output is buffered to the last MAX_OUTPUT_BUFFER bytes to avoid
          hitting Telegram's message size limit
        - MessageEditor handles rate limiting (2s minimum between edits)
        - If output arrives faster than edits can be made, intermediate
          chunks are accumulated and shown in the next edit
        - Interactive prompts are shown with inline keyboard buttons
    """
    if run.id is None:
        logger.error("run_consumer called with run that has no id")
        return

    run_id = run.id
    output_buffer = ""

    # Mark run as running
    run.status = "running"
    run.started_at = datetime.now(UTC)
    try:
        await state_store.update_run(run)
    except Exception:
        logger.exception(f"Failed to update run {run_id} to running status")

    # Send initial status message
    initial_status = format_status(run)
    try:
        await editor.send_or_edit(chat_id, initial_status)
    except Exception:
        logger.exception(f"Failed to send initial status for run {run_id}")

    # Parse command to get weld subcommand and args
    # run.command is like "weld doctor" or "weld plan --dry-run"
    parts = run.command.split()
    if len(parts) < 2 or parts[0] != "weld":
        logger.error(f"Run {run_id}: Invalid command format: {run.command}")
        run.status = "failed"
        run.completed_at = datetime.now(UTC)
        run.error = "Invalid command format"
        try:
            await state_store.update_run(run)
            await editor.send_or_edit(chat_id, format_status(run))
        except Exception:
            logger.exception(f"Failed to update run {run_id} status")
        return

    weld_subcommand = parts[1]
    weld_args = parts[2:] if len(parts) > 2 else None

    try:
        async for chunk_type, data in execute_run(
            run_id=run_id,
            command=weld_subcommand,
            args=weld_args,
            cwd=cwd,
        ):
            # Handle interactive prompts
            if chunk_type == "prompt":
                logger.info(f"Run {run_id}: Showing prompt to user")
                # Detect the prompt options
                prompt_info = detect_prompt(data)
                if prompt_info:
                    # Show prompt with inline keyboard
                    keyboard = create_prompt_keyboard(run_id, prompt_info.options)
                    prompt_text = (
                        f"*Run #{run_id} needs input:*\n\n"
                        f"```\n{data[-500:] if len(data) > 500 else data}\n```\n\n"
                        "Select an option:"
                    )
                    try:
                        await bot.send_message(chat_id, prompt_text, reply_markup=keyboard)
                    except Exception:
                        logger.exception(f"Failed to send prompt for run {run_id}")
                continue

            # Accumulate output (stdout and stderr combined)
            output_buffer += data

            # Truncate buffer to keep only recent output
            if len(output_buffer) > MAX_OUTPUT_BUFFER:
                # Keep only the last MAX_OUTPUT_BUFFER chars, starting at a newline if possible
                truncated = output_buffer[-MAX_OUTPUT_BUFFER:]
                newline_pos = truncated.find("\n")
                if newline_pos > 0 and newline_pos < 200:
                    truncated = truncated[newline_pos + 1 :]
                output_buffer = "..." + truncated

            # Update run with current output
            run.result = output_buffer

            # Format and chunk the status message to fit Telegram limits
            status_text = format_status(run)
            chunked_text = format_chunk(status_text)

            try:
                await editor.send_or_edit(chat_id, chunked_text)
            except Exception:
                # Log but don't fail the run if we can't update status
                logger.warning(f"Failed to update status message for run {run_id}")

        # Run completed successfully
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        logger.info(f"Run {run_id} completed successfully")

    except Exception as e:
        # Run failed
        run.status = "failed"
        run.completed_at = datetime.now(UTC)
        run.error = str(e)
        logger.exception(f"Run {run_id} failed: {e}")

    # Persist final status
    try:
        await state_store.update_run(run)
    except Exception:
        logger.exception(f"Failed to persist final status for run {run_id}")

    # Send final status update
    final_status = format_status(run)
    final_chunked = format_chunk(final_status)
    try:
        await editor.send_or_edit(chat_id, final_chunked)
    except Exception:
        logger.exception(f"Failed to send final status for run {run_id}")
