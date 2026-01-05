"""Logging configuration for weld CLI."""

import logging
import sys
from enum import IntEnum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO

from rich.console import Console
from rich.logging import RichHandler

# Debug file logging constants
DEBUG_LOG_FILE = "debug.log"
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
BACKUP_COUNT = 3


class LogLevel(IntEnum):
    """Log level enumeration."""

    QUIET = logging.WARNING
    NORMAL = logging.INFO
    VERBOSE = logging.DEBUG


def configure_logging(
    verbosity: int = 0,
    quiet: bool = False,
    no_color: bool = False,
    stream: TextIO = sys.stderr,
    debug: bool = False,
) -> Console:
    """Configure logging based on CLI options.

    Args:
        verbosity: Number of -v flags (0=normal, 1=verbose, 2+=debug)
        quiet: Suppress non-error output (takes precedence over debug/verbosity)
        no_color: Disable colored output
        stream: Output stream for logs
        debug: Enable debug logging (equivalent to -vv, ignored if quiet is set)

    Returns:
        Configured Rich console for output

    Note:
        Flag precedence: quiet > debug > verbosity
        - If quiet=True, log level is WARNING regardless of other flags
        - If debug=True (and not quiet), log level is DEBUG
        - Otherwise verbosity determines level: 0=INFO, 1=DEBUG, 2+=DEBUG
    """
    if quiet:
        level = LogLevel.QUIET
    elif debug or verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = LogLevel.VERBOSE
    else:
        level = LogLevel.NORMAL

    console = Console(
        stderr=True,
        force_terminal=not no_color,
        no_color=no_color,
    )

    handler = RichHandler(
        console=console,
        show_time=debug or verbosity >= 2,
        show_path=debug or verbosity >= 2,
    )

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[handler],
    )

    return console


def setup_debug_logging(weld_dir: Path, enabled: bool = False) -> None:
    """Configure file-based debug logging.

    When enabled, writes detailed debug logs to .weld/debug.log with
    automatic rotation to prevent unbounded growth.

    Args:
        weld_dir: Path to .weld directory
        enabled: Whether debug logging is enabled
    """
    if not enabled:
        return

    weld_logger = logging.getLogger("weld")

    # Prevent duplicate handlers if called multiple times
    if any(isinstance(h, RotatingFileHandler) for h in weld_logger.handlers):
        return

    # Ensure weld_dir exists before creating log file
    weld_dir.mkdir(parents=True, exist_ok=True)

    log_path = weld_dir / DEBUG_LOG_FILE
    handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
    )
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    handler.setLevel(logging.DEBUG)

    weld_logger.addHandler(handler)
    # Only lower the logger level if needed (don't override higher verbosity)
    if weld_logger.level == logging.NOTSET or weld_logger.level > logging.DEBUG:
        weld_logger.setLevel(logging.DEBUG)
