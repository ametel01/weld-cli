Implementation plan for the Telegram bot features described in `docs/telegram-spec.md`,
grounded in the current implementation under `src/weld/telegram/`.

`★ Insight ─────────────────────────────────────`
The telegram module follows a clean layered architecture:
- **cli.py** handles CLI commands and bot lifecycle (700+ lines)
- **bot.py** contains aiogram handlers with a shared `_enqueue_weld_command()` pattern
- **state.py** uses SQLite via aiosqlite with Pydantic models for type safety
- **runner.py** has a single-pattern prompt detection (`Select [N/N/N]:`) that needs extension
`─────────────────────────────────────────────────`

## Phase 1: Startup Housekeeping

Add crash recovery and state management to bot startup sequence.

### Phase Validation
```bash
.venv/bin/pytest tests/telegram/test_state.py -v -k "startup or housekeeping or prune" --tb=short
```

### Step 1: Add orphaned runs cleanup method to StateStore **COMPLETE**

#### Goal
Create `mark_orphaned_runs_failed()` method in StateStore to mark any "running" runs as "failed" on startup with error message "Bot restarted during execution".

#### Files
- `src/weld/telegram/state.py` - Add async method to mark orphaned runs

#### Validation
```bash
grep -q "mark_orphaned_runs_failed" src/weld/telegram/state.py && echo "OK"
```

#### Failure modes
- SQL query syntax error
- Missing commit after update
- Race condition if called while runs are active

---

### Step 2: Add runs table pruning method to StateStore **COMPLETE**

#### Goal
Create `prune_old_runs()` method in StateStore to keep only the last 100 runs per user, deleting oldest entries.

#### Files
- `src/weld/telegram/state.py` - Add async method to prune runs table

#### Validation
```bash
grep -q "prune_old_runs" src/weld/telegram/state.py && echo "OK"
```

#### Failure modes
- Deleting wrong runs due to ORDER BY error
- Not counting per-user correctly
- Foreign key constraint violations

---

### Step 3: Add project sync method to StateStore

#### Goal
Create `sync_projects_from_config()` method to sync projects from TelegramConfig to the projects table on startup.

#### Files
- `src/weld/telegram/state.py` - Add async method to sync projects

#### Validation
```bash
grep -q "sync_projects_from_config" src/weld/telegram/state.py && echo "OK"
```

#### Failure modes
- Deleting projects with active runs
- Path resolution errors
- Conflict between config and state timestamps

---

### Step 4: Call housekeeping methods in serve command startup

#### Goal
Integrate the three housekeeping methods into `_run_bot()` startup sequence: sync projects, mark orphaned runs, prune runs.

#### Files
- `src/weld/telegram/cli.py` - Add housekeeping calls after state_store.init()

#### Validation
```bash
grep -A 10 "await state_store.init()" src/weld/telegram/cli.py | grep -q "mark_orphaned" && echo "OK"
```

#### Failure modes
- Housekeeping errors preventing bot startup
- Wrong execution order
- Missing config parameter for sync

---

### Step 5: Add unit tests for startup housekeeping

#### Goal
Create tests for mark_orphaned_runs_failed(), prune_old_runs(), and sync_projects_from_config().

#### Files
- `tests/telegram/test_state.py` - Add tests for new StateStore methods

#### Validation
```bash
.venv/bin/pytest tests/telegram/test_state.py -v -k "orphaned or prune or sync_projects" --tb=short
```

#### Failure modes
- Test isolation issues with shared database
- Missing async test markers
- Fixtures not properly configured

---

## Phase 2: Extended Prompt Detection

Extend runner.py to detect additional prompt patterns per specification.

### Phase Validation
```bash
.venv/bin/pytest tests/telegram/test_runner.py -v --tb=short
```

### Step 1: Add comprehensive prompt patterns to runner.py

#### Goal
Replace single PROMPT_PATTERN with a list of patterns: Select [N/N/N], (y/n), [Y/n], [y/N], Continue?, Proceed?, Apply?, and arrow menu `> [x] Item`.

#### Files
- `src/weld/telegram/runner.py` - Add PROMPT_PATTERNS list and update detect_prompt()

#### Validation
```bash
grep -q "PROMPT_PATTERNS" src/weld/telegram/runner.py && echo "OK"
```

#### Failure modes
- Regex escaping errors
- False positives from output text
- Breaking existing Select [N] detection

---

### Step 2: Update PromptInfo to include prompt type

#### Goal
Extend PromptInfo dataclass with `prompt_type` field to distinguish between select, yes_no, confirm, and arrow_menu prompts.

#### Files
- `src/weld/telegram/runner.py` - Add prompt_type field to PromptInfo

#### Validation
```bash
grep -q "prompt_type" src/weld/telegram/runner.py && echo "OK"
```

#### Failure modes
- Type annotation errors
- Existing code not handling new field

---

### Step 3: Add arrow menu parsing for implement command

#### Goal
Create `parse_arrow_menu()` function to extract menu items from simple-term-menu style output (`> [x] Step 1`).

#### Files
- `src/weld/telegram/runner.py` - Add parse_arrow_menu() function

#### Validation
```bash
grep -q "parse_arrow_menu" src/weld/telegram/runner.py && echo "OK"
```

#### Failure modes
- Menu items not captured correctly
- Checkbox state ([x] vs [ ]) not preserved
- Unicode characters in menu items

---

### Step 4: Update create_prompt_keyboard for different prompt types

#### Goal
Modify create_prompt_keyboard() in bot.py to render appropriate buttons based on prompt_type: numbered buttons for select, Yes/No for confirm, menu items for arrow menu.

#### Files
- `src/weld/telegram/bot.py` - Update create_prompt_keyboard() to accept prompt_type

#### Validation
```bash
grep -q "prompt_type" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Button labels too long for Telegram
- Wrong button indices sent to stdin
- Callback data format incompatible

---

### Step 5: Add prompt timeout handling with 5-minute limit

#### Goal
Implement dedicated 5-minute timeout for prompt responses per spec, separate from command timeout. Cancel run if prompt not answered.

#### Files
- `src/weld/telegram/runner.py` - Add PROMPT_TIMEOUT constant and timeout handling

#### Validation
```bash
grep -q "PROMPT_TIMEOUT" src/weld/telegram/runner.py && echo "OK"
```

#### Failure modes
- Timeout not cancelling run properly
- Nested timeout conflicts
- User response during timeout cancellation

---

### Step 6: Add tests for extended prompt detection

#### Goal
Create comprehensive tests for all prompt patterns and arrow menu parsing.

#### Files
- `tests/telegram/test_runner.py` - Add tests for new prompt patterns

#### Validation
```bash
.venv/bin/pytest tests/telegram/test_runner.py -v -k "prompt" --tb=short
```

#### Failure modes
- Missing edge cases
- Test patterns not matching real weld output
- Async test timeouts

---

## Phase 3: Universal /weld Command

Implement generic `/weld <command>` for any weld subcommand.

### Phase Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "weld_command" --tb=short
```

### Step 1: Create weld_command handler in bot.py

#### Goal
Add `weld_command()` handler that accepts any weld subcommand and arguments, reusing `_enqueue_weld_command()` pattern.

#### Files
- `src/weld/telegram/bot.py` - Add weld_command() async function

#### Validation
```bash
grep -q "async def weld_command" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Empty subcommand not handled
- Dangerous subcommands not blocked (if any)
- Arguments containing special characters

---

### Step 2: Register /weld handler in cli.py

#### Goal
Add handler registration for /weld command in `_run_bot()` function.

#### Files
- `src/weld/telegram/cli.py` - Add @dp.message(Command("weld")) handler

#### Validation
```bash
grep -q 'Command("weld")' src/weld/telegram/cli.py && echo "OK"
```

#### Failure modes
- Handler ordering conflicts
- CommandObject not passed correctly
- Missing import

---

### Step 3: Update /help to show /weld usage

#### Goal
Add /weld documentation to help_handler showing universal command usage.

#### Files
- `src/weld/telegram/cli.py` - Update help_handler message

#### Validation
```bash
grep -q "/weld" src/weld/telegram/cli.py | head -1 && echo "OK"
```

#### Failure modes
- Help text too long
- Markdown escaping issues
- Missing examples

---

### Step 4: Add tests for /weld command

#### Goal
Create tests for /weld with various subcommands and argument combinations.

#### Files
- `tests/telegram/test_bot.py` - Add tests for weld_command()

#### Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "weld_command" --tb=short
```

#### Failure modes
- Mocking subprocess incorrectly
- Missing edge cases for argument parsing
- Test isolation issues

---

## Phase 4: File Attachment Workflow

Implement document upload handling and reply-to-document injection.

### Phase Validation
```bash
.venv/bin/pytest tests/telegram/test_files.py tests/telegram/test_bot.py -v -k "upload or document" --tb=short
```

### Step 1: Create uploads directory constant and helper

#### Goal
Add UPLOADS_DIR constant for `.weld/telegram/uploads/` and `get_uploads_dir()` helper that creates directory if needed.

#### Files
- `src/weld/telegram/files.py` - Add uploads directory utilities

#### Validation
```bash
grep -q "UPLOADS_DIR" src/weld/telegram/files.py && echo "OK"
```

#### Failure modes
- Path not relative to project root
- Directory creation permissions
- Concurrent creation race condition

---

### Step 2: Add document message handler for file uploads

#### Goal
Create handler for document messages that downloads file to uploads directory with conflict handling (spec.1.md, spec.2.md).

#### Files
- `src/weld/telegram/bot.py` - Add document_handler() for Message with document

#### Validation
```bash
grep -q "async def document_handler" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Large file handling (>50MB)
- Invalid file extensions
- Filename sanitization
- Concurrent uploads with same name

---

### Step 3: Add reply-to-document detection in _enqueue_weld_command

#### Goal
Modify `_enqueue_weld_command()` to detect when message is reply to document and auto-inject uploaded file path as first positional argument.

#### Files
- `src/weld/telegram/bot.py` - Update _enqueue_weld_command() for reply-to-document

#### Validation
```bash
grep -q "reply_to_message" src/weld/telegram/bot.py | grep -q "document" && echo "OK"
```

#### Failure modes
- Not detecting reply correctly
- File not yet uploaded
- Argument position wrong for some commands
- Path injection breaking existing arguments

---

### Step 4: Register document handler in cli.py

#### Goal
Add document message handler registration in `_run_bot()`.

#### Files
- `src/weld/telegram/cli.py` - Add @dp.message() handler with document filter

#### Validation
```bash
grep -q "document_handler" src/weld/telegram/cli.py && echo "OK"
```

#### Failure modes
- Filter not matching document messages
- Handler ordering with other message handlers
- Missing imports

---

### Step 5: Add tests for file attachment workflow

#### Goal
Create tests for document upload, conflict handling, and reply-to-document injection.

#### Files
- `tests/telegram/test_bot.py` - Add tests for document handling

#### Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "document or upload" --tb=short
```

#### Failure modes
- Mocking Telegram file downloads
- Temporary directory cleanup
- Async file operations in tests

---

## Phase 5: Output File Detection

Detect created files in command output and offer download button.

### Phase Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "output_file" --tb=short
```

### Step 1: Add output file pattern detection

#### Goal
Create `detect_output_files()` function in bot.py to scan output for "saved to", "created", "wrote", "output:" patterns and extract file paths.

#### Files
- `src/weld/telegram/bot.py` - Add detect_output_files() function

#### Validation
```bash
grep -q "detect_output_files" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- False positives from log messages
- Relative vs absolute path handling
- Paths with spaces or special characters

---

### Step 2: Add Download button to run completion message

#### Goal
Modify run_consumer() to detect output files on completion and add inline "Download" button linking to /fetch.

#### Files
- `src/weld/telegram/bot.py` - Update run_consumer() completion handling

#### Validation
```bash
grep -q "Download" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- File doesn't exist after command
- Multiple output files
- Button callback data too long
- File outside project boundary

---

### Step 3: Add callback handler for download button

#### Goal
Create callback handler for download buttons that triggers /fetch for the detected file.

#### Files
- `src/weld/telegram/bot.py` - Add handle_download_callback()
- `src/weld/telegram/cli.py` - Register callback handler

#### Validation
```bash
grep -q "handle_download_callback" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- File deleted between detection and download
- Path validation failure
- Callback data parsing errors

---

### Step 4: Add tests for output file detection

#### Goal
Create tests for detect_output_files() and download button flow.

#### Files
- `tests/telegram/test_bot.py` - Add tests for output file detection

#### Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "output_file or download" --tb=short
```

#### Failure modes
- Test output patterns not matching real weld output
- Mocking file existence checks
- Callback flow testing complexity

---

## Phase 6: Integrate FilePathError into TelegramError Hierarchy

Align error hierarchy per specification.

### Phase Validation
```bash
.venv/bin/pytest tests/telegram/test_errors.py -v --tb=short
```

### Step 1: Move FilePathError under TelegramError

#### Goal
Make FilePathError inherit from TelegramError instead of Exception to unify error handling.

#### Files
- `src/weld/telegram/files.py` - Update FilePathError base class
- `src/weld/telegram/errors.py` - Import and re-export FilePathError
- `tests/telegram/test_errors.py` - Add hierarchy tests for TelegramError/FilePathError

#### Validation
```bash
python -c "from weld.telegram.errors import FilePathError; from weld.telegram.errors import TelegramError; assert issubclass(FilePathError, TelegramError)" && echo "OK"
```

#### Failure modes
- Circular import between files.py and errors.py
- Exception handler changes needed
- Import path changes for consumers

---

### Step 2: Update exception handlers to use unified hierarchy

#### Goal
Update exception handlers in bot.py to catch TelegramError for unified error handling.

#### Files
- `src/weld/telegram/bot.py` - Update exception handling

#### Validation
```bash
grep -q "except TelegramError" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Over-catching exceptions
- Lost error context
- Different error message formatting

---

### Step 3: Remove dead TelegramFileError class

#### Goal
Remove unused TelegramFileError from errors.py since FilePathError hierarchy handles file errors.

#### Files
- `src/weld/telegram/errors.py` - Remove TelegramFileError class

#### Validation
```bash
! grep -q "class TelegramFileError" src/weld/telegram/errors.py && echo "OK"
```

#### Failure modes
- External code importing TelegramFileError
- Documentation references

---

## Phase 7: Task Monitoring Commands

Implement /runs, /logs, /tail, and /status <run_id> commands.

### Phase Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "runs or logs or tail" --tb=short
```

### Step 1: Add runs_command for /runs

#### Goal
Create `runs_command()` handler to list recent runs with optional filters (--failed, --today, count).

#### Files
- `src/weld/telegram/bot.py` - Add runs_command() function

#### Validation
```bash
grep -q "async def runs_command" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Date parsing for --today filter
- Pagination for large history
- Output formatting for Telegram

---

### Step 2: Extend status_command to accept run_id

#### Goal
Modify status_command() to show detailed info when run_id argument provided: progress, duration, files modified.

#### Files
- `src/weld/telegram/bot.py` - Update status_command() for optional run_id

#### Validation
```bash
grep -A 20 "async def status_command" src/weld/telegram/bot.py | grep -q "run_id" && echo "OK"
```

#### Failure modes
- Invalid run_id handling
- Run not found message
- Progress extraction from output

---

### Step 3: Add logs_command for /logs <run_id>

#### Goal
Create `logs_command()` to display full output log of a completed run, with pagination for large outputs.

#### Files
- `src/weld/telegram/bot.py` - Add logs_command() function

#### Validation
```bash
grep -q "async def logs_command" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Run not found
- Output too large for Telegram
- Pagination state management

---

### Step 4: Add tail_command for /tail <run_id>

#### Goal
Create `tail_command()` to stream live output of a running command, updating message every 2 seconds until completion or `/tail stop`.

#### Files
- `src/weld/telegram/bot.py` - Add tail_command() and tail_state management

#### Validation
```bash
grep -q "async def tail_command" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Multiple concurrent tails
- Run completes during tail
- Memory leak from orphaned tail tasks
- Stop command not working

---

### Step 5: Register monitoring command handlers in cli.py

#### Goal
Add handler registrations for /runs, /logs, /tail in `_run_bot()`.

#### Files
- `src/weld/telegram/cli.py` - Add command handler registrations

#### Validation
```bash
grep -q 'Command("runs")' src/weld/telegram/cli.py && echo "OK"
```

#### Failure modes
- CommandObject not passed for argument commands
- Handler ordering issues
- Missing imports

---

### Step 6: Add tests for monitoring commands

#### Goal
Create tests for runs_command, logs_command, tail_command, and status with run_id.

#### Files
- `tests/telegram/test_bot.py` - Add monitoring command tests

#### Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "runs or logs or tail" --tb=short
```

#### Failure modes
- Async task cleanup in tests
- Mocking streaming output
- Test timing issues

---

## Phase 8: Project Navigation Commands

Implement /ls, /tree, /cat, /head commands per specification.

### Phase Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "ls or tree or cat or head" --tb=short
```

### Step 1: Add text extension allowlist constant

#### Goal
Add TEXT_EXTENSIONS and TEXT_FILENAMES constants for file viewing validation per spec.

#### Files
- `src/weld/telegram/files.py` - Add extension constants

#### Validation
```bash
grep -q "TEXT_EXTENSIONS" src/weld/telegram/files.py && echo "OK"
```

#### Failure modes
- Missing common extensions
- Case sensitivity issues

---

### Step 2: Add ls_command for /ls [path]

#### Goal
Create `ls_command()` to list directory contents with type indicator, size, modified date, name.

#### Files
- `src/weld/telegram/bot.py` - Add ls_command() function

#### Validation
```bash
grep -q "async def ls_command" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Path validation for directories
- Hidden files handling (--all flag)
- Output formatting for long filenames
- Permissions errors

---

### Step 3: Add tree_command for /tree [path] [depth]

#### Goal
Create `tree_command()` to show directory tree respecting .gitignore, with configurable depth.

#### Files
- `src/weld/telegram/bot.py` - Add tree_command() function

#### Validation
```bash
grep -q "async def tree_command" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- .gitignore parsing complexity
- Large directory trees
- Depth parameter validation
- Unicode characters in paths

---

### Step 4: Add pagination state management

#### Goal
Create PaginationState class and cache dict with 5-minute TTL for paginated file viewing.

#### Files
- `src/weld/telegram/bot.py` - Add PaginationState and cache management

#### Validation
```bash
grep -q "class PaginationState" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Memory leak if TTL cleanup fails
- Concurrent access to cache
- State serialization for callbacks

---

### Step 5: Add cat_command for /cat <path>

#### Goal
Create `cat_command()` to view file contents with syntax highlighting, pagination for files > 4000 chars.

#### Files
- `src/weld/telegram/bot.py` - Add cat_command() function

#### Validation
```bash
grep -q "async def cat_command" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Binary file detection
- Extension not in allowlist
- Pagination button callbacks
- Code block escaping for markdown

---

### Step 6: Add head_command for /head <path> [lines]

#### Goal
Create `head_command()` to view first N lines of a file (default 20).

#### Files
- `src/weld/telegram/bot.py` - Add head_command() function

#### Validation
```bash
grep -q "async def head_command" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Lines parameter parsing
- File with fewer lines than requested
- Binary file handling

---

### Step 7: Register navigation command handlers

#### Goal
Add handler registrations for /ls, /tree, /cat, /head in `_run_bot()`.

#### Files
- `src/weld/telegram/cli.py` - Add command handler registrations

#### Validation
```bash
grep -q 'Command("ls")' src/weld/telegram/cli.py && echo "OK"
```

#### Failure modes
- Path argument parsing
- Missing CommandObject injection
- Handler conflicts

---

### Step 8: Add tests for navigation commands

#### Goal
Create tests for ls_command, tree_command, cat_command, head_command including pagination.

#### Files
- `tests/telegram/test_bot.py` - Add navigation command tests

#### Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "ls or tree or cat or head" --tb=short
```

#### Failure modes
- Test fixtures for directory structure
- Pagination callback testing
- GitIgnore mocking for tree

---

## Phase 9: Search Commands

Implement /find and /grep commands with gitignore support.

### Phase Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "find or grep" --tb=short
```

### Step 1: Add pathspec dependency for gitignore matching

#### Goal
Verify pathspec is available or add to dependencies for .gitignore pattern matching.

#### Files
- `pyproject.toml` - Add pathspec to dependencies if not present

#### Validation
```bash
python -c "import pathspec" && echo "OK"
```

#### Failure modes
- Version conflicts
- Import errors

---

### Step 2: Add gitignore loading utility

#### Goal
Create `load_gitignore()` function in files.py to load and parse .gitignore patterns from project root.

#### Files
- `src/weld/telegram/files.py` - Add load_gitignore() function

#### Validation
```bash
grep -q "load_gitignore" src/weld/telegram/files.py && echo "OK"
```

#### Failure modes
- Missing .gitignore file
- Nested .gitignore files
- Invalid patterns

---

### Step 3: Add find_command for /find <pattern>

#### Goal
Create `find_command()` to find files matching glob pattern, respecting .gitignore, limited to 50 results.

#### Files
- `src/weld/telegram/bot.py` - Add find_command() function

#### Validation
```bash
grep -q "async def find_command" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Glob pattern validation
- Large result sets
- Relative path display
- Performance on large directories

---

### Step 4: Add grep_command for /grep <pattern> [path]

#### Goal
Create `grep_command()` to search file contents with regex, respecting .gitignore, limited to 50 matches.

#### Files
- `src/weld/telegram/bot.py` - Add grep_command() function

#### Validation
```bash
grep -q "async def grep_command" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Invalid regex patterns
- Binary file handling
- Context lines (optional)
- Performance on large codebases

---

### Step 5: Register search command handlers

#### Goal
Add handler registrations for /find and /grep in `_run_bot()`.

#### Files
- `src/weld/telegram/cli.py` - Add command handler registrations

#### Validation
```bash
grep -q 'Command("find")' src/weld/telegram/cli.py && echo "OK"
```

#### Failure modes
- Pattern argument containing special characters
- Path argument parsing

---

### Step 6: Add tests for search commands

#### Goal
Create tests for find_command and grep_command including gitignore filtering.

#### Files
- `tests/telegram/test_bot.py` - Add search command tests

#### Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "find or grep" --tb=short
```

#### Failure modes
- Test directory setup with gitignore
- Regex pattern edge cases
- Result ordering verification

---

## Phase 10: Inline File Creation

Implement /file command for inline file creation.

### Phase Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "file_command" --tb=short
```

### Step 1: Add file_command for /file <path>

#### Goal
Create `file_command()` to create files from inline message content with 4KB limit check.

#### Files
- `src/weld/telegram/bot.py` - Add file_command() function

#### Validation
```bash
grep -q "async def file_command" src/weld/telegram/bot.py && echo "OK"
```

#### Failure modes
- Content > 4KB rejection
- Path validation
- Parent directory creation
- Overwrite warning for existing files

---

### Step 2: Register /file handler

#### Goal
Add handler registration for /file command in `_run_bot()`.

#### Files
- `src/weld/telegram/cli.py` - Add @dp.message(Command("file")) handler

#### Validation
```bash
grep -q 'Command("file")' src/weld/telegram/cli.py && echo "OK"
```

#### Failure modes
- Message text parsing after command
- Newline handling in content

---

### Step 3: Add tests for /file command

#### Goal
Create tests for file_command including size limit and overwrite handling.

#### Files
- `tests/telegram/test_bot.py` - Add file_command tests

#### Validation
```bash
.venv/bin/pytest tests/telegram/test_bot.py -v -k "file_command" --tb=short
```

#### Failure modes
- Test file cleanup
- Content encoding edge cases

---
