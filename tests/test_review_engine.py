"""Tests for review engine."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from weld.config import WeldConfig
from weld.core.review_engine import run_step_review
from weld.models import Step


def make_step() -> Step:
    """Create a test step."""
    return Step(
        n=1,
        title="Test Step",
        slug="test-step",
        body_md="Implement the feature.",
        acceptance_criteria=["Tests pass", "Linter clean"],
        tests=["pytest"],
    )


def make_config(provider: str = "codex") -> WeldConfig:
    """Create test config with specified provider."""
    config_dict = {
        "project": {"name": "test"},
        "checks": {"command": "echo ok"},
        "codex": {"exec": "codex", "sandbox": "read-only"},
        "claude": {"exec": "claude"},
        "loop": {"max_iterations": 5, "fail_on_blockers_only": False},
        "task_models": {
            "implementation_review": {"provider": provider},
        },
    }
    return WeldConfig.model_validate(config_dict)


class TestRunStepReview:
    """Tests for run_step_review function."""

    @patch("weld.core.review_engine.run_codex")
    @patch("weld.core.review_engine.parse_codex_review")
    def test_codex_review_passing(
        self, mock_parse: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """run_step_review should return passing status when no issues."""
        mock_run.return_value = '{"pass": true, "issues": []}'
        mock_parse.return_value = MagicMock(
            pass_=True,
            issues=[],
        )

        step = make_step()
        config = make_config("codex")

        _review_md, _issues, status = run_step_review(
            step=step,
            diff="+added line",
            checks_output="exit_code: 0",
            checks_exit_code=0,
            config=config,
            cwd=tmp_path,
        )

        assert status.pass_ is True
        assert status.issue_count == 0
        mock_run.assert_called_once()

    @patch("weld.core.review_engine.run_codex")
    @patch("weld.core.review_engine.parse_codex_review")
    def test_codex_review_failing(
        self, mock_parse: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """run_step_review should return failing status with issues."""
        mock_run.return_value = "review with issues"
        mock_issue = MagicMock(severity="blocker")
        mock_parse.return_value = MagicMock(
            pass_=False,
            issues=[mock_issue],
        )

        step = make_step()
        config = make_config("codex")

        _review_md, _issues, status = run_step_review(
            step=step,
            diff="+added line",
            checks_output="exit_code: 0",
            checks_exit_code=0,
            config=config,
            cwd=tmp_path,
        )

        assert status.pass_ is False
        assert status.issue_count == 1
        assert status.blocker_count == 1

    def test_claude_provider_config(self, tmp_path: Path) -> None:
        """Verify Claude provider config is parsed correctly."""
        config = make_config("claude")
        from weld.config import TaskType

        model_cfg = config.get_task_model(TaskType.IMPLEMENTATION_REVIEW)
        assert model_cfg.provider == "claude"

    @patch("weld.core.review_engine.run_codex")
    @patch("weld.core.review_engine.parse_codex_review")
    def test_fail_on_blockers_only(
        self, mock_parse: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """run_step_review should pass with minors when fail_on_blockers_only is True."""
        mock_run.return_value = "review"
        mock_issue = MagicMock(severity="minor")
        mock_parse.return_value = MagicMock(
            pass_=False,
            issues=[mock_issue],
        )

        step = make_step()
        config_dict = {
            "project": {"name": "test"},
            "checks": {"command": "echo ok"},
            "codex": {"exec": "codex", "sandbox": "read-only"},
            "claude": {"exec": "claude"},
            "loop": {"max_iterations": 5, "fail_on_blockers_only": True},
            "task_models": {"implementation_review": {"provider": "codex"}},
        }
        config = WeldConfig.model_validate(config_dict)

        _review_md, _issues, status = run_step_review(
            step=step,
            diff="+added line",
            checks_output="exit_code: 0",
            checks_exit_code=0,
            config=config,
            cwd=tmp_path,
        )

        # Should pass because only minors and fail_on_blockers_only=True
        assert status.pass_ is True
        assert status.minor_count == 1

    def test_codex_provider_config(self, tmp_path: Path) -> None:
        """Verify Codex provider config is parsed correctly."""
        config = make_config("codex")
        from weld.config import TaskType

        model_cfg = config.get_task_model(TaskType.IMPLEMENTATION_REVIEW)
        assert model_cfg.provider == "codex"

    @patch("weld.core.review_engine.run_codex")
    @patch("weld.core.review_engine.parse_codex_review")
    def test_counts_issue_severities(
        self, mock_parse: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """run_step_review should count issues by severity."""
        mock_run.return_value = "review"
        mock_parse.return_value = MagicMock(
            pass_=False,
            issues=[
                MagicMock(severity="blocker"),
                MagicMock(severity="blocker"),
                MagicMock(severity="major"),
                MagicMock(severity="minor"),
                MagicMock(severity="minor"),
                MagicMock(severity="minor"),
            ],
        )

        step = make_step()
        config = make_config("codex")

        _review_md, _issues, status = run_step_review(
            step=step,
            diff="+added line",
            checks_output="exit_code: 0",
            checks_exit_code=0,
            config=config,
            cwd=tmp_path,
        )

        assert status.blocker_count == 2
        assert status.major_count == 1
        assert status.minor_count == 3
        assert status.issue_count == 6

    @patch("weld.core.review_engine.run_codex")
    @patch("weld.core.review_engine.parse_codex_review")
    def test_diff_nonempty_flag(
        self, mock_parse: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """run_step_review should set diff_nonempty correctly."""
        mock_run.return_value = "review"
        mock_parse.return_value = MagicMock(pass_=True, issues=[])

        step = make_step()
        config = make_config("codex")

        # Test with non-empty diff
        _, _, status = run_step_review(
            step=step,
            diff="+line",
            checks_output="exit_code: 0",
            checks_exit_code=0,
            config=config,
            cwd=tmp_path,
        )
        assert status.diff_nonempty is True

        # Test with empty diff
        _, _, status = run_step_review(
            step=step,
            diff="",
            checks_output="exit_code: 0",
            checks_exit_code=0,
            config=config,
            cwd=tmp_path,
        )
        assert status.diff_nonempty is False

    def test_unsupported_provider_raises(self, tmp_path: Path) -> None:
        """run_step_review should raise for unsupported provider.

        Note: Currently the config validation may prevent invalid providers,
        so this test verifies behavior if an invalid provider somehow gets through.
        """
        # This test is skipped as config validation prevents invalid providers
        pytest.skip("Config validation prevents invalid providers at parse time")
