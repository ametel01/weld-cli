"""Checks runner for weld."""

import shlex
import subprocess
from pathlib import Path

from ..config import ChecksConfig
from ..constants import CHECKS_TIMEOUT
from ..models import CategoryResult, ChecksSummary


class ChecksError(Exception):
    """Error running checks."""

    pass


def run_single_check(
    command: str,
    cwd: Path,
    timeout: int | None = None,
) -> tuple[str, int]:
    """Run a single check command and return (output, exit_code).

    Args:
        command: Shell command to run (will be parsed safely)
        cwd: Working directory
        timeout: Optional timeout in seconds (default: CHECKS_TIMEOUT)

    Returns:
        Tuple of (formatted output with stdout/stderr, exit code)

    Raises:
        ChecksError: If command times out or fails to execute
    """
    timeout = timeout or CHECKS_TIMEOUT

    try:
        args = shlex.split(command)
    except ValueError as e:
        raise ChecksError(f"Invalid command syntax: {e}") from e

    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ChecksError(f"Check timed out after {timeout} seconds") from e
    except FileNotFoundError:
        raise ChecksError(f"Command not found: {args[0]}") from None

    output = f"exit_code: {result.returncode}\n\n"
    output += "=== stdout ===\n"
    output += result.stdout
    output += "\n=== stderr ===\n"
    output += result.stderr
    return output, result.returncode


def run_checks(
    config: ChecksConfig,
    cwd: Path,
    timeout: int | None = None,
    fail_fast: bool = True,
) -> ChecksSummary:
    """Run checks by category with optional fail-fast.

    Args:
        config: ChecksConfig with category commands
        cwd: Working directory
        timeout: Timeout per check category
        fail_fast: If True, stop at first failure (for iteration loop)
                   If False, run all checks (for review context)

    Returns:
        ChecksSummary with per-category results
    """
    # Handle legacy single-command mode
    if config.is_legacy_mode():
        if config.command is None:
            raise RuntimeError("Legacy mode requires command")  # Should never happen
        output, exit_code = run_single_check(config.command, cwd, timeout)
        passed = exit_code == 0
        return ChecksSummary(
            categories={
                "default": CategoryResult(
                    category="default",
                    exit_code=exit_code,
                    passed=passed,
                    output=output,
                )
            },
            first_failure=None if passed else "default",
            all_passed=passed,
        )

    categories = config.get_categories()
    if not categories:
        # No checks configured
        return ChecksSummary(categories={}, first_failure=None, all_passed=True)

    results: dict[str, CategoryResult] = {}
    first_failure: str | None = None

    for name, command in categories.items():
        try:
            output, exit_code = run_single_check(command, cwd, timeout)
            passed = exit_code == 0
        except ChecksError as e:
            output = str(e)
            exit_code = 1
            passed = False

        results[name] = CategoryResult(
            category=name,
            exit_code=exit_code,
            passed=passed,
            output=output,
        )

        if not passed and first_failure is None:
            first_failure = name
            if fail_fast:
                break

    return ChecksSummary(
        categories=results,
        first_failure=first_failure,
        all_passed=first_failure is None,
    )


def write_checks(path: Path, output: str) -> None:
    """Write checks output to file.

    Args:
        path: File path to write to
        output: Checks output content
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output)


def write_checks_results(iter_dir: Path, summary: ChecksSummary) -> None:
    """Write checks results to iteration directory.

    Creates checks/ subdirectory with per-category output files
    and checks.summary.json. Only creates the checks/ directory
    if there are categories to write.

    Args:
        iter_dir: Path to iteration directory
        summary: ChecksSummary with category results
    """
    # Only create checks directory if there are categories
    if summary.categories:
        checks_dir = iter_dir / "checks"
        checks_dir.mkdir(parents=True, exist_ok=True)
        for name, result in summary.categories.items():
            (checks_dir / f"{name}.txt").write_text(result.output)

    # Always write the summary JSON
    (iter_dir / "checks.summary.json").write_text(summary.model_dump_json(indent=2))
