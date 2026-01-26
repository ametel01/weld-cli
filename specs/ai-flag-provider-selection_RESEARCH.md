# Research Document: --ai Flag for AI Provider Selection

## Executive Summary

This research document analyzes the specification for adding a global `--ai` flag to the weld CLI. The implementation is straightforward with well-defined extension points, but requires resolving several open questions about the Codex CLI interface. The existing architecture provides clear patterns to follow, and the phased approach in the specification is sound.

---

## 1. Architecture Analysis

### 1.1 Existing Code Patterns to Follow

#### Service Layer Pattern (`services/claude.py`)

The Claude service provides an exemplary pattern for the Codex implementation:

**Key components** (from `src/weld/services/claude.py`):
- **Custom exception class**: `ClaudeError(Exception)` with descriptive messages
- **Main runner function**: `run_claude()` with clear parameter interface
- **Streaming support**: Uses `subprocess.Popen` with non-blocking I/O via `select.select()`
- **Output format parsing**: `_extract_text_from_stream_json()` for stream-json format
- **Error handling**: Graceful handling of `FileNotFoundError`, `TimeoutExpired`, non-zero exit codes

**Function signature to mirror**:
```python
def run_claude(
    prompt: str,
    exec_path: str = "claude",
    model: str | None = None,
    timeout: int | None = None,
    stream: bool = False,
    cwd: Path | None = None,
    skip_permissions: bool = False,
    max_output_tokens: int = 128000,
) -> str:
```

**Critical implementation details**:
- Prompt passed via stdin (`input=prompt`) to avoid OS argument length limits (`cli.py:26-34`)
- Timeout always applied (`timeout=timeout or 1800`)
- Process cleanup in `finally` blocks for streaming mode
- Streaming uses `--output-format stream-json --verbose` flags

#### Global Option Pattern (`cli.py`)

The main CLI callback shows how global options are implemented:

**Location**: `src/weld/cli.py:31-82`

```python
@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", ...)] = False,
    quiet: Annotated[bool, typer.Option("-q", "--quiet", ...)] = False,
    json_mode: Annotated[bool, typer.Option("--json", ...)] = False,
    # ... other options
) -> None:
```

**Pattern for `--ai` flag**:
```python
ai_provider: Annotated[
    str | None,
    typer.Option(
        "--ai",
        help="Override AI provider (claude, codex)",
        metavar="PROVIDER",
    ),
] = None,
```

**Validation approach**: Use Typer's callback pattern or validate in the main callback before storing in context.

#### OutputContext Pattern (`output.py`)

The `OutputContext` dataclass at `src/weld/output.py:23-35` uses a context variable pattern:

```python
@dataclass
class OutputContext:
    console: Console
    json_mode: bool = False
    dry_run: bool = False

_output_context: ContextVar[OutputContext] = ContextVar("output_context")
```

**Access pattern**: Commands use `get_output_context()` to retrieve the current context.

**Extension**: Add `ai_override: str | None = None` field to store the `--ai` flag value.

### 1.2 Extension Points and Integration Boundaries

#### Extension Point 1: `services/__init__.py`

**Location**: `src/weld/services/__init__.py`

Current exports:
```python
from .claude import ClaudeError, run_claude, run_claude_interactive
from .git import GitError, commit_file, get_repo_root, get_staged_files, ...
# etc.
```

**Required additions**:
```python
from .codex import CodexError, run_codex
from .ai_provider import AIProvider, AIProviderError, run_ai
```

#### Extension Point 2: Config Model (`config.py`)

The config already has `CodexConfig` and `TaskModelsConfig` at `src/weld/config.py:38-79`:

```python
class CodexConfig(BaseModel):
    exec: str = "codex"
    sandbox: str = "read-only"
    model: str | None = None

class TaskModelsConfig(BaseModel):
    discover: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    research: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    # ... other tasks
```

**Gap**: No `get_task_model(task: TaskType)` method exists. This needs to be added or provider resolution logic needs to be embedded in `run_ai()`.

#### Extension Point 3: Command Integration

Commands currently call `run_claude()` directly. Example from `research.py:109-117`:

```python
result = run_claude(
    prompt=prompt,
    exec_path=claude_exec,
    cwd=repo_root,
    timeout=config.claude.timeout,
    stream=not quiet,
    max_output_tokens=config.claude.max_output_tokens,
)
```

**Migration path**: Replace with `run_ai()` call that takes `AIProvider` enum.

### 1.3 Potential Conflicts with Existing Systems

#### Conflict 1: Streaming Output Differences

- **Claude**: Uses `--output-format stream-json` with JSON lines containing `{"type":"assistant","message":{"content":[...]}}`
- **Codex**: Uses `--json` or `--experimental-json` flag with "newline-delimited JSON events"

**Mitigation**: The `run_codex()` function must implement its own `_extract_text_from_codex_json()` parser. Cannot reuse Claude's parser.

#### Conflict 2: Interactive Mode Mismatch

- **Claude**: Has `run_claude_interactive()` for resumable sessions
- **Codex**: Has `codex exec resume [SESSION_ID]` mechanism

**Mitigation**: For Phase 1, skip interactive mode for Codex. The `run_codex()` function should focus on non-interactive `codex exec` usage. Interactive support can be a follow-up feature.

#### Conflict 3: Permission Handling

- **Claude**: Uses `--dangerously-skip-permissions` flag
- **Codex**: Uses `--sandbox` with values `read-only | workspace-write | danger-full-access`

**Mitigation**: Map Claude's permission concept to Codex's sandbox model. The `skip_permissions` parameter should set `sandbox="danger-full-access"` for Codex.

---

## 2. Dependency Mapping

### 2.1 External Dependencies

| Dependency | Purpose | Required Version | Notes |
|------------|---------|------------------|-------|
| `codex` CLI | AI provider | Latest | Not bundled; user must install |
| `subprocess` | Process execution | stdlib | Already used |
| `select` | Non-blocking I/O | stdlib | Already used for Claude streaming |

**New external dependency**: OpenAI Codex CLI
- Installation: `pip install openai-codex` or similar
- Documentation: https://github.com/openai/codex

### 2.2 Internal Module Dependencies

```
services/ai_provider.py
├── services/claude.py (run_claude, ClaudeError)
├── services/codex.py (run_codex, CodexError)  [NEW]
└── config.py (WeldConfig, TaskModelsConfig)

commands/*.py
├── services/ai_provider.py (run_ai, AIProvider)  [NEW dependency]
├── output.py (get_output_context)
└── config.py (WeldConfig, TaskType)  [TaskType might need creation]

cli.py
└── output.py (set_output_context, OutputContext)
```

### 2.3 Version Constraints

- **Python**: 3.10+ (existing requirement, uses `match` statements and `|` union types)
- **Typer**: Current version (no changes needed)
- **Pydantic**: Current version (using `BaseModel`, `Field`)

---

## 3. Risk Assessment

### 3.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Codex output format differs from expected | Medium | High | Prototype with actual codex CLI before full implementation |
| Streaming format incompatibility | Medium | Medium | Implement separate parser; don't share with Claude |
| Codex not installed on user systems | High | Low | Clear error messages with installation instructions |
| Breaking changes to existing tests | Low | High | Run test suite after each phase; maintain backwards compatibility |

### 3.2 Areas Requiring Prototyping

#### Prototype 1: Codex CLI Investigation

Before implementing `services/codex.py`, run these experiments:

```bash
# Basic execution
echo "Hello world" | codex exec --json -

# Check output format
codex exec --json "Explain Python decorators" 2>&1 | head -20

# Verify sandbox flag
codex exec --sandbox read-only --json "list files" 2>&1

# Model selection
codex exec --model gpt-5-codex --json "test" 2>&1
```

**Capture**:
1. Exact JSON structure in output
2. Error message format
3. Exit codes for various failure modes

#### Prototype 2: Streaming Output

```bash
# Test streaming behavior
codex exec --json "Write a long story" 2>&1 | while read line; do
    echo "LINE: $line"
done
```

**Determine**:
1. Does output arrive incrementally or all at once?
2. What JSON structure does each line have?
3. How to detect completion vs. error?

### 3.3 Performance Considerations

- **Minimal overhead**: The `run_ai()` abstraction adds one function call and an enum comparison—negligible cost
- **No caching needed**: Each AI call is independent
- **Streaming unchanged**: Both providers will use the same select-based streaming pattern

### 3.4 Security Considerations

| Concern | Status | Notes |
|---------|--------|-------|
| Command injection | Mitigated | All subprocess calls use `shell=False` (enforced by CLAUDE.md) |
| Credential exposure | N/A | Codex uses environment variables, not passed via weld |
| Sandbox bypass | Mitigated | Default sandbox is `read-only`; escalation requires explicit config |

---

## 4. Open Questions

### 4.1 Questions Requiring Human Input

#### Q1: TaskType Enum Location

**Decision needed**: Where should `TaskType` enum be defined?

**Options**:
1. **`config.py`**: Alongside `TaskModelsConfig` (logical grouping)
2. **`services/ai_provider.py`**: With the provider abstraction (encapsulation)
3. **New file `models/task.py`**: In models layer (separation of concerns)

**Recommendation**: Option 1 (`config.py`) as it directly relates to `TaskModelsConfig`.

#### Q2: Error Type Hierarchy

**Decision needed**: Should there be a common `AIProviderError` base class?

**Options**:
1. **Separate exceptions**: `ClaudeError`, `CodexError` (current approach)
2. **Common base**: `AIProviderError` with `ClaudeError(AIProviderError)`, `CodexError(AIProviderError)`

**Recommendation**: Option 2 allows commands to catch any provider error with a single `except AIProviderError`.

#### Q3: Dry-Run Behavior

**Decision needed**: What should `--dry-run` show when `--ai codex` is specified?

**Current behavior**: Shows Claude prompt
**Proposed**: Show prompt with "[Would use: codex]" indicator

### 4.2 Ambiguities in Specification

#### Ambiguity 1: Model Config Resolution

The spec shows:
```python
model_config = config.get_task_model(task)
```

But `WeldConfig` currently has no `get_task_model()` method. The actual structure is:
```python
config.task_models.discover  # Returns ModelConfig
config.task_models.research  # etc.
```

**Clarification needed**: Either add `get_task_model(task: TaskType)` method or use attribute access with `getattr()`.

**Suggested implementation**:
```python
# In WeldConfig
def get_task_model(self, task: TaskType) -> ModelConfig:
    return getattr(self.task_models, task.value, ModelConfig())
```

#### Ambiguity 2: Default Provider When Config Missing

If a task isn't explicitly configured, what provider should be used?

**Spec implies**: Claude (based on defaults in `TaskModelsConfig`)
**Recommendation**: Make this explicit in the abstraction layer.

### 4.3 Alternative Approaches Worth Considering

#### Alternative 1: Plugin Architecture

Instead of hardcoding Claude/Codex, implement a provider plugin system:

```python
class AIProviderPlugin(Protocol):
    def run(self, prompt: str, **kwargs) -> str: ...
    def name(self) -> str: ...
```

**Pros**: Future extensibility (Gemini, local LLMs, etc.)
**Cons**: Over-engineering for current requirements; adds complexity

**Recommendation**: Defer to later. The current approach can evolve into plugins if needed.

#### Alternative 2: Decorator-Based Provider Selection

```python
@with_ai_provider(TaskType.RESEARCH)
def research(...):
    # Provider automatically injected
```

**Pros**: DRY, less boilerplate in commands
**Cons**: Magic behavior, harder to understand, complicates testing

**Recommendation**: Reject. Explicit `run_ai()` calls are clearer.

#### Alternative 3: Environment Variable Override

In addition to `--ai` flag, support `WELD_AI_PROVIDER` env var:

```bash
WELD_AI_PROVIDER=codex weld research spec.md
```

**Pros**: Scriptable, persistent across sessions
**Cons**: Three levels of precedence to document (flag > env > config)

**Recommendation**: Consider for Phase 5 (post-MVP).

---

## 5. Implementation Recommendations

### 5.1 Recommended Implementation Order

The specification's phased approach is sound. Minor adjustments:

1. **Phase 0 (prep)**: Run Codex CLI prototype experiments to answer open questions
2. **Phase 1 (codex service)**: As specified, but include prototype learnings
3. **Phase 2 (abstraction)**: Add `TaskType` enum to `config.py` in this phase
4. **Phase 3 (CLI flag)**: As specified
5. **Phase 4 (commands)**: Migrate one command fully, then parallelize the rest

### 5.2 Critical Files Reference

| File | Lines of Interest | What to Check |
|------|-------------------|---------------|
| `src/weld/services/claude.py` | 1-150 | Pattern for `run_codex()` |
| `src/weld/cli.py` | 31-82 | Pattern for `--ai` flag |
| `src/weld/output.py` | 23-35 | Pattern for `ai_override` field |
| `src/weld/config.py` | 38-79 | `CodexConfig`, `TaskModelsConfig` |
| `src/weld/commands/research.py` | 90-120 | First command to migrate |
| `tests/test_claude.py` | 1-100 | Pattern for `test_codex_service.py` |

### 5.3 Testing Strategy Refinements

**Unit test approach** (from `tests/test_claude.py`):
```python
def test_successful_execution(self) -> None:
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Codex response here"
    mock_result.stderr = ""

    with patch("weld.services.codex.subprocess.run", return_value=mock_result) as mock_run:
        result = run_codex("test prompt")

    assert result == "Codex response here"
```

**CLI test approach** (from `tests/test_cli.py`):
```python
def test_ai_flag_accepted(self, runner: CliRunner) -> None:
    """--ai flag should be accepted with valid values."""
    result = runner.invoke(app, ["--ai", "claude", "--help"])
    assert result.exit_code == 0

def test_ai_flag_invalid_rejected(self, runner: CliRunner) -> None:
    """--ai flag should reject invalid values."""
    result = runner.invoke(app, ["--ai", "gpt4", "--help"])
    assert result.exit_code != 0
    assert "Invalid" in result.stdout or "gpt4" in result.stdout
```

---

## 6. Codex CLI Details (From Research)

Based on web research of the Codex CLI documentation:

### 6.1 Key Flags

| Flag | Values | Purpose |
|------|--------|---------|
| `--sandbox, -s` | `read-only`, `workspace-write`, `danger-full-access` | Sandbox policy |
| `--model, -m` | Model ID string | Override configured model |
| `--json`, `--experimental-json` | Boolean | Newline-delimited JSON output |
| `--output-last-message, -o` | File path | Write final message to file |
| `--ask-for-approval, -a` | `untrusted`, `on-failure`, `on-request`, `never` | Approval control |

### 6.2 Non-Interactive Execution

For weld's use case, the `codex exec` subcommand is the correct entry point:

```bash
echo "prompt" | codex exec --json --sandbox read-only -
```

**Key difference from Claude**: Codex uses `codex exec` subcommand, while Claude uses `claude` directly.

### 6.3 Mapping to run_codex() Parameters

| Parameter | Claude Equivalent | Codex Flag |
|-----------|-------------------|------------|
| `prompt` | stdin | stdin |
| `exec_path` | `claude` | `codex exec` |
| `model` | `--model` | `--model, -m` |
| `stream` | `--output-format stream-json` | `--json` (partial) |
| `sandbox` | N/A | `--sandbox` |
| `cwd` | `-` | `-` (process cwd) |
| `timeout` | subprocess timeout | subprocess timeout |

---

## 7. Answers to Specification's Open Questions

### Q1: Codex Output Format

**Answer**: Codex uses `--json` or `--experimental-json` for "newline-delimited JSON events". The exact structure needs prototype validation, but it differs from Claude's `stream-json` format.

### Q2: Interactive Mode

**Answer**: Codex supports session resumption via `codex exec resume [SESSION_ID]` with `--last` flag for continuing the most recent conversation. This differs significantly from Claude's interactive approach and should be deferred to a future phase.

### Q3: Streaming Format

**Answer**: Based on documentation, `--json` outputs newline-delimited JSON. The exact event structure is undocumented and requires prototype testing. Unlike Claude's semantic events (`assistant`, `tool_use`), Codex may use different event types.

### Q4: Sandbox Modes

**Answer**: Valid sandbox values are:
- `read-only` (default) - Safe for research/planning tasks
- `workspace-write` - Allows writing to workspace
- `danger-full-access` - No restrictions (equivalent to Claude's `--dangerously-skip-permissions`)

### Q5: Model Names

**Answer**: Model selection uses `--model, -m` flag with model ID strings. The documentation mentions "gpt-5-codex" as an example. Valid model IDs depend on OpenAI's current offerings and may change over time. The `--oss` flag activates local open-source models.

---

## 8. Summary

The specification is well-designed and follows existing patterns. Key actions before implementation:

1. **Run Codex CLI prototype** to validate JSON output format assumptions
2. **Define `TaskType` enum** in `config.py`
3. **Create `AIProviderError` base class** for unified error handling
4. **Start with `research.py` migration** as the simplest command

The phased approach minimizes risk, and all extension points are clearly identified. The main uncertainty is Codex's streaming JSON format, which must be resolved through prototype testing before Phase 1 is complete.
