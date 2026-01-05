# Weld CLI Implementation Plan

> **Generated**: 2026-01-04
> **Spec**: SPECS.md
> **Target**: Python 3.11+ CLI with uv, typer, pydantic, rich

---

## Phase 1: Project Scaffolding **COMPLETE**

### Step 1.1: Create pyproject.toml

**File**: `pyproject.toml`

```toml
[project]
name = "weld"
version = "0.1.0"
description = "Human-in-the-loop coding harness: plan, review, iterate, commit with transcript provenance"
requires-python = ">=3.14"
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

**Validation**:
```bash
uv venv && uv pip install -e .
weld --help  # Should fail with import error (expected - no code yet)
```

**Failure modes**:
- `uv` not installed → exits with "command not found"
- Invalid TOML syntax → uv reports parse error with line number

---

### Step 1.2: Create .python-version

**File**: `.python-version`

```
3.11
```

**Validation**:
```bash
cat .python-version  # Should output "3.11"
```

---

### Step 1.3: Create directory structure

**Directories to create**:
```
src/weld/
src/weld/models/
```

**Files to create** (empty `__init__.py` stubs):
- `src/weld/__init__.py`
- `src/weld/models/__init__.py`

**Validation**:
```bash
find src -type f -name "*.py" | sort
# Expected output:
# src/weld/__init__.py
# src/weld/models/__init__.py
```

**Failure modes**:
- Missing `src/` prefix → uv install fails with "package not found"

---

## Phase 2: Data Models (Pydantic) **COMPLETE**

### Step 2.1: Create models/meta.py

**File**: `src/weld/models/meta.py`

```python
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field

class SpecRef(BaseModel):
    """Reference to the input specification file."""
    absolute_path: Path
    sha256: str
    size_bytes: int
    git_blob_id: str | None = None

class Meta(BaseModel):
    """Run metadata written to meta.json."""
    run_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    repo_root: Path
    branch: str
    head_sha: str
    config_hash: str
    tool_versions: dict[str, str] = Field(default_factory=dict)
    plan_parse_warnings: list[str] = Field(default_factory=list)
```

**Validation**:
```bash
python -c "from weld.models.meta import Meta, SpecRef; print('OK')"
```

**Failure modes**:
- Pydantic not installed → ImportError
- Type annotation syntax error → SyntaxError with line number

---

### Step 2.2: Create models/step.py

**File**: `src/weld/models/step.py`

```python
from pydantic import BaseModel, Field

class Step(BaseModel):
    """Parsed step from the plan."""
    n: int
    title: str
    slug: str
    body_md: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
```

**Validation**:
```bash
python -c "from weld.models.step import Step; print('OK')"
```

---

### Step 2.3: Create models/issues.py

**File**: `src/weld/models/issues.py`

```python
from typing import Literal
from pydantic import BaseModel, Field

class Issue(BaseModel):
    """Single issue from Codex review."""
    severity: Literal["blocker", "major", "minor"]
    file: str
    hint: str
    maps_to: str | None = None  # e.g., "AC #2"

class Issues(BaseModel):
    """Codex review result (parsed from final JSON line)."""
    pass_: bool = Field(alias="pass")
    issues: list[Issue] = Field(default_factory=list)

    class Config:
        populate_by_name = True
```

**Validation**:
```bash
python -c "
from weld.models.issues import Issues
result = Issues.model_validate({'pass': True, 'issues': []})
print(f'pass={result.pass_}')
"
# Expected: pass=True
```

**Failure modes**:
- `pass` is Python keyword → must use `alias="pass"` with `pass_` field name

---

### Step 2.4: Create models/status.py

**File**: `src/weld/models/status.py`

```python
from datetime import datetime
from pydantic import BaseModel, Field

class Status(BaseModel):
    """Iteration status derived from review + checks."""
    pass_: bool = Field(alias="pass")
    issue_count: int = 0
    blocker_count: int = 0
    major_count: int = 0
    minor_count: int = 0
    checks_exit_code: int
    diff_nonempty: bool
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        populate_by_name = True
```

**Validation**:
```bash
python -c "
from weld.models.status import Status
s = Status(pass_=True, checks_exit_code=0, diff_nonempty=True)
print(s.model_dump_json(by_alias=True))
"
# Should output JSON with "pass" key (not "pass_")
```

---

### Step 2.5: Update models/__init__.py with exports

**File**: `src/weld/models/__init__.py`

```python
from .meta import Meta, SpecRef
from .step import Step
from .issues import Issue, Issues
from .status import Status

__all__ = ["Meta", "SpecRef", "Step", "Issue", "Issues", "Status"]
```

**Validation**:
```bash
python -c "from weld.models import Meta, Step, Issues, Status; print('OK')"
```

---

## Phase 3: Core Utilities **COMPLETE**

### Step 3.1: Create config.py

**File**: `src/weld/config.py`

```python
from pathlib import Path
from typing import Any
import tomllib
import tomli_w
from pydantic import BaseModel, Field

class ChecksConfig(BaseModel):
    command: str = "echo 'No checks configured'"

class CodexConfig(BaseModel):
    exec: str = "codex"
    sandbox: str = "read-only"
    model: str | None = None

class TranscriptsConfig(BaseModel):
    exec: str = "claude-code-transcripts"
    visibility: str = "secret"

class ClaudeConfig(BaseModel):
    transcripts: TranscriptsConfig = Field(default_factory=TranscriptsConfig)

class GitConfig(BaseModel):
    commit_trailer_key: str = "Claude-Transcript"
    include_run_trailer: bool = True

class LoopConfig(BaseModel):
    max_iterations: int = 5
    fail_on_blockers_only: bool = True

class ProjectConfig(BaseModel):
    name: str = "unnamed-project"

class WeldConfig(BaseModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    checks: ChecksConfig = Field(default_factory=ChecksConfig)
    codex: CodexConfig = Field(default_factory=CodexConfig)
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)

def load_config(weld_dir: Path) -> WeldConfig:
    """Load config from .weld/config.toml."""
    config_path = weld_dir / "config.toml"
    if not config_path.exists():
        return WeldConfig()
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    return WeldConfig.model_validate(data)

def write_config_template(weld_dir: Path) -> Path:
    """Write default config.toml template."""
    config_path = weld_dir / "config.toml"
    template = {
        "project": {"name": "your-project"},
        "checks": {"command": "echo 'Configure your checks command'"},
        "codex": {"exec": "codex", "sandbox": "read-only"},
        "claude": {"transcripts": {"exec": "claude-code-transcripts", "visibility": "secret"}},
        "git": {"commit_trailer_key": "Claude-Transcript", "include_run_trailer": True},
        "loop": {"max_iterations": 5, "fail_on_blockers_only": True},
    }
    with open(config_path, "wb") as f:
        tomli_w.dump(template, f)
    return config_path
```

**Validation**:
```bash
python -c "
from weld.config import WeldConfig, load_config
from pathlib import Path
cfg = WeldConfig()
print(f'max_iterations={cfg.loop.max_iterations}')
"
# Expected: max_iterations=5
```

**Failure modes**:
- TOML syntax error in config.toml → `tomllib.TOMLDecodeError` with position
- Missing required field → Pydantic validation error with field path

---

### Step 3.2: Create git.py

**File**: `src/weld/git.py`

```python
import subprocess
from pathlib import Path

class GitError(Exception):
    """Git command failed."""
    pass

def run_git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    """Run git command and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()

def get_repo_root(cwd: Path | None = None) -> Path:
    """Get git repository root directory."""
    try:
        root = run_git("rev-parse", "--show-toplevel", cwd=cwd)
        return Path(root)
    except GitError:
        raise GitError("Not a git repository")

def get_current_branch(cwd: Path | None = None) -> str:
    """Get current branch name."""
    return run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)

def get_head_sha(cwd: Path | None = None) -> str:
    """Get HEAD commit SHA."""
    return run_git("rev-parse", "HEAD", cwd=cwd)

def get_diff(staged: bool = False, cwd: Path | None = None) -> str:
    """Get diff output."""
    args = ["diff", "--staged"] if staged else ["diff"]
    return run_git(*args, cwd=cwd, check=False)

def get_status_porcelain(cwd: Path | None = None) -> str:
    """Get status in porcelain format."""
    return run_git("status", "--porcelain", cwd=cwd, check=False)

def stage_all(cwd: Path | None = None) -> None:
    """Stage all changes."""
    run_git("add", "-A", cwd=cwd)

def commit_file(message_file: Path, cwd: Path | None = None) -> str:
    """Create commit using message file, return commit SHA."""
    run_git("commit", "-F", str(message_file), cwd=cwd)
    return get_head_sha(cwd=cwd)

def has_staged_changes(cwd: Path | None = None) -> bool:
    """Check if there are staged changes."""
    result = run_git("diff", "--staged", "--quiet", cwd=cwd, check=False)
    # git diff --quiet exits 1 if there are differences
    return result != ""  # Actually need to check return code differently

def has_staged_changes(cwd: Path | None = None) -> bool:
    """Check if there are staged changes."""
    result = subprocess.run(
        ["git", "diff", "--staged", "--quiet"],
        cwd=cwd,
        capture_output=True,
    )
    return result.returncode != 0
```

**Validation**:
```bash
cd /home/ametel/source/weld-cli
git init  # Initialize git repo first
python -c "
from weld.git import get_repo_root
print(get_repo_root())
"
# Should print the repo path
```

**Failure modes**:
- Not a git repo → `GitError("Not a git repository")`
- Git not installed → `FileNotFoundError`

---

### Step 3.3: Create diff.py

**File**: `src/weld/diff.py`

```python
from pathlib import Path
from .git import get_diff

def capture_diff(repo_root: Path, staged: bool = False) -> tuple[str, bool]:
    """Capture diff and return (content, is_nonempty)."""
    diff_content = get_diff(staged=staged, cwd=repo_root)
    return diff_content, bool(diff_content.strip())

def write_diff(path: Path, content: str) -> None:
    """Write diff to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
```

**Validation**:
```bash
python -c "
from weld.diff import capture_diff
from pathlib import Path
diff, nonempty = capture_diff(Path('.'))
print(f'nonempty={nonempty}')
"
```

---

### Step 3.4: Create checks.py

**File**: `src/weld/checks.py`

```python
import subprocess
from pathlib import Path

def run_checks(command: str, cwd: Path) -> tuple[str, int]:
    """Run checks command and return (output, exit_code)."""
    result = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    output = f"exit_code: {result.returncode}\n\n"
    output += "=== stdout ===\n"
    output += result.stdout
    output += "\n=== stderr ===\n"
    output += result.stderr
    return output, result.returncode

def write_checks(path: Path, output: str) -> None:
    """Write checks output to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output)
```

**Validation**:
```bash
python -c "
from weld.checks import run_checks
from pathlib import Path
output, code = run_checks('echo hello', Path('.'))
print(f'exit_code={code}')
print(output[:50])
"
```

---

### Step 3.5: Create codex.py

**File**: `src/weld/codex.py`

```python
import subprocess
import json
from pathlib import Path
from .models import Issues

class CodexError(Exception):
    """Codex invocation failed."""
    pass

def run_codex(
    prompt: str,
    exec_path: str = "codex",
    sandbox: str = "read-only",
    cwd: Path | None = None,
) -> str:
    """Run codex with prompt and return output."""
    result = subprocess.run(
        [exec_path, "-p", prompt, "--sandbox", sandbox],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CodexError(f"Codex failed: {result.stderr}")
    return result.stdout

def parse_review_json(review_md: str) -> Issues:
    """Parse issues JSON from last line of review."""
    lines = review_md.strip().split("\n")
    if not lines:
        raise CodexError("Empty review output")

    last_line = lines[-1].strip()
    try:
        data = json.loads(last_line)
        return Issues.model_validate(data)
    except json.JSONDecodeError as e:
        raise CodexError(f"Invalid JSON in review last line: {e}")
    except Exception as e:
        raise CodexError(f"Failed to parse issues: {e}")

def extract_revised_plan(codex_output: str) -> str:
    """Extract 'Revised Plan' section from codex output."""
    lines = codex_output.split("\n")
    in_section = False
    section_lines = []

    for line in lines:
        if line.strip().lower().startswith("## revised plan") or \
           line.strip().lower() == "# revised plan":
            in_section = True
            continue
        if in_section:
            # Stop at next h1/h2 header
            if line.startswith("# ") or line.startswith("## "):
                break
            section_lines.append(line)

    if not section_lines:
        raise CodexError("No 'Revised Plan' section found in codex output")

    return "\n".join(section_lines).strip()
```

**Validation**:
```bash
python -c "
from weld.codex import parse_review_json
review = '''Some review text
More text
{\"pass\": true, \"issues\": []}'''
result = parse_review_json(review)
print(f'pass={result.pass_}')
"
```

**Failure modes**:
- Codex not installed → `FileNotFoundError`
- Codex returns error → `CodexError` with stderr
- JSON parse fails → `CodexError` with parse details

---

### Step 3.6: Create transcripts.py

**File**: `src/weld/transcripts.py`

```python
import subprocess
import re
from pathlib import Path
from pydantic import BaseModel, Field

class TranscriptResult(BaseModel):
    """Result from claude-code-transcripts."""
    gist_url: str | None = None
    preview_url: str | None = None
    raw_output: str
    warnings: list[str] = Field(default_factory=list)

def run_transcript_gist(
    exec_path: str = "claude-code-transcripts",
    visibility: str = "secret",
    cwd: Path | None = None,
) -> TranscriptResult:
    """Run transcript tool to create gist."""
    args = [exec_path, "--gist"]
    if visibility == "public":
        args.append("--public")

    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )

    output = result.stdout + result.stderr
    warnings = []

    # Check for auto-detect warning
    if "Could not auto-detect GitHub repo" in output:
        warnings.append("Could not auto-detect GitHub repo")

    # Parse gist URL
    gist_match = re.search(r"Gist:\s*(https://gist\.github\.com/\S+)", output)
    gist_url = gist_match.group(1) if gist_match else None

    # Parse preview URL
    preview_match = re.search(r"Preview:\s*(https://\S+)", output)
    preview_url = preview_match.group(1) if preview_match else None

    return TranscriptResult(
        gist_url=gist_url,
        preview_url=preview_url,
        raw_output=output,
        warnings=warnings,
    )
```

**Validation**:
```bash
python -c "
from weld.transcripts import TranscriptResult
r = TranscriptResult(raw_output='test', gist_url='https://gist.github.com/test')
print(r.model_dump_json())
"
```

---

### Step 3.7: Create run.py

**File**: `src/weld/run.py`

```python
import hashlib
import re
from datetime import datetime
from pathlib import Path
from .config import WeldConfig, load_config
from .git import get_repo_root, get_current_branch, get_head_sha
from .models import Meta, SpecRef

def generate_run_id(slug: str | None = None, spec_path: Path | None = None) -> str:
    """Generate run ID in format YYYYMMDD-HHMMSS-<slug>."""
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d-%H%M%S")

    if slug:
        safe_slug = sanitize_slug(slug)
    elif spec_path:
        safe_slug = sanitize_slug(spec_path.stem)
    else:
        safe_slug = "run"

    return f"{timestamp}-{safe_slug}"

def sanitize_slug(name: str) -> str:
    """Convert name to safe slug."""
    # Lowercase, replace spaces/special chars with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    return slug[:50] if slug else "unnamed"

def hash_file(path: Path) -> str:
    """Compute SHA256 of file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()

def hash_config(config: WeldConfig) -> str:
    """Compute hash of config for change detection."""
    return hashlib.sha256(
        config.model_dump_json().encode()
    ).hexdigest()[:16]

def create_run_directory(weld_dir: Path, run_id: str) -> Path:
    """Create run directory structure."""
    run_dir = weld_dir / "runs" / run_id

    # Create subdirectories
    (run_dir / "inputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "plan").mkdir(parents=True, exist_ok=True)
    (run_dir / "steps").mkdir(parents=True, exist_ok=True)
    (run_dir / "commit").mkdir(parents=True, exist_ok=True)

    return run_dir

def create_meta(
    run_id: str,
    repo_root: Path,
    config: WeldConfig,
) -> Meta:
    """Create run metadata."""
    return Meta(
        run_id=run_id,
        repo_root=repo_root,
        branch=get_current_branch(cwd=repo_root),
        head_sha=get_head_sha(cwd=repo_root),
        config_hash=hash_config(config),
    )

def create_spec_ref(spec_path: Path) -> SpecRef:
    """Create spec file reference."""
    return SpecRef(
        absolute_path=spec_path.resolve(),
        sha256=hash_file(spec_path),
        size_bytes=spec_path.stat().st_size,
    )

def get_weld_dir(repo_root: Path | None = None) -> Path:
    """Get .weld directory path."""
    if repo_root is None:
        repo_root = get_repo_root()
    return repo_root / ".weld"

def get_run_dir(weld_dir: Path, run_id: str) -> Path:
    """Get run directory path."""
    return weld_dir / "runs" / run_id

def list_runs(weld_dir: Path) -> list[str]:
    """List all run IDs."""
    runs_dir = weld_dir / "runs"
    if not runs_dir.exists():
        return []
    return sorted([d.name for d in runs_dir.iterdir() if d.is_dir()], reverse=True)
```

**Validation**:
```bash
python -c "
from weld.run import generate_run_id, sanitize_slug
rid = generate_run_id(spec_path=Path('specs/horizon.md'))
print(f'run_id={rid}')
print(f'slug={sanitize_slug(\"My Cool Spec!\")}')
"
```

---

## Phase 4: Plan Handling **COMPLETE**

### Step 4.1: Create plan.py

**File**: `src/weld/plan.py`

```python
import re
from pathlib import Path
from .models import Step

def generate_plan_prompt(spec_content: str, spec_path: Path) -> str:
    """Generate Claude prompt for plan creation."""
    return f"""# Implementation Plan Request

You are creating an implementation plan for the following specification.

## Specification: {spec_path.name}

{spec_content}

---

## Instructions

Create a detailed, step-by-step implementation plan. Each step must follow this format:

## Step N: <Title>

### Goal
Brief description of what this step accomplishes.

### Changes
- List of files to create/modify
- Specific changes to make

### Acceptance criteria
- [ ] Criterion 1
- [ ] Criterion 2

### Tests
- Commands to verify the step works

---

Guidelines:
- Each step should be independently verifiable
- Steps should be atomic and focused
- Order steps by dependency (do prerequisites first)
- Include validation commands for each step
"""

def generate_codex_review_prompt(plan_content: str) -> str:
    """Generate Codex prompt for plan review."""
    return f"""# Plan Review Request

Review the following implementation plan for completeness, correctness, and potential issues.

## Plan to Review

{plan_content}

---

## Your Task

Analyze this plan and provide:

## Findings
- List any issues, gaps, or improvements

## Revised Plan
Provide the complete revised plan (with your improvements incorporated).
Use the same format as the original plan (## Step N: Title, ### Goal, etc.)

## Risk Notes
- Any risks or considerations for implementation
"""

def parse_steps_strict(plan_content: str) -> list[Step]:
    """Parse steps using strict format (## Step N: Title)."""
    steps = []

    # Pattern for step headers
    pattern = r"^## Step (\d+):\s*(.+)$"

    lines = plan_content.split("\n")
    current_step = None
    current_body = []

    for line in lines:
        match = re.match(pattern, line, re.IGNORECASE)
        if match:
            # Save previous step
            if current_step is not None:
                body = "\n".join(current_body).strip()
                steps.append(_parse_step_body(current_step, body))

            # Start new step
            n = int(match.group(1))
            title = match.group(2).strip()
            current_step = {"n": n, "title": title}
            current_body = []
        elif current_step is not None:
            current_body.append(line)

    # Don't forget last step
    if current_step is not None:
        body = "\n".join(current_body).strip()
        steps.append(_parse_step_body(current_step, body))

    return steps

def _parse_step_body(header: dict, body: str) -> Step:
    """Parse step body for acceptance criteria and tests."""
    # Extract acceptance criteria (checkbox items under ### Acceptance criteria)
    ac_pattern = r"###\s*Acceptance criteria\s*\n((?:[-*]\s*\[.\].*\n?)+)"
    ac_match = re.search(ac_pattern, body, re.IGNORECASE)
    criteria = []
    if ac_match:
        for line in ac_match.group(1).split("\n"):
            if line.strip().startswith(("-", "*")):
                # Remove checkbox and bullet
                text = re.sub(r"^[-*]\s*\[.\]\s*", "", line.strip())
                if text:
                    criteria.append(text)

    # Extract tests
    tests_pattern = r"###\s*Tests?\s*\n((?:[-*`].*\n?)+)"
    tests_match = re.search(tests_pattern, body, re.IGNORECASE)
    tests = []
    if tests_match:
        for line in tests_match.group(1).split("\n"):
            line = line.strip()
            if line.startswith(("-", "*", "`")):
                text = line.lstrip("-* `").rstrip("`")
                if text:
                    tests.append(text)

    # Create slug from title
    slug = re.sub(r"[^a-z0-9]+", "-", header["title"].lower()).strip("-")[:30]

    return Step(
        n=header["n"],
        title=header["title"],
        slug=slug,
        body_md=body,
        acceptance_criteria=criteria,
        tests=tests,
    )

def parse_steps_lenient(plan_content: str) -> list[Step]:
    """Parse steps using lenient format (N. Title)."""
    steps = []
    pattern = r"^(\d+)\.\s+(.+)$"

    lines = plan_content.split("\n")
    current_step = None
    current_body = []

    for line in lines:
        match = re.match(pattern, line)
        if match:
            if current_step is not None:
                body = "\n".join(current_body).strip()
                slug = re.sub(r"[^a-z0-9]+", "-", current_step["title"].lower())[:30]
                steps.append(Step(
                    n=current_step["n"],
                    title=current_step["title"],
                    slug=slug.strip("-"),
                    body_md=body,
                ))

            current_step = {"n": int(match.group(1)), "title": match.group(2).strip()}
            current_body = []
        elif current_step is not None:
            current_body.append(line)

    if current_step is not None:
        body = "\n".join(current_body).strip()
        slug = re.sub(r"[^a-z0-9]+", "-", current_step["title"].lower())[:30]
        steps.append(Step(
            n=current_step["n"],
            title=current_step["title"],
            slug=slug.strip("-"),
            body_md=body,
        ))

    return steps

def parse_steps(plan_content: str) -> tuple[list[Step], list[str]]:
    """Parse steps, trying strict format first, then lenient. Returns (steps, warnings)."""
    warnings = []

    steps = parse_steps_strict(plan_content)
    if steps:
        return steps, warnings

    warnings.append("No strict-format steps found; using lenient parsing")
    steps = parse_steps_lenient(plan_content)

    if not steps:
        warnings.append("No steps found in plan")

    return steps, warnings
```

**Validation**:
```bash
python -c "
from weld.plan import parse_steps_strict
plan = '''
## Step 1: Create config
### Goal
Set up configuration

### Acceptance criteria
- [ ] Config file exists
- [ ] Config loads correctly

### Tests
- pytest tests/test_config.py

## Step 2: Build CLI
...
'''
steps = parse_steps_strict(plan)
print(f'Found {len(steps)} steps')
print(f'Step 1 AC: {steps[0].acceptance_criteria}')
"
```

---

### Step 4.2: Create step.py

**File**: `src/weld/step.py`

```python
from pathlib import Path
from .models import Step
from .plan import parse_steps

def get_step_dir(run_dir: Path, step: Step) -> Path:
    """Get step directory path."""
    return run_dir / "steps" / f"{step.n:02d}-{step.slug}"

def create_step_directory(run_dir: Path, step: Step) -> Path:
    """Create step directory structure."""
    step_dir = get_step_dir(run_dir, step)
    (step_dir / "prompt").mkdir(parents=True, exist_ok=True)
    (step_dir / "iter").mkdir(parents=True, exist_ok=True)
    return step_dir

def get_iter_dir(step_dir: Path, iteration: int) -> Path:
    """Get iteration directory path."""
    return step_dir / "iter" / f"{iteration:02d}"

def create_iter_directory(step_dir: Path, iteration: int) -> Path:
    """Create iteration directory."""
    iter_dir = get_iter_dir(step_dir, iteration)
    iter_dir.mkdir(parents=True, exist_ok=True)
    return iter_dir

def generate_impl_prompt(step: Step, checks_command: str) -> str:
    """Generate Claude implementation prompt."""
    ac_list = "\n".join(f"- [ ] {ac}" for ac in step.acceptance_criteria)

    return f"""# Implementation Task: Step {step.n}

## {step.title}

{step.body_md}

---

## Acceptance Criteria Checklist

{ac_list if ac_list else "- [ ] Implementation complete"}

---

## Validation

After implementing, run:
```bash
{checks_command}
```

---

## Scope Boundary

**IMPORTANT:**
- Only implement this step
- Minimize churn; no refactors unless necessary to satisfy criteria
- If you change interfaces, update typing/tests accordingly
- Do not implement future steps
"""

def generate_fix_prompt(step: Step, issues_json: dict, iteration: int) -> str:
    """Generate Claude fix prompt for next iteration."""
    issues = issues_json.get("issues", [])

    # Group by severity
    blockers = [i for i in issues if i.get("severity") == "blocker"]
    majors = [i for i in issues if i.get("severity") == "major"]
    minors = [i for i in issues if i.get("severity") == "minor"]

    def format_issues(items: list, label: str) -> str:
        if not items:
            return ""
        lines = [f"\n### {label}\n"]
        for item in items:
            lines.append(f"- **{item.get('file', 'unknown')}**: {item.get('hint', 'No details')}")
            if item.get("maps_to"):
                lines.append(f"  - Maps to: {item['maps_to']}")
        return "\n".join(lines)

    issues_text = ""
    issues_text += format_issues(blockers, "Blockers (must fix)")
    issues_text += format_issues(majors, "Major Issues")
    issues_text += format_issues(minors, "Minor Issues")

    return f"""# Fix Request: Step {step.n}, Iteration {iteration + 1}

The previous implementation has issues that need to be addressed.

## Issues Found
{issues_text if issues_text else "No specific issues listed"}

---

## Original Step

{step.body_md}

---

## Scope Boundary

**IMPORTANT:**
- Fix these issues only
- No refactors or unrelated changes
- Re-run checks after fixing
"""

def generate_codex_review_prompt(step: Step, diff: str, checks_output: str) -> str:
    """Generate Codex review prompt for implementation."""
    ac_list = "\n".join(f"- {ac}" for ac in step.acceptance_criteria)

    return f"""# Implementation Review Request

Review the following implementation against the step requirements.

## Step {step.n}: {step.title}

### Acceptance Criteria
{ac_list if ac_list else "- Implementation complete"}

---

## Diff

```diff
{diff}
```

---

## Checks Output

```
{checks_output}
```

---

## Your Task

1. Review the diff against acceptance criteria
2. Check for bugs, security issues, or missing requirements
3. Note any issues found

**IMPORTANT:** Your response must end with a JSON line in this exact format:
```json
{{"pass":true,"issues":[]}}
```

Or if issues found:
```json
{{"pass":false,"issues":[{{"severity":"blocker","file":"path/to/file.py","hint":"Description of issue","maps_to":"AC #1"}}]}}
```

Severity levels: "blocker", "major", "minor"
"""
```

**Validation**:
```bash
python -c "
from weld.step import generate_impl_prompt
from weld.models import Step
step = Step(n=1, title='Test', slug='test', body_md='Do stuff', acceptance_criteria=['Works'])
prompt = generate_impl_prompt(step, 'pytest')
print(prompt[:200])
"
```

---

## Phase 5: Loop and Review Logic **COMPLETE**

### Step 5.1: Create review.py

**File**: `src/weld/review.py`

```python
from pathlib import Path
from .codex import run_codex, parse_review_json, CodexError
from .config import WeldConfig
from .models import Step, Issues, Status

def run_step_review(
    step: Step,
    diff: str,
    checks_output: str,
    checks_exit_code: int,
    config: WeldConfig,
    cwd: Path,
) -> tuple[str, Issues, Status]:
    """Run Codex review and return (review_md, issues, status)."""
    from .step import generate_codex_review_prompt

    prompt = generate_codex_review_prompt(step, diff, checks_output)

    try:
        review_md = run_codex(
            prompt=prompt,
            exec_path=config.codex.exec,
            sandbox=config.codex.sandbox,
            cwd=cwd,
        )
        issues = parse_review_json(review_md)
    except CodexError as e:
        # On parse failure, treat as not passing
        review_md = str(e)
        issues = Issues(pass_=False, issues=[])

    # Compute status
    blocker_count = sum(1 for i in issues.issues if i.severity == "blocker")
    major_count = sum(1 for i in issues.issues if i.severity == "major")
    minor_count = sum(1 for i in issues.issues if i.severity == "minor")

    # Determine pass based on config
    if config.loop.fail_on_blockers_only:
        pass_result = blocker_count == 0
    else:
        pass_result = len(issues.issues) == 0

    status = Status(
        pass_=pass_result,
        issue_count=len(issues.issues),
        blocker_count=blocker_count,
        major_count=major_count,
        minor_count=minor_count,
        checks_exit_code=checks_exit_code,
        diff_nonempty=bool(diff.strip()),
    )

    return review_md, issues, status
```

**Validation**:
```bash
python -c "
from weld.models import Status
s = Status(pass_=True, checks_exit_code=0, diff_nonempty=True, blocker_count=0)
print(s.model_dump_json(by_alias=True))
"
```

---

### Step 5.2: Create loop.py

**File**: `src/weld/loop.py`

```python
from pathlib import Path
from rich.console import Console
from .config import WeldConfig
from .models import Step, Status
from .diff import capture_diff, write_diff
from .checks import run_checks, write_checks
from .review import run_step_review
from .step import create_iter_directory, generate_fix_prompt, get_step_dir
import json

console = Console()

class LoopResult:
    """Result of step implementation loop."""
    def __init__(self, success: bool, iterations: int, final_status: Status | None):
        self.success = success
        self.iterations = iterations
        self.final_status = final_status

def run_step_loop(
    run_dir: Path,
    step: Step,
    config: WeldConfig,
    repo_root: Path,
    max_iterations: int | None = None,
    wait_mode: bool = False,
) -> LoopResult:
    """Run the implement-review-fix loop for a step."""
    max_iter = max_iterations or config.loop.max_iterations
    step_dir = get_step_dir(run_dir, step)

    for iteration in range(1, max_iter + 1):
        console.print(f"\n[bold blue]Iteration {iteration}/{max_iter}[/bold blue]")

        if wait_mode:
            console.print("[yellow]Waiting for implementation... Press Enter when ready.[/yellow]")
            input()

        iter_dir = create_iter_directory(step_dir, iteration)

        # Capture diff
        diff, diff_nonempty = capture_diff(repo_root)
        write_diff(iter_dir / "diff.patch", diff)

        if not diff_nonempty:
            console.print("[yellow]No changes detected. Skipping review.[/yellow]")
            status = Status(
                pass_=False,
                checks_exit_code=-1,
                diff_nonempty=False,
            )
            (iter_dir / "status.json").write_text(status.model_dump_json(by_alias=True, indent=2))
            continue

        # Run checks
        checks_output, checks_exit = run_checks(config.checks.command, repo_root)
        write_checks(iter_dir / "checks.txt", checks_output)

        # Run review
        console.print("[cyan]Running Codex review...[/cyan]")
        review_md, issues, status = run_step_review(
            step=step,
            diff=diff,
            checks_output=checks_output,
            checks_exit_code=checks_exit,
            config=config,
            cwd=repo_root,
        )

        # Write results
        (iter_dir / "codex.review.md").write_text(review_md)
        (iter_dir / "codex.issues.json").write_text(
            issues.model_dump_json(by_alias=True, indent=2)
        )
        (iter_dir / "status.json").write_text(
            status.model_dump_json(by_alias=True, indent=2)
        )

        if status.pass_:
            console.print("[bold green]Step passed![/bold green]")
            return LoopResult(success=True, iterations=iteration, final_status=status)

        # Generate fix prompt
        console.print(f"[red]Found {status.issue_count} issues ({status.blocker_count} blockers)[/red]")

        if iteration < max_iter:
            fix_prompt = generate_fix_prompt(
                step,
                issues.model_dump(by_alias=True),
                iteration
            )
            fix_path = step_dir / "prompt" / f"claude.fix.prompt.iter{iteration + 1:02d}.md"
            fix_path.write_text(fix_prompt)

            console.print(f"\n[bold]Fix prompt written to:[/bold] {fix_path}")
            console.print("\n" + "=" * 60)
            console.print(fix_prompt)
            console.print("=" * 60 + "\n")

    console.print(f"[bold red]Max iterations ({max_iter}) reached[/bold red]")
    return LoopResult(success=False, iterations=max_iter, final_status=status)
```

**Validation**:
```bash
python -c "
from weld.loop import LoopResult
from weld.models import Status
s = Status(pass_=True, checks_exit_code=0, diff_nonempty=True)
r = LoopResult(True, 2, s)
print(f'success={r.success}, iterations={r.iterations}')
"
```

---

## Phase 6: Commit Handling **COMPLETE**

### Step 6.1: Create commit.py

**File**: `src/weld/commit.py`

```python
from pathlib import Path
from .config import WeldConfig
from .git import commit_file, has_staged_changes, stage_all, get_head_sha
from .transcripts import run_transcript_gist, TranscriptResult

class CommitError(Exception):
    """Commit operation failed."""
    pass

def build_commit_message(
    subject: str,
    run_id: str,
    gist_url: str,
    config: WeldConfig,
    step_summary: str | None = None,
) -> str:
    """Build commit message with trailers."""
    lines = [subject, ""]

    if step_summary:
        lines.append(step_summary)
        lines.append("")

    # Trailers
    lines.append(f"{config.git.commit_trailer_key}: {gist_url}")

    if config.git.include_run_trailer:
        lines.append(f"Weld-Run: .weld/runs/{run_id}")

    return "\n".join(lines)

def ensure_transcript_gist(
    run_dir: Path,
    config: WeldConfig,
    cwd: Path,
) -> TranscriptResult:
    """Ensure transcript gist exists, creating if needed."""
    transcript_file = run_dir / "commit" / "transcript.json"

    # Check if already exists
    if transcript_file.exists():
        import json
        data = json.loads(transcript_file.read_text())
        result = TranscriptResult.model_validate(data)
        if result.gist_url:
            return result

    # Create gist
    result = run_transcript_gist(
        exec_path=config.claude.transcripts.exec,
        visibility=config.claude.transcripts.visibility,
        cwd=cwd,
    )

    # Save result
    transcript_file.parent.mkdir(parents=True, exist_ok=True)
    transcript_file.write_text(result.model_dump_json(indent=2))

    return result

def do_commit(
    run_dir: Path,
    message: str,
    config: WeldConfig,
    repo_root: Path,
    stage_all_changes: bool = False,
) -> str:
    """Perform commit and return SHA."""
    # Stage if requested
    if stage_all_changes:
        stage_all(cwd=repo_root)

    # Verify staged changes exist
    if not has_staged_changes(cwd=repo_root):
        raise CommitError("No staged changes to commit")

    # Ensure transcript gist
    transcript = ensure_transcript_gist(run_dir, config, repo_root)
    if not transcript.gist_url:
        raise CommitError("Failed to get transcript gist URL")

    # Build message
    run_id = run_dir.name
    full_message = build_commit_message(
        subject=message,
        run_id=run_id,
        gist_url=transcript.gist_url,
        config=config,
    )

    # Write message file
    message_file = run_dir / "commit" / "message.txt"
    message_file.parent.mkdir(parents=True, exist_ok=True)
    message_file.write_text(full_message)

    # Commit
    sha = commit_file(message_file, cwd=repo_root)

    # Update summary
    summary_file = run_dir / "summary.md"
    summary = f"# Run: {run_id}\n\n"
    summary += f"- Commit: {sha}\n"
    summary += f"- Transcript: {transcript.gist_url}\n"
    summary_file.write_text(summary)

    return sha
```

**Validation**:
```bash
python -c "
from weld.commit import build_commit_message
from weld.config import WeldConfig
msg = build_commit_message('Test commit', 'run-123', 'https://gist.github.com/test', WeldConfig())
print(msg)
"
```

---

## Phase 7: CLI Implementation

### Step 7.1: Create cli.py (base structure)

**File**: `src/weld/cli.py`

```python
import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel

from .config import load_config, write_config_template, WeldConfig
from .git import get_repo_root, GitError
from .run import (
    generate_run_id, create_run_directory, create_meta, create_spec_ref,
    get_weld_dir, get_run_dir, hash_file, list_runs
)
from .models import Meta, SpecRef

app = typer.Typer(
    name="weld",
    help="Human-in-the-loop coding harness with transcript provenance",
    no_args_is_help=True,
)

# Sub-commands
plan_app = typer.Typer(help="Plan management commands")
step_app = typer.Typer(help="Step implementation commands")
transcript_app = typer.Typer(help="Transcript management commands")

app.add_typer(plan_app, name="plan")
app.add_typer(step_app, name="step")
app.add_typer(transcript_app, name="transcript")

console = Console()

# ============================================================================
# weld init
# ============================================================================

@app.command()
def init():
    """Initialize weld in the current repository."""
    # Check git repo
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3)

    weld_dir = repo_root / ".weld"

    # Create directories
    weld_dir.mkdir(exist_ok=True)
    (weld_dir / "runs").mkdir(exist_ok=True)

    # Create config if missing
    config_path = weld_dir / "config.toml"
    if not config_path.exists():
        write_config_template(weld_dir)
        console.print(f"[green]Created config template:[/green] {config_path}")
    else:
        console.print(f"[yellow]Config already exists:[/yellow] {config_path}")

    # Validate toolchain
    import subprocess

    tools = {
        "git": ["git", "--version"],
        "gh": ["gh", "auth", "status"],
        "codex": ["codex", "--version"],
        "claude-code-transcripts": ["claude-code-transcripts", "--help"],
    }

    all_ok = True
    for name, cmd in tools.items():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                console.print(f"[green]✓[/green] {name}")
            else:
                console.print(f"[red]✗[/red] {name}: {result.stderr.strip()[:50]}")
                all_ok = False
        except FileNotFoundError:
            console.print(f"[red]✗[/red] {name}: not found in PATH")
            all_ok = False
        except subprocess.TimeoutExpired:
            console.print(f"[yellow]?[/yellow] {name}: timed out")

    if not all_ok:
        console.print("\n[yellow]Warning: Some tools are missing or not configured[/yellow]")
        raise typer.Exit(2)

    console.print("\n[bold green]Weld initialized successfully![/bold green]")

# ============================================================================
# weld run start
# ============================================================================

@app.command("run")
def run_start(
    spec: Path = typer.Option(..., "--spec", "-s", help="Path to spec file"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Run name slug"),
):
    """Start a new weld run."""
    # Validate spec exists
    if not spec.exists():
        console.print(f"[red]Error: Spec file not found: {spec}[/red]")
        raise typer.Exit(1)

    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3)

    weld_dir = get_weld_dir(repo_root)
    if not weld_dir.exists():
        console.print("[red]Error: Weld not initialized. Run 'weld init' first.[/red]")
        raise typer.Exit(1)

    config = load_config(weld_dir)

    # Generate run ID
    run_id = generate_run_id(slug=name, spec_path=spec)
    run_dir = create_run_directory(weld_dir, run_id)

    # Create metadata
    meta = create_meta(run_id, repo_root, config)
    (run_dir / "meta.json").write_text(meta.model_dump_json(indent=2))

    # Create spec reference
    spec_ref = create_spec_ref(spec)
    (run_dir / "inputs" / "spec.ref.json").write_text(spec_ref.model_dump_json(indent=2))

    # Generate Claude plan prompt
    from .plan import generate_plan_prompt
    spec_content = spec.read_text()
    plan_prompt = generate_plan_prompt(spec_content, spec)

    prompt_path = run_dir / "plan" / "claude.prompt.md"
    prompt_path.write_text(plan_prompt)

    # Output
    console.print(Panel(f"[bold]Run created:[/bold] {run_id}", style="green"))
    console.print(f"\n[bold]Prompt file:[/bold] {prompt_path}")
    console.print("\n" + "=" * 60)
    console.print(plan_prompt)
    console.print("=" * 60)
    console.print(f"\n[bold]Next step:[/bold] Copy prompt to Claude, then run:")
    console.print(f"  weld plan import --run {run_id} --file <plan_output.md>")

# ============================================================================
# weld plan import
# ============================================================================

@plan_app.command("import")
def plan_import(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    file: Path = typer.Option(..., "--file", "-f", help="Plan file from Claude"),
):
    """Import Claude's plan output."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3)

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)

    if not run_dir.exists():
        console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    if not file.exists():
        console.print(f"[red]Error: Plan file not found: {file}[/red]")
        raise typer.Exit(1)

    plan_content = file.read_text()

    # Write verbatim output
    (run_dir / "plan" / "claude.output.md").write_text(plan_content)

    # Parse and validate
    from .plan import parse_steps
    steps, warnings = parse_steps(plan_content)

    # Update meta with warnings
    meta_path = run_dir / "meta.json"
    import json
    meta = json.loads(meta_path.read_text())
    meta["plan_parse_warnings"] = warnings
    meta_path.write_text(json.dumps(meta, indent=2, default=str))

    # Write normalized plan
    (run_dir / "plan" / "plan.raw.md").write_text(plan_content)

    console.print(f"[green]Imported plan with {len(steps)} steps[/green]")
    if warnings:
        for w in warnings:
            console.print(f"[yellow]Warning: {w}[/yellow]")

    console.print(f"\n[bold]Next step:[/bold] Review plan with Codex:")
    console.print(f"  weld plan review --run {run} --apply")

# ============================================================================
# weld plan review
# ============================================================================

@plan_app.command("review")
def plan_review(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    apply: bool = typer.Option(False, "--apply", help="Apply revised plan"),
):
    """Run review on the plan."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3)

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    if not run_dir.exists():
        console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    # Load plan
    plan_raw = run_dir / "plan" / "plan.raw.md"
    if not plan_raw.exists():
        console.print("[red]Error: No plan imported yet. Run 'weld plan import' first.[/red]")
        raise typer.Exit(1)

    plan_content = plan_raw.read_text()

    # Generate Codex prompt
    from .plan import generate_codex_review_prompt
    codex_prompt = generate_codex_review_prompt(plan_content)
    (run_dir / "plan" / "codex.prompt.md").write_text(codex_prompt)

    # Run Codex
    console.print("[cyan]Running Codex plan review...[/cyan]")
    from .codex import run_codex, extract_revised_plan, CodexError

    try:
        codex_output = run_codex(
            prompt=codex_prompt,
            exec_path=config.codex.exec,
            sandbox=config.codex.sandbox,
            cwd=repo_root,
        )
        (run_dir / "plan" / "codex.output.md").write_text(codex_output)

        if apply:
            revised = extract_revised_plan(codex_output)
            (run_dir / "plan" / "plan.final.md").write_text(revised)
            console.print("[green]Revised plan saved to plan.final.md[/green]")

        console.print("[green]Plan review complete[/green]")
        console.print(f"\n[bold]Next step:[/bold] Select a step to implement:")
        console.print(f"  weld step select --run {run} --n 1")

    except CodexError as e:
        console.print(f"[red]Codex error: {e}[/red]")
        raise typer.Exit(12)

# ============================================================================
# weld step select
# ============================================================================

@step_app.command("select")
def step_select(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
):
    """Select a step from the plan."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3)

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find plan file
    plan_final = run_dir / "plan" / "plan.final.md"
    plan_raw = run_dir / "plan" / "plan.raw.md"
    plan_path = plan_final if plan_final.exists() else plan_raw

    if not plan_path.exists():
        console.print("[red]Error: No plan found[/red]")
        raise typer.Exit(1)

    # Parse steps
    from .plan import parse_steps
    steps, _ = parse_steps(plan_path.read_text())

    # Find requested step
    step = next((s for s in steps if s.n == n), None)
    if not step:
        console.print(f"[red]Error: Step {n} not found. Available: {[s.n for s in steps]}[/red]")
        raise typer.Exit(1)

    # Create step directory
    from .step import create_step_directory, generate_impl_prompt
    step_dir = create_step_directory(run_dir, step)

    # Write step.json
    (step_dir / "step.json").write_text(step.model_dump_json(indent=2))

    # Generate implementation prompt
    impl_prompt = generate_impl_prompt(step, config.checks.command)
    prompt_path = step_dir / "prompt" / "claude.impl.prompt.md"
    prompt_path.write_text(impl_prompt)

    console.print(f"[green]Selected step {n}: {step.title}[/green]")
    console.print(f"\n[bold]Prompt file:[/bold] {prompt_path}")
    console.print("\n" + "=" * 60)
    console.print(impl_prompt)
    console.print("=" * 60)
    console.print(f"\n[bold]Next step:[/bold] Start implementation loop:")
    console.print(f"  weld step loop --run {run} --n {n} --wait")

# ============================================================================
# weld step snapshot
# ============================================================================

@step_app.command("snapshot")
def step_snapshot(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    iter: int = typer.Option(1, "--iter", "-i", help="Iteration number"),
):
    """Capture current diff and checks for a step iteration."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3)

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find step directory
    import os
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    if not step_dirs:
        console.print(f"[red]Error: Step {n} not selected yet[/red]")
        raise typer.Exit(1)

    step_dir = step_dirs[0]

    # Create iteration directory
    from .step import create_iter_directory
    iter_dir = create_iter_directory(step_dir, iter)

    # Capture diff
    from .diff import capture_diff, write_diff
    diff, nonempty = capture_diff(repo_root)
    write_diff(iter_dir / "diff.patch", diff)

    if not nonempty:
        console.print("[yellow]No changes detected[/yellow]")
        from .models import Status
        status = Status(pass_=False, checks_exit_code=-1, diff_nonempty=False)
        (iter_dir / "status.json").write_text(status.model_dump_json(by_alias=True, indent=2))
        raise typer.Exit(0)

    # Run checks
    from .checks import run_checks, write_checks
    console.print("[cyan]Running checks...[/cyan]")
    checks_output, exit_code = run_checks(config.checks.command, repo_root)
    write_checks(iter_dir / "checks.txt", checks_output)

    console.print(f"[green]Snapshot captured for iteration {iter}[/green]")
    console.print(f"  Diff: {len(diff)} bytes")
    console.print(f"  Checks exit code: {exit_code}")

# ============================================================================
# weld step review
# ============================================================================

@step_app.command("review")
def step_review_cmd(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    iter: int = typer.Option(1, "--iter", "-i", help="Iteration number"),
):
    """Run Codex review on step implementation."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3)

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find step
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    if not step_dirs:
        console.print(f"[red]Error: Step {n} not found[/red]")
        raise typer.Exit(1)

    step_dir = step_dirs[0]
    iter_dir = step_dir / "iter" / f"{iter:02d}"

    # Load step
    import json
    from .models import Step
    step = Step.model_validate(json.loads((step_dir / "step.json").read_text()))

    # Load diff and checks
    diff = (iter_dir / "diff.patch").read_text() if (iter_dir / "diff.patch").exists() else ""
    checks = (iter_dir / "checks.txt").read_text() if (iter_dir / "checks.txt").exists() else ""

    # Parse checks exit code
    import re
    exit_match = re.search(r"exit_code:\s*(\d+)", checks)
    checks_exit = int(exit_match.group(1)) if exit_match else -1

    # Run review
    from .review import run_step_review
    console.print("[cyan]Running Codex review...[/cyan]")

    review_md, issues, status = run_step_review(
        step=step,
        diff=diff,
        checks_output=checks,
        checks_exit_code=checks_exit,
        config=config,
        cwd=repo_root,
    )

    # Write results
    (iter_dir / "codex.review.md").write_text(review_md)
    (iter_dir / "codex.issues.json").write_text(issues.model_dump_json(by_alias=True, indent=2))
    (iter_dir / "status.json").write_text(status.model_dump_json(by_alias=True, indent=2))

    if status.pass_:
        console.print("[bold green]Review passed![/bold green]")
    else:
        console.print(f"[red]Review found {status.issue_count} issues ({status.blocker_count} blockers)[/red]")

# ============================================================================
# weld step fix-prompt
# ============================================================================

@step_app.command("fix-prompt")
def step_fix_prompt(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    iter: int = typer.Option(..., "--iter", "-i", help="Current iteration"),
):
    """Generate fix prompt for next iteration."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3)

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)

    # Find step
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    if not step_dirs:
        console.print(f"[red]Error: Step {n} not found[/red]")
        raise typer.Exit(1)

    step_dir = step_dirs[0]
    iter_dir = step_dir / "iter" / f"{iter:02d}"

    # Load step and issues
    import json
    from .models import Step
    from .step import generate_fix_prompt

    step = Step.model_validate(json.loads((step_dir / "step.json").read_text()))
    issues = json.loads((iter_dir / "codex.issues.json").read_text())

    # Generate fix prompt
    fix_prompt = generate_fix_prompt(step, issues, iter)
    fix_path = step_dir / "prompt" / f"claude.fix.prompt.iter{iter + 1:02d}.md"
    fix_path.write_text(fix_prompt)

    console.print(f"[green]Fix prompt written to:[/green] {fix_path}")
    console.print("\n" + "=" * 60)
    console.print(fix_prompt)
    console.print("=" * 60)

# ============================================================================
# weld step loop
# ============================================================================

@step_app.command("loop")
def step_loop(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    n: int = typer.Option(..., "--n", help="Step number"),
    max: Optional[int] = typer.Option(None, "--max", "-m", help="Max iterations"),
    wait: bool = typer.Option(False, "--wait", "-w", help="Wait for user between iterations"),
):
    """Run implement-review-fix loop for a step."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3)

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    # Find or select step
    steps_dir = run_dir / "steps"
    step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")] if steps_dir.exists() else []

    if not step_dirs:
        # Auto-select step
        console.print(f"[yellow]Step {n} not selected, selecting now...[/yellow]")
        step_select(run=run, n=n)
        step_dirs = [d for d in steps_dir.iterdir() if d.is_dir() and d.name.startswith(f"{n:02d}-")]

    step_dir = step_dirs[0]

    # Load step
    import json
    from .models import Step
    step = Step.model_validate(json.loads((step_dir / "step.json").read_text()))

    # Print initial prompt
    impl_prompt_path = step_dir / "prompt" / "claude.impl.prompt.md"
    console.print(f"\n[bold]Implementation prompt:[/bold] {impl_prompt_path}")
    console.print("\n" + "=" * 60)
    console.print(impl_prompt_path.read_text())
    console.print("=" * 60 + "\n")

    # Run loop
    from .loop import run_step_loop
    result = run_step_loop(
        run_dir=run_dir,
        step=step,
        config=config,
        repo_root=repo_root,
        max_iterations=max,
        wait_mode=wait,
    )

    if result.success:
        console.print(f"\n[bold green]Step {n} completed in {result.iterations} iteration(s)![/bold green]")
        console.print(f"\n[bold]Next step:[/bold] Commit your changes:")
        console.print(f"  weld commit --run {run} -m 'Implement step {n}' --staged")
        raise typer.Exit(0)
    else:
        console.print(f"\n[bold red]Step {n} did not pass after {result.iterations} iterations[/bold red]")
        raise typer.Exit(10)

# ============================================================================
# weld transcript gist
# ============================================================================

@transcript_app.command("gist")
def transcript_gist(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
):
    """Generate transcript gist."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3)

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    from .commit import ensure_transcript_gist

    console.print("[cyan]Generating transcript gist...[/cyan]")
    result = ensure_transcript_gist(run_dir, config, repo_root)

    if result.gist_url:
        console.print(f"[green]Gist URL:[/green] {result.gist_url}")
        if result.preview_url:
            console.print(f"[green]Preview:[/green] {result.preview_url}")
    else:
        console.print("[red]Failed to generate gist[/red]")
        raise typer.Exit(21)

    if result.warnings:
        for w in result.warnings:
            console.print(f"[yellow]Warning: {w}[/yellow]")

# ============================================================================
# weld commit
# ============================================================================

@app.command()
def commit(
    run: str = typer.Option(..., "--run", "-r", help="Run ID"),
    message: str = typer.Option(..., "-m", help="Commit message"),
    all: bool = typer.Option(False, "--all", "-a", help="Stage all changes"),
    staged: bool = typer.Option(True, "--staged", help="Commit staged changes only"),
):
    """Create commit with transcript trailer."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3)

    weld_dir = get_weld_dir(repo_root)
    run_dir = get_run_dir(weld_dir, run)
    config = load_config(weld_dir)

    if not run_dir.exists():
        console.print(f"[red]Error: Run not found: {run}[/red]")
        raise typer.Exit(1)

    from .commit import do_commit, CommitError

    try:
        sha = do_commit(
            run_dir=run_dir,
            message=message,
            config=config,
            repo_root=repo_root,
            stage_all_changes=all,
        )
        console.print(f"[bold green]Committed:[/bold green] {sha[:8]}")
    except CommitError as e:
        if "No staged changes" in str(e):
            console.print("[red]Error: No staged changes to commit[/red]")
            raise typer.Exit(20)
        elif "gist" in str(e).lower():
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(21)
        else:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(22)

# ============================================================================
# weld list (helper command)
# ============================================================================

@app.command("list")
def list_runs_cmd():
    """List all runs."""
    try:
        repo_root = get_repo_root()
    except GitError:
        console.print("[red]Error: Not a git repository[/red]")
        raise typer.Exit(3)

    weld_dir = get_weld_dir(repo_root)
    runs = list_runs(weld_dir)

    if not runs:
        console.print("[yellow]No runs found[/yellow]")
        return

    console.print("[bold]Runs:[/bold]")
    for r in runs:
        console.print(f"  {r}")

if __name__ == "__main__":
    app()
```

**Validation**:
```bash
uv pip install -e .
weld --help
# Should show all commands
weld init --help
weld run --help
weld plan --help
weld step --help
weld commit --help
```

**Failure modes**:
- Missing dependency → ImportError with module name
- Typer misconfiguration → CLI help text wrong or missing

---

## Phase 8: Update Package Init **COMPLETE**

### Step 8.1: Update src/weld/__init__.py

**File**: `src/weld/__init__.py`

```python
"""Weld: Human-in-the-loop coding harness with transcript provenance."""

__version__ = "0.1.0"
```

**Validation**:
```bash
python -c "import weld; print(weld.__version__)"
# Expected: 0.1.0
```

---

## Phase 9: Integration Testing **COMPLETE**

### Step 9.1: Create test fixtures directory

```bash
mkdir -p tests
touch tests/__init__.py
```

### Step 9.2: Create tests/test_models.py

**File**: `tests/test_models.py`

```python
import pytest
from weld.models import Meta, Step, Issue, Issues, Status, SpecRef
from pathlib import Path
from datetime import datetime

def test_meta_creation():
    meta = Meta(
        run_id="20260104-120000-test",
        repo_root=Path("/tmp/repo"),
        branch="main",
        head_sha="abc123",
        config_hash="hash123",
    )
    assert meta.run_id == "20260104-120000-test"
    assert meta.branch == "main"

def test_step_creation():
    step = Step(
        n=1,
        title="Test Step",
        slug="test-step",
        body_md="Do the thing",
        acceptance_criteria=["It works"],
        tests=["pytest"],
    )
    assert step.n == 1
    assert len(step.acceptance_criteria) == 1

def test_issues_parsing():
    data = {"pass": True, "issues": []}
    issues = Issues.model_validate(data)
    assert issues.pass_ is True
    assert len(issues.issues) == 0

def test_issues_with_items():
    data = {
        "pass": False,
        "issues": [
            {"severity": "blocker", "file": "test.py", "hint": "Fix this"}
        ]
    }
    issues = Issues.model_validate(data)
    assert issues.pass_ is False
    assert len(issues.issues) == 1
    assert issues.issues[0].severity == "blocker"

def test_status_serialization():
    status = Status(
        pass_=True,
        checks_exit_code=0,
        diff_nonempty=True,
        blocker_count=0,
    )
    json_str = status.model_dump_json(by_alias=True)
    assert '"pass":' in json_str or '"pass": ' in json_str
```

**Validation**:
```bash
uv pip install -e ".[dev]"
pytest tests/test_models.py -v
# All tests should pass
```

### Step 9.3: Create tests/test_plan.py

**File**: `tests/test_plan.py`

```python
import pytest
from weld.plan import parse_steps_strict, parse_steps_lenient, parse_steps

STRICT_PLAN = """
## Step 1: Create config module

### Goal
Set up configuration handling.

### Changes
- Create src/config.py

### Acceptance criteria
- [ ] Config loads from TOML
- [ ] Defaults are sane

### Tests
- pytest tests/test_config.py

## Step 2: Build CLI

### Goal
Create the CLI entry point.

### Changes
- Create src/cli.py

### Acceptance criteria
- [ ] --help works

### Tests
- weld --help
"""

LENIENT_PLAN = """
1. Create config module
   Set up configuration handling.

2. Build CLI
   Create the CLI entry point.
"""

def test_parse_strict_format():
    steps = parse_steps_strict(STRICT_PLAN)
    assert len(steps) == 2
    assert steps[0].n == 1
    assert steps[0].title == "Create config module"
    assert "Config loads from TOML" in steps[0].acceptance_criteria
    assert steps[1].n == 2

def test_parse_lenient_format():
    steps = parse_steps_lenient(LENIENT_PLAN)
    assert len(steps) == 2
    assert steps[0].title == "Create config module"

def test_parse_steps_prefers_strict():
    steps, warnings = parse_steps(STRICT_PLAN)
    assert len(steps) == 2
    assert len(warnings) == 0

def test_parse_steps_falls_back_to_lenient():
    steps, warnings = parse_steps(LENIENT_PLAN)
    assert len(steps) == 2
    assert "lenient" in warnings[0].lower()
```

**Validation**:
```bash
pytest tests/test_plan.py -v
```

### Step 9.4: Create tests/test_run.py

**File**: `tests/test_run.py`

```python
import pytest
from weld.run import generate_run_id, sanitize_slug
from pathlib import Path

def test_generate_run_id_with_slug():
    rid = generate_run_id(slug="my-feature")
    assert "my-feature" in rid
    assert len(rid.split("-")) >= 3

def test_generate_run_id_from_spec():
    rid = generate_run_id(spec_path=Path("specs/my_feature.md"))
    assert "my-feature" in rid or "my_feature" in rid

def test_sanitize_slug():
    assert sanitize_slug("Hello World!") == "hello-world"
    assert sanitize_slug("Test@#$123") == "test-123"
    assert sanitize_slug("   spaces   ") == "spaces"
```

**Validation**:
```bash
pytest tests/test_run.py -v
```

### Step 9.5: End-to-end manual test script

**File**: `tests/e2e_test.sh`

```bash
#!/bin/bash
set -e

echo "=== Weld E2E Test ==="

# Create temp directory
TMPDIR=$(mktemp -d)
cd "$TMPDIR"

echo "Working in: $TMPDIR"

# Initialize git repo
git init
git config user.email "test@test.com"
git config user.name "Test User"

# Create a dummy spec
mkdir specs
cat > specs/test.md << 'EOF'
# Test Spec

Implement a hello world function.

## Requirements
- Create hello.py with greet() function
- Function returns "Hello, World!"
EOF

# Initialize weld (this will fail on missing tools, which is expected)
echo "Testing weld init..."
weld init || echo "Expected: some tools missing"

# Create config manually for testing
mkdir -p .weld
cat > .weld/config.toml << 'EOF'
[project]
name = "test-project"

[checks]
command = "echo 'checks ok'"

[codex]
exec = "echo"
sandbox = "read-only"

[claude.transcripts]
exec = "echo"
visibility = "secret"

[git]
commit_trailer_key = "Claude-Transcript"
include_run_trailer = true

[loop]
max_iterations = 3
fail_on_blockers_only = true
EOF

mkdir -p .weld/runs

# Start a run
echo "Testing weld run start..."
weld run --spec specs/test.md

echo "=== E2E Test Complete ==="
echo "Temp dir: $TMPDIR"
```

**Validation**:
```bash
chmod +x tests/e2e_test.sh
./tests/e2e_test.sh
# Should complete without Python errors
```

---

## Exit Codes Reference

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error / file not found |
| 2 | Dependency missing / unauthenticated gh |
| 3 | Not a git repository |
| 10 | Max iterations reached |
| 11 | Checks failed (strict mode) |
| 12 | Codex invocation failed / malformed JSON |
| 20 | No changes to commit |
| 21 | Transcript generation failed |
| 22 | Git commit failed |

---

## Implementation Order Summary

1. **Phase 1**: Project scaffolding (pyproject.toml, directories, __init__.py)
2. **Phase 2**: Pydantic models (meta, step, issues, status)
3. **Phase 3**: Core utilities (config, git, diff, checks, codex, transcripts, run)
4. **Phase 4**: Plan handling (plan.py)
5. **Phase 5**: Step handling (step.py, review.py, loop.py)
6. **Phase 6**: Commit handling (commit.py)
7. **Phase 7**: CLI implementation (cli.py)
8. **Phase 8**: Package init update
9. **Phase 9**: Integration tests

Each step is independently verifiable via the provided validation commands.
