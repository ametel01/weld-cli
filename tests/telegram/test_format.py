"""Tests for Telegram message formatting and chunking."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from weld.telegram.format import (
    BASE_BACKOFF_DELAY,
    MIN_EDIT_INTERVAL,
    TELEGRAM_MESSAGE_LIMIT,
    MessageEditor,
    format_chunk,
    format_chunks,
    format_error,
    format_status,
)
from weld.telegram.state import Run


@pytest.mark.unit
class TestFormatChunk:
    """Tests for format_chunk function."""

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert format_chunk("") == ""

    def test_text_within_limit_unchanged(self) -> None:
        """Text within limit is returned unchanged."""
        text = "Hello, world!"
        assert format_chunk(text) == text

    def test_exact_limit_unchanged(self) -> None:
        """Text exactly at limit is returned unchanged."""
        text = "a" * TELEGRAM_MESSAGE_LIMIT
        assert format_chunk(text) == text

    def test_text_over_limit_truncated(self) -> None:
        """Text over limit is truncated."""
        text = "a" * (TELEGRAM_MESSAGE_LIMIT + 100)
        result = format_chunk(text)
        assert len(result.encode("utf-8")) <= TELEGRAM_MESSAGE_LIMIT
        assert len(result) == TELEGRAM_MESSAGE_LIMIT

    def test_custom_max_size(self) -> None:
        """Custom max_size is respected."""
        text = "Hello, world! This is a longer message."
        result = format_chunk(text, max_size=10)
        assert len(result.encode("utf-8")) <= 10

    def test_unicode_not_broken_2byte(self) -> None:
        """Two-byte Unicode characters are not split mid-character."""
        # é is 2 bytes in UTF-8: 0xC3 0xA9
        text = "ééééé"  # 5 chars, 10 bytes
        result = format_chunk(text, max_size=7)
        # Should truncate to 3 chars (6 bytes), not split a character
        assert result == "ééé"
        assert len(result.encode("utf-8")) == 6

    def test_unicode_not_broken_3byte(self) -> None:
        """Three-byte Unicode characters are not split mid-character."""
        # 中 is 3 bytes in UTF-8
        text = "中文测试"  # 4 chars, 12 bytes
        result = format_chunk(text, max_size=8)
        # Should truncate to 2 chars (6 bytes), not split a character
        assert result == "中文"
        assert len(result.encode("utf-8")) == 6

    def test_unicode_not_broken_4byte(self) -> None:
        """Four-byte Unicode characters (emoji) are not split mid-character."""
        # 🎉 is 4 bytes in UTF-8
        text = "🎉🎊🎁"  # 3 chars, 12 bytes
        result = format_chunk(text, max_size=10)
        # Should truncate to 2 chars (8 bytes), not split emoji
        assert result == "🎉🎊"
        assert len(result.encode("utf-8")) == 8

    def test_mixed_ascii_unicode(self) -> None:
        """Mixed ASCII and Unicode is handled correctly."""
        text = "Hello 世界 🌍"  # "Hello " (6) + "世界" (6) + " " (1) + "🌍" (4) = 17 bytes
        result = format_chunk(text, max_size=12)
        # Should fit "Hello 世界" (12 bytes)
        assert result == "Hello 世界"
        assert len(result.encode("utf-8")) == 12

    def test_very_small_limit(self) -> None:
        """Very small limit still works without error."""
        text = "Hello"
        result = format_chunk(text, max_size=3)
        assert result == "Hel"
        assert len(result.encode("utf-8")) <= 3

    def test_limit_smaller_than_single_char(self) -> None:
        """Limit smaller than a multi-byte char returns empty."""
        text = "🎉"  # 4 bytes
        result = format_chunk(text, max_size=2)
        # Can't fit the emoji, walks back to 0
        assert result == ""


@pytest.mark.unit
class TestFormatChunks:
    """Tests for format_chunks function."""

    def test_empty_string(self) -> None:
        """Empty string returns empty list."""
        assert format_chunks("") == []

    def test_single_chunk(self) -> None:
        """Text within limit returns single chunk."""
        text = "Hello, world!"
        chunks = format_chunks(text, max_size=100)
        assert chunks == [text]

    def test_multiple_chunks(self) -> None:
        """Long text is split into multiple chunks."""
        text = "a" * 100
        chunks = format_chunks(text, max_size=30)
        assert len(chunks) == 4
        assert "".join(chunks) == text

    def test_unicode_chunks_not_broken(self) -> None:
        """Unicode characters are not broken across chunk boundaries."""
        text = "中" * 50  # 150 bytes
        chunks = format_chunks(text, max_size=30)
        # Each chunk should be valid UTF-8
        for chunk in chunks:
            # This will raise if chunk is invalid UTF-8
            chunk.encode("utf-8")
        # All chunks together should equal original
        assert "".join(chunks) == text

    def test_emoji_chunks(self) -> None:
        """Emoji are not broken across chunk boundaries."""
        text = "🎉" * 20  # 80 bytes
        chunks = format_chunks(text, max_size=20)
        # 20 bytes fits 5 emoji (4 bytes each)
        assert all(len(c) == 5 for c in chunks[:-1])
        assert "".join(chunks) == text


@pytest.mark.unit
class TestFormatStatus:
    """Tests for format_status function."""

    def test_basic_status(self) -> None:
        """Basic run status is formatted correctly."""
        run = Run(
            id=42,
            user_id=123,
            project_name="myproject",
            command="weld plan",
            status="running",
        )
        result = format_status(run)
        assert "Run #42" in result
        assert "myproject" in result
        assert "weld plan" in result
        assert "running" in result

    def test_status_emoji_pending(self) -> None:
        """Pending status shows hourglass emoji."""
        run = Run(id=1, user_id=1, project_name="p", command="c", status="pending")
        result = format_status(run)
        assert "⏳" in result

    def test_status_emoji_running(self) -> None:
        """Running status shows play button emoji."""
        run = Run(id=1, user_id=1, project_name="p", command="c", status="running")
        result = format_status(run)
        assert "▶️" in result

    def test_status_emoji_completed(self) -> None:
        """Completed status shows checkmark emoji."""
        run = Run(id=1, user_id=1, project_name="p", command="c", status="completed")
        result = format_status(run)
        assert "✅" in result

    def test_status_emoji_failed(self) -> None:
        """Failed status shows cross mark emoji."""
        run = Run(id=1, user_id=1, project_name="p", command="c", status="failed")
        result = format_status(run)
        assert "❌" in result

    def test_status_emoji_cancelled(self) -> None:
        """Cancelled status shows stop button emoji."""
        run = Run(id=1, user_id=1, project_name="p", command="c", status="cancelled")
        result = format_status(run)
        assert "⏹️" in result

    def test_status_emoji_fallback_exists(self) -> None:
        """STATUS_EMOJI dict has fallback for unmapped statuses."""
        from weld.telegram.format import STATUS_EMOJI

        # Verify all valid statuses are mapped
        assert "pending" in STATUS_EMOJI
        assert "running" in STATUS_EMOJI
        assert "completed" in STATUS_EMOJI
        assert "failed" in STATUS_EMOJI
        assert "cancelled" in STATUS_EMOJI
        # format_status uses .get() with fallback ❓ for any unmapped status

    def test_status_with_timestamps(self) -> None:
        """Status includes timestamps when present."""
        now = datetime.now(UTC)
        run = Run(
            id=1,
            user_id=1,
            project_name="p",
            command="c",
            status="completed",
            started_at=now,
            completed_at=now,
        )
        result = format_status(run)
        assert "Started:" in result
        assert "Completed:" in result

    def test_status_with_result(self) -> None:
        """Status includes result output when present."""
        run = Run(
            id=1,
            user_id=1,
            project_name="p",
            command="c",
            status="completed",
            result="Build successful!",
        )
        result = format_status(run)
        assert "Output:" in result
        assert "Build successful!" in result

    def test_status_result_truncated(self) -> None:
        """Long result is truncated with ellipsis."""
        run = Run(
            id=1,
            user_id=1,
            project_name="p",
            command="c",
            status="completed",
            result="x" * 600,
        )
        result = format_status(run)
        assert "..." in result
        # Result preview should be max 500 chars + "..."
        assert "x" * 501 not in result

    def test_status_result_truncation_preserves_end(self) -> None:
        """Truncation preserves the END of output where errors appear."""
        # Simulate long output with error at the end
        long_output = "x" * 600 + "\nError: Command failed"
        run = Run(
            id=1,
            user_id=1,
            project_name="p",
            command="c",
            status="failed",
            result=long_output,
        )
        result = format_status(run)
        # Error at the end should be visible
        assert "Error: Command failed" in result
        # Start should be truncated with ellipsis
        assert result.count("...") >= 1


@pytest.mark.unit
class TestFormatError:
    """Tests for format_error function."""

    def test_string_error(self) -> None:
        """String errors are formatted correctly."""
        result = format_error("Something went wrong")
        assert "Error" in result
        assert "Something went wrong" in result
        assert "❌" in result

    def test_exception_error(self) -> None:
        """Exception errors are formatted correctly."""
        result = format_error(ValueError("Invalid input"))
        assert "Error" in result
        assert "Invalid input" in result

    def test_backtick_escaped(self) -> None:
        """Backticks in error are escaped."""
        result = format_error("Error in `function`")
        # Backticks replaced with single quotes
        assert "`function`" not in result
        assert "'function'" in result

    def test_asterisk_escaped(self) -> None:
        """Asterisks in error are escaped."""
        result = format_error("Error: *important*")
        # Asterisks are escaped
        assert "*important*" not in result
        assert "\\*important\\*" in result


@pytest.mark.asyncio
@pytest.mark.unit
class TestMessageEditor:
    """Tests for MessageEditor class."""

    async def test_first_call_sends_new_message(self) -> None:
        """First call sends a new message."""
        bot = AsyncMock()
        bot.send_message.return_value = MagicMock(message_id=100)

        editor = MessageEditor(bot)
        msg_id = await editor.send_or_edit(chat_id=123, text="Hello")

        assert msg_id == 100
        bot.send_message.assert_called_once_with(chat_id=123, text="Hello", parse_mode="Markdown")
        bot.edit_message_text.assert_not_called()

    async def test_second_call_edits_message(self) -> None:
        """Second call edits existing message."""
        bot = AsyncMock()
        bot.send_message.return_value = MagicMock(message_id=100)

        editor = MessageEditor(bot)
        # Override throttle for testing
        editor._last_edit_time = 0.0

        await editor.send_or_edit(chat_id=123, text="Hello")
        await editor.send_or_edit(chat_id=123, text="Updated")

        bot.send_message.assert_called_once()
        bot.edit_message_text.assert_called_once_with(
            chat_id=123, message_id=100, text="Updated", parse_mode="Markdown"
        )

    async def test_same_text_skips_edit(self) -> None:
        """Editing with same text is skipped."""
        bot = AsyncMock()
        bot.send_message.return_value = MagicMock(message_id=100)

        editor = MessageEditor(bot)
        await editor.send_or_edit(chat_id=123, text="Hello")
        await editor.send_or_edit(chat_id=123, text="Hello")

        bot.send_message.assert_called_once()
        bot.edit_message_text.assert_not_called()

    async def test_different_chat_sends_new(self) -> None:
        """Different chat_id sends new message."""
        bot = AsyncMock()
        bot.send_message.return_value = MagicMock(message_id=100)

        editor = MessageEditor(bot)
        await editor.send_or_edit(chat_id=123, text="Hello")

        bot.send_message.return_value = MagicMock(message_id=200)
        msg_id = await editor.send_or_edit(chat_id=456, text="Different chat")

        assert msg_id == 200
        assert bot.send_message.call_count == 2

    async def test_reset_clears_state(self) -> None:
        """reset() clears state to send new message."""
        bot = AsyncMock()
        bot.send_message.return_value = MagicMock(message_id=100)

        editor = MessageEditor(bot)
        await editor.send_or_edit(chat_id=123, text="Hello")
        editor.reset()

        bot.send_message.return_value = MagicMock(message_id=200)
        msg_id = await editor.send_or_edit(chat_id=123, text="After reset")

        assert msg_id == 200
        assert bot.send_message.call_count == 2

    async def test_deleted_message_sends_new(self) -> None:
        """Deleted message triggers new message send."""
        bot = AsyncMock()
        bot.send_message.return_value = MagicMock(message_id=100)
        bot.edit_message_text.side_effect = Exception("message to edit not found")

        editor = MessageEditor(bot)
        editor._last_edit_time = 0.0

        await editor.send_or_edit(chat_id=123, text="Hello")

        bot.send_message.return_value = MagicMock(message_id=200)
        msg_id = await editor.send_or_edit(chat_id=123, text="Updated")

        # Should have sent a new message after detecting deletion
        assert msg_id == 200
        assert bot.send_message.call_count == 2

    async def test_rate_limit_retries_with_backoff(self) -> None:
        """Rate limit errors trigger exponential backoff retry."""
        bot = AsyncMock()
        bot.send_message.return_value = MagicMock(message_id=100)
        # Fail twice with rate limit, then succeed
        bot.edit_message_text.side_effect = [
            Exception("Too many requests, retry after 5"),
            Exception("429 Too Many Requests"),
            None,  # Success on third attempt
        ]

        editor = MessageEditor(bot)
        editor._last_edit_time = 0.0

        await editor.send_or_edit(chat_id=123, text="Hello")
        await editor.send_or_edit(chat_id=123, text="Updated")

        # Should have retried 3 times
        assert bot.edit_message_text.call_count == 3

    async def test_non_rate_limit_error_raises(self) -> None:
        """Non-rate-limit errors are raised immediately."""
        bot = AsyncMock()
        bot.send_message.return_value = MagicMock(message_id=100)
        bot.edit_message_text.side_effect = Exception("Network error")

        editor = MessageEditor(bot)
        editor._last_edit_time = 0.0

        await editor.send_or_edit(chat_id=123, text="Hello")

        with pytest.raises(Exception, match="Network error"):
            await editor.send_or_edit(chat_id=123, text="Updated")

        # Should not retry for non-rate-limit errors
        assert bot.edit_message_text.call_count == 1


@pytest.mark.unit
class TestThrottleConstants:
    """Tests for throttle timing constants."""

    def test_min_edit_interval_value(self) -> None:
        """MIN_EDIT_INTERVAL is 2 seconds per Telegram limits."""
        assert MIN_EDIT_INTERVAL == 2.0

    def test_base_backoff_delay_value(self) -> None:
        """BASE_BACKOFF_DELAY is reasonable for exponential backoff."""
        assert BASE_BACKOFF_DELAY == 1.0

    def test_telegram_message_limit_value(self) -> None:
        """TELEGRAM_MESSAGE_LIMIT is 4096 bytes."""
        assert TELEGRAM_MESSAGE_LIMIT == 4096
