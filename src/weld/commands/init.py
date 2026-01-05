"""Init command implementation."""

import subprocess

import typer

from ..config import write_config_template
from ..constants import INIT_TOOL_CHECK_TIMEOUT
from ..output import get_output_context
from ..services import GitError, get_repo_root


def init() -> None:
    """Initialize weld in the current repository."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = repo_root / ".weld"
    config_path = weld_dir / "config.toml"

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would initialize weld in this repository:")
        ctx.console.print(f"  Create directory: {weld_dir}")
        ctx.console.print(f"  Create directory: {weld_dir / 'runs'}")
        if not config_path.exists():
            ctx.console.print(f"  Create config: {config_path}")
        else:
            ctx.console.print(f"  Config already exists: {config_path}")
        ctx.console.print("\n[cyan][DRY RUN][/cyan] Would check toolchain:")
        ctx.console.print("  git, gh, codex, claude-code-transcripts")
        return

    # Create directories
    weld_dir.mkdir(exist_ok=True)
    (weld_dir / "runs").mkdir(exist_ok=True)

    # Create config if missing
    if not config_path.exists():
        write_config_template(weld_dir)
        ctx.console.print(f"[green]Created config template:[/green] {config_path}")
    else:
        ctx.console.print(f"[yellow]Config already exists:[/yellow] {config_path}")

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
                ctx.console.print(f"[green]✓[/green] {name}")
            else:
                ctx.console.print(f"[red]✗[/red] {name}: {result.stderr.strip()[:50]}")
                all_ok = False
        except FileNotFoundError:
            ctx.console.print(f"[red]✗[/red] {name}: not found in PATH")
            all_ok = False
        except subprocess.TimeoutExpired:
            ctx.console.print(f"[yellow]?[/yellow] {name}: timed out")

    if not all_ok:
        ctx.console.print("\n[yellow]Warning: Some tools are missing or not configured[/yellow]")
        raise typer.Exit(2)

    ctx.console.print("\n[bold green]Weld initialized successfully![/bold green]")
