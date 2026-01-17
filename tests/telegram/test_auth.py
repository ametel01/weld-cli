"""Tests for Telegram bot authentication."""

import pytest

from weld.telegram.auth import check_auth
from weld.telegram.config import TelegramAuth, TelegramConfig
from weld.telegram.errors import TelegramAuthError


@pytest.mark.unit
class TestCheckAuth:
    """Tests for check_auth function."""

    def test_raises_when_user_not_allowed(self) -> None:
        """check_auth raises TelegramAuthError when user is not in allowlist."""
        config = TelegramConfig(auth=TelegramAuth(allowed_user_ids=[12345]))
        with pytest.raises(TelegramAuthError, match="not authorized"):
            check_auth(99999, config)

    def test_passes_when_user_id_allowed(self) -> None:
        """check_auth does not raise when user ID is in allowlist."""
        config = TelegramConfig(auth=TelegramAuth(allowed_user_ids=[12345]))
        # Should not raise
        check_auth(12345, config)

    def test_passes_when_username_allowed(self) -> None:
        """check_auth does not raise when username is in allowlist."""
        config = TelegramConfig(auth=TelegramAuth(allowed_usernames=["alice"]))
        # Should not raise
        check_auth(99999, config, username="alice")

    def test_raises_when_allowlists_empty(self) -> None:
        """check_auth raises when both allowlists are empty."""
        config = TelegramConfig()
        with pytest.raises(TelegramAuthError, match="not authorized"):
            check_auth(12345, config)

    def test_raises_with_none_user_id(self) -> None:
        """check_auth raises when user_id is None and username not allowed."""
        config = TelegramConfig(auth=TelegramAuth(allowed_user_ids=[12345]))
        with pytest.raises(TelegramAuthError, match="not authorized"):
            check_auth(None, config)

    def test_passes_with_none_user_id_but_username_allowed(self) -> None:
        """check_auth passes when user_id is None but username is allowed."""
        config = TelegramConfig(auth=TelegramAuth(allowed_usernames=["alice"]))
        # Should not raise
        check_auth(None, config, username="alice")

    def test_error_message_includes_user_id(self) -> None:
        """Error message includes the user ID."""
        config = TelegramConfig(auth=TelegramAuth(allowed_user_ids=[12345]))
        with pytest.raises(TelegramAuthError, match="user_id=99999"):
            check_auth(99999, config)

    def test_error_message_includes_username_when_provided(self) -> None:
        """Error message includes username when provided."""
        config = TelegramConfig(auth=TelegramAuth(allowed_user_ids=[12345]))
        with pytest.raises(TelegramAuthError, match="user_id=99999, username=eve"):
            check_auth(99999, config, username="eve")

    def test_error_message_handles_none_user_id(self) -> None:
        """Error message handles None user ID gracefully."""
        config = TelegramConfig(auth=TelegramAuth(allowed_user_ids=[12345]))
        with pytest.raises(TelegramAuthError, match="user_id=None"):
            check_auth(None, config)
