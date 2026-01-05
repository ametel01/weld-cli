"""Timing model for per-phase performance tracking."""

from pydantic import BaseModel, Field


class Timing(BaseModel):
    """Per-iteration timing breakdown.

    Tracks time spent in each phase of a step loop iteration,
    enabling performance analysis and optimization.

    Attributes:
        ai_invocation_ms: Time spent waiting for AI response
        checks_ms: Time spent running checks
        review_ms: Time spent on review
        total_ms: Total iteration time
    """

    ai_invocation_ms: int = Field(default=0, description="AI invocation time in ms")
    checks_ms: int = Field(default=0, description="Checks execution time in ms")
    review_ms: int = Field(default=0, description="Review time in ms")
    total_ms: int = Field(default=0, description="Total iteration time in ms")
