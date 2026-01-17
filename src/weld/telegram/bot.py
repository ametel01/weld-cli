"""Bot module with aiogram dispatcher and command handlers."""

import logging
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandObject
from aiogram.types import Message

from weld.telegram.config import TelegramConfig
from weld.telegram.queue import QueueManager
from weld.telegram.state import StateStore, UserContext

logger = logging.getLogger(__name__)


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
