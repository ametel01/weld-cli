"""Interview CLI command for specification refinement."""

from pathlib import Path

import typer

from ..core.interview_engine import run_interview_loop
from ..output import get_output_context


def interview(
    file: Path = typer.Argument(..., help="Markdown file to refine"),
    focus: str | None = typer.Option(
        None,
        "--focus",
        "-f",
        help="Topic to focus questions on",
    ),
) -> None:
    """Interactively refine a specification through Q&A."""
    ctx = get_output_context()

    if not file.exists():
        ctx.console.print(f"[red]Error: File not found: {file}[/red]")
        raise typer.Exit(1) from None

    if file.suffix != ".md":
        ctx.console.print(
            "[yellow]Warning: File is not markdown - interview may not work well[/yellow]"
        )

    try:
        modified = run_interview_loop(
            file,
            focus,
            console=ctx.console,
            dry_run=ctx.dry_run,
        )
        if modified:
            ctx.console.print("[green]Document updated[/green]")
        else:
            ctx.console.print("No changes made")
    except KeyboardInterrupt:
        ctx.console.print("\n[yellow]Interview cancelled[/yellow]")
        raise typer.Exit(0) from None
