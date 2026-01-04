"""Status model for iteration review results."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Status(BaseModel):
    """Iteration status derived from review + checks."""

    model_config = ConfigDict(populate_by_name=True)

    pass_: bool = Field(alias="pass")
    issue_count: int = 0
    blocker_count: int = 0
    major_count: int = 0
    minor_count: int = 0
    checks_exit_code: int
    diff_nonempty: bool
    timestamp: datetime = Field(default_factory=datetime.now)
