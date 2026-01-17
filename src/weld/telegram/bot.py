"""Bot module with aiogram dispatcher and command handlers."""

import logging
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


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
