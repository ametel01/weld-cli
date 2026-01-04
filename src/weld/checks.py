"""Checks runner for weld."""

import subprocess
from pathlib import Path


def run_checks(command: str, cwd: Path) -> tuple[str, int]:
    """Run checks command and return (output, exit_code).

    Args:
        command: Shell command to run
        cwd: Working directory

    Returns:
        Tuple of (formatted output with stdout/stderr, exit code)
    """
    result = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
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
