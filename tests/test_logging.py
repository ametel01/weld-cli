"""Tests for logging configuration."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from weld.logging import (
    BACKUP_COUNT,
    DEBUG_LOG_FILE,
    MAX_LOG_SIZE,
    setup_debug_logging,
)


class TestSetupDebugLogging:
    """Tests for setup_debug_logging function."""

    @pytest.fixture(autouse=True)
    def cleanup_handlers(self):
        """Remove any handlers added during tests."""
        weld_logger = logging.getLogger("weld")
        original_handlers = weld_logger.handlers.copy()
        original_level = weld_logger.level
        yield
        # Restore original state
        weld_logger.handlers = original_handlers
        weld_logger.level = original_level

    def test_creates_log_file_in_weld_dir(self, tmp_path: Path) -> None:
        """setup_debug_logging should create debug.log in weld directory."""
        weld_dir = tmp_path / ".weld"

        setup_debug_logging(weld_dir, enabled=True)

        log_path = weld_dir / DEBUG_LOG_FILE
        assert weld_dir.exists()
        # File may not exist until first log write, but handler should be configured
        weld_logger = logging.getLogger("weld")
        file_handlers = [h for h in weld_logger.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1
        assert file_handlers[0].baseFilename == str(log_path)

    def test_does_nothing_when_disabled(self, tmp_path: Path) -> None:
        """setup_debug_logging should not add handler when disabled."""
        weld_dir = tmp_path / ".weld"
        weld_logger = logging.getLogger("weld")
        initial_handler_count = len(weld_logger.handlers)

        setup_debug_logging(weld_dir, enabled=False)

        assert len(weld_logger.handlers) == initial_handler_count
        assert not weld_dir.exists()

    def test_prevents_duplicate_handlers(self, tmp_path: Path) -> None:
        """setup_debug_logging should not add duplicate handlers."""
        weld_dir = tmp_path / ".weld"

        # Call twice
        setup_debug_logging(weld_dir, enabled=True)
        setup_debug_logging(weld_dir, enabled=True)

        weld_logger = logging.getLogger("weld")
        file_handlers = [h for h in weld_logger.handlers if isinstance(h, RotatingFileHandler)]
        assert len(file_handlers) == 1

    def test_sets_logger_level_to_debug(self, tmp_path: Path) -> None:
        """setup_debug_logging should set logger level to DEBUG."""
        weld_dir = tmp_path / ".weld"
        weld_logger = logging.getLogger("weld")
        weld_logger.setLevel(logging.WARNING)  # Start with higher level

        setup_debug_logging(weld_dir, enabled=True)

        assert weld_logger.level == logging.DEBUG

    def test_handler_has_correct_rotation_settings(self, tmp_path: Path) -> None:
        """setup_debug_logging should configure rotation correctly."""
        weld_dir = tmp_path / ".weld"

        setup_debug_logging(weld_dir, enabled=True)

        weld_logger = logging.getLogger("weld")
        file_handlers = [h for h in weld_logger.handlers if isinstance(h, RotatingFileHandler)]
        handler = file_handlers[0]
        assert handler.maxBytes == MAX_LOG_SIZE
        assert handler.backupCount == BACKUP_COUNT

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """setup_debug_logging should create parent directories if needed."""
        weld_dir = tmp_path / "deep" / "nested" / ".weld"
        assert not weld_dir.exists()

        setup_debug_logging(weld_dir, enabled=True)

        assert weld_dir.exists()

    def test_log_format_includes_timestamp(self, tmp_path: Path) -> None:
        """setup_debug_logging should use format with timestamp."""
        weld_dir = tmp_path / ".weld"

        setup_debug_logging(weld_dir, enabled=True)

        weld_logger = logging.getLogger("weld")
        file_handlers = [h for h in weld_logger.handlers if isinstance(h, RotatingFileHandler)]
        handler = file_handlers[0]
        assert handler.formatter is not None
        # Check format contains asctime (access via _fmt attribute)
        fmt = getattr(handler.formatter, "_fmt", None)
        assert fmt is not None
        assert "asctime" in fmt

    def test_writes_debug_messages_to_file(self, tmp_path: Path) -> None:
        """setup_debug_logging should actually write debug messages."""
        weld_dir = tmp_path / ".weld"
        log_path = weld_dir / DEBUG_LOG_FILE

        setup_debug_logging(weld_dir, enabled=True)

        weld_logger = logging.getLogger("weld")
        weld_logger.debug("Test debug message")

        # Force flush
        for handler in weld_logger.handlers:
            handler.flush()

        assert log_path.exists()
        content = log_path.read_text()
        assert "Test debug message" in content
        assert "DEBUG" in content
