"""Lock model for concurrent run prevention.

Implements PID-based file locking to ensure only one weld command
modifies run state at a time.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Lock(BaseModel):
    """Active run lock written to .weld/active.lock.

    Attributes:
        pid: Process ID of the lock holder.
        run_id: ID of the run being modified.
        command: Command that acquired the lock.
        started_at: When the lock was acquired.
        last_heartbeat: Last heartbeat update (for stale detection).
    """

    pid: int = Field(description="Process ID holding the lock")
    run_id: str = Field(description="Run ID being modified")
    command: str = Field(description="Command that acquired lock")
    started_at: datetime = Field(default_factory=datetime.now)
    last_heartbeat: datetime = Field(default_factory=datetime.now)
