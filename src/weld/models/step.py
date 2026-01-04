"""Step model for parsed plan steps.

Represents a single implementation step extracted from a plan document.
Steps are the atomic units of work in the weld workflow.
"""

from pydantic import BaseModel, Field


class Step(BaseModel):
    """Parsed step from the plan.

    A step represents one atomic unit of implementation work,
    extracted from the plan markdown. Each step has acceptance
    criteria that must be satisfied before moving to the next step.

    Attributes:
        n: Step number (1-indexed) determining execution order.
        title: Human-readable step title from the plan header.
        slug: URL-safe identifier derived from the title.
        body_md: Full markdown content of the step.
        acceptance_criteria: List of criteria that must pass for step completion.
        tests: Commands to run for validation.

    Example:
        >>> step = Step(
        ...     n=1,
        ...     title="Setup project structure",
        ...     slug="setup-project-structure",
        ...     body_md="Create the initial directory layout...",
        ...     acceptance_criteria=["src/ directory exists"],
        ...     tests=["ls src/"],
        ... )
    """

    n: int = Field(description="Step number (1-indexed)")
    title: str = Field(description="Human-readable step title")
    slug: str = Field(description="URL-safe identifier from title")
    body_md: str = Field(description="Full markdown content of the step")
    acceptance_criteria: list[str] = Field(
        default_factory=list, description="Criteria for step completion"
    )
    tests: list[str] = Field(default_factory=list, description="Validation commands")
