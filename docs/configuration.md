# Configuration

Configuration lives in `.weld/config.toml`, created by `weld init`.

## Version Control

**Only `.weld/config.toml` should be committed** to version control. All other `.weld/` files are excluded via `.gitignore` (automatically configured during `weld init`):

- ✓ **Tracked**: `.weld/config.toml` (project configuration)
- ✗ **Ignored**: `.weld/sessions/`, `.weld/reviews/`, `.weld/commit/history.jsonl`, etc. (local metadata)

This ensures team members share configuration while keeping local session data and review artifacts private.

## Full Configuration Reference

```toml
[project]
name = "your-project"

[checks]
lint = "ruff check ."
test = "pytest tests/ -q"
typecheck = "pyright"
order = ["lint", "typecheck", "test"]

[codex]
exec = "codex"
sandbox = "read-only"

[claude]
exec = "claude"                    # Claude CLI path
model = "claude-sonnet-4-20250514" # Default model (optional)
timeout = 1800                     # Timeout in seconds (30 min default)
max_output_tokens = 128000         # Max tokens for responses (128K default)

[transcripts]
enabled = true                     # Enable transcript generation
visibility = "secret"              # Gist visibility: "secret" or "public"

[git]
commit_trailer_key = "Claude-Transcript"
include_run_trailer = true

[loop]
max_iterations = 5
fail_on_blockers_only = true

[task_models.discover]
provider = "claude"

[task_models.interview]
provider = "claude"

[task_models.research]
provider = "claude"

[task_models.research_review]
provider = "codex"

[task_models.plan_generation]
provider = "claude"

[task_models.plan_review]
provider = "codex"

[task_models.implementation]
provider = "claude"

[task_models.implementation_review]
provider = "codex"

[task_models.fix_generation]
provider = "claude"

# Prompt customization (optional)
# [prompts]
# global_prefix = "This is a Python project."
# global_suffix = "Include type hints."
#
# [prompts.discover]
# prefix = "Focus on the API layer."
# default_focus = "architecture"
```

## Configuration Options

### `[project]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `name` | string | Directory name | Project name |

### `[checks]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `lint` | string | `"ruff check ."` | Lint command |
| `test` | string | `"pytest tests/ -q"` | Test command |
| `typecheck` | string | `"pyright"` | Type checking command |
| `order` | array | `["lint", "typecheck", "test"]` | Execution order for checks |

### `[codex]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `exec` | string | `"codex"` | Path to Codex CLI |
| `sandbox` | string | `"read-only"` | Sandbox mode |
| `model` | string | - | Default model for Codex provider |

### `[claude]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `exec` | string | `"claude"` | Path to Claude CLI |
| `model` | string | - | Default model to use |
| `timeout` | integer | `1800` | Timeout in seconds for AI operations |
| `max_output_tokens` | integer | `128000` | Maximum output tokens for responses |

### `[transcripts]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Enable transcript generation |
| `visibility` | string | `"secret"` | Gist visibility: `"secret"` or `"public"` |

### `[git]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `commit_trailer_key` | string | `"Claude-Transcript"` | Key for transcript trailer in commits |
| `include_run_trailer` | boolean | `true` | Include run trailer in commits |

### `[loop]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_iterations` | integer | `5` | Maximum review-fix loop iterations |
| `fail_on_blockers_only` | boolean | `true` | Only fail on blocker-level issues |

### `[task_models]`

Per-task model assignments. Each task can specify:
- `provider`: `"claude"`, `"codex"`, or other supported provider
- `model`: Optional specific model name (e.g., `"claude-opus-4-20250514"`)
- `exec`: Optional override for executable path

Available task types:
- `discover`: Codebase discovery
- `interview`: Specification refinement
- `research`: Research prompts
- `research_review`: Review research outputs
- `plan_generation`: Generate implementation plans
- `plan_review`: Review plans
- `implementation`: Execute implementation steps
- `implementation_review`: Review implementation changes
- `fix_generation`: Generate fixes for issues

Example:
```toml
[task_models.implementation]
provider = "claude"
model = "claude-opus-4-20250514"
```

### `[prompts]`

Customize AI prompts with project-specific context. Customizations are applied in layers:

```
global_prefix → task_prefix → prompt → task_suffix → global_suffix
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `global_prefix` | string | - | Text prepended to all prompts |
| `global_suffix` | string | - | Text appended to all prompts |

Per-task customizations use `[prompts.<task_type>]` sections:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `prefix` | string | - | Text prepended to this task's prompts |
| `suffix` | string | - | Text appended to this task's prompts |
| `default_focus` | string | - | Default `--focus` value when not specified |

Available task types: `discover`, `interview`, `research`, `research_review`, `plan_generation`, `plan_review`, `implementation`, `implementation_review`, `fix_generation`, `doc_review`, `code_review`, `commit`.

Example:
```toml
[prompts]
global_prefix = "This is a Python 3.12 project using FastAPI and SQLAlchemy."
global_suffix = "Always include type hints and docstrings."

[prompts.discover]
prefix = "Focus on the data model and API layer."
default_focus = "architecture"

[prompts.research]
prefix = "Consider security implications."
suffix = "Include a risk assessment section."
default_focus = "security"

[prompts.plan_generation]
prefix = "Plans should be incremental and testable."
```

Use `weld prompt list` to see all task types and their customization status. See the [prompt command](commands/prompt.md) for more details.

## Minimal Configuration

```toml
[project]
name = "my-project"
```

All other values use sensible defaults.

## Output Token Limit

Weld sets Claude's output token limit to **128,000 tokens** by default (via `CLAUDE_CODE_MAX_OUTPUT_TOKENS`). This is sufficient for most operations.

### Handling Token Limit Errors

If you encounter an error like:

```
API Error: Claude's response exceeded the output token maximum.
```

The error message will include a helpful fix:

```
Output token limit exceeded.

  Fix: Increase [claude].max_output_tokens in .weld/config.toml
  Current setting: 128000
```

To resolve, increase the limit:

```toml
[claude]
max_output_tokens = 200000  # Increase for very large documents
```

## Configuration Precedence

1. **Command-line flags** (highest priority)
2. **Environment variables** (where applicable)
3. **`.weld/config.toml`**
4. **Default values** (lowest priority)

## See Also

- [Troubleshooting](troubleshooting.md) - Common configuration issues
- [Commands Reference](commands/index.md) - Command-specific options
