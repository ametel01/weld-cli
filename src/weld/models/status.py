"""Status model for iteration review results.

Captures the combined outcome of running checks and AI review
for a single iteration of the implement-review-fix loop.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CategoryResult(BaseModel):
    """Result from a single check category."""

    category: str = Field(description="Check category name (lint, test, etc.)")
    exit_code: int = Field(description="Exit code from command")
    passed: bool = Field(description="True if exit_code == 0")
    output: str = Field(default="", description="Captured stdout+stderr")


class ChecksSummary(BaseModel):
    """Aggregated results from all check categories."""

    categories: dict[str, CategoryResult] = Field(
        default_factory=dict, description="Results keyed by category name"
    )
    first_failure: str | None = Field(
        default=None, description="Name of first failing category, or None"
    )
    all_passed: bool = Field(default=True, description="True if all categories passed")

    def get_exit_code(self) -> int:
        """Return exit code of first failure, or 0 if all passed.

        Provides defensive access to avoid KeyError if first_failure
        is set but somehow not present in categories.
        """
        if self.first_failure and self.first_failure in self.categories:
            return self.categories[self.first_failure].exit_code
        return 0


class Status(BaseModel):
    """Iteration status derived from review and checks.

    Aggregates the results of running checks (tests, linting, etc.)
    and AI code review into a single pass/fail determination. This
    status drives the loop's decision to continue iterating or stop.

    Attributes:
        pass_: Final pass/fail based on blockers and config.
        issue_count: Total number of issues from AI review.
        blocker_count: Number of blocker-severity issues.
        major_count: Number of major-severity issues.
        minor_count: Number of minor-severity issues.
        checks_summary: Per-category check results.
        checks_exit_code: Exit code from checks (-1 if not run). Deprecated.
        diff_nonempty: Whether the diff contained any changes.
        timestamp: When this status was recorded.

    Note:
        The `pass_` field uses an alias of "pass" for JSON serialization
        since "pass" is a Python reserved keyword.
    """

    model_config = ConfigDict(populate_by_name=True)

    pass_: bool = Field(alias="pass", description="Final pass/fail determination")
    issue_count: int = Field(default=0, description="Total issues from review")
    blocker_count: int = Field(default=0, description="Blocker-severity issues")
    major_count: int = Field(default=0, description="Major-severity issues")
    minor_count: int = Field(default=0, description="Minor-severity issues")
    checks_summary: ChecksSummary | None = Field(
        default=None, description="Per-category check results"
    )
    # DEPRECATED: Use checks_summary.first_failure exit code instead
    checks_exit_code: int = Field(
        default=-1, description="Exit code from checks (-1 if not run). Deprecated."
    )
    diff_nonempty: bool = Field(description="True if diff contained changes")
    timestamp: datetime = Field(default_factory=datetime.now, description="Status timestamp")
