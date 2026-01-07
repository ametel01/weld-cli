## Best practices for user docs for a Python CLI tool (OSS-grade)

### 1) Define your doc set (minimum viable, then scale)

**Minimum**

* **README.md**: fast onboarding + core commands.
* **`mycli --help`**: authoritative CLI reference for flags/args.
* **Command reference** (docs site or `/docs`): one page per command + examples.

**Common additions**

* **Installation**: pipx / uv tool install / pip / brew (if you ship it).
* **Configuration**: file format, env vars, precedence, locations.
* **Tutorials**: 2–3 end-to-end workflows users actually do.
* **How-to**: targeted tasks (“use dry-run”, “debug logging”, “CI integration”).
* **Troubleshooting**: known errors, exit codes, common gotchas.
* **FAQ**: concise answers, links to deeper docs.
* **Changelog** + **Upgrade notes**: breaking changes and migration steps.

---

### 2) Optimize for “first success in 2 minutes”

Your README should contain, in this order:

1. **One-sentence value** (what it does, who for).
2. **Install** (one preferred method, others collapsed).
3. **Quick start**: 3–5 commands that produce a visible result.
4. **Common workflows**: 2–4 examples.
5. **Configuration**: where config lives + minimal example.
6. **Support**: how to file issues, debug info to include.

Pattern for quick start:

```bash
uv tool install mycli
mycli init
mycli run plan.md
mycli status
```

---

### 3) Make the CLI self-documenting

**`--help` quality is part of docs quality.**

Best practices:

* Every command has:

  * short summary
  * longer help text
  * examples (even 1 is enough)
* Flags:

  * consistent naming (`--dry-run`, `--debug`, `--json`, `--config`, `--version`)
  * clear defaults shown in help output
* Subcommands are discoverable:

  * `mycli help`
  * `mycli <cmd> --help`

If using Typer/Click, invest in:

* good parameter names
* `help=` strings everywhere
* sane defaults

---

### 4) Document output contracts (users build automation)

If people will script your tool, document:

* **Exit codes** (table)
* **stdout vs stderr** behavior
* **JSON output schemas** (`--json`), stability guarantees:

  * “stable fields” vs “best-effort fields”
* **Determinism** expectations (ordering, timestamps, concurrency)

Example exit code contract:

* `0` success
* `1` runtime error
* `2` usage error (bad args/config)
* `3` partial success / some checks failed (if relevant)

---

### 5) Configuration docs: be explicit and testable

Users fail most often on config.

Include:

* **Search path** (e.g. current dir → XDG → home)
* **Precedence**: flags > env > config file > defaults
* **Full config reference** (generated if possible)
* A “minimal config” and a “full config” example
* Validation behavior: what happens on unknown keys / wrong types

If you support env vars, document them in a dedicated table:

* name, type, default, example, related flags.

---

### 6) Examples that match real user intent

Prefer “task-based” pages over exhaustive prose.

* “Run in dry-run mode to preview changes”
* “Enable debug logs and collect diagnostics for an issue”
* “Integrate with CI (GitHub Actions)”
* “Use JSON output with jq”
* “Handle non-zero exit codes in bash”

Each example should show:

* command
* expected output snippet (short)
* what to do next

---

### 7) Keep docs versioned and tied to releases

Best practice for OSS:

* Host docs per version (or at least “latest” + “stable”).
* At minimum: docs in repo; release tags preserve exact docs state.
* For breaking changes, add a dedicated **Upgrade Guide** section and link it from release notes.

---

### 8) Choose a docs toolchain that fits CLI repos

Recommended:

* **MkDocs + mkdocs-material**: simple, fast, great UX.
* Keep docs in `docs/`, build on CI, deploy to GitHub Pages.

Doc site structure that scales:

```
docs/
  index.md
  install.md
  quickstart.md
  commands/
    init.md
    run.md
    status.md
    checks.md
  config.md
  tutorials/
    workflow-basic.md
    ci-github-actions.md
  troubleshooting.md
  faq.md
```

---

### 9) Troubleshooting: include a diagnostics checklist

Have a “copy/paste for issues” section:

* `mycli --version`
* `python --version`
* OS info
* config file used
* command invoked
* `--debug` logs (redaction guidance)
* relevant output files/artifacts paths

Also document:

* common permission errors
* path issues
* lockfile/state issues (if your tool uses locks)
* proxy/network behavior (if applicable)

---

### 10) Doc quality gates (enterprise habit)

Add CI that fails if docs break:

* Build docs on PRs (MkDocs build)
* Check links (optional)
* Spellcheck (optional, but useful at scale)
* Ensure `--help` output is updated if you snapshot it

---

## Recommended “minimum bar” for your CLI (given your features like `--dry-run`, `--debug`, checks)

* README with install + quick start + “how it works” paragraph
* Command docs: `init`, `plan`, `implement`, `review`, `checks`, `status`, `commit`
* Config docs including new checks categories and defaults
* “CI integration” how-to
* Troubleshooting page covering locks, stale locks, debug logs, non-zero exit codes
* Output contract page (`--json`, exit codes)

If you share your command list (or `mycli --help` output), I can propose an exact docs IA (page tree) and draft the README + 2–3 core docs pages in your style.
