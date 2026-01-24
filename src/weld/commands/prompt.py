"""Prompt customization management commands.

Provides CLI commands to list, show, and export prompt customizations
configured in the project's .weld/config.toml [prompts] section.
"""

from pathlib import Path
from typing import Annotated

import typer

from ..config import TaskType, load_config
from ..core import get_weld_dir
from ..output import get_output_context
from ..services import GitError, get_repo_root

prompt_app = typer.Typer(
    help="Manage prompt customizations",
    invoke_without_command=True,
)


@prompt_app.callback(invoke_without_command=True)
def prompt_callback(ctx: typer.Context) -> None:
    """Manage prompt customizations.

    When invoked without a subcommand, shows a summary of configured customizations.
    """
    if ctx.invoked_subcommand is not None:
        return

    # Default behavior: show summary (same as 'list')
    list_prompts()


# Human-readable descriptions for each task type
TASK_DESCRIPTIONS: dict[TaskType, str] = {
    TaskType.DISCOVER: "Brownfield codebase discovery and analysis",
    TaskType.INTERVIEW: "Interactive specification refinement",
    TaskType.RESEARCH: "Research prompts for gathering context",
    TaskType.RESEARCH_REVIEW: "Review of research outputs",
    TaskType.PLAN_GENERATION: "Implementation plan generation",
    TaskType.PLAN_REVIEW: "Review of generated plans",
    TaskType.IMPLEMENTATION: "Code implementation phase",
    TaskType.IMPLEMENTATION_REVIEW: "Review of implemented code",
    TaskType.FIX_GENERATION: "Generate fixes for review feedback",
    TaskType.DOC_REVIEW: "Document review and analysis",
    TaskType.CODE_REVIEW: "Code review and quality assessment",
    TaskType.COMMIT: "Commit message generation",
}


@prompt_app.command("list")
def list_prompts() -> None:
    """List all available prompt types with descriptions."""
    from rich.table import Table

    output_ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        output_ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    if not weld_dir.exists():
        output_ctx.error("Weld not initialized. Run 'weld init' first.")
        raise typer.Exit(1)

    config = load_config(weld_dir)
    prompts_config = config.prompts

    # Build data for all task types
    task_data: list[dict[str, str | bool | None]] = []
    for task in TaskType:
        custom = prompts_config.get_customization(task)
        has_customization = bool(custom.prefix or custom.suffix or custom.default_focus)
        task_data.append(
            {
                "name": task.value,
                "description": TASK_DESCRIPTIONS.get(task, ""),
                "customized": has_customization,
                "prefix": custom.prefix,
                "suffix": custom.suffix,
                "default_focus": custom.default_focus,
            }
        )

    # Check global settings
    has_global = bool(prompts_config.global_prefix or prompts_config.global_suffix)

    if output_ctx.json_mode:
        result = {
            "global": {
                "prefix": prompts_config.global_prefix,
                "suffix": prompts_config.global_suffix,
            }
            if has_global
            else None,
            "tasks": task_data,
        }
        output_ctx.success("Available prompt types", result)
        return

    # Console output with Rich table
    output_ctx.console.print("[bold]Available Prompt Types[/bold]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Type", style="cyan")
    table.add_column("Description")
    table.add_column("Customized", justify="center")

    for task in TaskType:
        custom = prompts_config.get_customization(task)
        has_customization = bool(custom.prefix or custom.suffix or custom.default_focus)
        status = "[green]✓[/green]" if has_customization else "[dim]-[/dim]"
        table.add_row(
            task.value,
            TASK_DESCRIPTIONS.get(task, ""),
            status,
        )

    output_ctx.console.print(table)

    # Show global customization status
    output_ctx.console.print()
    if has_global:
        output_ctx.console.print("[cyan]Global customization:[/cyan] [green]✓ configured[/green]")
        if prompts_config.global_prefix:
            output_ctx.console.print(f"  prefix: {_truncate(prompts_config.global_prefix)}")
        if prompts_config.global_suffix:
            output_ctx.console.print(f"  suffix: {_truncate(prompts_config.global_suffix)}")
    else:
        output_ctx.console.print("[cyan]Global customization:[/cyan] [dim]not configured[/dim]")

    output_ctx.console.print(
        "\n[dim]Use 'weld prompt show <type>' to see full customization.[/dim]"
    )


# Base prompt templates for each task type (for --raw output)
# These are sample templates that show the structure - actual prompts come from engines
_BASE_PROMPT_TEMPLATES: dict[TaskType, str] = {
    TaskType.DISCOVER: """\
You are a senior software architect creating a comprehensive technical specification
document for an existing codebase.

## Focus Areas
{focus}

## Your Mission
Produce a detailed, exhaustive technical specification that fully documents this
codebase. This document will be used by developers to understand, maintain, and
extend the system.

(Full template in weld.core.discover_engine.DISCOVER_PROMPT_TEMPLATE)
""",
    TaskType.INTERVIEW: """\
You are an expert technical interviewer helping flesh out a specification document.

## Focus Area
{focus}

## Interview Scope
Ask about technical implementation details, architecture choices, UI/UX, edge cases,
tradeoffs, integrations, error handling, performance, and security.

(Full template in weld.core.interview_engine.INTERVIEW_SYSTEM_PROMPT)
""",
    TaskType.RESEARCH: """\
You are a senior software architect analyzing a specification for planning.

## Focus Areas
{focus}

## Research Requirements
Analyze this specification and produce comprehensive research covering:
- Architecture analysis
- Dependency mapping
- Risk assessment
- Open questions

(Full template in weld.commands.research.generate_research_prompt)
""",
    TaskType.RESEARCH_REVIEW: """\
Review research output for completeness and accuracy.

## Focus
{focus}
""",
    TaskType.PLAN_GENERATION: """\
You MUST output a structured implementation plan following the EXACT format specified.
Do NOT output summaries, overviews, or prose. Output ONLY the structured plan.

## Focus
{focus}

(Full template in weld.commands.plan.generate_plan_prompt)
""",
    TaskType.PLAN_REVIEW: """\
Review generated plan for feasibility, completeness, and correctness.

## Focus
{focus}
""",
    TaskType.IMPLEMENTATION: """\
Execute the specified implementation step following the plan.

## Focus
{focus}
""",
    TaskType.IMPLEMENTATION_REVIEW: """\
Review implemented code for correctness, style, and adherence to plan.

## Focus
{focus}

(Full template in weld.core.doc_review_engine.CODE_REVIEW_PROMPT_TEMPLATE)
""",
    TaskType.FIX_GENERATION: """\
Generate fixes based on review feedback.

## Focus
{focus}
""",
    TaskType.DOC_REVIEW: """\
Review documentation for completeness, accuracy, and clarity.

## Focus
{focus}

(Full template in weld.core.doc_review_engine.DOC_REVIEW_PROMPT_TEMPLATE)
""",
    TaskType.CODE_REVIEW: """\
Review code for correctness, style, performance, and security.

## Focus
{focus}

(Full template in weld.core.doc_review_engine.CODE_REVIEW_PROMPT_TEMPLATE)
""",
    TaskType.COMMIT: """\
Generate a commit message summarizing the changes.

## Focus
{focus}
""",
}


@prompt_app.command("show")
def show_prompt(
    task: Annotated[
        str,
        typer.Argument(help="Task type to show (e.g., discover, research, plan_generation)"),
    ],
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            "-r",
            help="Output raw prompt template without Rich formatting (suitable for piping)",
        ),
    ] = False,
    focus: Annotated[
        str | None,
        typer.Option(
            "--focus",
            "-f",
            help="Focus value to apply to the template preview",
        ),
    ] = None,
) -> None:
    """Show prompt template and customization for a specific task type.

    Use --raw to see the base prompt template without Rich formatting.
    Use --focus to preview how a focus value would be applied.
    """
    output_ctx = get_output_context()

    # Validate task type
    try:
        task_type = TaskType(task)
    except ValueError:
        valid_tasks = ", ".join(t.value for t in TaskType)
        if raw:
            # Plain error for pipe-friendly output
            print(f"Error: Invalid task type: {task}")
            print(f"Valid types: {valid_tasks}")
        else:
            output_ctx.error(
                f"Invalid task type: {task}", next_action=f"Valid types: {valid_tasks}"
            )
        raise typer.Exit(1) from None

    try:
        repo_root = get_repo_root()
    except GitError:
        if raw:
            print("Error: Not a git repository")
        else:
            output_ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    if not weld_dir.exists():
        if raw:
            print("Error: Weld not initialized. Run 'weld init' first.")
        else:
            output_ctx.error("Weld not initialized. Run 'weld init' first.")
        raise typer.Exit(1)

    config = load_config(weld_dir)
    prompts_config = config.prompts
    custom = prompts_config.get_customization(task_type)

    # Get effective focus: explicit > config default > placeholder
    effective_focus = focus or custom.default_focus or "(no focus specified)"

    if raw:
        # Output raw template for piping
        base_template = _BASE_PROMPT_TEMPLATES.get(task_type, f"No template for {task_type.value}")
        formatted_template = base_template.format(focus=effective_focus)

        # Apply customizations if present
        parts: list[str] = []

        if prompts_config.global_prefix:
            parts.append(f"# Global Prefix\n{prompts_config.global_prefix}")

        if custom.prefix:
            parts.append(f"# Task Prefix ({task_type.value})\n{custom.prefix}")

        parts.append(f"# Base Template\n{formatted_template}")

        if custom.suffix:
            parts.append(f"# Task Suffix ({task_type.value})\n{custom.suffix}")

        if prompts_config.global_suffix:
            parts.append(f"# Global Suffix\n{prompts_config.global_suffix}")

        print("\n\n".join(parts))
        return

    result = {
        "task": task_type.value,
        "global_prefix": prompts_config.global_prefix,
        "global_suffix": prompts_config.global_suffix,
        "prefix": custom.prefix,
        "suffix": custom.suffix,
        "default_focus": custom.default_focus,
        "effective_focus": effective_focus if focus else custom.default_focus,
    }

    if output_ctx.json_mode:
        output_ctx.success(f"Customization for {task_type.value}", result)
        return

    output_ctx.console.print(f"[bold]Prompt Customization: {task_type.value}[/bold]\n")

    output_ctx.console.print("[cyan]Global:[/cyan]")
    output_ctx.console.print(f"  prefix: {prompts_config.global_prefix or '(none)'}")
    output_ctx.console.print(f"  suffix: {prompts_config.global_suffix or '(none)'}")

    output_ctx.console.print(f"\n[cyan]Task ({task_type.value}):[/cyan]")
    output_ctx.console.print(f"  prefix: {custom.prefix or '(none)'}")
    output_ctx.console.print(f"  suffix: {custom.suffix or '(none)'}")
    output_ctx.console.print(f"  default_focus: {custom.default_focus or '(none)'}")

    if focus:
        output_ctx.console.print(f"\n[cyan]Preview focus:[/cyan] {focus}")

    output_ctx.console.print("\n[dim]Use --raw to see the full prompt template.[/dim]")


@prompt_app.command("export")
def export_prompts(
    directory: Annotated[
        Path | None,
        typer.Argument(
            help="Directory to export prompt templates to (creates if needed)",
        ),
    ] = None,
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            "-r",
            help="Export raw prompt templates as individual markdown files",
        ),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Path to write exported configuration (legacy, use directory argument instead)",
        ),
    ] = None,
    format_type: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help="Export format for config (toml or json), ignored with --raw",
        ),
    ] = "toml",
) -> None:
    """Export prompt templates or customizations.

    With --raw: exports all prompt templates as individual markdown files to the
    specified directory. Each task type gets its own file (e.g., discover.md).

    Without --raw: exports prompt customizations from config.toml in TOML or JSON format.
    """
    output_ctx = get_output_context()

    try:
        repo_root = get_repo_root()
    except GitError:
        output_ctx.error("Not a git repository")
        raise typer.Exit(3) from None

    weld_dir = get_weld_dir(repo_root)
    if not weld_dir.exists():
        output_ctx.error("Weld not initialized. Run 'weld init' first.")
        raise typer.Exit(1)

    config = load_config(weld_dir)
    prompts_config = config.prompts

    # Handle --raw mode: export templates as markdown files
    if raw:
        if directory is None:
            output_ctx.error(
                "Directory argument required with --raw",
                next_action="Usage: weld prompt export <directory> --raw",
            )
            raise typer.Exit(1)

        if output_ctx.dry_run:
            output_ctx.console.print(
                f"[cyan][DRY RUN][/cyan] Would export {len(_BASE_PROMPT_TEMPLATES)} "
                f"prompt templates to: {directory}"
            )
            return

        # Create directory if it doesn't exist
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            output_ctx.error(f"Failed to create directory: {e}")
            raise typer.Exit(1) from None

        # Export each template as a markdown file
        exported_count = 0
        for task_type, template in _BASE_PROMPT_TEMPLATES.items():
            custom = prompts_config.get_customization(task_type)
            effective_focus = custom.default_focus or "(no focus specified)"

            # Build the full prompt with customizations
            parts: list[str] = []

            if prompts_config.global_prefix:
                parts.append(f"## Global Prefix\n\n{prompts_config.global_prefix}")

            if custom.prefix:
                parts.append(f"## Task Prefix\n\n{custom.prefix}")

            # Format template with focus
            formatted_template = template.format(focus=effective_focus)
            parts.append(f"## Base Template\n\n{formatted_template}")

            if custom.suffix:
                parts.append(f"## Task Suffix\n\n{custom.suffix}")

            if prompts_config.global_suffix:
                parts.append(f"## Global Suffix\n\n{prompts_config.global_suffix}")

            # Write to file
            file_path = directory / f"{task_type.value}.md"
            try:
                content = f"# {task_type.value}\n\n" + "\n\n".join(parts)
                file_path.write_text(content)
                exported_count += 1
            except OSError as e:
                output_ctx.error(f"Failed to write {file_path}: {e}")
                raise typer.Exit(1) from None

        if output_ctx.json_mode:
            output_ctx.success(
                "Exported prompt templates",
                {"directory": str(directory), "count": exported_count},
            )
        else:
            output_ctx.success(f"Exported {exported_count} prompt templates to {directory}")
        return

    # Legacy behavior: export config as TOML/JSON
    if format_type not in ("toml", "json"):
        output_ctx.error(f"Invalid format: {format_type}", next_action="Use 'toml' or 'json'")
        raise typer.Exit(1)

    # Build export data
    export_data: dict[str, dict[str, str | None] | str | None] = {}

    if prompts_config.global_prefix:
        export_data["global_prefix"] = prompts_config.global_prefix
    if prompts_config.global_suffix:
        export_data["global_suffix"] = prompts_config.global_suffix

    for task in TaskType:
        custom = prompts_config.get_customization(task)
        if custom.prefix or custom.suffix or custom.default_focus:
            export_data[task.value] = {
                "prefix": custom.prefix,
                "suffix": custom.suffix,
                "default_focus": custom.default_focus,
            }

    # Use directory as output path if provided (backwards compat)
    effective_output = output or directory

    if output_ctx.dry_run:
        output_ctx.console.print(
            f"[cyan][DRY RUN][/cyan] Would export prompts to: {effective_output}"
        )
        return

    if format_type == "json":
        import json

        content = json.dumps(export_data, indent=2)
    else:  # toml
        import tomli_w

        content = tomli_w.dumps({"prompts": export_data})

    if effective_output is None:
        # Print to stdout
        output_ctx.console.print(content)
    else:
        effective_output.write_text(content)
        output_ctx.success(f"Exported prompt customizations to {effective_output}")


def _truncate(text: str, max_length: int = 50) -> str:
    """Truncate text for display, adding ellipsis if needed."""
    # Replace newlines with spaces for single-line display
    text = text.replace("\n", " ").strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
