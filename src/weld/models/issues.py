"""Issue models for Codex review results."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Issue(BaseModel):
    """Single issue from Codex review."""

    severity: Literal["blocker", "major", "minor"]
    file: str
    hint: str
    maps_to: str | None = None  # e.g., "AC #2"


class Issues(BaseModel):
    """Codex review result (parsed from final JSON line)."""

    model_config = ConfigDict(populate_by_name=True)

    pass_: bool = Field(alias="pass")
    issues: list[Issue] = Field(default_factory=list)
