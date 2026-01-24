# Technical Specification: Prompt Features

This document specifies two planned features for weld-cli:
1. **Prompts Personalization** - Allow users to customize prompt templates
2. **Prompt Viewer Command** - View prompt content for all commands

---

## Current State Analysis

### Prompt Architecture

All prompts follow a consistent pattern:
- **Template constants**: `*_PROMPT_TEMPLATE` strings at module level
- **Generator functions**: `generate_*_prompt()` returning formatted strings
- **Parameter support**: Most prompts support `focus` or `focus_areas` parameters

### Prompt Locations

| Command | Prompt Location | Template Constant | Generator Function |
|---------|-----------------|-------------------|-------------------|
| `discover` | `core/discover_engine.py:9-169` | `DISCOVER_PROMPT_TEMPLATE` | `generate_discover_prompt()` |
| `interview` | `core/interview_engine.py:10-48` | `INTERVIEW_SYSTEM_PROMPT` | `generate_interview_prompt()` |
| `research` | `commands/research.py:29-89` | inline | `generate_research_prompt()` |
| `plan` | `commands/plan.py:14-212` | inline | `generate_plan_prompt()` |
| `implement` | `commands/implement.py:837-866` | inline | `_execute_step()` |
| `review` (doc) | `core/doc_review_engine.py:12-130` | `DOC_REVIEW_PROMPT_TEMPLATE` | `generate_doc_review_prompt()` |
| `review` (code) | `core/doc_review_engine.py:210-325` | `CODE_REVIEW_PROMPT_TEMPLATE` | `generate_code_review_prompt()` |
| `commit` | `commands/commit.py:159-228` | inline | `_generate_commit_prompt()` |

### Configuration System

Config location: `.weld/config.toml` (TOML, Pydantic validation)

Existing customization patterns in `src/weld/config.py`:
- `TaskModelsConfig` (lines 43-60): Per-task model assignment
- `TaskType` enum (lines 14-32): Defines all task categories
- Config loading via `load_config()` (line 245)

---

## Feature 1: Prompts Personalization

### Overview

Enable users to customize prompt templates per command, allowing:
- Custom instructions to prepend/append to prompts
- Per-project prompt overrides
- Focus area defaults per command

### Configuration Schema

Add new section to `.weld/config.toml`:

```toml
[prompts]
# Global customization applied to all prompts
global_prefix = ""
global_suffix = ""

[prompts.discover]
# Prepended to discover prompts
prefix = """
Additional context for this project:
- We use Clean Architecture patterns
- All services implement interface segregation
"""
# Appended to discover prompts
suffix = ""
# Default focus areas (used when --focus not specified)
default_focus = "API layer and domain models"

[prompts.interview]
prefix = ""
suffix = ""
default_focus = ""

[prompts.research]
prefix = ""
suffix = ""
default_focus = ""

[prompts.plan]
prefix = ""
suffix = ""

[prompts.implement]
prefix = ""
suffix = ""

[prompts.review]
prefix = ""
suffix = ""
default_focus = ""

[prompts.commit]
prefix = ""
suffix = ""
```

### Implementation

#### 1. New Pydantic Models

**File:** `src/weld/config.py`

```python
class PromptCustomization(BaseModel):
    """Customization options for a single prompt type."""
    prefix: str = ""
    suffix: str = ""
    default_focus: str | None = None

class PromptsConfig(BaseModel):
    """Prompt customization configuration."""
    global_prefix: str = ""
    global_suffix: str = ""
    discover: PromptCustomization = Field(default_factory=PromptCustomization)
    interview: PromptCustomization = Field(default_factory=PromptCustomization)
    research: PromptCustomization = Field(default_factory=PromptCustomization)
    plan: PromptCustomization = Field(default_factory=PromptCustomization)
    implement: PromptCustomization = Field(default_factory=PromptCustomization)
    review: PromptCustomization = Field(default_factory=PromptCustomization)
    commit: PromptCustomization = Field(default_factory=PromptCustomization)
```

Add to `WeldConfig`:

```python
class WeldConfig(BaseModel):
    # ... existing fields ...
    prompts: PromptsConfig = Field(default_factory=PromptsConfig)
```

#### 2. Prompt Customization Utility

**File:** `src/weld/core/prompt_customizer.py` (new)

```python
"""Prompt customization utilities."""
from pathlib import Path
from weld.config import load_config, PromptCustomization, TaskType

def apply_customization(
    prompt: str,
    task_type: TaskType,
    weld_dir: Path,
) -> str:
    """Apply user customizations to a prompt.

    Args:
        prompt: The base prompt template output
        task_type: The task type (discover, plan, etc.)
        weld_dir: Path to .weld directory

    Returns:
        Customized prompt with prefix/suffix applied
    """
    config = load_config(weld_dir)
    prompts_config = config.prompts

    # Get task-specific customization
    task_custom: PromptCustomization = getattr(
        prompts_config,
        task_type.value,
        PromptCustomization()
    )

    parts = []

    # Apply global prefix
    if prompts_config.global_prefix:
        parts.append(prompts_config.global_prefix)

    # Apply task-specific prefix
    if task_custom.prefix:
        parts.append(task_custom.prefix)

    # Add base prompt
    parts.append(prompt)

    # Apply task-specific suffix
    if task_custom.suffix:
        parts.append(task_custom.suffix)

    # Apply global suffix
    if prompts_config.global_suffix:
        parts.append(prompts_config.global_suffix)

    return "\n\n".join(parts)


def get_default_focus(task_type: TaskType, weld_dir: Path) -> str | None:
    """Get default focus for a task type from config.

    Args:
        task_type: The task type
        weld_dir: Path to .weld directory

    Returns:
        Default focus string or None if not configured
    """
    config = load_config(weld_dir)
    task_custom = getattr(config.prompts, task_type.value, None)

    if task_custom and hasattr(task_custom, 'default_focus'):
        return task_custom.default_focus or None
    return None
```

#### 3. Integration Points

Update each command to apply customizations:

**Example: `src/weld/commands/discover.py`**

```python
from weld.core.prompt_customizer import apply_customization, get_default_focus
from weld.config import TaskType

def discover(...):
    # Use default focus if not provided
    if focus is None:
        focus = get_default_focus(TaskType.DISCOVER, weld_dir)

    # Generate base prompt
    prompt = generate_discover_prompt(focus_areas=focus)

    # Apply user customizations
    prompt = apply_customization(prompt, TaskType.DISCOVER, weld_dir)

    # ... rest of command
```

Similar changes for: `interview.py`, `research.py`, `plan.py`, `implement.py`, `doc_review.py`, `commit.py`

### Files to Modify

| File | Changes |
|------|---------|
| `src/weld/config.py` | Add `PromptCustomization`, `PromptsConfig` models |
| `src/weld/core/prompt_customizer.py` | New file: customization utilities |
| `src/weld/core/__init__.py` | Export new functions |
| `src/weld/commands/discover.py` | Apply customization |
| `src/weld/commands/interview.py` | Apply customization |
| `src/weld/commands/research.py` | Apply customization |
| `src/weld/commands/plan.py` | Apply customization |
| `src/weld/commands/implement.py` | Apply customization (2 locations) |
| `src/weld/commands/doc_review.py` | Apply customization |
| `src/weld/commands/commit.py` | Apply customization |

### Testing

```python
# tests/test_prompt_customizer.py

class TestPromptCustomization:
    def test_applies_global_prefix(self, temp_weld_dir):
        # Write config with global_prefix
        # Verify prefix appears in customized prompt

    def test_applies_task_prefix_and_suffix(self, temp_weld_dir):
        # Verify task-specific customization

    def test_prefix_order(self, temp_weld_dir):
        # Verify: global_prefix -> task_prefix -> prompt -> task_suffix -> global_suffix

    def test_default_focus(self, temp_weld_dir):
        # Verify default_focus is used when focus not provided

    def test_empty_customization_returns_original(self, temp_weld_dir):
        # Verify no changes when config is empty
```

---

## Feature 2: Prompt Viewer Command

### Overview

Add `weld prompt` command group to view and manage prompt content:
- `weld prompt show <command>` - Display prompt template for a command
- `weld prompt list` - List all available prompt types
- `weld prompt export` - Export all prompts to files

### CLI Interface

```bash
# List all prompt types
weld prompt list

# Show specific prompt (with customizations applied)
weld prompt show discover
weld prompt show plan
weld prompt show review --mode doc
weld prompt show review --mode code
weld prompt show implement

# Show raw prompt (without customizations)
weld prompt show discover --raw

# Export all prompts to directory
weld prompt export ./prompts/

# Show with mock content (for templates requiring input)
weld prompt show plan --spec "Build a REST API"
weld prompt show commit --diff "sample diff content"
```

### Implementation

#### 1. New Command Module

**File:** `src/weld/commands/prompt.py` (new)

```python
"""Prompt viewing and management commands."""
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from weld.config import TaskType, load_config
from weld.core.discover_engine import generate_discover_prompt
from weld.core.interview_engine import generate_interview_prompt
from weld.core.doc_review_engine import (
    generate_doc_review_prompt,
    generate_code_review_prompt,
)
from weld.core.prompt_customizer import apply_customization
from weld.commands.plan import generate_plan_prompt
from weld.commands.research import generate_research_prompt
from weld.core.weld_dir import find_weld_dir

app = typer.Typer(
    name="prompt",
    help="View and manage prompt templates.",
    no_args_is_help=True,
)


class PromptType(str, Enum):
    """Available prompt types."""
    DISCOVER = "discover"
    INTERVIEW = "interview"
    RESEARCH = "research"
    PLAN = "plan"
    IMPLEMENT = "implement"
    REVIEW_DOC = "review-doc"
    REVIEW_CODE = "review-code"
    COMMIT = "commit"


# Mapping of prompt types to their generators
PROMPT_GENERATORS = {
    PromptType.DISCOVER: lambda **kw: generate_discover_prompt(
        focus_areas=kw.get("focus")
    ),
    PromptType.INTERVIEW: lambda **kw: generate_interview_prompt(),
    PromptType.RESEARCH: lambda **kw: generate_research_prompt(
        spec_content=kw.get("spec", "<spec content>"),
        spec_name=kw.get("spec_name", "spec.md"),
        focus=kw.get("focus"),
    ),
    PromptType.PLAN: lambda **kw: generate_plan_prompt(
        specs=[(kw.get("spec_name", "spec.md"), kw.get("spec", "<spec content>"))]
    ),
    PromptType.REVIEW_DOC: lambda **kw: generate_doc_review_prompt(
        document_path=kw.get("document_path", "<document>"),
        document_content=kw.get("document_content", "<content>"),
        focus_area=kw.get("focus"),
        apply_mode=kw.get("apply", False),
    ),
    PromptType.REVIEW_CODE: lambda **kw: generate_code_review_prompt(
        diff_content=kw.get("diff", "<diff content>"),
        focus_area=kw.get("focus"),
        apply_mode=kw.get("apply", False),
    ),
}


@app.command("list")
def list_prompts() -> None:
    """List all available prompt types."""
    console = Console()

    console.print("\n[bold]Available Prompt Types[/bold]\n")

    prompts_info = [
        ("discover", "Codebase discovery and documentation", "~160 lines"),
        ("interview", "Interactive specification refinement", "~40 lines"),
        ("research", "Pre-planning research analysis", "~60 lines"),
        ("plan", "Implementation plan generation", "~210 lines"),
        ("implement", "Step execution prompts", "~30 lines"),
        ("review-doc", "Document review and verification", "~120 lines"),
        ("review-code", "Code review from diff", "~115 lines"),
        ("commit", "Commit message generation", "~70 lines"),
    ]

    for name, description, size in prompts_info:
        console.print(f"  [cyan]{name:12}[/cyan] {description} [dim]({size})[/dim]")

    console.print("\n[dim]Use 'weld prompt show <name>' to view a prompt[/dim]\n")


@app.command("show")
def show_prompt(
    prompt_type: Annotated[
        PromptType,
        typer.Argument(help="Prompt type to display"),
    ],
    raw: Annotated[
        bool,
        typer.Option("--raw", "-r", help="Show raw prompt without customizations"),
    ] = False,
    focus: Annotated[
        Optional[str],
        typer.Option("--focus", "-f", help="Focus area to include"),
    ] = None,
    spec: Annotated[
        Optional[str],
        typer.Option("--spec", help="Sample spec content for templates"),
    ] = None,
    diff: Annotated[
        Optional[str],
        typer.Option("--diff", help="Sample diff content for code review"),
    ] = None,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Show apply mode variant (for review prompts)"),
    ] = False,
) -> None:
    """Display a prompt template.

    Shows the full prompt that would be sent to Claude for the specified
    command type. Use --raw to see the base template without any
    customizations from .weld/config.toml.
    """
    console = Console()

    # Build kwargs for generator
    kwargs = {
        "focus": focus,
        "spec": spec or "<specification content>",
        "spec_name": "spec.md",
        "diff": diff or "<diff content>",
        "document_path": "document.md",
        "document_content": "<document content>",
        "apply": apply,
    }

    # Generate base prompt
    generator = PROMPT_GENERATORS.get(prompt_type)
    if generator is None:
        # Handle implement and commit separately (inline prompts)
        if prompt_type == PromptType.IMPLEMENT:
            prompt = _get_implement_prompt_sample()
        elif prompt_type == PromptType.COMMIT:
            prompt = _get_commit_prompt_sample()
        else:
            console.print(f"[red]Unknown prompt type: {prompt_type}[/red]")
            raise typer.Exit(1)
    else:
        prompt = generator(**kwargs)

    # Apply customizations unless --raw
    if not raw:
        try:
            weld_dir = find_weld_dir()
            task_type = _prompt_type_to_task_type(prompt_type)
            if task_type:
                prompt = apply_customization(prompt, task_type, weld_dir)
        except FileNotFoundError:
            pass  # No weld dir, skip customization

    # Display
    title = f"Prompt: {prompt_type.value}"
    if not raw:
        title += " (with customizations)"
    else:
        title += " (raw)"

    console.print()
    console.print(Panel(
        Syntax(prompt, "markdown", theme="monokai", word_wrap=True),
        title=title,
        border_style="blue",
    ))
    console.print()


@app.command("export")
def export_prompts(
    output_dir: Annotated[
        Path,
        typer.Argument(help="Directory to export prompts to"),
    ],
    raw: Annotated[
        bool,
        typer.Option("--raw", "-r", help="Export raw prompts without customizations"),
    ] = False,
) -> None:
    """Export all prompt templates to files.

    Creates one markdown file per prompt type in the specified directory.
    """
    console = Console()
    output_dir.mkdir(parents=True, exist_ok=True)

    exported = []
    for prompt_type in PromptType:
        filename = f"{prompt_type.value}.md"
        filepath = output_dir / filename

        # Generate prompt
        kwargs = {
            "focus": None,
            "spec": "<specification content>",
            "spec_name": "spec.md",
            "diff": "<diff content>",
            "document_path": "document.md",
            "document_content": "<document content>",
            "apply": False,
        }

        generator = PROMPT_GENERATORS.get(prompt_type)
        if generator:
            prompt = generator(**kwargs)
        elif prompt_type == PromptType.IMPLEMENT:
            prompt = _get_implement_prompt_sample()
        elif prompt_type == PromptType.COMMIT:
            prompt = _get_commit_prompt_sample()
        else:
            continue

        # Apply customizations unless --raw
        if not raw:
            try:
                weld_dir = find_weld_dir()
                task_type = _prompt_type_to_task_type(prompt_type)
                if task_type:
                    prompt = apply_customization(prompt, task_type, weld_dir)
            except FileNotFoundError:
                pass

        # Write file
        filepath.write_text(prompt)
        exported.append(filename)

    console.print(f"\n[green]Exported {len(exported)} prompts to {output_dir}/[/green]")
    for f in exported:
        console.print(f"  - {f}")
    console.print()


def _prompt_type_to_task_type(prompt_type: PromptType) -> TaskType | None:
    """Map PromptType to TaskType for customization."""
    mapping = {
        PromptType.DISCOVER: TaskType.DISCOVER,
        PromptType.INTERVIEW: TaskType.INTERVIEW,
        PromptType.RESEARCH: TaskType.RESEARCH,
        PromptType.PLAN: TaskType.PLAN_GENERATION,
        PromptType.IMPLEMENT: TaskType.IMPLEMENTATION,
        PromptType.REVIEW_DOC: TaskType.REVIEW,
        PromptType.REVIEW_CODE: TaskType.REVIEW,
        PromptType.COMMIT: TaskType.COMMIT,
    }
    return mapping.get(prompt_type)


def _get_implement_prompt_sample() -> str:
    """Return sample implementation prompt."""
    return """You are executing Step 1 of a phased implementation plan.

## Current Step
**Step 1: <step title>**

<step content from parsed plan>

## Instructions
1. Review the step content above
2. If step is already complete, respond with "ALREADY_COMPLETE" and explain
3. Otherwise, implement the step completely
4. Run validation command if specified
5. Report any issues encountered

## Context
- Plan file: plan.md
- Current phase: Phase 1
- Previous steps completed: 0"""


def _get_commit_prompt_sample() -> str:
    """Return sample commit prompt."""
    return """Analyze the following git diff and staged files to generate commit message(s).

## Staged Files
<list of staged files>

## Diff Content
<diff content>

## CHANGELOG.md
<changelog content if present>

## Instructions
1. Analyze the changes for logical grouping
2. Generate commit message(s) using imperative mood
3. Keep messages concise (1-2 sentences)
4. Focus on "why" rather than "what"
5. Do not mention AI assistance

## Output Format
Respond with XML structure:
<commits>
  <commit>
    <files>file1.py, file2.py</files>
    <message>Add user authentication endpoint</message>
  </commit>
</commits>"""
```

#### 2. Register Command

**File:** `src/weld/cli.py`

```python
from weld.commands import prompt

# Add to app
app.add_typer(prompt.app, name="prompt")
```

### Files to Create/Modify

| File | Changes |
|------|---------|
| `src/weld/commands/prompt.py` | New file: prompt command group |
| `src/weld/cli.py` | Register prompt subcommand |

### Testing

```python
# tests/test_prompt_command.py

class TestPromptList:
    def test_lists_all_prompts(self, runner):
        result = runner.invoke(app, ["prompt", "list"])
        assert result.exit_code == 0
        assert "discover" in result.output
        assert "plan" in result.output

class TestPromptShow:
    def test_shows_discover_prompt(self, runner):
        result = runner.invoke(app, ["prompt", "show", "discover"])
        assert result.exit_code == 0
        assert "System Architecture" in result.output

    def test_raw_flag_skips_customization(self, runner, temp_weld_dir):
        # Create config with prefix
        # Verify --raw excludes prefix

    def test_focus_parameter(self, runner):
        result = runner.invoke(app, ["prompt", "show", "discover", "--focus", "API"])
        assert "API" in result.output

class TestPromptExport:
    def test_exports_all_prompts(self, runner, tmp_path):
        result = runner.invoke(app, ["prompt", "export", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "discover.md").exists()
        assert (tmp_path / "plan.md").exists()
```

---

## Implementation Order

### Phase 1: Prompt Viewer Command (simpler, standalone)

1. Create `src/weld/commands/prompt.py` with `list`, `show`, `export` commands
2. Register in `src/weld/cli.py`
3. Add tests in `tests/test_prompt_command.py`
4. Update `CLAUDE.md` with new command documentation

### Phase 2: Prompts Personalization

1. Add `PromptCustomization` and `PromptsConfig` to `src/weld/config.py`
2. Create `src/weld/core/prompt_customizer.py`
3. Update all command files to use `apply_customization()`
4. Add tests for customization behavior
5. Update `CLAUDE.md` with configuration documentation

---

## Validation Checklist

- [ ] All existing tests pass after changes
- [ ] New features have >80% test coverage
- [ ] `make check` passes (lint, format, types)
- [ ] `make security` passes
- [ ] Commands work with `--dry-run` and `--json` flags
- [ ] Error messages are clear and actionable
- [ ] CHANGELOG.md updated with new features
