"""Telegram-specific errors."""


class TelegramError(Exception):
    """Base exception for Telegram integration errors."""


class TelegramAuthError(TelegramError):
    """Raised when user authentication fails."""


class TelegramFileError(TelegramError):
    """Raised when file operations fail."""


class TelegramRunError(TelegramError):
    """Raised when run execution fails."""
