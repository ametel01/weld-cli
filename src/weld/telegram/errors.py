"""Telegram-specific errors."""


class TelegramError(Exception):
    """Base exception for Telegram integration errors."""


class TelegramAuthError(TelegramError):
    """Raised when user authentication fails."""
