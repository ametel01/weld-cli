"""Discover workflow models.

Captures metadata for codebase discovery artifacts, enabling
lineage tracking between discover outputs and implementation runs.
"""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class DiscoverMeta(BaseModel):
    """Metadata for a discover artifact.

    Attributes:
        discover_id: Unique identifier (format: YYYYMMDD-HHMMSS-discover)
        created_at: When discovery was run
        config_hash: Hash of weld config at time of discovery
        output_path: Path where discover output was written
        used_by_runs: List of run IDs that reference this discover
        partial: Whether discovery was interrupted/incomplete
    """

    discover_id: str = Field(description="Unique discover identifier")
    created_at: datetime = Field(default_factory=datetime.now)
    config_hash: str = Field(description="Config hash at discovery time")
    output_path: Path = Field(description="Output file path")
    used_by_runs: list[str] = Field(default_factory=list, description="Runs using this discover")
    partial: bool = Field(default=False, description="True if discovery was interrupted")
