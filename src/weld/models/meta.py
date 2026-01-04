"""Metadata models for weld runs.

These models capture the initial state and provenance information
for each weld run, enabling reproducibility and audit trails.
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class SpecRef(BaseModel):
    """Reference to the input specification file.

    Captures the specification file's identity and content hash
    at the time the run was created, enabling verification that
    the spec hasn't changed.

    Attributes:
        absolute_path: Full path to the specification file.
        sha256: SHA256 hash of the file contents for integrity verification.
        size_bytes: File size in bytes.
        git_blob_id: Optional git blob SHA if file is tracked.
    """

    absolute_path: Path = Field(description="Full path to the specification file")
    sha256: str = Field(description="SHA256 hash of file contents")
    size_bytes: int = Field(description="File size in bytes")
    git_blob_id: str | None = Field(default=None, description="Git blob SHA if tracked")


class Meta(BaseModel):
    """Run metadata written to meta.json.

    Captures the repository state and configuration at run creation time,
    providing context for debugging and reproducibility.

    Attributes:
        run_id: Unique run identifier (format: YYYYMMDD-HHMMSS-slug).
        created_at: Timestamp when the run was created.
        updated_at: Timestamp of the last modification.
        repo_root: Absolute path to the git repository root.
        branch: Git branch name at run creation.
        head_sha: Git HEAD commit SHA at run creation.
        config_hash: Hash of weld config for change detection.
        tool_versions: Version info for external tools (codex, claude, etc.).
        plan_parse_warnings: Warnings generated during plan parsing.
    """

    run_id: str = Field(description="Unique run identifier")
    created_at: datetime = Field(default_factory=datetime.now, description="Run creation time")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last modification time")
    repo_root: Path = Field(description="Git repository root path")
    branch: str = Field(description="Git branch at run creation")
    head_sha: str = Field(description="Git HEAD SHA at run creation")
    config_hash: str = Field(description="Hash of weld config for change detection")
    tool_versions: dict[str, str] = Field(
        default_factory=dict, description="Version info for external tools"
    )
    plan_parse_warnings: list[str] = Field(
        default_factory=list, description="Warnings from plan parsing"
    )
