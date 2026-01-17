# Spec: Telegram Bot Integration for `weld-cli` (Monorepo)

## 0. Goals and non-goals

### Goals

1. Provide a **Telegram bot** interface to run `weld` workflows while away from the workstation: *research → plan → implement → review → commit*, plus environment checks (`doctor`). ([GitHub][1])
2. Support **multiple projects** (local repos), and optionally **branch/worktree selection** per run, borrowing the “remote agent runner + resume” interaction style demonstrated by Takopi. ([GitHub][2])
3. Stream progress back to Telegram (logs, step transitions, file changes summary).
4. Keep the integration **inside the `weld-cli` repo** (monorepo), released as part of the same package and versioning.
5. Be **safe-by-default**: explicit allowlists, minimal shell exposure, constrained command surface.

### Non-goals

* Not a generic Telegram automation framework.
* Not an alternative “engine” that replaces Weld’s prompt-generation/harness logic.
* No requirement to support every Telegram feature on day 1 (voice dictation, file browser UX, etc.). (Design should not block adding them later.)

---

## 1. User experience (Telegram)

### Core interaction model

* The bot is a **remote control** for `weld` runs inside registered local repos.
* A “run” is initiated from Telegram, executed on the workstation/server where `weld telegram serve` is running, and streamed back.
* The bot supports “resume” semantics: after completion, user can reply with follow-up instructions to continue in same context, similar to Takopi’s “reply to continue” concept. ([GitHub][2])

### Commands (Telegram slash commands)

All commands must work in:

* Direct message chat
* Group chat (optional v1)
* Topic-based group (optional v2)

#### `/help`

Shows:

* Available commands
* Current project/branch context
* Security mode (safe mode on/off)
* Link/instructions for local setup (`weld telegram init`)

#### `/projects`

Lists known projects:

* `name`
* absolute path (redacted by default; show only basename unless `--verbose`)
* default branch
* whether worktree mode is enabled

#### `/use <project> [@branch]`

Sets the active context for subsequent commands.

* Example: `/use horizon @feat/pt-v2`
* Reply: “Context set: horizon (branch feat/pt-v2)”

#### `/status`

Shows:

* active context
* queue depth (per context)
* current run (if any): id, phase, elapsed time
* last 5 completed runs (id, summary)

#### `/run <weld-subcommand> [args…]`

Runs a **restricted subset** of weld commands (see allowlist below).

* Example: `/run plan specs/feature.md -o plan.md`

#### Shortcut commands

* `/doctor`
* `/plan <spec_path> [-o <out>]`
* `/interview <spec_path> [-o <out>]`
* `/implement <plan_path>`
* `/commit [--all | --path <p>] [--message <m>]`

These must translate 1:1 into the internal `weld` CLI invocation.

#### `/cancel [run_id]`

Requests cancellation:

* If no id provided, cancels the current run in that chat context.
* Cancellation is cooperative (terminate subprocess, clean up worktree lock, mark run canceled).

#### `/fetch <path>`

Sends back:

* a file, if `<path>` is file
* a zipped archive, if `<path>` is directory (size limit enforcement)

#### `/push <path>`

User uploads a file to Telegram; bot saves it into repo at `<path>` (must be within repo root; no `..` traversal).

### Message streaming format

During execution, the bot posts:

1. **Run header** message (single message edited in-place when possible):

   * Run id, project, branch/worktree
   * Command invoked
   * Phase (e.g., PLAN, IMPLEMENT, COMMIT)
   * Elapsed time
2. **Streaming updates**:

   * throttle: at most once per 2 seconds or per 4KB of new output
   * chunk stdout/stderr into Telegram-sized messages
   * optionally attach a “diff summary” at end:

     * list of changed files
     * counts of additions/deletions (best-effort via `git diff --stat`)

### “Resume” behavior

If user replies to a previous run’s header message:

* treat it as continuation in the same context
* by default: interpret reply as `/run plan|implement` depending on last phase (see §5 routing)

This mirrors Takopi’s “reply to continue” behavior. ([GitHub][2])

---

## 2. Local CLI UX (`weld` subcommands)

Add a new top-level command group:

* `weld telegram init`
* `weld telegram serve`
* `weld telegram projects ...`
* `weld telegram whoami`
* `weld telegram doctor`
* `weld telegram run ...` (local equivalent of `/run` for debugging)

### `weld telegram init`

Interactive wizard (non-interactive flags supported) inspired by Takopi’s onboarding flow. ([GitHub][2])
Collects and writes config:

* Bot token
* Allowed chat id(s)
* Allowed Telegram user id(s) (optional but recommended)
* Default repo registration (optional)
* Storage paths

Outputs:

* Config file path
* A test instruction: “Send `/whoami` to the bot now.”

### `weld telegram serve`

Runs the bot server:

* long-running polling mode (v1)
* optional webhook mode (v2)
* reads config
* starts run queue workers
* emits structured logs

Flags:

* `--config <path>`
* `--log-level`
* `--dry-run` (no subprocess execution; useful for tests)
* `--unsafe` (enables broader command execution; default false)

### `weld telegram projects add <name> <path>`

Registers a repo.

### `weld telegram projects remove <name>`

Unregisters.

### `weld telegram projects list`

Lists.

---

## 3. Safety and security model

### Authentication / authorization

Minimum viable:

* Allowlist **chat IDs**: only handle messages originating from configured chats.
* Allowlist **user IDs** inside those chats (optional but recommended).
* Reject everything else with no side effects.

Recommended extras:

* Optional per-chat **shared secret**:

  * user must run `/auth <passphrase>` once per chat (store hashed token, expire after N days)
* Rate limiting:

  * max commands/minute per user
  * max concurrent runs per chat = 1 (default)

### Command allowlist (safe mode default)

Only allow these weld invocations:

* `weld doctor`
* `weld plan ...`
* `weld interview ...`
* `weld implement ...`
* `weld commit ...`
* `weld init` (optional; off by default)

Explicitly disallow:

* arbitrary shell commands
* arbitrary `git push` from Telegram (if added later, require explicit confirmations and a “trusted mode”)

### Filesystem confinement

All file paths received from Telegram must be:

* normalized
* validated to remain under repo root
* reject symlink escapes (best-effort: resolve realpath and compare prefixes)

### Secrets handling

* Bot token must never be printed in logs.
* Config file permissions: enforce `0600` on creation.
* Provide an optional `WELD_TELEGRAM_TOKEN` env override.

---

## 4. Monorepo layout (inside `weld-cli`)

Proposed structure:

```
weld-cli/
  src/weld/
    telegram/
      __init__.py
      cli.py               # weld telegram ... command group
      bot.py               # telegram update handling + routing
      config.py            # config schema + load/save
      auth.py              # allowlists, optional auth
      runner.py            # subprocess execution + streaming
      queue.py             # per-context queue/locks
      state.py             # sqlite models or json store
      worktrees.py         # optional worktree management
      files.py             # fetch/push helpers + path validation
      format.py            # telegram message formatting + chunking
  tests/
    telegram/
      test_routing.py
      test_auth.py
      test_paths.py
      test_runner_streaming.py
```

Notes:

* Keep Telegram integration as an internal package under `weld.telegram`.
* Expose a CLI entry via the existing `weld` console script (same package/version). ([GitHub][1])

---

## 5. Execution architecture

### Components

1. **Telegram Transport**: receives updates, sends messages.
2. **Router**: maps Telegram messages to internal actions (commands).
3. **Context Resolver**: picks (project, branch/worktree, cwd).
4. **Run Queue**: serializes runs per context and/or per chat.
5. **Runner**: spawns `weld` subprocess, streams output events.
6. **State Store**: persists:

   * chat contexts
   * registered projects
   * run history
   * message ids for editing updates

This is the same high-level “bridge + runner + streaming + resume” shape that Takopi advertises. ([GitHub][2])

### Run lifecycle states

`QUEUED -> RUNNING -> (SUCCEEDED | FAILED | CANCELED)`

Each run stores:

* `run_id` (uuid)
* `chat_id`
* `user_id`
* `project_name`
* `repo_path`
* `branch` or `worktree_path`
* `command` (normalized list of args)
* timestamps: created/started/ended
* exit code
* summary:

  * last 50 lines of output (for quick recall)
  * changed files summary (optional)

### Output streaming events

Runner emits events:

* `RUN_STARTED`
* `STDOUT_CHUNK`
* `STDERR_CHUNK`
* `PHASE_CHANGED` (if detectable)
* `RUN_FINISHED`
* `RUN_FAILED`
* `RUN_CANCELED`

Telegram formatter converts events to:

* edited header message (status)
* appended chunk messages (output)

---

## 6. Worktree/branch support (optional but designed-in)

### Modes

* **Simple mode (v1 default)**: run in the repo’s current working tree.
* **Worktree mode (v2)**: each `@branch` maps to a dedicated git worktree path.

Takopi uses git worktrees for parallel repo/branch contexts. Adopt the same pattern. ([GitHub][2])

### Worktree rules

* Root folder: `~/.weld/worktrees/<project>/<branch-sanitized>/`
* If worktree exists: reuse.
* Else:

  * `git worktree add ...`
  * optionally `git fetch` (configurable)
* Lock: only one run per worktree at a time.

---

## 7. Configuration

### Config file location

Default: `~/.config/weld/telegram.toml` (Linux/macOS)

* Allow override via `--config` or env var `WELD_TELEGRAM_CONFIG`.

### Config schema (TOML)

Example:

```toml
[telegram]
token = "..."                # or omit and use env
allowed_chat_ids = [12345]
allowed_user_ids = [111, 222]
poll_interval_seconds = 1.0
edit_header_message = true

[storage]
state_dir = "~/.weld/telegram"
db_path = "~/.weld/telegram/state.db"
runs_dir = "~/.weld/telegram/runs"
worktrees_dir = "~/.weld/worktrees"

[security]
safe_mode = true
require_auth = false
auth_ttl_days = 14

[defaults]
project = "default"
branch = "main"

[[projects]]
name = "default"
path = "/home/alex/dev/default"
worktrees = false
```

---

## 8. Mapping Telegram commands to `weld` invocations

### Normalization rules

* Parse user text into:

  * command name
  * args
* Validate against allowlist
* Convert to subprocess argv:

  * `["weld", <subcmd>, ...]`
* Always run with `cwd=<resolved repo/worktree path>`.

### Examples

* `/doctor` → `weld doctor`
* `/plan specs/x.md -o plan.md` → `weld plan specs/x.md -o plan.md`
* `/implement plan.md` → `weld implement plan.md`
* `/commit --all` → `weld commit --all`

This matches Weld’s documented workflow and command set (init/doctor/plan/implement/commit). ([GitHub][1])

---

## 9. Observability

### Logging

* Structured logs (json-lines) recommended for `serve`.
* Log fields:

  * chat_id, user_id, run_id, project, branch, phase, event_type

### Metrics (optional)

* counters: runs_succeeded, runs_failed, runs_canceled
* histogram: run_duration_seconds

---

## 10. Testing strategy

### Unit tests

* Routing:

  * command parsing
  * context resolution
  * allowlist enforcement
* Path security:

  * reject `..`
  * reject absolute paths (unless explicitly permitted)
  * reject symlink escape
* Runner:

  * streaming chunk logic
  * cancel behavior

### Integration tests (no real Telegram)

* Mock transport interface:

  * feed “Update” objects
  * capture outbound messages
* Dry-run mode:

  * ensures commands are “accepted” without spawning

---

## 11. Implementation milestones

### Milestone 1: MVP (safe-mode, single repo)

* `weld telegram init`
* `weld telegram serve` (polling)
* Allowlist: `doctor`, `plan`, `implement`, `commit`, `interview`
* One configured project, no branches/worktrees
* Streaming stdout/stderr
* State store: sqlite or single JSON file

### Milestone 2: Multi-project + `/use`

* Project registry commands
* Context per chat
* `/projects`, `/use`, `/status`

### Milestone 3: Worktrees + concurrency

* `@branch` selector
* per-worktree locking + queue

### Milestone 4: File transfer

* `/fetch`, `/push`

---

## 12. Open questions (must be decided in research doc)

1. Telegram library choice (`python-telegram-bot` vs `aiogram`) and why.
2. State store choice (sqlite vs json + file locks).
3. How to detect Weld “phases” reliably (parse structured output? add `--json-events` to weld?).
4. Whether to support group topics as first-class “contexts” (Takopi does). ([GitHub][2])
5. Whether to implement a plugin surface (Takopi supports plugins; you may not need this for Weld v1). ([GitHub][2])

---

## 13. Acceptance criteria (MVP)

* From a phone, user can:

  1. Run `/doctor` and receive output.
  2. Run `/plan specs/feature.md -o plan.md` and see progress + completion message.
  3. Run `/implement plan.md` and see streamed progress.
  4. Run `/status` and view current/last run.
  5. Unauthorized chat/user is rejected with no execution.
* Bot runs reliably as a single process on the workstation/server.
* All paths are confined to repo root; no traversal escapes.
* Packaging: `uv tool install weld-cli` includes Telegram integration with no extra repo. ([GitHub][1])

[1]: https://github.com/ametel01/weld-cli "GitHub - ametel01/weld-cli: Human-in-the-loop coding harness with transcript provenance"
[2]: https://github.com/banteg/takopi "GitHub - banteg/takopi: he just wants to help-pi!"
