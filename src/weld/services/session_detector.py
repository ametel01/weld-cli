"""Claude Code session detection utilities.

This module provides functions to detect and identify Claude Code sessions
from Claude's local storage. Sessions are stored as JSONL files in
~/.claude/projects/{encoded-path}/.

The session detection logic:
1. Encodes the repo path to match Claude's directory naming scheme
2. Finds all .jsonl session files in the projects directory
3. Excludes subagent sessions (agent-*.jsonl) and empty files
4. Returns the most recently modified session
"""

from pathlib import Path


def encode_project_path(repo_root: Path) -> str:
    """Encode repo path for Claude sessions directory.

    Claude Code stores sessions in ~/.claude/projects/{encoded-path}/
    where the encoded path replaces forward slashes with hyphens.

    Args:
        repo_root: Absolute path to the repository root

    Returns:
        Encoded path string (e.g., "/home/user/project" -> "-home-user-project")

    Examples:
        >>> encode_project_path(Path("/home/user/source/my-project"))
        '-home-user-source-my-project'
    """
    return "-" + str(repo_root.resolve()).replace("/", "-").lstrip("-")


def get_claude_sessions_dir(repo_root: Path) -> Path | None:
    """Get Claude sessions directory for this repo.

    Args:
        repo_root: Absolute path to the repository root

    Returns:
        Path to Claude sessions directory, or None if it doesn't exist
    """
    encoded = encode_project_path(repo_root)
    sessions_dir = Path.home() / ".claude" / "projects" / encoded
    return sessions_dir if sessions_dir.exists() else None


def detect_current_session(repo_root: Path) -> Path | None:
    """Find the most recently modified Claude session for this repo.

    Scans Claude's session storage to find the active session file.
    This is useful for attaching transcripts to commits.

    Args:
        repo_root: Absolute path to the repository root

    Returns:
        Path to .jsonl session file, or None if no session found

    Rules:
        - Excludes files starting with "agent-" (subagent sessions)
        - Excludes empty files (no content to transcript)
        - Returns the most recently modified session file
    """
    sessions_dir = get_claude_sessions_dir(repo_root)
    if not sessions_dir:
        return None

    candidates: list[Path] = []
    for f in sessions_dir.glob("*.jsonl"):
        # Skip subagent session files
        if f.name.startswith("agent-"):
            continue
        # Skip empty files
        if f.stat().st_size == 0:
            continue
        candidates.append(f)

    if not candidates:
        return None

    # Return most recently modified
    return max(candidates, key=lambda f: f.stat().st_mtime)


def get_session_id(session_file: Path) -> str:
    """Extract session ID from filename.

    The session ID is the UUID portion of the filename, which is
    the stem (filename without extension).

    Args:
        session_file: Path to the session .jsonl file

    Returns:
        Session ID string (e.g., "abc123-def456" from "abc123-def456.jsonl")
    """
    return session_file.stem
