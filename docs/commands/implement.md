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
| `--auto-commit` | | Prompt to commit changes after each step completes |
| `--timeout` | `-t` | Timeout in seconds for Claude (default: from config) |

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

### With auto-commit

```bash
weld implement plan.md --auto-commit
```

After each step completes, you'll be prompted:

```
Commit changes from step 1.1? (y/n)
```

If you answer yes, all changes are staged and committed automatically using session-based
grouping (same as `weld commit --all`).

## Progress Tracking

When a step is completed, it's marked in the plan file:

```markdown
### Step 1: Create data models [COMPLETE]
```

## Auto-Commit

The `--auto-commit` flag enables automatic commit prompts after each step completes successfully.

### How It Works

1. After a step is marked complete, weld checks for uncommitted changes
2. If changes exist, you're prompted: `Commit changes from step X.X? (y/n)`
3. If you answer yes:
   - All changes are staged (`git add --all`)
   - A session-based commit is created with transcript
   - Files are grouped by their originating Claude Code session
4. If you answer no or press Ctrl+C, the prompt is skipped and execution continues

### Features

- **Non-blocking**: Commit failures don't stop the implement flow
- **Session-aware**: Uses the same session-based grouping as `weld commit`
- **Smart detection**: Skips prompt if no changes were made during the step
- **Dry-run compatible**: Shows what would happen without actually committing

### Example Usage

```bash
# Enable auto-commit in interactive mode
weld implement plan.md --auto-commit

# Works in non-interactive mode too
weld implement plan.md --step 1.1 --auto-commit
```

## Review Prompt

After each step completes, you'll be prompted to review the changes made during that step.

### How It Works

1. After a step is marked complete, weld checks for uncommitted changes
2. If changes exist, you're prompted: `Review changes from step X.X? (y/n)` (default: No)
3. If you answer yes, you're prompted: `Apply fixes directly to files? (y/n)` (default: No)
4. weld runs `weld review --diff` (or `--diff --apply` if you chose yes for fixes):
   - Generates a diff of all uncommitted changes
   - Sends to Claude for review
   - Saves findings to `.weld/reviews/{timestamp}/`
5. If you answer no or press Ctrl+C, the prompt is skipped and execution continues

### Features

- **Always available**: Independent of `--auto-commit` flag
- **Non-blocking**: Review failures don't stop the implement flow
- **Two-stage confirmation**: Separate prompts for review and auto-fix
- **Safe defaults**: Both prompts default to "No" for safety
- **Artifact preservation**: All reviews saved to `.weld/reviews/` with timestamps
- **Optional auto-fix**: Choose whether Claude should apply fixes directly or just report issues

### Security Note

When you choose to apply fixes directly, Claude runs with `skip_permissions=True`, allowing it to modify any file in the repository without additional prompts. Only enable this if you trust the review process.

### Example Usage

```bash
# Standard workflow with review prompts
weld implement plan.md

# After step completes:
✓ Step 1.1 marked complete

Review changes from step 1.1? [y/N]: y
Apply fixes directly to files? [y/N]: n

┌──────────────────────────────────┐
│ Reviewing step 1.1 changes       │
└──────────────────────────────────┘

claude> Found 2 style issues...

✓ Review complete
Results: .weld/reviews/20260109-143022-code-review-step1-1/findings.md
```

### Review Artifacts

Each review creates a timestamped directory in `.weld/reviews/`:

```
.weld/reviews/20260109-143022-code-review-step1-1/
├── prompt.md      # The prompt sent to Claude
├── diff.patch     # The diff that was reviewed
└── findings.md    # Claude's review findings (or fixes.md if auto-fix was used)
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

## Input Validation

Before starting the (potentially expensive) Claude operation, weld validates inputs upfront:

- **File existence**: Verifies the plan file exists
- **File type**: Ensures the path points to a file, not a directory

When validation fails, you'll see a clear error message with an actionable hint:

```
Error: plans/ is a directory, expected a file
Hint: Provide a valid plan file path
```

This prevents wasted API tokens from invalid inputs.

## See Also

- [plan](plan.md) - Generate a plan to implement
- [Plan Format](../reference/plan-format.md) - How plans are structured
- [review](review.md) - Review changes after implementing
