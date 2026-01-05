"""Version tracking models for research and plan artifacts.

Enables history tracking with up to 5 versions retained per artifact.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class VersionInfo(BaseModel):
    """Metadata for a single artifact version.

    Attributes:
        version: Version number (1-indexed)
        created_at: When this version was created
        review_id: Optional reference to review that triggered new version
        trigger_reason: Why this version was created (import, review, regenerate)
        superseded_at: When this version was replaced (None if current)
    """

    version: int = Field(ge=1, description="Version number")
    created_at: datetime = Field(default_factory=datetime.now)
    review_id: str | None = Field(default=None, description="Review that triggered this version")
    trigger_reason: str | None = Field(default=None, description="Reason for version creation")
    superseded_at: datetime | None = Field(default=None, description="When superseded")


class StaleOverride(BaseModel):
    """Record of user overriding a stale artifact warning.

    Attributes:
        timestamp: When the override was recorded
        artifact: Which artifact was stale (research, plan)
        stale_reason: Why it was considered stale
    """

    timestamp: datetime = Field(default_factory=datetime.now)
    artifact: str = Field(description="Stale artifact name")
    stale_reason: str = Field(description="Reason artifact was stale")


class CommandEvent(BaseModel):
    """Record of a command execution for audit trail.

    Attributes:
        timestamp: When command was executed
        command: Full command string
    """

    timestamp: datetime = Field(default_factory=datetime.now)
    command: str = Field(description="Executed command")


# Maximum versions to retain (Decision: 5 versions)
MAX_VERSIONS = 5
