"""Tests for transcript renderer service."""

import json
from pathlib import Path

import pytest

from weld.services.transcript_renderer import (
    MAX_MESSAGES,
    MAX_TEXT_SIZE,
    MAX_THINKING_SIZE,
    MAX_TOOL_RESULT_SIZE,
    MAX_TRANSCRIPT_SIZE,
    redact_secrets,
    render_message,
    render_transcript,
    truncate_content,
)


class TestRedactSecrets:
    """Tests for redact_secrets function."""

    def test_redacts_api_key(self) -> None:
        """Should redact sk- style API keys."""
        text = "My key is sk-abcdefghij1234567890"  # pragma: allowlist secret
        result = redact_secrets(text)
        assert "[REDACTED-API-KEY]" in result
        assert "sk-abcdefghij1234567890" not in result  # pragma: allowlist secret

    def test_redacts_github_pat(self) -> None:
        """Should redact GitHub personal access tokens."""
        # pragma: allowlist nextline secret
        text = "Using ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij for auth"
        result = redact_secrets(text)
        assert "[REDACTED-GITHUB-TOKEN]" in result
        assert "ghp_" not in result

    def test_redacts_github_oauth(self) -> None:
        """Should redact GitHub OAuth tokens."""
        # pragma: allowlist nextline secret
        text = "Using gho_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij for access"
        result = redact_secrets(text)
        assert "[REDACTED-GITHUB-TOKEN]" in result

    def test_redacts_bearer_token(self) -> None:
        """Should redact Bearer tokens."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = redact_secrets(text)
        assert "[REDACTED-BEARER-TOKEN]" in result
        assert "eyJ" not in result

    def test_redacts_aws_key(self) -> None:
        """Should redact AWS access key IDs."""
        # pragma: allowlist nextline secret
        text = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"
        result = redact_secrets(text)
        assert "[REDACTED-AWS-KEY]" in result

    def test_redacts_slack_token(self) -> None:
        """Should redact Slack tokens."""
        text = "Using xoxb-123456789012-abcdef for Slack"
        result = redact_secrets(text)
        assert "[REDACTED-SLACK-TOKEN]" in result

    def test_redacts_password_assignment(self) -> None:
        """Should redact password assignments."""
        text = "PASSWORD= mysecretpassword123"
        result = redact_secrets(text)
        assert "PASSWORD=[REDACTED]" in result
        assert "mysecretpassword" not in result

    def test_redacts_api_key_assignment(self) -> None:
        """Should redact API key assignments."""
        text = "API_KEY: my_api_key_value"
        result = redact_secrets(text)
        assert "API_KEY=[REDACTED]" in result

    def test_redacts_secret_paths(self) -> None:
        """Should redact paths containing 'secret'."""
        text = "Reading /home/user/.secrets/api.key"
        result = redact_secrets(text)
        assert "[REDACTED-PATH]" in result

    def test_redacts_credential_paths(self) -> None:
        """Should redact paths containing 'credential'."""
        text = "File: /etc/credentials/db.conf"
        result = redact_secrets(text)
        assert "[REDACTED-PATH]" in result

    def test_preserves_normal_text(self) -> None:
        """Should not alter text without secrets."""
        text = "This is normal text with no secrets"
        result = redact_secrets(text)
        assert result == text

    def test_case_insensitive(self) -> None:
        """Should redact regardless of case."""
        text = "token: my_secret_token"
        result = redact_secrets(text)
        assert "token=[REDACTED]" in result


class TestTruncateContent:
    """Tests for truncate_content function."""

    def test_no_truncation_under_limit(self) -> None:
        """Should not truncate content under the limit."""
        content = "Short content"
        result = truncate_content(content, 100)
        assert result == content

    def test_truncates_over_limit(self) -> None:
        """Should truncate content over the limit."""
        content = "x" * 1000
        result = truncate_content(content, 100)
        assert len(result) < len(content)
        assert "[truncated" in result

    def test_includes_size_in_kb(self) -> None:
        """Should include original size in KB."""
        content = "x" * 5120  # 5KB
        result = truncate_content(content, 100)
        assert "5KB" in result

    def test_includes_label(self) -> None:
        """Should include optional label."""
        content = "x" * 1000
        result = truncate_content(content, 100, label="tool result")
        assert "tool result" in result

    def test_exactly_at_limit(self) -> None:
        """Should not truncate content exactly at limit."""
        content = "x" * 100
        result = truncate_content(content, 100)
        assert result == content


class TestRenderMessage:
    """Tests for render_message function."""

    def test_renders_user_message(self) -> None:
        """Should render user message with header."""
        msg = {
            "type": "user",
            "message": {"role": "user", "content": "Hello, Claude!"},
        }
        result = render_message(msg)
        assert "## User" in result
        assert "Hello, Claude!" in result

    def test_renders_assistant_message(self) -> None:
        """Should render assistant message with header."""
        msg = {
            "type": "assistant",
            "message": {"role": "assistant", "content": "Hello! How can I help?"},
        }
        result = render_message(msg)
        assert "## Assistant" in result
        assert "Hello! How can I help?" in result

    def test_ignores_non_message_types(self) -> None:
        """Should return empty string for non-user/assistant types."""
        msg = {"type": "system", "message": {"content": "System message"}}
        result = render_message(msg)
        assert result == ""

    def test_parses_timestamp(self) -> None:
        """Should parse and display timestamp."""
        msg = {
            "type": "user",
            "timestamp": "2024-01-15T10:30:00Z",
            "message": {"role": "user", "content": "Hello"},
        }
        result = render_message(msg)
        assert "(10:30:00)" in result

    def test_handles_list_content_text_block(self) -> None:
        """Should handle content as list of text blocks."""
        msg = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Block text content"}],
            },
        }
        result = render_message(msg)
        assert "Block text content" in result

    def test_handles_tool_use_block(self) -> None:
        """Should render tool use blocks."""
        msg = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "read_file",
                        "input": {"path": "/tmp/test.py"},
                    }
                ],
            },
        }
        result = render_message(msg)
        assert "### Tool: read_file" in result
        assert "**path**:" in result

    def test_truncates_long_tool_input(self) -> None:
        """Should truncate long tool input values."""
        msg = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "write_file",
                        "input": {"content": "x" * 500},
                    }
                ],
            },
        }
        result = render_message(msg)
        assert "..." in result

    def test_handles_tool_result_block(self) -> None:
        """Should render tool result blocks."""
        msg = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "content": "File contents here"}],
            },
        }
        result = render_message(msg)
        assert "```" in result
        assert "File contents here" in result

    def test_handles_thinking_block(self) -> None:
        """Should render thinking blocks."""
        msg = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "thinking", "thinking": "Let me analyze this..."}],
            },
        }
        result = render_message(msg)
        assert "*Thinking:" in result
        assert "Let me analyze this" in result

    def test_redacts_secrets_in_content(self) -> None:
        """Should redact secrets in message content."""
        msg = {
            "type": "user",
            "message": {"role": "user", "content": "My API key is sk-12345678901234567890"},
        }
        result = render_message(msg)
        assert "[REDACTED-API-KEY]" in result
        assert "sk-12345678901234567890" not in result

    def test_handles_missing_timestamp(self) -> None:
        """Should handle messages without timestamp."""
        msg = {
            "type": "user",
            "message": {"role": "user", "content": "No timestamp"},
        }
        result = render_message(msg)
        assert "## User" in result
        assert "No timestamp" in result

    def test_ends_with_separator(self) -> None:
        """Should end with markdown separator."""
        msg = {
            "type": "user",
            "message": {"role": "user", "content": "Test"},
        }
        result = render_message(msg)
        assert "---" in result


class TestRenderTranscript:
    """Tests for render_transcript function."""

    def test_renders_full_transcript(self, tmp_path: Path) -> None:
        """Should render complete transcript with header and messages."""
        session_file = tmp_path / "test-session.jsonl"
        messages = [
            {"type": "user", "message": {"role": "user", "content": "Hello"}},
            {"type": "assistant", "message": {"role": "assistant", "content": "Hi!"}},
        ]
        session_file.write_text("\n".join(json.dumps(m) for m in messages))

        result = render_transcript(session_file, project_name="test-project")

        assert "# Claude Code Transcript" in result
        assert "**Session**: test-session" in result
        assert "**Project**: test-project" in result
        assert "**Messages**: 2" in result
        assert "## User" in result
        assert "Hello" in result
        assert "## Assistant" in result
        assert "Hi!" in result

    def test_handles_malformed_jsonl(self, tmp_path: Path) -> None:
        """Should skip malformed JSONL lines."""
        session_file = tmp_path / "session.jsonl"
        content = (
            '{"type": "user", "message": {"role": "user", "content": "Valid"}}\n'
            "not valid json\n"
            '{"type": "assistant", "message": {"role": "assistant", "content": "Also valid"}}'
        )
        session_file.write_text(content)

        result = render_transcript(session_file)

        assert "Valid" in result
        assert "Also valid" in result
        assert "**Messages**: 2" in result

    def test_handles_empty_lines(self, tmp_path: Path) -> None:
        """Should skip empty lines in JSONL."""
        session_file = tmp_path / "session.jsonl"
        content = (
            '{"type": "user", "message": {"role": "user", "content": "Message"}}\n'
            "\n"
            "\n"
            '{"type": "assistant", "message": {"role": "assistant", "content": "Reply"}}'
        )
        session_file.write_text(content)

        result = render_transcript(session_file)

        assert "**Messages**: 2" in result

    def test_filters_non_user_assistant(self, tmp_path: Path) -> None:
        """Should only include user and assistant messages."""
        session_file = tmp_path / "session.jsonl"
        messages = [
            {"type": "system", "message": {"content": "System setup"}},
            {"type": "user", "message": {"role": "user", "content": "Hello"}},
            {"type": "result", "data": "some result"},
            {"type": "assistant", "message": {"role": "assistant", "content": "Hi!"}},
        ]
        session_file.write_text("\n".join(json.dumps(m) for m in messages))

        result = render_transcript(session_file)

        assert "**Messages**: 2" in result
        assert "System setup" not in result
        assert "some result" not in result

    def test_limits_message_count(self, tmp_path: Path) -> None:
        """Should limit to MAX_MESSAGES."""
        session_file = tmp_path / "session.jsonl"
        messages = [
            {"type": "user", "message": {"role": "user", "content": f"Message {i}"}}
            for i in range(MAX_MESSAGES + 50)
        ]
        session_file.write_text("\n".join(json.dumps(m) for m in messages))

        result = render_transcript(session_file)

        assert f"**Messages**: {MAX_MESSAGES}" in result

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError for missing file."""
        missing_file = tmp_path / "nonexistent.jsonl"

        with pytest.raises(FileNotFoundError):
            render_transcript(missing_file)

    def test_default_project_name(self, tmp_path: Path) -> None:
        """Should use 'unknown' as default project name."""
        session_file = tmp_path / "session.jsonl"
        session_file.write_text('{"type": "user", "message": {"role": "user", "content": "Test"}}')

        result = render_transcript(session_file)

        assert "**Project**: unknown" in result

    def test_uses_session_filename_as_id(self, tmp_path: Path) -> None:
        """Should use session filename (without extension) as session ID."""
        session_file = tmp_path / "abc123-session.jsonl"
        session_file.write_text('{"type": "user", "message": {"role": "user", "content": "Test"}}')

        result = render_transcript(session_file)

        assert "**Session**: abc123-session" in result


class TestSizeLimits:
    """Tests for size limit constants and enforcement."""

    def test_max_tool_result_size(self) -> None:
        """MAX_TOOL_RESULT_SIZE should be 2KB."""
        assert MAX_TOOL_RESULT_SIZE == 2048

    def test_max_text_size(self) -> None:
        """MAX_TEXT_SIZE should be 10KB."""
        assert MAX_TEXT_SIZE == 10240

    def test_max_thinking_size(self) -> None:
        """MAX_THINKING_SIZE should be 5KB."""
        assert MAX_THINKING_SIZE == 5120

    def test_max_transcript_size(self) -> None:
        """MAX_TRANSCRIPT_SIZE should be 1MB."""
        assert MAX_TRANSCRIPT_SIZE == 1024 * 1024

    def test_max_messages(self) -> None:
        """MAX_MESSAGES should be 500."""
        assert MAX_MESSAGES == 500

    def test_transcript_truncation_on_size(self, tmp_path: Path) -> None:
        """Should truncate transcript when exceeding MAX_TRANSCRIPT_SIZE."""
        session_file = tmp_path / "large-session.jsonl"
        # Each message content gets truncated to MAX_TEXT_SIZE (10KB) in render_message,
        # plus overhead for headers/separators. Need 100+ messages to exceed 1MB.
        large_content = "x" * 50000  # Source is 50KB but truncated to 10KB
        messages = [
            {"type": "user", "message": {"role": "user", "content": large_content}}
            for _ in range(150)  # ~11KB per rendered message * 150 > 1MB
        ]
        session_file.write_text("\n".join(json.dumps(m) for m in messages))

        result = render_transcript(session_file)

        assert "[transcript truncated due to size]" in result
        assert len(result) <= MAX_TRANSCRIPT_SIZE + 1000  # Allow for truncation message
