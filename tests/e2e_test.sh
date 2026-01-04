#!/bin/bash
set -e

echo "=== Weld E2E Test ==="

# Create temp directory
TMPDIR=$(mktemp -d)
cd "$TMPDIR"

echo "Working in: $TMPDIR"

# Initialize git repo
git init
git config user.email "test@test.com"
git config user.name "Test User"

# Create a dummy spec
mkdir specs
cat > specs/test.md << 'EOF'
# Test Spec

Implement a hello world function.

## Requirements
- Create hello.py with greet() function
- Function returns "Hello, World!"
EOF

# Initialize weld (this will fail on missing tools, which is expected)
echo "Testing weld init..."
weld init || echo "Expected: some tools missing"

# Create config manually for testing
mkdir -p .weld
cat > .weld/config.toml << 'EOF'
[project]
name = "test-project"

[checks]
command = "echo 'checks ok'"

[codex]
exec = "echo"
sandbox = "read-only"

[claude.transcripts]
exec = "echo"
visibility = "secret"

[git]
commit_trailer_key = "Claude-Transcript"
include_run_trailer = true

[loop]
max_iterations = 3
fail_on_blockers_only = true
EOF

mkdir -p .weld/runs

# Start a run
echo "Testing weld run start..."
weld run --spec specs/test.md

echo "=== E2E Test Complete ==="
echo "Temp dir: $TMPDIR"
