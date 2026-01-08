"""Transcript rendering service for Claude session files.

Renders Claude Code .jsonl session files to markdown format with:
- Secret redaction (API keys, tokens, credentials)
- Content truncation (tool results, thinking blocks)
- Size limits (per-message and total)
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Redaction patterns for sensitive data
REDACTION_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{20,}", "[REDACTED-API-KEY]"),
    (r"ghp_[a-zA-Z0-9]{36,}", "[REDACTED-GITHUB-TOKEN]"),
    (r"gho_[a-zA-Z0-9]{36,}", "[REDACTED-GITHUB-TOKEN]"),
    (r"Bearer [a-zA-Z0-9\-._~+/]+=*", "[REDACTED-BEARER-TOKEN]"),
    (r"AKIA[A-Z0-9]{16}", "[REDACTED-AWS-KEY]"),
    (r"xox[baprs]-[a-zA-Z0-9\-]+", "[REDACTED-SLACK-TOKEN]"),
    (r"(SECRET|TOKEN|PASSWORD|API_KEY|APIKEY|AUTH)[=:]\s*[^\s\n]+", r"\1=[REDACTED]"),
    (r"/[^\s]*secret[^\s]*/[^\s]*", "[REDACTED-PATH]"),
    (r"/[^\s]*credential[^\s]*/[^\s]*", "[REDACTED-PATH]"),
]

MAX_TOOL_RESULT_SIZE = 2048  # 2KB - aggressive truncation for verbose tool output
MAX_TEXT_SIZE = 10240  # 10KB - user/assistant text content
MAX_THINKING_SIZE = 5120  # 5KB - thinking blocks (less verbose than text, more than tools)
MAX_TRANSCRIPT_SIZE = 1024 * 1024  # 1MB - total transcript size limit
MAX_MESSAGES = 500  # Maximum number of messages to include


def redact_secrets(text: str) -> str:
    """Apply all redaction patterns to text.

    Args:
        text: Text to redact

    Returns:
        Text with sensitive data replaced by redaction markers
    """
    for pattern, replacement in REDACTION_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def truncate_content(content: str, max_size: int, label: str = "") -> str:
    """Truncate content with indicator.

    Args:
        content: Content to truncate
        max_size: Maximum size in bytes
        label: Optional label for truncation message

    Returns:
        Truncated content with size indicator if truncated
    """
    if len(content) <= max_size:
        return content
    size_kb = len(content) // 1024
    return f"{content[:max_size]}\n[truncated{' - ' + label if label else ''} - {size_kb}KB]"


def render_message(msg: dict[str, Any]) -> str:
    """Render a single message to markdown.

    Args:
        msg: Message dict from JSONL with type, message, timestamp fields

    Returns:
        Markdown string for the message, empty string for non-user/assistant messages
    """
    msg_type = msg.get("type", "")
    if msg_type not in ("user", "assistant"):
        return ""

    message = msg.get("message", {})
    role = message.get("role", msg_type).capitalize()
    timestamp = msg.get("timestamp", "")

    # Parse timestamp if present
    time_str = ""
    if timestamp:
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            time_str = f" ({dt.strftime('%H:%M:%S')})"
        except (ValueError, TypeError):
            pass

    lines = [f"## {role}{time_str}", ""]

    content = message.get("content", "")
    if isinstance(content, str):
        lines.append(redact_secrets(truncate_content(content, MAX_TEXT_SIZE)))
    elif isinstance(content, list):
        for block in content:
            block_type = block.get("type", "")

            if block_type == "text":
                text = block.get("text", "")
                lines.append(redact_secrets(truncate_content(text, MAX_TEXT_SIZE)))

            elif block_type == "tool_use":
                name = block.get("name", "unknown")
                input_data = block.get("input", {})
                lines.append(f"\n### Tool: {name}\n")
                if isinstance(input_data, dict):
                    # Show key parameters concisely
                    for key, value in input_data.items():
                        if isinstance(value, str) and len(value) > 200:
                            value = value[:200] + "..."
                        lines.append(f"**{key}**: `{value}`")

            elif block_type == "tool_result":
                result = block.get("content", "")
                if isinstance(result, str):
                    result = redact_secrets(
                        truncate_content(result, MAX_TOOL_RESULT_SIZE, "tool result")
                    )
                    lines.append(f"\n```\n{result}\n```")

            elif block_type == "thinking":
                text = block.get("thinking", block.get("text", ""))
                lines.append(
                    f"\n*Thinking: {truncate_content(text, MAX_THINKING_SIZE, 'thinking')}*"
                )

    lines.append("\n---\n")
    return "\n".join(lines)


def render_transcript(
    session_file: Path,
    project_name: str = "unknown",
) -> str:
    """Render Claude session JSONL to markdown transcript.

    Args:
        session_file: Path to .jsonl session file
        project_name: Project name for header

    Returns:
        Markdown string

    Raises:
        FileNotFoundError: If session_file does not exist
    """
    session_id = session_file.stem

    # Read and parse messages
    messages = []
    for line in session_file.read_text().splitlines():
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
            messages.append(msg)
        except json.JSONDecodeError:
            continue

    # Filter to user/assistant only
    messages = [m for m in messages if m.get("type") in ("user", "assistant")]

    # Apply limits
    if len(messages) > MAX_MESSAGES:
        messages = messages[:MAX_MESSAGES]

    # Build header
    header = f"""# Claude Code Transcript

**Session**: {session_id}
**Project**: {project_name}
**Date**: {datetime.now(UTC).strftime("%Y-%m-%d")}
**Messages**: {len(messages)}

---

"""

    # Render messages
    body_parts = []
    total_size = len(header)

    for msg in messages:
        rendered = render_message(msg)
        if total_size + len(rendered) > MAX_TRANSCRIPT_SIZE:
            body_parts.append("\n[transcript truncated due to size]\n")
            break
        body_parts.append(rendered)
        total_size += len(rendered)

    return header + "\n".join(body_parts)
