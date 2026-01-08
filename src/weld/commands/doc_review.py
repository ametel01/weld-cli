"""Review CLI command for documents and code changes.

Validates documentation against the actual codebase state, or reviews
git diff for bugs, missing implementations, and test issues.
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.panel import Panel

from ..config import WeldConfig, load_config
from ..core import generate_code_review_prompt, get_weld_dir, strip_preamble
from ..core.doc_review_engine import generate_doc_review_prompt, get_doc_review_dir
from ..output import OutputContext, get_output_context
from ..services import (
    ClaudeError,
    GitError,
    get_diff,
    get_repo_root,
    run_claude,
    track_session_activity,
)


def doc_review(
    document: Annotated[
        Path | None,
        typer.Argument(
            help="Markdown document to review against the codebase",
        ),
    ] = None,
    diff: Annotated[
        bool,
        typer.Option(
            "--diff",
            "-d",
            help="Review git diff instead of a document",
        ),
    ] = False,
    staged: Annotated[
        bool,
        typer.Option(
            "--staged",
            "-s",
            help="Review only staged changes (with --diff)",
        ),
    ] = False,
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
            help="Apply corrections/fixes directly",
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
    timeout: Annotated[
        int | None,
        typer.Option(
            "--timeout",
            "-t",
            help="Timeout in seconds for Claude (default: 1800 from config)",
        ),
    ] = None,
    focus: Annotated[
        str | None,
        typer.Option(
            "--focus",
            "-f",
            help="Topic to focus the review on",
        ),
    ] = None,
    track: Annotated[
        bool,
        typer.Option("--track", help="Track session activity for this command"),
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

    With --diff, reviews code changes instead:
    - Bugs and logic errors
    - Security vulnerabilities
    - Missing implementations
    - Test issues (assertions, coverage)
    - Significant improvements needed

    Use --diff --apply to have Claude fix all issues directly.

    Examples:
        weld review ARCHITECTURE.md --output findings.md
        weld review README.md --apply
        weld review --diff                    # Review all uncommitted changes
        weld review --diff --staged           # Review only staged changes
        weld review --diff --apply            # Review and fix all issues
    """
    ctx = get_output_context()

    # Validate arguments
    if diff and document:
        ctx.console.print("[red]Error: Cannot use --diff with a document argument[/red]")
        raise typer.Exit(1)

    if staged and not diff:
        ctx.console.print("[red]Error: --staged requires --diff[/red]")
        raise typer.Exit(1)

    if not diff and not document:
        ctx.console.print("[red]Error: Either provide a document or use --diff[/red]")
        raise typer.Exit(1)

    if document and not document.exists():
        ctx.console.print(f"[red]Error: Document not found: {document}[/red]")
        raise typer.Exit(1)

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

    # Use CLI timeout if specified, otherwise fall back to config timeout
    effective_timeout = timeout if timeout is not None else config.claude.timeout

    # Branch to code review or document review
    if diff:
        _run_code_review(
            ctx=ctx,
            repo_root=repo_root,
            weld_dir=weld_dir,
            config=config,
            staged=staged,
            output=output,
            apply=apply,
            prompt_only=prompt_only,
            quiet=quiet,
            timeout=effective_timeout,
            focus=focus,
            track=track,
        )
    else:
        assert document is not None  # Validated above
        _run_doc_review(
            ctx=ctx,
            repo_root=repo_root,
            weld_dir=weld_dir,
            config=config,
            document=document,
            output=output,
            apply=apply,
            prompt_only=prompt_only,
            quiet=quiet,
            timeout=effective_timeout,
            focus=focus,
            track=track,
        )


def _run_code_review(
    ctx: OutputContext,
    repo_root: Path,
    weld_dir: Path,
    config: WeldConfig,
    staged: bool,
    output: Path | None,
    apply: bool,
    prompt_only: bool,
    quiet: bool,
    timeout: int,
    focus: str | None,
    track: bool,
) -> None:
    """Run code review on git diff."""
    # Get diff content
    diff_content = get_diff(staged=staged, cwd=repo_root)

    if not diff_content.strip():
        change_type = "staged" if staged else "uncommitted"
        ctx.console.print(f"[yellow]No {change_type} changes to review.[/yellow]")
        raise typer.Exit(0)

    # Generate review ID
    mode_suffix = "fix" if apply else "review"
    staged_suffix = "-staged" if staged else ""
    review_id = datetime.now().strftime(f"%Y%m%d-%H%M%S-code{staged_suffix}-{mode_suffix}")

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would create code review:")
        ctx.console.print(f"  Review ID: {review_id}")
        ctx.console.print(f"  Changes: {'staged only' if staged else 'all uncommitted'}")
        ctx.console.print(f"  Mode: {'apply fixes' if apply else 'findings report'}")
        if output and not apply:
            ctx.console.print(f"  Output: {output}")
        if not prompt_only:
            action = "fix issues directly" if apply else "review code changes"
            ctx.console.print(f"  Action: Run Claude to {action}")
        return

    # Create review artifact directory
    review_dir = get_doc_review_dir(weld_dir)
    artifact_dir = review_dir / review_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Save diff for reference
    diff_path = artifact_dir / "diff.patch"
    diff_path.write_text(diff_content)

    # Generate and write prompt
    prompt = generate_code_review_prompt(diff_content, apply_mode=apply, focus=focus)
    prompt_path = artifact_dir / "prompt.md"
    prompt_path.write_text(prompt)

    # Show run created
    mode_label = "Code fix" if apply else "Code review"
    change_type = "staged changes" if staged else "all uncommitted changes"
    ctx.console.print(Panel(f"[bold]{mode_label}:[/bold] {review_id}", style="green"))
    ctx.console.print(f"[dim]Changes: {change_type}[/dim]")
    ctx.console.print(f"[dim]Prompt: .weld/reviews/{review_id}/prompt.md[/dim]")

    if prompt_only:
        output_msg = f" Output path: {output}" if output and not apply else ""
        ctx.console.print(f"\n[bold]Prompt generated.[/bold]{output_msg}")
        ctx.console.print("\n[bold]Next steps:[/bold]")
        ctx.console.print("  1. Copy prompt.md content to Claude")
        if apply:
            ctx.console.print("  2. Claude will fix issues directly in the files")
        else:
            ctx.console.print("  2. Save response to the output path")
        return

    # Run Claude directly with streaming
    action_msg = "fix issues" if apply else "review code changes"
    ctx.console.print(f"\n[bold]Running Claude to {action_msg}...[/bold]\n")

    # Get claude config from weld config
    claude_exec = config.claude.exec if config.claude else "claude"

    def _run() -> str:
        return run_claude(
            prompt=prompt,
            exec_path=claude_exec,
            cwd=repo_root,
            stream=not quiet,
            timeout=timeout,
            skip_permissions=apply,  # Allow file writes in apply mode
            max_output_tokens=config.claude.max_output_tokens,
        )

    try:
        if track:
            with track_session_activity(weld_dir, repo_root, "review"):
                result = _run()
        else:
            result = _run()
    except ClaudeError as e:
        ctx.console.print(f"\n[red]Error: Claude failed: {e}[/red]")
        raise typer.Exit(1) from None

    # Save result to artifact directory
    result_name = "fixes.md" if apply else "findings.md"
    result_path = artifact_dir / result_name
    result_path.write_text(result)

    if apply:
        ctx.console.print("\n[green]✓ Fixes applied by Claude[/green]")
        ctx.console.print(f"[dim]Summary saved to .weld/reviews/{review_id}/fixes.md[/dim]")
        ctx.console.print("\n[bold]Review the changes and run tests.[/bold]")
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
        ctx.console.print("\n[bold]Review complete.[/bold] Check the findings for issues.")


def _run_doc_review(
    ctx: OutputContext,
    repo_root: Path,
    weld_dir: Path,
    config: WeldConfig,
    document: Path,
    output: Path | None,
    apply: bool,
    prompt_only: bool,
    quiet: bool,
    timeout: int,
    focus: str | None,
    track: bool,
) -> None:
    """Run document review against codebase."""
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
    prompt = generate_doc_review_prompt(document_content, apply_mode=apply, focus=focus)
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

    def _run() -> str:
        return run_claude(
            prompt=prompt,
            exec_path=claude_exec,
            cwd=repo_root,
            stream=not quiet,
            timeout=timeout,
            skip_permissions=apply,  # Allow file writes in apply mode
            max_output_tokens=config.claude.max_output_tokens,
        )

    try:
        if track:
            with track_session_activity(weld_dir, repo_root, "review"):
                result = _run()
        else:
            result = _run()
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
