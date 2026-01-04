"""Checks runner for weld."""

import shlex
import subprocess
from pathlib import Path

from ..constants import CHECKS_TIMEOUT


class ChecksError(Exception):
    """Error running checks."""

    pass


def run_checks(
    command: str,
    cwd: Path,
    timeout: int | None = None,
) -> tuple[str, int]:
    """Run checks command and return (output, exit_code).

    Args:
        command: Shell command to run (will be parsed safely)
        cwd: Working directory
        timeout: Optional timeout in seconds (default: 300)

    Returns:
        Tuple of (formatted output with stdout/stderr, exit code)

    Raises:
        ChecksError: If command times out or fails to execute
    """
    timeout = timeout or CHECKS_TIMEOUT

    try:
        # Parse command safely - this handles quoting properly
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
        raise ChecksError(f"Checks timed out after {timeout} seconds") from e
    except FileNotFoundError:
        raise ChecksError(f"Command not found: {args[0]}") from None

    output = f"exit_code: {result.returncode}\n\n"
    output += "=== stdout ===\n"
    output += result.stdout
    output += "\n=== stderr ===\n"
    output += result.stderr
    return output, result.returncode


def write_checks(path: Path, output: str) -> None:
    """Write checks output to file.

    Args:
        path: File path to write to
        output: Checks output content
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output)
