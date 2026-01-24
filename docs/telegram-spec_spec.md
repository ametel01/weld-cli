# Spec: Weld Telegram Bot

## Summary

Remote weld CLI interaction via Telegram for single-user operation. Provides project navigation, universal weld command execution, file attachment workflows, and real-time task monitoring through a long-polling bot server.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| User model | Single-user only | Simplifies state management, no concurrency conflicts |
| Interactive prompt detection | Pattern matching | Reliable detection of known weld prompts |
| Binary file detection | Extension allowlist | Predictable behavior, no content inspection needed |
| Serve mode | Foreground blocking | Simpler ops, logs to stdout, Ctrl+C to stop |
| Config vs state | Config is source of truth | State mirrors config on startup, restart to apply changes |
| Pagination state | 5-minute TTL | Balances memory with usability |
| Arg injection (reply-to-doc) | First positional arg | Simple rule, works for plan/implement/interview |
| Prompt timeout | Cancel run after 5 minutes | Prevents zombie processes |
| Arrow-key menus | Convert to numbered list + buttons | Makes implement usable via Telegram |
| Run retention | Keep last 100 runs | Auto-prune oldest, bounded growth |
| Hot reload | Not supported | Restart required for config changes |
| Gist auth failure | Fail with helpful message | Clear path to resolution |
| Timestamps | UTC always | No timezone ambiguity |
| Output file delivery | Offer via button | Convenient without being intrusive |
| Inline file limit | 4KB | Large files should be uploaded as documents |
| Crash recovery | Mark orphaned runs as failed | Clean state on restart |
| Search gitignore | Always respect | Skip noise like node_modules, .venv |

## Requirements

### Must Have
- [ ] Config file at `~/.config/weld/telegram.toml` with 0600 permissions
- [ ] SQLite state at `~/.weld/telegram/state.db` (async via aiosqlite)
- [ ] Allowlist-only authentication (user IDs or usernames)
- [ ] Silent rejection for unauthorized users (log only)
- [ ] Per-chat FIFO queue with 100-item limit
- [ ] Path traversal protection (resolve symlinks, validate project boundary)
- [ ] Command argument sanitization (block shell metacharacters)
- [ ] Subprocess execution without `shell=True`
- [ ] 600-second default command timeout
- [ ] Graceful shutdown: SIGTERM → 5s wait → SIGKILL
- [ ] 2-second minimum between message edits
- [ ] 4096-byte message chunking

### Must Not
- [ ] Never use `shell=True` in subprocess calls
- [ ] Never respond to unauthorized users
- [ ] Never allow path traversal outside registered projects
- [ ] Never hot-reload config (require restart)
- [ ] Never keep pagination state beyond 5 minutes

## Behavior

### Bot Startup (`weld telegram serve`)
- Input: None (uses config from `~/.config/weld/telegram.toml`)
- Output: Blocking foreground process, logs to stdout
- Startup sequence:
  1. Load and validate config
  2. Sync projects from config to state.db
  3. Mark any orphaned "running" runs as "failed"
  4. Prune runs table to last 100 entries
  5. Start aiogram long-polling loop
- Errors:
  - Missing config: Exit with "Run 'weld telegram init' first"
  - Invalid token: Exit with "Invalid bot token"
  - Database error: Exit with details

### Interactive Prompt Handling
- Input: Output buffer from running command
- Detection patterns (case-insensitive):
  - `Select [N/N/N]:` or `[1] Option [2] Option`
  - `(y/n)`, `[Y/n]`, `[y/N]`, `yes/no`
  - `Continue?`, `Proceed?`, `Apply?`
  - Lines starting with `>` followed by numbered items (arrow menus)
- Output: Inline keyboard with extracted options
- Behavior:
  1. Parse options from output
  2. Send inline keyboard to user
  3. Start 5-minute timeout
  4. On button click: write selection to process stdin
  5. On timeout: send SIGTERM, mark run cancelled

### Arrow-Key Menu Conversion
- Input: simple-term-menu style output
- Pattern: Lines like `> [x] Step 1: Do thing` or `  [ ] Step 2: Other`
- Output: Numbered inline keyboard buttons
- Behavior:
  1. Extract menu items from output
  2. Create inline keyboard with item labels
  3. On selection: write index to stdin

### File Viewing (`/cat`, `/head`)
- Allowed extensions: `.py`, `.md`, `.txt`, `.toml`, `.yaml`, `.yml`, `.json`, `.js`, `.ts`, `.tsx`, `.jsx`, `.html`, `.css`, `.sh`, `.bash`, `.zsh`, `.sql`, `.xml`, `.ini`, `.cfg`, `.conf`, `.env.example`, `.gitignore`, `.dockerignore`, `Makefile`, `Dockerfile`, `.rs`, `.go`, `.java`, `.c`, `.cpp`, `.h`, `.hpp`
- Unknown extensions: "Unsupported file type. Use /fetch to download."
- Files > 4000 chars: Split into pages, show "Next page" button
- Pagination state: Stored in memory with 5-minute TTL, keyed by (user_id, file_path)

### Reply-to-Document Injection
- Input: User sends document, then replies with `/weld <command>`
- Behavior:
  1. Download document to `.weld/telegram/uploads/<filename>`
  2. Inject path as first positional argument after command
  3. Example: `/weld plan` → `weld plan .weld/telegram/uploads/spec.md`

### Output File Detection
- After command completes successfully, scan output for file creation patterns:
  - `saved to <path>`
  - `created <path>`
  - `wrote <path>`
  - `output: <path>`
- If pattern found and file exists, add "Download" inline button

### Search Commands (`/find`, `/grep`)
- Always respect `.gitignore` patterns
- Use `pathspec` library for gitignore matching
- Results limited to 50 matches
- Show relative paths from project root

### Gist Upload Fallback
- Trigger: `/fetch` for file > 50MB (text only)
- Requires: `gh` CLI authenticated
- On auth failure: "Large file requires GitHub CLI. Run 'gh auth login' and retry."

### Edge Cases

| Case | Behavior |
|------|----------|
| Empty project list | `/use` shows "No projects registered. Run 'weld telegram projects add' first." |
| No project selected | Commands requiring project show "No project selected. Use /use <project> first." |
| File doesn't exist | `/cat`, `/head` return "File not found: <path>" |
| Path escapes project | "Access denied: path outside project boundary" |
| Queue full (100 items) | "Queue full. Use /cancel to clear pending items." |
| Command timeout (600s) | Mark failed, notify user: "Command timed out after 10 minutes" |
| Telegram rate limit | Exponential backoff: 1s, 2s, 4s (max 3 retries) |
| Message deleted mid-edit | Send new message, continue streaming |
| Orphaned run on restart | Mark as "failed" with error "Bot restarted during execution" |
| Upload filename conflict | Add numeric suffix: `spec.1.md`, `spec.2.md` |
| /file content > 4KB | "Content too large. Upload as document instead." |
| gh not authenticated | Fail with "Run 'gh auth login' to enable large file uploads" |

## Technical Notes

### State Database Schema

```sql
CREATE TABLE contexts (
    user_id INTEGER PRIMARY KEY,
    current_project TEXT,
    last_message_id INTEGER,
    updated_at TEXT
);

CREATE TABLE projects (
    name TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    description TEXT,
    last_accessed_at TEXT,
    created_at TEXT
);

CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    project_name TEXT NOT NULL,
    command TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TEXT,
    completed_at TEXT,
    result TEXT,
    error TEXT,
    FOREIGN KEY (project_name) REFERENCES projects(name)
);

CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_user_id ON runs(user_id);
```

### Pagination State (In-Memory)

```python
# Key: (user_id, file_path)
# Value: {"content": str, "offset": int, "expires_at": datetime}
pagination_cache: dict[tuple[int, str], PaginationState] = {}
```

### Prompt Detection Regex Patterns

```python
PROMPT_PATTERNS = [
    r"Select \[[\d/]+\]:",           # Select [1/2/3]:
    r"\[\d+\]\s+\w+",                # [1] Option
    r"\([yYnN]/[yYnN]\)",            # (y/n), (Y/n)
    r"\b(yes|no)\b.*\?",             # "Continue? (yes/no)"
    r"^\s*>\s*\[.\]",                # Arrow menu: > [x] Item
    r"(Continue|Proceed|Apply)\?",   # Common confirmations
]
```

### Extension Allowlist

```python
TEXT_EXTENSIONS = {
    ".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json",
    ".js", ".ts", ".tsx", ".jsx", ".html", ".css",
    ".sh", ".bash", ".zsh", ".sql", ".xml", ".ini", ".cfg", ".conf",
    ".rs", ".go", ".java", ".c", ".cpp", ".h", ".hpp",
    ".gitignore", ".dockerignore", ".env.example",
}
TEXT_FILENAMES = {"Makefile", "Dockerfile", "LICENSE", "README"}
```

### Message Rate Limiting

```python
class MessageEditor:
    MIN_EDIT_INTERVAL = 2.0  # seconds
    last_edit: float = 0

    async def edit(self, text: str) -> None:
        elapsed = time.time() - self.last_edit
        if elapsed < self.MIN_EDIT_INTERVAL:
            await asyncio.sleep(self.MIN_EDIT_INTERVAL - elapsed)
        # ... perform edit
        self.last_edit = time.time()
```

## Open Questions

None - all blocking questions resolved.

## Out of Scope

- Multi-user concurrent access to same projects
- Hot-reload of configuration
- Webhook mode (long-polling only)
- Daemonization / background service mode
- Binary file content display
- File editing via Telegram (read-only navigation)
- Git operations (use weld commit instead)
