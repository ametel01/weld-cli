"""Discover command implementation."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from ..config import load_config
from ..core import get_weld_dir, log_command, strip_preamble
from ..core.discover_engine import generate_discover_prompt, get_discover_dir
from ..output import get_output_context
from ..services import ClaudeError, GitError, get_repo_root, run_claude

discover_app = typer.Typer(
    help="Analyze codebase and generate architecture documentation",
    invoke_without_command=True,
)


@discover_app.callback(invoke_without_command=True)
def discover(
    ctx: typer.Context,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Path to write discover output",
        ),
    ] = None,
    focus: Annotated[
        str | None,
        typer.Option(
            "--focus",
            "-f",
            help="Specific areas to focus on",
        ),
    ] = None,
    prompt_only: Annotated[
        bool,
        typer.Option(
            "--prompt-only",
            help="Only generate prompt without running Claude",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            "-q",
            help="Suppress Claude output (only show result)",
        ),
    ] = False,
) -> None:
    """Analyze codebase and generate architecture documentation.

    If --output is not specified, writes to .weld/discover/{timestamp}.md
    Use --prompt-only to generate the prompt without running Claude.
    """
    if ctx.invoked_subcommand is not None:
        return

    _run_discover(output, focus, prompt_only, quiet)


def _run_discover(output: Path | None, focus: str | None, prompt_only: bool, quiet: bool) -> None:
    """Execute the discover workflow."""
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    # Get weld directory for history logging and default output
    weld_dir = get_weld_dir(repo_root)

    # Determine output path
    if output is None:
        if not weld_dir.exists():
            ctx.error("Weld not initialized. Use --output or run 'weld init' first.")
            raise typer.Exit(1)
        discover_dir = get_discover_dir(weld_dir)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = discover_dir / f"{timestamp}.md"

    # Load config from repo root (weld init not required for discover)
    config = load_config(repo_root)

    # Generate prompt
    prompt = generate_discover_prompt(focus)

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would run discover:")
        ctx.console.print(f"  Output: {output}")
        ctx.console.print("\n[cyan]Prompt:[/cyan]")
        ctx.console.print(prompt)
        return

    if prompt_only:
        ctx.console.print(prompt)
        return

    # Run Claude
    ctx.console.print("[cyan]Analyzing codebase...[/cyan]\n")

    claude_exec = config.claude.exec if config.claude else "claude"

    try:
        result = run_claude(
            prompt=prompt,
            exec_path=claude_exec,
            cwd=repo_root,
            stream=not quiet,
            max_output_tokens=config.claude.max_output_tokens,
        )
    except ClaudeError as e:
        ctx.error(f"Claude failed: {e}")
        raise typer.Exit(1) from None

    # Strip any AI preamble
    result = strip_preamble(result)

    # Write output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result)

    # Log to history (only if weld is initialized)
    if weld_dir.exists():
        log_command(weld_dir, "discover", "", str(output))

    ctx.success(f"Architecture documentation written to {output}")
