"""Telegram bot authentication."""

from weld.telegram.config import TelegramConfig
from weld.telegram.errors import TelegramAuthError


def check_auth(user_id: int | None, config: TelegramConfig, username: str | None = None) -> None:
    """Validate user against configured allowlist.

    Args:
        user_id: Telegram user ID to validate
        config: TelegramConfig containing auth settings
        username: Optional Telegram username (without @)

    Raises:
        TelegramAuthError: If user is not in the allowlist
    """
    if not config.auth.is_user_allowed(user_id, username):
        user_info = f"user_id={user_id}"
        if username:
            user_info += f", username={username}"
        raise TelegramAuthError(f"User not authorized: {user_info}")
