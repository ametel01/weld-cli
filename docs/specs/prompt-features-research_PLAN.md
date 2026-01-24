1. **TranscriptsConfig** is at line 106, NOT 114 as stated
2. **WeldConfig** prompts field doesn't exist - line 155 shows transcripts, NOT prompts
3. The `prompt_customizer.py` module does NOT exist
4. The `commands/prompt.py` does NOT exist
5. No `prompt_app` is registered in cli.py
6. The prompt generators are in their respective modules (not just some inline):
   - `generate_discover_prompt` in `core/discover_engine.py`
   - `generate_research_prompt` inline in `commands/research.py`
   - `generate_plan_prompt` inline in `commands/plan.py`
   - `generate_interview_prompt` in `core/interview_engine.py`
   - `generate_code_review_prompt` and `generate_doc_review_prompt` in `core/doc_review_engine.py`
7. The step prompt in implement is at line 837-866, NOT "around line 866"

Let me also verify a few more details about the implement command and config.py line numbers.
The write_config_template is at line 275 as stated. Now I can produce the corrected document.

## Phase 1: Configuration Infrastructure **COMPLETE**

Add prompt customization configuration models to support per-task prefix/suffix and default focus.

### Phase Validation
```bash
.venv/bin/pytest tests/test_config.py -v && .venv/bin/python -c "from weld.config import PromptsConfig, PromptCustomization; print('OK')"
```

### Step 1: Create PromptCustomization model **COMPLETE**

#### Goal
Define the Pydantic model for individual prompt customizations with prefix, suffix, and default_focus fields.

#### Files
- `src/weld/config.py` - Add PromptCustomization class after TranscriptsConfig (around line 115)

#### Validation
```bash
.venv/bin/python -c "from weld.config import PromptCustomization; c = PromptCustomization(prefix='test'); print(c.prefix)"
```

#### Failure modes
- Import conflicts with existing classes
- Pydantic validation errors on default values

---

### Step 2: Create PromptsConfig model **COMPLETE**

#### Goal
Define the container config for all prompt customizations with global and per-task settings.

#### Files
- `src/weld/config.py` - Add PromptsConfig class after PromptCustomization

#### Validation
```bash
.venv/bin/python -c "from weld.config import PromptsConfig; p = PromptsConfig(); print(p.discover.prefix)"
```

#### Failure modes
- Field naming inconsistency with TaskType enum values
- Circular reference between nested models

---

### Step 3: Integrate PromptsConfig into WeldConfig **COMPLETE**

#### Goal
Add prompts field to WeldConfig using the established Field(default_factory=...) pattern.

#### Files
- `src/weld/config.py` - Add prompts field to WeldConfig class (around line 156)

#### Validation
```bash
.venv/bin/python -c "from weld.config import WeldConfig; c = WeldConfig(); print(c.prompts.global_prefix)"
```

#### Failure modes
- WeldConfig instantiation failures
- Default factory not properly initialized

---

### Step 4: Update config template with prompts section **COMPLETE**

#### Goal
Add commented prompts section to write_config_template so new weld init includes prompt customization examples.

#### Files
- `src/weld/config.py` - Update write_config_template function (around line 275)

#### Validation
```bash
.venv/bin/python -c "from weld.config import write_config_template; from pathlib import Path; import tempfile; d = Path(tempfile.mkdtemp()); write_config_template(d); print(open(d/'config.toml').read())" | grep -q "prompts" && echo "OK"
```

#### Failure modes
- TOML syntax errors in template string
- Missing closing quotes on multi-line strings

---

### Step 5: Add unit tests for prompt config models **COMPLETE**

#### Goal
Verify PromptCustomization, PromptsConfig, and WeldConfig integration work correctly with defaults and custom values.

#### Files
- `tests/test_config.py` - Add test functions for new config models

#### Validation
```bash
.venv/bin/pytest tests/test_config.py::test_prompt_customization_defaults tests/test_config.py::test_prompts_config_defaults tests/test_config.py::test_weld_config_includes_prompts -v
```

#### Failure modes
- Test assertions fail due to unexpected defaults
- Import errors in test file

---

## Phase 2: Prompt Customizer Core Module **COMPLETE**

Create the core utility for applying prompt customizations with proper ordering and default focus handling.

### Phase Validation
```bash
.venv/bin/pytest tests/test_prompt_customizer.py -v && make typecheck
```

### Step 1: Create prompt_customizer module structure **COMPLETE**

#### Goal
Create the prompt_customizer.py module in core/ with apply_customization and get_default_focus functions.

#### Files
- `src/weld/core/prompt_customizer.py` - Create new module with two main functions

#### Validation
```bash
.venv/bin/python -c "from weld.core.prompt_customizer import apply_customization, get_default_focus; print('OK')"
```

#### Failure modes
- Module path not found
- Import errors from config module

---

### Step 2: Implement apply_customization function **COMPLETE**

#### Goal
Implement function that applies global_prefix → task_prefix → prompt → task_suffix → global_suffix ordering.

#### Files
- `src/weld/core/prompt_customizer.py` - Implement apply_customization with proper ordering

#### Validation
```bash
.venv/bin/python -c "
from weld.config import WeldConfig, PromptsConfig, PromptCustomization
from weld.core.prompt_customizer import apply_customization
config = WeldConfig(prompts=PromptsConfig(global_prefix='GLOBAL:', discover=PromptCustomization(prefix='DISC:')))
result = apply_customization('BASE', 'discover', config)
assert 'GLOBAL:' in result and 'DISC:' in result and 'BASE' in result
print('OK')
"
```

#### Failure modes
- Incorrect ordering of prefix/suffix application
- None values not handled gracefully

---

### Step 3: Implement get_default_focus function **COMPLETE**

#### Goal
Implement function that retrieves default focus from config for a given prompt type if explicit focus not provided.

#### Files
- `src/weld/core/prompt_customizer.py` - Implement get_default_focus function

#### Validation
```bash
.venv/bin/python -c "
from weld.config import WeldConfig, PromptsConfig, PromptCustomization
from weld.core.prompt_customizer import get_default_focus
config = WeldConfig(prompts=PromptsConfig(discover=PromptCustomization(default_focus='API')))
assert get_default_focus('discover', config, None) == 'API'
assert get_default_focus('discover', config, 'Override') == 'Override'
print('OK')
"
```

#### Failure modes
- Empty string not treated as valid override
- Unknown prompt type causes crash instead of returning None

---

### Step 4: Export functions from core/__init__.py **COMPLETE**

#### Goal
Add apply_customization and get_default_focus to core module exports.

#### Files
- `src/weld/core/__init__.py` - Add imports and __all__ entries for new functions

#### Validation
```bash
.venv/bin/python -c "from weld.core import apply_customization, get_default_focus; print('OK')"
```

#### Failure modes
- Circular import issues
- Missing from __all__ list

---

### Step 5: Add comprehensive unit tests for prompt customizer **COMPLETE**

#### Goal
Test all customization scenarios: global-only, task-only, combined, empty strings, default focus resolution.

#### Files
- `tests/test_prompt_customizer.py` - Create new test file with test cases

#### Validation
```bash
.venv/bin/pytest tests/test_prompt_customizer.py -v --tb=short
```

#### Failure modes
- Edge cases not covered
- Test isolation issues with shared config

---

## Phase 3: Prompt Viewer Command **COMPLETE**

Create the weld prompt command with list, show, and export subcommands for viewing prompt templates.

### Phase Validation
```bash
.venv/bin/pytest tests/test_prompt_command.py -v && .venv/bin/python -m weld prompt list
```

### Step 1: Create prompt command module structure **COMPLETE**

#### Goal
Create commands/prompt.py with Typer app and basic command structure for list, show, export.

#### Files
- `src/weld/commands/prompt.py` - Create new command module with Typer app

#### Validation
```bash
.venv/bin/python -c "from weld.commands.prompt import prompt_app; print('OK')"
```

#### Failure modes
- Typer configuration errors
- Missing imports

---

### Step 2: Implement prompt list command **COMPLETE**

#### Goal
Implement list subcommand that displays all available prompt types with descriptions.

#### Files
- `src/weld/commands/prompt.py` - Add list command implementation

#### Validation
```bash
.venv/bin/python -m weld prompt list | grep -q "discover" && echo "OK"
```

#### Failure modes
- Rich table formatting issues
- Missing prompt type descriptions

---

### Step 3: Implement prompt show command **COMPLETE**

#### Goal
Implement show subcommand that displays a specific prompt template with optional customization and focus.

#### Files
- `src/weld/commands/prompt.py` - Add show command with --raw and --focus options

#### Validation
```bash
.venv/bin/python -m weld prompt show discover --raw | head -5
```

#### Failure modes
- Unknown prompt type not handled gracefully
- Config loading fails outside weld project

---

### Step 4: Implement prompt export command **COMPLETE**

#### Goal
Implement export subcommand that writes all prompt templates to a specified directory.

#### Files
- `src/weld/commands/prompt.py` - Add export command implementation

#### Validation
```bash
TMP=$(mktemp -d) && .venv/bin/python -m weld prompt export "$TMP" --raw && ls "$TMP"/*.md | wc -l
```

#### Failure modes
- Directory creation failures
- File write permission errors

---

### Step 5: Register prompt command in CLI **COMPLETE**

#### Goal
Add prompt_app to cli.py using add_typer pattern.

#### Files
- `src/weld/cli.py` - Import prompt_app and register with app.add_typer

#### Validation
```bash
.venv/bin/python -m weld prompt --help
```

#### Failure modes
- Import error from prompt module
- Command name collision

---

### Step 6: Add unit tests for prompt command **COMPLETE**

#### Goal
Test list, show, and export commands with various options and edge cases.

#### Files
- `tests/test_prompt_command.py` - Create new test file

#### Validation
```bash
.venv/bin/pytest tests/test_prompt_command.py -v
```

#### Failure modes
- CLI runner test isolation issues
- File system test cleanup failures

---

## Phase 4: Integrate Customization into Commands **COMPLETE**

Apply prompt customization to all prompt-generating commands.

### Phase Validation
```bash
make test-unit && make check
```

### Step 1: Integrate customization into discover command **COMPLETE**

#### Goal
Apply customization to generate_discover_prompt result and use get_default_focus for focus parameter.

#### Files
- `src/weld/commands/discover.py` - Import and apply customization after prompt generation (around line 106)

#### Validation
```bash
.venv/bin/python -c "
# Verify import works
from weld.commands.discover import _run_discover
print('OK')
"
```

#### Failure modes
- Config not available at prompt generation time
- Customization applied before prompt generation

---

### Step 2: Integrate customization into research command **COMPLETE**

#### Goal
Apply customization to generate_research_prompt result and use get_default_focus.

#### Files
- `src/weld/commands/research.py` - Import and apply customization after prompt generation

#### Validation
```bash
grep -q "apply_customization" src/weld/commands/research.py && echo "OK"
```

#### Failure modes
- Focus parameter passed incorrectly to generator
- Customization not applied before prompt_only output

---

### Step 3: Integrate customization into plan command **COMPLETE**

#### Goal
Apply customization to generate_plan_prompt result. Note: plan does not support focus parameter.

#### Files
- `src/weld/commands/plan.py` - Import and apply customization after prompt generation

#### Validation
```bash
grep -q "apply_customization" src/weld/commands/plan.py && echo "OK"
```

#### Failure modes
- Plan prompt structure disrupted by prefix/suffix
- Customization applied at wrong location in code flow

---

### Step 4: Integrate customization into interview command **COMPLETE**

#### Goal
Apply customization to generate_interview_prompt result and use get_default_focus.

#### Files
- `src/weld/core/interview_engine.py` - Import and apply customization in run_interview_loop after prompt generation (around line 103)

#### Validation
```bash
grep -q "apply_customization\|get_default_focus" src/weld/core/interview_engine.py && echo "OK"
```

#### Failure modes
- Interview prompt printed to stdout without customization
- Config not accessible in core module

---

### Step 5: Integrate customization into review command **COMPLETE**

#### Goal
Apply customization to generate_doc_review_prompt and generate_code_review_prompt results.

#### Files
- `src/weld/commands/doc_review.py` - Import and apply customization for both doc and code review prompts

#### Validation
```bash
grep -q "apply_customization" src/weld/commands/doc_review.py && echo "OK"
```

#### Failure modes
- Wrong prompt type key used for code vs doc review
- Customization interferes with apply mode behavior

---

### Step 6: Integrate customization into implement command **COMPLETE**

#### Goal
Apply customization to the inline step prompt in _execute_step function.

#### Files
- `src/weld/commands/implement.py` - Import and apply customization to step prompt (around line 837)

#### Validation
```bash
grep -q "apply_customization" src/weld/commands/implement.py && echo "OK"
```

#### Failure modes
- Config not available in _execute_step context
- Step prompt format disrupted

---

### Step 7: Integrate customization into commit command **COMPLETE**

#### Goal
Apply customization to _generate_commit_prompt result.

#### Files
- `src/weld/commands/commit.py` - Import and apply customization after prompt generation

#### Validation
```bash
grep -q "apply_customization" src/weld/commands/commit.py && echo "OK"
```

#### Failure modes
- XML output structure disrupted by customization
- Commit parsing fails after customization applied

---

### Step 8: Add integration tests for customized prompts **COMPLETE**

#### Goal
Test that customizations are applied correctly when commands run with custom config.

#### Files
- `tests/test_prompt_customizer.py` - Add integration tests with mocked commands

#### Validation
```bash
.venv/bin/pytest tests/test_prompt_customizer.py -v -k integration
```

#### Failure modes
- Mock setup incomplete
- Config fixtures not properly isolated

---

## Phase 5: Documentation and Polish

Update documentation and ensure all quality checks pass.

### Phase Validation
```bash
make ci
```

### Step 1: Update CLAUDE.md with prompt commands **COMPLETE**

#### Goal
Document new weld prompt commands and prompts configuration section.

#### Files
- `CLAUDE.md` - Add prompt command documentation and config section

#### Validation
```bash
grep -q "weld prompt" CLAUDE.md && grep -q "\[prompts\]" CLAUDE.md && echo "OK"
```

#### Failure modes
- Documentation inconsistent with implementation
- Missing configuration examples

---

### Step 2: Update CHANGELOG.md with new features **COMPLETE**

#### Goal
Add entries for prompt personalization and prompt viewer features under [Unreleased].

#### Files
- `CHANGELOG.md` - Add entries under [Unreleased] section

#### Validation
```bash
grep -q "prompt personalization\|prompt viewer" CHANGELOG.md && echo "OK"
```

#### Failure modes
- Missing feature descriptions
- Incorrect changelog format

---

### Step 3: Run full test suite and fix any failures **COMPLETE**

#### Goal
Ensure all tests pass including new tests and existing regression tests.

#### Files
- Various test files as needed based on failures

#### Validation
```bash
make test
```

#### Failure modes
- Unexpected test regressions
- Coverage drops below 70%

---

### Step 4: Run linting and type checking **COMPLETE**

#### Goal
Ensure all code quality checks pass without errors.

#### Files
- Various source files as needed based on errors

#### Validation
```bash
make check
```

#### Failure modes
- Type errors in new code
- Linting violations

---
