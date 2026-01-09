"""End-to-end tests for implement tracking and session-based commits."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from weld.cli import app
from weld.services.gist_uploader import GistResult
from weld.services.session_detector import encode_project_path
from weld.services.session_tracker import SessionRegistry


@pytest.mark.cli
@pytest.mark.slow
def test_implement_to_commit_workflow(runner, temp_git_repo):
    """End-to-end: implement tracks → commit groups by session."""

    # 1. Initialize weld
    def mock_subprocess_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
        result = runner.invoke(app, ["init"], input="test-project\n")

    assert result.exit_code == 0

    # 2. Create plan file
    plan_file = temp_git_repo / "plan.md"
    plan_file.write_text("""
## Phase 1: Setup

### Step 1.1: Create module

#### Goal
Create calculator module

#### Files
- src/calc.py

#### Validation
```bash
test -f src/calc.py
```
""")
    subprocess.run(["git", "add", "plan.md"], cwd=temp_git_repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add plan"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )

    # 3. Create fake Claude session
    claude_dir = Path.home() / ".claude" / "projects" / encode_project_path(temp_git_repo)
    claude_dir.mkdir(parents=True, exist_ok=True)
    session_file = claude_dir / "test-session-abc123.jsonl"
    session_file.write_text('{"type":"user","message":{"role":"user","content":"test"}}\n')

    # 4. Mock implement to create files
    def mock_run_claude(*args, **kwargs):
        src_dir = temp_git_repo / "src"
        src_dir.mkdir(exist_ok=True)
        calc_file = src_dir / "calc.py"
        calc_file.write_text("def add(a, b): return a + b\n")
        return "Implementation complete."

    with patch("weld.commands.implement.run_claude", side_effect=mock_run_claude):
        result = runner.invoke(app, ["implement", "plan.md", "--step", "1.1"])

    assert result.exit_code == 0

    # 5. Verify registry created
    registry_path = temp_git_repo / ".weld" / "sessions" / "registry.jsonl"
    assert registry_path.exists()

    # 6. Stage only the files created by implement
    subprocess.run(["git", "add", "src/calc.py"], cwd=temp_git_repo, check=True)

    # 7. Mock Claude for commit message and mock gist upload
    commit_response = """<commit>
<files>
src/calc.py
</files>
<commit_message>
Add calculator module
</commit_message>
<changelog_entry>
### Added
- Calculator with add function
</changelog_entry>
</commit>"""

    with (
        patch("weld.commands.commit.run_claude", return_value=commit_response),
        patch("weld.commands.commit.upload_gist") as mock_gist,
        patch("weld.commands.commit.render_transcript", return_value="# Transcript"),
    ):
        mock_gist.return_value = GistResult(
            gist_url="https://gist.github.com/abc123",
            gist_id="abc123",
        )

        result = runner.invoke(app, ["commit", "--skip-changelog"])

    assert result.exit_code == 0

    # 8. Verify commit created
    log_result = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=temp_git_repo,
        capture_output=True,
        text=True,
    )
    assert "Add calculator module" in log_result.stdout

    # 9. Verify transcript trailer
    body_result = subprocess.run(
        ["git", "log", "-1", "--format=%b"],
        cwd=temp_git_repo,
        capture_output=True,
        text=True,
    )
    assert "Claude-Transcript:" in body_result.stdout
    assert "https://gist.github.com/abc123" in body_result.stdout

    # 10. Verify registry pruned
    registry = SessionRegistry(registry_path)
    assert len(registry.sessions) == 0  # Session should be removed after commit

    # Cleanup
    import shutil

    shutil.rmtree(claude_dir)


@pytest.mark.cli
def test_commit_without_tracking_falls_back(runner, temp_git_repo):
    """Commit without session tracking should use logical grouping."""

    # 1. Initialize weld
    def mock_subprocess_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    with patch("weld.commands.init.subprocess.run", side_effect=mock_subprocess_run):
        result = runner.invoke(app, ["init"], input="test-project\n")

    assert result.exit_code == 0

    # 2. Create and stage files manually (no implement tracking)
    test_file = temp_git_repo / "test.txt"
    test_file.write_text("content")
    subprocess.run(["git", "add", "test.txt"], cwd=temp_git_repo, check=True)

    # 3. Mock Claude for commit message
    commit_response = """<commit>
<files>
test.txt
</files>
<commit_message>
Add test file
</commit_message>
<changelog_entry>
</changelog_entry>
</commit>"""

    with patch("weld.commands.commit.run_claude", return_value=commit_response):
        result = runner.invoke(app, ["commit", "--skip-transcript", "--skip-changelog"])

    assert result.exit_code == 0

    # Verify commit created using fallback (no session grouping)
    log_result = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=temp_git_repo,
        capture_output=True,
        text=True,
    )
    assert "Add test file" in log_result.stdout
