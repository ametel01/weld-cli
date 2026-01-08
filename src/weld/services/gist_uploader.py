"""Gist uploader service for transcript publishing.

Uploads markdown transcripts to GitHub Gists via the gh CLI.
"""

import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel


class GistResult(BaseModel):
    """Result from gist upload."""

    gist_url: str
    gist_id: str


class GistError(Exception):
    """Gist upload failed."""

    pass


def upload_gist(
    content: str,
    filename: str,
    description: str,
    public: bool = False,
    cwd: Path | None = None,
    timeout: int = 60,
) -> GistResult:
    """Upload content to GitHub Gist via gh CLI.

    Args:
        content: Markdown content to upload
        filename: Filename for the gist (e.g., "project-abc12345.md")
        description: Gist description
        public: Whether gist should be public
        cwd: Working directory for gh command
        timeout: Timeout in seconds

    Returns:
        GistResult with URL and ID

    Raises:
        GistError: If upload fails
    """
    # Write to temp file (gh gist create requires a file)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix=filename.replace(".md", "-"),
        delete=False,
    ) as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        cmd = ["gh", "gist", "create", str(temp_path)]
        cmd.extend(["--desc", description])
        cmd.extend(["--filename", filename])
        if public:
            cmd.append("--public")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
        )

        if result.returncode != 0:
            stderr = result.stderr.lower()
            if "not logged in" in stderr or "auth" in stderr:
                raise GistError("Not authenticated. Run: gh auth login")
            raise GistError(f"Gist creation failed: {result.stderr}")

        gist_url = result.stdout.strip()
        if not gist_url.startswith("https://"):
            raise GistError(f"Unexpected gh output: {gist_url}")

        gist_id = gist_url.rstrip("/").split("/")[-1]

        return GistResult(gist_url=gist_url, gist_id=gist_id)

    except FileNotFoundError:
        raise GistError("gh CLI not found. Install: https://cli.github.com/") from None
    except subprocess.TimeoutExpired:
        raise GistError(f"Gist upload timed out after {timeout} seconds") from None
    finally:
        temp_path.unlink(missing_ok=True)


def generate_transcript_filename(project_name: str, session_id: str) -> str:
    """Generate transcript filename: {project}-{short-session-id}.md

    Args:
        project_name: Name of the project
        session_id: Full session ID (will be truncated to first 8 chars)

    Returns:
        Sanitized filename like "my-project-abc12345.md"
    """
    short_id = session_id[:8]
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in project_name)
    return f"{safe_name}-{short_id}.md"


def generate_gist_description(project_name: str, commit_subject: str) -> str:
    """Generate gist description including commit subject.

    Args:
        project_name: Name of the project
        commit_subject: First line of commit message

    Returns:
        Description like "my-project: Add new feature..."
    """
    subject = commit_subject[:60] + "..." if len(commit_subject) > 60 else commit_subject
    return f"{project_name}: {subject}"
