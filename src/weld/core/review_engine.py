"""Review logic for weld step implementations."""

from pathlib import Path

from ..config import TaskType, WeldConfig
from ..models import Issues, Status, Step
from ..services import (
    ClaudeError,
    CodexError,
    parse_claude_review,
    parse_codex_review,
    run_claude,
    run_codex,
)


class ReviewError(Exception):
    """Review invocation failed."""

    pass


def run_step_review(
    step: Step,
    diff: str,
    checks_output: str,
    checks_exit_code: int,
    config: WeldConfig,
    cwd: Path,
    stream: bool = False,
) -> tuple[str, Issues, Status]:
    """Run review using configured provider and return (review_md, issues, status).

    Args:
        step: Step being reviewed
        diff: Git diff of changes
        checks_output: Output from running checks
        checks_exit_code: Exit code from checks
        config: Weld configuration
        cwd: Working directory
        stream: If True, stream output to stdout in real-time

    Returns:
        Tuple of (review markdown, issues, status)
    """
    from .step_processor import generate_review_prompt

    prompt = generate_review_prompt(step, diff, checks_output)

    # Get model config for implementation review task
    model_cfg = config.get_task_model(TaskType.IMPLEMENTATION_REVIEW)

    try:
        if model_cfg.provider == "codex":
            review_md = run_codex(
                prompt=prompt,
                exec_path=model_cfg.exec or config.codex.exec,
                sandbox=config.codex.sandbox,
                model=model_cfg.model,
                cwd=cwd,
                stream=stream,
            )
            issues = parse_codex_review(review_md)
        elif model_cfg.provider == "claude":
            review_md = run_claude(
                prompt=prompt,
                exec_path=model_cfg.exec or config.claude.exec,
                model=model_cfg.model,
                cwd=cwd,
                stream=stream,
            )
            issues = parse_claude_review(review_md)
        else:
            raise ReviewError(f"Unsupported provider: {model_cfg.provider}")
    except (CodexError, ClaudeError) as e:
        # On parse failure, treat as not passing
        review_md = str(e)
        issues = Issues.model_validate({"pass": False, "issues": []})

    # Compute status
    blocker_count = sum(1 for i in issues.issues if i.severity == "blocker")
    major_count = sum(1 for i in issues.issues if i.severity == "major")
    minor_count = sum(1 for i in issues.issues if i.severity == "minor")

    # Determine pass based on config
    if config.loop.fail_on_blockers_only:
        pass_result = blocker_count == 0
    else:
        pass_result = len(issues.issues) == 0

    status = Status.model_validate(
        {
            "pass": pass_result,
            "issue_count": len(issues.issues),
            "blocker_count": blocker_count,
            "major_count": major_count,
            "minor_count": minor_count,
            "checks_exit_code": checks_exit_code,
            "diff_nonempty": bool(diff.strip()),
        }
    )

    return review_md, issues, status
