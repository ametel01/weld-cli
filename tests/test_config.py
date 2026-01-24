"""Tests for weld configuration."""

from pathlib import Path

import pytest

from weld.config import (
    ClaudeConfig,
    CodexConfig,
    ModelConfig,
    PromptCustomization,
    PromptsConfig,
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

    def test_migrates_enabled_field(self, tmp_path: Path) -> None:
        """load_config should migrate enabled field from claude.transcripts."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        config_file = weld_dir / "config.toml"
        config_file.write_text("""
[claude.transcripts]
enabled = false
visibility = "secret"
""")
        config = load_config(weld_dir)

        # Both fields should be migrated
        assert config.transcripts.enabled is False
        assert config.transcripts.visibility == "secret"

        # Verify file was updated (migration persisted)
        content = config_file.read_text()
        assert "[transcripts]" in content
        assert "[claude.transcripts]" not in content

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

    def test_migration_creates_backup_file(self, tmp_path: Path) -> None:
        """load_config should create .toml.bak backup when migrating."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        config_file = weld_dir / "config.toml"
        config_file.write_text("""
[claude.transcripts]
visibility = "public"
""")
        backup_file = weld_dir / "config.toml.bak"
        assert not backup_file.exists()

        # Load config - should trigger migration
        config = load_config(weld_dir)

        # Backup should be created
        assert backup_file.exists()
        # Backup should contain original content
        assert "[claude.transcripts]" in backup_file.read_text()
        assert config.transcripts.visibility == "public"

    def test_migration_saves_to_disk(self, tmp_path: Path) -> None:
        """load_config should save migrated config to disk."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        config_file = weld_dir / "config.toml"
        config_file.write_text("""
[project]
name = "test"

[claude.transcripts]
visibility = "public"
""")

        # Load config - should trigger migration
        load_config(weld_dir)

        # Read file again to verify persistence
        migrated_content = config_file.read_text()
        # Should have new format
        assert "[transcripts]" in migrated_content
        assert "visibility" in migrated_content
        # Should NOT have old format
        assert "[claude.transcripts]" not in migrated_content

    def test_no_backup_when_no_migration_needed(self, tmp_path: Path) -> None:
        """load_config should not create backup when config is already new format."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        config_file = weld_dir / "config.toml"
        config_file.write_text("""
[transcripts]
visibility = "public"
""")
        backup_file = weld_dir / "config.toml.bak"

        # Load config - no migration needed
        load_config(weld_dir)

        # No backup should be created
        assert not backup_file.exists()

    def test_migration_rollback_on_write_failure(self, tmp_path: Path, monkeypatch) -> None:
        """load_config should restore backup if migration write fails."""
        import tomli_w

        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        config_file = weld_dir / "config.toml"
        original_content = """
[claude.transcripts]
visibility = "public"
"""
        config_file.write_text(original_content)

        # Mock tomli_w.dump to raise an error
        def mock_dump_error(*args, **kwargs):
            raise OSError("Disk full")

        monkeypatch.setattr(tomli_w, "dump", mock_dump_error)

        # Load config should raise error but restore backup
        with pytest.raises(RuntimeError, match="Config migration failed, restored backup"):
            load_config(weld_dir)

        # Original file should be restored
        assert config_file.read_text() == original_content
        # Backup should still exist
        backup_file = weld_dir / "config.toml.bak"
        assert backup_file.exists()

    def test_migration_preserves_other_config(self, tmp_path: Path) -> None:
        """Migration should not affect other config sections."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        config_file = weld_dir / "config.toml"
        config_file.write_text("""
[project]
name = "test-project"

[claude]
exec = "claude"
model = "opus"

[claude.transcripts]
visibility = "public"

[codex]
exec = "codex"

[checks]
lint = "ruff check ."

[git]
commit_trailer_key = "Claude-Transcript"

[loop]
max_iterations = 5
""")

        config = load_config(weld_dir)

        # Verify all sections preserved
        assert config.project.name == "test-project"
        assert config.claude.exec == "claude"
        assert config.claude.model == "opus"
        assert config.codex.exec == "codex"
        assert config.checks.lint == "ruff check ."
        assert config.git.commit_trailer_key == "Claude-Transcript"
        assert config.loop.max_iterations == 5
        # And transcripts migrated correctly
        assert config.transcripts.visibility == "public"

    def test_migration_idempotent(self, tmp_path: Path) -> None:
        """Running migration twice should be safe."""
        weld_dir = tmp_path / ".weld"
        weld_dir.mkdir()
        config_file = weld_dir / "config.toml"
        config_file.write_text("""
[claude.transcripts]
visibility = "secret"
""")

        # First migration
        config1 = load_config(weld_dir)
        content1 = config_file.read_text()

        # Second migration (should be no-op)
        config2 = load_config(weld_dir)
        content2 = config_file.read_text()

        # Content should be identical
        assert content1 == content2
        assert config1.transcripts.visibility == config2.transcripts.visibility


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


def test_prompt_customization_defaults() -> None:
    """PromptCustomization should have None defaults for all fields."""
    custom = PromptCustomization()

    assert custom.prefix is None
    assert custom.suffix is None
    assert custom.default_focus is None


def test_prompt_customization_accepts_values() -> None:
    """PromptCustomization should accept custom values."""
    custom = PromptCustomization(
        prefix="Always use Python 3.12 features.",
        suffix="Include comprehensive docstrings.",
        default_focus="performance",
    )

    assert custom.prefix == "Always use Python 3.12 features."
    assert custom.suffix == "Include comprehensive docstrings."
    assert custom.default_focus == "performance"


def test_prompts_config_defaults() -> None:
    """PromptsConfig should have empty defaults for global and all tasks."""
    config = PromptsConfig()

    # Global prefix/suffix should be None
    assert config.global_prefix is None
    assert config.global_suffix is None

    # All task-specific should be empty
    assert config.discover.prefix is None
    assert config.research.prefix is None
    assert config.plan_generation.prefix is None
    assert config.implementation.prefix is None


def test_prompts_config_get_customization() -> None:
    """PromptsConfig.get_customization should return task-specific config."""
    config = PromptsConfig(
        research=PromptCustomization(prefix="Security focus"),
    )

    research = config.get_customization(TaskType.RESEARCH)
    assert research.prefix == "Security focus"

    # Other tasks remain default
    discover = config.get_customization(TaskType.DISCOVER)
    assert discover.prefix is None


def test_prompts_config_layered_customization() -> None:
    """PromptsConfig should support layered global and task-specific customization."""
    config = PromptsConfig(
        global_prefix="Global prefix",
        global_suffix="Global suffix",
        research=PromptCustomization(
            prefix="Research-specific prefix",
            default_focus="security",
        ),
    )

    # Global values are accessible directly
    assert config.global_prefix == "Global prefix"
    assert config.global_suffix == "Global suffix"

    # Task-specific values via get_customization
    task_custom = config.get_customization(TaskType.RESEARCH)
    assert task_custom.prefix == "Research-specific prefix"
    assert task_custom.default_focus == "security"


def test_prompts_config_task_only_values() -> None:
    """PromptsConfig with only task-specific values."""
    config = PromptsConfig(
        plan_generation=PromptCustomization(
            suffix="Break into small steps.",
        ),
    )

    task_custom = config.get_customization(TaskType.PLAN_GENERATION)

    assert task_custom.prefix is None
    assert task_custom.suffix == "Break into small steps."
    assert task_custom.default_focus is None


def test_weld_config_includes_prompts() -> None:
    """WeldConfig should have prompts field with PromptsConfig type."""
    config = WeldConfig()

    assert hasattr(config, "prompts")
    assert isinstance(config.prompts, PromptsConfig)
    # Default prompts should be empty customizations
    assert config.prompts.global_prefix is None
    assert config.prompts.global_suffix is None


def test_weld_config_with_custom_prompts() -> None:
    """WeldConfig should accept custom prompts configuration."""
    config = WeldConfig(
        prompts=PromptsConfig(
            global_prefix="Python 3.12 project",
            discover=PromptCustomization(default_focus="architecture"),
        )
    )

    assert config.prompts.global_prefix == "Python 3.12 project"
    assert config.prompts.discover.default_focus == "architecture"
