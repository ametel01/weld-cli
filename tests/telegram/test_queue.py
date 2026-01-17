"""Tests for Telegram bot per-chat FIFO queue manager."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from weld.telegram.queue import (
    DEFAULT_DEQUEUE_TIMEOUT,
    INACTIVE_QUEUE_THRESHOLD,
    QueuedItem,
    QueueManager,
)


@pytest.fixture
def queue_manager() -> QueueManager[int]:
    """Create a fresh QueueManager for each test."""
    return QueueManager[int]()


@pytest.mark.asyncio
@pytest.mark.unit
class TestQueuedItem:
    """Tests for QueuedItem dataclass."""

    async def test_queued_item_stores_item(self) -> None:
        """QueuedItem stores the item correctly."""
        item = QueuedItem(item=42)
        assert item.item == 42

    async def test_queued_item_has_timestamp(self) -> None:
        """QueuedItem has enqueued_at timestamp."""
        before = datetime.now(UTC)
        item = QueuedItem(item=1)
        after = datetime.now(UTC)

        assert before <= item.enqueued_at <= after

    async def test_queued_item_not_cancelled_by_default(self) -> None:
        """QueuedItem is not cancelled by default."""
        item = QueuedItem(item=1)
        assert item.cancelled is False

    async def test_queued_item_can_be_marked_cancelled(self) -> None:
        """QueuedItem can be marked as cancelled."""
        item = QueuedItem(item=1)
        item.cancelled = True
        assert item.cancelled is True


@pytest.mark.asyncio
@pytest.mark.unit
class TestQueueManagerEnqueue:
    """Tests for QueueManager.enqueue."""

    async def test_enqueue_returns_position(self, queue_manager: QueueManager[int]) -> None:
        """enqueue returns the position of the item in the queue."""
        pos1 = await queue_manager.enqueue(chat_id=100, item=1)
        pos2 = await queue_manager.enqueue(chat_id=100, item=2)
        pos3 = await queue_manager.enqueue(chat_id=100, item=3)

        assert pos1 == 1
        assert pos2 == 2
        assert pos3 == 3

    async def test_enqueue_separate_chats_independent(
        self, queue_manager: QueueManager[int]
    ) -> None:
        """Items from different chats have independent positions."""
        pos_a1 = await queue_manager.enqueue(chat_id=100, item=1)
        pos_b1 = await queue_manager.enqueue(chat_id=200, item=1)
        pos_a2 = await queue_manager.enqueue(chat_id=100, item=2)

        assert pos_a1 == 1
        assert pos_b1 == 1  # Different chat, starts at 1
        assert pos_a2 == 2

    async def test_enqueue_creates_queue_lazily(self, queue_manager: QueueManager[int]) -> None:
        """Queues are created on first enqueue for a chat."""
        assert queue_manager.active_queue_count() == 0

        await queue_manager.enqueue(chat_id=100, item=1)
        assert queue_manager.active_queue_count() == 1

        await queue_manager.enqueue(chat_id=200, item=1)
        assert queue_manager.active_queue_count() == 2

    async def test_enqueue_respects_max_queue_size(self) -> None:
        """enqueue raises when queue is full."""
        small_queue = QueueManager[int](max_queue_size=2)

        await small_queue.enqueue(chat_id=100, item=1)
        await small_queue.enqueue(chat_id=100, item=2)

        # Third enqueue should timeout (queue full)
        with pytest.raises(TimeoutError):
            await small_queue.enqueue(chat_id=100, item=3, timeout=0.1)

    async def test_enqueue_order_preserved(self, queue_manager: QueueManager[int]) -> None:
        """Items are dequeued in FIFO order."""
        await queue_manager.enqueue(chat_id=100, item=1)
        await queue_manager.enqueue(chat_id=100, item=2)
        await queue_manager.enqueue(chat_id=100, item=3)

        item1 = await queue_manager.dequeue(chat_id=100, timeout=1.0)
        item2 = await queue_manager.dequeue(chat_id=100, timeout=1.0)
        item3 = await queue_manager.dequeue(chat_id=100, timeout=1.0)

        assert item1 == 1
        assert item2 == 2
        assert item3 == 3


@pytest.mark.asyncio
@pytest.mark.unit
class TestQueueManagerDequeue:
    """Tests for QueueManager.dequeue."""

    async def test_dequeue_returns_item(self, queue_manager: QueueManager[int]) -> None:
        """dequeue returns the next item from the queue."""
        await queue_manager.enqueue(chat_id=100, item=42)
        result = await queue_manager.dequeue(chat_id=100, timeout=1.0)
        assert result == 42

    async def test_dequeue_timeout_returns_none(self, queue_manager: QueueManager[int]) -> None:
        """dequeue returns None when timeout expires on empty queue."""
        result = await queue_manager.dequeue(chat_id=100, timeout=0.1)
        assert result is None

    async def test_dequeue_blocks_until_item_available(
        self, queue_manager: QueueManager[int]
    ) -> None:
        """dequeue blocks until an item is enqueued."""

        async def delayed_enqueue():
            await asyncio.sleep(0.1)
            await queue_manager.enqueue(chat_id=100, item=99)

        task = asyncio.create_task(delayed_enqueue())

        result = await queue_manager.dequeue(chat_id=100, timeout=1.0)
        await task  # Ensure the task completes
        assert result == 99

    async def test_dequeue_skips_cancelled_items(self, queue_manager: QueueManager[int]) -> None:
        """dequeue skips items marked as cancelled."""
        await queue_manager.enqueue(chat_id=100, item=1)
        await queue_manager.enqueue(chat_id=100, item=2)
        await queue_manager.enqueue(chat_id=100, item=3)

        # Cancel the first two items
        await queue_manager.cancel_pending(chat_id=100)

        # Add a non-cancelled item
        await queue_manager.enqueue(chat_id=100, item=4)

        # Should get the non-cancelled item
        result = await queue_manager.dequeue(chat_id=100, timeout=1.0)
        assert result == 4


@pytest.mark.asyncio
@pytest.mark.unit
class TestQueueManagerGetPosition:
    """Tests for QueueManager.get_position."""

    async def test_get_position_returns_position(self, queue_manager: QueueManager[int]) -> None:
        """get_position returns 1-based position of item in queue."""
        await queue_manager.enqueue(chat_id=100, item=1)
        await queue_manager.enqueue(chat_id=100, item=2)
        await queue_manager.enqueue(chat_id=100, item=3)

        assert queue_manager.get_position(chat_id=100, item=1) == 1
        assert queue_manager.get_position(chat_id=100, item=2) == 2
        assert queue_manager.get_position(chat_id=100, item=3) == 3

    async def test_get_position_not_found_returns_none(
        self, queue_manager: QueueManager[int]
    ) -> None:
        """get_position returns None if item not in queue."""
        await queue_manager.enqueue(chat_id=100, item=1)

        assert queue_manager.get_position(chat_id=100, item=999) is None

    async def test_get_position_nonexistent_chat_returns_none(
        self, queue_manager: QueueManager[int]
    ) -> None:
        """get_position returns None for nonexistent chat_id."""
        assert queue_manager.get_position(chat_id=999, item=1) is None

    async def test_get_position_returns_none_for_cancelled_items(
        self, queue_manager: QueueManager[int]
    ) -> None:
        """get_position returns None for cancelled items."""
        await queue_manager.enqueue(chat_id=100, item=1)
        await queue_manager.enqueue(chat_id=100, item=2)

        # Cancel all items
        await queue_manager.cancel_pending(chat_id=100)

        # Cancelled items should not be found
        assert queue_manager.get_position(chat_id=100, item=1) is None
        assert queue_manager.get_position(chat_id=100, item=2) is None

        # Add item 3 (not cancelled)
        await queue_manager.enqueue(chat_id=100, item=3)

        # Item 3 is at position 3 (after the 2 cancelled items in the queue)
        assert queue_manager.get_position(chat_id=100, item=3) == 3


@pytest.mark.asyncio
@pytest.mark.unit
class TestQueueManagerCancelPending:
    """Tests for QueueManager.cancel_pending."""

    async def test_cancel_pending_returns_count(self, queue_manager: QueueManager[int]) -> None:
        """cancel_pending returns number of items cancelled."""
        await queue_manager.enqueue(chat_id=100, item=1)
        await queue_manager.enqueue(chat_id=100, item=2)
        await queue_manager.enqueue(chat_id=100, item=3)

        cancelled = await queue_manager.cancel_pending(chat_id=100)
        assert cancelled == 3

    async def test_cancel_pending_nonexistent_chat_returns_zero(
        self, queue_manager: QueueManager[int]
    ) -> None:
        """cancel_pending returns 0 for nonexistent chat_id."""
        cancelled = await queue_manager.cancel_pending(chat_id=999)
        assert cancelled == 0

    async def test_cancel_pending_marks_items_cancelled(
        self, queue_manager: QueueManager[int]
    ) -> None:
        """cancel_pending marks all items as cancelled."""
        await queue_manager.enqueue(chat_id=100, item=1)
        await queue_manager.enqueue(chat_id=100, item=2)

        await queue_manager.cancel_pending(chat_id=100)

        # Try to dequeue - should timeout as all items are cancelled
        result = await queue_manager.dequeue(chat_id=100, timeout=0.1)
        assert result is None

    async def test_cancel_pending_idempotent(self, queue_manager: QueueManager[int]) -> None:
        """Calling cancel_pending multiple times doesn't recount."""
        await queue_manager.enqueue(chat_id=100, item=1)
        await queue_manager.enqueue(chat_id=100, item=2)

        first_cancel = await queue_manager.cancel_pending(chat_id=100)
        second_cancel = await queue_manager.cancel_pending(chat_id=100)

        assert first_cancel == 2
        assert second_cancel == 0  # Already cancelled


@pytest.mark.asyncio
@pytest.mark.unit
class TestQueueManagerQueueSize:
    """Tests for QueueManager.queue_size."""

    async def test_queue_size_returns_count(self, queue_manager: QueueManager[int]) -> None:
        """queue_size returns the number of items in queue."""
        assert queue_manager.queue_size(chat_id=100) == 0

        await queue_manager.enqueue(chat_id=100, item=1)
        assert queue_manager.queue_size(chat_id=100) == 1

        await queue_manager.enqueue(chat_id=100, item=2)
        assert queue_manager.queue_size(chat_id=100) == 2

    async def test_queue_size_nonexistent_chat_returns_zero(
        self, queue_manager: QueueManager[int]
    ) -> None:
        """queue_size returns 0 for nonexistent chat_id."""
        assert queue_manager.queue_size(chat_id=999) == 0

    async def test_queue_size_decreases_after_dequeue(
        self, queue_manager: QueueManager[int]
    ) -> None:
        """queue_size decreases after successful dequeue."""
        await queue_manager.enqueue(chat_id=100, item=1)
        await queue_manager.enqueue(chat_id=100, item=2)
        assert queue_manager.queue_size(chat_id=100) == 2

        await queue_manager.dequeue(chat_id=100, timeout=1.0)
        assert queue_manager.queue_size(chat_id=100) == 1


@pytest.mark.asyncio
@pytest.mark.unit
class TestQueueManagerCleanup:
    """Tests for QueueManager.cleanup_inactive."""

    async def test_cleanup_removes_old_empty_queues(self, queue_manager: QueueManager[int]) -> None:
        """cleanup_inactive removes queues inactive beyond threshold."""
        await queue_manager.enqueue(chat_id=100, item=1)
        await queue_manager.dequeue(chat_id=100, timeout=1.0)  # Empty the queue

        # Manually set last_activity to the past
        queue_manager._last_activity[100] = datetime.now(UTC) - timedelta(hours=2)

        removed = await queue_manager.cleanup_inactive(threshold=3600.0)
        assert removed == 1
        assert queue_manager.active_queue_count() == 0

    async def test_cleanup_keeps_non_empty_queues(self, queue_manager: QueueManager[int]) -> None:
        """cleanup_inactive keeps queues that still have items."""
        await queue_manager.enqueue(chat_id=100, item=1)

        # Manually set last_activity to the past
        queue_manager._last_activity[100] = datetime.now(UTC) - timedelta(hours=2)

        removed = await queue_manager.cleanup_inactive(threshold=3600.0)
        assert removed == 0
        assert queue_manager.active_queue_count() == 1

    async def test_cleanup_keeps_recently_active_queues(
        self, queue_manager: QueueManager[int]
    ) -> None:
        """cleanup_inactive keeps recently active empty queues."""
        await queue_manager.enqueue(chat_id=100, item=1)
        await queue_manager.dequeue(chat_id=100, timeout=1.0)

        # Last activity is recent
        removed = await queue_manager.cleanup_inactive(threshold=3600.0)
        assert removed == 0


@pytest.mark.asyncio
@pytest.mark.unit
class TestQueueManagerShutdown:
    """Tests for QueueManager.shutdown."""

    async def test_shutdown_cancels_all_items(self, queue_manager: QueueManager[int]) -> None:
        """shutdown cancels all pending items across all queues."""
        await queue_manager.enqueue(chat_id=100, item=1)
        await queue_manager.enqueue(chat_id=100, item=2)
        await queue_manager.enqueue(chat_id=200, item=1)

        await queue_manager.shutdown()

        assert queue_manager.active_queue_count() == 0

    async def test_shutdown_clears_queues(self, queue_manager: QueueManager[int]) -> None:
        """shutdown removes all queues."""
        await queue_manager.enqueue(chat_id=100, item=1)
        await queue_manager.enqueue(chat_id=200, item=1)

        await queue_manager.shutdown()

        assert queue_manager.active_queue_count() == 0
        assert queue_manager.queue_size(chat_id=100) == 0
        assert queue_manager.queue_size(chat_id=200) == 0


@pytest.mark.asyncio
@pytest.mark.unit
class TestQueueManagerConstants:
    """Tests for module constants."""

    async def test_default_dequeue_timeout_is_reasonable(self) -> None:
        """DEFAULT_DEQUEUE_TIMEOUT is reasonable (5 minutes)."""
        assert DEFAULT_DEQUEUE_TIMEOUT >= 60  # At least 1 minute
        assert DEFAULT_DEQUEUE_TIMEOUT <= 600  # At most 10 minutes

    async def test_inactive_queue_threshold_is_reasonable(self) -> None:
        """INACTIVE_QUEUE_THRESHOLD is reasonable (1 hour)."""
        assert INACTIVE_QUEUE_THRESHOLD >= 1800  # At least 30 minutes
        assert INACTIVE_QUEUE_THRESHOLD <= 7200  # At most 2 hours
