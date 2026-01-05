"""Plan command implementation."""

from pathlib import Path

import typer

from ..core import get_weld_dir, log_command
from ..output import get_output_context
from ..services import ClaudeError, GitError, get_repo_root, run_claude


def generate_plan_prompt(spec_content: str, spec_name: str) -> str:
    """Generate prompt for creating an implementation plan.

    Args:
        spec_content: Content of the specification file
        spec_name: Name of the specification file

    Returns:
        Formatted prompt for Claude
    """
    return f"""# Implementation Plan Request

Read the following specification carefully and create an implementation plan.

## Specification: {spec_name}

{spec_content}

---

## Planning Principles

Planning is the highest-leverage activity. A good plan:
- Lists exact steps
- References concrete files and snippets
- Specifies validation after each change
- Makes failure modes obvious

A solid plan dramatically constrains agent behavior.

## Output Format

Create a step-by-step implementation plan. Each step must follow this format:

## Step N: <Title>

### Goal
Brief description of what this step accomplishes.

### Files
- `path/to/file.py` - What changes to make

### Validation
```bash
# Command to verify this step works
```

### Failure modes
- What could go wrong and how to detect it

---

Guidelines:
- Each step should be independently verifiable
- Steps should be atomic and focused
- Order steps by dependency (do prerequisites first)
- Reference specific files, functions, and line numbers where possible
- Include concrete validation commands for each step
"""


def plan(
    input_file: Path = typer.Argument(..., help="Specification markdown file"),
    output: Path = typer.Option(..., "--output", "-o", help="Output path for the plan"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress streaming output"),
) -> None:
    """Generate an implementation plan from a specification."""
    ctx = get_output_context()

    if not input_file.exists():
        ctx.error(f"Input file not found: {input_file}")
        raise typer.Exit(1)

    # Get weld directory for history logging (optional - plan can run without init)
    try:
        repo_root = get_repo_root()
        weld_dir = get_weld_dir(repo_root)
    except GitError:
        repo_root = None
        weld_dir = None

    spec_content = input_file.read_text()
    prompt = generate_plan_prompt(spec_content, input_file.name)

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would generate plan:")
        ctx.console.print(f"  Input: {input_file}")
        ctx.console.print(f"  Output: {output}")
        ctx.console.print("\n[cyan]Prompt:[/cyan]")
        ctx.console.print(prompt)
        return

    ctx.console.print(f"[cyan]Generating plan from {input_file.name}...[/cyan]\n")

    try:
        result = run_claude(prompt=prompt, stream=not quiet)
    except ClaudeError as e:
        ctx.error(f"Claude failed: {e}")
        raise typer.Exit(1) from None

    # Write output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result)

    # Log to history (only if weld is initialized)
    if weld_dir and weld_dir.exists():
        log_command(weld_dir, "plan", str(input_file), str(output))

    ctx.success(f"Plan written to {output}")
