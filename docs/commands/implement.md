# weld implement

Interactively execute a phased implementation plan.

## Usage

```bash
weld implement <plan> [OPTIONS]
```

## Arguments

| Argument | Description |
|----------|-------------|
| `plan` | Path to the plan file |

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--phase` | `-p` | Start at a specific phase number |
| `--step` | `-s` | Start at a specific step number |
| `--quiet` | `-q` | Suppress streaming output |

## Description

The command:

1. Parses the plan to extract phases and steps
2. Shows an interactive menu (or jumps to specified step)
3. Generates implementation prompts for each step
4. Runs Claude to implement the step
5. Marks the step complete in the plan file

## Features

- **Interactive mode**: Arrow-key navigable menu for selecting phases/steps
- **Non-interactive mode**: Use `--phase` and `--step` flags for CI/automation
- **Progress tracking**: Steps are marked complete with `[COMPLETE]` in the plan file
- **Graceful interruption**: Ctrl+C preserves progress (completed steps stay marked)

## Examples

### Interactive mode

```bash
weld implement plan.md
```

### Start at specific phase

```bash
weld implement plan.md --phase 2
```

### Start at specific step

```bash
weld implement plan.md --step 3
```

### Non-interactive: specific step

```bash
weld implement plan.md --phase 2 --step 1
```

## Progress Tracking

When a step is completed, it's marked in the plan file:

```markdown
### Step 1: Create data models [COMPLETE]
```

## See Also

- [plan](plan.md) - Generate a plan to implement
- [Plan Format](../reference/plan-format.md) - How plans are structured
- [review](review.md) - Review changes after implementing
