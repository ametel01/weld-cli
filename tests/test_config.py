"""Tests for weld configuration."""

from pathlib import Path

import pytest

from weld.config import (
    ClaudeConfig,
    CodexConfig,
    ModelConfig,
    TaskModelsConfig,
    TaskType,
    TranscriptsConfig,
    WeldConfig,
    load_config,
    write_config_template,
)


def test_default_task_models():
    """Default task models should be set correctly."""
    config = WeldConfig()

    # Discovery phase defaults to Claude
    discover = config.get_task_model(TaskType.DISCOVER)
    assert discover.provider == "claude"

    interview = config.get_task_model(TaskType.INTERVIEW)
    assert interview.provider == "claude"

    # Research phase defaults
    research = config.get_task_model(TaskType.RESEARCH)
    assert research.provider == "claude"

    research_review = config.get_task_model(TaskType.RESEARCH_REVIEW)
    assert research_review.provider == "codex"

    # Plan generation defaults to Claude
    plan_gen = config.get_task_model(TaskType.PLAN_GENERATION)
    assert plan_gen.provider == "claude"

    # Plan review defaults to Codex
    plan_review = config.get_task_model(TaskType.PLAN_REVIEW)
    assert plan_review.provider == "codex"

    # Implementation defaults to Claude
    impl = config.get_task_model(TaskType.IMPLEMENTATION)
    assert impl.provider == "claude"

    # Implementation review defaults to Codex
    impl_review = config.get_task_model(TaskType.IMPLEMENTATION_REVIEW)
    assert impl_review.provider == "codex"

    # Fix generation defaults to Claude
    fix = config.get_task_model(TaskType.FIX_GENERATION)
    assert fix.provider == "claude"


def test_custom_task_models():
    """Custom task model assignments should override defaults."""
    config = WeldConfig(
        task_models=TaskModelsConfig(
            plan_review=ModelConfig(provider="claude", model="claude-3-opus"),
            implementation_review=ModelConfig(provider="openai", model="gpt-4o"),
        )
    )

    # Plan review should use Claude with specific model
    plan_review = config.get_task_model(TaskType.PLAN_REVIEW)
    assert plan_review.provider == "claude"
    assert plan_review.model == "claude-3-opus"

    # Implementation review should use custom provider
    impl_review = config.get_task_model(TaskType.IMPLEMENTATION_REVIEW)
    assert impl_review.provider == "openai"
    assert impl_review.model == "gpt-4o"


def test_model_config_inherits_provider_defaults():
    """Task model should inherit defaults from provider config."""
    config = WeldConfig(
        codex=CodexConfig(exec="custom-codex", model="o3"),
        claude=ClaudeConfig(exec="custom-claude", model="claude-3-sonnet"),
    )

    # Codex task should inherit from codex config
    plan_review = config.get_task_model(TaskType.PLAN_REVIEW)
    assert plan_review.exec == "custom-codex"
    assert plan_review.model == "o3"

    # Claude task should inherit from claude config
    impl = config.get_task_model(TaskType.IMPLEMENTATION)
    assert impl.exec == "custom-claude"
    assert impl.model == "claude-3-sonnet"


def test_task_specific_override_beats_provider_default():
    """Task-specific model should override provider default."""
    config = WeldConfig(
        codex=CodexConfig(exec="codex", model="default-model"),
        task_models=TaskModelsConfig(
            plan_review=ModelConfig(provider="codex", model="specific-model"),
        ),
    )

    plan_review = config.get_task_model(TaskType.PLAN_REVIEW)
    assert plan_review.model == "specific-model"


class TestChecksConfigCategories:
    """Tests for multi-category checks configuration."""

    def test_get_categories_returns_enabled_only(self) -> None:
        """Only categories with commands are returned."""
        from weld.config import ChecksConfig

        cfg = ChecksConfig(lint="ruff check .", test=None, typecheck="pyright")
        categories = cfg.get_categories()
        assert categories == {"lint": "ruff check .", "typecheck": "pyright"}

    def test_get_categories_respects_order(self) -> None:
        """Categories returned in configured order."""
        from weld.config import ChecksConfig

        cfg = ChecksConfig(
            lint="ruff",
            test="pytest",
            typecheck="pyright",
            order=["test", "lint", "typecheck"],
        )
        assert list(cfg.get_categories().keys()) == ["test", "lint", "typecheck"]

    def test_is_legacy_mode_true_when_only_command(self) -> None:
        """Legacy mode when only command field is set."""
        from weld.config import ChecksConfig

        cfg = ChecksConfig(command="make check")
        assert cfg.is_legacy_mode() is True

    def test_is_legacy_mode_false_when_categories_set(self) -> None:
        """Not legacy mode when category commands exist."""
        from weld.config import ChecksConfig

        cfg = ChecksConfig(lint="ruff", command="make check")
        assert cfg.is_legacy_mode() is False

    def test_default_has_no_categories(self) -> None:
        """Default config has no enabled categories."""
        from weld.config import ChecksConfig

        cfg = ChecksConfig()
        assert cfg.get_categories() == {}
        assert cfg.is_legacy_mode() is False


class TestTranscriptsConfig:
    """Tests for TranscriptsConfig."""

    def test_default_values(self) -> None:
        """TranscriptsConfig should have correct defaults."""
        config = TranscriptsConfig()
        assert config.enabled is True
        assert config.visibility == "secret"

    def test_custom_values(self) -> None:
        """TranscriptsConfig should accept custom values."""
        config = TranscriptsConfig(enabled=False, visibility="public")
        assert config.enabled is False
        assert config.visibility == "public"

    def test_weld_config_has_transcripts(self) -> None:
        """WeldConfig should have top-level transcripts field."""
        config = WeldConfig()
        assert hasattr(config, "transcripts")
        assert isinstance(config.transcripts, TranscriptsConfig)
        assert config.transcripts.enabled is True

    def test_claude_config_no_transcripts(self) -> None:
        """ClaudeConfig should not have transcripts field."""
        config = ClaudeConfig()
        assert not hasattr(config, "transcripts")


class TestLoadConfigMigration:
    """Tests for config migration in load_config."""

    def test_loads_new_format(self, tmp_path: Path) -> None:
        """load_config should load new top-level transcripts format."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        config_file = weld_dir / "config.toml"
        config_file.write_text("""
[project]
name = "test-project"

[transcripts]
enabled = false
visibility = "public"
""")
        config = load_config(weld_dir)
        assert config.project.name == "test-project"
        assert config.transcripts.enabled is False
        assert config.transcripts.visibility == "public"

    def test_migrates_old_format(self, tmp_path: Path) -> None:
        """load_config should migrate old claude.transcripts to top-level."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        config_file = weld_dir / "config.toml"
        config_file.write_text("""
[project]
name = "old-project"

[claude]
timeout = 1800

[claude.transcripts]
visibility = "public"
""")
        config = load_config(weld_dir)
        assert config.project.name == "old-project"
        # Old transcripts.visibility should be migrated
        assert config.transcripts.visibility == "public"
        # enabled should use default since it didn't exist in old format
        assert config.transcripts.enabled is True

    def test_migration_ignores_old_fields(
        self, tmp_path: Path, caplog: "pytest.LogCaptureFixture"
    ) -> None:
        """load_config should ignore old exec field during migration."""
        import logging

        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        config_file = weld_dir / "config.toml"
        config_file.write_text("""
[claude.transcripts]
exec = "old-transcript-binary"
visibility = "secret"
""")
        with caplog.at_level(logging.INFO):
            config = load_config(weld_dir)

        assert config.transcripts.visibility == "secret"
        assert "no longer used" in caplog.text

    def test_new_format_takes_precedence(self, tmp_path: Path) -> None:
        """When both old and new format exist, migration updates new format."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        config_file = weld_dir / "config.toml"
        # This would be an unusual config, but test the behavior
        config_file.write_text("""
[transcripts]
enabled = false
visibility = "public"

[claude.transcripts]
visibility = "secret"
""")
        config = load_config(weld_dir)
        # The old visibility="secret" overwrites the new visibility="public"
        assert config.transcripts.visibility == "secret"

    def test_returns_defaults_when_no_config(self, tmp_path: Path) -> None:
        """load_config should return defaults when config.toml doesn't exist."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        # No config.toml file
        config = load_config(weld_dir)
        assert config.transcripts.enabled is True
        assert config.transcripts.visibility == "secret"


class TestWriteConfigTemplate:
    """Tests for write_config_template."""

    def test_writes_new_transcripts_format(self, tmp_path: Path) -> None:
        """write_config_template should write new top-level transcripts."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        config_path = write_config_template(weld_dir)

        assert config_path.exists()
        content = config_path.read_text()
        # Should have top-level [transcripts] section
        assert "[transcripts]" in content
        assert "enabled" in content
        # Should NOT have old nested format
        assert "[claude.transcripts]" not in content

    def test_template_loads_correctly(self, tmp_path: Path) -> None:
        """Template written by write_config_template should load correctly."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()

        write_config_template(weld_dir)
        config = load_config(weld_dir)

        assert config.transcripts.enabled is True
        assert config.transcripts.visibility == "secret"
