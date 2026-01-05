"""Weld CLI: Human-in-the-loop coding harness.

This module provides the CLI entry point and argument parsing.
Command implementations are in the commands/ package.
"""

import typer
from rich.console import Console

from weld import __version__

from .commands import (
    commit,
    init,
    list_runs_cmd,
    plan_import,
    plan_prompt,
    plan_review,
    run_start,
    step_fix_prompt,
    step_loop,
    step_review_cmd,
    step_select,
    step_snapshot,
    transcript_gist,
)
from .commands.discover import discover_app
from .commands.interview import interview
from .commands.research import research_app
from .logging import configure_logging
from .output import OutputContext, set_output_context


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
plan_app = typer.Typer(help="Plan management commands")
step_app = typer.Typer(help="Step implementation commands")
transcript_app = typer.Typer(help="Transcript management commands")

app.add_typer(discover_app, name="discover")
app.add_typer(plan_app, name="plan")
app.add_typer(research_app, name="research")
app.add_typer(step_app, name="step")
app.add_typer(transcript_app, name="transcript")

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
app.command("run")(run_start)
app.command()(commit)
app.command()(interview)
app.command("list")(list_runs_cmd)

# Plan subcommands
plan_app.command("prompt")(plan_prompt)
plan_app.command("import")(plan_import)
plan_app.command("review")(plan_review)

# Step subcommands
step_app.command("select")(step_select)
step_app.command("snapshot")(step_snapshot)
step_app.command("review")(step_review_cmd)
step_app.command("fix-prompt")(step_fix_prompt)
step_app.command("loop")(step_loop)

# Transcript subcommands
transcript_app.command("gist")(transcript_gist)


if __name__ == "__main__":
    app()
