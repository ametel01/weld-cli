I'll explore the codebase to understand the existing patterns and ground the implementation plan in concrete code locations.
Now let me also examine a command file to understand how commands currently use Claude, and look at the constants file and service exports.
Let me also look at the test patterns for Claude service and the CLI to understand the testing approach.
Now I have a comprehensive understanding of the codebase. Let me create the implementation plan.

`★ Insight ─────────────────────────────────────`
The weld-cli codebase has an excellent foundation for the `--ai` flag implementation:
1. **TaskType enum already exists** at `config.py:14-40` with all task types defined
2. **get_task_model() already implemented** at `config.py:224-246` - returns provider-aware ModelConfig
3. **Commands don't use the abstraction** - they directly call `run_claude()` instead of using `config.get_task_model()`
4. The main gap is: no `run_codex()` service and no unified `run_ai()` abstraction that commands can call
`─────────────────────────────────────────────────`

## Phase 1: Codex Service Implementation

Create the Codex CLI service following the established Claude service pattern.

### Phase Validation
```bash
.venv/bin/pytest tests/test_codex.py -v
```

### Step 1: Create CodexError exception class and constants

#### Goal
Define the Codex-specific error class and import CODEX_TIMEOUT constant to mirror Claude service structure.

#### Files
- `src/weld/services/codex.py` - Create new file with CodexError class and module docstring

#### Validation
```bash
.venv/bin/python -c "from weld.services.codex import CodexError; print('OK')"
```

#### Failure modes
- Import path incorrect if file not placed in services/

---

### Step 2: Implement run_codex non-streaming function

#### Goal
Create the core `run_codex()` function that executes Codex CLI with prompt via stdin, handling timeout, model selection, and sandbox flags.

#### Files
- `src/weld/services/codex.py` - Add run_codex function with parameters: prompt, exec_path, model, cwd, timeout, sandbox

#### Validation
```bash
.venv/bin/python -c "from weld.services.codex import run_codex; import inspect; sig = inspect.signature(run_codex); assert 'prompt' in sig.parameters; print('OK')"
```

#### Failure modes
- Missing subprocess timeout parameter causes hanging
- Incorrect sandbox flag mapping to Codex CLI

---

### Step 3: Add streaming support to run_codex

#### Goal
Implement streaming output parsing for Codex's JSON format, following Claude's `_run_streaming()` pattern but with Codex-specific JSON parsing.

#### Files
- `src/weld/services/codex.py` - Add _extract_text_from_codex_json helper and stream parameter to run_codex

#### Validation
```bash
.venv/bin/python -c "from weld.services.codex import _extract_text_from_codex_json; print('OK')"
```

#### Failure modes
- Codex JSON format differs from expectations; requires prototype validation
- Streaming buffer handling edge cases with partial JSON

---

### Step 4: Export Codex service from services package

#### Goal
Add CodexError and run_codex to the services package exports for use by other modules.

#### Files
- `src/weld/services/__init__.py` - Add imports and __all__ entries for CodexError, run_codex

#### Validation
```bash
.venv/bin/python -c "from weld.services import CodexError, run_codex; print('OK')"
```

#### Failure modes
- Circular import if codex.py imports from __init__.py

---

### Step 5: Create unit tests for Codex service

#### Goal
Create comprehensive unit tests for run_codex mirroring test_claude.py patterns with mocked subprocess.

#### Files
- `tests/test_codex.py` - Create test file with TestRunCodex class covering success, timeout, errors, sandbox flags

#### Validation
```bash
.venv/bin/pytest tests/test_codex.py -v --tb=short
```

#### Failure modes
- Mock structure doesn't match actual subprocess behavior

---

## Phase 2: AI Provider Abstraction Layer

Create a unified abstraction layer that routes to the appropriate provider based on configuration.

### Phase Validation
```bash
.venv/bin/pytest tests/test_ai_provider.py -v
```

### Step 1: Create AIProviderError base exception

#### Goal
Define a common base exception class that both ClaudeError and CodexError can optionally inherit from, enabling unified error handling in commands.

#### Files
- `src/weld/services/ai_provider.py` - Create new file with AIProviderError class

#### Validation
```bash
.venv/bin/python -c "from weld.services.ai_provider import AIProviderError; print('OK')"
```

#### Failure modes
- Conflicting with existing exception hierarchies

---

### Step 2: Create AIProvider enum

#### Goal
Define an enum for supported AI providers (claude, codex) to use in provider selection logic.

#### Files
- `src/weld/services/ai_provider.py` - Add AIProvider enum with CLAUDE, CODEX values

#### Validation
```bash
.venv/bin/python -c "from weld.services.ai_provider import AIProvider; assert AIProvider.CLAUDE.value == 'claude'; print('OK')"
```

#### Failure modes
- Enum values don't match config provider strings

---

### Step 3: Implement run_ai dispatcher function

#### Goal
Create `run_ai()` function that takes TaskType, prompt, config, and optional provider override, then dispatches to the appropriate provider service.

#### Files
- `src/weld/services/ai_provider.py` - Add run_ai function that resolves provider from config or override and calls run_claude/run_codex

#### Validation
```bash
.venv/bin/python -c "from weld.services.ai_provider import run_ai; import inspect; sig = inspect.signature(run_ai); assert 'task' in sig.parameters; print('OK')"
```

#### Failure modes
- Provider resolution logic doesn't match config.get_task_model() behavior
- Missing parameter passthrough for stream, timeout, etc.

---

### Step 4: Export AI provider abstraction from services

#### Goal
Export AIProviderError, AIProvider, and run_ai from the services package.

#### Files
- `src/weld/services/__init__.py` - Add imports and __all__ entries for ai_provider exports

#### Validation
```bash
.venv/bin/python -c "from weld.services import AIProviderError, AIProvider, run_ai; print('OK')"
```

#### Failure modes
- Import order issues with circular dependencies

---

### Step 5: Create unit tests for AI provider abstraction

#### Goal
Test run_ai provider resolution logic, override behavior, and error propagation.

#### Files
- `tests/test_ai_provider.py` - Create test file covering provider dispatch, config resolution, override handling

#### Validation
```bash
.venv/bin/pytest tests/test_ai_provider.py -v --tb=short
```

#### Failure modes
- Mock structure doesn't correctly simulate provider services

---

## Phase 3: CLI --ai Flag Implementation

Add the global --ai flag to the CLI entry point.

### Phase Validation
```bash
.venv/bin/pytest tests/test_cli.py -v -k "ai"
```

### Step 1: Add ai_override field to OutputContext

#### Goal
Extend OutputContext dataclass to store the --ai flag value for access by commands.

#### Files
- `src/weld/output.py` - Add ai_override: str | None = None field to OutputContext

#### Validation
```bash
.venv/bin/python -c "from weld.output import OutputContext; from rich.console import Console; ctx = OutputContext(Console(), ai_override='codex'); assert ctx.ai_override == 'codex'; print('OK')"
```

#### Failure modes
- Field name conflicts with existing attributes

---

### Step 2: Add --ai option to CLI main callback

#### Goal
Add the --ai global option to cli.py main() callback with validation for allowed values (claude, codex).

#### Files
- `src/weld/cli.py` - Add ai_provider parameter with typer.Option and pass to OutputContext

#### Validation
```bash
.venv/bin/python -m weld --ai claude --help
```

#### Failure modes
- Typer callback validation doesn't trigger on invalid values
- Option not propagated to OutputContext correctly

---

### Step 3: Create CLI tests for --ai flag

#### Goal
Add tests verifying --ai flag acceptance and validation.

#### Files
- `tests/test_cli.py` - Add TestAIFlag class with tests for valid values, invalid rejection

#### Validation
```bash
.venv/bin/pytest tests/test_cli.py::TestAIFlag -v
```

#### Failure modes
- Exit codes differ from expectations for invalid values

---

## Phase 4: Migrate Research Command

Update the research command to use the AI provider abstraction as a reference implementation.

### Phase Validation
```bash
.venv/bin/pytest tests/test_research.py -v && make typecheck
```

### Step 1: Update research command imports

#### Goal
Import run_ai and TaskType in research.py to prepare for provider abstraction usage.

#### Files
- `src/weld/commands/research.py` - Add imports for run_ai, TaskType, AIProviderError, get_output_context

#### Validation
```bash
.venv/bin/python -c "from weld.commands.research import research; print('OK')"
```

#### Failure modes
- Circular import issues

---

### Step 2: Replace run_claude with run_ai in research command

#### Goal
Change the research command to use run_ai() with TaskType.RESEARCH, passing the ai_override from OutputContext.

#### Files
- `src/weld/commands/research.py` - Replace run_claude call with run_ai call, update error handling to catch AIProviderError

#### Validation
```bash
.venv/bin/python -m weld research --dry-run specs/test.md 2>&1 | grep -q "Would research" && echo "OK"
```

#### Failure modes
- Missing parameter mapping between run_claude and run_ai signatures
- AIProviderError not caught properly

---

### Step 3: Update dry-run output to show provider

#### Goal
When --dry-run is active, show which AI provider would be used based on config and --ai override.

#### Files
- `src/weld/commands/research.py` - Add provider indicator to dry-run output

#### Validation
```bash
.venv/bin/python -m weld --ai codex research --dry-run specs/test.md 2>&1 | grep -qi "codex" && echo "OK"
```

#### Failure modes
- Output formatting issues in JSON mode

---

### Step 4: Add/update research command tests

#### Goal
Update research command tests to verify provider abstraction is used correctly.

#### Files
- `tests/test_research.py` - Add tests for --ai override, verify run_ai is called instead of run_claude

#### Validation
```bash
.venv/bin/pytest tests/test_research.py -v --tb=short
```

#### Failure modes
- Mock patching targets wrong function after refactor

---

## Phase 5: Migrate Remaining Commands

Update all other commands that use run_claude to use the AI provider abstraction.

### Phase Validation
```bash
make test && make typecheck
```

### Step 1: Migrate discover command

#### Goal
Update discover command to use run_ai with TaskType.DISCOVER.

#### Files
- `src/weld/commands/discover.py` - Replace run_claude with run_ai, update imports and error handling

#### Validation
```bash
.venv/bin/python -c "from weld.commands.discover import discover_app; print('OK')"
```

#### Failure modes
- Command-specific parameters not mapped correctly

---

### Step 2: Migrate interview command

#### Goal
Update interview command to use run_ai with TaskType.INTERVIEW.

#### Files
- `src/weld/commands/interview.py` - Replace run_claude with run_ai, update imports and error handling

#### Validation
```bash
.venv/bin/python -c "from weld.commands.interview import interview_app; print('OK')"
```

#### Failure modes
- Interactive mode may require special handling

---

### Step 3: Migrate plan command

#### Goal
Update plan command to use run_ai with TaskType.PLAN_GENERATION.

#### Files
- `src/weld/commands/plan.py` - Replace run_claude with run_ai, update imports and error handling

#### Validation
```bash
.venv/bin/python -c "from weld.commands.plan import plan; print('OK')"
```

#### Failure modes
- Multiple AI calls in plan may need different task types

---

### Step 4: Migrate implement command

#### Goal
Update implement command to use run_ai with TaskType.IMPLEMENTATION.

#### Files
- `src/weld/commands/implement.py` - Replace run_claude/run_claude_interactive with run_ai, update imports

#### Validation
```bash
.venv/bin/python -c "from weld.commands.implement import implement; print('OK')"
```

#### Failure modes
- Interactive mode for implement requires special handling with run_ai_interactive

---

### Step 5: Migrate doc_review command

#### Goal
Update doc_review command to use run_ai with TaskType.DOC_REVIEW.

#### Files
- `src/weld/commands/doc_review.py` - Replace run_claude with run_ai, update imports and error handling

#### Validation
```bash
.venv/bin/python -c "from weld.commands.doc_review import doc_review; print('OK')"
```

#### Failure modes
- Review loop logic may need multiple task types

---

### Step 6: Run full test suite and typecheck

#### Goal
Verify all migrations are complete and no regressions introduced.

#### Files
- No new files; validation of existing changes

#### Validation
```bash
make check && make test
```

#### Failure modes
- Type errors from signature changes
- Broken tests from mock path changes

---

## Phase 6: Documentation and Finalization

Update documentation and ensure backwards compatibility.

### Phase Validation
```bash
make ci
```

### Step 1: Update CLAUDE.md with --ai flag documentation

#### Goal
Document the new --ai flag usage and provider configuration in project documentation.

#### Files
- `CLAUDE.md` - Add section describing --ai flag usage and provider selection

#### Validation
```bash
grep -q "\-\-ai" CLAUDE.md && echo "OK"
```

#### Failure modes
- Documentation doesn't match actual behavior

---

### Step 2: Update config template with provider examples

#### Goal
Enhance the config.toml template comments to explain task_models provider configuration.

#### Files
- `src/weld/config.py` - Update write_config_template to include clearer provider documentation

#### Validation
```bash
.venv/bin/python -c "from weld.config import write_config_template; from pathlib import Path; import tempfile; d = Path(tempfile.mkdtemp()); write_config_template(d); print((d/'config.toml').read_text())" | grep -q "provider" && echo "OK"
```

#### Failure modes
- Template changes break existing config parsing

---

### Step 3: Add run_ai_interactive for interactive commands

#### Goal
Create run_ai_interactive variant that dispatches to run_claude_interactive or equivalent for interactive sessions.

#### Files
- `src/weld/services/ai_provider.py` - Add run_ai_interactive function

#### Validation
```bash
.venv/bin/python -c "from weld.services.ai_provider import run_ai_interactive; print('OK')"
```

#### Failure modes
- Codex may not support equivalent interactive mode

---

### Step 4: Final integration test

#### Goal
Run full CI pipeline to verify all changes work together.

#### Files
- No new files; validation only

#### Validation
```bash
make ci
```

#### Failure modes
- CI failures from cumulative changes

---
