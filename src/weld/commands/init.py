"""Init command implementation."""

import subprocess

import typer
from rich.console import Console

from ..config import write_config_template
from ..constants import INIT_TOOL_CHECK_TIMEOUT
from ..services import GitError, get_repo_root

console = Console()


def init() -> None:
    """Initialize weld in the current repository."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = repo_root / ".weld"

    # Create directories
    weld_dir.mkdir(exist_ok=True)
    (weld_dir / "runs").mkdir(exist_ok=True)

    # Create config if missing
    config_path = weld_dir / "config.toml"
    if not config_path.exists():
        write_config_template(weld_dir)
        console.print(f"[green]Created config template:[/green] {config_path}")
    else:
        console.print(f"[yellow]Config already exists:[/yellow] {config_path}")

    # Validate toolchain
    tools = {
        "git": ["git", "--version"],
        "gh": ["gh", "auth", "status"],
        "codex": ["codex", "--version"],
        "claude-code-transcripts": ["claude-code-transcripts", "--help"],
    }

    all_ok = True
    for name, cmd in tools.items():
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=INIT_TOOL_CHECK_TIMEOUT
            )
            if result.returncode == 0:
                console.print(f"[green]✓[/green] {name}")
            else:
                console.print(f"[red]✗[/red] {name}: {result.stderr.strip()[:50]}")
                all_ok = False
        except FileNotFoundError:
            console.print(f"[red]✗[/red] {name}: not found in PATH")
            all_ok = False
        except subprocess.TimeoutExpired:
            console.print(f"[yellow]?[/yellow] {name}: timed out")

    if not all_ok:
        console.print("\n[yellow]Warning: Some tools are missing or not configured[/yellow]")
        raise typer.Exit(2)

    console.print("\n[bold green]Weld initialized successfully![/bold green]")
