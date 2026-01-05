"""Research command implementation."""

from pathlib import Path

import typer

from ..core import get_weld_dir, log_command
from ..output import get_output_context
from ..services import ClaudeError, GitError, get_repo_root, run_claude


def generate_research_prompt(spec_content: str, spec_name: str) -> str:
    """Generate prompt for researching a specification.

    Args:
        spec_content: Content of the specification file
        spec_name: Name of the specification file

    Returns:
        Formatted prompt for Claude
    """
    return f"""# Research Request

You are a senior software architect analyzing a specification for planning.

## Specification: {spec_name}

{spec_content}

---

## Research Requirements

Analyze this specification and produce a comprehensive research document
that will inform the implementation plan.

Your research should cover:

### 1. Architecture Analysis
- Identify existing code patterns to follow
- Note extension points and integration boundaries
- Flag potential conflicts with existing systems

### 2. Dependency Mapping
- External dependencies required
- Internal module dependencies
- Version constraints or compatibility concerns

### 3. Risk Assessment
- Technical risks and mitigation strategies
- Areas requiring prototyping or spikes
- Performance or security considerations

### 4. Open Questions
- Ambiguities in the specification
- Decisions that need human input
- Alternative approaches worth considering

## Output Format

Write a markdown document with clear sections. Reference specific files
and line numbers where applicable.
"""


def research(
    input_file: Path = typer.Argument(..., help="Specification markdown file"),
    output: Path = typer.Option(..., "--output", "-o", help="Output path for research"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress streaming output"),
) -> None:
    """Research a specification before creating a plan."""
    ctx = get_output_context()

    if not input_file.exists():
        ctx.error(f"Input file not found: {input_file}")
        raise typer.Exit(1)

    # Get weld directory for history logging (optional - research can run without init)
    try:
        repo_root = get_repo_root()
        weld_dir = get_weld_dir(repo_root)
    except GitError:
        repo_root = None
        weld_dir = None

    spec_content = input_file.read_text()
    prompt = generate_research_prompt(spec_content, input_file.name)

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would research specification:")
        ctx.console.print(f"  Input: {input_file}")
        ctx.console.print(f"  Output: {output}")
        ctx.console.print("\n[cyan]Prompt:[/cyan]")
        ctx.console.print(prompt)
        return

    ctx.console.print(f"[cyan]Researching {input_file.name}...[/cyan]\n")

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
        log_command(weld_dir, "research", str(input_file), str(output))

    ctx.success(f"Research written to {output}")
