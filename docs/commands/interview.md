# weld interview

Refine a specification through interactive Q&A.

## Usage

```bash
weld interview <file> [OPTIONS]
```

## Arguments

| Argument | Description |
|----------|-------------|
| `file` | Path to the specification file |

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--focus` | `-f` | Topic to focus questions on |

## Description

Outputs a prompt for Claude Code that:

1. Asks in-depth questions using the `AskUserQuestion` tool
2. Covers implementation, UI/UX, edge cases, tradeoffs
3. Rewrites the specification when complete

This helps ensure specifications are complete before planning.

## Examples

### Interview a specification

```bash
weld interview specs/feature.md
```

### Focus on specific topic

```bash
weld interview specs/feature.md --focus "edge cases"
```

### Focus on security concerns

```bash
weld interview specs/auth.md --focus "security"
```

## Input Validation

Before starting the Claude operation, weld validates inputs upfront:

- **File existence**: Verifies the specification file exists
- **File type**: Ensures the path points to a file, not a directory

When validation fails, you'll see a clear error message with an actionable hint:

```
Error: specs/ is a directory, expected a file
Hint: Provide a valid specification file path
```

This prevents wasted time from invalid inputs.

## See Also

- [Workflow](../workflow.md) - How interview fits in the workflow
- [research](research.md) - Research after refining the spec
- [plan](plan.md) - Generate a plan from the refined spec
