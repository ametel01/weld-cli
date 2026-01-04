#!/bin/bash
set -uo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

TESTS_PASSED=0
TESTS_FAILED=0

# Increment helpers (avoid ((x++)) returning 1 when x=0)
pass() { TESTS_PASSED=$((TESTS_PASSED + 1)); }
fail() { TESTS_FAILED=$((TESTS_FAILED + 1)); }

# Assertion helpers
assert_eq() {
    local expected="$1"
    local actual="$2"
    local msg="${3:-Values should be equal}"
    if [ "$expected" != "$actual" ]; then
        echo -e "${RED}FAIL:${NC} $msg"
        echo "  Expected: $expected"
        echo "  Actual:   $actual"
        fail
        return 1
    fi
    pass
    return 0
}

assert_file_exists() {
    local path="$1"
    local msg="${2:-File should exist: $path}"
    if [ ! -f "$path" ]; then
        echo -e "${RED}FAIL:${NC} $msg"
        fail
        return 1
    fi
    pass
    return 0
}

assert_dir_exists() {
    local path="$1"
    local msg="${2:-Directory should exist: $path}"
    if [ ! -d "$path" ]; then
        echo -e "${RED}FAIL:${NC} $msg"
        fail
        return 1
    fi
    pass
    return 0
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    local msg="${3:-Output should contain: $needle}"
    if ! echo "$haystack" | grep -q "$needle"; then
        echo -e "${RED}FAIL:${NC} $msg"
        echo "  Looking for: $needle"
        echo "  In output: $haystack"
        fail
        return 1
    fi
    pass
    return 0
}

assert_json_has_field() {
    local file="$1"
    local field="$2"
    local msg="${3:-JSON should have field: $field}"
    if ! grep -q "\"$field\"" "$file"; then
        echo -e "${RED}FAIL:${NC} $msg"
        fail
        return 1
    fi
    pass
    return 0
}

# Setup temp directory with cleanup trap
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT
cd "$TMPDIR"

echo "=== Weld E2E Test Suite ==="
echo "Working in: $TMPDIR"
echo ""

# ============================================================================
# SETUP: Initialize git repo with initial commit
# ============================================================================
echo "Setting up test environment..."

git init -q
git config user.email "test@test.com"
git config user.name "Test User"
echo "# Test Project" > README.md
git add .
git commit -q -m "Initial commit"

# Create spec file
mkdir specs
cat > specs/test.md << 'EOF'
# Test Spec

Implement a hello world function.

## Requirements
- Create hello.py with greet() function
- Function returns "Hello, World!"
EOF

# Setup weld config manually (avoids tool detection issues in CI)
mkdir -p .weld/runs
cat > .weld/config.toml << 'EOF'
[project]
name = "test-project"

[checks]
command = "echo 'checks ok'"

[codex]
exec = "echo"
sandbox = "read-only"

[claude]
exec = "echo"

[loop]
max_iterations = 3
fail_on_blockers_only = true
EOF

echo ""

# ============================================================================
# TEST 1: weld list shows no runs initially
# ============================================================================
echo "TEST 1: weld list with no runs"

OUTPUT=$(weld list 2>&1)
assert_contains "$OUTPUT" "No runs found" "list should show 'No runs found' when empty"

echo ""

# ============================================================================
# TEST 2: weld run creates run directory with correct structure
# ============================================================================
echo "TEST 2: weld run --spec creates run with correct structure"

OUTPUT=$(weld run --spec specs/test.md 2>&1)

# Assert success message
assert_contains "$OUTPUT" "Run created" "run should print success message"

# Assert exactly one run directory created
RUN_COUNT=$(ls .weld/runs | wc -l)
assert_eq "1" "$RUN_COUNT" "Should create exactly one run directory"

# Get the run ID
RUN_ID=$(ls .weld/runs)
RUN_DIR=".weld/runs/$RUN_ID"

# Assert run directory structure
assert_dir_exists "$RUN_DIR" "Run directory should exist"
assert_file_exists "$RUN_DIR/meta.json" "Run should have meta.json"
assert_file_exists "$RUN_DIR/inputs/spec.ref.json" "Run should have spec reference"
assert_dir_exists "$RUN_DIR/plan" "Run should have plan directory"

# Assert meta.json has required fields
assert_json_has_field "$RUN_DIR/meta.json" "run_id" "meta.json should have run_id"
assert_json_has_field "$RUN_DIR/meta.json" "repo_root" "meta.json should have repo_root"
assert_json_has_field "$RUN_DIR/meta.json" "branch" "meta.json should have branch"
assert_json_has_field "$RUN_DIR/meta.json" "head_sha" "meta.json should have head_sha"

# Assert run ID format (YYYYMMDD-HHMMSS-slug pattern)
if ! echo "$RUN_ID" | grep -qE '^[0-9]{8}-[0-9]{6}-'; then
    echo -e "${RED}FAIL:${NC} Run ID should match YYYYMMDD-HHMMSS-* format"
    echo "  Actual: $RUN_ID"
    fail
else
    pass
fi

echo ""

# ============================================================================
# TEST 3: weld list shows the created run
# ============================================================================
echo "TEST 3: weld list shows created run"

OUTPUT=$(weld list 2>&1)
assert_contains "$OUTPUT" "$RUN_ID" "list should show the run ID"

echo ""

# ============================================================================
# TEST 4: weld run with missing spec fails with clear error
# ============================================================================
echo "TEST 4: weld run with missing spec fails gracefully"

OUTPUT=$(weld run --spec nonexistent.md 2>&1) && EXIT_CODE=0 || EXIT_CODE=$?

if [ "$EXIT_CODE" -eq 0 ]; then
    echo -e "${RED}FAIL:${NC} Should fail with missing spec file"
    fail
else
    assert_eq "1" "$EXIT_CODE" "Should exit with code 1 for missing spec" || true
    assert_contains "$OUTPUT" "not found" "Should mention file not found" || true
fi

echo ""

# ============================================================================
# TEST 5: Plan import and step select workflow
# ============================================================================
echo "TEST 5: Plan import and step select workflow"

# Create a plan file
cat > plan.md << 'EOF'
## Step 1: Create hello module

### Goal
Create a hello world module.

### Changes
- Create src/hello.py with greet() function

### Acceptance criteria
- [ ] Function returns "Hello, World!"
- [ ] Module can be imported

### Tests
- pytest tests/test_hello.py

## Step 2: Add CLI command

### Goal
Add a CLI command to run greet.

### Changes
- Update cli.py to add hello command

### Acceptance criteria
- [ ] weld hello prints greeting

### Tests
- weld hello
EOF

# Import plan
OUTPUT=$(weld plan import --run "$RUN_ID" --file plan.md 2>&1)
assert_contains "$OUTPUT" "Imported plan with 2 steps" "Should import 2 steps"

# Verify plan files created
assert_file_exists "$RUN_DIR/plan/plan.raw.md" "Should create plan.raw.md"
assert_file_exists "$RUN_DIR/plan/output.md" "Should create output.md"

# Select step 1
OUTPUT=$(weld step select --run "$RUN_ID" --n 1 2>&1)
assert_contains "$OUTPUT" "Selected step 1" "Should select step 1"

# Verify step directory created
STEP_DIRS=$(ls "$RUN_DIR/steps" 2>/dev/null | wc -l)
assert_eq "1" "$STEP_DIRS" "Should create one step directory"

STEP_DIR=$(ls "$RUN_DIR/steps")
assert_file_exists "$RUN_DIR/steps/$STEP_DIR/step.json" "Step should have step.json"
assert_file_exists "$RUN_DIR/steps/$STEP_DIR/prompt/impl.prompt.md" "Step should have implementation prompt"

# Verify step.json content
assert_json_has_field "$RUN_DIR/steps/$STEP_DIR/step.json" "n" "step.json should have step number"
assert_json_has_field "$RUN_DIR/steps/$STEP_DIR/step.json" "title" "step.json should have title"

echo ""

# ============================================================================
# TEST 6: Invalid step number fails gracefully
# ============================================================================
echo "TEST 6: Invalid step number fails gracefully"

OUTPUT=$(weld step select --run "$RUN_ID" --n 99 2>&1) && EXIT_CODE=0 || EXIT_CODE=$?

if [ "$EXIT_CODE" -eq 0 ]; then
    echo -e "${RED}FAIL:${NC} Should fail with invalid step number"
    fail
else
    assert_eq "1" "$EXIT_CODE" "Should exit with code 1 for invalid step" || true
    assert_contains "$OUTPUT" "not found" "Should mention step not found" || true
fi

echo ""

# ============================================================================
# RESULTS
# ============================================================================
echo "==========================================="
echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}"
echo "==========================================="

if [ "$TESTS_FAILED" -gt 0 ]; then
    echo -e "${RED}E2E TESTS FAILED${NC}"
    exit 1
fi

echo -e "${GREEN}All E2E tests passed!${NC}"
exit 0
