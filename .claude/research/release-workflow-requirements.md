# Research: Release Workflow Requirements

## Executive Summary

This research documents the requirements for implementing a fully automated OSS release workflow for `weld-cli`. The workflow is triggered by pushing a git tag `vX.Y.Z`, runs quality gates, validates version consistency between tag/pyproject.toml/CHANGELOG.md, and publishes to both PyPI (via Trusted Publishing) and GitHub Releases with auto-extracted release notes.

**Key insight**: The codebase already has most infrastructure in place (CI workflow, Makefile release target, proper CHANGELOG format). Implementation requires:
1. Creating two Python scripts in `scripts/`
2. Creating a new GitHub Actions workflow `release.yml`
3. Configuring PyPI Trusted Publisher (one-time manual step)

---

## Current State Analysis

### What Exists

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| Version in pyproject.toml | ✅ Exists | `pyproject.toml:7` | `version = "0.3.0"` |
| Version in __init__.py | ✅ Exists | `src/weld/__init__.py:3` | `__version__ = "0.3.0"` |
| CHANGELOG.md | ✅ Exists, compliant | `CHANGELOG.md` | Uses Keep a Changelog format |
| `## [Unreleased]` section | ✅ Exists | `CHANGELOG.md:8` | Currently empty |
| Versioned sections | ✅ Exists | `CHANGELOG.md:10,23,117` | `## [0.3.0]`, `## [0.2.0]`, `## [0.1.0]` |
| CI workflow | ✅ Exists | `.github/workflows/ci.yml` | lint, test, security jobs |
| Makefile release target | ✅ Exists | `Makefile:268-289` | Uses `gh release create` with awk extraction |
| scripts/ directory | ❌ Missing | N/A | Need to create |
| release.yml workflow | ❌ Missing | N/A | Need to create |
| Trusted Publisher config | ❌ Missing | PyPI settings | One-time manual setup |

### Current CHANGELOG Format

The CHANGELOG already uses Keep a Changelog format (verified in `CHANGELOG.md:1-6`):

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-01-07
### Added
...
```

The bottom of the file contains comparison links:
```markdown
[Unreleased]: https://github.com/user/weld-cli/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/user/weld-cli/compare/v0.2.0...v0.3.0
```

### Current Makefile Release Target

`Makefile:268-289` has a working `release` target:
```makefile
.PHONY: release
release: ## Create GitHub release from CHANGELOG (usage: make release VERSION=0.2.0)
ifndef VERSION
	@echo -e "$(YELLOW)Usage: make release VERSION=x.y.z$(NC)"
	...
else
	@echo -e "$(BLUE)Creating release v$(VERSION)...$(NC)"
	@if ! grep -q "## \[$(VERSION)\]" CHANGELOG.md; then \
		echo -e "$(YELLOW)Error: Version $(VERSION) not found in CHANGELOG.md$(NC)"; \
		exit 1; \
	fi
	gh release create v$(VERSION) \
		--title "v$(VERSION)" \
		--notes "$$(awk '/^## \[$(VERSION)\]/{flag=1; next} /^## \[/{flag=0} flag' CHANGELOG.md)"
	@echo -e "$(GREEN)Release v$(VERSION) created!$(NC)"
endif
```

This uses `awk` for CHANGELOG extraction. The spec wants Python scripts instead for robustness.

---

## Implementation Requirements

### 1. Create `scripts/` Directory

```bash
mkdir -p scripts/
```

### 2. Create `scripts/extract_release_notes.py`

**Purpose**: Extract release notes for version X.Y.Z from CHANGELOG.md and write to RELEASE_NOTES.md.

**Spec from RELEASE_WORKFLOW.md:81-101**:
```python
import re, sys, pathlib

version = sys.argv[1]
text = pathlib.Path("CHANGELOG.md").read_text(encoding="utf-8")

pattern = rf"""
^##\s+\[{re.escape(version)}\][^\n]*\n
(.*?)
(?=^##\s+\[|\Z)
"""

m = re.search(pattern, text, re.S | re.M | re.X)
if not m:
    raise SystemExit(f"CHANGELOG.md missing section for [{version}]")

notes = m.group(1).strip()
pathlib.Path("RELEASE_NOTES.md").write_text(notes + "\n", encoding="utf-8")
```

**Behavior**:
- Takes version string as CLI argument (without `v` prefix)
- Finds section header matching `^## \[X.Y.Z\]` (date suffix optional)
- Captures everything until next `^## \[` or EOF
- Excludes the header line itself
- Preserves all markdown below (including nested headings)
- Writes to `RELEASE_NOTES.md`
- Exits non-zero if section not found

### 3. Create `scripts/assert_unreleased_empty.py`

**Purpose**: Verify the `## [Unreleased]` section is empty before release.

**Spec from RELEASE_WORKFLOW.md:110-120**:
```python
import re, pathlib

text = pathlib.Path("CHANGELOG.md").read_text(encoding="utf-8")
m = re.search(r"^##\s+\[Unreleased\]\n(.*?)(?=^##\s+\[|\Z)", text, re.S | re.M)

if m and m.group(1).strip():
    raise SystemExit("Unreleased section is not empty — move entries into the release section before tagging.")
```

**Behavior**:
- Reads CHANGELOG.md
- Extracts body of `## [Unreleased]` section
- If non-whitespace content exists, exits with error message
- Silent success if empty

### 4. Create `.github/workflows/release.yml`

**Trigger**: Push of tags matching `v*`

**Permissions**:
- `contents: write` - for creating GitHub Release
- `id-token: write` - for PyPI Trusted Publishing

**Jobs**:

1. **Checkout** with full history (`fetch-depth: 0`)
2. **Setup Python** (3.11)
3. **Install uv** via `astral-sh/setup-uv@v3`
4. **Sync deps** with `uv sync --frozen`
5. **Quality gates**:
   - `uv run ruff format --check .`
   - `uv run ruff check .`
   - `uv run pyright`
   - `uv run pytest -q`
6. **Extract version from tag**: `${GITHUB_REF_NAME#v}` → `X.Y.Z`
7. **Verify pyproject version matches tag**: Python assertion
8. **Ensure Unreleased is empty**: `scripts/assert_unreleased_empty.py`
9. **Extract release notes**: `scripts/extract_release_notes.py $VERSION`
10. **Build**: `uv run python -m build`
11. **Publish to PyPI**: `pypa/gh-action-pypi-publish@release/v1` (Trusted Publishing)
12. **Create GitHub Release**: `gh release create` with `--notes-file RELEASE_NOTES.md` and `dist/*`

**Full workflow from spec** (RELEASE_WORKFLOW.md:131-205):
```yaml
name: release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: write
  id-token: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Sync deps (locked)
        run: uv sync --frozen

      - name: Quality gates
        run: |
          uv run ruff format --check .
          uv run ruff check .
          uv run pyright
          uv run pytest -q

      - name: Extract version from tag
        id: tag
        run: echo "version=${GITHUB_REF_NAME#v}" >> $GITHUB_OUTPUT

      - name: Verify pyproject version matches tag
        run: |
          uv run python - <<'PY'
          import tomllib
          v=tomllib.load(open("pyproject.toml","rb"))["project"]["version"]
          tv="${{ steps.tag.outputs.version }}"
          assert v==tv, f"pyproject version {v} != tag {tv}"
          PY

      - name: Ensure Unreleased is empty
        run: uv run python scripts/assert_unreleased_empty.py

      - name: Extract release notes from CHANGELOG.md
        run: uv run python scripts/extract_release_notes.py "${{ steps.tag.outputs.version }}"

      - name: Build (sdist + wheel)
        run: uv run python -m build

      - name: Publish to PyPI (Trusted Publishing)
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: dist/

      - name: Create GitHub Release + upload artifacts
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh release create "${GITHUB_REF_NAME}" \
            --title "${GITHUB_REF_NAME}" \
            --notes-file RELEASE_NOTES.md \
            dist/*
```

### 5. Add `build` Dependency to pyproject.toml

The workflow uses `uv run python -m build`. Need to ensure `build` is available:

```toml
[dependency-groups]
dev = [
  ...existing deps...
  "build>=1.0",  # Add this
]
```

### 6. PyPI Trusted Publishing Setup (Manual)

**One-time setup in PyPI project settings**:
1. Create project on PyPI (or publish once manually)
2. In PyPI project settings → "Publishing" → "Add a trusted publisher"
3. Configure:
   - Provider: GitHub
   - Repository: `user/weld-cli` (replace with actual)
   - Workflow: `.github/workflows/release.yml`
   - Environment: (leave blank or "release" if using)

---

## Gap Analysis

| Requirement | Current State | Action Needed |
|-------------|---------------|---------------|
| Version source of truth in pyproject.toml | ✅ Present | None |
| Git tag format `vX.Y.Z` | ✅ Convention followed | None |
| CHANGELOG with `## [Unreleased]` | ✅ Present, empty | None |
| CHANGELOG with `## [X.Y.Z] - YYYY-MM-DD` | ✅ Present | None |
| `scripts/extract_release_notes.py` | ❌ Missing | Create per spec |
| `scripts/assert_unreleased_empty.py` | ❌ Missing | Create per spec |
| `.github/workflows/release.yml` | ❌ Missing | Create per spec |
| `build` package in dev deps | ❌ Missing | Add to pyproject.toml |
| PyPI Trusted Publisher | ❌ Not configured | Manual PyPI setup |
| `uv.lock` committed | ✅ Present | None |

---

## Validation Checklist

### Pre-Implementation Verification

- [ ] `scripts/` directory created
- [ ] `scripts/extract_release_notes.py` created and tested
- [ ] `scripts/assert_unreleased_empty.py` created and tested
- [ ] `.github/workflows/release.yml` created
- [ ] `build` added to dev dependencies
- [ ] Workflow syntax validated (e.g., via `actionlint`)

### Post-Implementation Verification

- [ ] Local test: `python scripts/extract_release_notes.py 0.3.0` produces valid RELEASE_NOTES.md
- [ ] Local test: `python scripts/assert_unreleased_empty.py` passes (Unreleased is empty)
- [ ] Local test: `uv run python -m build` creates dist/*.whl and dist/*.tar.gz
- [ ] Tag push triggers workflow
- [ ] Quality gates pass
- [ ] Version validation passes
- [ ] PyPI publish succeeds
- [ ] GitHub Release created with correct notes and artifacts

---

## File Locations Summary

### Files to Create

| File | Purpose |
|------|---------|
| `scripts/extract_release_notes.py` | Extract release notes from CHANGELOG |
| `scripts/assert_unreleased_empty.py` | Validate Unreleased section is empty |
| `.github/workflows/release.yml` | Tag-triggered release workflow |

### Files to Modify

| File | Change |
|------|--------|
| `pyproject.toml` | Add `build>=1.0` to dev dependencies |

### One-Time Manual Steps

| Task | Location |
|------|----------|
| Configure PyPI Trusted Publisher | PyPI project settings |
| Verify `uv.lock` is committed | Git repository |

---

## Human Release Process (Per Release)

From RELEASE_WORKFLOW.md:44-51:

1. Move entries from `## [Unreleased]` into new `## [X.Y.Z] - YYYY-MM-DD` section
2. Ensure `pyproject.toml` version is set to `X.Y.Z`
3. Commit to `main`/`master`
4. Create annotated tag: `git tag -a vX.Y.Z -m "vX.Y.Z"`
5. Push tag: `git push origin vX.Y.Z`

**Note**: The spec doesn't explicitly mention `src/weld/__init__.py`, but this codebase maintains version in both files. Use `make bump PART=patch|minor|major` to update both atomically before step 2.

Automation takes over from step 5.

---

## Existing Makefile Targets to Keep

The existing `release` target in Makefile:268-289 can coexist with the new CI workflow. It's useful for:
- Creating releases manually without a tag push
- Creating releases for tags that were already pushed
- Testing release note extraction locally

However, the CI workflow will be the **authoritative** release mechanism.

---

## Dependencies & Constraints

### External Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| `build` | >=1.0 | Build sdist + wheel |
| `tomllib` | stdlib (3.11+) | Parse pyproject.toml |

### GitHub Actions Dependencies

| Action | Version | Purpose |
|--------|---------|---------|
| `actions/checkout` | v4 | Checkout with full history |
| `actions/setup-python` | v5 | Python 3.11 |
| `astral-sh/setup-uv` | v3 | Install uv |
| `pypa/gh-action-pypi-publish` | release/v1 | Trusted Publishing to PyPI |

### Invariants

- Tag version (`vX.Y.Z`) must match pyproject.toml version (`X.Y.Z`)
- CHANGELOG must have `## [X.Y.Z]` section
- CHANGELOG `## [Unreleased]` must be empty at release time
- All quality gates must pass before publish

---

## Open Questions

### Requires Human Input

- [ ] What is the actual GitHub repository URL? (`CHANGELOG.md:188-191` shows `https://github.com/user/weld-cli` which appears to be a placeholder)
- [ ] Is the project already registered on PyPI, or will this be the first publish?
- [ ] Should there be a fallback to token-based PyPI publishing?

### Implementation Decisions

- [ ] Should `scripts/` files be marked executable (`chmod +x`)?
- [ ] Should the workflow include `pip-audit` in quality gates? (Currently omitted but recommended in hardening checklist)
- [ ] Should there be a "dry-run" mode for testing without actual publish?

---

## Appendix: Key Code Snippets

### Current Version Extraction Pattern (Makefile:214)

```makefile
CURRENT_VERSION := $(shell grep -E '^version = ' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/')
```

### Current CHANGELOG Extraction Pattern (Makefile:287)

```makefile
gh release create v$(VERSION) \
    --title "v$(VERSION)" \
    --notes "$$(awk '/^## \[$(VERSION)\]/{flag=1; next} /^## \[/{flag=0} flag' CHANGELOG.md)"
```

### Version Files to Keep in Sync

- `pyproject.toml:7` - `version = "X.Y.Z"`
- `src/weld/__init__.py:3` - `__version__ = "X.Y.Z"`

The Makefile `bump` target (lines 220-254) already handles updating both files atomically.

---

## Appendix: Useful Commands

```bash
# Test release notes extraction locally
python scripts/extract_release_notes.py 0.3.0
cat RELEASE_NOTES.md

# Test unreleased check
python scripts/assert_unreleased_empty.py

# Build package locally
uv run python -m build
ls -la dist/

# Validate workflow syntax (requires actionlint)
actionlint .github/workflows/release.yml

# Test full release flow without pushing
git tag -a v0.3.1 -m "v0.3.1"  # create local tag
git tag -d v0.3.1              # delete before pushing if just testing
```
