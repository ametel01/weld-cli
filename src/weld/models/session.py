"""Session tracking models.

Captures Claude Code session activity for transcript generation and
commit provenance tracking. Sessions are detected from Claude's
local storage and activity is recorded during weld command execution.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class SessionActivity(BaseModel):
    """A single command execution within a session.

    Attributes:
        command: The weld command that was executed (e.g., "research", "plan", "implement")
        timestamp: When the command was executed
        files_created: List of relative paths to files created during this activity
        files_modified: List of relative paths to files modified during this activity
        completed: Whether the command completed successfully (False if interrupted)
    """

    command: str = Field(description="Weld command executed (e.g., research, plan, implement)")
    timestamp: datetime = Field(description="When the command was executed")
    files_created: list[str] = Field(
        default_factory=list, description="Relative paths to files created"
    )
    files_modified: list[str] = Field(
        default_factory=list, description="Relative paths to files modified"
    )
    completed: bool = Field(default=True, description="False if command was interrupted")


class TrackedSession(BaseModel):
    """A Claude session with recorded activity.

    Tracks a Claude Code session from first detection through to commit.
    Sessions are identified by UUID from the Claude session filename.

    Attributes:
        session_id: UUID extracted from Claude session filename
        session_file: Absolute path to the .jsonl session file
        first_seen: When weld first detected this session
        last_activity: Most recent weld command in this session
        activities: List of weld commands executed in this session
    """

    session_id: str = Field(description="UUID from session filename")
    session_file: str = Field(description="Absolute path to .jsonl file")
    first_seen: datetime = Field(description="When session was first detected")
    last_activity: datetime = Field(description="Most recent activity timestamp")
    activities: list[SessionActivity] = Field(
        default_factory=list, description="Commands executed in this session"
    )
