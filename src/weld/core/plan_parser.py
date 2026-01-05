"""Plan parsing and prompt generation for weld."""

import re
from pathlib import Path

from ..models import Step


def generate_plan_prompt(
    spec_content: str,
    spec_path: Path,
    *,
    research_content: str | None = None,
) -> str:
    """Generate Claude prompt for plan creation.

    Args:
        spec_content: Content of the specification file
        spec_path: Path to the specification file
        research_content: Optional research findings to incorporate

    Returns:
        Formatted prompt for Claude to create an implementation plan
    """
    research_section = ""
    if research_content:
        research_section = f"""
## Research Findings

The following research has been conducted to inform this plan:

{research_content}

---
"""

    return f"""# Implementation Plan Request

You are creating an implementation plan for the following specification.

## Specification: {spec_path.name}

{spec_content}

---
{research_section}
## Instructions

Create a detailed, step-by-step implementation plan. Each step must follow this format:

## Step N: <Title>

### Goal
Brief description of what this step accomplishes.

### Changes
- List of files to create/modify
- Specific changes to make

### Acceptance criteria
- [ ] Criterion 1
- [ ] Criterion 2

### Tests
- Commands to verify the step works

---

Guidelines:
- Each step should be independently verifiable
- Steps should be atomic and focused
- Order steps by dependency (do prerequisites first)
- Include validation commands for each step{
        '''
- Incorporate insights from the research findings above'''
        if research_content
        else ""
    }
"""


def generate_codex_review_prompt(plan_content: str) -> str:
    """Generate Codex prompt for plan review.

    Args:
        plan_content: The plan content to review

    Returns:
        Formatted prompt for Codex to review the plan
    """
    return f"""# Plan Review Request

Review the following implementation plan for completeness, correctness, and potential issues.

## Plan to Review

{plan_content}

---

## Your Task

Analyze this plan and provide:

## Findings
- List any issues, gaps, or improvements

## Revised Plan
Provide the complete revised plan (with your improvements incorporated).
Use the same format as the original plan (## Step N: Title, ### Goal, etc.)

## Risk Notes
- Any risks or considerations for implementation
"""


def parse_steps_strict(plan_content: str) -> list[Step]:
    """Parse steps using strict format (## Step N: Title).

    Args:
        plan_content: Plan content in markdown format

    Returns:
        List of parsed Step objects
    """
    steps: list[Step] = []

    # Pattern for step headers
    pattern = r"^## Step (\d+):\s*(.+)$"

    lines = plan_content.split("\n")
    current_step: dict[str, str | int] | None = None
    current_body: list[str] = []

    for line in lines:
        match = re.match(pattern, line, re.IGNORECASE)
        if match:
            # Save previous step
            if current_step is not None:
                body = "\n".join(current_body).strip()
                steps.append(_parse_step_body(current_step, body))

            # Start new step
            n = int(match.group(1))
            title = match.group(2).strip()
            current_step = {"n": n, "title": title}
            current_body = []
        elif current_step is not None:
            current_body.append(line)

    # Don't forget last step
    if current_step is not None:
        body = "\n".join(current_body).strip()
        steps.append(_parse_step_body(current_step, body))

    return steps


def _parse_step_body(header: dict[str, str | int], body: str) -> Step:
    """Parse step body for acceptance criteria and tests.

    Args:
        header: Dict with 'n' and 'title' keys
        body: The step body content

    Returns:
        Parsed Step object
    """
    # Extract acceptance criteria (checkbox items under ### Acceptance criteria)
    ac_pattern = r"###\s*Acceptance criteria\s*\n((?:[-*]\s*\[.\].*\n?)+)"
    ac_match = re.search(ac_pattern, body, re.IGNORECASE)
    criteria: list[str] = []
    if ac_match:
        for line in ac_match.group(1).split("\n"):
            if line.strip().startswith(("-", "*")):
                # Remove checkbox and bullet
                text = re.sub(r"^[-*]\s*\[.\]\s*", "", line.strip())
                if text:
                    criteria.append(text)

    # Extract tests
    tests_pattern = r"###\s*Tests?\s*\n((?:[-*`].*\n?)+)"
    tests_match = re.search(tests_pattern, body, re.IGNORECASE)
    tests: list[str] = []
    if tests_match:
        for line in tests_match.group(1).split("\n"):
            line = line.strip()
            if line.startswith(("-", "*", "`")):
                text = line.lstrip("-* `").rstrip("`")
                if text:
                    tests.append(text)

    # Create slug from title
    title = str(header["title"])
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:30]

    return Step(
        n=int(header["n"]),
        title=title,
        slug=slug,
        body_md=body,
        acceptance_criteria=criteria,
        tests=tests,
    )


def parse_steps_lenient(plan_content: str) -> list[Step]:
    """Parse steps using lenient format (N. Title).

    Args:
        plan_content: Plan content in markdown format

    Returns:
        List of parsed Step objects
    """
    steps: list[Step] = []
    pattern = r"^(\d+)\.\s+(.+)$"

    lines = plan_content.split("\n")
    current_step: dict[str, str | int] | None = None
    current_body: list[str] = []

    for line in lines:
        match = re.match(pattern, line)
        if match:
            if current_step is not None:
                body = "\n".join(current_body).strip()
                title = str(current_step["title"])
                slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:30]
                steps.append(
                    Step(
                        n=int(current_step["n"]),
                        title=title,
                        slug=slug.strip("-"),
                        body_md=body,
                    )
                )

            current_step = {"n": int(match.group(1)), "title": match.group(2).strip()}
            current_body = []
        elif current_step is not None:
            current_body.append(line)

    if current_step is not None:
        body = "\n".join(current_body).strip()
        title = str(current_step["title"])
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:30]
        steps.append(
            Step(
                n=int(current_step["n"]),
                title=title,
                slug=slug.strip("-"),
                body_md=body,
            )
        )

    return steps


def parse_steps(plan_content: str) -> tuple[list[Step], list[str]]:
    """Parse steps, trying strict format first, then lenient.

    Args:
        plan_content: Plan content in markdown format

    Returns:
        Tuple of (list of Step objects, list of warning messages)
    """
    warnings: list[str] = []

    steps = parse_steps_strict(plan_content)
    if steps:
        return steps, warnings

    warnings.append("No strict-format steps found; using lenient parsing")
    steps = parse_steps_lenient(plan_content)

    if not steps:
        warnings.append("No steps found in plan")

    return steps, warnings
