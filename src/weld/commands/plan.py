"""Plan command implementation."""

from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from ..config import load_config
from ..core import get_weld_dir, log_command
from ..output import get_output_context
from ..services import ClaudeError, GitError, get_repo_root, run_claude, track_session_activity


def get_plan_dir(weld_dir: Path) -> Path:
    """Get or create plan output directory.

    Args:
        weld_dir: Path to .weld directory

    Returns:
        Path to .weld/plan/ directory
    """
    plan_dir = weld_dir / "plan"
    plan_dir.mkdir(exist_ok=True)
    return plan_dir


def generate_plan_prompt(spec_content: str, spec_name: str) -> str:
    """Generate prompt for creating an implementation plan.

    Args:
        spec_content: Content of the specification file
        spec_name: Name of the specification file

    Returns:
        Formatted prompt for Claude
    """
    return f"""# Implementation Plan Request

Read the following specification carefully, explore the codebase, and create an implementation plan.

## Specification: {spec_name}

{spec_content}

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

## Planning Principles

Planning is the highest-leverage activity. A good plan:
- Lists exact steps
- References concrete files and snippets
- Specifies validation after each change
- Makes failure modes obvious

A solid plan dramatically constrains agent behavior.

## Output Format

Create a phased implementation plan. The plan MUST follow this exact structure:

### Phase Structure

Divide the implementation into discrete, incremental phases. Each phase builds on the previous
one and represents a logical milestone. Use this exact format for phase headers:

## Phase <number>: <Title>

Brief description of what this phase accomplishes and its prerequisites.

### Phase Validation
```bash
# Command(s) to verify the entire phase is complete and working
```

### Step Structure

Within each phase, break down the work into discrete, incremental steps. Each step must be
atomic and verifiable. Step numbers restart at 1 within each phase. Use this exact format:

### Step <number>: <Title>

#### Goal
Brief description of what this step accomplishes.

#### Files
- `path/to/file.py` - What changes to make

#### Validation
```bash
# Command to verify this step works
```

#### Failure modes
- What could go wrong and how to detect it

---

## Example

Here is a brief example showing the structure (your plan should be more detailed):

## Phase 1: Data Models

Set up the core data structures needed for the feature.

### Phase Validation
```bash
pytest tests/test_models.py -v
```

### Step 1: Create user model

#### Goal
Define the User dataclass with required fields.

#### Files
- `src/models/user.py` - Create new file with User dataclass

#### Validation
```bash
python -c "from src.models.user import User; print(User.__annotations__)"
```

#### Failure modes
- Import error if module path is wrong

---

### Step 2: Add validation logic

#### Goal
Add field validation to the User model.

#### Files
- `src/models/user.py` - Add validator methods

#### Validation
```bash
pytest tests/test_models.py::test_user_validation -v
```

#### Failure modes
- Validation too strict/lenient for requirements

---

## Phase 2: Core Logic

Implement the business logic using the data models from Phase 1.

### Phase Validation
```bash
pytest tests/test_core.py -v
```

### Step 1: Implement user service

(Note: Step numbering restarts at 1 for each phase)

...

---

## Guidelines

**Phase guidelines:**
- Each phase should be a logical milestone (e.g., "Phase 1: Data Models", "Phase 2: Core Logic")
- Phases are incremental - each builds on the foundation of previous phases
- A phase should be completable and testable before moving to the next
- Include a Phase Validation section with commands to verify the entire phase works
- Number phases sequentially starting from 1

**Step guidelines:**
- Step numbers restart at 1 within each new phase
- Each step should be independently verifiable
- Steps should be atomic and focused
- Order steps by dependency (do prerequisites first)
- Reference specific files, functions, and line numbers where possible
- Include concrete validation commands for each step
"""


def plan(
    input_file: Annotated[Path, typer.Argument(help="Specification markdown file")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output path for the plan"),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress streaming output"),
    ] = False,
    track: Annotated[
        bool,
        typer.Option("--track", help="Track session activity for this command"),
    ] = False,
    skip_permissions: Annotated[
        bool,
        typer.Option(
            "--dangerously-skip-permissions",
            help="Allow Claude to explore codebase without permission prompts",
        ),
    ] = False,
) -> None:
    """Generate an implementation plan from a specification.

    If --output is not specified, writes to .weld/plan/{filename}-{timestamp}.md

    Note: Claude often needs to explore the codebase (read files, search for patterns)
    to create a proper plan. Use --dangerously-skip-permissions to allow this.
    """
    ctx = get_output_context()

    if not input_file.exists():
        ctx.error(f"Input file not found: {input_file}")
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
        plan_dir = get_plan_dir(weld_dir)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = plan_dir / f"{input_file.stem}-{timestamp}.md"

    spec_content = input_file.read_text()
    prompt = generate_plan_prompt(spec_content, input_file.name)

    # Load config (falls back to defaults if not initialized)
    config = load_config(weld_dir) if weld_dir else load_config(input_file.parent)

    if ctx.dry_run:
        ctx.console.print("[cyan][DRY RUN][/cyan] Would generate plan:")
        ctx.console.print(f"  Input: {input_file}")
        ctx.console.print(f"  Output: {output}")
        ctx.console.print("\n[cyan]Prompt:[/cyan]")
        ctx.console.print(prompt)
        return

    ctx.console.print(f"[cyan]Generating plan from {input_file.name}...[/cyan]\n")

    claude_exec = config.claude.exec if config.claude else "claude"

    def _run() -> str:
        return run_claude(
            prompt=prompt,
            exec_path=claude_exec,
            cwd=repo_root,
            stream=not quiet,
            skip_permissions=skip_permissions,
            max_output_tokens=config.claude.max_output_tokens,
        )

    try:
        if track and weld_dir and repo_root:
            with track_session_activity(weld_dir, repo_root, "plan"):
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
        log_command(weld_dir, "plan", str(input_file), str(output))

    ctx.success(f"Plan written to {output}")
