"""Research command implementation."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from ..completions import complete_markdown_file
from ..config import load_config
from ..core import (
    apply_customization,
    get_default_focus,
    get_weld_dir,
    log_command,
    validate_input_file,
    validate_output_path,
)
from ..output import get_output_context
from ..services import ClaudeError, GitError, get_repo_root, run_claude, track_session_activity


def get_research_dir(weld_dir: Path) -> Path:
    """Get or create research output directory.

    Args:
        weld_dir: Path to .weld directory

    Returns:
        Path to .weld/research/ directory
    """
    research_dir = weld_dir / "research"
    research_dir.mkdir(exist_ok=True)
    return research_dir


def generate_research_prompt(spec_content: str, spec_name: str, focus: str | None = None) -> str:
    """Generate prompt for researching a specification.

    Args:
        spec_content: Content of the specification file
        spec_name: Name of the specification file
        focus: Optional specific areas to focus on

    Returns:
        Formatted prompt for Claude
    """
    focus_section = ""
    if focus:
        focus_section = f"""
## Focus Areas

Pay particular attention to: {focus}
"""

    return f"""# Research Request

You are a senior software architect analyzing a specification for planning.

## Specification: {spec_name}

{spec_content}

---
{focus_section}
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
    input_file: Annotated[
        Path,
        typer.Argument(help="Specification markdown file", autocompletion=complete_markdown_file),
    ],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output path for research"),
    ] = None,
    focus: Annotated[
        str | None,
        typer.Option("--focus", "-f", help="Specific areas to focus on"),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress streaming output"),
    ] = False,
    track: Annotated[
        bool,
        typer.Option("--track", help="Track session activity for this command"),
    ] = False,
) -> None:
    """Research a specification before creating a plan.

    If --output is not specified, writes to .weld/research/{filename}-{timestamp}.md
    """
    ctx = get_output_context()

    # Early validation of input file
    if error := validate_input_file(input_file, must_be_markdown=True, param_name="spec file"):
        ctx.error(error[0], next_action=error[1])
        raise typer.Exit(1)

    # Early validation of output path if provided
    if output is not None and (
        error := validate_output_path(output, must_be_markdown=True, param_name="output")
    ):
        ctx.error(error[0], next_action=error[1])
        raise typer.Exit(1)

    # Get weld directory for history logging and default output
    try:
        repo_root = get_repo_root()
        weld_dir = get_weld_dir(repo_root)
    except GitError:
        repo_root = None
        weld_dir = None

    # Determine output path
    if output is None:
        if weld_dir is None:
            ctx.error("Not a git repository. Use --output to specify output path.")
            raise typer.Exit(1)
        if not weld_dir.exists():
            ctx.error("Weld not initialized. Use --output or run 'weld init' first.")
            raise typer.Exit(1)
        research_dir = get_research_dir(weld_dir)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = research_dir / f"{input_file.stem}-{timestamp}.md"

    # Load config (falls back to defaults if not initialized)
    config = load_config(weld_dir) if weld_dir else load_config(input_file.parent)

    # Resolve focus: CLI flag takes precedence over configured default
    effective_focus = get_default_focus("research", config, focus)

    spec_content = input_file.read_text()
    prompt = generate_research_prompt(spec_content, input_file.name, effective_focus)

    # Apply prefix/suffix customization from config
    prompt = apply_customization(prompt, "research", config)

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would research specification:")
        ctx.console.print(f"  Input: {input_file}")
        ctx.console.print(f"  Output: {output}")
        ctx.console.print("\n[cyan]Prompt:[/cyan]")
        ctx.console.print(prompt)
        return

    ctx.console.print(f"[cyan]Researching {input_file.name}...[/cyan]\n")

    def _run() -> str:
        return run_claude(
            prompt=prompt,
            stream=not quiet,
            skip_permissions=True,
            max_output_tokens=config.claude.max_output_tokens,
        )

    try:
        if track and weld_dir and repo_root:
            with track_session_activity(weld_dir, repo_root, "research"):
                result = _run()
        else:
            result = _run()
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
