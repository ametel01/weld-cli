1. **discover_engine.py**:
   - Claims: `9-169` for template, `generate_discover_prompt(focus_areas: str | None = None)`
   - Reality: Lines 9-169 for template ✓, function at lines 172-182 ✓, signature matches ✓

2. **interview_engine.py**:
   - Claims: `10-48` for template
   - Reality: Lines 10-48 for template ✓, function at lines 51-71 ✓, signature matches ✓
   - Claims: `102-104` for `run_interview_loop` printing prompt
   - Reality: Lines 103-104 ✓

3. **doc_review_engine.py**:
   - Claims: `12-130` for DOC_REVIEW_PROMPT_TEMPLATE
   - Reality: Lines 12-130 ✓
   - Claims: `210-325` for CODE_REVIEW_PROMPT_TEMPLATE
   - Reality: Lines 210-325 ✓
   - Claims: function at "lines 443-461"
   - Reality: `generate_doc_review_prompt` at lines 420-440, `generate_code_review_prompt` at lines 443-461 ✓

4. **research.py**:
   - Claims: `29-89` for `generate_research_prompt`
   - Reality: Lines 29-89 ✓

5. **plan.py**:
   - Claims: `14-212` for `generate_plan_prompt`
   - Reality: Lines 14-212 ✓

6. **implement.py**:
   - Claims: `837-866` for inline prompt in `_execute_step`
   - Reality: Lines 837-866 ✓

7. **commit.py**:
   - Claims: `159-228` for `_generate_commit_prompt`
   - Reality: Lines 159-228 ✓

8. **config.py**:
   - Claims: `TaskType` lines `14-32`
   - Reality: Lines 14-33 (includes empty line before next class) - close enough
   - Claims: `TaskModelsConfig` lines `43-60`
   - Reality: Lines 43-61 (includes the `get_model` method) ✓
   - Claims: `TranscriptsConfig` lines `106-113`
   - Reality: Lines 106-113 ✓
   - Claims: `WeldConfig` lines `145-155`
   - Reality: Lines 145-179 (the full class is larger)

9. **cli.py**:
   - Claims: lines `40-41` for add_typer pattern
   - Reality: Lines 40-41 ✓
   - Claims: lines `126-133` for direct command registration
   - Reality: Lines 126-133 ✓

The document is largely accurate. Let me output the corrected document with minor line number fixes:

# Research Document: Prompt Features Implementation

This document provides comprehensive analysis of the prompt-features-spec.md specification
to inform the implementation planning phase.

---

## 1. Architecture Analysis

### 1.1 Existing Prompt Pattern

All prompts in the codebase follow a consistent architecture:

| Location | Pattern | Template Style |
|----------|---------|----------------|
| `core/discover_engine.py:9-169` | `DISCOVER_PROMPT_TEMPLATE` + `generate_discover_prompt()` | Module-level constant |
| `core/interview_engine.py:10-48` | `INTERVIEW_SYSTEM_PROMPT` + `generate_interview_prompt()` | Module-level constant |
| `core/doc_review_engine.py:12-130` | `DOC_REVIEW_PROMPT_TEMPLATE` + `generate_doc_review_prompt()` | Module-level constant |
| `core/doc_review_engine.py:210-325` | `CODE_REVIEW_PROMPT_TEMPLATE` + `generate_code_review_prompt()` | Module-level constant |
| `commands/research.py:29-89` | Inline in `generate_research_prompt()` | Inline f-string |
| `commands/plan.py:14-212` | Inline in `generate_plan_prompt()` | Inline f-string |
| `commands/implement.py:837-866` | Inline in `_execute_step()` | Inline f-string |
| `commands/commit.py:159-228` | Inline in `_generate_commit_prompt()` | Inline f-string |

**Key Observations:**

1. **Core vs Commands Split**: Prompts that are considered "engines" live in `core/`, while
   command-specific prompts are inline in `commands/`. This suggests the spec's `prompt.py`
   module should live in `commands/` since it's CLI-facing.

2. **Generator Function Signatures**: Each generator has different parameters:
   - `generate_discover_prompt(focus_areas: str | None = None)`
   - `generate_interview_prompt(document_path: Path, document_content: str, focus: str | None = None)`
   - `generate_doc_review_prompt(document_content: str, apply_mode: bool = False, focus: str | None = None)`
   - `generate_code_review_prompt(diff_content: str, apply_mode: bool = False, focus: str | None = None)`
   - `generate_research_prompt(spec_content: str, spec_name: str, focus: str | None = None)`
   - `generate_plan_prompt(specs: list[tuple[str, str]])`

3. **Focus Parameter Inconsistency**: Some use `focus`, others use `focus_areas`, and some
   have no focus parameter at all (plan, implement). The spec's `default_focus` will only
   apply to commands that support focus.

### 1.2 Configuration System Extension Points

The configuration system in `src/weld/config.py` provides clear extension patterns:

**Existing Nested Config Pattern** (lines 43-61, 106-113):
```python
class TaskModelsConfig(BaseModel):
    """Per-task model assignments."""
    discover: ModelConfig = Field(default_factory=lambda: ModelConfig(provider="claude"))
    # ... more fields

class TranscriptsConfig(BaseModel):
    """Configuration for transcript generation."""
    enabled: bool = True
    visibility: str = "secret"
```

**WeldConfig Integration** (lines 145-179):
```python
class WeldConfig(BaseModel):
    # ... existing fields ...
    task_models: TaskModelsConfig = Field(default_factory=TaskModelsConfig)
    transcripts: TranscriptsConfig = Field(default_factory=TranscriptsConfig)
```

The new `PromptsConfig` should follow this exact pattern.

### 1.3 TaskType Enum Analysis

**Current TaskType values** (`config.py:14-33`):
```python
class TaskType(str, Enum):
    DISCOVER = "discover"
    INTERVIEW = "interview"
    RESEARCH = "research"
    RESEARCH_REVIEW = "research_review"
    PLAN_GENERATION = "plan_generation"
    PLAN_REVIEW = "plan_review"
    IMPLEMENTATION = "implementation"
    IMPLEMENTATION_REVIEW = "implementation_review"
    FIX_GENERATION = "fix_generation"
```

**Mapping Issue Identified**: The spec proposes `PromptsConfig` with fields like `plan` and
`implement`, but `TaskType` uses `PLAN_GENERATION` and `IMPLEMENTATION`. This requires
careful mapping:

| PromptsConfig Field | TaskType Value | Notes |
|---------------------|----------------|-------|
| `discover` | `TaskType.DISCOVER` | Direct match |
| `interview` | `TaskType.INTERVIEW` | Direct match |
| `research` | `TaskType.RESEARCH` | Direct match |
| `plan` | `TaskType.PLAN_GENERATION` | Name differs |
| `implement` | `TaskType.IMPLEMENTATION` | Name differs |
| `review` | N/A | Uses doc_review/code_review in commands |
| `commit` | N/A | No TaskType exists |

**Recommendation**: Either:
1. Add `TaskType.COMMIT` and `TaskType.REVIEW` to the enum, OR
2. Create a separate mapping in `prompt_customizer.py` that doesn't rely on `TaskType`

Option 2 is cleaner since `TaskType` is for model assignment, not prompt customization.

### 1.4 CLI Registration Pattern

The CLI in `src/weld/cli.py` uses two patterns:

**Typer subcommand groups** (lines 40-41):
```python
app.add_typer(discover_app, name="discover")
app.add_typer(telegram_app, name="telegram")
```

**Direct command registration** (lines 126-133):
```python
app.command()(init)
app.command()(commit)
# ...
app.command("review")(doc_review)
```

The `prompt` command should use the subcommand group pattern since it has `list`, `show`,
and `export` subcommands.

---

## 2. Dependency Mapping

### 2.1 External Dependencies

**Already Present** (no additions needed):
- `typer` - CLI framework
- `rich` - Console output (Console, Panel, Syntax)
- `pydantic` - Data validation (BaseModel, Field)

### 2.2 Internal Module Dependencies

**Feature 1 (Prompt Personalization):**

| New Module | Imports From | Used By |
|------------|--------------|---------|
| `config.py` (modified) | `pydantic` | All commands |
| `core/prompt_customizer.py` (new) | `config.py`, `pathlib` | All prompt-using commands |

Commands requiring modification:
- `commands/discover.py` - Uses `generate_discover_prompt`
- `commands/interview.py` - Uses `run_interview_loop` → `generate_interview_prompt`
- `commands/research.py` - Uses `generate_research_prompt`
- `commands/plan.py` - Uses `generate_plan_prompt`
- `commands/implement.py` - Uses inline prompt in `_execute_step`
- `commands/doc_review.py` - Uses `generate_doc_review_prompt`, `generate_code_review_prompt`
- `commands/commit.py` - Uses `_generate_commit_prompt`

**Feature 2 (Prompt Viewer):**

| New Module | Imports From | Used By |
|------------|--------------|---------|
| `commands/prompt.py` (new) | All prompt generators, `config.py`, `core/weld_dir.py` | CLI |

**Import Consideration**: The spec shows importing `generate_plan_prompt` from `commands/plan`
and `generate_research_prompt` from `commands/research`. This creates a cross-dependency
between command modules. This is acceptable but could be refactored later if needed.

### 2.3 Version Constraints

No new external dependencies are required. All functionality uses existing packages.

---

## 3. Risk Assessment

### 3.1 Technical Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Config migration breaks existing configs** | Medium | Default all new fields to empty strings; existing configs remain valid |
| **Customization changes prompt semantics** | Low | Prefix/suffix append pattern preserves core prompt integrity |
| **Performance impact from config reloading** | Low | Config is already loaded per-command; no additional overhead |
| **Circular import between commands/** | Medium | Import at function level if needed, not module level |

### 3.2 Areas Requiring Care

**1. Interview Engine Difference**

The interview engine is unique - it outputs the prompt to stdout via `run_interview_loop()`
rather than using it with `run_claude()`. The customization must be applied in
`generate_interview_prompt()`, not at the command level.

See `core/interview_engine.py:103-104`:
```python
prompt = generate_interview_prompt(document_path, content, focus)
con.print(prompt)
```

**2. Implement Command Inline Prompt**

The implement command has an inline prompt in `_execute_step()` (lines 837-866).
This is not a module-level constant or generator function. Options:
- Extract to a generator function in `core/` (cleaner)
- Apply customization inline (messier but localized change)

**Recommendation**: Keep inline for now, apply customization in `_execute_step()` directly.
Extracting would be a larger refactor better done separately.

**3. Commit Prompt is Private**

`_generate_commit_prompt()` (lines 159-228) is a private function. For the prompt viewer
to access it, either:
- Make it public (`generate_commit_prompt`)
- Provide a sample in the viewer (spec's approach with `_get_commit_prompt_sample()`)

The spec's approach is pragmatic - sample prompts for implement and commit avoid
exposing internal implementation details.

### 3.3 Security Considerations

- **Config file permissions**: `.weld/config.toml` is already in `.gitignore` per CLAUDE.md
- **Prompt injection via prefix/suffix**: Low risk since customizations are user-controlled
  and applied to their own prompts
- **No secrets in prompts**: Prompts should not contain API keys; this is existing behavior

---

## 4. Open Questions

### 4.1 Ambiguities in Specification

**Q1: Should `weld prompt show` work outside a weld project?**

The spec shows `find_weld_dir()` raising `FileNotFoundError` and catching it. This means
`--raw` is implicit outside projects. But should `weld prompt list` work anywhere?

**Recommendation**: Yes, `list` and `show --raw` should work anywhere. Only customization
application requires a weld project.

**Q2: What happens when `default_focus` is set but `--focus` is explicitly empty?**

```toml
[prompts.discover]
default_focus = "API layer"
```
```bash
weld discover --focus ""  # Empty string
```

**Recommendation**: Explicit empty string (`""`) should override default. Only `None`
(not provided) triggers default.

**Q3: Should the `prompt export` include customizations by default?**

The spec shows `--raw` flag for export. This is the opposite of `show` where customizations
are applied by default.

**Recommendation**: Be consistent - apply customizations by default, use `--raw` to skip.
The spec already shows this pattern.

**Q4: How should multi-line prefixes/suffixes be handled in TOML?**

TOML supports multi-line strings with `"""..."""`. Example:
```toml
[prompts.discover]
prefix = """
Additional context:
- We use Clean Architecture
- All services implement ISP
"""
```

**Recommendation**: Document this in CLAUDE.md. No code changes needed - TOML handles it.

### 4.2 Decisions Requiring Human Input

**D1: Should `plan` and `implement` support `default_focus`?**

Currently, neither `generate_plan_prompt` nor the implement inline prompt accept a focus
parameter. The spec shows `PromptCustomization` with `default_focus: str | None` for all
prompt types, but this field would be ignored for plan/implement.

**Options**:
1. Add focus support to plan/implement (scope creep)
2. Document that `default_focus` is ignored for plan/implement
3. Create `PromptCustomizationWithFocus` and `PromptCustomization` variants

**Recommendation**: Option 2 - Document the limitation. Adding focus to plan/implement
is valuable but orthogonal to this feature.

**D2: Should the prompt viewer support `--diff` for code review variants?**

The spec shows `--mode doc` and `--mode code` for review prompts. But code review also
has staged vs all changes. Should the viewer surface this?

**Recommendation**: Keep simple. The viewer shows template structure, not all CLI variations.

**D3: Ordering of trailers in PromptsConfig?**

Should prefix/suffix order be:
1. `global_prefix → task_prefix → prompt → task_suffix → global_suffix` (nested)
2. `global_prefix → prompt → global_suffix` then separately apply task-specific

The spec clearly specifies option 1 (nested ordering). This is the right choice.

### 4.3 Alternative Approaches Worth Considering

**A1: File-based prompt overrides instead of TOML config**

Instead of embedding in config.toml:
```
.weld/
  prompts/
    discover.prefix.md
    discover.suffix.md
    global.prefix.md
```

**Pros**: Easier to manage multi-line prompts, version control friendly
**Cons**: More complex implementation, file proliferation

**Recommendation**: Start with TOML-based (spec's approach). File-based can be added later
if demand exists.

**A2: Prompt templates with variable substitution**

Allow `{{project_name}}` or similar in prefix/suffix that gets replaced at runtime.

**Recommendation**: Out of scope for initial implementation. Can be added later.

**A3: Separate "prompts" subcommand vs nested under existing**

The spec proposes `weld prompt list|show|export`. Alternatively:
- `weld config prompts` (under config management)
- `weld debug prompts` (as debugging tool)

**Recommendation**: `weld prompt` is cleaner and more discoverable.

---

## 5. Implementation Considerations

### 5.1 File Organization

```
src/weld/
├── config.py              # Add PromptCustomization, PromptsConfig
├── commands/
│   └── prompt.py          # NEW: prompt command group
└── core/
    ├── __init__.py        # Export apply_customization, get_default_focus
    └── prompt_customizer.py  # NEW: customization utilities
```

### 5.2 Testing Strategy

**Unit Tests** (`tests/test_prompt_customizer.py`):
- `test_applies_global_prefix`
- `test_applies_task_prefix_and_suffix`
- `test_prefix_order` (verify: global_prefix → task_prefix → prompt → task_suffix → global_suffix)
- `test_default_focus_used_when_focus_none`
- `test_empty_customization_returns_original`
- `test_explicit_empty_focus_overrides_default`

**Unit Tests** (`tests/test_prompt_command.py`):
- `test_list_prompts_shows_all_types`
- `test_show_discover_prompt`
- `test_show_with_focus_parameter`
- `test_show_raw_skips_customization`
- `test_export_creates_files`
- `test_export_to_existing_directory`

**CLI Integration Tests**:
- `test_prompt_show_no_weld_dir` (should work with --raw)
- `test_prompt_show_with_customization`

### 5.3 Documentation Updates

Update `CLAUDE.md` with:

1. New command documentation:
```
# Prompt Viewer
weld prompt list              # List available prompts
weld prompt show <type>       # Show prompt template
weld prompt export ./prompts/ # Export all prompts
```

2. New configuration section:
```toml
[prompts]
global_prefix = ""
global_suffix = ""

[prompts.discover]
prefix = ""
suffix = ""
default_focus = ""
```

---

## 6. Verification Checklist

Before implementation is considered complete:

- [ ] All existing tests pass (`make test`)
- [ ] New tests achieve >80% coverage for new code
- [ ] `make check` passes (lint, format, types)
- [ ] `make security` passes
- [ ] `weld prompt list` works without weld init
- [ ] `weld prompt show discover` works without weld init (with --raw behavior)
- [ ] `weld prompt show discover` applies customizations when weld initialized
- [ ] All commands with prompts apply customizations
- [ ] `default_focus` works for supported commands
- [ ] Empty config section doesn't break existing behavior
- [ ] CHANGELOG.md updated with new features

---

## 7. Summary

The specification is well-designed and aligns with existing codebase patterns. Key findings:

1. **Phase 1 (Prompt Viewer)** is truly standalone and can be implemented first
2. **Phase 2 (Personalization)** touches 7+ command files but changes are mechanical
3. **TaskType mapping** needs careful handling - recommend independent mapping
4. **Interview engine** requires special attention due to stdout pattern
5. **Implement/commit prompts** use sample approach for viewer (per spec)

No blocking issues identified. Ready for implementation planning.
