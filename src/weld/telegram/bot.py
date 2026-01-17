"""Bot module with aiogram dispatcher and command handlers."""

import logging
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandObject
from aiogram.types import Message

from weld.telegram.config import TelegramConfig
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
