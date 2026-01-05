"""Configuration management for weld."""

import tomllib
from enum import Enum
from pathlib import Path

import tomli_w
from pydantic import BaseModel, Field


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
    """Configuration for transcript generation."""

    exec: str = "claude-code-transcripts"
    visibility: str = "secret"


class ClaudeConfig(BaseModel):
    """Configuration for Claude-related settings."""

    exec: str = "claude"  # Path to Claude CLI if available
    model: str | None = None  # Default model (e.g., claude-3-opus)
    transcripts: TranscriptsConfig = Field(default_factory=TranscriptsConfig)


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


def load_config(weld_dir: Path) -> WeldConfig:
    """Load config from .weld/config.toml.

    Args:
        weld_dir: Path to .weld directory

    Returns:
        Loaded configuration, or defaults if config.toml doesn't exist
    """
    config_path = weld_dir / "config.toml"
    if not config_path.exists():
        return WeldConfig()
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    return WeldConfig.model_validate(data)


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
            "transcripts": {"exec": "claude-code-transcripts", "visibility": "secret"},
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
