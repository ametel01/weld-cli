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

## Session Management

### How Claude Execution Works Per Step

`weld implement` does **not** maintain conversational context between steps. Each step execution
is independent:

1. **Each step is a separate Claude CLI invocation**: When you execute a step, a fresh Claude
   process is spawned with a prompt containing only that step's specification (Goal, Files,
   Validation, Failure modes).

2. **No memory between steps**: Each Claude invocation starts with a clean slate - it doesn't
   have access to what happened in previous steps. This is why each step prompt includes all
   the context needed to complete that specific step independently.

3. **Session tracking is for commits, not context**: The `track_session_activity()` wrapper
   tracks file changes for the entire `weld implement` command execution (all steps combined),
   not individual step conversations. This tracking is used later by `weld commit` to group
   files by their originating Claude Code session and attach transcript URLs.

### Practical Implications

- **Step prompts must be self-contained**: Each step needs complete information since it can't
  reference previous step outputs
- **Interactive menu loop continues**: After a step completes, the menu shows again, but this
  is just the `weld implement` process looping - not a continued conversation
- **Session ID is shared**: If running inside Claude Code, all step executions share the same
  session ID for commit grouping purposes

### Example Flow

```bash
weld implement plan.md
# Step 1 executes → Fresh Claude invocation → Step completes
# Menu shows again
# Step 2 executes → NEW fresh Claude invocation → Step completes
# Menu shows again
# ...and so on
```

Each arrow represents a completely independent Claude CLI execution with no shared context.

## See Also

- [plan](plan.md) - Generate a plan to implement
- [Plan Format](../reference/plan-format.md) - How plans are structured
- [review](review.md) - Review changes after implementing
