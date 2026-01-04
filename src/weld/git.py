"""Git operations wrapper for weld."""

import subprocess
from pathlib import Path


class GitError(Exception):
    """Git command failed."""

    pass


def run_git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    """Run git command and return stdout.

    Args:
        *args: Git command arguments
        cwd: Working directory for git command
        check: Whether to raise GitError on non-zero exit

    Returns:
        Stripped stdout output

    Raises:
        GitError: If check=True and git command fails
    """
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
    """Get git repository root directory.

    Args:
        cwd: Working directory to start from

    Returns:
        Path to repository root

    Raises:
        GitError: If not in a git repository
    """
    try:
        root = run_git("rev-parse", "--show-toplevel", cwd=cwd)
        return Path(root)
    except GitError:
        raise GitError("Not a git repository") from None


def get_current_branch(cwd: Path | None = None) -> str:
    """Get current branch name.

    Args:
        cwd: Working directory

    Returns:
        Current branch name
    """
    return run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)


def get_head_sha(cwd: Path | None = None) -> str:
    """Get HEAD commit SHA.

    Args:
        cwd: Working directory

    Returns:
        Full HEAD commit SHA
    """
    return run_git("rev-parse", "HEAD", cwd=cwd)


def get_diff(staged: bool = False, cwd: Path | None = None) -> str:
    """Get diff output.

    Args:
        staged: If True, get staged diff (--staged)
        cwd: Working directory

    Returns:
        Diff output string
    """
    args = ["diff", "--staged"] if staged else ["diff"]
    return run_git(*args, cwd=cwd, check=False)


def get_status_porcelain(cwd: Path | None = None) -> str:
    """Get status in porcelain format.

    Args:
        cwd: Working directory

    Returns:
        Porcelain status output
    """
    return run_git("status", "--porcelain", cwd=cwd, check=False)


def stage_all(cwd: Path | None = None) -> None:
    """Stage all changes.

    Args:
        cwd: Working directory
    """
    run_git("add", "-A", cwd=cwd)


def commit_file(message_file: Path, cwd: Path | None = None) -> str:
    """Create commit using message file, return commit SHA.

    Args:
        message_file: Path to file containing commit message
        cwd: Working directory

    Returns:
        New commit SHA
    """
    run_git("commit", "-F", str(message_file), cwd=cwd)
    return get_head_sha(cwd=cwd)


def has_staged_changes(cwd: Path | None = None) -> bool:
    """Check if there are staged changes.

    Args:
        cwd: Working directory

    Returns:
        True if there are staged changes
    """
    result = subprocess.run(
        ["git", "diff", "--staged", "--quiet"],
        cwd=cwd,
        capture_output=True,
    )
    # git diff --quiet exits 1 if there are differences
    return result.returncode != 0
