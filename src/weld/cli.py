"""Weld CLI: Human-in-the-loop coding harness.

This module provides the CLI entry point and argument parsing.
Command implementations are in the commands/ package.
"""

import typer
from rich.console import Console

from weld import __version__

from .commands.commit import commit
from .commands.discover import discover_app
from .commands.doc_review import doc_review
from .commands.doctor import doctor
from .commands.implement import implement
from .commands.init import init
from .commands.interview import interview
from .commands.plan import plan
from .commands.research import research
from .logging import configure_logging, setup_debug_logging
from .output import OutputContext, set_output_context
from .telegram.cli import telegram_app


def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"weld {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="weld",
    help="Human-in-the-loop coding harness with transcript provenance",
    no_args_is_help=True,
)

# Sub-command groups
app.add_typer(discover_app, name="discover")
app.add_typer(telegram_app, name="telegram")

# Global console (initialized in main callback)
_console: Console | None = None


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase verbosity (-v, -vv)",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress non-error output",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output in JSON format for automation",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable colored output",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview effects without applying changes",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug logging for this invocation",
    ),
) -> None:
    """Weld CLI - Human-in-the-loop coding harness."""
    global _console
    # Configure logging (uses stderr)
    _console = configure_logging(
        verbosity=verbose,
        quiet=quiet,
        no_color=no_color,
        debug=debug,
    )
    # Setup debug file logging if in a git repo
    if debug:
        from .core import get_weld_dir
        from .services.git import GitError

        try:
            weld_dir = get_weld_dir()
            setup_debug_logging(weld_dir, enabled=True)
        except GitError:
            # Not in a git repository - skip file logging
            pass
        except OSError:
            # File system error (permissions, disk full, etc.) - skip file logging
            pass
    # Create output console for user-facing messages (uses stdout)
    # Don't force terminal mode - let Rich auto-detect (tests won't have TTY)
    output_console = Console(no_color=no_color)
    ctx = OutputContext(console=output_console, json_mode=json_output, dry_run=dry_run)
    set_output_context(ctx)


# ============================================================================
# Register commands from commands/ package
# ============================================================================

# Top-level commands
app.command()(init)
app.command()(commit)
app.command()(implement)
app.command()(interview)
app.command()(doctor)
app.command()(plan)
app.command()(research)
app.command("review")(doc_review)


if __name__ == "__main__":
    app()
