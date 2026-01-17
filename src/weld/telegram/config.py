"""Telegram bot configuration models."""

import logging
import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


class TelegramProject(BaseModel):
    """Registered project for Telegram bot access."""

    name: str = Field(..., description="Project name identifier")
    path: Path = Field(..., description="Absolute path to project directory")
    description: str | None = Field(default=None, description="Optional project description")

    def model_post_init(self, __context: object) -> None:
        """Ensure path is absolute."""
        if not self.path.is_absolute():
            object.__setattr__(self, "path", self.path.resolve())


class TelegramAuth(BaseModel):
    """User authentication configuration for Telegram bot."""

    allowed_user_ids: list[int] = Field(
        default_factory=list, description="List of Telegram user IDs allowed to use the bot"
    )
    allowed_usernames: list[str] = Field(
        default_factory=list, description="List of Telegram usernames allowed to use the bot"
    )

    def is_user_allowed(self, user_id: int | None, username: str | None) -> bool:
        """Check if a user is allowed to access the bot.

        Args:
            user_id: Telegram user ID
            username: Telegram username (without @)

        Returns:
            True if user is in allowlist, False otherwise.
            If both allowlists are empty, no users are allowed.
        """
        if not self.allowed_user_ids and not self.allowed_usernames:
            return False

        if user_id is not None and user_id in self.allowed_user_ids:
            return True

        return bool(username and username in self.allowed_usernames)


class TelegramConfig(BaseModel):
    """Configuration for Telegram bot integration."""

    bot_token: str | None = Field(default=None, description="Telegram bot API token")
    projects: list[TelegramProject] = Field(
        default_factory=list, description="Registered projects accessible via bot"
    )
    auth: TelegramAuth = Field(
        default_factory=TelegramAuth, description="User authentication settings"
    )

    def get_project(self, name: str) -> TelegramProject | None:
        """Get a project by name.

        Args:
            name: Project name to look up

        Returns:
            TelegramProject if found, None otherwise
        """
        for project in self.projects:
            if project.name == name:
                return project
        return None

    def list_project_names(self) -> list[str]:
        """Get list of registered project names."""
        return [p.name for p in self.projects]


def get_config_path() -> Path:
    """Get the path to the Telegram bot config file.

    Returns:
        Path to ~/.config/weld/telegram.toml
    """
    config_dir = Path.home() / ".config" / "weld"
    return config_dir / "telegram.toml"


def load_config(config_path: Path | None = None) -> TelegramConfig:
    """Load Telegram bot configuration from file.

    Args:
        config_path: Path to config file. Defaults to ~/.config/weld/telegram.toml

    Returns:
        Loaded TelegramConfig, or default config if file doesn't exist

    Raises:
        tomllib.TOMLDecodeError: If config file contains invalid TOML
        ValidationError: If config file contains invalid configuration values
    """
    if config_path is None:
        config_path = get_config_path()

    if not config_path.exists():
        logger.debug(f"Config file not found at {config_path}, using defaults")
        return TelegramConfig()

    try:
        with open(config_path, "rb") as f:
            config_dict = tomllib.load(f)
    except tomllib.TOMLDecodeError:
        logger.error(f"Invalid TOML in config file: {config_path}")
        raise

    # Convert project paths from strings to Path objects
    if "projects" in config_dict:
        for project in config_dict["projects"]:
            if "path" in project and isinstance(project["path"], str):
                project["path"] = Path(project["path"])

    try:
        return TelegramConfig.model_validate(config_dict)
    except ValidationError:
        logger.error(f"Invalid configuration in: {config_path}")
        raise


def save_config(config: TelegramConfig, config_path: Path | None = None) -> Path:
    """Save Telegram bot configuration to file.

    Creates parent directories if they don't exist.

    Note: The config file will contain the bot_token in plaintext.
    Ensure appropriate file permissions are set.

    Args:
        config: TelegramConfig to save
        config_path: Path to config file. Defaults to ~/.config/weld/telegram.toml

    Returns:
        Path to the saved config file

    Raises:
        PermissionError: If unable to write to config path
        OSError: If unable to create parent directories or write file
    """
    if config_path is None:
        config_path = get_config_path()

    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict with Path objects preserved, then stringify for TOML
    config_dict = config.model_dump(mode="python")

    # Convert Path objects to strings for TOML serialization
    if "projects" in config_dict:
        for project in config_dict["projects"]:
            if "path" in project and isinstance(project["path"], Path):
                project["path"] = str(project["path"])

    with open(config_path, "wb") as f:
        tomli_w.dump(config_dict, f)

    logger.info(f"Saved Telegram config to {config_path}")
    return config_path
