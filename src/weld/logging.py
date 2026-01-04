"""Logging configuration for weld CLI."""

import logging
import sys
from enum import IntEnum
from typing import TextIO

from rich.console import Console
from rich.logging import RichHandler


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
) -> Console:
    """Configure logging based on CLI options.

    Args:
        verbosity: Number of -v flags (0=normal, 1=verbose, 2+=debug)
        quiet: Suppress non-error output
        no_color: Disable colored output
        stream: Output stream for logs

    Returns:
        Configured Rich console for output
    """
    if quiet:
        level = LogLevel.QUIET
    elif verbosity >= 2:
        level = logging.DEBUG
    elif verbosity >= 1:
        level = LogLevel.VERBOSE
    else:
        level = LogLevel.NORMAL

    console = Console(
        stderr=True,
        force_terminal=not no_color if not no_color else False,
        no_color=no_color,
    )

    handler = RichHandler(
        console=console,
        show_time=verbosity >= 2,
        show_path=verbosity >= 2,
    )

    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[handler],
    )

    return console
