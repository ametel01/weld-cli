"""Step management utilities for weld."""

from pathlib import Path
from typing import Any

from ..config import ChecksConfig
from ..models import Step


def get_step_dir(run_dir: Path, step: Step) -> Path:
    """Get step directory path.

    Args:
        run_dir: Path to the run directory
        step: Step object

    Returns:
        Path to the step directory
    """
    return run_dir / "steps" / f"{step.n:02d}-{step.slug}"


def create_step_directory(run_dir: Path, step: Step) -> Path:
    """Create step directory structure.

    Args:
        run_dir: Path to the run directory
        step: Step object

    Returns:
        Path to the created step directory
    """
    step_dir = get_step_dir(run_dir, step)
    (step_dir / "prompt").mkdir(parents=True, exist_ok=True)
    (step_dir / "iter").mkdir(parents=True, exist_ok=True)
    return step_dir


def get_iter_dir(step_dir: Path, iteration: int) -> Path:
    """Get iteration directory path.

    Args:
        step_dir: Path to the step directory
        iteration: Iteration number

    Returns:
        Path to the iteration directory
    """
    return step_dir / "iter" / f"{iteration:02d}"


def create_iter_directory(step_dir: Path, iteration: int) -> Path:
    """Create iteration directory.

    Args:
        step_dir: Path to the step directory
        iteration: Iteration number

    Returns:
        Path to the created iteration directory
    """
    iter_dir = get_iter_dir(step_dir, iteration)
    iter_dir.mkdir(parents=True, exist_ok=True)
    return iter_dir


def generate_impl_prompt(step: Step, checks_config: ChecksConfig) -> str:
    """Generate Claude implementation prompt.

    Args:
        step: Step to implement
        checks_config: Checks configuration

    Returns:
        Formatted implementation prompt
    """
    ac_list = "\n".join(f"- [ ] {ac}" for ac in step.acceptance_criteria)

    # Format checks commands for display
    categories = checks_config.get_categories()
    if categories:
        checks_cmds = "\n".join(f"{name}: {cmd}" for name, cmd in categories.items())
    elif checks_config.command:
        checks_cmds = checks_config.command
    else:
        checks_cmds = "# No checks configured"

    return f"""# Implementation Task: Step {step.n}

## {step.title}

{step.body_md}

---

## Acceptance Criteria Checklist

{ac_list if ac_list else "- [ ] Implementation complete"}

---

## Validation

After implementing, run:
```bash
{checks_cmds}
```

---

## Scope Boundary

**IMPORTANT:**
- Only implement this step
- Minimize churn; no refactors unless necessary to satisfy criteria
- If you change interfaces, update typing/tests accordingly
- Do not implement future steps
"""


def generate_fix_prompt(step: Step, issues_json: dict[str, Any], iteration: int) -> str:
    """Generate Claude fix prompt for next iteration.

    Args:
        step: Step being fixed
        issues_json: Issues dict with 'issues' list
        iteration: Current iteration number

    Returns:
        Formatted fix prompt
    """
    issues = issues_json.get("issues", [])

    # Group by severity
    blockers = [i for i in issues if i.get("severity") == "blocker"]
    majors = [i for i in issues if i.get("severity") == "major"]
    minors = [i for i in issues if i.get("severity") == "minor"]

    def format_issues(items: list[dict[str, Any]], label: str) -> str:
        if not items:
            return ""
        lines = [f"\n### {label}\n"]
        for item in items:
            lines.append(f"- **{item.get('file', 'unknown')}**: {item.get('hint', 'No details')}")
            if item.get("maps_to"):
                lines.append(f"  - Maps to: {item['maps_to']}")
        return "\n".join(lines)

    issues_text = ""
    issues_text += format_issues(blockers, "Blockers (must fix)")
    issues_text += format_issues(majors, "Major Issues")
    issues_text += format_issues(minors, "Minor Issues")

    return f"""# Fix Request: Step {step.n}, Iteration {iteration + 1}

The previous implementation has issues that need to be addressed.

## Issues Found
{issues_text if issues_text else "No specific issues listed"}

---

## Original Step

{step.body_md}

---

## Scope Boundary

**IMPORTANT:**
- Fix these issues only
- No refactors or unrelated changes
- Re-run checks after fixing
"""


def generate_review_prompt(step: Step, diff: str, checks_output: str) -> str:
    """Generate review prompt for implementation.

    Args:
        step: Step being reviewed
        diff: Git diff of changes
        checks_output: Output from running checks

    Returns:
        Formatted review prompt
    """
    ac_list = "\n".join(f"- {ac}" for ac in step.acceptance_criteria)

    return f"""# Implementation Review Request

Review the following implementation against the step requirements.

## Step {step.n}: {step.title}

### Acceptance Criteria
{ac_list if ac_list else "- Implementation complete"}

---

## Diff

```diff
{diff}
```

---

## Checks Output

```
{checks_output}
```

---

## Your Task

1. Review the diff against acceptance criteria
2. Check for bugs, security issues, or missing requirements
3. Note any issues found

**IMPORTANT:** Your response must end with a JSON line in this exact format:
```json
{{"pass":true,"issues":[]}}
```

Or if issues found:
```json
{{"pass":false,"issues":[{{"severity":"blocker","file":"f.py","hint":"Desc","maps_to":"AC1"}}]}}
```

Severity levels: "blocker", "major", "minor"
"""
