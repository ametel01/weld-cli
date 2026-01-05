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
