"""Message formatting for Telegram with chunking support."""

import asyncio
import logging
import time
from typing import Protocol

from weld.telegram.state import Run

logger = logging.getLogger(__name__)

# Telegram message size limit (4KB)
TELEGRAM_MESSAGE_LIMIT = 4096

# Status emoji mapping
STATUS_EMOJI = {
    "pending": "\u23f3",  # hourglass
    "running": "\u25b6\ufe0f",  # play button
    "completed": "\u2705",  # check mark
    "failed": "\u274c",  # cross mark
    "cancelled": "\u23f9\ufe0f",  # stop button
}


def format_chunk(text: str, max_size: int = TELEGRAM_MESSAGE_LIMIT) -> str:
    """Chunk text to fit within Telegram's message size limit.

    Handles multi-byte Unicode characters correctly by encoding to UTF-8
    and finding safe split points that don't break character boundaries.

    Args:
        text: The text to chunk
        max_size: Maximum size in bytes (default: 4096 for Telegram)

    Returns:
        The first chunk that fits within max_size bytes.
        If the entire text fits, returns the original text.
    """
    if not text:
        return text

    # Encode to get byte representation
    encoded = text.encode("utf-8")

    # If it fits, return as-is
    if len(encoded) <= max_size:
        return text

    # Find a safe split point that doesn't break multi-byte characters
    # UTF-8 continuation bytes start with 10xxxxxx (0x80-0xBF)
    split_point = max_size

    # Walk back from max_size to find a safe boundary
    while split_point > 0 and (encoded[split_point] & 0xC0) == 0x80:
        split_point -= 1

    # Decode the safe chunk
    return encoded[:split_point].decode("utf-8")


def format_chunks(text: str, max_size: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split text into multiple chunks that each fit within the size limit.

    Args:
        text: The text to split
        max_size: Maximum size in bytes for each chunk (default: 4096)

    Returns:
        List of text chunks, each within max_size bytes.
    """
    if not text:
        return []

    chunks = []
    remaining = text

    while remaining:
        chunk = format_chunk(remaining, max_size)
        if not chunk:
            # Safety: avoid infinite loop if something goes wrong
            break
        chunks.append(chunk)

        # Remove the chunk from remaining text
        if chunk == remaining:
            break
        remaining = remaining[len(chunk) :]

    return chunks


def format_status(run: Run) -> str:
    """Format a run status message for Telegram.

    Creates a compact status message showing run details.

    Args:
        run: The Run object to format

    Returns:
        Formatted status message string
    """
    emoji = STATUS_EMOJI.get(run.status, "\u2753")  # question mark fallback

    lines = [
        f"{emoji} *Run #{run.id}*",
        f"Project: `{run.project_name}`",
        f"Command: `{run.command}`",
        f"Status: {run.status}",
    ]

    if run.started_at:
        lines.append(f"Started: {run.started_at.strftime('%Y-%m-%d %H:%M:%S')}")

    if run.completed_at:
        lines.append(f"Completed: {run.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")

    if run.result:
        # Truncate result if too long - show LAST 500 chars since errors appear at the end
        result_preview = "..." + run.result[-500:] if len(run.result) > 500 else run.result
        lines.append(f"\nOutput:\n```\n{result_preview}\n```")

    return "\n".join(lines)


def format_error(error: str | Exception) -> str:
    """Format an error message for Telegram.

    Escapes special Markdown characters to prevent formatting issues.

    Args:
        error: The error message or exception to format

    Returns:
        Formatted error message string
    """
    error_text = str(error) if isinstance(error, Exception) else error

    # Escape Markdown special characters that could break formatting
    # For MarkdownV2: _ * [ ] ( ) ~ ` > # + - = | { } . !
    # We use basic Markdown mode, so mainly escape ` and *
    escaped = error_text.replace("`", "'").replace("*", "\\*")

    return f"\u274c *Error*\n```\n{escaped}\n```"


# Minimum interval between message edits to avoid Telegram rate limits
MIN_EDIT_INTERVAL = 2.0

# Maximum retry attempts for rate limit errors
MAX_RETRY_ATTEMPTS = 3

# Base delay for exponential backoff (seconds)
BASE_BACKOFF_DELAY = 1.0


class TelegramBot(Protocol):
    """Protocol for Telegram bot interface (for typing)."""

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
    ) -> object:
        """Send a message and return a message object with message_id."""
        ...

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str | None = None,
    ) -> object:
        """Edit an existing message."""
        ...


class MessageEditor:
    """Rate-limited message editor for Telegram.

    Enforces a minimum 2-second interval between edits to avoid Telegram
    rate limit errors. Implements exponential backoff for retry on failures.

    Usage:
        editor = MessageEditor(bot)

        # First call sends a new message
        await editor.send_or_edit(chat_id, "Starting...")

        # Subsequent calls edit the same message (throttled)
        await editor.send_or_edit(chat_id, "Progress: 50%")
        await editor.send_or_edit(chat_id, "Complete!")
    """

    def __init__(self, bot: TelegramBot) -> None:
        """Initialize the message editor.

        Args:
            bot: Telegram bot instance with send_message and edit_message_text methods.
        """
        self._bot = bot
        self._message_id: int | None = None
        self._chat_id: int | None = None
        self._last_edit_time: float = 0.0
        self._last_text: str = ""

    async def send_or_edit(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = "Markdown",
    ) -> int:
        """Send a new message or edit the existing one with rate limiting.

        On first call, sends a new message and stores its ID.
        On subsequent calls, edits the existing message with throttling.

        Args:
            chat_id: Telegram chat ID to send/edit message in.
            text: Message text content.
            parse_mode: Telegram parse mode (default: "Markdown").

        Returns:
            The message ID of the sent/edited message.

        Raises:
            Exception: Re-raises Telegram API errors after retry attempts exhausted.
        """
        # If no message yet or chat changed, send new message
        if self._message_id is None or self._chat_id != chat_id:
            return await self._send_new(chat_id, text, parse_mode)

        # Skip edit if text unchanged
        if text == self._last_text:
            return self._message_id

        # Throttle edits to minimum interval
        await self._wait_for_throttle()

        # Try to edit with exponential backoff on rate limit errors
        return await self._edit_with_retry(chat_id, text, parse_mode)

    async def _send_new(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None,
    ) -> int:
        """Send a new message and store its ID."""
        logger.debug(f"Sending new message to chat {chat_id}")

        message = await self._bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
        )

        # Extract message_id from the returned message object
        message_id: int = message.message_id  # type: ignore[union-attr]
        self._message_id = message_id
        self._chat_id = chat_id
        self._last_edit_time = time.monotonic()
        self._last_text = text

        logger.debug(f"Sent message {message_id} to chat {chat_id}")
        return message_id

    async def _wait_for_throttle(self) -> None:
        """Wait if needed to respect minimum edit interval."""
        elapsed = time.monotonic() - self._last_edit_time
        if elapsed < MIN_EDIT_INTERVAL:
            wait_time = MIN_EDIT_INTERVAL - elapsed
            logger.debug(f"Throttling edit for {wait_time:.2f}s")
            await asyncio.sleep(wait_time)

    async def _edit_with_retry(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None,
    ) -> int:
        """Edit message with exponential backoff on rate limit errors."""
        last_error: Exception | None = None

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                await self._bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=self._message_id,  # type: ignore[arg-type]
                    text=text,
                    parse_mode=parse_mode,
                )

                self._last_edit_time = time.monotonic()
                self._last_text = text

                logger.debug(f"Edited message {self._message_id} in chat {chat_id}")
                return self._message_id  # type: ignore[return-value]

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Check if it's a rate limit error (Telegram returns 429)
                is_rate_limit = (
                    "too many requests" in error_str
                    or "retry after" in error_str
                    or "429" in error_str
                )
                if is_rate_limit:
                    backoff = BASE_BACKOFF_DELAY * (2**attempt)
                    logger.warning(
                        f"Rate limited on edit attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS}, "
                        f"backing off for {backoff}s"
                    )
                    await asyncio.sleep(backoff)
                    continue

                # Check if message was deleted by user (can't recover from this)
                if "message to edit not found" in error_str or "message not found" in error_str:
                    logger.warning(f"Message {self._message_id} was deleted, sending new message")
                    # Reset state and send new message
                    self._message_id = None
                    self._chat_id = None
                    try:
                        return await self._send_new(chat_id, text, parse_mode)
                    except Exception as send_error:
                        logger.error(
                            f"Failed to send new message after deleted message recovery: "
                            f"{send_error}"
                        )
                        raise

                # For other errors, re-raise immediately
                raise

        # All retries exhausted
        logger.error(f"Failed to edit message after {MAX_RETRY_ATTEMPTS} attempts")
        raise last_error  # type: ignore[misc]

    def reset(self) -> None:
        """Reset the editor state to send a new message on next call.

        Use this when starting a new logical message sequence.
        """
        self._message_id = None
        self._chat_id = None
        self._last_edit_time = 0.0
        self._last_text = ""
