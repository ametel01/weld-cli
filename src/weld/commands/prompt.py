"""Prompt customization management commands.

Provides CLI commands to list, show, and export prompt customizations
configured in the project's .weld/config.toml [prompts] section.
"""

from pathlib import Path
from typing import Annotated

import typer

from ..completions import complete_export_format, complete_task_type
from ..config import TaskType, load_config
from ..core import get_weld_dir
from ..core.discover_engine import DISCOVER_PROMPT_TEMPLATE
from ..core.doc_review_engine import (
    CODE_REVIEW_PROMPT_TEMPLATE,
    DOC_REVIEW_PROMPT_TEMPLATE,
)
from ..core.interview_engine import QUESTIONNAIRE_PROMPT as INTERVIEW_PROMPT
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


# =============================================================================
# Actual prompt templates for each task type
# =============================================================================

# Research prompt template (from commands/research.py)
RESEARCH_PROMPT_TEMPLATE = """\
# Research Request

You are a senior software architect researching how to implement a specification.

## Core Principles

1. **Read code, not docs** - The codebase is the source of truth. Documentation may be stale.
2. **Identify authoritative files** - Find the actual implementation, not abstractions.
3. **Eliminate assumptions** - Verify every claim by reading the code.
4. **Produce a short artifact** - Be concise. This document guides implementation.

If you don't ground your research in actual code, you will fabricate.
This mirrors Memento: without verified context, you invent narratives.

## Specification: {{spec_name}}

{{spec_content}}

---

## Focus Areas

Pay particular attention to: {focus}

## Research Process

Before writing anything, you MUST:

1. **Explore the codebase** - Use your tools to find relevant files
2. **Read actual implementations** - Don't guess based on file names
3. **Trace data flows** - Follow how data moves through the system
4. **Note specific locations** - Record file:line references for everything

## Research Output

Produce a **short, focused research document** covering:

### 1. Authoritative Files
List the key files that govern this area of the codebase:
- `path/to/file.py:42-100` - What this section does
- `path/to/other.py:15` - Entry point for X

### 2. Existing Patterns
How similar functionality is implemented:
- Pattern name and where it's used
- Code example or reference
- Why this pattern was chosen (if evident)

### 3. Integration Points
Where the new code will connect:
- Entry points to modify
- Interfaces to implement
- Data structures to use

### 4. Constraints & Risks
What could go wrong:
- Technical constraints discovered in code
- Potential conflicts with existing systems
- Areas needing careful implementation

### 5. Open Questions
Decisions requiring human input:
- Ambiguities that code doesn't resolve
- Trade-offs to discuss
- Alternative approaches found

## Output Format

- Keep it **short** - aim for 1-2 pages, not 10
- Every claim must have a **file:line reference**
- Use bullet points, not prose
- Mark uncertain items with [VERIFY]
"""

# Plan generation prompt template (from commands/plan.py)
PLAN_GENERATION_PROMPT_TEMPLATE = """\
# Implementation Plan Request

## Why Plans Matter

Planning is the **highest-leverage activity**. A solid plan dramatically constrains
agent behavior—and constraints produce quality.

A good plan:
- Lists **exact steps** (not vague intentions)
- References **concrete files and snippets** (not "the auth module")
- Specifies **validation after each change** (not "test later")
- Makes **failure modes obvious** (not hidden surprises)

Bad plans produce dozens of bad lines of code.
Bad research produces hundreds.
**Invest the time here.**

---

You MUST output a structured implementation plan following the EXACT format specified below.
Do NOT output summaries, overviews, or prose. Output ONLY the structured plan.

---

## CRITICAL: Required Output Format

Your output MUST follow this EXACT structure. Every step MUST have ALL four sections.

**Phase structure:**
```
## Phase <N>: <Title>

<One sentence description>

### Phase Validation
```bash
<command to verify phase>
```

### Step <N>: <Title>

#### Goal
<What this step accomplishes>

#### Files
- `<path>` - <what to change>

#### Validation
```bash
<command to verify step>
```

#### Failure modes
- <what could go wrong>

---
```

---

## Specifications

{{spec_content}}

---

## Planning Process

Before creating the plan, you MUST:

1. **Explore the codebase structure**: Use your tools to understand the project layout,
   key directories, and architectural patterns
2. **Identify relevant files**: Find existing files that need modification or that serve
   as reference implementations
3. **Understand existing patterns**: Review how similar features are implemented in
   the codebase
4. **Reference actual code locations**: Ground your plan in specific files, functions,
   and line numbers that exist

Your plan should reference concrete existing code locations and follow established
patterns in the codebase.

---

## Planning Rules

1. **Monotonic phases**: Phases ordered by dependency. No forward references.
   Later phases never require artifacts not built earlier.

2. **Discrete steps**: Single clear outcome per step, independently verifiable.

3. **Artifact-driven**: Every step produces concrete artifact (code, interface,
   schema, config, test). Forbid vague actions ("work on", "improve", "handle").

4. **Explicit dependencies**: Each step lists inputs and outputs.

5. **Vertical slices**: Each phase delivers end-to-end capability.
   Avoid "all infra first, all logic later". System runnable early.

6. **Invariants first**: Establish data models, state machines, invariants before features.

7. **Test parallelism**: Every functional step has paired validation.

8. **Rollback safety**: System builds and runs after each phase. Each phase shippable.

9. **Bounded scope**: Phase defines explicit "in" and "out". Clear completion criteria.

10. **Execution ready**: Imperative language ("Create", "Add", "Implement").
    Each step maps to concrete code change. No research-only placeholders.

---

## REMINDER: Output Format Checklist

Before outputting your plan, verify:

- [ ] Every phase has `## Phase N: Title` heading
- [ ] Every phase has `### Phase Validation` with bash command
- [ ] Every step has `### Step N: Title` heading
- [ ] Every step has `#### Goal` section
- [ ] Every step has `#### Files` section with bullet points
- [ ] Every step has `#### Validation` section with bash command
- [ ] Every step has `#### Failure modes` section
- [ ] Steps end with `---` separator
- [ ] NO bullet-point summaries or overviews
- [ ] NO prose paragraphs outside the structure
- [ ] NO questions to the user (e.g., "Would you like me to...")
- [ ] NO follow-up options or suggestions
- [ ] NO conversational closing

CRITICAL: This is a CLI tool. Your output will be written directly to a file.
Do NOT ask questions. Do NOT offer alternatives. Do NOT include any text after the final `---`.
Do NOT use the Write tool to create any files. Just output the plan content directly.
Output ONLY the structured plan now. Begin with `## Phase 1:`
"""

# Placeholder templates for tasks not yet fully implemented
_PLACEHOLDER_TEMPLATE = """\
[This task type does not have a dedicated prompt template yet]

Task: {task_type}
Focus: {focus}

This prompt is generated dynamically or uses the default AI behavior.
"""


def _get_base_prompt_template(task: TaskType) -> str:
    """Get the actual base prompt template for a task type.

    Returns the real prompt template used by the task, not a stub.
    """
    # Map task types to their actual templates
    templates: dict[TaskType, str] = {
        TaskType.DISCOVER: DISCOVER_PROMPT_TEMPLATE,
        TaskType.INTERVIEW: INTERVIEW_PROMPT,
        TaskType.RESEARCH: RESEARCH_PROMPT_TEMPLATE,
        TaskType.RESEARCH_REVIEW: _PLACEHOLDER_TEMPLATE.format(
            task_type="research_review", focus="{focus}"
        ),
        TaskType.PLAN_GENERATION: PLAN_GENERATION_PROMPT_TEMPLATE,
        TaskType.PLAN_REVIEW: _PLACEHOLDER_TEMPLATE.format(
            task_type="plan_review", focus="{focus}"
        ),
        TaskType.IMPLEMENTATION: _PLACEHOLDER_TEMPLATE.format(
            task_type="implementation", focus="{focus}"
        ),
        TaskType.IMPLEMENTATION_REVIEW: CODE_REVIEW_PROMPT_TEMPLATE,
        TaskType.FIX_GENERATION: _PLACEHOLDER_TEMPLATE.format(
            task_type="fix_generation", focus="{focus}"
        ),
        TaskType.DOC_REVIEW: DOC_REVIEW_PROMPT_TEMPLATE,
        TaskType.CODE_REVIEW: CODE_REVIEW_PROMPT_TEMPLATE,
        TaskType.COMMIT: _PLACEHOLDER_TEMPLATE.format(task_type="commit", focus="{focus}"),
    }
    return templates.get(task, f"No template defined for {task.value}")


@prompt_app.command("show")
def show_prompt(
    task: Annotated[
        str,
        typer.Argument(
            help="Task type to show (e.g., discover, research, plan_generation)",
            autocompletion=complete_task_type,
        ),
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
        base_template = _get_base_prompt_template(task_type)
        # Handle different placeholder formats in templates
        # Some use {focus}, some use {focus_areas}, some use {focus_area}
        try:
            formatted_template = base_template.format(
                focus=effective_focus,
                focus_areas=effective_focus,
                focus_area=effective_focus,
            )
        except KeyError:
            # Template has other placeholders - show as-is with focus note
            formatted_template = base_template

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
            autocompletion=complete_export_format,
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
                f"[cyan][DRY RUN][/cyan] Would export {len(TaskType)} "
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
        for task_type in TaskType:
            template = _get_base_prompt_template(task_type)
            custom = prompts_config.get_customization(task_type)
            effective_focus = custom.default_focus or "(no focus specified)"

            # Build the full prompt with customizations
            parts: list[str] = []

            if prompts_config.global_prefix:
                parts.append(f"## Global Prefix\n\n{prompts_config.global_prefix}")

            if custom.prefix:
                parts.append(f"## Task Prefix\n\n{custom.prefix}")

            # Format template with focus (handle different placeholder names)
            try:
                formatted_template = template.format(
                    focus=effective_focus,
                    focus_areas=effective_focus,
                    focus_area=effective_focus,
                )
            except KeyError:
                formatted_template = template
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
