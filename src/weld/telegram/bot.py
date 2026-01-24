"""Bot module with aiogram dispatcher and command handlers."""

import asyncio
import contextlib
import fnmatch
import logging
import re
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandObject
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from weld.services.gist_uploader import GistError, upload_gist
from weld.telegram.config import TelegramConfig
from weld.telegram.errors import TelegramError
from weld.telegram.files import (
    get_syntax_language,
    get_uploads_dir,
    is_text_file,
    resolve_upload_filename,
    sanitize_filename,
    validate_fetch_path,
    validate_push_path,
)
from weld.telegram.format import MessageEditor, format_chunk, format_status
from weld.telegram.queue import QueueManager
from weld.telegram.runner import (
    PromptType,
    detect_prompt,
    execute_run,
    parse_arrow_menu,
    send_input,
)
from weld.telegram.state import Run, RunStatus, StateStore, UserContext

# Pending prompt responses: run_id -> asyncio.Future
_pending_prompts: dict[int, asyncio.Future[str]] = {}

# Output buffer registry for active runs: run_id -> accumulated output
# Updated by run_consumer, read by tail_command
_run_output_buffers: dict[int, str] = {}

# Active tail tasks: user_id -> (run_id, asyncio.Task)
# Only one tail per user allowed to prevent resource exhaustion
_active_tails: dict[int, tuple[int, asyncio.Task[None]]] = {}

# Telegram file size limits
TELEGRAM_MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024  # 50MB for bot downloads

# Pagination TTL in seconds (5 minutes)
PAGINATION_TTL_SECONDS = 300

logger = logging.getLogger(__name__)


@dataclass
class PaginationState:
    """State for paginated file viewing.

    Tracks the file path, current page, total pages, and content lines
    for a paginated file view session. Each state has a TTL for automatic
    expiration.
    """

    file_path: Path
    lines: list[str]
    current_page: int
    total_pages: int
    lines_per_page: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_expired(self) -> bool:
        """Check if this pagination state has expired (5-minute TTL)."""
        age = (datetime.now(UTC) - self.created_at).total_seconds()
        return age > PAGINATION_TTL_SECONDS

    def get_page_content(self) -> str:
        """Get content for the current page."""
        start = self.current_page * self.lines_per_page
        end = start + self.lines_per_page
        return "\n".join(self.lines[start:end])


# Pagination state cache: callback_id -> PaginationState
# Uses a lock for thread-safe access during cleanup
_pagination_cache: dict[str, PaginationState] = {}
_pagination_cache_lock = threading.Lock()


def _cleanup_expired_pagination() -> None:
    """Remove expired pagination states from cache.

    Called lazily on cache access to prevent memory leaks.
    Thread-safe via lock.
    """
    with _pagination_cache_lock:
        expired_keys = [key for key, state in _pagination_cache.items() if state.is_expired()]
        for key in expired_keys:
            del _pagination_cache[key]
            logger.debug(f"Expired pagination state removed: {key}")


def get_pagination_state(callback_id: str) -> PaginationState | None:
    """Get pagination state by callback ID, with lazy cleanup.

    Args:
        callback_id: Unique identifier for the pagination session

    Returns:
        PaginationState if found and not expired, None otherwise
    """
    _cleanup_expired_pagination()
    with _pagination_cache_lock:
        state = _pagination_cache.get(callback_id)
        if state and state.is_expired():
            del _pagination_cache[callback_id]
            return None
        return state


def set_pagination_state(callback_id: str, state: PaginationState) -> None:
    """Store pagination state in cache.

    Args:
        callback_id: Unique identifier for the pagination session
        state: PaginationState to store
    """
    _cleanup_expired_pagination()
    with _pagination_cache_lock:
        _pagination_cache[callback_id] = state


def remove_pagination_state(callback_id: str) -> None:
    """Remove pagination state from cache.

    Args:
        callback_id: Unique identifier for the pagination session
    """
    with _pagination_cache_lock:
        _pagination_cache.pop(callback_id, None)


def create_prompt_keyboard(
    run_id: int,
    options: list[str],
    prompt_type: PromptType,
    prompt_text: str = "",
) -> InlineKeyboardMarkup:
    """Create inline keyboard for prompt options based on prompt type.

    Args:
        run_id: The run ID to associate with button callbacks
        options: List of option values (e.g., ["1", "2", "3"] or ["y", "n"])
        prompt_type: Type of prompt (select, yes_no, confirm, arrow_menu)
        prompt_text: Full prompt text (used for arrow_menu to extract items)

    Returns:
        InlineKeyboardMarkup with buttons appropriate for the prompt type
    """
    buttons: list[list[InlineKeyboardButton]] = []

    if prompt_type == "arrow_menu":
        # Parse menu items and create buttons for each
        menu_items = parse_arrow_menu(prompt_text)
        if menu_items:
            for i, item in enumerate(menu_items):
                # Truncate long labels to fit Telegram's limits (64 bytes for callback_data)
                label = item.text[:40] + "..." if len(item.text) > 40 else item.text
                # Prefix with checkbox state
                prefix = "☑ " if item.checked else "☐ "
                # Add selection indicator
                if item.selected:
                    prefix = "▶ " + prefix
                # Use 1-indexed position to match menu selection
                callback_data = f"prompt:{run_id}:{i + 1}"
                buttons.append(
                    [InlineKeyboardButton(text=f"{prefix}{label}", callback_data=callback_data)]
                )
            # Add quit option
            buttons.append(
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"prompt:{run_id}:q")]
            )
        else:
            # Fallback if no items parsed: show navigation buttons
            nav_buttons = [
                InlineKeyboardButton(text="⬆️ Up", callback_data=f"prompt:{run_id}:up"),
                InlineKeyboardButton(text="⬇️ Down", callback_data=f"prompt:{run_id}:down"),
            ]
            action_buttons = [
                InlineKeyboardButton(text="✅ Select", callback_data=f"prompt:{run_id}:enter"),
                InlineKeyboardButton(text="❌ Quit", callback_data=f"prompt:{run_id}:q"),
            ]
            buttons = [nav_buttons, action_buttons]

    elif prompt_type in ("yes_no", "confirm"):
        # Yes/No buttons on same row
        yes_btn = InlineKeyboardButton(text="✅ Yes", callback_data=f"prompt:{run_id}:y")
        no_btn = InlineKeyboardButton(text="❌ No", callback_data=f"prompt:{run_id}:n")
        buttons = [[yes_btn, no_btn]]

    else:  # "select" or fallback
        # Numbered options (weld implement menu, commit grouping, etc.)
        row: list[InlineKeyboardButton] = []
        for opt in options:
            # Keep labels short for numbered options
            callback_data = f"prompt:{run_id}:{opt}"
            row.append(InlineKeyboardButton(text=opt, callback_data=callback_data))
        buttons = [row]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_download_keyboard(file_path: str, cwd: Path) -> InlineKeyboardMarkup | None:
    """Create inline keyboard with Download button for an output file.

    Args:
        file_path: Absolute or relative path to the file
        cwd: Working directory for resolving relative paths

    Returns:
        InlineKeyboardMarkup with Download button, or None if path is too long
        for callback data (64-byte limit)
    """
    # Convert to Path and make relative to cwd for shorter callback data
    path = Path(file_path)
    if path.is_absolute():
        with contextlib.suppress(ValueError):
            path = path.relative_to(cwd)

    # Callback data format: fetch:<relative_path>
    # Telegram limit is 64 bytes for callback_data
    path_str = str(path)
    callback_data = f"fetch:{path_str}"

    if len(callback_data.encode("utf-8")) > 64:
        # Path too long for callback data
        logger.warning(f"File path too long for download button: {path_str}")
        return None

    button = InlineKeyboardButton(text="📥 Download", callback_data=callback_data)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


async def handle_fetch_callback(
    callback: CallbackQuery, config: TelegramConfig, bot: Bot, state_store: StateStore
) -> None:
    """Handle callback from Download inline keyboard button.

    Downloads the file and sends it to the user.

    Args:
        callback: The callback query from button press
        config: TelegramConfig with registered projects
        bot: Bot instance for sending files
        state_store: StateStore for looking up user context
    """
    if not callback.data or not callback.data.startswith("fetch:"):
        return

    # Extract file path from callback data
    file_path = callback.data[6:]  # Remove "fetch:" prefix
    if not file_path:
        await callback.answer("Invalid file path", show_alert=True)
        return

    user_id = callback.from_user.id if callback.from_user else None
    if user_id is None:
        await callback.answer("Unable to identify user", show_alert=True)
        return

    # Get user's current project context
    context = await state_store.get_context(user_id)
    if not context or not context.current_project:
        await callback.answer("No project selected", show_alert=True)
        return

    project = config.get_project(context.current_project)
    if project is None:
        await callback.answer("Project not found", show_alert=True)
        return

    # Resolve the file path relative to project
    resolved_path = project.path / file_path
    try:
        resolved_path = resolved_path.resolve()
    except OSError:
        await callback.answer("Invalid path", show_alert=True)
        return

    # Security: ensure file is within project boundary
    try:
        resolved_path.relative_to(project.path.resolve())
    except ValueError:
        logger.warning(f"User {user_id} attempted to fetch file outside project: {resolved_path}")
        await callback.answer("Access denied: file outside project", show_alert=True)
        return

    # Check file exists
    if not resolved_path.is_file():
        await callback.answer("File not found", show_alert=True)
        return

    # Get file size
    try:
        file_size = resolved_path.stat().st_size
    except OSError:
        await callback.answer("Cannot read file", show_alert=True)
        return

    # Check size limit
    if file_size > TELEGRAM_MAX_DOWNLOAD_SIZE:
        await callback.answer("File too large (>50MB)", show_alert=True)
        return

    # Send file
    try:
        document = FSInputFile(resolved_path, filename=resolved_path.name)
        await bot.send_document(
            chat_id=callback.message.chat.id if callback.message else user_id,
            document=document,
            caption=f"`{_escape_markdown(str(resolved_path.name))}`",
        )
        await callback.answer("File sent!")
        logger.info(f"User {user_id} downloaded file via button: {resolved_path}")
    except Exception as e:
        logger.exception(f"Failed to send file {resolved_path}")
        await callback.answer(f"Failed to send file: {e!s}", show_alert=True)


async def handle_prompt_callback(callback: CallbackQuery) -> None:
    """Handle callback from prompt inline keyboard button.

    Args:
        callback: The callback query from button press
    """
    if not callback.data or not callback.data.startswith("prompt:"):
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        logger.warning(f"Invalid prompt callback data: {callback.data}")
        return

    _, run_id_str, option = parts
    try:
        run_id = int(run_id_str)
    except ValueError:
        logger.warning(f"Invalid run_id in callback: {run_id_str}")
        return

    logger.info(f"Prompt callback: run_id={run_id}, option={option}")

    # Send the response to the running process
    if await send_input(run_id, option):
        # Acknowledge the callback
        await callback.answer(f"Selected option {option}")

        # Update the message to show selection was received and command is continuing
        if isinstance(callback.message, Message):
            with contextlib.suppress(Exception):
                await callback.message.edit_text(
                    f"*Run #{run_id}*\n\n✓ Selected option {option}\n\n_Command continuing..._",
                    parse_mode="Markdown",
                )
    else:
        await callback.answer("Command no longer running", show_alert=True)


def _escape_markdown(text: str) -> str:
    """Escape Markdown special characters for safe message formatting.

    Args:
        text: Text to escape

    Returns:
        Text with Markdown special characters escaped
    """
    # For basic Markdown mode, escape: * _ ` [
    for char in ("*", "_", "`", "["):
        text = text.replace(char, "\\" + char)
    return text


# Patterns for detecting output file paths in command output
# These patterns match common CLI output formats for file creation/saving
_OUTPUT_FILE_PATTERNS = [
    # "Saved to /path/to/file" or "saved to: /path"
    re.compile(r"(?:saved|saving)\s+to:?\s+['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE),
    # "Created /path/to/file" or "created: /path"
    re.compile(r"created:?\s+['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE),
    # "Wrote /path/to/file" or "wrote to /path" or "written to /path"
    re.compile(r"(?:wrote|written)\s+(?:to\s+)?:?\s*['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE),
    # "Output: /path/to/file" or "output file: /path"
    re.compile(r"output(?:\s+file)?:?\s+['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE),
    # "Generated /path/to/file"
    re.compile(r"generated:?\s+['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE),
    # "Plan saved to /path" (weld-specific)
    re.compile(r"plan\s+saved\s+to:?\s+['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE),
    # "Writing to /path"
    re.compile(r"writing\s+to:?\s+['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE),
]

# Extensions that indicate actual output files (not log paths or URLs)
_OUTPUT_FILE_EXTENSIONS = frozenset(
    {
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".py",
        ".js",
        ".ts",
        ".html",
        ".css",
        ".sh",
        ".log",
        ".csv",
    }
)


def detect_output_files(output: str, cwd: Path | None = None) -> list[Path]:
    """Detect file paths mentioned in command output as created/saved files.

    Scans command output for patterns indicating file creation (e.g., "saved to",
    "created", "wrote", "output:") and extracts the file paths. Validates that
    paths have recognized extensions and optionally checks existence.

    Args:
        output: Command output text to scan for file paths
        cwd: Optional working directory for resolving relative paths.
             If provided, relative paths are resolved against it and
             existence is verified. If None, paths are returned as-is.

    Returns:
        List of Path objects for detected output files. Paths are deduplicated
        and returned in order of first occurrence. Only paths with recognized
        extensions are included to reduce false positives.

    Example:
        >>> output = "Plan saved to: spec_PLAN.md\\nProcessing complete."
        >>> detect_output_files(output, Path("/project"))
        [PosixPath('/project/spec_PLAN.md')]

    Note:
        - Paths in quotes (single or double) are handled correctly
        - URLs (http://, https://) are filtered out
        - Paths without file extensions are filtered out
        - When cwd is provided, non-existent files are filtered out
    """
    detected: list[Path] = []
    seen: set[str] = set()

    for pattern in _OUTPUT_FILE_PATTERNS:
        for match in pattern.finditer(output):
            path_str = match.group(1).strip()

            # Skip empty matches
            if not path_str:
                continue

            # Skip URLs
            if path_str.startswith(("http://", "https://", "ftp://")):
                continue

            # Skip if already seen
            if path_str in seen:
                continue
            seen.add(path_str)

            # Check for valid file extension
            path = Path(path_str)
            suffix = path.suffix.lower()
            if suffix not in _OUTPUT_FILE_EXTENSIONS:
                continue

            # Resolve relative paths if cwd provided
            if cwd is not None:
                if not path.is_absolute():
                    path = cwd / path
                # Resolve symlinks and normalize
                try:
                    path = path.resolve()
                except OSError:
                    continue
                # Verify file exists
                if not path.is_file():
                    continue

            detected.append(path)

    return detected


def create_bot(token: str) -> tuple[Bot, Dispatcher]:
    """Create and configure an aiogram Bot and Dispatcher.

    Creates a Bot instance with MarkdownV2 parse mode as default and
    a Dispatcher ready for registering handlers.

    Args:
        token: Telegram Bot API token from @BotFather.

    Returns:
        Tuple of (Bot, Dispatcher) ready for handler registration and polling.

    Raises:
        ValueError: If token is empty or invalid format.

    Example:
        bot, dp = create_bot("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")

        @dp.message(Command("start"))
        async def start_handler(message: Message):
            await message.answer("Hello!")

        await dp.start_polling(bot)
    """
    if not token or not token.strip():
        raise ValueError("Bot token cannot be empty")

    # Basic token format validation (number:alphanumeric)
    token = token.strip()
    if ":" not in token:
        raise ValueError("Invalid bot token format: missing colon separator")

    parts = token.split(":", 1)
    if not parts[0].isdigit():
        raise ValueError("Invalid bot token format: bot ID must be numeric")
    if not parts[1]:
        raise ValueError("Invalid bot token format: missing token hash")

    logger.debug("Creating bot instance")

    # Create bot with default properties
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )

    # Create dispatcher
    dp = Dispatcher()

    logger.info("Bot and dispatcher created successfully")

    return bot, dp


async def use_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    config: TelegramConfig,
) -> None:
    """Handle /use <project> command to switch project context.

    Validates the project exists in config, checks for race conditions
    (run in progress for this user), and updates the context table.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        config: TelegramConfig with registered projects

    Usage:
        /use myproject - Switch to project "myproject"
        /use          - Show current project and available projects
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    project_name = command.args.strip() if command.args else None

    # If no project specified, show current context and available projects
    if not project_name:
        context = await state_store.get_context(user_id)
        current = context.current_project if context else None

        project_names = config.list_project_names()
        if not project_names:
            await message.answer(
                "No projects configured.\nAdd projects to ~/.config/weld/telegram.toml"
            )
            return

        projects_list = "\n".join(f"  • {_escape_markdown(name)}" for name in project_names)
        if current:
            await message.answer(
                f"Current project: *{_escape_markdown(current)}*\n\n"
                f"Available projects:\n{projects_list}\n\n"
                "Usage: `/use <project>`"
            )
        else:
            await message.answer(
                "No project selected.\n\n"
                f"Available projects:\n{projects_list}\n\n"
                "Usage: `/use <project>`"
            )
        return

    # Validate project exists in config
    project = config.get_project(project_name)
    if project is None:
        escaped_name = _escape_markdown(project_name)
        project_names = config.list_project_names()
        if project_names:
            projects_list = "\n".join(f"  • {_escape_markdown(name)}" for name in project_names)
            await message.answer(
                f"Unknown project: `{escaped_name}`\n\nAvailable projects:\n{projects_list}"
            )
        else:
            await message.answer(f"Unknown project: `{escaped_name}`\n\nNo projects configured.")
        return

    # Check for race condition: don't allow context switch while run in progress
    context = await state_store.get_context(user_id)
    if context and context.conversation_state == "running":
        await message.answer(
            "Cannot switch projects while a command is running.\n"
            "Wait for the current command to complete or cancel it first."
        )
        return

    # Update context with new project
    new_context = UserContext(
        user_id=user_id,
        current_project=project_name,
        conversation_state=context.conversation_state if context else "idle",
        last_message_id=message.message_id,
        updated_at=datetime.now(UTC),
    )
    await state_store.upsert_context(new_context)

    # Also touch the project to track last access
    await state_store.touch_project(project_name)

    logger.info(f"User {user_id} switched to project '{project_name}'")
    await message.answer(f"Switched to project: *{_escape_markdown(project_name)}*")


async def runs_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
) -> None:
    """Handle /runs command to list recent command run history.

    Displays runs with optional filters for status and date range.
    Supports count parameter to control how many runs to show.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations

    Usage:
        /runs              - Show last 10 runs
        /runs 20           - Show last 20 runs
        /runs --failed     - Show only failed runs
        /runs --today      - Show runs from today only
        /runs --today 5    - Show last 5 runs from today
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Parse arguments
    args = command.args.strip() if command.args else ""
    parts = args.split()

    # Default values
    limit = 10
    filter_failed = False
    filter_today = False

    # Parse flags and count
    for part in parts:
        if part == "--failed":
            filter_failed = True
        elif part == "--today":
            filter_today = True
        elif part.isdigit():
            limit = min(int(part), 50)  # Cap at 50 to avoid huge messages

    # Determine status filter
    status_filter: RunStatus | None = "failed" if filter_failed else None

    # Fetch runs - we'll fetch more than limit to allow for date filtering
    fetch_limit = limit * 3 if filter_today else limit
    runs = await state_store.list_runs_by_user(user_id, limit=fetch_limit, status=status_filter)

    # Apply date filter if --today
    if filter_today:
        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        runs = [r for r in runs if r.started_at >= today_start]
        runs = runs[:limit]  # Apply limit after filtering

    if not runs:
        filter_desc = []
        if filter_failed:
            filter_desc.append("failed")
        if filter_today:
            filter_desc.append("today")
        filter_text = f" ({', '.join(filter_desc)})" if filter_desc else ""
        await message.answer(f"No runs found{filter_text}.")
        return

    # Build output
    lines: list[str] = []

    # Header with filter info
    header_parts = ["*Recent runs*"]
    if filter_failed:
        header_parts.append("(failed only)")
    if filter_today:
        header_parts.append("(today)")
    lines.append(" ".join(header_parts))
    lines.append("")

    # Format each run
    for run in runs:
        # Status emoji
        status_emoji = {
            "completed": "✓",
            "failed": "✗",
            "cancelled": "⊘",
            "running": "⟳",
            "pending": "○",
        }.get(run.status, "?")

        # Truncate command for display
        cmd_display = run.command[:35] + "..." if len(run.command) > 35 else run.command
        cmd_escaped = _escape_markdown(cmd_display)

        # Format timestamp
        time_str = run.started_at.strftime("%m/%d %H:%M")

        # Build run line
        run_line = f"{status_emoji} `{cmd_escaped}`"

        # Add project if different commands might be from different projects
        project_escaped = _escape_markdown(run.project_name)
        run_line += f" _{project_escaped}_"

        run_line += f" {time_str}"

        # Add error snippet for failed runs
        if run.status == "failed" and run.error:
            error_snippet = run.error[:30] + "..." if len(run.error) > 30 else run.error
            run_line += f"\n  └ `{_escape_markdown(error_snippet)}`"

        lines.append(run_line)

    # Add summary footer
    lines.append("")
    shown = len(runs)
    lines.append(f"_Showing {shown} run(s)_")

    # Join and chunk if needed
    output = "\n".join(lines)

    # Telegram message limit is 4096 chars; chunk if needed
    if len(output) > 4000:
        # Truncate to fit, keeping header and footer
        lines_to_show = lines[:2]  # Header
        char_count = len("\n".join(lines_to_show))
        for line in lines[2:-2]:  # Skip header and footer
            if char_count + len(line) + 50 > 4000:  # Leave room for footer
                lines_to_show.append("...")
                break
            lines_to_show.append(line)
            char_count += len(line) + 1
        lines_to_show.extend(lines[-2:])  # Footer
        output = "\n".join(lines_to_show)

    await message.answer(output)


def _format_duration(started_at: datetime, completed_at: datetime | None) -> str:
    """Format a duration between two timestamps.

    Args:
        started_at: Start time
        completed_at: End time (or None for ongoing runs)

    Returns:
        Human-readable duration string (e.g., "2m 30s", "1h 5m")
    """
    end_time = completed_at if completed_at else datetime.now(UTC)
    delta = end_time - started_at
    total_seconds = int(delta.total_seconds())

    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}m {seconds}s"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}h {minutes}m"


async def _show_run_details(
    message: Message,
    state_store: StateStore,
    user_id: int,
    run_id: int,
) -> None:
    """Show detailed information about a specific run.

    Displays command, project, status, duration, and any result/error output.

    Args:
        message: Telegram message to reply to
        state_store: StateStore instance
        user_id: Requesting user's ID (for authorization check)
        run_id: ID of the run to display
    """
    run = await state_store.get_run(run_id)

    if run is None:
        await message.answer(f"Run \\#{run_id} not found\\.")
        return

    # Security: only show runs belonging to the requesting user
    if run.user_id != user_id:
        await message.answer(f"Run \\#{run_id} not found\\.")
        return

    # Build detailed output
    lines: list[str] = []
    lines.append(f"*Run \\#{run_id}*")
    lines.append("")

    # Status with emoji
    status_emoji = {
        "pending": "⏳",
        "running": "▶️",
        "completed": "✅",
        "failed": "❌",
        "cancelled": "⊘",
    }.get(run.status, "❓")
    lines.append(f"*Status:* {status_emoji} {run.status}")

    # Project
    lines.append(f"*Project:* {_escape_markdown(run.project_name)}")

    # Command (full, not truncated)
    cmd_escaped = _escape_markdown(run.command)
    lines.append(f"*Command:* `{cmd_escaped}`")

    # Duration
    duration = _format_duration(run.started_at, run.completed_at)
    if run.status == "running":
        lines.append(f"*Duration:* {duration} \\(ongoing\\)")
    elif run.status == "pending":
        lines.append(f"*Queued:* {duration} ago")
    else:
        lines.append(f"*Duration:* {duration}")

    # Timestamps
    started_str = run.started_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append(f"*Started:* {_escape_markdown(started_str)}")
    if run.completed_at:
        completed_str = run.completed_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"*Completed:* {_escape_markdown(completed_str)}")

    # Result or error (truncated if too long)
    if run.error:
        lines.append("")
        lines.append("*Error:*")
        error_preview = run.error[:500] + "..." if len(run.error) > 500 else run.error
        lines.append(f"```\n{_escape_markdown(error_preview)}\n```")
    elif run.result:
        lines.append("")
        lines.append("*Result:*")
        result_preview = run.result[:500] + "..." if len(run.result) > 500 else run.result
        lines.append(f"```\n{_escape_markdown(result_preview)}\n```")

    await message.answer("\n".join(lines))


# Telegram message size limit for logs pagination
TELEGRAM_MAX_MESSAGE_SIZE = 4000  # Leave room for formatting, headers


async def logs_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
) -> None:
    """Handle /logs <run_id> command to display full output log of a run.

    Shows the complete output of a completed run with pagination for large
    outputs. Supports page navigation via optional page number argument.

    Args:
        message: Incoming Telegram message
        command: Parsed command with run_id and optional page number
        state_store: StateStore instance for database operations

    Usage:
        /logs 123       - Show first page of logs for run #123
        /logs 123 2     - Show page 2 of logs for run #123
        /logs 123 all   - Upload full logs as a file (for very large outputs)

    Failure modes:
        - Run not found: Returns error message
        - No output: Returns message indicating empty output
        - Output too large: Automatically paginates or offers file download
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Parse arguments: /logs <run_id> [page|all]
    args = command.args.strip() if command.args else ""
    parts = args.split()

    if not parts:
        await message.answer(
            "Usage: `/logs <run_id> [page]`\n\n"
            "Display full output log of a completed run.\n"
            "  `/logs 123` \\- Show first page of run #123\n"
            "  `/logs 123 2` \\- Show page 2\n"
            "  `/logs 123 all` \\- Download full log as file"
        )
        return

    # Parse run_id
    run_id_str = parts[0]
    if not run_id_str.isdigit():
        await message.answer(f"Invalid run ID: `{_escape_markdown(run_id_str)}`")
        return
    run_id = int(run_id_str)

    # Parse optional page number or 'all'
    page = 1
    download_all = False
    if len(parts) > 1:
        page_arg = parts[1].lower()
        if page_arg == "all":
            download_all = True
        elif page_arg.isdigit():
            page = max(1, int(page_arg))
        else:
            await message.answer(
                f"Invalid page: `{_escape_markdown(parts[1])}`\n"
                "Use a number or 'all' to download full log."
            )
            return

    # Fetch the run
    run = await state_store.get_run(run_id)

    if run is None:
        await message.answer(f"Run \\#{run_id} not found\\.")
        return

    # Security: only show runs belonging to the requesting user
    if run.user_id != user_id:
        await message.answer(f"Run \\#{run_id} not found\\.")
        return

    # Check if run has output
    output = run.result or ""
    error = run.error or ""

    # Combine output and error for display
    full_log = ""
    if output:
        full_log = output
    if error:
        if full_log:
            full_log += f"\n\n--- ERROR ---\n{error}"
        else:
            full_log = f"--- ERROR ---\n{error}"

    if not full_log:
        status_msg = f"pending ({run.status})" if run.status == "pending" else run.status
        await message.answer(
            f"*Run \\#{run_id}* has no output yet\\.\n\nStatus: {_escape_markdown(status_msg)}"
        )
        return

    # Handle 'all' - send as document
    if download_all:
        await _send_logs_as_file(message, run_id, full_log)
        return

    # Calculate pagination
    total_chars = len(full_log)
    # Reserve space for header and footer in each page
    content_size = TELEGRAM_MAX_MESSAGE_SIZE - 200
    total_pages = (total_chars + content_size - 1) // content_size

    if total_pages == 1:
        # Single page - show everything
        await message.answer(
            f"*Run \\#{run_id} \\- Logs*\n\n"
            f"```\n{_escape_markdown(full_log[: TELEGRAM_MAX_MESSAGE_SIZE - 100])}\n```"
        )
        return

    # Multi-page pagination
    if page > total_pages:
        await message.answer(
            f"Page {page} does not exist\\. Run \\#{run_id} has {total_pages} page\\(s\\)\\."
        )
        return

    # Extract page content
    start_idx = (page - 1) * content_size
    end_idx = min(start_idx + content_size, total_chars)
    page_content = full_log[start_idx:end_idx]

    # Build navigation hints
    nav_hints: list[str] = []
    if page > 1:
        nav_hints.append(f"`/logs {run_id} {page - 1}` \\- prev")
    if page < total_pages:
        nav_hints.append(f"`/logs {run_id} {page + 1}` \\- next")
    nav_hints.append(f"`/logs {run_id} all` \\- download")

    nav_text = " | ".join(nav_hints)

    await message.answer(
        f"*Run \\#{run_id} \\- Logs* \\(page {page}/{total_pages}\\)\n\n"
        f"```\n{_escape_markdown(page_content)}\n```\n\n"
        f"{nav_text}"
    )


async def _send_logs_as_file(message: Message, run_id: int, content: str) -> None:
    """Send logs as a text file attachment.

    Creates a temporary file and sends it as a document for large log outputs.

    Args:
        message: Message to reply to
        run_id: Run ID for filename
        content: Full log content to send
    """
    import tempfile

    # Create temporary file with logs
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            prefix=f"run_{run_id}_logs_",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(content)
            temp_path = Path(f.name)

        # Send as document
        document = FSInputFile(temp_path, filename=f"run_{run_id}_logs.txt")
        await message.answer_document(
            document=document,
            caption=f"Full logs for run \\#{run_id} \\({len(content)} bytes\\)",
        )

        # Clean up temp file
        temp_path.unlink(missing_ok=True)

    except Exception as e:
        logger.exception(f"Failed to send logs file for run {run_id}")
        await message.answer(f"Failed to create log file: `{_escape_markdown(str(e))}`")


# Tail update interval in seconds
TAIL_UPDATE_INTERVAL = 2.0

# Maximum tail duration before auto-stop (10 minutes)
TAIL_MAX_DURATION = 600.0


async def _tail_loop(
    chat_id: int,
    user_id: int,
    run_id: int,
    bot: Bot,
    state_store: StateStore,
    editor: MessageEditor,
) -> None:
    """Background task that streams run output to chat.

    Updates the message every TAIL_UPDATE_INTERVAL seconds with the latest
    output buffer content. Automatically stops when:
    - The run completes (status != running)
    - Max duration exceeded (TAIL_MAX_DURATION)
    - Task is cancelled (user runs /tail stop)

    Args:
        chat_id: Telegram chat ID for sending updates
        user_id: User ID (for cleanup in _active_tails)
        run_id: The run ID to tail
        bot: Bot instance for sending messages
        state_store: StateStore for checking run status
        editor: MessageEditor for rate-limited updates
    """
    start_time = asyncio.get_event_loop().time()
    last_output_len = 0

    try:
        # Send initial message
        await editor.send_or_edit(
            chat_id,
            f"📡 *Tailing run \\#{run_id}*\n\n_Waiting for output..._\n\n"
            f"Use `/tail stop` to stop tailing.",
        )

        while True:
            # Check max duration
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= TAIL_MAX_DURATION:
                await editor.send_or_edit(
                    chat_id,
                    f"📡 *Tail stopped* \\(run \\#{run_id}\\)\n\n"
                    f"Maximum tail duration \\({int(TAIL_MAX_DURATION // 60)} min\\) reached\\.",
                )
                break

            # Check if run is still active
            run = await state_store.get_run(run_id)
            if run is None or run.status != "running":
                status_text = run.status if run else "not found"
                final_output = _run_output_buffers.get(run_id, "")
                if final_output:
                    # Show final output snippet
                    output_tail = final_output[-1500:] if len(final_output) > 1500 else final_output
                    await editor.send_or_edit(
                        chat_id,
                        f"📡 *Tail ended* \\- run \\#{run_id} {_escape_markdown(status_text)}\n\n"
                        f"```\n{_escape_markdown(output_tail)}\n```",
                    )
                else:
                    await editor.send_or_edit(
                        chat_id,
                        f"📡 *Tail ended* \\- run \\#{run_id} {_escape_markdown(status_text)}",
                    )
                break

            # Get current output buffer
            current_output = _run_output_buffers.get(run_id, "")

            # Only update if output changed
            if len(current_output) != last_output_len:
                last_output_len = len(current_output)
                # Show tail of output (last ~1500 chars to stay under Telegram limits)
                if len(current_output) > 1500:
                    output_tail = current_output[-1500:]
                else:
                    output_tail = current_output
                if output_tail:
                    minutes = int(elapsed // 60)
                    seconds = int(elapsed % 60)
                    time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
                    await editor.send_or_edit(
                        chat_id,
                        f"📡 *Tailing run \\#{run_id}* \\({time_str}\\)\n\n"
                        f"```\n{_escape_markdown(output_tail)}\n```\n\n"
                        f"Use `/tail stop` to stop\\.",
                    )

            # Wait before next update
            await asyncio.sleep(TAIL_UPDATE_INTERVAL)

    except asyncio.CancelledError:
        # User stopped the tail
        await bot.send_message(
            chat_id,
            f"📡 *Tail stopped* \\(run \\#{run_id}\\)",
            parse_mode="Markdown",
        )
        raise

    except Exception as e:
        logger.exception(f"Tail loop error for run {run_id}")
        with contextlib.suppress(Exception):
            await bot.send_message(
                chat_id,
                f"📡 *Tail error:* `{_escape_markdown(str(e)[:100])}`",
                parse_mode="Markdown",
            )

    finally:
        # Clean up registration
        _active_tails.pop(user_id, None)


async def tail_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    bot: Bot,
) -> None:
    """Handle /tail <run_id> command to stream live output of a running command.

    Starts a background task that updates a message every 2 seconds with the
    latest output from a running command. Only one tail per user is allowed.

    Args:
        message: Incoming Telegram message
        command: Parsed command with run_id or 'stop' argument
        state_store: StateStore for run lookup and status checking
        bot: Bot instance for sending messages

    Usage:
        /tail <run_id>  - Start tailing output of run #<run_id>
        /tail stop      - Stop the active tail for this user

    Failure modes handled:
        - Multiple concurrent tails: Only one allowed per user
        - Run completes during tail: Auto-stops with final status
        - Memory leak from orphaned tasks: Cleanup in finally block
        - Stop command: Cancels the background task
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    chat_id = message.chat.id

    # Parse arguments: /tail <run_id> or /tail stop
    args = command.args.strip().lower() if command.args else ""

    # Handle /tail stop
    if args == "stop":
        tail_info = _active_tails.get(user_id)
        if tail_info is None:
            await message.answer("No active tail to stop.")
            return

        run_id, task = tail_info
        task.cancel()
        # Cleanup happens in the task's finally block
        await message.answer(f"Stopping tail for run \\#{run_id}\\.")
        return

    # Handle /tail (no args) - show usage
    if not args:
        # Check if user has an active tail
        tail_info = _active_tails.get(user_id)
        if tail_info:
            run_id, _ = tail_info
            await message.answer(
                f"Currently tailing run \\#{run_id}\\.\n\nUse `/tail stop` to stop tailing."
            )
        else:
            await message.answer(
                "Usage: `/tail <run_id>`\n\n"
                "Stream live output from a running command\\.\n"
                "  `/tail 123` \\- Start tailing run \\#123\n"
                "  `/tail stop` \\- Stop active tail"
            )
        return

    # Parse run_id
    if not args.isdigit():
        await message.answer(f"Invalid run ID: `{_escape_markdown(args)}`")
        return
    run_id = int(args)

    # Check if user already has an active tail
    existing_tail = _active_tails.get(user_id)
    if existing_tail is not None:
        existing_run_id, _ = existing_tail
        await message.answer(
            f"Already tailing run \\#{existing_run_id}\\.\n\n"
            "Use `/tail stop` first, then start a new tail."
        )
        return

    # Verify run exists and belongs to user
    run = await state_store.get_run(run_id)
    if run is None:
        await message.answer(f"Run \\#{run_id} not found\\.")
        return

    if run.user_id != user_id:
        await message.answer(f"Run \\#{run_id} not found\\.")
        return

    # Check if run is still running
    if run.status != "running":
        await message.answer(
            f"Run \\#{run_id} is not running \\(status: {_escape_markdown(run.status)}\\)\\.\n\n"
            "Use `/logs {run_id}` to view completed run output."
        )
        return

    # Create message editor for this tail session
    # Bot is compatible with TelegramBot protocol at runtime
    editor = MessageEditor(bot)  # type: ignore[arg-type]

    # Start background tail task
    task = asyncio.create_task(_tail_loop(chat_id, user_id, run_id, bot, state_store, editor))
    _active_tails[user_id] = (run_id, task)

    logger.info(f"User {user_id} started tailing run {run_id}")


async def status_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
) -> None:
    """Handle /status command to show current run and queue state.

    When called without arguments, displays:
    - Current active run (if any) with project and command
    - Queue position and pending count
    - Recent completed/failed runs

    When called with a run_id argument (e.g., /status 123), displays detailed
    information about that specific run:
    - Command, project, status
    - Duration (started_at to completed_at or current time)
    - Result or error message if available

    Args:
        message: Incoming Telegram message
        command: Parsed command with optional run_id argument
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue state
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Check if a specific run_id was requested
    args = command.args.strip() if command.args else ""
    if args:
        # Try to parse run_id from arguments
        if args.isdigit():
            run_id = int(args)
            await _show_run_details(message, state_store, user_id, run_id)
            return
        else:
            await message.answer(
                f"Invalid run ID: {_escape_markdown(args)}\nUsage: /status \\[run\\_id\\]"
            )
            return

    chat_id = message.chat.id

    # Get current context
    context = await state_store.get_context(user_id)

    # Get active/pending runs
    running_runs = await state_store.list_runs_by_user(user_id, limit=1, status="running")
    pending_runs = await state_store.list_runs_by_user(user_id, limit=10, status="pending")

    # Build status message
    lines: list[str] = []

    # Current project
    if context and context.current_project:
        lines.append(f"*Project:* {_escape_markdown(context.current_project)}")
    else:
        lines.append("*Project:* None selected")

    lines.append("")

    # Active run
    if running_runs:
        run = running_runs[0]
        cmd_display = run.command[:50] + "..." if len(run.command) > 50 else run.command
        cmd_escaped = _escape_markdown(cmd_display)
        lines.append("*Current run:*")
        lines.append(f"  Command: `{cmd_escaped}`")
        lines.append(f"  Project: {_escape_markdown(run.project_name)}")
        lines.append("  Status: running")
    else:
        lines.append("*Current run:* None")

    lines.append("")

    # Queue status
    queue_size = queue_manager.queue_size(chat_id)
    if queue_size > 0 or pending_runs:
        lines.append(f"*Queue:* {queue_size} pending")
        if pending_runs:
            lines.append("Pending commands:")
            for i, run in enumerate(pending_runs[:5], 1):
                cmd_short = run.command[:30] + "..." if len(run.command) > 30 else run.command
                lines.append(f"  {i}. `{_escape_markdown(cmd_short)}`")
            if len(pending_runs) > 5:
                lines.append(f"  ... and {len(pending_runs) - 5} more")
    else:
        lines.append("*Queue:* Empty")

    # Recent history (last 3 completed/failed)
    recent_runs = await state_store.list_runs_by_user(user_id, limit=5)
    terminal_statuses = ("completed", "failed", "cancelled")
    completed_runs = [r for r in recent_runs if r.status in terminal_statuses][:3]

    if completed_runs:
        lines.append("")
        lines.append("*Recent:*")
        for run in completed_runs:
            status_emoji = {"completed": "✓", "failed": "✗", "cancelled": "⊘"}.get(run.status, "?")
            cmd_short = run.command[:25] + "..." if len(run.command) > 25 else run.command
            lines.append(f"  {status_emoji} `{_escape_markdown(cmd_short)}`")

    await message.answer("\n".join(lines))


async def cancel_command(
    message: Message,
    state_store: StateStore,
    queue_manager: QueueManager[int],
) -> None:
    """Handle /cancel command to abort active run and clear queue.

    Cancels the currently running command (if any) and clears all
    pending commands from the queue.

    Args:
        message: Incoming Telegram message
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    chat_id = message.chat.id

    # Track what we cancelled
    cancelled_active = False
    cancelled_pending = 0

    # Get and cancel active run
    running_runs = await state_store.list_runs_by_user(user_id, limit=1, status="running")
    if running_runs:
        run = running_runs[0]
        # Mark the run as cancelled in the database
        run.status = "cancelled"
        run.completed_at = datetime.now(UTC)
        run.error = "Cancelled by user"
        try:
            await state_store.update_run(run)
            cancelled_active = True
            logger.info(f"User {user_id} cancelled active run {run.id}")
        except Exception:
            logger.exception(f"Failed to cancel active run {run.id} for user {user_id}")

    # Cancel pending items in queue
    cancelled_pending = await queue_manager.cancel_pending(chat_id)

    # Also mark pending runs in database as cancelled
    pending_runs = await state_store.list_runs_by_user(user_id, limit=100, status="pending")
    db_cancelled_count = 0
    for run in pending_runs:
        run.status = "cancelled"
        run.completed_at = datetime.now(UTC)
        run.error = "Cancelled by user"
        try:
            await state_store.update_run(run)
            db_cancelled_count += 1
        except Exception:
            logger.exception(f"Failed to cancel pending run {run.id} for user {user_id}")
    if db_cancelled_count > 0:
        logger.info(f"User {user_id} cancelled {db_cancelled_count} pending runs in database")

    # Update user context to idle
    context = await state_store.get_context(user_id)
    if context and context.conversation_state == "running":
        context.conversation_state = "idle"
        context.updated_at = datetime.now(UTC)
        await state_store.upsert_context(context)

    # Build response
    if cancelled_active or cancelled_pending > 0 or db_cancelled_count > 0:
        parts: list[str] = []
        if cancelled_active:
            parts.append("Cancelled active run")
        total_pending = max(cancelled_pending, db_cancelled_count)
        if total_pending > 0:
            parts.append(f"cleared {total_pending} pending command(s)")
        await message.answer("✓ " + ", ".join(parts) + ".")
    else:
        await message.answer("Nothing to cancel. No active or pending runs.")


def _sanitize_command_args(args: str) -> str:
    """Sanitize command arguments to prevent shell injection.

    Removes or escapes potentially dangerous characters from user input.
    Also normalizes Unicode dashes to regular hyphens (Telegram auto-converts
    -- to em-dash).

    Args:
        args: Raw command arguments from user

    Returns:
        Sanitized argument string safe for command construction
    """
    if not args:
        return ""

    # Remove null bytes
    args = args.replace("\0", "")

    # Normalize Unicode dashes to regular hyphens
    # Telegram and other apps often auto-convert -- to em-dash or similar
    unicode_dashes = [
        "\u2014",  # Em dash
        "\u2013",  # En dash
        "\u2212",  # Minus sign
        "\u2015",  # Horizontal bar
    ]
    for dash in unicode_dashes:
        args = args.replace(dash, "--")

    # Remove shell metacharacters that could enable injection
    # Allow: alphanumeric, space, dash, underscore, dot, forward slash, quotes
    dangerous_chars = [";", "&", "|", "$", "`", "(", ")", "{", "}", "<", ">", "\n", "\r"]
    for char in dangerous_chars:
        args = args.replace(char, "")

    return args.strip()


def _find_uploaded_file(uploads_dir: Path, sanitized_name: str) -> Path | None:
    """Find an uploaded file by its sanitized name.

    Searches for exact match first, then looks for files with numeric
    suffixes (e.g., spec.1.md, spec.2.md) in case of filename conflicts
    during upload. Returns the most recently modified match.

    Args:
        uploads_dir: The uploads directory to search in
        sanitized_name: Sanitized filename to look for

    Returns:
        Path to the found file, or None if not found
    """
    if not uploads_dir.exists():
        return None

    # Try exact match first
    exact_path = uploads_dir / sanitized_name
    if exact_path.exists() and exact_path.is_file():
        return exact_path

    # Look for files with numeric suffixes (name.N.ext or name.N)
    # Split into base name and extension
    parts = sanitized_name.rsplit(".", 1)
    if len(parts) == 2:
        base, ext = parts
        pattern = f"{base}.*"  # Will match base.1.ext, base.2.ext, etc.
    else:
        base = sanitized_name
        ext = None
        pattern = f"{base}.*"

    # Find all candidates
    candidates: list[Path] = []
    for candidate in uploads_dir.glob(pattern):
        if not candidate.is_file():
            continue
        # Check if it matches the expected pattern (base.N.ext or base.N)
        name = candidate.name
        if ext:
            # Expected format: base.N.ext
            if name.startswith(f"{base}.") and name.endswith(f".{ext}"):
                middle = name[len(base) + 1 : -(len(ext) + 1)]
                if middle.isdigit():
                    candidates.append(candidate)
        else:
            # Expected format: base.N
            if name.startswith(f"{base}."):
                suffix = name[len(base) + 1 :]
                if suffix.isdigit():
                    candidates.append(candidate)

    if not candidates:
        return None

    # Return most recently modified
    return max(candidates, key=lambda p: p.stat().st_mtime)


async def _enqueue_weld_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
    config: TelegramConfig,
    weld_command: str,
) -> None:
    """Common handler for weld commands that enqueue runs.

    Validates project context, creates a run record, and enqueues it.
    When the message is a reply to a document, auto-injects the uploaded
    file path as the first positional argument.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations
        config: TelegramConfig with registered projects
        weld_command: The weld subcommand name (e.g., "doctor", "plan")
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    chat_id = message.chat.id

    # Check project context
    context = await state_store.get_context(user_id)
    if not context or not context.current_project:
        await message.answer(
            "No project selected.\n\nUse `/use <project>` to select a project first."
        )
        return

    project_name = context.current_project

    # Check if message is a reply to a document - auto-inject file path
    injected_file_path: str | None = None
    if message.reply_to_message and message.reply_to_message.document:
        replied_doc = message.reply_to_message.document
        if replied_doc.file_name:
            # Get project path to find uploads directory
            project = config.get_project(project_name)
            if project:
                uploads_dir = get_uploads_dir(project.path)
                # Sanitize the filename to match what document_handler saved
                sanitized_name = sanitize_filename(replied_doc.file_name)
                # Look for the file (exact match or with numeric suffix)
                uploaded_file = _find_uploaded_file(uploads_dir, sanitized_name)
                if uploaded_file:
                    # Use path relative to project root for the command
                    try:
                        relative_path = uploaded_file.relative_to(project.path)
                        injected_file_path = str(relative_path)
                    except ValueError:
                        # Fallback to absolute path if not under project
                        injected_file_path = str(uploaded_file)
                    logger.info(
                        f"Auto-injecting file path '{injected_file_path}' from reply-to-document"
                    )
                else:
                    await message.answer(
                        f"Cannot find uploaded file `{_escape_markdown(sanitized_name)}`.\n"
                        "The file may have been deleted or not uploaded yet."
                    )
                    return

    # Build the full command string with sanitized arguments
    raw_args = command.args.strip() if command.args else ""
    args = _sanitize_command_args(raw_args)

    # If we have an injected file path, prepend it to args
    if injected_file_path:
        args = f"{injected_file_path} {args}" if args else injected_file_path

    full_command = f"weld {weld_command} {args}" if args else f"weld {weld_command}"

    # Create run record
    run = Run(
        user_id=user_id,
        project_name=project_name,
        command=full_command,
        status="pending",
    )
    run_id = await state_store.create_run(run)

    # Enqueue the run
    try:
        position = await queue_manager.enqueue(chat_id, run_id)
    except Exception:
        # If enqueue fails, mark run as failed
        run.id = run_id
        run.status = "failed"
        run.completed_at = datetime.now(UTC)
        run.error = "Failed to enqueue command"
        try:
            await state_store.update_run(run)
        except Exception:
            logger.exception(f"Failed to update run {run_id} status to failed")
        logger.exception(f"Failed to enqueue run {run_id} for user {user_id}")
        await message.answer("Failed to queue command. Please try again.")
        return

    logger.info(
        f"User {user_id} queued '{full_command}' for project '{project_name}' "
        f"(run_id={run_id}, position={position})"
    )

    # Build response
    cmd_escaped = _escape_markdown(full_command)
    if position == 1:
        await message.answer(
            f"Queued: `{cmd_escaped}`\n"
            f"Project: *{_escape_markdown(project_name)}*\n"
            f"Position: next up"
        )
    else:
        await message.answer(
            f"Queued: `{cmd_escaped}`\n"
            f"Project: *{_escape_markdown(project_name)}*\n"
            f"Position: {position} in queue"
        )


async def doctor_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
    config: TelegramConfig,
) -> None:
    """Handle /doctor command to run weld doctor.

    Validates environment and tool availability for the selected project.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations
        config: TelegramConfig with registered projects

    Usage:
        /doctor - Run environment validation
    """
    await _enqueue_weld_command(message, command, state_store, queue_manager, config, "doctor")


async def plan_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
    config: TelegramConfig,
) -> None:
    """Handle /plan command to run weld plan.

    Generate or view implementation plans for the selected project.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations
        config: TelegramConfig with registered projects

    Usage:
        /plan              - Show plan help/status
        /plan <file.md>    - Generate plan from specification file
    """
    await _enqueue_weld_command(message, command, state_store, queue_manager, config, "plan")


async def interview_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
    config: TelegramConfig,
) -> None:
    """Handle /interview command to run weld interview.

    Interactive specification refinement for the selected project.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations
        config: TelegramConfig with registered projects

    Usage:
        /interview              - Start interactive interview
        /interview <spec.md>    - Interview about specific spec file
    """
    await _enqueue_weld_command(message, command, state_store, queue_manager, config, "interview")


async def implement_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
    config: TelegramConfig,
) -> None:
    """Handle /implement command to run weld implement.

    Execute implementation plans step by step for the selected project.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations
        config: TelegramConfig with registered projects

    Usage:
        /implement <plan.md>              - Execute plan interactively
        /implement <plan.md> --phase 1    - Execute specific phase
        /implement <plan.md> --step 1.2   - Execute specific step
    """
    await _enqueue_weld_command(message, command, state_store, queue_manager, config, "implement")


async def commit_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
    config: TelegramConfig,
) -> None:
    """Handle /commit command to run weld commit.

    Create session-based commits with transcript provenance.

    Args:
        message: Incoming Telegram message
        command: Parsed command with arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations
        config: TelegramConfig with registered projects

    Usage:
        /commit                       - Commit with auto-generated message
        /commit -m "message"          - Commit with custom message
        /commit --no-session-split    - Single commit for all files
    """
    await _enqueue_weld_command(message, command, state_store, queue_manager, config, "commit")


# Subcommands blocked for safety - these could cause unintended harm or are not appropriate
# for remote execution via Telegram
_BLOCKED_WELD_SUBCOMMANDS = frozenset(
    {
        "telegram",  # Prevent recursive bot operations
    }
)


async def weld_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    queue_manager: QueueManager[int],
    config: TelegramConfig,
) -> None:
    """Handle /weld <subcommand> [args] to run any weld command.

    Generic handler that accepts any weld subcommand and its arguments,
    providing a flexible way to run weld commands not covered by dedicated
    bot commands. When the message is a reply to a document, auto-injects
    the uploaded file path as the first positional argument.

    Args:
        message: Incoming Telegram message
        command: Parsed command with subcommand and arguments
        state_store: StateStore instance for database operations
        queue_manager: QueueManager for queue operations
        config: TelegramConfig with registered projects

    Usage:
        /weld research spec.md        - Run weld research
        /weld discover                - Run weld discover
        /weld review file.py          - Run weld review
        /weld init                    - Initialize weld in project
    """
    # Parse subcommand and remaining args from command.args
    raw_args = command.args.strip() if command.args else ""

    if not raw_args:
        await message.answer(
            "Usage: `/weld <subcommand> [args]`\n\n"
            "Run any weld command. Examples:\n"
            "  `/weld research spec.md`\n"
            "  `/weld discover`\n"
            "  `/weld review file.py`\n"
            "  `/weld init`\n\n"
            "Or use dedicated commands:\n"
            "  `/doctor`, `/plan`, `/interview`, `/implement`, `/commit`"
        )
        return

    # Extract subcommand (first word) and remaining args
    parts = raw_args.split(maxsplit=1)
    subcommand = parts[0].lower()
    remaining_args = parts[1] if len(parts) > 1 else ""

    # Check for blocked subcommands
    if subcommand in _BLOCKED_WELD_SUBCOMMANDS:
        await message.answer(
            f"The `{_escape_markdown(subcommand)}` subcommand is not allowed via Telegram."
        )
        return

    # Sanitize the subcommand itself (should be alphanumeric/dash/underscore only)
    if not all(c.isalnum() or c in "-_" for c in subcommand):
        await message.answer(
            "Invalid subcommand. "
            "Subcommand must contain only letters, numbers, dashes, or underscores."
        )
        return

    # Create a synthetic CommandObject with remaining_args for _enqueue_weld_command
    # We can't modify command.args directly, so we'll inline the logic here
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    chat_id = message.chat.id

    # Check project context
    context = await state_store.get_context(user_id)
    if not context or not context.current_project:
        await message.answer(
            "No project selected.\n\nUse `/use <project>` to select a project first."
        )
        return

    project_name = context.current_project

    # Check if message is a reply to a document - auto-inject file path
    injected_file_path: str | None = None
    if message.reply_to_message and message.reply_to_message.document:
        replied_doc = message.reply_to_message.document
        if replied_doc.file_name:
            # Get project path to find uploads directory
            project = config.get_project(project_name)
            if project:
                uploads_dir = get_uploads_dir(project.path)
                # Sanitize the filename to match what document_handler saved
                sanitized_name = sanitize_filename(replied_doc.file_name)
                # Look for the file (exact match or with numeric suffix)
                uploaded_file = _find_uploaded_file(uploads_dir, sanitized_name)
                if uploaded_file:
                    # Use path relative to project root for the command
                    try:
                        relative_path = uploaded_file.relative_to(project.path)
                        injected_file_path = str(relative_path)
                    except ValueError:
                        # Fallback to absolute path if not under project
                        injected_file_path = str(uploaded_file)
                    logger.info(
                        f"Auto-injecting file path '{injected_file_path}' from reply-to-document"
                    )
                else:
                    await message.answer(
                        f"Cannot find uploaded file `{_escape_markdown(sanitized_name)}`.\n"
                        "The file may have been deleted or not uploaded yet."
                    )
                    return

    # Build the full command string with sanitized arguments
    args = _sanitize_command_args(remaining_args)

    # If we have an injected file path, prepend it to args
    if injected_file_path:
        args = f"{injected_file_path} {args}" if args else injected_file_path

    full_command = f"weld {subcommand} {args}" if args else f"weld {subcommand}"

    # Create run record
    run = Run(
        user_id=user_id,
        project_name=project_name,
        command=full_command,
        status="pending",
    )
    run_id = await state_store.create_run(run)

    # Enqueue the run
    try:
        position = await queue_manager.enqueue(chat_id, run_id)
    except Exception:
        # If enqueue fails, mark run as failed
        run.id = run_id
        run.status = "failed"
        run.completed_at = datetime.now(UTC)
        run.error = "Failed to enqueue command"
        try:
            await state_store.update_run(run)
        except Exception:
            logger.exception(f"Failed to update run {run_id} status to failed")
        logger.exception(f"Failed to enqueue run {run_id} for user {user_id}")
        await message.answer("Failed to queue command. Please try again.")
        return

    logger.info(
        f"User {user_id} queued '{full_command}' for project '{project_name}' "
        f"(run_id={run_id}, position={position})"
    )

    # Build response
    cmd_escaped = _escape_markdown(full_command)
    if position == 1:
        await message.answer(
            f"Queued: `{cmd_escaped}`\n"
            f"Project: *{_escape_markdown(project_name)}*\n"
            f"Position: next up"
        )
    else:
        await message.answer(
            f"Queued: `{cmd_escaped}`\n"
            f"Project: *{_escape_markdown(project_name)}*\n"
            f"Position: {position} in queue"
        )


async def fetch_command(
    message: Message,
    command: CommandObject,
    config: TelegramConfig,
    bot: Bot,
) -> None:
    """Handle /fetch <path> command to download a file from the project.

    Validates the path is within a registered project, checks file size,
    and sends the file via Telegram. Falls back to GitHub Gist for files
    larger than Telegram's 50MB limit.

    Args:
        message: Incoming Telegram message
        command: Parsed command with path argument
        config: TelegramConfig with registered projects
        bot: Bot instance for sending files

    Usage:
        /fetch src/main.py           - Download a file
        /fetch /absolute/path/file   - Download using absolute path
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Extract path argument
    path_arg = command.args.strip() if command.args else ""
    if not path_arg:
        await message.answer(
            "Usage: `/fetch <path>`\n\n"
            "Downloads a file from a registered project.\n"
            "Path must be within a project directory."
        )
        return

    # Validate path
    try:
        resolved_path = validate_fetch_path(path_arg, config)
    except TelegramError as e:
        # Unified error handling for all Telegram-related path errors
        # The error message already contains appropriate context
        await message.answer(f"Error: `{_escape_markdown(str(e))}`")
        return

    # Check if it's a directory
    if resolved_path.is_dir():
        await message.answer("Cannot fetch directories. Specify a file path.")
        return

    # Get file size
    try:
        file_size = resolved_path.stat().st_size
    except OSError as e:
        await message.answer(f"Cannot read file: `{_escape_markdown(str(e))}`")
        return

    # Check if file is too large for Telegram
    if file_size > TELEGRAM_MAX_DOWNLOAD_SIZE:
        # Fall back to gist for large files
        logger.info(
            f"File {resolved_path} ({file_size} bytes) exceeds Telegram limit, using gist fallback"
        )
        await _fetch_via_gist(message, resolved_path)
        return

    # Send file via Telegram
    try:
        document = FSInputFile(resolved_path, filename=resolved_path.name)
        await bot.send_document(
            chat_id=message.chat.id,
            document=document,
            caption=f"`{_escape_markdown(str(resolved_path))}`",
            reply_to_message_id=message.message_id,
        )
        logger.info(f"User {user_id} fetched file: {resolved_path}")
    except Exception as e:
        logger.exception(f"Failed to send file {resolved_path}")
        await message.answer(f"Failed to send file: `{_escape_markdown(str(e))}`")


async def _fetch_via_gist(message: Message, path: Path) -> None:
    """Upload a file to GitHub Gist as fallback for large files.

    Args:
        message: Original message to reply to
        path: Path to the file to upload
    """
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        await message.answer(
            "File is too large for Telegram (>50MB) and is binary.\n"
            "Cannot upload binary files to Gist."
        )
        return
    except OSError as e:
        await message.answer(f"Failed to read file: `{_escape_markdown(str(e))}`")
        return

    try:
        # upload_gist is synchronous and does blocking I/O - run in thread pool
        result = await asyncio.to_thread(
            upload_gist,
            content=content,
            filename=path.name,
            description=f"File fetch: {path.name}",
            public=False,
        )
        await message.answer(
            f"File too large for Telegram (>50MB).\nUploaded to Gist: {result.gist_url}"
        )
    except GistError as e:
        await message.answer(
            f"File too large for Telegram and Gist upload failed:\n`{_escape_markdown(str(e))}`"
        )


# Maximum content length before pagination is triggered
CAT_PAGINATION_THRESHOLD = 4000

# Lines per page for paginated cat output
CAT_LINES_PER_PAGE = 50


def _create_cat_pagination_keyboard(
    callback_id: str, current_page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """Create inline keyboard for cat pagination navigation.

    Args:
        callback_id: Unique identifier for this pagination session
        current_page: Current page number (0-indexed)
        total_pages: Total number of pages

    Returns:
        InlineKeyboardMarkup with Prev/Next/Close buttons
    """
    buttons: list[InlineKeyboardButton] = []

    # Previous button (disabled on first page)
    if current_page > 0:
        buttons.append(
            InlineKeyboardButton(
                text="⬅️ Prev", callback_data=f"cat:{callback_id}:{current_page - 1}"
            )
        )

    # Page indicator
    buttons.append(
        InlineKeyboardButton(text=f"{current_page + 1}/{total_pages}", callback_data="cat:noop")
    )

    # Next button (disabled on last page)
    if current_page < total_pages - 1:
        buttons.append(
            InlineKeyboardButton(
                text="Next ➡️", callback_data=f"cat:{callback_id}:{current_page + 1}"
            )
        )

    # Close button on its own row
    close_button = InlineKeyboardButton(text="❌ Close", callback_data=f"cat:{callback_id}:close")

    return InlineKeyboardMarkup(inline_keyboard=[buttons, [close_button]])


async def cat_command(
    message: Message,
    command: CommandObject,
    config: TelegramConfig,
) -> None:
    """Handle /cat <path> command to view file contents with syntax highlighting.

    Validates the path is within a registered project, checks if the file is
    a text file (based on extension allowlist), and displays the content with
    appropriate syntax highlighting. Files larger than 4000 characters are
    paginated.

    Args:
        message: Incoming Telegram message
        command: Parsed command with path argument
        config: TelegramConfig with registered projects

    Usage:
        /cat src/main.py           - View a file with syntax highlighting
        /cat /absolute/path/file   - View using absolute path
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Extract path argument
    path_arg = command.args.strip() if command.args else ""
    if not path_arg:
        await message.answer(
            "Usage: `/cat <path>`\n\n"
            "Displays file contents with syntax highlighting.\n"
            "Path must be within a registered project."
        )
        return

    # Validate path
    try:
        resolved_path = validate_fetch_path(path_arg, config)
    except TelegramError as e:
        await message.answer(f"Error: `{_escape_markdown(str(e))}`")
        return

    # Check if it's a directory
    if resolved_path.is_dir():
        await message.answer("Cannot view directories. Specify a file path.")
        return

    # Check if it's a text file based on extension
    if not is_text_file(resolved_path):
        await message.answer(
            f"Cannot view binary file: `{_escape_markdown(resolved_path.name)}`\n\n"
            "Use `/fetch` to download it instead."
        )
        return

    # Read file content
    try:
        content = resolved_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        await message.answer(
            f"Cannot decode file as text: `{_escape_markdown(resolved_path.name)}`\n\n"
            "File may be binary. Use `/fetch` to download it."
        )
        return
    except OSError as e:
        await message.answer(f"Cannot read file: `{_escape_markdown(str(e))}`")
        return

    # Get syntax language for highlighting
    language = get_syntax_language(resolved_path)

    # Format header with file path
    header = f"📄 `{_escape_markdown(resolved_path.name)}`\n\n"

    # Check if pagination is needed
    if len(content) <= CAT_PAGINATION_THRESHOLD:
        # Small file - send directly
        # Escape backticks within content to prevent markdown breaking
        escaped_content = content.replace("`", "\\`")
        code_block = f"```{language}\n{escaped_content}\n```"
        await message.answer(header + code_block)
        logger.info(f"User {user_id} viewed file: {resolved_path} ({len(content)} chars)")
    else:
        # Large file - paginate
        lines = content.splitlines()
        total_lines = len(lines)
        total_pages = (total_lines + CAT_LINES_PER_PAGE - 1) // CAT_LINES_PER_PAGE

        # Create unique callback ID for this pagination session
        import uuid

        callback_id = str(uuid.uuid4())[:8]

        # Create pagination state
        state = PaginationState(
            file_path=resolved_path,
            lines=lines,
            current_page=0,
            total_pages=total_pages,
            lines_per_page=CAT_LINES_PER_PAGE,
        )
        set_pagination_state(callback_id, state)

        # Get first page content
        page_content = state.get_page_content()
        escaped_content = page_content.replace("`", "\\`")
        code_block = f"```{language}\n{escaped_content}\n```"

        # Create navigation keyboard
        keyboard = _create_cat_pagination_keyboard(callback_id, 0, total_pages)

        await message.answer(header + code_block, reply_markup=keyboard)
        logger.info(
            f"User {user_id} viewing paginated file: {resolved_path} "
            f"({total_lines} lines, {total_pages} pages)"
        )


async def handle_cat_pagination_callback(callback: CallbackQuery) -> None:
    """Handle callback from cat pagination inline keyboard buttons.

    Args:
        callback: The callback query from button press
    """
    if not callback.data or not callback.data.startswith("cat:"):
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        logger.warning(f"Invalid cat callback data: {callback.data}")
        return

    _, callback_id, action = parts

    # Handle no-op (page indicator button)
    if action == "noop":
        await callback.answer()
        return

    # Handle close action
    if action == "close":
        remove_pagination_state(callback_id)
        if isinstance(callback.message, Message):
            with contextlib.suppress(Exception):
                await callback.message.delete()
        await callback.answer("Closed")
        return

    # Handle page navigation
    try:
        target_page = int(action)
    except ValueError:
        logger.warning(f"Invalid page number in cat callback: {action}")
        await callback.answer("Invalid action", show_alert=True)
        return

    # Get pagination state
    state = get_pagination_state(callback_id)
    if state is None:
        await callback.answer("Session expired. Use /cat again.", show_alert=True)
        if isinstance(callback.message, Message):
            with contextlib.suppress(Exception):
                await callback.message.delete()
        return

    # Validate target page
    if target_page < 0 or target_page >= state.total_pages:
        await callback.answer("Invalid page", show_alert=True)
        return

    # Update state with new page
    state.current_page = target_page

    # Get page content
    page_content = state.get_page_content()
    escaped_content = page_content.replace("`", "\\`")

    # Get syntax language
    language = get_syntax_language(state.file_path)

    # Format message
    header = f"📄 `{_escape_markdown(state.file_path.name)}`\n\n"
    code_block = f"```{language}\n{escaped_content}\n```"

    # Create updated keyboard
    keyboard = _create_cat_pagination_keyboard(callback_id, target_page, state.total_pages)

    # Update message
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                header + code_block, reply_markup=keyboard, parse_mode="Markdown"
            )
            await callback.answer()
        except Exception as e:
            logger.warning(f"Failed to update cat pagination message: {e}")
            await callback.answer("Failed to update", show_alert=True)
    else:
        await callback.answer("Cannot update message", show_alert=True)


async def head_command(
    message: Message,
    command: CommandObject,
    config: TelegramConfig,
) -> None:
    """Handle /head <path> [lines] command to view first N lines of a file.

    Validates the path is within a registered project, checks if the file is
    a text file (based on extension allowlist), and displays the first N lines
    with appropriate syntax highlighting. Default is 20 lines if not specified.

    Args:
        message: Incoming Telegram message
        command: Parsed command with path and optional line count arguments
        config: TelegramConfig with registered projects

    Usage:
        /head src/main.py           - View first 20 lines
        /head src/main.py 50        - View first 50 lines
        /head /absolute/path/file   - View using absolute path
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Default number of lines
    default_lines = 20

    # Extract arguments: <path> [lines]
    args = command.args.strip() if command.args else ""
    if not args:
        await message.answer(
            "Usage: `/head <path> [lines]`\n\n"
            "Displays first N lines of a file (default 20).\n"
            "Path must be within a registered project."
        )
        return

    # Parse path and optional line count
    parts = args.split()
    path_arg = parts[0]
    lines_count = default_lines

    if len(parts) > 1:
        try:
            lines_count = int(parts[1])
            if lines_count <= 0:
                await message.answer("Line count must be a positive integer.")
                return
        except ValueError:
            await message.answer(
                f"Invalid line count: `{_escape_markdown(parts[1])}`\n\n"
                "Usage: `/head <path> [lines]`"
            )
            return

    # Validate path
    try:
        resolved_path = validate_fetch_path(path_arg, config)
    except TelegramError as e:
        await message.answer(f"Error: `{_escape_markdown(str(e))}`")
        return

    # Check if it's a directory
    if resolved_path.is_dir():
        await message.answer("Cannot view directories. Specify a file path.")
        return

    # Check if it's a text file based on extension
    if not is_text_file(resolved_path):
        await message.answer(
            f"Cannot view binary file: `{_escape_markdown(resolved_path.name)}`\n\n"
            "Use `/fetch` to download it instead."
        )
        return

    # Read file content
    try:
        content = resolved_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        await message.answer(
            f"Cannot decode file as text: `{_escape_markdown(resolved_path.name)}`\n\n"
            "File may be binary. Use `/fetch` to download it."
        )
        return
    except OSError as e:
        await message.answer(f"Cannot read file: `{_escape_markdown(str(e))}`")
        return

    # Get first N lines
    lines = content.splitlines()
    total_lines = len(lines)
    head_lines = lines[:lines_count]

    # Get syntax language for highlighting
    language = get_syntax_language(resolved_path)

    # Format header with file path and line info
    if total_lines <= lines_count:
        # File has fewer lines than requested, show all
        header = f"📄 `{_escape_markdown(resolved_path.name)}` ({total_lines} lines)\n\n"
    else:
        header = (
            f"📄 `{_escape_markdown(resolved_path.name)}` "
            f"(lines 1-{lines_count} of {total_lines})\n\n"
        )

    # Format content
    head_content = "\n".join(head_lines)
    escaped_content = head_content.replace("`", "\\`")
    code_block = f"```{language}\n{escaped_content}\n```"

    await message.answer(header + code_block)
    logger.info(
        f"User {user_id} viewed head of file: {resolved_path} "
        f"({min(lines_count, total_lines)} of {total_lines} lines)"
    )


async def push_command(
    message: Message,
    command: CommandObject,
    config: TelegramConfig,
    bot: Bot,
) -> None:
    """Handle /push <path> command to upload a file to the project.

    Must be used as a reply to a document message. Downloads the document
    and writes it to the specified path within a registered project.

    Args:
        message: Incoming Telegram message (should be a reply to a document)
        command: Parsed command with path argument
        config: TelegramConfig with registered projects
        bot: Bot instance for downloading files

    Usage:
        Reply to a document with:
        /push src/new_file.py        - Save document to specified path
        /push /absolute/path/file    - Save using absolute path
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Check if this is a reply to a message
    if not message.reply_to_message:
        await message.answer(
            "Reply to a document with `/push <path>` to save it.\n\n"
            "Usage:\n"
            "1. Send or forward a file to this chat\n"
            "2. Reply to that file with `/push <destination-path>`"
        )
        return

    # Check if the replied message has a document
    replied = message.reply_to_message
    if not replied.document:
        await message.answer(
            "The replied message does not contain a document.\n"
            "Reply to a file/document message to push it."
        )
        return

    # Extract path argument
    path_arg = command.args.strip() if command.args else ""
    if not path_arg:
        # Default to document's original filename if no path specified
        if replied.document.file_name:
            await message.answer(
                "Usage: `/push <path>`\n\n"
                "Specify the destination path for the file.\n"
                f"Original filename: `{_escape_markdown(replied.document.file_name)}`"
            )
        else:
            await message.answer(
                "Usage: `/push <path>`\n\nSpecify the destination path for the file."
            )
        return

    # Validate destination path
    try:
        resolved_path = validate_push_path(path_arg, config)
    except TelegramError as e:
        # Unified error handling for all Telegram-related path errors
        await message.answer(f"Error: `{_escape_markdown(str(e))}`")
        return

    # Check file size (Telegram bot download limit is 20MB, but we allow larger via getFile)
    file_size = replied.document.file_size or 0
    if file_size > TELEGRAM_MAX_DOWNLOAD_SIZE:
        await message.answer(
            f"File too large to download ({file_size / 1024 / 1024:.1f}MB).\n"
            "Telegram bots can only download files up to 50MB."
        )
        return

    # Download the file
    try:
        file = await bot.get_file(replied.document.file_id)
        if not file.file_path:
            await message.answer("Failed to get file path from Telegram.")
            return

        # Download file content
        file_bytes = await bot.download_file(file.file_path)
        if file_bytes is None:
            await message.answer("Failed to download file from Telegram.")
            return

        content = file_bytes.read()
    except Exception as e:
        logger.exception("Failed to download file from Telegram")
        await message.answer(f"Failed to download file: `{_escape_markdown(str(e))}`")
        return

    # Ensure parent directory exists
    try:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        await message.answer(f"Failed to create directory: `{_escape_markdown(str(e))}`")
        return

    # Write file
    try:
        resolved_path.write_bytes(content)
        logger.info(f"User {user_id} pushed file to: {resolved_path}")
        await message.answer(f"Saved to: `{_escape_markdown(str(resolved_path))}`")
    except OSError as e:
        logger.exception(f"Failed to write file to {resolved_path}")
        await message.answer(f"Failed to write file: `{_escape_markdown(str(e))}`")


# Maximum content size for /file command (4KB)
FILE_COMMAND_MAX_SIZE = 4 * 1024


async def file_command(
    message: Message,
    command: CommandObject,
    config: TelegramConfig,
) -> None:
    """Handle /file <path> command to create a file from inline message content.

    Creates a new file at the specified path with content from the message.
    The content follows the path on the same line or subsequent lines.
    Limited to 4KB to prevent abuse and ensure responsive handling.

    Args:
        message: Incoming Telegram message with path and content
        command: Parsed command with path and content arguments
        config: TelegramConfig with registered projects

    Usage:
        /file src/config.py           - Creates file with content from following lines
        CONTENT_HERE

        /file README.md # My Project  - Single line content after path
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Parse arguments: first word is path, rest is content
    args = command.args if command.args else ""

    if not args.strip():
        await message.answer(
            "Usage: `/file <path>`\n"
            "Content on same line or following lines\\.\n\n"
            "Examples:\n"
            "• `/file notes.txt Quick note here`\n"
            "• `/file src/config.py`\n"
            '  `key = "value"`'
        )
        return

    # Split into path and inline content
    # Path is the first whitespace-separated token
    parts = args.split(None, 1)
    path_arg = parts[0]
    inline_content = parts[1] if len(parts) > 1 else ""

    # Validate path argument
    if not path_arg:
        await message.answer("Path cannot be empty.")
        return

    # Reject obvious path traversal in argument
    if ".." in path_arg:
        await message.answer("Path cannot contain `..` path traversal.")
        return

    # Validate destination path using existing security infrastructure
    try:
        resolved_path = validate_push_path(path_arg, config)
    except TelegramError as e:
        await message.answer(f"Error: `{_escape_markdown(str(e))}`")
        return

    # Determine content: inline content or empty for now
    content = inline_content

    # Check content size limit (4KB)
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > FILE_COMMAND_MAX_SIZE:
        size_kb = len(content_bytes) / 1024
        await message.answer(
            f"Content too large ({size_kb:.1f}KB).\n"
            f"Maximum size is {FILE_COMMAND_MAX_SIZE // 1024}KB.\n\n"
            "For larger files, use `/push` with a document attachment."
        )
        return

    # Check if file already exists (warn user)
    file_exists = resolved_path.exists()

    # Ensure parent directory exists
    try:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        await message.answer(f"Failed to create directory: `{_escape_markdown(str(e))}`")
        return

    # Write file
    try:
        resolved_path.write_text(content, encoding="utf-8")
        logger.info(f"User {user_id} created file: {resolved_path}")

        # Build response message
        action = "Overwrote" if file_exists else "Created"

        size_info = f"{len(content_bytes)} bytes"
        await message.answer(f"{action}: `{_escape_markdown(str(resolved_path))}`\n({size_info})")

    except OSError as e:
        logger.exception(f"Failed to write file to {resolved_path}")
        await message.answer(f"Failed to write file: `{_escape_markdown(str(e))}`")


# Allowed file extensions for direct upload (common spec/config files)
_ALLOWED_UPLOAD_EXTENSIONS = frozenset(
    {
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".py",
        ".js",
        ".ts",
        ".sh",
        ".bash",
        ".zsh",
    }
)


async def ls_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    config: TelegramConfig,
) -> None:
    """Handle /ls [path] command to list directory contents.

    Lists files and directories with type indicators, sizes, and modified dates.
    Defaults to project root if no path specified.

    Args:
        message: Incoming Telegram message
        command: Parsed command with optional path argument
        state_store: StateStore for user context
        config: TelegramConfig with registered projects

    Usage:
        /ls              - List project root
        /ls src          - List src directory
        /ls --all        - Include hidden files
        /ls src --all    - List src with hidden files
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Get user's current project context
    context = await state_store.get_context(user_id)
    if not context or not context.current_project:
        await message.answer("No project selected. Use `/use <project>` first.")
        return

    project = config.get_project(context.current_project)
    if project is None:
        await message.answer(f"Project `{_escape_markdown(context.current_project)}` not found.")
        return

    # Parse arguments
    args = command.args.strip() if command.args else ""
    parts = args.split()

    show_hidden = False
    path_arg = ""

    for part in parts:
        if part in ("--all", "-a"):
            show_hidden = True
        elif not path_arg:  # First non-flag argument is the path
            path_arg = part

    # Resolve path relative to project root
    project_root = project.path.resolve()
    target_path = project_root / path_arg if path_arg else project_root

    # Resolve and validate path is within project
    try:
        target_path = target_path.resolve()
    except OSError as e:
        await message.answer(f"Invalid path: `{_escape_markdown(str(e))}`")
        return

    # Security: ensure path is within project boundary
    try:
        target_path.relative_to(project_root)
    except ValueError:
        await message.answer("Error: Path is outside project directory.")
        return

    # Check path exists
    if not target_path.exists():
        await message.answer(f"Path not found: `{_escape_markdown(path_arg or '.')}`")
        return

    # Check it's a directory
    if not target_path.is_dir():
        await message.answer(f"Not a directory: `{_escape_markdown(path_arg)}`")
        return

    # List directory contents
    try:
        entries = list(target_path.iterdir())
    except PermissionError:
        await message.answer(f"Permission denied: `{_escape_markdown(path_arg or '.')}`")
        return
    except OSError as e:
        await message.answer(f"Error reading directory: `{_escape_markdown(str(e))}`")
        return

    # Filter hidden files unless --all
    if not show_hidden:
        entries = [e for e in entries if not e.name.startswith(".")]

    # Sort: directories first, then files, alphabetically
    entries.sort(key=lambda e: (not e.is_dir(), e.name.lower()))

    if not entries:
        if show_hidden:
            await message.answer("Directory is empty.")
        else:
            await message.answer("Directory is empty (use `--all` to show hidden files).")
        return

    # Format output
    lines: list[str] = []

    # Header with path
    try:
        display_path = target_path.relative_to(project_root)
        display_path_str = "/" if str(display_path) == "." else "/" + str(display_path)
    except ValueError:
        display_path_str = str(target_path)

    lines.append(
        f"*{_escape_markdown(context.current_project)}*`{_escape_markdown(display_path_str)}`"
    )
    lines.append("")

    # Format each entry: type indicator, size, date, name
    for entry in entries:
        try:
            stat = entry.stat()
            is_dir = entry.is_dir()

            # Type indicator
            if is_dir:
                type_indicator = "📁"
            elif entry.is_symlink():
                type_indicator = "🔗"
            else:
                type_indicator = "📄"

            # Size (only for files)
            if is_dir:
                size_str = "     "  # 5 spaces for alignment
            else:
                size = stat.st_size
                if size < 1024:
                    size_str = f"{size:>4}B"
                elif size < 1024 * 1024:
                    size_str = f"{size // 1024:>3}KB"
                elif size < 1024 * 1024 * 1024:
                    size_str = f"{size // (1024 * 1024):>3}MB"
                else:
                    size_str = f"{size // (1024 * 1024 * 1024):>3}GB"

            # Modified date
            from datetime import datetime

            mtime = datetime.fromtimestamp(stat.st_mtime)
            date_str = mtime.strftime("%b %d %H:%M")

            # Name (truncate if too long)
            name = entry.name
            if is_dir:
                name += "/"
            if len(name) > 35:
                name = name[:32] + "..."

            # Escape markdown in name
            name_escaped = _escape_markdown(name)

            lines.append(f"{type_indicator} `{size_str}` {date_str} {name_escaped}")

        except (OSError, PermissionError):
            # Skip entries we can't stat
            name_escaped = _escape_markdown(entry.name)
            lines.append(f"❓ `     ` ------------ {name_escaped}")

    # Add summary
    dir_count = sum(1 for e in entries if e.is_dir())
    file_count = len(entries) - dir_count
    lines.append("")
    summary_parts = []
    if dir_count > 0:
        summary_parts.append(f"{dir_count} dir{'s' if dir_count != 1 else ''}")
    if file_count > 0:
        summary_parts.append(f"{file_count} file{'s' if file_count != 1 else ''}")
    lines.append(f"_{', '.join(summary_parts)}_")

    # Join and send
    output = "\n".join(lines)

    # Telegram message limit is 4096 chars; truncate if needed
    if len(output) > 4000:
        # Find a good truncation point
        truncated_lines = lines[:2]  # Keep header
        char_count = len("\n".join(truncated_lines))
        for line in lines[2:-2]:  # Skip header and footer
            if char_count + len(line) + 50 > 3900:
                truncated_lines.append("...")
                remaining = len(entries) - len(truncated_lines) + 3
                truncated_lines.append(f"_({remaining} more entries)_")
                break
            truncated_lines.append(line)
            char_count += len(line) + 1
        truncated_lines.extend(lines[-2:])  # Keep footer
        output = "\n".join(truncated_lines)

    await message.answer(output)


async def tree_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    config: TelegramConfig,
) -> None:
    """Handle /tree [path] [depth] command to show directory tree respecting .gitignore.

    Shows a tree-style directory listing that respects .gitignore patterns by using
    git ls-files to determine which files are tracked/unignored.

    Args:
        message: Incoming Telegram message
        command: Parsed command with optional path and depth arguments
        state_store: StateStore for user context
        config: TelegramConfig with registered projects

    Usage:
        /tree              - Show tree from project root (depth 3)
        /tree src          - Show tree from src directory
        /tree src 2        - Show tree from src with depth 2
        /tree 5            - Show tree from project root with depth 5
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Get user's current project context
    context = await state_store.get_context(user_id)
    if not context or not context.current_project:
        await message.answer("No project selected. Use `/use <project>` first.")
        return

    project = config.get_project(context.current_project)
    if project is None:
        await message.answer(f"Project `{_escape_markdown(context.current_project)}` not found.")
        return

    # Parse arguments: [path] [depth]
    args = command.args.strip() if command.args else ""
    parts = args.split()

    path_arg = ""
    depth = 3  # Default depth

    for part in parts:
        # Check if it's a number (depth)
        if part.isdigit():
            depth = int(part)
            # Validate depth range
            if depth < 1:
                await message.answer("Depth must be at least 1.")
                return
            if depth > 10:
                await message.answer("Depth cannot exceed 10 to prevent large outputs.")
                return
        elif not path_arg:
            # First non-numeric argument is the path
            path_arg = part

    # Resolve path relative to project root
    project_root = project.path.resolve()
    target_path = project_root / path_arg if path_arg else project_root

    # Resolve and validate path is within project
    try:
        target_path = target_path.resolve()
    except OSError as e:
        await message.answer(f"Invalid path: `{_escape_markdown(str(e))}`")
        return

    # Security: ensure path is within project boundary
    try:
        target_path.relative_to(project_root)
    except ValueError:
        await message.answer("Error: Path is outside project directory.")
        return

    # Check path exists
    if not target_path.exists():
        await message.answer(f"Path not found: `{_escape_markdown(path_arg or '.')}`")
        return

    # Check it's a directory
    if not target_path.is_dir():
        await message.answer(f"Not a directory: `{_escape_markdown(path_arg)}`")
        return

    # Get list of files tracked by git (respects .gitignore)
    # Use git ls-files to get tracked files, plus git ls-files --others --exclude-standard
    # for untracked but not ignored files
    tracked_files: set[str] = set()
    try:
        # Get tracked files
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            tracked_files.update(f for f in result.stdout.strip().split("\n") if f)

        # Get untracked but not ignored files
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            tracked_files.update(f for f in result.stdout.strip().split("\n") if f)

    except subprocess.TimeoutExpired:
        await message.answer("Error: Git command timed out.")
        return
    except FileNotFoundError:
        await message.answer("Error: Git is not installed or not in PATH.")
        return
    except OSError as e:
        await message.answer(f"Error running git: `{_escape_markdown(str(e))}`")
        return

    # Filter files to those under target path
    try:
        rel_target = target_path.relative_to(project_root)
        rel_target_str = str(rel_target)
    except ValueError:
        rel_target_str = ""

    # Build directory tree structure from tracked files
    # Filter to files under target path
    if rel_target_str and rel_target_str != ".":
        prefix = rel_target_str + "/"
        filtered_files = [f for f in tracked_files if f.startswith(prefix) or f == rel_target_str]
        # Strip the prefix to make paths relative to target
        filtered_files = [f[len(prefix) :] if f.startswith(prefix) else f for f in filtered_files]
    else:
        filtered_files = list(tracked_files)

    if not filtered_files:
        # No tracked files - check if directory has any files at all
        try:
            any_files = any(target_path.iterdir())
        except PermissionError:
            any_files = False

        if any_files:
            await message.answer(
                "No tracked files in this directory (all files may be ignored by .gitignore)."
            )
        else:
            await message.answer("Directory is empty.")
        return

    # Build tree structure: dict of path -> set of immediate children
    tree: dict[str, set[str]] = {"": set()}

    for file_path in filtered_files:
        parts_list = Path(file_path).parts
        current = ""
        for i, part in enumerate(parts_list):
            # Check depth limit (depth is 1-based, so depth=1 means only show immediate children)
            if i >= depth:
                break
            if current not in tree:
                tree[current] = set()
            tree[current].add(part)
            current = str(Path(current) / part) if current else part
            if current not in tree:
                tree[current] = set()

    # Render tree with box-drawing characters
    lines: list[str] = []

    # Header
    try:
        display_path = target_path.relative_to(project_root)
        display_path_str = str(display_path) if str(display_path) != "." else ""
    except ValueError:
        display_path_str = str(target_path)

    if display_path_str:
        lines.append(
            f"*{_escape_markdown(context.current_project)}*`/{_escape_markdown(display_path_str)}/`"
        )
    else:
        lines.append(f"*{_escape_markdown(context.current_project)}*`/`")
    lines.append("")

    def render_tree(path: str, prefix: str = "") -> None:
        """Recursively render tree with box-drawing characters."""
        if path not in tree:
            return

        children = sorted(tree[path])
        for i, child in enumerate(children):
            is_last = i == len(children) - 1
            connector = "└── " if is_last else "├── "
            child_path = str(Path(path) / child) if path else child

            # Determine if this is a directory (has children in tree)
            is_dir = child_path in tree and len(tree[child_path]) > 0

            # Add type indicator
            indicator = "📁 " if is_dir else "📄 "

            # Escape markdown in name
            name_escaped = _escape_markdown(child + ("/" if is_dir else ""))

            lines.append(f"`{prefix}{connector}`{indicator}{name_escaped}")

            # Recurse for directories
            if is_dir:
                # Calculate new prefix for children
                new_prefix = prefix + ("    " if is_last else "│   ")
                render_tree(child_path, new_prefix)

    render_tree("")

    # Count files and directories
    file_count = 0
    dir_count = 0
    for path, children in tree.items():
        for child in children:
            child_path = str(Path(path) / child) if path else child
            if child_path in tree and len(tree[child_path]) > 0:
                dir_count += 1
            else:
                file_count += 1

    lines.append("")
    summary_parts = []
    if dir_count > 0:
        summary_parts.append(f"{dir_count} dir{'s' if dir_count != 1 else ''}")
    if file_count > 0:
        summary_parts.append(f"{file_count} file{'s' if file_count != 1 else ''}")
    if depth < 10:
        summary_parts.append(f"depth {depth}")
    lines.append(f"_{', '.join(summary_parts)}_")

    # Join and send
    output = "\n".join(lines)

    # Telegram message limit is 4096 chars; truncate if needed
    if len(output) > 4000:
        # Find a good truncation point
        truncated_lines = lines[:2]  # Keep header
        char_count = len("\n".join(truncated_lines))
        for entry_count, line in enumerate(lines[2:-2]):  # Skip header and footer
            if char_count + len(line) + 50 > 3900:
                truncated_lines.append("...")
                remaining = len(lines) - 4 - entry_count  # Approximate remaining entries
                truncated_lines.append(f"_({remaining} more entries, try reducing depth)_")
                break
            truncated_lines.append(line)
            char_count += len(line) + 1
        truncated_lines.extend(lines[-2:])  # Keep footer
        output = "\n".join(truncated_lines)

    await message.answer(output)


async def find_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    config: TelegramConfig,
) -> None:
    """Handle /find <pattern> command to find files matching a glob pattern.

    Finds files in the project directory that match the given glob pattern,
    respecting .gitignore rules. Results are limited to 50 files to prevent
    message overflow.

    Args:
        message: Incoming Telegram message
        command: Parsed command with glob pattern argument
        state_store: StateStore for user context
        config: TelegramConfig with registered projects

    Usage:
        /find *.py           - Find all Python files
        /find test_*.py      - Find test files
        /find src/**/*.ts    - Find TypeScript files in src (recursive)
        /find README*        - Find README files
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Get user's current project context
    context = await state_store.get_context(user_id)
    if not context or not context.current_project:
        await message.answer("No project selected. Use `/use <project>` first.")
        return

    project = config.get_project(context.current_project)
    if project is None:
        await message.answer(f"Project `{_escape_markdown(context.current_project)}` not found.")
        return

    # Parse pattern argument
    pattern = command.args.strip() if command.args else ""

    if not pattern:
        await message.answer(
            "Usage: `/find <pattern>`\n\n"
            "Examples:\n"
            "• `/find *.py` - All Python files\n"
            "• `/find test_*` - Files starting with test\\_\n"
            "• `/find **/*.md` - Markdown files recursively"
        )
        return

    # Validate pattern: reject obviously malicious or problematic patterns
    if len(pattern) > 200:
        await message.answer("Pattern too long (max 200 characters).")
        return

    # Reject patterns with path traversal attempts
    if ".." in pattern:
        await message.answer("Pattern cannot contain `..` path traversal.")
        return

    project_root = project.path.resolve()

    # Get list of files tracked by git (respects .gitignore)
    # Use git ls-files for tracked files, plus --others --exclude-standard
    # for untracked but not ignored files
    tracked_files: set[str] = set()
    try:
        # Get tracked files
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            tracked_files.update(f for f in result.stdout.strip().split("\n") if f)

        # Get untracked but not ignored files
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            tracked_files.update(f for f in result.stdout.strip().split("\n") if f)

    except subprocess.TimeoutExpired:
        await message.answer("Error: Git command timed out.")
        return
    except FileNotFoundError:
        await message.answer("Error: Git is not installed or not in PATH.")
        return
    except OSError as e:
        await message.answer(f"Error running git: `{_escape_markdown(str(e))}`")
        return

    if not tracked_files:
        await message.answer("No files found in project (is it a git repository?).")
        return

    # Match files against pattern
    # Handle ** patterns specially for recursive matching
    matches: list[str] = []
    max_results = 50

    for file_path in sorted(tracked_files):
        # Check if pattern matches
        # For patterns starting with **/, match anywhere in the path
        if pattern.startswith("**/"):
            # Match against filename or full path
            sub_pattern = pattern[3:]  # Remove **/
            if fnmatch.fnmatch(Path(file_path).name, sub_pattern) or fnmatch.fnmatch(
                file_path, pattern
            ):
                matches.append(file_path)
        elif "**" in pattern:
            # For patterns with ** in the middle, use fnmatch on full path
            if fnmatch.fnmatch(file_path, pattern):
                matches.append(file_path)
        else:
            # Simple pattern: match against filename only
            if fnmatch.fnmatch(Path(file_path).name, pattern):
                matches.append(file_path)

        # Stop if we've found enough matches
        if len(matches) >= max_results:
            break

    if not matches:
        await message.answer(f"No files matching `{_escape_markdown(pattern)}` found.")
        return

    # Format output
    lines: list[str] = []

    # Header
    project_name = _escape_markdown(context.current_project)
    pattern_escaped = _escape_markdown(pattern)
    lines.append(f"*{project_name}* — find `{pattern_escaped}`")
    lines.append("")

    # List files
    for file_path in matches:
        lines.append(f"• `{_escape_markdown(file_path)}`")

    # Summary
    lines.append("")
    if len(matches) >= max_results:
        lines.append(f"_Showing first {max_results} matches (limit reached)_")
    else:
        lines.append(f"_{len(matches)} file{'s' if len(matches) != 1 else ''} found_")

    # Join and send
    output = "\n".join(lines)

    # Telegram message limit is 4096 chars; truncate if needed
    if len(output) > 4000:
        # Find a good truncation point
        truncated_lines = lines[:2]  # Keep header
        char_count = len("\n".join(truncated_lines))
        for line in lines[2:-2]:  # Skip header and footer
            if char_count + len(line) + 50 > 3900:
                truncated_lines.append("...")
                remaining = len(matches) - len(truncated_lines) + 3
                truncated_lines.append(f"_({remaining} more matches)_")
                break
            truncated_lines.append(line)
            char_count += len(line) + 1
        truncated_lines.extend(lines[-2:])  # Keep footer
        output = "\n".join(truncated_lines)

    await message.answer(output)


async def grep_command(
    message: Message,
    command: CommandObject,
    state_store: StateStore,
    config: TelegramConfig,
) -> None:
    """Handle /grep <pattern> [path] command to search file contents with regex.

    Searches file contents in the project directory using a regex pattern,
    respecting .gitignore rules. Results are limited to 50 matches to prevent
    message overflow.

    Args:
        message: Incoming Telegram message
        command: Parsed command with pattern and optional path arguments
        state_store: StateStore for user context
        config: TelegramConfig with registered projects

    Usage:
        /grep TODO               - Find TODO in all files
        /grep "def .*test"       - Find function definitions with 'test'
        /grep error src/         - Search only in src directory
        /grep "import.*json"     - Find JSON import statements
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Get user's current project context
    context = await state_store.get_context(user_id)
    if not context or not context.current_project:
        await message.answer("No project selected. Use `/use <project>` first.")
        return

    project = config.get_project(context.current_project)
    if project is None:
        await message.answer(f"Project `{_escape_markdown(context.current_project)}` not found.")
        return

    # Parse arguments: pattern [path]
    args = command.args.strip() if command.args else ""

    if not args:
        await message.answer(
            "Usage: `/grep <pattern> [path]`\n\n"
            "Examples:\n"
            "• `/grep TODO` - Find TODO in all files\n"
            '• `/grep "def .*test"` - Find test functions\n'
            "• `/grep error src/` - Search in src directory"
        )
        return

    # Parse pattern and optional path from args
    # Support quoted patterns: /grep "pattern with spaces" path
    pattern: str
    search_path: str | None = None

    if args.startswith('"'):
        # Quoted pattern
        end_quote = args.find('"', 1)
        if end_quote == -1:
            await message.answer("Unclosed quote in pattern.")
            return
        pattern = args[1:end_quote]
        remaining = args[end_quote + 1 :].strip()
        if remaining:
            search_path = remaining
    elif args.startswith("'"):
        # Single-quoted pattern
        end_quote = args.find("'", 1)
        if end_quote == -1:
            await message.answer("Unclosed quote in pattern.")
            return
        pattern = args[1:end_quote]
        remaining = args[end_quote + 1 :].strip()
        if remaining:
            search_path = remaining
    else:
        # Unquoted: first word is pattern, rest is path
        parts = args.split(None, 1)
        pattern = parts[0]
        if len(parts) > 1:
            search_path = parts[1]

    if not pattern:
        await message.answer("Pattern cannot be empty.")
        return

    # Validate pattern length
    if len(pattern) > 500:
        await message.answer("Pattern too long (max 500 characters).")
        return

    # Validate regex pattern
    try:
        regex = re.compile(pattern)
    except re.error as e:
        await message.answer(f"Invalid regex pattern: `{_escape_markdown(str(e))}`")
        return

    # Validate search path if provided
    project_root = project.path.resolve()

    if search_path:
        # Reject path traversal attempts
        if ".." in search_path:
            await message.answer("Path cannot contain `..` path traversal.")
            return

        search_dir = project_root / search_path
        try:
            search_dir = search_dir.resolve()
        except OSError as e:
            await message.answer(f"Invalid path: `{_escape_markdown(str(e))}`")
            return

        # Ensure search path is within project
        try:
            search_dir.relative_to(project_root)
        except ValueError:
            await message.answer("Path must be within project directory.")
            return

        if not search_dir.exists():
            await message.answer(f"Path not found: `{_escape_markdown(search_path)}`")
            return

    # Get list of files tracked by git (respects .gitignore)
    tracked_files: set[str] = set()
    try:
        # Get tracked files
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            tracked_files.update(f for f in result.stdout.strip().split("\n") if f)

        # Get untracked but not ignored files
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            tracked_files.update(f for f in result.stdout.strip().split("\n") if f)

    except subprocess.TimeoutExpired:
        await message.answer("Error: Git command timed out.")
        return
    except FileNotFoundError:
        await message.answer("Error: Git is not installed or not in PATH.")
        return
    except OSError as e:
        await message.answer(f"Error running git: `{_escape_markdown(str(e))}`")
        return

    if not tracked_files:
        await message.answer("No files found in project (is it a git repository?).")
        return

    # Filter files by search path if provided
    if search_path:
        # Normalize search path for comparison
        search_prefix = search_path.rstrip("/") + "/"
        if not search_path.endswith("/"):
            # Could be a file or directory prefix
            tracked_files = {
                f
                for f in tracked_files
                if f.startswith(search_prefix) or f == search_path or f.startswith(search_path)
            }
        else:
            tracked_files = {f for f in tracked_files if f.startswith(search_prefix)}

    # Search files for pattern matches
    @dataclass
    class GrepMatch:
        """A single grep match result."""

        file_path: str
        line_num: int
        line_content: str

    matches: list[GrepMatch] = []
    max_results = 50
    files_searched = 0
    files_with_matches = 0

    for file_path in sorted(tracked_files):
        if len(matches) >= max_results:
            break

        full_path = project_root / file_path

        # Skip binary files
        if not is_text_file(full_path):
            continue

        # Skip if file doesn't exist (could be deleted but still in git)
        if not full_path.is_file():
            continue

        files_searched += 1
        file_has_match = False

        try:
            # Read file with error handling for encoding issues
            content = full_path.read_text(encoding="utf-8", errors="replace")

            for line_num, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    if not file_has_match:
                        file_has_match = True
                        files_with_matches += 1

                    # Truncate long lines
                    line_display = line.strip()
                    if len(line_display) > 100:
                        line_display = line_display[:97] + "..."

                    matches.append(
                        GrepMatch(
                            file_path=file_path,
                            line_num=line_num,
                            line_content=line_display,
                        )
                    )

                    if len(matches) >= max_results:
                        break

        except OSError:
            # Skip files that can't be read
            continue

    if not matches:
        pattern_escaped = _escape_markdown(pattern)
        if search_path:
            path_escaped = _escape_markdown(search_path)
            await message.answer(
                f"No matches for `{pattern_escaped}` in `{path_escaped}`.\n"
                f"_Searched {files_searched} file{'s' if files_searched != 1 else ''}_"
            )
        else:
            await message.answer(
                f"No matches for `{pattern_escaped}`.\n"
                f"_Searched {files_searched} file{'s' if files_searched != 1 else ''}_"
            )
        return

    # Format output
    lines: list[str] = []

    # Header
    project_name = _escape_markdown(context.current_project)
    pattern_escaped = _escape_markdown(pattern)
    if search_path:
        path_escaped = _escape_markdown(search_path)
        lines.append(f"*{project_name}* — grep `{pattern_escaped}` in `{path_escaped}`")
    else:
        lines.append(f"*{project_name}* — grep `{pattern_escaped}`")
    lines.append("")

    # Group matches by file
    current_file: str | None = None
    for match in matches:
        if match.file_path != current_file:
            if current_file is not None:
                lines.append("")  # Blank line between files
            current_file = match.file_path
            lines.append(f"*{_escape_markdown(match.file_path)}*")

        # Format: line_num: content
        line_escaped = _escape_markdown(match.line_content)
        lines.append(f"  {match.line_num}: `{line_escaped}`")

    # Summary
    lines.append("")
    if len(matches) >= max_results:
        lines.append(f"_Showing first {max_results} matches (limit reached)_")
    else:
        lines.append(
            f"_{len(matches)} match{'es' if len(matches) != 1 else ''} "
            f"in {files_with_matches} file{'s' if files_with_matches != 1 else ''}_"
        )

    # Join and send
    output = "\n".join(lines)

    # Telegram message limit is 4096 chars; truncate if needed
    if len(output) > 4000:
        # Find a good truncation point
        truncated_lines = lines[:3]  # Keep header
        char_count = len("\n".join(truncated_lines))
        for line in lines[3:-2]:  # Skip header and footer
            if char_count + len(line) + 50 > 3900:
                truncated_lines.append("...")
                remaining = len(matches) - sum(1 for ln in truncated_lines if ln.startswith("  "))
                truncated_lines.append(f"_({remaining} more matches)_")
                break
            truncated_lines.append(line)
            char_count += len(line) + 1
        truncated_lines.extend(lines[-2:])  # Keep footer
        output = "\n".join(truncated_lines)

    await message.answer(output)


async def document_handler(
    message: Message,
    state_store: StateStore,
    config: TelegramConfig,
    bot: Bot,
) -> None:
    """Handle document messages for automatic file uploads.

    When a user sends a document (not as a reply to /push), this handler
    downloads it to the project's uploads directory with conflict resolution.

    Files are saved to: .weld/telegram/uploads/<sanitized_filename>
    If a file with the same name exists, creates spec.1.md, spec.2.md, etc.

    Args:
        message: Incoming Telegram message with document attachment
        state_store: StateStore instance for user context lookup
        config: TelegramConfig with registered projects
        bot: Bot instance for downloading files

    Failure modes handled:
        - Large file handling (>50MB): Rejected with error message
        - Invalid file extensions: Only allowed extensions accepted
        - Filename sanitization: Dangerous characters removed
        - Concurrent uploads with same name: Numeric suffix added
    """
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        await message.answer("Unable to identify user.")
        return

    # Ignore if this is a reply (likely handled by /push command)
    if message.reply_to_message:
        return

    # Must have a document
    if not message.document:
        return

    document = message.document

    # Check file size limit
    file_size = document.file_size or 0
    if file_size > TELEGRAM_MAX_DOWNLOAD_SIZE:
        await message.answer(
            f"File too large ({file_size / 1024 / 1024:.1f}MB).\nMaximum upload size is 50MB."
        )
        return

    # Get and sanitize filename
    original_filename = document.file_name or "unnamed_file"
    sanitized = sanitize_filename(original_filename)

    # Check file extension
    suffix = Path(sanitized).suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_EXTENSIONS:
        allowed_list = ", ".join(sorted(_ALLOWED_UPLOAD_EXTENSIONS)[:10])
        await message.answer(
            f"File type `{_escape_markdown(suffix or 'none')}` not allowed for direct upload.\n\n"
            f"Allowed types: {allowed_list}, ...\n\n"
            "Use `/push <path>` to upload to a specific location."
        )
        return

    # Get user's current project context
    context = await state_store.get_context(user_id)
    if not context or not context.current_project:
        await message.answer(
            "No project selected.\n\n"
            "Use `/use <project>` to select a project first, then send files."
        )
        return

    project = config.get_project(context.current_project)
    if project is None:
        await message.answer(
            f"Project `{_escape_markdown(context.current_project)}` not found in config.\n\n"
            "Use `/use <project>` to select a valid project."
        )
        return

    # Get uploads directory for the project
    uploads_dir = get_uploads_dir(project.path)

    # Resolve filename conflicts
    target_path = resolve_upload_filename(uploads_dir, sanitized)

    # Download file from Telegram
    try:
        file = await bot.get_file(document.file_id)
        if not file.file_path:
            await message.answer("Failed to get file path from Telegram.")
            return

        file_bytes = await bot.download_file(file.file_path)
        if file_bytes is None:
            await message.answer("Failed to download file from Telegram.")
            return

        content = file_bytes.read()
    except Exception as e:
        logger.exception("Failed to download file from Telegram")
        await message.answer(f"Failed to download file: `{_escape_markdown(str(e))}`")
        return

    # Write file to uploads directory
    try:
        target_path.write_bytes(content)
        logger.info(f"User {user_id} uploaded file to: {target_path}")

        # Show relative path from project root for cleaner display
        try:
            relative_path = target_path.relative_to(project.path)
        except ValueError:
            relative_path = target_path

        # Indicate if filename was modified
        final_filename = target_path.name
        if final_filename != original_filename:
            await message.answer(
                f"Saved: `{_escape_markdown(str(relative_path))}`\n"
                f"(original: `{_escape_markdown(original_filename)}`)"
            )
        else:
            await message.answer(f"Saved: `{_escape_markdown(str(relative_path))}`")

    except OSError as e:
        logger.exception(f"Failed to write uploaded file to {target_path}")
        await message.answer(f"Failed to save file: `{_escape_markdown(str(e))}`")


# Maximum output buffer size for status display (preserve last N bytes)
MAX_OUTPUT_BUFFER = 3000


async def run_consumer(
    run: Run,
    chat_id: int,
    editor: MessageEditor,
    cwd: Path,
    state_store: StateStore,
    bot: Bot,
) -> None:
    """Consume runner output stream and update status message in real-time.

    Reads output chunks from execute_run and uses MessageEditor to update
    a status message with progress. The message shows the run status and
    a tail of the most recent output. Handles interactive prompts by showing
    inline keyboard buttons.

    Args:
        run: The Run object with command details (must have id set)
        chat_id: Telegram chat ID to send/edit status messages in
        editor: MessageEditor instance for rate-limited message updates
        cwd: Working directory for command execution
        state_store: StateStore for persisting run status updates
        bot: Bot instance for sending messages with inline keyboards

    Note:
        - Output is buffered to the last MAX_OUTPUT_BUFFER bytes to avoid
          hitting Telegram's message size limit
        - MessageEditor handles rate limiting (2s minimum between edits)
        - If output arrives faster than edits can be made, intermediate
          chunks are accumulated and shown in the next edit
        - Interactive prompts are shown with inline keyboard buttons
    """
    if run.id is None:
        logger.error("run_consumer called with run that has no id")
        return

    run_id = run.id
    output_buffer = ""

    # Initialize output buffer for tail command access
    _run_output_buffers[run_id] = ""

    # Mark run as running
    run.status = "running"
    run.started_at = datetime.now(UTC)
    try:
        await state_store.update_run(run)
    except Exception:
        logger.exception(f"Failed to update run {run_id} to running status")

    # Send initial status message
    initial_status = format_status(run)
    try:
        await editor.send_or_edit(chat_id, initial_status)
    except Exception:
        logger.exception(f"Failed to send initial status for run {run_id}")

    # Parse command to get weld subcommand and args
    # run.command is like "weld doctor" or "weld plan --dry-run"
    parts = run.command.split()
    if len(parts) < 2 or parts[0] != "weld":
        logger.error(f"Run {run_id}: Invalid command format: {run.command}")
        run.status = "failed"
        run.completed_at = datetime.now(UTC)
        run.error = "Invalid command format"
        try:
            await state_store.update_run(run)
            await editor.send_or_edit(chat_id, format_status(run))
        except Exception:
            logger.exception(f"Failed to update run {run_id} status")
        return

    weld_subcommand = parts[1]
    weld_args = parts[2:] if len(parts) > 2 else None

    # Track prompt message for final update
    prompt_message_id: int | None = None

    try:
        async for chunk_type, data in execute_run(
            run_id=run_id,
            command=weld_subcommand,
            args=weld_args,
            cwd=cwd,
        ):
            # Handle interactive prompts
            if chunk_type == "prompt":
                logger.info(f"Run {run_id}: Showing prompt to user")
                # Detect the prompt options
                prompt_info = detect_prompt(data)
                if prompt_info:
                    # Show prompt with inline keyboard based on prompt type
                    keyboard = create_prompt_keyboard(
                        run_id,
                        prompt_info.options,
                        prompt_info.prompt_type,
                        prompt_text=data,
                    )
                    prompt_message = (
                        f"*Run #{run_id} needs input:*\n\n"
                        f"```\n{data[-500:] if len(data) > 500 else data}\n```\n\n"
                        "Select an option:"
                    )
                    try:
                        msg = await bot.send_message(chat_id, prompt_message, reply_markup=keyboard)
                        prompt_message_id = msg.message_id
                    except Exception:
                        logger.exception(f"Failed to send prompt for run {run_id}")
                continue

            # Accumulate output (stdout and stderr combined)
            output_buffer += data

            # Truncate buffer to keep only recent output
            if len(output_buffer) > MAX_OUTPUT_BUFFER:
                # Keep only the last MAX_OUTPUT_BUFFER chars, starting at a newline if possible
                truncated = output_buffer[-MAX_OUTPUT_BUFFER:]
                newline_pos = truncated.find("\n")
                if newline_pos > 0 and newline_pos < 200:
                    truncated = truncated[newline_pos + 1 :]
                output_buffer = "..." + truncated

            # Update run with current output
            run.result = output_buffer

            # Update shared buffer for tail command access
            _run_output_buffers[run_id] = output_buffer

            # Format and chunk the status message to fit Telegram limits
            status_text = format_status(run)
            chunked_text = format_chunk(status_text)

            try:
                await editor.send_or_edit(chat_id, chunked_text)
            except Exception:
                # Log but don't fail the run if we can't update status
                logger.warning(f"Failed to update status message for run {run_id}")

        # Run completed successfully
        run.status = "completed"
        run.completed_at = datetime.now(UTC)
        logger.info(f"Run {run_id} completed successfully")

    except Exception as e:
        # Run failed
        run.status = "failed"
        run.completed_at = datetime.now(UTC)
        run.error = str(e)
        logger.exception(f"Run {run_id} failed: {e}")

    # Persist final status
    try:
        await state_store.update_run(run)
    except Exception:
        logger.exception(f"Failed to persist final status for run {run_id}")

    # Send final status update
    final_status = format_status(run)
    final_chunked = format_chunk(final_status)
    try:
        await editor.send_or_edit(chat_id, final_chunked)
    except Exception:
        logger.exception(f"Failed to send final status for run {run_id}")

    # On successful completion, check for output files and offer Download button
    if run.status == "completed" and run.result:
        output_files = detect_output_files(run.result, cwd)
        if output_files:
            # Use only the first output file (most common case is single output)
            # Multiple files scenario: could extend to multiple buttons in future
            output_file = output_files[0]

            # Security: verify file is within project directory
            try:
                output_file.relative_to(cwd.resolve())
            except ValueError:
                logger.warning(f"Output file outside project boundary: {output_file}")
            else:
                # Create Download button
                keyboard = create_download_keyboard(str(output_file), cwd)
                if keyboard is not None:
                    try:
                        # Get relative path for display
                        try:
                            display_path = output_file.relative_to(cwd)
                        except ValueError:
                            display_path = output_file

                        await bot.send_message(
                            chat_id=chat_id,
                            text=f"📄 Output: `{_escape_markdown(str(display_path))}`",
                            reply_markup=keyboard,
                        )
                        logger.info(f"Run {run_id}: offered download for {output_file}")
                    except Exception:
                        logger.warning(f"Failed to send download button for run {run_id}")

    # Update prompt message with final result (if one was shown)
    if prompt_message_id is not None:
        try:
            if run.status == "completed":
                # Extract key info from output for summary
                result_summary = ""
                if run.result:
                    # Look for commit summary or other success indicators
                    lines = run.result.split("\n")
                    for line in reversed(lines):
                        if "Created" in line and "commit" in line:
                            result_summary = line.strip()
                            break
                        if "Committed:" in line:
                            result_summary = line.strip()
                            break

                prompt_final = (
                    f"✅ *Run #{run_id} completed*\n\n"
                    f"{result_summary if result_summary else 'Command finished successfully.'}"
                )
            else:
                error_msg = run.error[:200] if run.error else "Unknown error"
                prompt_final = f"❌ *Run #{run_id} failed*\n\n`{error_msg}`"

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=prompt_message_id,
                text=prompt_final,
                parse_mode="Markdown",
            )
        except Exception:
            logger.warning(f"Failed to update prompt message for run {run_id}")

    # Clean up output buffer (tail tasks will see run completed via status check)
    _run_output_buffers.pop(run_id, None)
