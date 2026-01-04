"""Constants for weld CLI.

Centralized timeout and limit values for subprocess operations.
All timeouts are in seconds and are designed to prevent hanging
while allowing sufficient time for legitimate long-running operations.

Timeout Guidelines:
    - AI operations (Codex, Claude): 10 minutes to handle complex analysis
    - Build/test checks: 5 minutes for typical CI operations
    - Git operations: 30 seconds, enough for most repos
    - Quick checks: 10 seconds for simple tool availability tests
"""

# =============================================================================
# Subprocess Timeouts (in seconds)
# =============================================================================

#: Timeout for git commands (rev-parse, diff, commit, etc.)
GIT_TIMEOUT = 30

#: Timeout for Codex CLI invocations (review, plan analysis)
CODEX_TIMEOUT = 600  # 10 minutes

#: Timeout for Claude CLI invocations (implementation, review)
CLAUDE_TIMEOUT = 600  # 10 minutes

#: Timeout for transcript gist generation via claude-code-transcripts
TRANSCRIPT_TIMEOUT = 60

#: Timeout for running configured checks command (tests, linting)
CHECKS_TIMEOUT = 300  # 5 minutes

#: Timeout for tool availability checks during `weld init`
INIT_TOOL_CHECK_TIMEOUT = 10
