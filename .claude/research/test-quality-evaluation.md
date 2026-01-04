# Research: Test Quality Evaluation

## Executive Summary

This evaluation analyzes 11 new test files in the weld-cli project. The tests exhibit **mixed quality** - some establish clear invariants and would catch regressions, while others are fragile, implementation-coupled, or test trivial behavior rather than meaningful contracts.

**Key Finding:** Several tests verify output format strings rather than semantic behavior, making them brittle to cosmetic changes while missing actual bugs. The test suite would benefit from focusing on **what the code must do** rather than **how it currently does it**.

---

## Critical Issues Found

### 1. Output Format Coupling (HIGH SEVERITY)

**Files affected:** `test_checks.py`, `test_cli.py`

Tests verify exact string formats rather than semantic properties:

```python
# test_checks.py:17-19
assert "hello" in output
assert "exit_code: 0" in output
assert "=== stdout ===" in output
assert "=== stderr ===" in output
```

**Problem:** These tests will break if the output format changes (e.g., `exit_code: 0` → `Exit Code: 0`), but won't catch actual bugs like:
- stdout/stderr being swapped
- exit code being computed incorrectly
- output being truncated

**Better invariant:** Test that:
1. Exit code matches actual subprocess exit code
2. stdout content appears somewhere in output
3. stderr content appears somewhere in output

### 2. Tests That Adapt to Implementation Quirks (HIGH SEVERITY)

**File:** `test_checks.py:28-33`

```python
def test_command_with_stderr(self, tmp_path: Path) -> None:
    """Command outputting to stderr should capture it."""
    _output, exit_code = run_checks("echo error >&2", tmp_path)
    # Shell features need shell=True, which we removed
    # So this just runs "echo" with "error" and ">&2" as args
    assert exit_code == 0
```

**Problem:** The test name claims to test stderr capture, but the comment admits it doesn't actually test stderr at all. This test:
1. Doesn't test what it claims
2. Documents a limitation but passes anyway
3. Would not catch a regression in stderr handling

**What should happen:** Either:
- Delete the test (it tests nothing)
- Write a test that actually sends to stderr (e.g., use Python subprocess to write to stderr)
- Mark as `@pytest.skip("shell=True removed, stderr redirection not supported")`

### 3. Permissive Exit Code Assertions (MEDIUM SEVERITY)

**File:** `test_cli.py:91-100`

```python
def test_init_in_git_repo(self, runner: CliRunner, temp_git_repo: Path) -> None:
    """init should work in a git repository (may fail on missing tools)."""
    result = runner.invoke(app, ["init"])
    # Exit 0 = success, Exit 2 = missing tools (both acceptable)
    assert result.exit_code in [0, 2]

def test_init_already_initialized(self, ...) -> None:
    """init should handle already initialized directory."""
    result = runner.invoke(app, ["init"])
    # Should either succeed or warn about existing config
    assert result.exit_code in [0, 2]
```

**Problem:** These tests accept multiple exit codes, meaning they can't distinguish between:
- Success
- Failure due to missing tools
- Actual bugs

**Better approach:**
- Mock external tool detection
- Test each exit path separately
- Document which exit code means what

### 4. Mock-Heavy Tests That Don't Test Real Behavior (MEDIUM SEVERITY)

**File:** `test_review_engine.py`

```python
@patch("weld.core.review_engine.run_codex")
@patch("weld.core.review_engine.parse_codex_review")
def test_codex_review_passing(
    self, mock_parse: MagicMock, mock_run: MagicMock, tmp_path: Path
) -> None:
    mock_run.return_value = '{"pass": true, "issues": []}'
    mock_parse.return_value = MagicMock(pass_=True, issues=[])
    ...
```

**Problem:** The test mocks out the actual review logic and then tests that the mocked values are processed correctly. This tests:
- The wiring between functions (weak)
- That mock returns what we told it to return (useless)

**What's missing:**
- No test that `run_codex` is called with correct arguments
- No test that prompt is properly formatted
- No integration test that runs actual review flow

### 5. Skipped Tests That Document Missing Coverage (LOW SEVERITY)

**File:** `test_review_engine.py:223-230`

```python
def test_unsupported_provider_raises(self, tmp_path: Path) -> None:
    """run_step_review should raise for unsupported provider."""
    # This test is skipped as config validation prevents invalid providers
    pytest.skip("Config validation prevents invalid providers at parse time")
```

**Problem:** This admits there's no test for error handling of unsupported providers. If config validation is bypassed (bug, API misuse), the behavior is untested.

---

## Good Patterns Found

### 1. Clear Invariant Tests (GOOD)

**File:** `test_git.py:83-86`

```python
def test_returns_full_sha(self, temp_git_repo: Path) -> None:
    """get_head_sha should return full SHA."""
    result = get_head_sha(temp_git_repo)
    assert len(result) == 40  # Full SHA length
```

**Why it's good:** Tests a clear invariant (SHA is always 40 chars) that doesn't depend on implementation details.

### 2. Behavior-Focused Tests (GOOD)

**File:** `test_git.py:181-196`

```python
def test_with_staged_changes(self, temp_git_repo: Path) -> None:
    """has_staged_changes should return True when changes staged."""
    (temp_git_repo / "README.md").write_text("# Changed\n")
    subprocess.run(["git", "add", "README.md"], ...)
    result = has_staged_changes(temp_git_repo)
    assert result is True

def test_with_unstaged_changes(self, temp_git_repo: Path) -> None:
    """has_staged_changes should return False for unstaged only."""
    (temp_git_repo / "README.md").write_text("# Changed\n")
    result = has_staged_changes(temp_git_repo)
    assert result is False
```

**Why it's good:** Tests observable behavior distinction (staged vs unstaged) rather than implementation.

### 3. Error Path Testing (GOOD)

**File:** `test_checks.py:35-38`

```python
def test_command_not_found(self, tmp_path: Path) -> None:
    """Non-existent command should raise ChecksError."""
    with pytest.raises(ChecksError, match="Command not found"):
        run_checks("nonexistent_command_xyz", tmp_path)
```

**Why it's good:** Tests error handling with specific error message matching.

---

## Tests Missing Entirely

### 1. Edge Cases Not Covered

| Module | Missing Test |
|--------|--------------|
| `checks.py` | Command with very long output (truncation?) |
| `checks.py` | Command with binary/non-UTF8 output |
| `git.py` | Detached HEAD state |
| `git.py` | Merge conflicts |
| `step_processor.py` | Step with special characters in title/slug |
| `step_processor.py` | Very long body_md content |

### 2. Integration Gaps

| Flow | Missing |
|------|---------|
| CLI → checks | No test that CLI actually calls `run_checks` correctly |
| review → codex | No test of actual JSON parsing from real codex output |
| step select → prompt generation | Only tests prompt content, not that it's written to correct path |

---

## Recommendations

### Immediate Fixes

1. **Remove or fix `test_command_with_stderr`** - it tests nothing
2. **Split permissive exit code tests** - mock tool detection and test each path
3. **Add semantic assertions to format tests** - verify stdout/stderr separation, not exact strings

### Structural Changes

1. **Add property-based tests for path generation**
   ```python
   @given(st.integers(1, 99), st.text(alphabet=string.ascii_lowercase, min_size=1))
   def test_step_dir_format(n, slug):
       step = make_step(n=n, slug=slug)
       result = get_step_dir(Path("/tmp"), step)
       assert result.name.startswith(f"{n:02d}-")
   ```

2. **Add integration tests with real subprocess behavior**
   - Test `run_checks` with actual commands
   - Test git operations in real repos
   - Test full CLI flows end-to-end

3. **Document invariants explicitly in test names**
   - Current: `test_successful_command`
   - Better: `test_exit_code_zero_for_successful_command`

### Invariants That Should Be Tested

| Module | Invariant | Currently Tested? |
|--------|-----------|-------------------|
| `checks.run_checks` | exit_code matches subprocess exit | ❌ Implicit only |
| `checks.run_checks` | timeout raises ChecksError | ✅ |
| `git.get_head_sha` | Returns exactly 40 hex chars | ✅ |
| `git.get_repo_root` | Returns parent of .git dir | ❌ |
| `step_processor.get_step_dir` | Format is `{n:02d}-{slug}` | ✅ |
| `review_engine.run_step_review` | blocker_count + major_count + minor_count = issue_count | ❌ |

---

## File-by-File Assessment

| File | Rating | Key Issue |
|------|--------|-----------|
| `test_checks.py` | C | Tests format strings, not behavior |
| `test_cli.py` | B- | Permissive assertions, but covers commands |
| `test_diff.py` | B | Reasonable, but thin |
| `test_filesystem.py` | A- | Good invariants, comprehensive |
| `test_git.py` | A- | Strong behavior tests |
| `test_integration.py` | B | Good flows, but setup-heavy |
| `test_output.py` | B | Tests mode switching well |
| `test_review_engine.py` | C | Over-mocked, tests wiring not logic |
| `test_step_processor.py` | A | Clear invariants, good coverage |
| `test_transcripts.py` | B- | Mock-heavy but verifies args |

---

## Conclusion

The test suite has a structural issue: **tests are written to pass, not to catch bugs**. Many tests verify that the code does what it currently does, rather than establishing contracts that must hold.

Highest-priority fixes:
1. Delete or rewrite `test_command_with_stderr` (actively misleading)
2. Add invariant assertions to `test_checks.py` format tests
3. Split the permissive exit code CLI tests

The git and step_processor tests show good patterns that should be replicated across the suite.
