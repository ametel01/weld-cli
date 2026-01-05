"""Doctor command for environment validation."""

import shutil
import subprocess

import typer

from ..constants import INIT_TOOL_CHECK_TIMEOUT
from ..output import get_output_context

REQUIRED_TOOLS = [
    ("git", "git --version"),
    ("gh", "gh --version"),
]

OPTIONAL_TOOLS = [
    ("codex", "codex --version"),
    ("claude", "claude --version"),
    ("claude-code-transcripts", "claude-code-transcripts --version"),
]


def check_tool(name: str, version_cmd: str) -> tuple[bool, str]:
    """Check if a tool is available.

    Returns:
        Tuple of (available, version_or_error)
    """
    if not shutil.which(name):
        return False, "not found in PATH"

    try:
        result = subprocess.run(
            version_cmd.split(),
            capture_output=True,
            text=True,
            timeout=INIT_TOOL_CHECK_TIMEOUT,
        )
        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0]
            return True, version
        return False, f"exit code {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def doctor() -> None:
    """Check environment and dependencies."""
    ctx = get_output_context()
    all_ok = True

    # Collect results for JSON output
    required_results: dict[str, dict[str, str | bool]] = {}
    optional_results: dict[str, dict[str, str | bool]] = {}

    ctx.print("\n[bold]Required Tools[/bold]")
    for name, cmd in REQUIRED_TOOLS:
        ok, info = check_tool(name, cmd)
        required_results[name] = {"available": ok, "info": info}
        if ok:
            ctx.print(f"  [green]✓[/green] {name}: {info}")
        else:
            ctx.print(f"  [red]✗[/red] {name}: {info}")
            all_ok = False

    ctx.print("\n[bold]Optional Tools[/bold]")
    for name, cmd in OPTIONAL_TOOLS:
        ok, info = check_tool(name, cmd)
        optional_results[name] = {"available": ok, "info": info}
        if ok:
            ctx.print(f"  [green]✓[/green] {name}: {info}")
        else:
            ctx.print(f"  [yellow]○[/yellow] {name}: {info}")

    ctx.print("")

    if all_ok:
        ctx.success(
            "All required dependencies available",
            {"required": required_results, "optional": optional_results},
        )
    else:
        ctx.error(
            "Some required dependencies missing",
            {"required": required_results, "optional": optional_results},
        )
        raise typer.Exit(2) from None
