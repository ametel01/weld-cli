"""Issue models for AI review results.

These models represent the structured output from AI code reviews,
parsed from the JSON line at the end of review responses.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Issue(BaseModel):
    """Single issue identified during code review.

    Represents a specific problem found by the AI reviewer,
    with enough context to locate and fix the issue.

    Attributes:
        severity: Issue severity level affecting pass/fail logic.
            - "blocker": Must be fixed before proceeding.
            - "major": Should be fixed, may block depending on config.
            - "minor": Nice to fix, won't block.
        file: Path to the file containing the issue.
        hint: Description of the problem and how to fix it.
        maps_to: Optional reference to acceptance criterion (e.g., "AC #2").
    """

    severity: Literal["blocker", "major", "minor"] = Field(
        description="Issue severity: blocker, major, or minor"
    )
    file: str = Field(description="File path containing the issue")
    hint: str = Field(description="Problem description and fix guidance")
    maps_to: str | None = Field(default=None, description="Related acceptance criterion")


class Issues(BaseModel):
    """AI review result parsed from the review response.

    The review output format expects a JSON line at the end with
    this structure, enabling programmatic pass/fail determination.

    Attributes:
        pass_: Whether the implementation passed review (no blockers).
        issues: List of identified issues with severity and details.

    Note:
        The `pass_` field uses an alias of "pass" for JSON serialization
        since "pass" is a Python reserved keyword.
    """

    model_config = ConfigDict(populate_by_name=True)

    pass_: bool = Field(alias="pass", description="True if review passed (no blockers)")
    issues: list[Issue] = Field(default_factory=list, description="List of identified issues")
