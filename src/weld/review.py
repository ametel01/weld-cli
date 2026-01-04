"""Review logic for weld step implementations."""

from pathlib import Path

from .claude import ClaudeError, run_claude
from .claude import parse_review_json as parse_claude_review
from .codex import CodexError, run_codex
from .codex import parse_review_json as parse_codex_review
from .config import TaskType, WeldConfig
from .models import Issues, Status, Step


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
) -> tuple[str, Issues, Status]:
    """Run review using configured provider and return (review_md, issues, status).

    Args:
        step: Step being reviewed
        diff: Git diff of changes
        checks_output: Output from running checks
        checks_exit_code: Exit code from checks
        config: Weld configuration
        cwd: Working directory

    Returns:
        Tuple of (review markdown, issues, status)
    """
    from .step import generate_review_prompt

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
            )
            issues = parse_codex_review(review_md)
        elif model_cfg.provider == "claude":
            review_md = run_claude(
                prompt=prompt,
                exec_path=model_cfg.exec or config.claude.exec,
                model=model_cfg.model,
                cwd=cwd,
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
