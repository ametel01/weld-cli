"""Configuration management for weld."""

import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, Field


class ChecksConfig(BaseModel):
    """Configuration for checks command."""

    command: str = "echo 'No checks configured'"


class CodexConfig(BaseModel):
    """Configuration for Codex integration."""

    exec: str = "codex"
    sandbox: str = "read-only"
    model: str | None = None


class TranscriptsConfig(BaseModel):
    """Configuration for transcript generation."""

    exec: str = "claude-code-transcripts"
    visibility: str = "secret"


class ClaudeConfig(BaseModel):
    """Configuration for Claude-related settings."""

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
        "checks": {"command": "echo 'Configure your checks command'"},
        "codex": {"exec": "codex", "sandbox": "read-only"},
        "claude": {"transcripts": {"exec": "claude-code-transcripts", "visibility": "secret"}},
        "git": {"commit_trailer_key": "Claude-Transcript", "include_run_trailer": True},
        "loop": {"max_iterations": 5, "fail_on_blockers_only": True},
    }
    with open(config_path, "wb") as f:
        tomli_w.dump(template, f)
    return config_path
