"""Tests for weld data models."""

from pathlib import Path

from weld.models import Issues, Meta, Status, Step


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
