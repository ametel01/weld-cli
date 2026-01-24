"""Telegram-specific errors."""


class TelegramError(Exception):
    """Base exception for Telegram integration errors."""


class TelegramAuthError(TelegramError):
    """Raised when user authentication fails."""


class TelegramRunError(TelegramError):
    """Raised when run execution fails."""


# Re-export file path errors for unified error imports
# These are defined in files.py to avoid circular imports but are part of the error hierarchy
from weld.telegram.files import (  # noqa: E402
    FilePathError,
    PathNotAllowedError,
    PathNotFoundError,
    PathTraversalError,
)

__all__ = [
    "FilePathError",
    "PathNotAllowedError",
    "PathNotFoundError",
    "PathTraversalError",
    "TelegramAuthError",
    "TelegramError",
    "TelegramRunError",
]
