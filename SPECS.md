## Python harness spec: `weld` (Claude Code implementer + OpenAI Codex CLI reviewer + transcript-linked commits) — **uv required**

### Objectives

* Encode your workflow as a deterministic, auditable pipeline:

  1. Claude Code reads a spec doc → produces implementation plan
  2. Codex reviews/amends plan
  3. Claude implements step *x*
  4. Codex reviews implementation vs plan and reports issues
  5. Loop 3–4 until no issues remain (or only non-blocking issues per config)
  6. Create git commit with transcript link in commit message
* Automate reliably:

  * Codex stages are fully non-interactive via OpenAI CLI
  * Diffs, checks, step parsing, issues, iteration control, commit message building are automated
* Keep Claude Code human-in-the-loop but low-friction:

  * `weld` generates exact prompts and fix lists for copy/paste
  * `weld` validates progress via diff + checks + Codex review
* Preserve provenance:

  * Every run writes a structured artifact directory under `.weld/runs/<run_id>/`
  * Every iteration stores prompts, diffs, check output, Codex review, issues JSON, status JSON

---

## Hard requirements

* Python **3.11+**
* Package manager: **`uv` only** (strict requirement)

  * No pip/poetry/pipenv workflows in docs or tooling
* External CLIs available in PATH:

  * `git`
  * `gh` (GitHub CLI) authenticated
  * `codex` (OpenAI Codex CLI)
  * `claude-code-transcripts` (for transcript → gist)

---

## Repository layout (created/managed by `weld`)

```
repo/
  pyproject.toml
  .python-version
  .weld/
    config.toml
    runs/
      <run_id>/
        meta.json
        inputs/
          spec.ref.json
        plan/
          claude.prompt.md
          claude.output.md
          plan.raw.md
          codex.prompt.md
          codex.output.md
          plan.final.md
        steps/
          01-<slug>/
            step.json
            prompt/
              claude.impl.prompt.md
              codex.review.prompt.md
              claude.fix.prompt.iter02.md
            iter/
              01/
                diff.patch
                checks.txt
                codex.review.md
                codex.issues.json
                status.json
              02/...
        commit/
          message.txt
          transcript.json
        summary.md
  src/
    weld/
      __init__.py
      cli.py
      config.py
      run.py
      plan.py
      step.py
      review.py
      loop.py
      commit.py
      git.py
      codex.py
      transcripts.py
      checks.py
      diff.py
      models/
        meta.py
        step.py
        issues.py
        status.py
```

---

## Installation and execution (uv-only)

### Create environment and install editable

```bash
uv venv
uv pip install -e .
```

### Run

```bash
weld init
weld run start --spec specs/horizon.md
```

---

## `pyproject.toml` (uv-native)

```toml
[project]
name = "weld"
version = "0.1.0"
description = "Human-in-the-loop coding harness: plan, review, iterate, commit with transcript provenance"
requires-python = ">=3.11"
dependencies = [
  "typer>=0.12",
  "pydantic>=2.6",
  "rich>=13.7",
  "tomli-w>=1.0",
]

[project.scripts]
weld = "weld.cli:app"

[tool.uv]
dev-dependencies = [
  "pytest>=8",
  "ruff>=0.5",
  "mypy>=1.10",
]

[tool.ruff]
line-length = 100
```

`.python-version` should contain `3.11` (or your chosen 3.11+ minor).

---

## Configuration (`.weld/config.toml`)

### Required keys

```toml
[project]
name = "your-project"

[checks]
command = "bun test && bun lint"

[codex]
exec = "codex"
sandbox = "read-only"
# model = "..."   # optional

[claude.transcripts]
exec = "claude-code-transcripts"
visibility = "secret" # or "public"

[git]
commit_trailer_key = "Claude-Transcript"
include_run_trailer = true

[loop]
max_iterations = 5
fail_on_blockers_only = true
```

### Notes

* `checks.command` runs from repo root and its output is always captured.
* `codex.sandbox=read-only` ensures Codex only reviews.

---

## CLI contract

### `weld init`

* Creates `.weld/config.toml` template if missing
* Creates `.weld/runs/`
* Validates toolchain:

  * `git`, `gh auth status`, `codex`, `claude-code-transcripts`
* Writes tool versions into `.weld/config.toml` comment block (optional) or prints them.

Exit codes:

* `0` ok
* `2` dependency missing / unauthenticated `gh`
* `3` not a git repo

---

### `weld run start --spec <path> [--name <slug>]`

Creates a new run directory.

Writes:

* `.weld/runs/<run_id>/meta.json` (timestamps, repo root, branch, HEAD sha, config hash)
* `inputs/spec.ref.json` (absolute path, sha256, size, optional git blob id)
* `plan/claude.prompt.md` (prompt for Claude to produce plan)

Prints to terminal:

* Path to `plan/claude.prompt.md`
* The prompt contents (for copy/paste)

`run_id` format:

* `YYYYMMDD-HHMMSS-<slug>` (slug defaults to sanitized spec basename)

---

### `weld plan import --run <run_id> --file <plan_md>`

Imports Claude’s plan output (verbatim).

Writes:

* `plan/claude.output.md` (verbatim)
* `plan/plan.raw.md` (normalized with welded front-matter)

Normalization rules:

* Ensure numbered steps exist; if not, record `plan_parse_warnings` in `meta.json`
* Preserve content; do not rewrite semantics here

---

### `weld plan review --run <run_id> [--apply]`

Runs Codex to review/amend plan (Step 2).

Writes:

* `plan/codex.prompt.md`
* `plan/codex.output.md`
* If `--apply`: `plan/plan.final.md` (the revised plan extracted from codex output)

Codex review must output in Markdown sections:

* `Findings`
* `Revised Plan` (full plan)
* `Risk Notes`

Parsing:

* `plan.final.md` is extracted from the `Revised Plan` section (strict header match in default mode)

---

### `weld step select --run <run_id> --n <int>`

Selects step N from `plan.final.md` (or `plan.raw.md` if final absent).

Writes:

* `steps/<NN>-<slug>/step.json`
* `steps/<NN>-<slug>/prompt/claude.impl.prompt.md`

Step extraction (default “strict” plan format strongly encouraged):

* `## Step N: <Title>`
* `### Goal`
* `### Changes`
* `### Acceptance criteria`
* `### Tests`

Lenient fallback:

* Step begins with `N.` line, continues until next `^\d+\.`

`step.json` structure:

* `n`, `title`, `slug`
* `body_md`
* `acceptance_criteria[]`
* `tests[]`

---

### `weld step prompt --run <run_id> --n <int>`

Regenerates the Claude implement prompt (idempotent).

`claude.impl.prompt.md` contents:

* Step text (verbatim)
* Acceptance criteria checklist
* Test commands from config
* Scope boundary: “Only implement this step”
* “Minimize churn; no refactors unless necessary to satisfy criteria”
* “If you change interfaces, update typing/tests accordingly”

---

### `weld step snapshot --run <run_id> --n <int> [--iter <k>]`

Captures repo state for iteration `k`.

Writes under `iter/<k>/`:

* `diff.patch`

  * from `git diff` (default) or `git diff --staged` if configured
* `checks.txt`

  * runs `checks.command`
  * records exit code (prefix line)

Rules:

* If diff is empty: write status with `diff_nonempty=false` and stop (review won’t run)

---

### `weld step review --run <run_id> --n <int> [--iter <k>]`

Runs Codex review against step + diff + checks.

Writes:

* `prompt/codex.review.prompt.md` (template instantiation)
* `iter/<k>/codex.review.md`
* `iter/<k>/codex.issues.json`
* `iter/<k>/status.json`

Codex output contract:

* `codex.review.md` is free-form Markdown, but the **last line** must be strict JSON:

```json
{"pass":true,"issues":[{"severity":"blocker","file":"path","hint":"...","maps_to":"AC #2"}]}
```

`status.json` derived fields:

* `pass`
* `issue_count`, `blocker_count`, `major_count`, `minor_count`
* `checks_exit_code`
* `diff_nonempty`
* `timestamp`

Pass logic:

* If `fail_on_blockers_only=true`: pass iff `blocker_count == 0`
* Else: pass iff `issue_count == 0`

---

### `weld step fix-prompt --run <run_id> --n <int> --iter <k>`

Generates Claude fix prompt for next iteration.

Writes:

* `prompt/claude.fix.prompt.iter<k+1>.md`

Content:

* Issues grouped by severity
* For each issue: file + hint + mapping to acceptance criterion
* Scope boundary: “Fix these issues only; no refactors/churn”
* Re-run checks

---

### `weld step loop --run <run_id> --n <int> [--max <m>] [--wait]`

Implements the main loop (Steps 3–5).

Behavior:

1. Ensure step selected (or auto-call `step select`)
2. Iteration 1:

   * Print Claude implement prompt path + content
   * If `--wait`: pause until user presses enter
3. Snapshot diff+checks
4. Codex review
5. If pass: stop success
6. Else:

   * Generate fix prompt, print it
   * If `--wait`: pause for Claude Code edits, then repeat
7. Stop when pass or `max_iterations` reached

Writes:

* `steps/<slug>/history.log` (append each iteration summary)

Exit codes:

* `0` success
* `10` max iterations reached
* `11` checks failed (optional strict mode; configurable)
* `12` codex invocation failed / malformed JSON

---

## Transcript → Gist stage (Step 6)

### `weld transcript gist --run <run_id> [--session latest|pick]`

Runs `claude-code-transcripts --gist` and extracts URLs.

Writes:

* `commit/transcript.json`:

  * `gist_url`
  * `preview_url` (if present)
  * `raw_output`
  * `warnings[]` (e.g., repo auto-detect failure)

Parsing:

* `Gist: <url>` line is authoritative
* `Preview: <url>` line optional

Behavior on “Could not auto-detect GitHub repo”:

* Record warning; proceed if gist URL exists.

---

## Commit stage (Step 6)

### `weld commit --run <run_id> -m "<message>" [--session latest|pick] [--all|--staged]`

Default mode: `--staged` (only staged changes).

Behavior:

1. Verify repo state:

   * if `--staged` and no staged changes → fail
   * if `--all` → stage all (`git add -A`)
2. Ensure transcript gist URL exists (call `weld transcript gist` if needed)
3. Write `commit/message.txt`:

   * subject line = `-m`
   * blank line
   * optional body: step summary + checks status
   * trailers:

     * `<commit_trailer_key>: <gist_url>`
     * `Weld-Run: .weld/runs/<run_id>` (if enabled)
4. `git commit -F commit/message.txt`
5. Update `summary.md` with commit SHA + gist URL

Exit codes:

* `0` committed
* `20` no changes to commit
* `21` transcript generation failed (no gist url)
* `22` git commit failed

---

## Codex adapter (OpenAI CLI) — strict behavior

### Invocation

* Use `codex exec` in **read-only sandbox** for all reviews.

### Plan review prompt requirements

* Must output the full revised plan in a clearly delimited section so `weld` can extract it.

### Implementation review prompt requirements

* Must include:

  * Step text and acceptance criteria
  * Diff
  * Checks output
* Must emit final-line JSON as specified.

### Robustness checks

* If JSON parse fails:

  * store full output
  * mark status `pass=false`
  * surface error with path to `codex.review.md`

---

## Data models (pydantic)

### `Meta`

* run_id, timestamps
* repo_root, branch, head_sha
* config_hash
* tool versions

### `Step`

* n, title, slug
* acceptance_criteria[], tests[]
* body_md

### `Issues`

* pass: bool
* issues[]: severity/file/hint/maps_to

### `Status`

* derived counts
* checks_exit_code
* diff_nonempty
* pass
* timestamp

---

## Implementation details (Python)

### Runtime and packaging

* Python 3.11+
* `typer` CLI
* `pydantic` for JSON contracts
* `rich` for terminal UX
* `tomli-w` to write config template
* subprocess for all external tools

### Subprocess rules

* Always `cwd=repo_root`
* Always capture stdout+stderr and persist to artifact files
* Never assume interactive tools unless explicitly in `--wait` mode

### Git interaction

Use subprocess `git` commands (no GitPython):

* `git rev-parse --show-toplevel`
* `git diff`, `git diff --staged`
* `git status --porcelain`
* `git add -A` (only `--all`)
* `git commit -F`

---

## UX behavior tailored to you

* “Clipboard-first” for Claude Code:

  * prompts are written to files and also printed to stdout
* “Single command loop”:

  * during implementation you mostly run:

    * `weld step loop --run <id> --n N --wait`
* Everything is inspectable on disk under `.weld/runs/...`

---

## Definition of done

You can run end-to-end:

```bash
uv venv
uv pip install -e .

weld init
weld run start --spec specs/horizon.md

# paste Claude plan into plan.md
weld plan import --run <run_id> --file plan.md
weld plan review --run <run_id> --apply

weld step loop --run <run_id> --n 1 --wait

weld commit --run <run_id> -m "Implement step 1" --staged
```

Result:

* `.weld/runs/<run_id>/` contains all artifacts
* commit message contains `Claude-Transcript: <gist-url>` trailer
* iteration loop stops only when Codex review criteria are satisfied (per config)
