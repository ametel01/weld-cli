"""Tests for weld configuration."""

from weld.config import (
    ClaudeConfig,
    CodexConfig,
    ModelConfig,
    TaskModelsConfig,
    TaskType,
    WeldConfig,
)


def test_default_task_models():
    """Default task models should be set correctly."""
    config = WeldConfig()

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
