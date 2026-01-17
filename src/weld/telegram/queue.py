"""Per-chat FIFO queue for run ordering in Telegram bot."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

# Default timeout for dequeue operations (5 minutes)
DEFAULT_DEQUEUE_TIMEOUT = 300.0

# Cleanup threshold: remove queues inactive for this many seconds
INACTIVE_QUEUE_THRESHOLD = 3600.0  # 1 hour

T = TypeVar("T")


@dataclass
class QueuedItem(Generic[T]):
    """Item wrapper with metadata for queue tracking."""

    item: T
    enqueued_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    cancelled: bool = False


class QueueManager(Generic[T]):
    """Manages per-chat FIFO queues for run ordering.

    Each chat_id gets its own asyncio.Queue to ensure runs are processed
    in order within that chat while allowing concurrent processing across
    different chats.

    Type parameter T represents the type of items stored in the queue
    (typically run IDs or Run objects).

    Example:
        queue_manager: QueueManager[int] = QueueManager()

        # Enqueue a run
        position = await queue_manager.enqueue(chat_id=123, item=run_id)
        print(f"Run queued at position {position}")

        # Process runs (consumer loop)
        async def consumer(chat_id: int):
            while True:
                item = await queue_manager.dequeue(chat_id, timeout=60.0)
                if item is None:
                    break  # Timeout or queue cancelled
                await process_run(item)

        # Get queue position
        pos = queue_manager.get_position(chat_id=123, item=run_id)

        # Cancel pending items
        cancelled = await queue_manager.cancel_pending(chat_id=123)
    """

    def __init__(self, max_queue_size: int = 100) -> None:
        """Initialize queue manager.

        Args:
            max_queue_size: Maximum items per chat queue (prevents memory exhaustion)
        """
        self._queues: dict[int, asyncio.Queue[QueuedItem[T]]] = {}
        self._max_queue_size = max_queue_size
        self._last_activity: dict[int, datetime] = {}
        self._lock = asyncio.Lock()

    def _get_or_create_queue(self, chat_id: int) -> asyncio.Queue[QueuedItem[T]]:
        """Get existing queue or create new one for chat_id."""
        if chat_id not in self._queues:
            self._queues[chat_id] = asyncio.Queue(maxsize=self._max_queue_size)
            logger.debug(f"Created new queue for chat_id={chat_id}")
        self._last_activity[chat_id] = datetime.now(UTC)
        return self._queues[chat_id]

    async def enqueue(self, chat_id: int, item: T, timeout: float | None = 10.0) -> int:
        """Add an item to the chat's queue.

        Args:
            chat_id: Telegram chat ID
            item: Item to queue (typically run ID)
            timeout: Max time to wait if queue is full (None = block forever)

        Returns:
            Position in queue (1-based, 1 = next to be processed)

        Raises:
            asyncio.QueueFull: If queue is full and timeout expires
            asyncio.TimeoutError: If timeout expires waiting to enqueue
        """
        async with self._lock:
            queue = self._get_or_create_queue(chat_id)

        queued_item = QueuedItem(item=item)

        try:
            if timeout is not None:
                await asyncio.wait_for(queue.put(queued_item), timeout=timeout)
            else:
                await queue.put(queued_item)
        except TimeoutError:
            logger.warning(f"Timeout enqueuing item for chat_id={chat_id}")
            raise

        position = queue.qsize()
        logger.debug(f"Enqueued item for chat_id={chat_id}, position={position}")

        self._last_activity[chat_id] = datetime.now(UTC)
        return position

    async def dequeue(self, chat_id: int, timeout: float = DEFAULT_DEQUEUE_TIMEOUT) -> T | None:
        """Get the next item from the chat's queue.

        Blocks until an item is available or timeout expires. This prevents
        deadlock if the consumer dies - callers should handle None return
        by checking queue state and potentially retrying.

        Args:
            chat_id: Telegram chat ID
            timeout: Max time to wait for an item (prevents deadlock)

        Returns:
            The next item, or None if timeout expires or item was cancelled
        """
        async with self._lock:
            queue = self._get_or_create_queue(chat_id)

        try:
            queued_item = await asyncio.wait_for(queue.get(), timeout=timeout)
        except TimeoutError:
            logger.debug(f"Dequeue timeout for chat_id={chat_id}")
            return None

        self._last_activity[chat_id] = datetime.now(UTC)

        # Skip cancelled items
        if queued_item.cancelled:
            logger.debug(f"Skipping cancelled item for chat_id={chat_id}")
            queue.task_done()
            # Recursively get next non-cancelled item (with remaining timeout)
            return await self.dequeue(chat_id, timeout=timeout)

        queue.task_done()
        return queued_item.item

    def get_position(self, chat_id: int, item: T) -> int | None:
        """Get the queue position of an item.

        Args:
            chat_id: Telegram chat ID
            item: Item to find

        Returns:
            Position (1-based) if found, None if not in queue
        """
        if chat_id not in self._queues:
            return None

        queue = self._queues[chat_id]

        # Access internal queue list (implementation detail of asyncio.Queue)
        # This is safe for read-only access
        try:
            items = list(queue._queue)  # type: ignore[attr-defined]
        except AttributeError:
            # Fallback if internal structure changes
            logger.warning("Unable to inspect queue internals")
            return None

        for i, queued_item in enumerate(items):
            if not queued_item.cancelled and queued_item.item == item:
                return i + 1

        return None

    def queue_size(self, chat_id: int) -> int:
        """Get the current queue size for a chat.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Number of items in queue (0 if queue doesn't exist)
        """
        if chat_id not in self._queues:
            return 0
        return self._queues[chat_id].qsize()

    async def cancel_pending(self, chat_id: int) -> int:
        """Cancel all pending items in a chat's queue.

        Marks items as cancelled so they'll be skipped by dequeue.
        Does not affect items that have already been dequeued.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Number of items cancelled
        """
        if chat_id not in self._queues:
            return 0

        queue = self._queues[chat_id]
        cancelled_count = 0

        # Access internal queue list to mark items as cancelled
        try:
            items = list(queue._queue)  # type: ignore[attr-defined]
            for queued_item in items:
                if not queued_item.cancelled:
                    queued_item.cancelled = True
                    cancelled_count += 1
        except AttributeError:
            logger.warning("Unable to cancel queue items - internal structure unavailable")
            return 0

        if cancelled_count > 0:
            logger.info(f"Cancelled {cancelled_count} pending items for chat_id={chat_id}")

        return cancelled_count

    async def cleanup_inactive(self, threshold: float = INACTIVE_QUEUE_THRESHOLD) -> int:
        """Remove queues that have been inactive beyond threshold.

        Should be called periodically to prevent memory leaks from
        abandoned chats.

        Args:
            threshold: Seconds of inactivity before cleanup

        Returns:
            Number of queues removed
        """
        now = datetime.now(UTC)
        to_remove: list[int] = []

        async with self._lock:
            for chat_id, last_activity in self._last_activity.items():
                inactive_seconds = (now - last_activity).total_seconds()
                # Only remove empty queues that have been inactive
                if (
                    inactive_seconds > threshold
                    and chat_id in self._queues
                    and self._queues[chat_id].empty()
                ):
                    to_remove.append(chat_id)

            for chat_id in to_remove:
                del self._queues[chat_id]
                del self._last_activity[chat_id]
                logger.debug(f"Cleaned up inactive queue for chat_id={chat_id}")

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} inactive queues")

        return len(to_remove)

    def active_queue_count(self) -> int:
        """Get the number of active queues.

        Returns:
            Number of chat queues currently managed
        """
        return len(self._queues)

    def active_chat_ids(self) -> list[int]:
        """Get list of chat IDs with active queues.

        Returns:
            List of chat IDs that have queues (may be empty)
        """
        return list(self._queues.keys())

    async def shutdown(self) -> None:
        """Shutdown the queue manager, cancelling all pending items.

        Should be called during application shutdown.
        """
        async with self._lock:
            total_cancelled = 0
            for chat_id in list(self._queues.keys()):
                cancelled = await self.cancel_pending(chat_id)
                total_cancelled += cancelled

            self._queues.clear()
            self._last_activity.clear()

        if total_cancelled > 0:
            logger.info(f"Shutdown: cancelled {total_cancelled} pending items across all queues")
