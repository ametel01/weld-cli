"""External service integrations for weld.

This package provides interfaces to external tools and services:
- git: Git operations
- claude: Claude CLI integration
- transcripts: Transcript gist generation
- filesystem: Common file I/O operations
- session_detector: Claude Code session detection
- session_tracker: Session registry management
- transcript_renderer: Transcript JSONL to markdown rendering
- gist_uploader: GitHub Gist upload via gh CLI
"""

from .claude import ClaudeError, run_claude, run_claude_interactive
from .filesystem import (
    dir_exists,
    ensure_directory,
    file_exists,
    read_file,
    read_file_optional,
    write_file,
)
from .gist_uploader import (
    GistError,
    GistResult,
    generate_gist_description,
    generate_transcript_filename,
    upload_gist,
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
from .session_detector import (
    detect_current_session,
    encode_project_path,
    get_claude_sessions_dir,
    get_session_id,
)
from .session_tracker import (
    SNAPSHOT_EXCLUDES,
    SessionRegistry,
    compute_changes,
    get_file_snapshot,
    get_registry,
    track_session_activity,
)
from .transcript_renderer import (
    MAX_MESSAGES,
    MAX_TEXT_SIZE,
    MAX_THINKING_SIZE,
    MAX_TOOL_RESULT_SIZE,
    MAX_TRANSCRIPT_SIZE,
    REDACTION_PATTERNS,
    redact_secrets,
    render_message,
    render_transcript,
    truncate_content,
)
from .transcripts import TranscriptError, TranscriptResult, run_transcript_gist

__all__ = [
    "MAX_MESSAGES",
    "MAX_TEXT_SIZE",
    "MAX_THINKING_SIZE",
    "MAX_TOOL_RESULT_SIZE",
    "MAX_TRANSCRIPT_SIZE",
    "REDACTION_PATTERNS",
    "SNAPSHOT_EXCLUDES",
    "ClaudeError",
    "GistError",
    "GistResult",
    "GitError",
    "SessionRegistry",
    "TranscriptError",
    "TranscriptResult",
    "commit_file",
    "compute_changes",
    "detect_current_session",
    "dir_exists",
    "encode_project_path",
    "ensure_directory",
    "file_exists",
    "generate_gist_description",
    "generate_transcript_filename",
    "get_claude_sessions_dir",
    "get_current_branch",
    "get_diff",
    "get_file_snapshot",
    "get_head_sha",
    "get_registry",
    "get_repo_root",
    "get_session_id",
    "get_staged_files",
    "get_status_porcelain",
    "has_staged_changes",
    "is_file_staged",
    "read_file",
    "read_file_optional",
    "redact_secrets",
    "render_message",
    "render_transcript",
    "run_claude",
    "run_claude_interactive",
    "run_git",
    "run_transcript_gist",
    "stage_all",
    "stage_files",
    "track_session_activity",
    "truncate_content",
    "unstage_all",
    "upload_gist",
    "write_file",
]
