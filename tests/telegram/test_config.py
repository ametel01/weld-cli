"""Tests for Telegram bot configuration."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from weld.telegram.config import (
    TelegramAuth,
    TelegramConfig,
    TelegramProject,
    load_config,
    save_config,
)


@pytest.mark.unit
class TestTelegramProject:
    """Tests for TelegramProject model."""

    def test_create_with_absolute_path(self, tmp_path: Path) -> None:
        """Project with absolute path should keep it as-is."""
        project = TelegramProject(name="test", path=tmp_path)
        assert project.path == tmp_path
        assert project.path.is_absolute()

    def test_create_with_relative_path_resolves(self) -> None:
        """Project with relative path should resolve to absolute."""
        project = TelegramProject(name="test", path=Path("relative/path"))
        assert project.path.is_absolute()

    def test_description_is_optional(self, tmp_path: Path) -> None:
        """Project description should be optional."""
        project = TelegramProject(name="test", path=tmp_path)
        assert project.description is None

    def test_description_can_be_set(self, tmp_path: Path) -> None:
        """Project description can be provided."""
        project = TelegramProject(name="test", path=tmp_path, description="Test project")
        assert project.description == "Test project"

    def test_name_required(self, tmp_path: Path) -> None:
        """Project name is required."""
        with pytest.raises(ValidationError):
            TelegramProject(path=tmp_path)  # type: ignore[call-arg]

    def test_path_required(self) -> None:
        """Project path is required."""
        with pytest.raises(ValidationError):
            TelegramProject(name="test")  # type: ignore[call-arg]


@pytest.mark.unit
class TestTelegramAuth:
    """Tests for TelegramAuth model."""

    def test_default_empty_allowlists(self) -> None:
        """Default auth has empty allowlists."""
        auth = TelegramAuth()
        assert auth.allowed_user_ids == []
        assert auth.allowed_usernames == []

    def test_is_user_allowed_empty_allowlists(self) -> None:
        """No users allowed when both allowlists are empty."""
        auth = TelegramAuth()
        assert auth.is_user_allowed(12345, "testuser") is False
        assert auth.is_user_allowed(None, None) is False

    def test_is_user_allowed_by_user_id(self) -> None:
        """User allowed if ID is in allowlist."""
        auth = TelegramAuth(allowed_user_ids=[12345, 67890])
        assert auth.is_user_allowed(12345, None) is True
        assert auth.is_user_allowed(67890, "someuser") is True
        assert auth.is_user_allowed(11111, None) is False

    def test_is_user_allowed_by_username(self) -> None:
        """User allowed if username is in allowlist."""
        auth = TelegramAuth(allowed_usernames=["alice", "bob"])
        assert auth.is_user_allowed(None, "alice") is True
        assert auth.is_user_allowed(99999, "bob") is True
        assert auth.is_user_allowed(None, "eve") is False

    def test_is_user_allowed_both_criteria(self) -> None:
        """User allowed if either ID or username matches."""
        auth = TelegramAuth(allowed_user_ids=[12345], allowed_usernames=["alice"])
        # ID matches
        assert auth.is_user_allowed(12345, "eve") is True
        # Username matches
        assert auth.is_user_allowed(99999, "alice") is True
        # Neither matches
        assert auth.is_user_allowed(99999, "eve") is False

    def test_is_user_allowed_none_values(self) -> None:
        """Handle None user_id and username correctly."""
        auth = TelegramAuth(allowed_user_ids=[12345], allowed_usernames=["alice"])
        assert auth.is_user_allowed(None, "alice") is True
        assert auth.is_user_allowed(12345, None) is True
        assert auth.is_user_allowed(None, None) is False


@pytest.mark.unit
class TestTelegramConfig:
    """Tests for TelegramConfig model."""

    def test_default_values(self) -> None:
        """Default config has expected values."""
        config = TelegramConfig()
        assert config.bot_token is None
        assert config.projects == []
        assert isinstance(config.auth, TelegramAuth)

    def test_bot_token_can_be_set(self) -> None:
        """Bot token can be configured."""
        config = TelegramConfig(bot_token="123:ABC")
        assert config.bot_token == "123:ABC"

    def test_get_project_found(self, tmp_path: Path) -> None:
        """get_project returns project when found."""
        project = TelegramProject(name="myproject", path=tmp_path)
        config = TelegramConfig(projects=[project])
        result = config.get_project("myproject")
        assert result is not None
        assert result.name == "myproject"

    def test_get_project_not_found(self) -> None:
        """get_project returns None when not found."""
        config = TelegramConfig()
        result = config.get_project("nonexistent")
        assert result is None

    def test_list_project_names(self, tmp_path: Path) -> None:
        """list_project_names returns all project names."""
        projects = [
            TelegramProject(name="proj1", path=tmp_path / "a"),
            TelegramProject(name="proj2", path=tmp_path / "b"),
        ]
        config = TelegramConfig(projects=projects)
        names = config.list_project_names()
        assert names == ["proj1", "proj2"]

    def test_list_project_names_empty(self) -> None:
        """list_project_names returns empty list when no projects."""
        config = TelegramConfig()
        assert config.list_project_names() == []


@pytest.mark.unit
class TestLoadConfig:
    """Tests for load_config function."""

    def test_returns_default_when_file_missing(self, tmp_path: Path) -> None:
        """Returns default config when file doesn't exist."""
        config_path = tmp_path / "telegram.toml"
        config = load_config(config_path)
        assert config.bot_token is None
        assert config.projects == []

    def test_loads_basic_config(self, tmp_path: Path) -> None:
        """Loads bot token from file."""
        config_path = tmp_path / "telegram.toml"
        config_path.write_text('bot_token = "123:ABC"\n')
        config = load_config(config_path)
        assert config.bot_token == "123:ABC"

    def test_loads_auth_config(self, tmp_path: Path) -> None:
        """Loads auth configuration from file."""
        config_path = tmp_path / "telegram.toml"
        config_path.write_text("""
[auth]
allowed_user_ids = [12345, 67890]
allowed_usernames = ["alice", "bob"]
""")
        config = load_config(config_path)
        assert config.auth.allowed_user_ids == [12345, 67890]
        assert config.auth.allowed_usernames == ["alice", "bob"]

    def test_loads_projects(self, tmp_path: Path) -> None:
        """Loads project list from file."""
        config_path = tmp_path / "telegram.toml"
        config_path.write_text(f"""
[[projects]]
name = "project1"
path = "{tmp_path / "proj1"}"
description = "First project"

[[projects]]
name = "project2"
path = "{tmp_path / "proj2"}"
""")
        config = load_config(config_path)
        assert len(config.projects) == 2
        assert config.projects[0].name == "project1"
        assert config.projects[0].description == "First project"
        assert config.projects[1].name == "project2"
        assert config.projects[1].description is None

    def test_raises_on_invalid_toml(self, tmp_path: Path) -> None:
        """Raises error on invalid TOML syntax."""
        import tomllib

        config_path = tmp_path / "telegram.toml"
        config_path.write_text("invalid [ toml")
        with pytest.raises(tomllib.TOMLDecodeError):
            load_config(config_path)

    def test_raises_on_invalid_values(self, tmp_path: Path) -> None:
        """Raises ValidationError on invalid config values."""
        config_path = tmp_path / "telegram.toml"
        # auth.allowed_user_ids should be list of ints, not strings
        config_path.write_text("""
[auth]
allowed_user_ids = ["not", "integers"]
""")
        with pytest.raises(ValidationError):
            load_config(config_path)


@pytest.mark.unit
class TestSaveConfig:
    """Tests for save_config function."""

    def test_saves_to_specified_path(self, tmp_path: Path) -> None:
        """Saves config to specified path."""
        config_path = tmp_path / "config" / "telegram.toml"
        config = TelegramConfig(bot_token="123:ABC")
        result = save_config(config, config_path)
        assert result == config_path
        assert config_path.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Creates parent directories if they don't exist."""
        config_path = tmp_path / "nested" / "config" / "telegram.toml"
        config = TelegramConfig()
        save_config(config, config_path)
        assert config_path.exists()

    def test_roundtrip_basic_config(self, tmp_path: Path) -> None:
        """Config can be saved and loaded back correctly."""
        config_path = tmp_path / "telegram.toml"
        original = TelegramConfig(bot_token="test-token")
        save_config(original, config_path)
        loaded = load_config(config_path)
        assert loaded.bot_token == original.bot_token

    def test_roundtrip_auth_config(self, tmp_path: Path) -> None:
        """Auth config survives roundtrip."""
        config_path = tmp_path / "telegram.toml"
        original = TelegramConfig(
            auth=TelegramAuth(
                allowed_user_ids=[12345, 67890],
                allowed_usernames=["alice", "bob"],
            )
        )
        save_config(original, config_path)
        loaded = load_config(config_path)
        assert loaded.auth.allowed_user_ids == original.auth.allowed_user_ids
        assert loaded.auth.allowed_usernames == original.auth.allowed_usernames

    def test_roundtrip_projects(self, tmp_path: Path) -> None:
        """Projects survive roundtrip."""
        config_path = tmp_path / "telegram.toml"
        project_path = tmp_path / "myproject"
        original = TelegramConfig(
            projects=[
                TelegramProject(
                    name="test",
                    path=project_path,
                    description="Test project",
                )
            ]
        )
        save_config(original, config_path)
        loaded = load_config(config_path)
        assert len(loaded.projects) == 1
        assert loaded.projects[0].name == "test"
        assert loaded.projects[0].path == project_path
        assert loaded.projects[0].description == "Test project"

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Overwrites existing config file."""
        config_path = tmp_path / "telegram.toml"
        config_path.write_text('bot_token = "old-token"\n')
        new_config = TelegramConfig(bot_token="new-token")
        save_config(new_config, config_path)
        loaded = load_config(config_path)
        assert loaded.bot_token == "new-token"

    def test_roundtrip_with_none_values(self, tmp_path: Path) -> None:
        """Config with None values roundtrips correctly (TOML excludes null)."""
        config_path = tmp_path / "telegram.toml"
        # Default config has bot_token=None and empty lists
        original = TelegramConfig()
        save_config(original, config_path)

        # Verify TOML doesn't contain bot_token (excluded due to None)
        content = config_path.read_text()
        assert "bot_token" not in content

        # Roundtrip should preserve None default
        loaded = load_config(config_path)
        assert loaded.bot_token is None
        assert loaded.projects == []
