# Research: weld implement Command

## Executive Summary

The `weld implement <plan.md>` command will be a new interactive CLI command that:
1. Parses a plan file containing phases and steps in weld's established format
2. Validates plan structure upfront before entering interactive loop
3. Displays an arrow-key navigable menu for selecting phases/steps
4. Executes Claude to implement the selected phase/step (sequentially per-step when phase selected)
5. Marks completed items with `**COMPLETE**` suffix in the plan file immediately after each step
6. Prints a reminder to run `/compact` after each completion (user-triggered in outer Claude Code session)
7. Loops until all items are marked complete or user quits

**Key architectural insight**: Weld's existing command pattern is remarkably consistent - commands are thin wrappers in `commands/` that delegate to `core/` for business logic and `services/` for external I/O. The plan file format is well-defined with `## Phase N: Title` and `### Step N: Title` headers. Interactive CLI selection is **not currently used** in the codebase - this will require adding a new dependency like `simple-term-menu`.

**Critical constraint**: This command requires an interactive terminal. It is incompatible with `--json` mode and CI/automation environments without the `--step` non-interactive flag.

## Authoritative Files

### Core Implementation Patterns
| File | Purpose | Key Exports |
|------|---------|-------------|
| `src/weld/cli.py:1-134` | CLI entry point, global options, command registration | `app`, `main` callback |
| `src/weld/commands/plan.py:1-216` | Plan command - shows prompt structure | `plan`, `generate_plan_prompt` |
| `src/weld/commands/doc_review.py:1-397` | Complex command with multiple modes | `doc_review`, `_run_code_review`, `_run_doc_review` |
| `src/weld/output.py:1-95` | Output context for dry-run, JSON mode | `OutputContext`, `get_output_context` |

### Plan File Format
| File | Purpose | Key Patterns |
|------|---------|--------------|
| `src/weld/commands/plan.py:44-165` | Plan prompt template | Phase/Step header format |
| `.claude/docs/PLAN.md:1-2527` | Example plan file | Shows `**COMPLETE**` suffix pattern |

### Services Layer
| File | Purpose | Key Exports |
|------|---------|-------------|
| `src/weld/services/claude.py:1-232` | Claude CLI integration | `run_claude`, `ClaudeError` |
| `src/weld/services/filesystem.py:1-85` | File I/O utilities | `write_file`, `read_file` |
| `src/weld/services/git.py` | Git operations | `get_repo_root`, `GitError` |

### Test Patterns
| File | What it Tests | Useful Patterns |
|------|---------------|-----------------|
| `tests/conftest.py:1-93` | Test fixtures | `temp_git_repo`, `initialized_weld`, `runner` |
| `tests/test_cli.py:1-896` | CLI integration tests | Mock patterns, exit code assertions |
| `tests/test_plan.py:1-137` | Plan prompt tests | Prompt content assertions |

## System Flows

### Primary Flow: Command Registration

**Entry Point:** `src/weld/cli.py:123-129`

```python
# Top-level commands
app.command()(init)
app.command()(commit)
app.command()(interview)
app.command()(doctor)
app.command()(plan)
app.command()(research)
app.command("review")(doc_review)
```

- Commands are plain functions decorated with `@app.command()`
- Import the function from `commands/` package
- Register in `cli.py` using the decorator pattern

### Primary Flow: Command Structure

**Entry Point:** `src/weld/commands/plan.py:168-216`

**Step-by-step execution:**

1. **Parse arguments** - `plan.py:168-172`
   ```python
   def plan(
       input_file: Path = typer.Argument(..., help="Specification markdown file"),
       output: Path = typer.Option(..., "--output", "-o", help="Output path for the plan"),
       quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress streaming output"),
   ) -> None:
   ```
   - Input: Typer-parsed arguments
   - Output: Function parameters populated

2. **Get output context** - `plan.py:174`
   ```python
   ctx = get_output_context()
   ```
   - Retrieves global context set by `cli.py` main callback
   - Contains: `console`, `json_mode`, `dry_run`

3. **Validate inputs** - `plan.py:176-178`
   ```python
   if not input_file.exists():
       ctx.error(f"Input file not found: {input_file}")
       raise typer.Exit(1)
   ```
   - Check file existence
   - Use `ctx.error()` for error output
   - Exit with appropriate code

4. **Handle dry-run** - `plan.py:191-197`
   ```python
   if ctx.dry_run:
       ctx.console.print("[cyan][DRY RUN][/cyan] Would generate plan:")
       ctx.console.print(f"  Input: {input_file}")
       ctx.console.print(f"  Output: {output}")
       ctx.console.print("\n[cyan]Prompt:[/cyan]")
       ctx.console.print(prompt)
       return
   ```
   - Early return showing what would happen
   - No side effects in dry-run mode

5. **Call service layer** - `plan.py:201-205`
   ```python
   try:
       result = run_claude(prompt=prompt, stream=not quiet)
   except ClaudeError as e:
       ctx.error(f"Claude failed: {e}")
       raise typer.Exit(1) from None
   ```
   - Delegate to services for external calls
   - Handle service exceptions gracefully

6. **Write output and log** - `plan.py:207-215`
   ```python
   output.parent.mkdir(parents=True, exist_ok=True)
   output.write_text(result)
   if weld_dir and weld_dir.exists():
       log_command(weld_dir, "plan", str(input_file), str(output))
   ctx.success(f"Plan written to {output}")
   ```
   - Create parent directories
   - Write result
   - Log to history (optional)
   - Report success

### Plan File Format

**Source:** `src/weld/commands/plan.py:44-165`

**Phase header format:**
```markdown
## Phase <number>: <Title>
```

**Phase with completion marker:**
```markdown
## Phase 1: Project Scaffolding **COMPLETE**
```

**Step header format (within phase):**
```markdown
### Step <number>: <Title>
```

**Step sections:**
```markdown
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
```

**Verified in:** `.claude/docs/PLAN.md:9-94`
```markdown
## Phase 1: Project Scaffolding **COMPLETE**

### Step 1.1: Create pyproject.toml
...
### Step 1.2: Create .python-version
...
## Phase 2: Data Models (Pydantic) **COMPLETE**
```

### Parsing Plan Structure

**Pattern for phases:** `^## Phase (\d+):\s*(.+?)(?:\s*\*\*COMPLETE\*\*)?$`

**Pattern for steps:** `^### Step (\d+(?:\.\d+)?):\s*(.+?)(?:\s*\*\*COMPLETE\*\*)?$`

**Key observations from `.claude/docs/PLAN.md`:**
- Step numbering can be `N` or `N.N` format (e.g., `Step 1` or `Step 1.1`)
- `**COMPLETE**` suffix appears at end of header line
- Phase validation section uses `### Phase Validation` header
- Step content continues until next `###` or `##` header

### Content Extraction Algorithm

**Problem**: Given a step or phase header, extract all content until the next header of same or higher level.

**Algorithm**:
```python
from dataclasses import dataclass

@dataclass
class PlanItem:
    """Represents a phase or step in the plan."""
    level: int  # 2 for phase, 3 for step
    number: str  # "1" or "1.1"
    title: str
    is_complete: bool
    content: str  # Everything between this header and next same/higher level header
    line_number: int  # For write-back operations

def extract_content(lines: list[str], start_idx: int, header_level: int) -> tuple[str, int]:
    """Extract content from header until next header of same or higher level.

    Args:
        lines: All lines of the plan file
        start_idx: Index of the header line (0-based)
        header_level: Number of '#' characters (2 for ##, 3 for ###)

    Returns:
        Tuple of (content string, end line index)
    """
    content_lines = []
    end_idx = start_idx + 1

    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        # Check if this line is a header of same or higher level
        if line.startswith('#'):
            # Count leading '#' characters
            level = len(line) - len(line.lstrip('#'))
            if level <= header_level:
                end_idx = i
                break
        content_lines.append(line)
        end_idx = i + 1

    return '\n'.join(content_lines).strip(), end_idx

def parse_plan(plan_text: str) -> list[PlanItem]:
    """Parse plan file into structured items."""
    lines = plan_text.split('\n')
    items: list[PlanItem] = []
    current_phase: PlanItem | None = None

    for i, line in enumerate(lines):
        # Check for phase header
        phase_match = PHASE_PATTERN.match(line)
        if phase_match:
            content, _ = extract_content(lines, i, 2)
            current_phase = PlanItem(
                level=2,
                number=phase_match.group(1),
                title=phase_match.group(2).strip(),
                is_complete=line.rstrip().endswith("**COMPLETE**"),
                content=content,
                line_number=i + 1,  # 1-based for display
            )
            items.append(current_phase)
            continue

        # Check for step header
        step_match = STEP_PATTERN.match(line)
        if step_match:
            content, _ = extract_content(lines, i, 3)
            step = PlanItem(
                level=3,
                number=step_match.group(1),
                title=step_match.group(2).strip(),
                is_complete=line.rstrip().endswith("**COMPLETE**"),
                content=content,
                line_number=i + 1,
            )
            items.append(step)

    return items
```

**Edge case handling**:
- Empty content between headers: Return empty string
- Last item in file: Content extends to EOF
- Nested code blocks with `#`: Code blocks are inside content, not parsed as headers (line must start with `#`)

### Plan Validation

**Upfront validation before entering interactive loop:**

```python
@dataclass
class ValidationResult:
    """Result of plan validation."""
    valid: bool
    phases: list[PlanItem]
    steps: list[PlanItem]
    errors: list[str]
    warnings: list[str]

def validate_plan(plan_text: str) -> ValidationResult:
    """Validate plan structure and return parsed items."""
    errors: list[str] = []
    warnings: list[str] = []

    items = parse_plan(plan_text)
    phases = [i for i in items if i.level == 2]
    steps = [i for i in items if i.level == 3]

    # Error: No phases found
    if not phases:
        errors.append("No phases found. Plan must have at least one '## Phase N: Title' header.")

    # Error: Steps without parent phase
    if steps and not phases:
        errors.append("Steps found without parent phase.")

    # Warning: All items already complete
    incomplete = [i for i in items if not i.is_complete]
    if not incomplete:
        warnings.append("All phases and steps are already marked complete.")

    # Warning: Phase numbers not sequential
    phase_nums = [int(p.number) for p in phases]
    expected = list(range(1, len(phases) + 1))
    if phase_nums != expected:
        warnings.append(f"Phase numbers not sequential: found {phase_nums}, expected {expected}")

    return ValidationResult(
        valid=len(errors) == 0,
        phases=phases,
        steps=steps,
        errors=errors,
        warnings=warnings,
    )
```

### Phase Selection Semantics

**Requirement 4**: If a phase is selected, complete all substeps; if substep selected, only that substep.

**Decision**: When a phase is selected, execute steps **sequentially** (not as one batch).

**Rationale**:
- Each step has its own validation commands
- Marking completion after each step provides interruption checkpoints
- Claude can focus on one atomic change at a time
- Matches the "incremental, verifiable" design philosophy from plan.py

**Implementation**:
```python
def execute_step(step: PlanItem, plan_path: Path, quiet: bool = False) -> bool:
    """Execute a single step using Claude.

    Args:
        step: The step to implement
        plan_path: Path to plan file for write-back
        quiet: Suppress streaming output

    Returns:
        True if step completed successfully
    """
    ctx = get_output_context()

    # Generate implementation prompt
    prompt = generate_impl_prompt(
        phase_title="",  # Not needed for step-level
        step_title=f"Step {step.number}: {step.title}",
        content=step.content,
    )

    # Dry-run check
    if ctx.dry_run:
        ctx.console.print(f"[cyan][DRY RUN][/cyan] Would implement Step {step.number}")
        ctx.console.print(f"[dim]Prompt length: {len(prompt)} chars[/dim]")
        return True

    # Execute Claude
    try:
        result = run_claude(prompt=prompt, stream=not quiet)
    except ClaudeError as e:
        ctx.error(f"Claude failed: {e}")
        return False

    # Mark complete immediately after success
    mark_item_complete(plan_path, step)
    ctx.success(f"Step {step.number} complete")

    return True


def execute_phase(phase: PlanItem, steps: list[PlanItem], plan_path: Path, quiet: bool = False) -> bool:
    """Execute all incomplete steps in a phase sequentially.

    Args:
        phase: The selected phase
        steps: All steps belonging to this phase
        plan_path: Path to plan file for write-back
        quiet: Suppress streaming output

    Returns:
        True if all steps completed successfully
    """
    ctx = get_output_context()
    phase_steps = [s for s in steps if s.number.startswith(f"{phase.number}.")]
    incomplete_steps = [s for s in phase_steps if not s.is_complete]

    if not incomplete_steps:
        ctx.console.print(f"[yellow]All steps in Phase {phase.number} already complete[/yellow]")
        return True

    for step in incomplete_steps:
        ctx.console.print(f"\n[cyan]Implementing Step {step.number}: {step.title}[/cyan]")

        success = execute_step(step, plan_path, quiet=quiet)
        if not success:
            ctx.error(f"Step {step.number} failed. Stopping phase execution.")
            return False

        # Step was marked complete by execute_step()
        ctx.console.print("[dim]Tip: Run /compact in Claude Code to save context[/dim]")

    # Mark phase complete after all steps done
    mark_item_complete(plan_path, phase)
    return True
```

### Menu Display Format Specification

**Visual format for interactive menu:**

```
┌─ weld implement: plan.md ─────────────────────────────┐
│                                                        │
│  Select a phase or step to implement:                  │
│                                                        │
│  ✓ Phase 1: Project Scaffolding [3/3 complete]         │
│      ✓ Step 1.1: Create pyproject.toml                 │
│      ✓ Step 1.2: Create .python-version                │
│      ✓ Step 1.3: Create directory structure            │
│  ○ Phase 2: Data Models [1/4 complete]                 │
│      ✓ Step 2.1: Create models/meta.py                 │
│    ▸ Step 2.2: Create models/step.py        ◀ cursor   │
│      ○ Step 2.3: Create models/issues.py               │
│      ○ Step 2.4: Create models/status.py               │
│  ○ Phase 3: Core Utilities [0/5 complete]              │
│                                                        │
│  [↑↓] Navigate  [Enter] Select  [q] Quit               │
└────────────────────────────────────────────────────────┘
```

**Menu item format strings:**
```python
def format_menu_item(item: PlanItem, steps_for_phase: list[PlanItem] | None = None) -> str:
    """Format a plan item for menu display."""
    check = "✓" if item.is_complete else "○"

    if item.level == 2:  # Phase
        if steps_for_phase:
            complete = sum(1 for s in steps_for_phase if s.is_complete)
            total = len(steps_for_phase)
            return f"{check} Phase {item.number}: {item.title} [{complete}/{total} complete]"
        return f"{check} Phase {item.number}: {item.title}"
    else:  # Step
        indent = "    "  # 4 spaces for visual nesting
        return f"{indent}{check} Step {item.number}: {item.title}"

def build_menu_items(phases: list[PlanItem], steps: list[PlanItem]) -> list[tuple[str, PlanItem]]:
    """Build flat menu item list with display strings and item references."""
    menu_items: list[tuple[str, PlanItem]] = []

    for phase in phases:
        phase_steps = [s for s in steps if s.number.startswith(f"{phase.number}.")]
        menu_items.append((format_menu_item(phase, phase_steps), phase))

        for step in phase_steps:
            menu_items.append((format_menu_item(step), step))

    return menu_items
```

**simple-term-menu configuration:**
```python
from simple_term_menu import TerminalMenu

def show_selection_menu(items: list[tuple[str, PlanItem]]) -> PlanItem | None:
    """Display interactive menu and return selected item."""
    display_strings = [item[0] for item in items]

    menu = TerminalMenu(
        display_strings,
        title="Select phase or step to implement:",
        cursor_index=0,
        clear_screen=False,
        cycle_cursor=True,
        show_search_hint=True,
        search_key=None,  # Disable search, use arrows only
    )

    selected_idx = menu.show()
    if selected_idx is None:  # User pressed 'q' or Escape
        return None

    return items[selected_idx][1]
```

### Plan File Write-Back Strategy

**Approach**: Regex substitution on raw text (simplest and safest for markdown).

**Rationale**:
- Preserves all formatting, whitespace, and content
- Only modifies the specific header line
- No risk of re-serialization artifacts

```python
import re
from pathlib import Path

def mark_item_complete(plan_path: Path, item: PlanItem) -> None:
    """Mark a phase or step as complete in the plan file.

    Modifies the plan file in-place by appending **COMPLETE** to the header line.
    """
    content = plan_path.read_text()
    lines = content.split('\n')

    # Find the header line (line_number is 1-based)
    line_idx = item.line_number - 1
    original_line = lines[line_idx]

    # Safety check: verify this is the expected header
    if item.level == 2:
        expected_pattern = f"## Phase {item.number}:"
    else:
        expected_pattern = f"### Step {item.number}:"

    if not original_line.startswith(expected_pattern):
        raise ValueError(
            f"Line {item.line_number} does not match expected header. "
            f"Expected '{expected_pattern}', found '{original_line[:50]}...'"
        )

    # Skip if already complete
    if original_line.rstrip().endswith("**COMPLETE**"):
        return

    # Append completion marker
    lines[line_idx] = original_line.rstrip() + " **COMPLETE**"

    # Write back atomically
    new_content = '\n'.join(lines)
    plan_path.write_text(new_content)
```

**Atomic write consideration**: For extra safety, write to temp file then rename:
```python
import tempfile
import os

def atomic_write(path: Path, content: str) -> None:
    """Write content to file atomically."""
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        os.write(fd, content.encode())
        os.close(fd)
        os.rename(tmp_path, path)
    except:
        os.unlink(tmp_path)
        raise
```

### Interruption Handling

**Scenario**: User presses Ctrl+C during implementation loop.

**Design principle**: Completed work is preserved via immediate write-back after each step.

```python
import signal
import sys

class GracefulExit(Exception):
    """Raised when user requests graceful shutdown."""
    pass

def handle_interrupt(signum: int, frame) -> None:
    """Handle Ctrl+C gracefully."""
    raise GracefulExit()

def implement_loop(plan_path: Path) -> int:
    """Main implementation loop with interruption handling.

    Returns:
        Exit code (0 for success/quit, 1 for error)
    """
    ctx = get_output_context()

    # Set up signal handler
    original_handler = signal.signal(signal.SIGINT, handle_interrupt)

    try:
        while True:
            # Re-parse plan each iteration to see updated completion status
            plan_text = plan_path.read_text()
            validation = validate_plan(plan_text)

            if not validation.valid:
                for error in validation.errors:
                    ctx.error(error)
                return 1

            # Check if all done
            incomplete = [i for i in validation.phases + validation.steps if not i.is_complete]
            if not incomplete:
                ctx.success("All phases and steps complete!")
                return 0

            # Show menu and get selection
            menu_items = build_menu_items(validation.phases, validation.steps)
            selected = show_selection_menu(menu_items)

            if selected is None:  # User quit
                ctx.console.print("[yellow]Exiting. Progress has been saved.[/yellow]")
                return 0

            # Execute selected item
            if selected.level == 2:  # Phase
                execute_phase(selected, validation.steps, plan_path)
            else:  # Step
                execute_step(selected, plan_path)

            ctx.console.print("[dim]Tip: Run /compact in Claude Code to save context[/dim]")

    except GracefulExit:
        ctx.console.print("\n[yellow]Interrupted. Progress has been saved.[/yellow]")
        return 0

    finally:
        # Restore original signal handler
        signal.signal(signal.SIGINT, original_handler)
```

**Key behaviors**:
- Ctrl+C during menu selection: Exit cleanly with progress saved
- Ctrl+C during Claude execution: `run_claude()` will be interrupted, step NOT marked complete
- All completed steps remain marked in plan file

### JSON Mode Incompatibility

**Constraint**: Interactive menus require a TTY and are incompatible with `--json` output mode.

```python
def implement(
    plan_file: Path = typer.Argument(..., help="Plan markdown file to implement"),
    step: str | None = typer.Option(None, "--step", "-s", help="Step number to implement (non-interactive)"),
    phase: int | None = typer.Option(None, "--phase", "-p", help="Phase number to implement (non-interactive)"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress streaming output"),
) -> None:
    """Interactively implement phases and steps from a plan file."""
    ctx = get_output_context()

    # JSON mode check
    if ctx.json_mode and step is None and phase is None:
        ctx.error(
            "Interactive mode not supported with --json. Use --step or --phase for non-interactive mode.",
            next_action="weld implement plan.md --step 1.1"
        )
        raise typer.Exit(1)

    # TTY check for interactive mode
    if step is None and phase is None and not sys.stdin.isatty():
        ctx.error(
            "Interactive mode requires a terminal. Use --step or --phase for non-interactive mode.",
            next_action="weld implement plan.md --step 1.1"
        )
        raise typer.Exit(1)

    # ... rest of implementation
```

### Non-Interactive Mode

**Use case**: CI/automation, scripting, or when user knows exactly which step to run.

```python
def implement_non_interactive(
    plan_path: Path,
    step_number: str | None,
    phase_number: int | None,
    quiet: bool,
) -> int:
    """Non-interactive implementation of specific step or phase.

    Returns exit code.
    """
    ctx = get_output_context()

    plan_text = plan_path.read_text()
    validation = validate_plan(plan_text)

    if not validation.valid:
        for error in validation.errors:
            ctx.error(error)
        return 1

    if step_number:
        # Find and execute specific step
        step = next((s for s in validation.steps if s.number == step_number), None)
        if not step:
            ctx.error(f"Step {step_number} not found in plan")
            return 1
        if step.is_complete:
            ctx.console.print(f"[yellow]Step {step_number} already complete[/yellow]")
            return 0

        success = execute_step(step, plan_path, quiet=quiet)
        return 0 if success else 21

    if phase_number:
        # Find and execute specific phase
        phase = next((p for p in validation.phases if p.number == str(phase_number)), None)
        if not phase:
            ctx.error(f"Phase {phase_number} not found in plan")
            return 1

        success = execute_phase(phase, validation.steps, plan_path, quiet=quiet)
        return 0 if success else 21

    # Should not reach here
    return 1
```

**CLI usage examples:**
```bash
# Interactive mode (default)
weld implement plan.md

# Non-interactive: specific step
weld implement plan.md --step 2.1

# Non-interactive: entire phase
weld implement plan.md --phase 2

# In CI/scripts with JSON output
weld --json implement plan.md --step 2.1
```

## Implementation Patterns

### Pattern: Command Function Signature
**Used in:** All command files

```python
def command_name(
    positional_arg: Path = typer.Argument(..., help="Description"),
    optional_arg: Path = typer.Option(..., "--flag", "-f", help="Description"),
    flag: bool = typer.Option(False, "--flag", help="Description"),
) -> None:
    """Command docstring shown in --help."""
```

**When to apply:** Every new command
**Anti-pattern to avoid:** Using `click` directly instead of `typer`

### Pattern: Output Context Usage
**Used in:** `plan.py`, `research.py`, `doc_review.py`, `commit.py`

```python
ctx = get_output_context()

# Error with suggested action
ctx.error("Error message", next_action="weld command --help")

# Success message
ctx.success("Operation completed")

# Conditional dry-run
if ctx.dry_run:
    ctx.console.print("[cyan][DRY RUN][/cyan] Would do X")
    return
```

**When to apply:** All user-facing output
**Anti-pattern to avoid:** Using `print()` directly

### Pattern: Service Error Handling
**Used in:** `plan.py:201-205`, `doc_review.py:252-263`

```python
try:
    result = run_claude(prompt=prompt, stream=not quiet)
except ClaudeError as e:
    ctx.error(f"Claude failed: {e}")
    raise typer.Exit(1) from None
```

**When to apply:** All service calls
**Anti-pattern to avoid:** Letting exceptions propagate unhandled

### Pattern: File Modification
**Used in:** `services/filesystem.py:22-30`

```python
def write_file(path: Path, content: str) -> None:
    """Write content to a file, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
```

**When to apply:** All file writes
**Anti-pattern to avoid:** Not creating parent directories

## Dependencies & Constraints

### Internal Dependencies
- `commands/implement.py` will depend on:
  - `output.py` for `get_output_context()`
  - `services/claude.py` for `run_claude()`
  - `services/filesystem.py` for `read_file()`, `write_file()`
  - `core/weld_dir.py` for `get_weld_dir()`

### External Dependencies (New)
| Package | Purpose | Notes |
|---------|---------|-------|
| `simple-term-menu` | Arrow-key menu selection | Must add to `pyproject.toml` |

**pyproject.toml change required:**
```toml
dependencies = [
  "typer>=0.12",
  "pydantic>=2.6",
  "rich>=13.7",
  "tomli-w>=1.0",
  "simple-term-menu>=1.6",  # NEW: Interactive menu selection
]
```

**Alternative options considered:**
- `questionary` - More features but heavier dependency tree
- `rich` built-in - No arrow-key selection support (only prompts)
- `textual` - Full TUI framework, overkill for simple menu
- `pick` - Simpler but less maintained than simple-term-menu

**simple-term-menu features used:**
- Arrow key navigation (↑↓)
- Enter to select
- 'q' or Escape to quit
- Cursor cycling (wrap around at top/bottom)
- No search (disabled to keep UX simple)

### Invariants
- Plan file must exist and be readable
- Phase/step headers must follow the established format
- `**COMPLETE**` marker must be at end of header line (not on new line)
- Step numbers restart at 1 within each phase

### Boundaries
- This command is responsible for: Interactive selection, Claude invocation, plan file updates
- This command delegates to: `run_claude()` for AI implementation
- This command does NOT handle: Git commits, transcript generation

## Critical Details

### Non-Obvious Behaviors

1. **Step numbering varies**: Steps can be `Step 1` or `Step 1.1` format - the regex must handle both
2. **Complete marker format**: `**COMPLETE**` uses markdown bold syntax and must be preserved exactly
3. **Dry-run inheritance**: Global `--dry-run` flag is available via `ctx.dry_run`
4. **Stream default**: `run_claude()` defaults to `stream=False`, use `stream=not quiet` pattern

### Assumptions Validated
- ✅ Commands are registered in `cli.py` via `app.command()` - verified in `cli.py:123-129`
- ✅ `**COMPLETE**` suffix is used for completion markers - verified in `.claude/docs/PLAN.md:9,94,254`
- ✅ Output context provides `dry_run` flag - verified in `output.py:14-19`
- ✅ `run_claude()` accepts `stream` parameter - verified in `services/claude.py:180`

### Assumptions Invalidated
- ❌ Step numbers are always integers - actual: can be `N.N` format like `1.1`, `1.2`
- ❌ Interactive menus exist in codebase - actual: no interactive selection currently exists

### Edge Cases
- Plan file with no phases (error case)
- All phases already marked complete (success with message)
- Phase selected but some steps already complete (skip completed steps)
- Step with `**COMPLETE**` in title text (must match at EOL only)
- Nested markdown headers (must only match `##` and `###` at start)

## Extension Points

### Where to Add New Functionality
| Location | Type of Change | Pattern to Follow |
|----------|---------------|-------------------|
| `src/weld/commands/implement.py` | New command file | See `plan.py` structure |
| `src/weld/core/plan_parser.py` | Plan parsing logic | See `history.py` for JSONL parsing patterns |
| `src/weld/cli.py:128` | Command registration | `app.command()(implement)` |
| `pyproject.toml:11-16` | New dependency | Add to `dependencies` list |

### Where NOT to Modify
- `src/weld/services/claude.py` - Claude integration is stable
- `src/weld/output.py` - Output context is sufficient
- Existing command files - no need to modify other commands

## /compact Implementation

**Requirement 6:** Run `/compact` after each step completion

**Key insight:** `/compact` is a Claude Code session command that operates on the *outer* Claude Code session context—not the subprocess Claude instance that weld spawns via `run_claude()`.

**Execution context:**
```
┌─────────────────────────────────────────────────────────┐
│ Claude Code Session (outer)                             │
│   └─ User runs: weld implement plan.md                  │
│       └─ weld spawns: claude -p "implement step..."     │
│           └─ Inner Claude implements the step           │
│       └─ weld prints: "Run /compact to save context"    │
│   └─ User types: /compact                               │
│       └─ Compacts the OUTER session context             │
└─────────────────────────────────────────────────────────┘
```

**Decision:** Print a reminder after each step completion. The user triggers `/compact` manually in their Claude Code session.

**Implementation:**
```python
def print_compact_reminder(ctx: OutputContext) -> None:
    """Print reminder to run /compact after step completion."""
    ctx.console.print("[dim]Tip: Run /compact in Claude Code to save context[/dim]")
```

**Rationale:**
- `/compact` cannot be triggered programmatically from weld—it's a Claude Code interactive command
- The outer session accumulates context as weld runs repeatedly; `/compact` helps manage this
- Making it user-triggered keeps weld simple and avoids assumptions about the execution environment
- Users not running in Claude Code can ignore the reminder

**Alternative considered and rejected:**
- Automatic execution via `subprocess.run(["claude", "-p", "/compact"])` - This would start a *new* Claude process, not compact the existing session. Claude Code's `/compact` operates on its own persistent session state.

## Open Questions

### Resolved
- [x] Should `/compact` be automatic or user-triggered? → **User-triggered** (print reminder after each step)
- [x] Should the menu show nested steps under phases, or flat list? → **Flat list with visual indentation** (4 spaces for steps)
- [x] Preference for `simple-term-menu` vs other interactive library? → **simple-term-menu** (lightweight, sufficient features)
- [x] Should we support partial step completion (some substeps done)? → **Yes** (skip completed steps when phase selected)
- [x] Phase selection: batch or sequential execution? → **Sequential** (one step at a time with checkpoints)

### Requires Human Input
- [ ] Should completed items be visually distinct in menu (e.g., grayed out)?
- [ ] Should selecting a completed item re-run it or show a warning?
- [ ] Maximum plan file size to support (for validation)?

### Requires Runtime Validation
- [ ] Verify `simple-term-menu` works in all target terminal environments
- [ ] Test arrow-key navigation in various terminal emulators (iTerm2, Terminal.app, VS Code terminal, etc.)
- [ ] Test behavior when plan file is modified externally during execution

### Out of Scope (noted for later)
- Undo/rollback of completed steps
- Progress persistence across weld sessions (currently relies on plan file markers)
- Parallel step execution
- Plan file locking during execution

## Appendix: Key Code Snippets

### Command Registration Pattern
```python
# src/weld/cli.py
from .commands.implement import implement

# ... in command registration section ...
app.command()(implement)
```

### Plan Parsing Regex
```python
import re

# Pattern captures: (phase_number, title_without_complete_marker)
# Note: Title group uses non-greedy match to exclude trailing **COMPLETE**
PHASE_PATTERN = re.compile(
    r"^## Phase (\d+):\s*(.+?)(?:\s*\*\*COMPLETE\*\*)?$",
    re.MULTILINE
)

# Pattern captures: (step_number, title_without_complete_marker)
# Step number can be "N" or "N.N" format (e.g., "1", "1.1", "2.3")
# Constrained to single decimal (no "1.1.1")
STEP_PATTERN = re.compile(
    r"^### Step (\d+(?:\.\d+)?):\s*(.+?)(?:\s*\*\*COMPLETE\*\*)?$",
    re.MULTILINE
)

def is_complete(header_line: str) -> bool:
    """Check if a header line has the completion marker."""
    return header_line.rstrip().endswith("**COMPLETE**")

def mark_complete(header_line: str) -> str:
    """Add completion marker to header line if not already present."""
    if is_complete(header_line):
        return header_line
    return header_line.rstrip() + " **COMPLETE**"

# Example usage and edge case handling:
# "## Phase 1: Setup **COMPLETE**" -> number="1", title="Setup", is_complete=True
# "### Step 1.2: Add tests"        -> number="1.2", title="Add tests", is_complete=False
# "## Phase 2: **COMPLETE** Work"  -> number="2", title="**COMPLETE** Work", is_complete=False
#   ^ Edge case: COMPLETE in middle of title is NOT treated as marker
```

### Interactive Menu with simple-term-menu
```python
from simple_term_menu import TerminalMenu

def select_item(items: list[str]) -> int | None:
    """Display interactive menu and return selected index."""
    menu = TerminalMenu(
        items,
        title="Select phase or step to implement:",
        cursor_index=0,
        clear_screen=False,
    )
    return menu.show()
```

### Implementation Prompt Template
```python
def generate_impl_prompt(phase_title: str, step_title: str | None, content: str) -> str:
    if step_title:
        header = f"## Implement Step: {step_title}"
    else:
        header = f"## Implement Phase: {phase_title}"

    return f"""{header}

{content}

---

## Instructions

Implement the above specification. After implementation:
1. Verify changes work by running any validation commands shown
2. Keep changes focused on this specific step/phase only
3. Do not implement future steps

When complete, confirm the implementation is done.
"""
```

## Appendix: Useful Grep Patterns

```bash
# Find all command registrations
grep -n "app.command" src/weld/cli.py

# Find all **COMPLETE** markers in plan files
grep -rn "\*\*COMPLETE\*\*" .claude/docs/

# Find phase headers in plan files
grep -En "^## Phase" .claude/docs/*.md

# Find step headers
grep -En "^### Step" .claude/docs/*.md

# Find all typer.Option usages
grep -rn "typer.Option" src/weld/commands/

# Find service imports
grep -rn "from.*services import" src/weld/commands/
```

## Appendix: Exit Codes

Based on `tests/test_cli.py` and existing commands:

| Code | Meaning | Use Case |
|------|---------|----------|
| 0 | Success | Normal completion |
| 1 | General error / file not found | Input validation failures |
| 2 | Dependency missing | Required tool not installed |
| 3 | Not a git repository | Git operations outside repo |
| 20 | No changes to commit | Commit-specific |
| 21 | Claude/AI operation failed | Service layer failures |
| 22 | Git operation failed | Commit/staging failures |
| 23 | Parse failure | Response parsing errors |

**Exit codes for `implement` command:**

| Code | Condition | Example |
|------|-----------|---------|
| 0 | Success: all steps complete | Normal completion of all phases |
| 0 | Success: user quit menu | User pressed 'q' or Escape |
| 0 | Success: interrupted gracefully | User pressed Ctrl+C, progress saved |
| 1 | Plan file not found | `weld implement nonexistent.md` |
| 1 | Plan file invalid format | No phases found in file |
| 1 | Interactive mode without TTY | Piped input without `--step` flag |
| 1 | JSON mode without step/phase | `weld --json implement plan.md` |
| 21 | Claude implementation failed | API error, timeout, or Claude refusal |
| 23 | Plan parse error | Malformed phase/step headers |
