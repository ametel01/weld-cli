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

**WRONG - Do NOT output like this:**
```
## Phase 1: CSS Utility Extensions
Extend globals.css with new utilities:
- .text-subtitle - Enhanced subtitle contrast
- .link-underline-hover - Animated underline

## Phase 2: Component Styling
Apply utilities to components:
- StatCard.tsx - Add border glow
```

**CORRECT - Output like this instead:**
```
## Phase 1: CSS Utility Extensions

Add utility classes for enhanced visual feedback.

### Phase Validation
```bash
npm run build
```

### Step 1: Add subtitle contrast utility

#### Goal
Create .text-subtitle class for enhanced subtitle visibility.

#### Files
- `src/styles/globals.css` - Add .text-subtitle utility class

#### Validation
```bash
grep -q "text-subtitle" src/styles/globals.css && echo "OK"
```

#### Failure modes
- Class name conflicts with existing styles

---

### Step 2: Add link underline animation

#### Goal
Create .link-underline-hover class for animated underlines on hover.

#### Files
- `src/styles/globals.css` - Add .link-underline-hover utility class

#### Validation
```bash
grep -q "link-underline-hover" src/styles/globals.css && echo "OK"
```

#### Failure modes
- Animation conflicts with existing transitions

---
```

---

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

Output ONLY the structured plan now. Begin with `## Phase 1:`
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
    ] = True,
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
