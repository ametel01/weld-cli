"""Metadata models for weld runs."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class SpecRef(BaseModel):
    """Reference to the input specification file."""

    absolute_path: Path
    sha256: str
    size_bytes: int
    git_blob_id: str | None = None


class Meta(BaseModel):
    """Run metadata written to meta.json."""

    run_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    repo_root: Path
    branch: str
    head_sha: str
    config_hash: str
    tool_versions: dict[str, str] = Field(default_factory=dict)
    plan_parse_warnings: list[str] = Field(default_factory=list)
