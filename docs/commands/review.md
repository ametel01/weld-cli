# weld review

Review documents or code changes.

## Usage

```bash
weld review [<file>] [OPTIONS]
```

## Arguments

| Argument | Description |
|----------|-------------|
| `file` | Path to the document to review (optional if using `--diff`) |

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--diff` | `-d` | Review git diff instead of a document |
| `--staged` | `-s` | Review only staged changes (requires `--diff`) |
| `--focus` | `-f` | Topic to focus the review on |
| `--apply` | | Apply corrections/fixes directly |
| `--prompt-only` | | Output prompt without running Claude |
| `--quiet` | `-q` | Suppress streaming output |
| `--timeout` | `-t` | Timeout in seconds (default: 1800 from config) |

## Document Review

Verifies documents against your codebase.

### Checks Performed

- Errors and inaccuracies
- Missing implementations
- Gaps in coverage
- Wrong evaluations

### Examples

```bash
# Review document accuracy
weld review plan.md

# Apply corrections in place
weld review plan.md --apply

# Focus review on specific topic
weld review plan.md --focus "security"

# Preview the prompt
weld review research.md --prompt-only
```

## Code Review

Reviews git diff for issues.

### Checks Performed

- Bugs and logic errors
- Security vulnerabilities
- Missing implementations
- Test issues (assertions, coverage)
- Significant improvements needed

### Examples

```bash
# Review all uncommitted changes
weld review --diff

# Review only staged changes
weld review --diff --staged

# Apply fixes directly
weld review --diff --apply

# Focus review on specific topic
weld review --diff --focus "error handling"

# Preview the prompt
weld review --diff --prompt-only
```

## Input Validation

Before starting the (potentially expensive) Claude operation, weld validates inputs upfront:

- **File existence**: In document review mode, verifies the input file exists
- **File type**: Ensures the path points to a file, not a directory

When validation fails, you'll see a clear error message with an actionable hint:

```
Error: docs/specs is a directory, expected a file
Hint: Provide a valid document path to review
```

This prevents wasted API tokens from invalid inputs.

## See Also

- [commit](commit.md) - Commit after review
- [implement](implement.md) - Implement plan steps
- [Workflow](../workflow.md) - How review fits in the workflow
