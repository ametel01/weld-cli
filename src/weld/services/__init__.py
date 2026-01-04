"""External service integrations for weld.

This package provides interfaces to external tools and services:
- git: Git operations
- codex: OpenAI Codex CLI integration
- claude: Claude CLI integration
- transcripts: Transcript gist generation
- checks: External checks runner
- diff: Diff capture utilities
- filesystem: Common file I/O operations
"""

from .checks import ChecksError, run_checks, write_checks
from .claude import ClaudeError, run_claude
from .claude import parse_review_json as parse_claude_review
from .codex import CodexError, extract_revised_plan, run_codex
from .codex import parse_review_json as parse_codex_review
from .diff import capture_diff, write_diff
from .filesystem import (
    dir_exists,
    ensure_directory,
    file_exists,
    read_file,
    read_file_optional,
    write_file,
)
from .git import (
    GitError,
    commit_file,
    get_current_branch,
    get_diff,
    get_head_sha,
    get_repo_root,
    get_status_porcelain,
    has_staged_changes,
    run_git,
    stage_all,
)
from .transcripts import TranscriptError, TranscriptResult, run_transcript_gist

__all__ = [
    "ChecksError",
    "ClaudeError",
    "CodexError",
    "GitError",
    "TranscriptError",
    "TranscriptResult",
    "capture_diff",
    "commit_file",
    "dir_exists",
    "ensure_directory",
    "extract_revised_plan",
    "file_exists",
    "get_current_branch",
    "get_diff",
    "get_head_sha",
    "get_repo_root",
    "get_status_porcelain",
    "has_staged_changes",
    "parse_claude_review",
    "parse_codex_review",
    "read_file",
    "read_file_optional",
    "run_checks",
    "run_claude",
    "run_codex",
    "run_git",
    "run_transcript_gist",
    "stage_all",
    "write_checks",
    "write_diff",
    "write_file",
]
