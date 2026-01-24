I'll explore the codebase to understand the existing patterns and ground my plan in concrete code locations.
Now let me verify the exact TaskType enum values and look at how tests are structured for this project.
Let me also check the existing project structure for where new modules should be placed, and look at the test fixtures.
Now I have all the information needed to create a comprehensive implementation plan. Let me also verify the docs directory exists:
I have all the information needed. Here is the implementation plan:

`★ Insight ─────────────────────────────────────`
**Understanding Typer's Completion Architecture**
- Typer's `autocompletion` parameter on `typer.Argument()` and `typer.Option()` accepts a callable that returns completion suggestions
- The callable receives `incomplete: str` (what the user has typed so far) and optionally `ctx: typer.Context`
- Completion functions are invoked at shell time, so lazy imports are critical to avoid slow startup
`─────────────────────────────────────────────────`

## Phase 1: Create Completion Module **COMPLETE**

Create the core completion functions module with static completions for TaskType enum and export formats.

### Phase Validation
```bash
.venv/bin/python -c "from weld.completions import complete_task_type, complete_export_format; print('OK')"
```

### Step 1: Create completions.py with TaskType completion **COMPLETE**

#### Goal
Create the new `src/weld/completions.py` module with the `complete_task_type` function that returns matching TaskType enum values.

#### Files
- `src/weld/completions.py` - Create new module with `complete_task_type` function

#### Validation
```bash
.venv/bin/python -c "from weld.completions import complete_task_type; assert 'discover' in complete_task_type('disc'); print('OK')"
```

#### Failure modes
- Import error if weld.config module path is wrong
- Function returns empty list instead of matches

---

### Step 2: Add export format completion function **COMPLETE**

#### Goal
Add `complete_export_format` function that returns available export formats (toml, json, and yaml if pyyaml installed).

#### Files
- `src/weld/completions.py` - Add `complete_export_format` function

#### Validation
```bash
.venv/bin/python -c "from weld.completions import complete_export_format; r = complete_export_format(''); assert 'toml' in r and 'json' in r; print('OK')"
```

#### Failure modes
- Missing dependency check for yaml format
- Alphabetical sorting not applied

---

## Phase 2: Add Path-Based Completions **COMPLETE**

Implement markdown file and step/phase completion functions that follow user input paths.

### Phase Validation
```bash
.venv/bin/python -c "from weld.completions import complete_markdown_file, complete_step_number, complete_phase_number; print('OK')"
```

### Step 3: Add markdown file completion function **COMPLETE**

#### Goal
Create `complete_markdown_file` function that returns `.md` files following the user's typed path, with alphabetical ordering and 20-result cap.

#### Files
- `src/weld/completions.py` - Add `complete_markdown_file` function

#### Validation
```bash
.venv/bin/python -c "from weld.completions import complete_markdown_file; print('OK')"
```

#### Failure modes
- PermissionError not caught when accessing protected directories
- Subdirectory suggestions missing trailing slash
- Results exceed 20-item cap

---

### Step 4: Add step number completion function **COMPLETE**

#### Goal
Create `complete_step_number` function that returns static step numbers 1.1-3.3 as fallback suggestions.

#### Files
- `src/weld/completions.py` - Add `complete_step_number` function

#### Validation
```bash
.venv/bin/python -c "from weld.completions import complete_step_number; r = complete_step_number('1'); assert '1.1' in r; print('OK')"
```

#### Failure modes
- Wrong step number format (should be "1.1" not "1-1")

---

### Step 5: Add phase number completion function **COMPLETE**

#### Goal
Create `complete_phase_number` function that returns static phase numbers 1-5 as suggestions.

#### Files
- `src/weld/completions.py` - Add `complete_phase_number` function

#### Validation
```bash
.venv/bin/python -c "from weld.completions import complete_phase_number; r = complete_phase_number(''); assert '1' in r; print('OK')"
```

#### Failure modes
- Returns strings instead of matching phase prefix filter

---

## Phase 3: Wire Completions to Command Arguments

Connect completion functions to the appropriate Typer arguments and options in command modules.

### Phase Validation
```bash
make check
```

### Step 6: Add completion to implement command plan_file argument **COMPLETE**

#### Goal
Add `autocompletion=complete_markdown_file` to the `plan_file` argument in `src/weld/commands/implement.py`.

#### Files
- `src/weld/commands/implement.py` - Import `complete_markdown_file` and add autocompletion parameter at line ~85

#### Validation
```bash
.venv/bin/python -c "from weld.commands.implement import implement; print('OK')"
```

#### Failure modes
- Circular import if completions module imports from commands
- Typer version incompatibility with autocompletion parameter

---

### Step 7: Add completion to implement command --step option **COMPLETE**

#### Goal
Add `autocompletion=complete_step_number` to the `--step` option in `src/weld/commands/implement.py`.

#### Files
- `src/weld/commands/implement.py` - Import `complete_step_number` and add autocompletion parameter at line ~92

#### Validation
```bash
.venv/bin/python -c "from weld.commands.implement import implement; print('OK')"
```

#### Failure modes
- Wrong parameter name (should be autocompletion not shell_complete)

---

### Step 8: Add completion to implement command --phase option

#### Goal
Add `autocompletion=complete_phase_number` to the `--phase` option in `src/weld/commands/implement.py`.

#### Files
- `src/weld/commands/implement.py` - Import `complete_phase_number` and add autocompletion parameter at line ~100

#### Validation
```bash
.venv/bin/python -c "from weld.commands.implement import implement; print('OK')"
```

#### Failure modes
- Type mismatch (phase is int but completions return strings)

---

### Step 9: Add completion to prompt show command task argument

#### Goal
Add `autocompletion=complete_task_type` to the `task` argument in `src/weld/commands/prompt.py` show_prompt function.

#### Files
- `src/weld/commands/prompt.py` - Import `complete_task_type` and add autocompletion parameter at line ~255

#### Validation
```bash
.venv/bin/python -c "from weld.commands.prompt import show_prompt; print('OK')"
```

#### Failure modes
- Import at top of file causes slow CLI startup

---

### Step 10: Add completion to prompt export command --format option

#### Goal
Add `autocompletion=complete_export_format` to the `--format` option in `src/weld/commands/prompt.py` export_prompts function.

#### Files
- `src/weld/commands/prompt.py` - Import `complete_export_format` and add autocompletion parameter at line ~405

#### Validation
```bash
.venv/bin/python -c "from weld.commands.prompt import export_prompts; print('OK')"
```

#### Failure modes
- Format validation rejects completed value

---

### Step 11: Add completion to research command input_file argument

#### Goal
Add `autocompletion=complete_markdown_file` to the `input_file` argument in `src/weld/commands/research.py`.

#### Files
- `src/weld/commands/research.py` - Import `complete_markdown_file` and add autocompletion parameter

#### Validation
```bash
.venv/bin/python -c "from weld.commands.research import research; print('OK')"
```

#### Failure modes
- Argument name differs from plan_file

---

### Step 12: Add completion to plan command input_file argument

#### Goal
Add `autocompletion=complete_markdown_file` to the `input_file` argument in `src/weld/commands/plan.py`.

#### Files
- `src/weld/commands/plan.py` - Import `complete_markdown_file` and add autocompletion parameter

#### Validation
```bash
.venv/bin/python -c "from weld.commands.plan import plan; print('OK')"
```

#### Failure modes
- Argument name differs from other commands

---

### Step 13: Add completion to interview generate command file argument

#### Goal
Add `autocompletion=complete_markdown_file` to the `file` argument in `src/weld/commands/interview.py` generate function.

#### Files
- `src/weld/commands/interview.py` - Import `complete_markdown_file` and add autocompletion parameter

#### Validation
```bash
.venv/bin/python -c "from weld.commands.interview import generate; print('OK')"
```

#### Failure modes
- Sub-app registration interferes with completion

---

### Step 14: Add completion to interview apply command questionnaire argument

#### Goal
Add `autocompletion=complete_markdown_file` to the `questionnaire` argument in `src/weld/commands/interview.py` apply function.

#### Files
- `src/weld/commands/interview.py` - Import reused from Step 13, add autocompletion parameter

#### Validation
```bash
.venv/bin/python -c "from weld.commands.interview import apply; print('OK')"
```

#### Failure modes
- Duplicate import statement

---

## Phase 4: Unit Tests for Completion Functions

Add comprehensive unit tests for all completion functions with mocked filesystem access.

### Phase Validation
```bash
make test-unit
```

### Step 15: Create test file for completion functions

#### Goal
Create `tests/test_completions.py` with unit tests for `complete_task_type` and `complete_export_format` functions.

#### Files
- `tests/test_completions.py` - Create new test file with tests for static completion functions

#### Validation
```bash
.venv/bin/pytest tests/test_completions.py -v -k "task_type or export_format"
```

#### Failure modes
- Missing pytest.mark.unit decorator
- Test imports break due to path issues

---

### Step 16: Add tests for markdown file completion

#### Goal
Add tests for `complete_markdown_file` function with mocked `pathlib.Path.glob` to verify path-following behavior, prefix filtering, and 20-result cap.

#### Files
- `tests/test_completions.py` - Add TestMarkdownFileCompletion class with mocked tests

#### Validation
```bash
.venv/bin/pytest tests/test_completions.py -v -k "markdown"
```

#### Failure modes
- Mock setup incorrect for Path.glob
- Permission error handling not tested

---

### Step 17: Add tests for step and phase completion

#### Goal
Add tests for `complete_step_number` and `complete_phase_number` functions verifying static fallback values and prefix filtering.

#### Files
- `tests/test_completions.py` - Add tests for step and phase completion functions

#### Validation
```bash
.venv/bin/pytest tests/test_completions.py -v -k "step or phase"
```

#### Failure modes
- Wrong expected values for step format

---

## Phase 5: CLI Integration Tests

Add integration tests verifying completion infrastructure is available in the CLI.

### Phase Validation
```bash
make test-cli
```

### Step 18: Add CLI test for --install-completion flag

#### Goal
Add test in `tests/test_cli.py` verifying that `weld --help` shows `--install-completion` option.

#### Files
- `tests/test_cli.py` - Add test in TestHelpCommand class for completion flag visibility

#### Validation
```bash
.venv/bin/pytest tests/test_cli.py -v -k "completion"
```

#### Failure modes
- Flag not shown in help output (Typer version issue)

---

## Phase 6: Documentation

Create comprehensive shell completion documentation for users.

### Phase Validation
```bash
test -f docs/shell-completion.md && echo "OK"
```

### Step 19: Create shell completion documentation

#### Goal
Create `docs/shell-completion.md` with installation instructions for bash, zsh, fish, and PowerShell, plus troubleshooting section.

#### Files
- `docs/shell-completion.md` - Create new documentation file with multi-shell installation guide

#### Validation
```bash
grep -q "install-completion" docs/shell-completion.md && echo "OK"
```

#### Failure modes
- Shell-specific instructions incorrect
- Missing troubleshooting for common issues

---

### Step 20: Update installation documentation with completion reference

#### Goal
Add a brief mention of shell completion with link to `shell-completion.md` in `docs/installation.md`.

#### Files
- `docs/installation.md` - Add section referencing shell completion documentation

#### Validation
```bash
grep -q "shell-completion" docs/installation.md && echo "OK"
```

#### Failure modes
- Link path incorrect for mkdocs

---
