"""Step model for parsed plan steps."""

from pydantic import BaseModel, Field


class Step(BaseModel):
    """Parsed step from the plan."""

    n: int
    title: str
    slug: str
    body_md: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
