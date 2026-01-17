"""Telegram configuration model."""

from typing import Self

from pydantic import BaseModel, model_validator


class TelegramConfig(BaseModel):
    """Configuration for Telegram notifications."""

    bot_token: str | None = None
    chat_id: str | None = None
    enabled: bool = False

    @model_validator(mode="after")
    def validate_enabled_requires_credentials(self) -> Self:
        """Ensure bot_token and chat_id are provided when enabled."""
        if self.enabled:
            missing = []
            if not self.bot_token:
                missing.append("bot_token")
            if not self.chat_id:
                missing.append("chat_id")
            if missing:
                raise ValueError(
                    f"Telegram is enabled but missing required fields: {', '.join(missing)}"
                )
        return self
