"""Document review CLI command.

Validates documentation against the actual codebase state.
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from ..config import load_config
from ..core import get_weld_dir, strip_preamble
from ..core.doc_review_engine import generate_doc_review_prompt, get_doc_review_dir
from ..output import get_output_context
from ..services import ClaudeError, GitError, get_repo_root, run_claude


def doc_review(
    document: Annotated[
        Path,
        typer.Argument(
            help="Markdown document to review against the codebase",
            exists=True,
            readable=True,
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Path to write the findings report",
        ),
    ] = None,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Apply corrections directly to the document",
        ),
    ] = False,
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
    """Review a document against the current codebase state.

    Compares documentation claims against actual code to find:
    - Errors (factually incorrect statements)
    - Missing implementations (documented but not coded)
    - Missing steps (gaps in workflows)
    - Wrong evaluations (incorrect assessments)
    - Gaps (undocumented important features)

    Use --apply to have Claude correct the document in place.

    Examples:
        weld review ARCHITECTURE.md --output findings.md
        weld review README.md --apply
    """
    ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        ctx.console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    if not weld_dir.exists():
        ctx.console.print("[red]Error: Weld not initialized. Run 'weld init' first.[/red]")
        raise typer.Exit(1)

    config = load_config(repo_root)

    # Read document content
    document_content = document.read_text()

    # Generate review ID
    mode_suffix = "apply" if apply else "review"
    review_id = datetime.now().strftime(f"%Y%m%d-%H%M%S-{mode_suffix}")

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would create document review:")
        ctx.console.print(f"  Review ID: {review_id}")
        ctx.console.print(f"  Document: {document}")
        ctx.console.print(f"  Mode: {'apply corrections' if apply else 'findings report'}")
        if output and not apply:
            ctx.console.print(f"  Output: {output}")
        if not prompt_only:
            action = "correct document in place" if apply else "review document against codebase"
            ctx.console.print(f"  Action: Run Claude to {action}")
        return

    # Create review artifact directory
    review_dir = get_doc_review_dir(weld_dir)
    artifact_dir = review_dir / review_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Generate and write prompt
    prompt = generate_doc_review_prompt(document_content, apply_mode=apply)
    prompt_path = artifact_dir / "prompt.md"
    prompt_path.write_text(prompt)

    # Save original document for reference in apply mode
    if apply:
        original_path = artifact_dir / "original.md"
        original_path.write_text(document_content)

    # Show run created
    mode_label = "Document correction" if apply else "Document review"
    ctx.console.print(Panel(f"[bold]{mode_label}:[/bold] {review_id}", style="green"))
    ctx.console.print(f"[dim]Document: {document.name}[/dim]")
    ctx.console.print(f"[dim]Prompt: .weld/reviews/{review_id}/prompt.md[/dim]")

    if prompt_only:
        output_msg = f" Output path: {output}" if output and not apply else ""
        ctx.console.print(f"\n[bold]Prompt generated.[/bold]{output_msg}")
        ctx.console.print("\n[bold]Next steps:[/bold]")
        ctx.console.print("  1. Copy prompt.md content to Claude")
        if apply:
            ctx.console.print(f"  2. Save corrected document to {document}")
        else:
            ctx.console.print("  2. Save response to the output path")
        return

    # Run Claude directly with streaming
    action_msg = "correct document" if apply else "review document"
    ctx.console.print(f"\n[bold]Running Claude to {action_msg}...[/bold]\n")

    # Get claude config from weld config
    claude_exec = config.claude.exec if config.claude else "claude"

    try:
        result = run_claude(
            prompt=prompt,
            exec_path=claude_exec,
            cwd=repo_root,
            stream=not quiet,
        )
    except ClaudeError as e:
        ctx.console.print(f"\n[red]Error: Claude failed: {e}[/red]")
        raise typer.Exit(1) from None

    # Strip any AI preamble from the result
    result = strip_preamble(result)

    # Save result to artifact directory
    result_name = "corrected.md" if apply else "findings.md"
    result_path = artifact_dir / result_name
    result_path.write_text(result)

    if apply:
        # Write corrected content back to original file path
        doc_path = document
        doc_path.write_text(result)
        ctx.console.print(f"\n[green]✓ Document corrected: {doc_path}[/green]")
        ctx.console.print(f"[dim]Original saved to .weld/reviews/{review_id}/original.md[/dim]")
        ctx.console.print("\n[bold]Correction complete.[/bold] Review the changes.")
    else:
        # Write output file if specified
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(result)
            ctx.console.print(f"\n[green]✓ Findings written to {output}[/green]")
        else:
            ctx.console.print(
                f"\n[green]✓ Findings saved to .weld/reviews/{review_id}/findings.md[/green]"
            )
        ctx.console.print("\n[bold]Review complete.[/bold] Check the findings for discrepancies.")
