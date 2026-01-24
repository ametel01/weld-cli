"""Configuration management for weld."""

import logging
import tomllib
from enum import Enum
from pathlib import Path

import tomli_w
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """Types of tasks that can be assigned to different models."""

    # Discovery and interview (brownfield)
    DISCOVER = "discover"
    INTERVIEW = "interview"

    # Research phase
    RESEARCH = "research"
    RESEARCH_REVIEW = "research_review"

    # Plan phase
    PLAN_GENERATION = "plan_generation"
    PLAN_REVIEW = "plan_review"

    # Implementation phase
    IMPLEMENTATION = "implementation"
    IMPLEMENTATION_REVIEW = "implementation_review"
    FIX_GENERATION = "fix_generation"


class ModelConfig(BaseModel):
    """Configuration for a specific AI model."""

    provider: str = "codex"  # codex, claude, openai, etc.
    model: str | None = None  # Specific model name (e.g., gpt-4, claude-3-opus)
    exec: str | None = None  # Override executable path


class TaskModelsConfig(BaseModel):
    """Per-task model assignments."""

    discover: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    interview: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    research: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    research_review: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="codex"))
    plan_generation: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    plan_review: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="codex"))
    implementation: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    implementation_review: ModelConfig = Field(
        default_factory=lambda: ModelConfig(provider="codex")
    )
    fix_generation: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))

    def get_model(self, task: TaskType) -> ModelConfig:
        """Get model config for a specific task type."""
        return getattr(self, task.value)


class ChecksConfig(BaseModel):
    """Configuration for checks command.

    Supports two modes:
    1. Multi-category (preferred): Define lint/test/typecheck with order
    2. Legacy single command: Use 'command' field (deprecated)
    """

    # Multi-category checks (preferred)
    lint: str | None = Field(default=None, description="Lint command (e.g., 'ruff check .')")
    test: str | None = Field(default=None, description="Test command (e.g., 'pytest tests/')")
    typecheck: str | None = Field(default=None, description="Typecheck command (e.g., 'pyright')")
    order: list[str] = Field(
        default=["lint", "typecheck", "test"], description="Execution order for categories"
    )

    # Legacy single command (deprecated, for backward compatibility)
    command: str | None = Field(
        default=None, description="Single check command. Deprecated: use category fields instead."
    )

    def get_categories(self) -> dict[str, str]:
        """Get enabled category commands as {name: command} dict."""
        categories = {}
        for name in self.order:
            cmd = getattr(self, name, None)
            if cmd:
                categories[name] = cmd
        return categories

    def is_legacy_mode(self) -> bool:
        """Return True if using deprecated single-command mode."""
        return self.command is not None and not self.get_categories()


class CodexConfig(BaseModel):
    """Configuration for Codex integration (default settings)."""

    exec: str = "codex"
    sandbox: str = "read-only"
    model: str | None = None  # Default model for Codex provider


class TranscriptsConfig(BaseModel):
    """Configuration for transcript generation.

    Transcripts are rendered from Claude session files and uploaded as GitHub Gists.
    """

    enabled: bool = True
    visibility: str = "secret"  # "secret" or "public"


class PromptCustomization(BaseModel):
    """Customization for a single prompt type.

    Allows adding prefix/suffix text and setting the default focus
    for prompts like research, plan, discover, etc.
    """

    prefix: str | None = Field(
        default=None,
        description="Text to prepend to the prompt (e.g., project context, constraints)",
    )
    suffix: str | None = Field(
        default=None,
        description="Text to append to the prompt (e.g., output format requirements)",
    )
    default_focus: str | None = Field(
        default=None,
        description="Default focus area when --focus is not specified on command line",
    )


class PromptsConfig(BaseModel):
    """Container for all prompt customizations.

    Provides global defaults and per-task overrides for prompt customization.
    Task-specific settings override global settings when both are present.
    """

    # Global defaults applied to all prompts unless overridden
    default: PromptCustomization = Field(default_factory=PromptCustomization)

    # Per-task customizations (field names match TaskType enum values)
    discover: PromptCustomization = Field(default_factory=PromptCustomization)
    interview: PromptCustomization = Field(default_factory=PromptCustomization)
    research: PromptCustomization = Field(default_factory=PromptCustomization)
    research_review: PromptCustomization = Field(default_factory=PromptCustomization)
    plan_generation: PromptCustomization = Field(default_factory=PromptCustomization)
    plan_review: PromptCustomization = Field(default_factory=PromptCustomization)
    implementation: PromptCustomization = Field(default_factory=PromptCustomization)
    implementation_review: PromptCustomization = Field(default_factory=PromptCustomization)
    fix_generation: PromptCustomization = Field(default_factory=PromptCustomization)

    def get_customization(self, task: TaskType) -> PromptCustomization:
        """Get prompt customization for a specific task type.

        Returns the task-specific customization. Use get_effective_customization()
        to get merged global + task settings.
        """
        return getattr(self, task.value)

    def get_effective_customization(self, task: TaskType) -> PromptCustomization:
        """Get effective customization with global defaults merged.

        Task-specific values override global defaults. If a task field is None,
        the global default is used instead.
        """
        task_config = self.get_customization(task)
        return PromptCustomization(
            prefix=task_config.prefix if task_config.prefix is not None else self.default.prefix,
            suffix=task_config.suffix if task_config.suffix is not None else self.default.suffix,
            default_focus=(
                task_config.default_focus
                if task_config.default_focus is not None
                else self.default.default_focus
            ),
        )


class ClaudeConfig(BaseModel):
    """Configuration for Claude-related settings."""

    exec: str = "claude"  # Path to Claude CLI if available
    model: str | None = None  # Default model (e.g., claude-3-opus)
    timeout: int = 1800  # Default timeout in seconds (30 minutes)
    max_output_tokens: int = 128000  # Max output tokens for Claude responses


class GitConfig(BaseModel):
    """Configuration for git commit handling."""

    commit_trailer_key: str = "Claude-Transcript"
    include_run_trailer: bool = True


class LoopConfig(BaseModel):
    """Configuration for implement-review-fix loop."""

    max_iterations: int = 5
    fail_on_blockers_only: bool = True


class ProjectConfig(BaseModel):
    """Project-level configuration."""

    name: str = "unnamed-project"


class WeldConfig(BaseModel):
    """Root configuration for weld."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    checks: ChecksConfig = Field(default_factory=ChecksConfig)
    codex: CodexConfig = Field(default_factory=CodexConfig)
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    task_models: TaskModelsConfig = Field(default_factory=TaskModelsConfig)
    transcripts: TranscriptsConfig = Field(default_factory=TranscriptsConfig)
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)

    def get_task_model(self, task: TaskType) -> ModelConfig:
        """Get effective model config for a task.

        Returns the task-specific model config, with provider defaults
        filled in from codex/claude sections.
        """
        model_cfg = self.task_models.get_model(task)

        # Apply provider defaults if not overridden
        if model_cfg.provider == "codex":
            return ModelConfig(
                provider="codex",
                model=model_cfg.model or self.codex.model,
                exec=model_cfg.exec or self.codex.exec,
            )
        elif model_cfg.provider == "claude":
            return ModelConfig(
                provider="claude",
                model=model_cfg.model or self.claude.model,
                exec=model_cfg.exec or self.claude.exec,
            )
        else:
            return model_cfg


def _migrate_config(config_dict: dict) -> tuple[dict, bool]:
    """Apply migrations to config dict.

    Returns:
        Tuple of (migrated_config, was_modified)
    """
    modified = False

    # Migration 1: [claude.transcripts] → [transcripts]
    if "claude" in config_dict and "transcripts" in config_dict.get("claude", {}):
        old_transcripts = config_dict["claude"].pop("transcripts")
        logger.info("Migrating claude.transcripts to top-level transcripts config")

        if "transcripts" not in config_dict:
            config_dict["transcripts"] = {}

        # Map old fields to new structure
        if "visibility" in old_transcripts:
            config_dict["transcripts"]["visibility"] = old_transcripts["visibility"]
        if "enabled" in old_transcripts:
            config_dict["transcripts"]["enabled"] = old_transcripts["enabled"]
        # Note: 'exec' field is no longer used (native implementation)
        if "exec" in old_transcripts:
            logger.info("Ignoring claude.transcripts.exec (no longer used)")

        modified = True

    return config_dict, modified


def _save_config(config_path: Path, config_dict: dict) -> None:
    """Save config dict to TOML file with backup.

    Creates a backup file (.toml.bak) before writing. If write fails,
    the backup is restored automatically.

    Args:
        config_path: Path to config file
        config_dict: Configuration dictionary to save

    Raises:
        RuntimeError: If save fails (after restoring backup)
    """
    import shutil

    backup_path = config_path.with_suffix(".toml.bak")

    # Create backup
    if config_path.exists():
        shutil.copy2(config_path, backup_path)

    # Write new config
    try:
        with open(config_path, "wb") as f:
            tomli_w.dump(config_dict, f)
        logger.info(f"Config migrated, backup saved to {backup_path.name}")
    except Exception as e:
        # Restore backup on failure
        if backup_path.exists():
            shutil.copy2(backup_path, config_path)
        raise RuntimeError(f"Config migration failed, restored backup: {e}") from e


def load_config(weld_dir: Path) -> WeldConfig:
    """Load config from .weld/config.toml with auto-migration.

    Args:
        weld_dir: Path to .weld directory

    Returns:
        Loaded configuration, or defaults if config.toml doesn't exist

    Note:
        Automatically migrates old claude.transcripts config to top-level transcripts.
        Creates a backup file (.toml.bak) when migration is applied.
    """
    config_path = weld_dir / "config.toml"
    if not config_path.exists():
        return WeldConfig()

    with open(config_path, "rb") as f:
        config_dict = tomllib.load(f)

    # Apply migrations
    config_dict, modified = _migrate_config(config_dict)

    # Save if modified
    if modified:
        _save_config(config_path, config_dict)

    return WeldConfig.model_validate(config_dict)


def write_config_template(weld_dir: Path) -> Path:
    """Write default config.toml template.

    Args:
        weld_dir: Path to .weld directory

    Returns:
        Path to the written config file
    """
    config_path = weld_dir / "config.toml"
    template = {
        "project": {"name": "your-project"},
        "checks": {
            "lint": "ruff check .",
            "test": "pytest tests/ -q",
            "typecheck": "pyright",
            "order": ["lint", "typecheck", "test"],
        },
        "codex": {"exec": "codex", "sandbox": "read-only"},
        "claude": {
            "exec": "claude",
            "timeout": 1800,  # 30 minutes for AI operations
            "max_output_tokens": 128000,  # Increase if you hit token limit errors
        },
        "transcripts": {
            "enabled": True,  # Set to False to disable transcript generation
            "visibility": "secret",  # "secret" or "public" gist
        },
        "git": {"commit_trailer_key": "Claude-Transcript", "include_run_trailer": True},
        "loop": {"max_iterations": 5, "fail_on_blockers_only": True},
        # Per-task model selection: customize which AI handles each task
        # Provider can be "codex", "claude", or any other supported provider
        # Model is optional and overrides the provider default
        "task_models": {
            "discover": {"provider": "claude"},
            "interview": {"provider": "claude"},
            "research": {"provider": "claude"},
            "research_review": {"provider": "codex"},
            "plan_generation": {"provider": "claude"},
            "plan_review": {"provider": "codex"},
            "implementation": {"provider": "claude"},
            "implementation_review": {"provider": "codex"},
            "fix_generation": {"provider": "claude"},
        },
    }
    with open(config_path, "wb") as f:
        tomli_w.dump(template, f)
    return config_path
