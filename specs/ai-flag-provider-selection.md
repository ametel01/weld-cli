# Specification: --ai Flag for AI Provider Selection

## Overview

Add a global `--ai` flag to the weld CLI that allows users to override the AI provider (claude or codex) at runtime. This flag overrides the provider settings in `.weld/config.toml` for the current invocation.

## Current State

### Configuration Model (exists)

The config system already supports provider selection per task via `TaskModelsConfig`:

```python
# src/weld/config.py
class ModelConfig(BaseModel):
    provider: str = "codex"  # codex, claude, etc.
    model: str | None = None
    exec: str | None = None

class TaskModelsConfig(BaseModel):
    discover: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    research: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    plan_generation: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    # ... etc
```

Provider defaults exist:
- `CodexConfig`: exec="codex", sandbox="read-only", model=None
- `ClaudeConfig`: exec="claude", model=None, timeout=1800, max_output_tokens=128000

### Gap: No Codex Service

**Critical**: There is no `services/codex.py` implementation. Only `services/claude.py` exists. Commands currently hardcode Claude usage regardless of `TaskModelsConfig`.

### Gap: Commands Ignore Task Models

Commands like `research.py`, `plan.py`, and `doc_review.py` directly use `run_claude()` without checking the task's configured provider:

```python
# src/weld/commands/plan.py:315-323
def _run() -> str:
    return run_claude(
        prompt=prompt,
        exec_path=claude_exec,  # Always claude!
        ...
    )
```

## Requirements

### 1. Global --ai Flag

Add `--ai` option to the main CLI callback in `src/weld/cli.py`:

```
weld --ai claude research spec.md
weld --ai codex plan spec.md
```

Constraints:
- Only `claude` and `codex` are valid values (for now)
- Flag overrides config file settings for the entire invocation
- Invalid values should error with helpful message

### 2. Codex Service Implementation

Create `src/weld/services/codex.py` with similar interface to `claude.py`:

```python
def run_codex(
    prompt: str,
    exec_path: str = "codex",
    model: str | None = None,
    cwd: Path | None = None,
    timeout: int | None = None,
    stream: bool = False,
    sandbox: str = "read-only",
) -> str:
    """Run Codex CLI with prompt and return output."""
```

Key differences from Claude:
- Uses `--sandbox` flag (default: "read-only")
- Different output format parsing
- No `--dangerously-skip-permissions` flag needed

### 3. Provider Abstraction Layer

Create `src/weld/services/ai_provider.py` to unify provider calls:

```python
from enum import Enum

class AIProvider(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"

def run_ai(
    provider: AIProvider,
    prompt: str,
    config: WeldConfig,
    task: TaskType,
    stream: bool = False,
    cwd: Path | None = None,
    skip_permissions: bool = False,
) -> str:
    """Run AI provider with appropriate settings."""
    model_config = config.get_task_model(task)

    if provider == AIProvider.CLAUDE:
        return run_claude(
            prompt=prompt,
            exec_path=model_config.exec or config.claude.exec,
            model=model_config.model,
            timeout=config.claude.timeout,
            stream=stream,
            cwd=cwd,
            skip_permissions=skip_permissions,
            max_output_tokens=config.claude.max_output_tokens,
        )
    elif provider == AIProvider.CODEX:
        return run_codex(
            prompt=prompt,
            exec_path=model_config.exec or config.codex.exec,
            model=model_config.model,
            stream=stream,
            cwd=cwd,
            sandbox=config.codex.sandbox,
        )
```

### 4. Runtime Override Mechanism

Store the `--ai` override in a context that commands can access:

```python
# src/weld/output.py (extend OutputContext)
@dataclass
class OutputContext:
    console: Console
    json_mode: bool = False
    dry_run: bool = False
    ai_override: str | None = None  # NEW: "claude" or "codex"
```

### 5. Update Commands to Use Provider Abstraction

Commands should use `run_ai()` instead of `run_claude()`:

```python
# src/weld/commands/research.py
from ..services import run_ai, AIProvider
from ..config import TaskType

def research(...):
    ctx = get_output_context()

    # Determine effective provider
    if ctx.ai_override:
        provider = AIProvider(ctx.ai_override)
    else:
        model_config = config.get_task_model(TaskType.RESEARCH)
        provider = AIProvider(model_config.provider)

    result = run_ai(
        provider=provider,
        prompt=prompt,
        config=config,
        task=TaskType.RESEARCH,
        stream=not quiet,
        cwd=repo_root,
    )
```

## Implementation Phases

### Phase 1: Codex Service

1. Create `src/weld/services/codex.py`
   - `CodexError` exception class
   - `run_codex()` function with streaming support
   - Parse codex output format (investigate actual format)

2. Export from `services/__init__.py`

3. Add unit tests in `tests/test_codex_service.py`

**Validation**: `codex --help` should work, mock tests pass

### Phase 2: Provider Abstraction

1. Create `src/weld/services/ai_provider.py`
   - `AIProvider` enum
   - `run_ai()` unified interface

2. Add `ai_override` field to `OutputContext`

3. Add unit tests for provider routing

**Validation**: Unit tests verify routing to correct provider

### Phase 3: Global --ai Flag

1. Add `--ai` option to `cli.py` main callback
   - Validate against allowed values ("claude", "codex")
   - Store in `OutputContext.ai_override`
   - Use `click.Choice` for autocompletion

2. Add CLI tests for flag parsing

**Validation**: `weld --ai codex --help` works, invalid values error

### Phase 4: Update Commands

Update each command to use `run_ai()` with provider resolution:

1. `commands/research.py` - TaskType.RESEARCH
2. `commands/plan.py` - TaskType.PLAN_GENERATION
3. `commands/doc_review.py` - TaskType.DOC_REVIEW / CODE_REVIEW
4. `commands/discover.py` - TaskType.DISCOVER
5. `commands/interview.py` - TaskType.INTERVIEW
6. `commands/implement.py` - TaskType.IMPLEMENTATION

**Validation**: Each command respects `--ai` flag and config

## Edge Cases

### No Codex Installed
```
$ weld --ai codex research spec.md
Error: Codex executable not found: codex
       Install from: https://github.com/openai/codex
```

### Invalid Provider
```
$ weld --ai gpt4 research spec.md
Error: Invalid AI provider 'gpt4'. Valid options: claude, codex
```

### Config + Flag Interaction
- `--ai` flag always wins over config
- If `--ai` not specified, use `task_models.<task>.provider` from config
- If task not in config, use default (claude for most tasks)

## Testing Strategy

### Unit Tests
- `test_codex_service.py`: Mock subprocess, test output parsing
- `test_ai_provider.py`: Test routing logic
- `test_cli_ai_flag.py`: Test flag parsing and validation

### Integration Tests (marked @pytest.mark.cli)
- Test actual codex execution (if installed)
- Test fallback when codex not installed
- Test config override behavior

### Test Fixtures
```python
@pytest.fixture
def mock_codex(mocker):
    """Mock codex subprocess calls."""
    return mocker.patch("weld.services.codex.subprocess.run", ...)
```

## Files to Create/Modify

### New Files
- `src/weld/services/codex.py`
- `src/weld/services/ai_provider.py`
- `tests/test_codex_service.py`
- `tests/test_ai_provider.py`

### Modified Files
- `src/weld/cli.py` - Add `--ai` global option
- `src/weld/output.py` - Add `ai_override` field
- `src/weld/services/__init__.py` - Export new modules
- `src/weld/commands/research.py` - Use `run_ai()`
- `src/weld/commands/plan.py` - Use `run_ai()`
- `src/weld/commands/doc_review.py` - Use `run_ai()`
- `src/weld/commands/discover.py` - Use `run_ai()`
- `src/weld/commands/interview.py` - Use `run_ai()`
- `src/weld/commands/implement.py` - Use `run_ai()`

## Open Questions

1. **Codex Output Format**: What format does `codex` CLI output? Need to test:
   ```bash
   codex --help
   codex --output-format ?
   ```

2. **Interactive Mode**: Does codex support interactive mode like Claude's `run_claude_interactive()`?

3. **Streaming**: What's codex's streaming format? Similar to Claude's `stream-json`?

4. **Sandbox Modes**: Document valid sandbox values for codex (read-only, full, none?)

5. **Model Names**: What are valid codex model names to pass via `--model`?

## Success Criteria

1. `weld --ai codex research spec.md` uses codex instead of claude
2. `weld --ai claude plan spec.md` uses claude (explicit)
3. Without `--ai`, config's `task_models.<task>.provider` is used
4. `weld doctor` validates both claude and codex availability
5. Error messages are helpful when provider not installed
6. All existing tests continue to pass
7. New tests cover provider routing and flag parsing
