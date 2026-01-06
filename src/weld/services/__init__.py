"""External service integrations for weld.

This package provides interfaces to external tools and services:
- git: Git operations
- claude: Claude CLI integration
- transcripts: Transcript gist generation
- filesystem: Common file I/O operations
"""

from .claude import ClaudeError, run_claude
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
    get_staged_files,
    get_status_porcelain,
    has_staged_changes,
    is_file_staged,
    run_git,
    stage_all,
    stage_files,
    unstage_all,
)
from .transcripts import TranscriptError, TranscriptResult, run_transcript_gist

__all__ = [
    "ClaudeError",
    "GitError",
    "TranscriptError",
    "TranscriptResult",
    "commit_file",
    "dir_exists",
    "ensure_directory",
    "file_exists",
    "get_current_branch",
    "get_diff",
    "get_head_sha",
    "get_repo_root",
    "get_staged_files",
    "get_status_porcelain",
    "has_staged_changes",
    "is_file_staged",
    "read_file",
    "read_file_optional",
    "run_claude",
    "run_git",
    "run_transcript_gist",
    "stage_all",
    "stage_files",
    "unstage_all",
    "write_file",
]
