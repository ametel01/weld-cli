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
    plan_review,
    run_start,
    step_fix_prompt,
    step_loop,
    step_review_cmd,
    step_select,
    step_snapshot,
    transcript_gist,
)
from .logging import configure_logging
from .output import OutputContext


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

app.add_typer(plan_app, name="plan")
app.add_typer(step_app, name="step")
app.add_typer(transcript_app, name="transcript")

console = Console()

# Global output context
_ctx: OutputContext | None = None


def get_output_context() -> OutputContext:
    """Get the current output context."""
    if _ctx is None:
        return OutputContext(Console())
    return _ctx


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
) -> None:
    """Weld CLI - Human-in-the-loop coding harness."""
    global _ctx
    global console
    console = configure_logging(
        verbosity=verbose,
        quiet=quiet,
        no_color=no_color,
    )
    _ctx = OutputContext(console=console, json_mode=json_output)


# ============================================================================
# Register commands from commands/ package
# ============================================================================

# Top-level commands
app.command()(init)
app.command("run")(run_start)
app.command()(commit)
app.command("list")(list_runs_cmd)

# Plan subcommands
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
