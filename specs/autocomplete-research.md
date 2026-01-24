# Autocomplete Support Research Document

## Executive Summary

This document analyzes the specification for adding shell tab-completion support to the weld CLI. The implementation can leverage Typer's built-in completion infrastructure with minimal additional dependencies. Key findings indicate that the project is well-positioned for this feature, with clear patterns to follow and no significant blockers.

---

## 1. Architecture Analysis

### 1.1 Existing CLI Structure

The weld CLI uses Typer 0.12+ with a hierarchical command structure defined in `src/weld/cli.py`:

```
weld (main app)
├── discover (sub-app, invoke_without_command=True)
├── prompt (sub-app, invoke_without_command=True)
├── telegram (sub-app, no_args_is_help=True)
│   ├── projects (sub-sub-app)
│   └── user (sub-sub-app)
└── [top-level commands]: init, commit, implement, interview, doctor, plan, research, review
```

**Key file locations:**
- Entry point: `src/weld/cli.py:42` - Main app definition
- Commands: `src/weld/commands/*.py` - Individual command implementations
- Telegram nested commands: `src/weld/telegram/cli.py:21-38` - Multi-level sub-apps

### 1.2 Current Argument/Option Patterns

The codebase uses the modern `Annotated[type, typer.Argument/Option]` pattern consistently:

**Positional Arguments (from `src/weld/commands/implement.py:82-87`):**
```python
plan_file: Annotated[
    Path,
    typer.Argument(
        help="Markdown plan file to implement",
    ),
],
```

**Options with short forms (from `src/weld/commands/prompt.py:258-265`):**
```python
raw: Annotated[
    bool,
    typer.Option(
        "--raw",
        "-r",
        help="Output raw prompt template without Rich formatting",
    ),
] = False,
```

**String arguments for enum-like values (from `src/weld/commands/prompt.py:253-257`):**
```python
task: Annotated[
    str,
    typer.Argument(help="Task type to show (e.g., discover, research, plan_generation)"),
],
```

### 1.3 Extension Points

Typer supports the `autocompletion` parameter on `typer.Argument()` and `typer.Option()`:

```python
typer.Argument(
    help="...",
    autocompletion=complete_function,  # <-- Add this
)
```

The completion function receives:
- `incomplete: str` - The partial input typed so far
- `ctx: typer.Context` (optional) - Access to other parameter values
- Returns: `list[str]` (values only, per project convention)

### 1.4 Potential Conflicts

**None identified.** The specification aligns with existing patterns and Typer's built-in capabilities.

---

## 2. Dependency Mapping

### 2.1 External Dependencies

**No new dependencies required.** The implementation uses:
- `typer>=0.12` (already installed) - Built-in completion support via Click 8+
- Standard library `pathlib`, `glob` - For file path completion

### 2.2 Internal Module Dependencies

The completion module will have minimal dependencies:

| Dependency | Purpose | Import Risk |
|------------|---------|-------------|
| `weld.config.TaskType` | Enum values for task completion | Low - stable API |
| Standard library only | File path completion | None |

**Note:** Telegram config loading is explicitly excluded from completion functions. Users must type project and user names manually, avoiding the complexity and latency of config file parsing at shell time.

### 2.3 Version Constraints

**Typer 0.12+**: The `autocompletion` parameter is fully supported. Note that older Typer versions (pre-0.9) used `shell_complete` which had different semantics. The current codebase uses `typer>=0.12` which supports the modern `autocompletion` approach.

**Python 3.11+**: Required by the project, so we can use modern type hints and `Annotated`.

---

## 3. Design Decisions

### 3.1 Completion Result Strategy

**Decision: Alphabetical ordering with 20-result cap**

When multiple matches exist, completions are returned in alphabetical order, capped at 20 results. This provides:
- Predictable, consistent ordering users can rely on
- Simple implementation without filesystem stat calls
- Clear path to narrowing results by typing more characters

### 3.2 Telegram Completion Scope

**Decision: Skip config-dependent completions**

Telegram-related completions will only complete static values (subcommand names). Users must type project names and user identifiers manually. This decision:
- Eliminates latency from config file loading
- Avoids complexity of caching between completion calls
- Removes potential security concerns around exposing config contents

### 3.3 Path Completion Behavior

**Decision: Follow the incomplete path**

File completions follow the user's typed path without proactive subdirectory scanning:
- `weld implement <TAB>` - Shows `*.md` files in current directory
- `weld implement docs/<TAB>` - Shows `*.md` files inside `docs/`
- `weld implement src/specs/<TAB>` - Shows `*.md` files inside `src/specs/`

This approach respects user intent and avoids overwhelming results from deep directory traversal.

### 3.4 Completion Output Format

**Decision: Values only (no help text)**

Completion functions return plain string lists without description tuples. This provides:
- Minimal, fast-to-scan shell output
- Cleaner integration across different shell environments
- Help text remains available via `--help` when users need it

### 3.5 Static Plan Step Fallbacks

**Decision: Conservative range (1.1-3.3)**

When dynamic plan parsing isn't available, static suggestions cover steps 1.1 through 3.3 (9 total suggestions). This:
- Covers the most common small-to-medium plan structures
- Avoids overwhelming shell output with excessive suggestions
- Matches typical weld plan phase/step patterns

### 3.6 Export Format Completion

**Decision: Available formats only**

The `weld prompt export --format` completion checks for optional dependencies at completion time and only shows installable formats. For example:
- `toml` and `json` always shown (stdlib support)
- `yaml` only shown if `pyyaml` is installed

This prevents user frustration from selecting unavailable formats.

---

## 4. Risk Assessment

### 4.1 Technical Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Completion slowness | Medium | Lazy imports enforced via code review; no config loading |
| Large directories overwhelm shell | Low | Cap file completions at 20 results, alphabetically sorted |
| Cross-platform shell differences | Low | Typer abstracts shell-specific completion; document-only verification |

### 4.2 Areas Requiring Prototyping

1. **Typer completion with nested sub-apps**: Verify completion propagates correctly through `weld telegram projects remove <TAB>`. Based on exploration, this should work since Typer/Click handles sub-app routing before calling completion functions.

2. **File path completion behavior**: Test whether partial paths like `src/<TAB>` and `./spec<TAB>` work correctly with the path-following approach.

### 4.3 Performance Considerations

**Target: Lazy import enforcement (no runtime measurement)**

Completion functions are invoked on every TAB press. Performance is ensured through:
- Code review checklist item for lazy imports
- No config file loading in completion functions
- No filesystem stat calls for ordering (alphabetical only)
- No runtime benchmarking in CI (trust implementation patterns)

### 4.4 Security Considerations

1. **No secrets in completions**: Completion functions never expose:
   - Telegram bot tokens
   - API keys
   - Credentials from config files
   - (Telegram config is not loaded at all)

2. **Safe file system access**: Use try/except blocks around file operations to prevent crashes on permission errors.

3. **Path traversal**: File completion follows user-typed paths only; no proactive subdirectory scanning limits exposure of directory structures.

---

## 5. Testing Strategy

### 5.1 Unit Testing Approach

**Decision: Mock pathlib.Path.glob**

Completion functions are tested with mocked filesystem access:
- Pure unit tests with no actual file I/O
- Fast test execution
- Predictable test environments
- Focus on edge cases: empty input, no matches, partial matches, permission errors

```python
def test_complete_markdown_file_filters_by_prefix(mocker):
    mock_glob = mocker.patch("pathlib.Path.glob")
    mock_glob.return_value = [Path("plan.md"), Path("spec.md"), Path("readme.md")]

    results = complete_markdown_file("pl")

    assert results == ["plan.md"]
```

### 5.2 Shell Compatibility

**Decision: Document only (no active CI testing)**

Shell completion installation is documented for bash, zsh, fish, and PowerShell. Cross-shell compatibility relies on Typer's built-in abstraction without active CI verification. This:
- Reduces CI complexity and execution time
- Leverages Typer's mature cross-shell support
- Focuses testing effort on completion logic rather than shell integration

### 5.3 Integration Testing

CLI integration tests verify completion infrastructure exists:

```python
def test_help_shows_completion_option(self, runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "--install-completion" in result.stdout
```

---

## 6. Open Questions (Resolved)

### 6.1 Resolved from Interview

| Question | Resolution |
|----------|------------|
| Completion result ordering | Alphabetical order |
| Telegram config loading | Skip config-dependent completions entirely |
| Path completion depth | Follow incomplete path only |
| Help text verbosity | Values only (no descriptions) |
| Static step range | Conservative 1.1-3.3 |
| Testing approach | Mock pathlib.Path.glob |
| Shell compatibility testing | Document only |
| Export format scope | Available formats only (check deps) |
| Performance validation | Lazy import enforcement via review |
| Documentation location | Standalone docs/shell-completion.md |

### 6.2 Remaining Implementation Notes

1. **Step/phase completion from plan file**: Use static fallback patterns (`1.1`, `1.2`, `2.1`, etc. through `3.3`) as dynamic parsing from partial CLI state is unreliable.

2. **Completion for `weld commit`**: No custom completion needed - all options are flags with built-in completion.

---

## 7. Implementation Recommendations

### 7.1 Suggested File Structure

```
src/weld/
├── completions.py          # NEW: All completion functions
├── commands/
│   ├── implement.py        # Modify: Add autocompletion to plan_file, --step, --phase
│   ├── prompt.py           # Modify: Add autocompletion to task argument
│   └── ...
└── telegram/
    └── cli.py              # No changes needed (static subcommand completion only)

docs/
└── shell-completion.md     # NEW: Comprehensive installation guide per shell
```

### 7.2 Documentation Approach

**Primary location: `docs/shell-completion.md`**

A standalone documentation file keeps the README concise while providing comprehensive multi-shell installation instructions:
- Bash installation and configuration
- Zsh installation and configuration
- Fish installation and configuration
- PowerShell installation and configuration
- Troubleshooting common issues

The README may include a brief mention with a link to the full documentation.

### 7.3 Phased Implementation

1. **Phase 1**: Verify built-in completions work (low effort, quick win)
2. **Phase 2**: Static completions (TaskType enum, export formats with dep checking)
3. **Phase 3**: Dynamic path completions (markdown files following incomplete path)
4. **Phase 4**: Static step/phase completions (1.1-3.3 fallbacks)
5. **Phase 5**: Documentation (`docs/shell-completion.md`)
6. **Phase 6**: Testing (mocked unit tests)

---

## 8. Code Patterns to Follow

### 8.1 Completion Function Template

Based on Typer's API and project conventions (values only, lazy imports):

```python
def complete_task_type(incomplete: str) -> list[str]:
    """Complete task type argument.

    Args:
        incomplete: Partial input from user

    Returns:
        List of matching task type values (alphabetically sorted)
    """
    # Lazy import to avoid loading full config module at shell time
    from weld.config import TaskType

    matches = [
        task.value
        for task in TaskType
        if task.value.startswith(incomplete)
    ]
    return sorted(matches)[:20]
```

### 8.2 Argument with Completion

```python
task: Annotated[
    str,
    typer.Argument(
        help="Task type to show",
        autocompletion=complete_task_type,
    ),
],
```

### 8.3 Path-Following File Completion Pattern

```python
def complete_markdown_file(incomplete: str) -> list[str]:
    """Complete markdown file paths following user's typed path."""
    from pathlib import Path

    try:
        results = []

        if not incomplete:
            # No input: complete from current directory
            search_dir = Path(".")
            prefix = ""
        elif incomplete.endswith("/"):
            # Trailing slash: complete inside that directory
            search_dir = Path(incomplete)
            prefix = ""
        else:
            # Partial path: complete from parent with prefix filter
            base = Path(incomplete)
            search_dir = base.parent if base.parent.exists() else Path(".")
            prefix = base.name

        if not search_dir.is_dir():
            return []

        for md_file in search_dir.glob("*.md"):
            if md_file.name.startswith(prefix):
                results.append(str(md_file))

        # Also suggest subdirectories for navigation
        for subdir in search_dir.iterdir():
            if subdir.is_dir() and subdir.name.startswith(prefix):
                results.append(str(subdir) + "/")

        return sorted(results)[:20]  # Alphabetical, capped
    except (PermissionError, OSError):
        return []
```

### 8.4 Export Format Completion with Dependency Check

```python
def complete_export_format(incomplete: str) -> list[str]:
    """Complete export formats, showing only available ones."""
    formats = ["json", "toml"]  # Always available (stdlib)

    # Check for optional yaml support
    try:
        import yaml  # noqa: F401
        formats.append("yaml")
    except ImportError:
        pass

    matches = [f for f in formats if f.startswith(incomplete)]
    return sorted(matches)
```

### 8.5 Static Step Completion

```python
def complete_step_number(incomplete: str) -> list[str]:
    """Complete step numbers with static fallbacks (1.1-3.3)."""
    static_steps = [
        "1.1", "1.2", "1.3",
        "2.1", "2.2", "2.3",
        "3.1", "3.2", "3.3",
    ]
    matches = [s for s in static_steps if s.startswith(incomplete)]
    return sorted(matches)
```

---

## 9. Acceptance Criteria Validation

| Criterion | Status | Notes |
|-----------|--------|-------|
| `weld --install-completion bash` generates valid script | ✅ Built-in | Typer provides this |
| `weld <TAB>` shows commands | ✅ Built-in | Typer provides this |
| `weld prompt show <TAB>` shows TaskType values | ⏳ Implementation | Values only, alphabetical |
| `weld implement <TAB>` shows *.md files | ⏳ Implementation | Path-following, 20 max |
| `weld implement --step <TAB>` shows step numbers | ⏳ Implementation | Static 1.1-3.3 |
| `weld prompt export --format <TAB>` shows formats | ⏳ Implementation | Available formats only |
| `weld telegram projects remove <TAB>` | ⛔ Excluded | Config-dependent; user types manually |
| Documentation for bash/zsh/fish/PowerShell | ⏳ Documentation | `docs/shell-completion.md` |
| Unit tests for completion functions | ⏳ Testing | Mocked pathlib.Path.glob |

---

## 10. Summary

The autocomplete feature is well-suited for implementation:

- **Low risk**: Uses Typer's built-in infrastructure
- **No new dependencies**: Leverages existing tooling
- **Clear patterns**: Existing codebase provides good templates
- **Incremental delivery**: Can ship phases independently
- **Minimal complexity**: Config-dependent completions excluded

**Key implementation constraints (from interview):**
1. Alphabetical ordering, 20-result cap
2. No telegram config loading (static subcommands only)
3. Path completion follows user input (no proactive scanning)
4. Values only (no help text tuples)
5. Static step fallbacks: 1.1-3.3
6. Mock-based unit testing
7. Document-only shell verification
8. Available formats only for export completion
9. Lazy import enforcement via code review
10. Standalone documentation in `docs/shell-completion.md`

**Estimated complexity:** Low
- Core completion module: ~100 lines
- Command modifications: ~50 lines across files
- Tests: ~150 lines (mocked)
- Documentation: ~100 lines

---

## Sources

- [Typer CLI Options Autocompletion Tutorial](https://typer.tiangolo.com/tutorial/options-autocompletion/)
- [Typer GitHub Issue #949: shell_complete vs autocompletion](https://github.com/fastapi/typer/issues/949)
- [Typer Features Documentation](https://typer.tiangolo.com/features/)
