# Autocomplete Support for Weld CLI

## Overview

Add shell tab-completion support for weld commands, subcommands, arguments, and options. This enables users to discover available commands and arguments faster, reducing friction and typos.

## Goals

1. **Command completion**: Complete top-level commands (`weld init`, `weld commit`, `weld implement`)
2. **Subcommand completion**: Complete nested commands (`weld telegram projects add`, `weld prompt show`)
3. **Option completion**: Complete flags and options (`--quiet`, `--auto-commit`, `--format`)
4. **Argument completion**: Provide intelligent completions for command arguments
5. **Installation support**: Provide commands to install completions for bash, zsh, fish, and PowerShell

## Typer Shell Completion

Typer provides built-in shell completion via the `typer.main.get_completion_class()` infrastructure. Typer automatically handles:

- Command name completion
- Option name completion (`--help`, `--version`, etc.)
- Boolean flag completion

For custom argument completion, Typer uses `shell_complete` callbacks on `typer.Argument()` and `typer.Option()`.

### Installation Mechanism

Typer applications support completion installation via:

```bash
weld --install-completion [bash|zsh|fish|powershell]
weld --show-completion [bash|zsh|fish|powershell]
```

These are added automatically when using `typer.Typer()`.

## Implementation Strategy

### Phase 1: Enable Built-in Completions

Typer's built-in completion is already available but may need configuration to work optimally with the entry point. Verify:

1. The `weld` entry point in `pyproject.toml` is compatible
2. Completion works for all registered commands and subcommands
3. Add documentation for users on how to install completions

### Phase 2: Static Completions

Add `shell_complete` callbacks for arguments with known value sets.

#### Task Types (prompt show, prompt export)

The `weld prompt show <task>` command accepts task types from `TaskType` enum.

```python
# src/weld/commands/prompt.py

def complete_task_type(incomplete: str) -> list[tuple[str, str]]:
    """Complete task type argument."""
    from weld.config import TaskType

    completions = []
    for task in TaskType:
        if task.value.startswith(incomplete):
            description = TASK_DESCRIPTIONS.get(task, "")
            completions.append((task.value, description))
    return completions

@prompt_app.command("show")
def show_prompt(
    task: Annotated[
        str,
        typer.Argument(
            help="Task type to show",
            autocompletion=complete_task_type,
        ),
    ],
    ...
):
```

#### Export Formats (prompt export)

```python
def complete_format(incomplete: str) -> list[tuple[str, str]]:
    """Complete export format option."""
    formats = [
        ("toml", "TOML configuration format"),
        ("json", "JSON format for programmatic use"),
    ]
    return [(f, d) for f, d in formats if f.startswith(incomplete)]
```

### Phase 3: Dynamic Path Completions

For file/directory arguments, use Typer's path completion or custom completers.

#### Plan File (implement command)

```python
def complete_plan_file(incomplete: str) -> list[str]:
    """Complete plan file paths (*.md files)."""
    import glob

    pattern = f"{incomplete}*.md" if incomplete else "*.md"
    return glob.glob(pattern, recursive=False)[:20]

def implement(
    plan_file: Annotated[
        Path,
        typer.Argument(
            help="Markdown plan file to implement",
            autocompletion=complete_plan_file,
        ),
    ],
    ...
):
```

#### Project Names (telegram commands)

```python
def complete_project_name(incomplete: str) -> list[tuple[str, str]]:
    """Complete registered project names."""
    try:
        from weld.telegram.config import get_config_path, load_config

        config_path = get_config_path()
        if not config_path.exists():
            return []

        config = load_config(config_path)
        return [
            (p.name, p.description or p.path.name)
            for p in config.projects
            if p.name.startswith(incomplete)
        ]
    except Exception:
        return []
```

### Phase 4: Completions Module

Create a dedicated module for completion functions:

```
src/weld/
├── completions.py          # Shared completion functions
├── commands/
│   ├── commit.py           # Uses path completions
│   ├── implement.py        # Uses plan file completions
│   ├── prompt.py           # Uses task type completions
│   └── ...
```

**`src/weld/completions.py`**:

```python
"""Shell completion functions for weld CLI.

This module provides autocompletion for commands, arguments, and options.
Completions are used by Typer's shell completion infrastructure for
bash, zsh, fish, and PowerShell.
"""

from pathlib import Path

from weld.config import TaskType


def complete_task_type(incomplete: str) -> list[tuple[str, str]]:
    """Complete task type names with descriptions.

    Args:
        incomplete: Partial input from the user

    Returns:
        List of (value, help_text) tuples for matching task types
    """
    from weld.commands.prompt import TASK_DESCRIPTIONS

    return [
        (task.value, TASK_DESCRIPTIONS.get(task, ""))
        for task in TaskType
        if task.value.startswith(incomplete)
    ]


def complete_markdown_file(incomplete: str) -> list[str]:
    """Complete markdown file paths.

    Searches current directory and subdirectories for .md files.
    Limited to 20 results to avoid overwhelming the shell.
    """
    from pathlib import Path

    results = []
    search_path = Path(incomplete) if incomplete else Path(".")

    # If incomplete looks like a partial path, search that directory
    if incomplete and not incomplete.endswith("/"):
        search_dir = search_path.parent if search_path.parent.exists() else Path(".")
        prefix = search_path.name
    else:
        search_dir = search_path if search_path.is_dir() else Path(".")
        prefix = ""

    try:
        for md_file in search_dir.glob("*.md"):
            if md_file.name.startswith(prefix):
                results.append(str(md_file))

        # Also search one level of subdirectories
        for subdir in search_dir.iterdir():
            if subdir.is_dir() and not subdir.name.startswith("."):
                for md_file in subdir.glob("*.md"):
                    results.append(str(md_file))
    except PermissionError:
        pass

    return sorted(results)[:20]


def complete_telegram_project(incomplete: str) -> list[tuple[str, str]]:
    """Complete registered Telegram project names.

    Reads project list from Telegram config file.
    Returns project name and path as help text.
    """
    try:
        from weld.telegram.config import get_config_path, load_config

        config_path = get_config_path()
        if not config_path.exists():
            return []

        config = load_config(config_path)
        return [
            (project.name, f"{project.path}")
            for project in config.projects
            if project.name.startswith(incomplete)
        ]
    except Exception:
        return []


def complete_step_number(incomplete: str) -> list[tuple[str, str]]:
    """Complete step numbers for implement command.

    Attempts to parse a plan file from context and extract step numbers.
    Falls back to common patterns if no plan file is available.
    """
    # Common step number patterns as fallback
    common_steps = [
        ("1.1", "First step of phase 1"),
        ("1.2", "Second step of phase 1"),
        ("2.1", "First step of phase 2"),
        ("2.2", "Second step of phase 2"),
    ]

    return [
        (step, desc)
        for step, desc in common_steps
        if step.startswith(incomplete)
    ]


def complete_phase_number(incomplete: str) -> list[tuple[str, str]]:
    """Complete phase numbers for implement command."""
    phases = [
        ("1", "Phase 1"),
        ("2", "Phase 2"),
        ("3", "Phase 3"),
        ("4", "Phase 4"),
        ("5", "Phase 5"),
    ]

    return [
        (num, desc)
        for num, desc in phases
        if num.startswith(incomplete)
    ]


def complete_directory(incomplete: str) -> list[str]:
    """Complete directory paths.

    Used for export directories and project paths.
    """
    from pathlib import Path

    results = []
    search_path = Path(incomplete) if incomplete else Path(".")

    if incomplete and not incomplete.endswith("/"):
        search_dir = search_path.parent if search_path.parent.exists() else Path(".")
        prefix = search_path.name
    else:
        search_dir = search_path if search_path.is_dir() else Path(".")
        prefix = ""

    try:
        for item in search_dir.iterdir():
            if item.is_dir() and item.name.startswith(prefix):
                if not item.name.startswith("."):  # Skip hidden directories
                    results.append(str(item) + "/")
    except PermissionError:
        pass

    return sorted(results)[:20]
```

## Commands Requiring Completions

| Command | Argument/Option | Completion Type |
|---------|-----------------|-----------------|
| `weld implement` | `plan_file` | Markdown files (*.md) |
| `weld implement` | `--step` | Step numbers (dynamic from plan) |
| `weld implement` | `--phase` | Phase numbers (1-5) |
| `weld prompt show` | `task` | TaskType enum values |
| `weld prompt export` | `directory` | Directory paths |
| `weld prompt export` | `--format` | "toml", "json" |
| `weld telegram projects add` | `path` | Directory paths |
| `weld telegram projects remove` | `name` | Registered project names |
| `weld telegram user add` | `identifier` | (no completion - user input) |

## Installation Documentation

Add a `docs/shell-completion.md` file:

```markdown
# Shell Completion

Weld supports tab-completion for bash, zsh, fish, and PowerShell.

## Installation

### Bash

```bash
# Add to ~/.bashrc
weld --install-completion bash
```

### Zsh

```bash
# Add to ~/.zshrc
weld --install-completion zsh
```

### Fish

```bash
# Add to fish completions
weld --install-completion fish
```

### PowerShell

```powershell
# Add to $PROFILE
weld --install-completion powershell
```

## Manual Installation

If automatic installation doesn't work, you can manually add the completion script:

```bash
# Show the completion script
weld --show-completion bash >> ~/.bashrc

# Or for zsh
weld --show-completion zsh >> ~/.zshrc
```

## Usage

After installation and restarting your shell:

```bash
# Complete commands
weld <TAB>          # Shows: commit, implement, init, doctor, ...

# Complete subcommands
weld telegram <TAB> # Shows: init, serve, whoami, doctor, projects, user

# Complete options
weld implement --<TAB>  # Shows: --step, --phase, --quiet, --auto-commit, ...

# Complete arguments
weld prompt show <TAB>  # Shows: discover, research, plan_generation, ...
```
```

## Testing

### Unit Tests

Create `tests/test_completions.py`:

```python
"""Tests for shell completion functions."""

import pytest

from weld.completions import (
    complete_task_type,
    complete_markdown_file,
    complete_telegram_project,
    complete_phase_number,
)


class TestTaskTypeCompletion:
    """Tests for task type completion."""

    def test_empty_input_returns_all(self):
        """Empty input should return all task types."""
        results = complete_task_type("")
        assert len(results) == 12  # All TaskType values

    def test_partial_match(self):
        """Partial input should filter results."""
        results = complete_task_type("dis")
        assert len(results) == 1
        assert results[0][0] == "discover"

    def test_no_match(self):
        """Non-matching input should return empty list."""
        results = complete_task_type("xyz")
        assert len(results) == 0

    def test_returns_descriptions(self):
        """Results should include descriptions."""
        results = complete_task_type("res")
        assert any("Research" in desc for _, desc in results)


class TestPhaseNumberCompletion:
    """Tests for phase number completion."""

    def test_returns_phases_1_to_5(self):
        """Should return phases 1 through 5."""
        results = complete_phase_number("")
        assert len(results) == 5

    def test_filters_by_prefix(self):
        """Should filter by prefix."""
        results = complete_phase_number("2")
        assert len(results) == 1
        assert results[0][0] == "2"


class TestMarkdownFileCompletion:
    """Tests for markdown file completion."""

    def test_finds_md_files(self, tmp_path, monkeypatch):
        """Should find .md files in directory."""
        monkeypatch.chdir(tmp_path)

        (tmp_path / "plan.md").touch()
        (tmp_path / "spec.md").touch()
        (tmp_path / "readme.txt").touch()  # Should not match

        results = complete_markdown_file("")
        assert len(results) == 2
        assert any("plan.md" in r for r in results)
        assert any("spec.md" in r for r in results)
```

### Integration Tests

```python
@pytest.mark.cli
def test_completion_install_command(runner):
    """Test that completion installation command exists."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--install-completion" in result.output or "install-completion" in result.output


@pytest.mark.cli
def test_show_completion_bash(runner):
    """Test that bash completion script can be generated."""
    result = runner.invoke(app, ["--show-completion", "bash"])
    # Should succeed or show help (depending on Typer version)
    assert result.exit_code in (0, 1)
```

## Implementation Tasks

### Phase 1: Core Infrastructure (Priority: High)
- [ ] Create `src/weld/completions.py` module
- [ ] Add `complete_task_type()` for TaskType enum
- [ ] Add `complete_markdown_file()` for plan files
- [ ] Add `complete_directory()` for path arguments

### Phase 2: Command Integration (Priority: High)
- [ ] Add completion to `weld prompt show` task argument
- [ ] Add completion to `weld implement` plan_file argument
- [ ] Add completion to `weld implement --step` option
- [ ] Add completion to `weld implement --phase` option
- [ ] Add completion to `weld prompt export --format` option

### Phase 3: Telegram Commands (Priority: Medium)
- [ ] Add `complete_telegram_project()` function
- [ ] Add completion to `weld telegram projects remove` name argument
- [ ] Add completion to `weld telegram projects add` path argument

### Phase 4: Documentation (Priority: Medium)
- [ ] Create `docs/shell-completion.md`
- [ ] Update README.md with completion installation instructions
- [ ] Add shell completion section to CLI help output

### Phase 5: Testing (Priority: Medium)
- [ ] Create `tests/test_completions.py`
- [ ] Add unit tests for all completion functions
- [ ] Add CLI integration tests for completion installation

## Security Considerations

1. **No secrets in completions**: Completion functions must not expose sensitive data (tokens, passwords, etc.)
2. **Safe file system access**: Use try/except blocks around file system operations
3. **Limited results**: Always limit completion results to avoid DoS via large directories

## Dependencies

- No new dependencies required
- Uses Typer's built-in `autocompletion` parameter (available since Typer 0.4+)
- Current Typer version (>=0.12) fully supports shell completion

## Acceptance Criteria

1. ✅ Running `weld --install-completion bash` generates valid bash completion script
2. ✅ Tab-completing `weld <TAB>` shows all top-level commands
3. ✅ Tab-completing `weld prompt show <TAB>` shows all TaskType values
4. ✅ Tab-completing `weld implement <TAB>` shows *.md files in current directory
5. ✅ Tab-completing `weld telegram projects remove <TAB>` shows registered projects
6. ✅ Documentation explains completion installation for bash, zsh, fish, PowerShell
7. ✅ Unit tests cover all completion functions
