"""Telegram bot CLI commands."""

import asyncio
import contextlib
import logging
import tomllib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import typer
from pydantic import ValidationError

if TYPE_CHECKING:
    from weld.telegram.config import TelegramConfig

logger = logging.getLogger(__name__)

telegram_app = typer.Typer(
    help="Telegram bot for remote weld interaction",
    no_args_is_help=True,
)


def _check_telegram_deps() -> None:
    """Check if telegram dependencies are installed.

    Raises:
        typer.Exit: If aiogram is not installed.
    """
    try:
        import aiogram  # noqa: F401
    except ImportError:
        typer.echo(
            "Telegram dependencies not installed. Install with: pip install weld[telegram]",
            err=True,
        )
        raise typer.Exit(1) from None


@telegram_app.callback()
def telegram_callback() -> None:
    """Telegram bot commands for remote weld interaction."""
    pass


async def _validate_token(token: str) -> tuple[bool, str]:
    """Validate a Telegram bot token by calling Bot.get_me().

    Args:
        token: Telegram bot API token to validate.

    Returns:
        Tuple of (success, message). On success, message contains bot username.
        On failure, message contains error description.
    """
    from aiogram import Bot
    from aiogram.exceptions import TelegramUnauthorizedError

    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        return True, f"@{me.username}" if me.username else str(me.id)
    except TelegramUnauthorizedError:
        return False, "Invalid token: unauthorized"
    except Exception as e:
        # Network errors, timeouts, etc.
        return False, f"Could not validate token: {e}"
    finally:
        await bot.session.close()


@telegram_app.command()
def init(
    token: str | None = typer.Option(
        None,
        "--token",
        "-t",
        help="Telegram bot token from @BotFather. If not provided, will prompt interactively.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing configuration.",
    ),
) -> None:
    """Initialize Telegram bot configuration.

    Prompts for bot token, validates it with Telegram API, and saves
    configuration to ~/.config/weld/telegram.toml.

    Get a bot token from @BotFather on Telegram:
    https://core.telegram.org/bots#botfather
    """
    _check_telegram_deps()

    from weld.telegram.config import get_config_path, load_config, save_config

    config_path = get_config_path()

    # Check if config already exists
    if config_path.exists() and not force:
        try:
            existing_config = load_config(config_path)
            if existing_config.bot_token:
                typer.echo(f"Configuration already exists at {config_path}")
                typer.echo("Use --force to overwrite existing configuration.")
                raise typer.Exit(1)
        except (tomllib.TOMLDecodeError, ValidationError) as e:
            # Config file exists but is invalid (TOML parse error or validation error)
            # Allow overwriting in this case
            logger.debug(f"Existing config invalid, will overwrite: {e}")

    # Get token interactively if not provided
    if token is None:
        typer.echo("Get a bot token from @BotFather on Telegram.")
        typer.echo("https://core.telegram.org/bots#botfather")
        typer.echo()
        token = typer.prompt("Bot token")

    if not token or not token.strip():
        typer.echo("Error: Token cannot be empty.", err=True)
        raise typer.Exit(1)

    token = token.strip()

    # Basic format validation
    if ":" not in token:
        typer.echo("Error: Invalid token format (missing colon).", err=True)
        raise typer.Exit(1)

    # Validate token with Telegram API
    typer.echo("Validating token...")
    try:
        success, message = asyncio.run(_validate_token(token))
    except Exception as e:
        typer.echo(f"Error: Could not connect to Telegram API: {e}", err=True)
        typer.echo("Check your network connection and try again.")
        raise typer.Exit(1) from None

    if not success:
        typer.echo(f"Error: {message}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Token valid! Bot: {message}")

    # Load existing config or create new one
    try:
        config = load_config(config_path)
    except (tomllib.TOMLDecodeError, ValidationError):
        # Start fresh if existing config is invalid
        from weld.telegram.config import TelegramConfig

        config = TelegramConfig()

    # Update token
    config.bot_token = token

    # Save config
    try:
        saved_path = save_config(config, config_path)
        typer.echo(f"Configuration saved to {saved_path}")
        typer.echo()
        typer.echo("Next steps:")
        typer.echo("  1. Add allowed users with: weld telegram user add <user_id>")
        typer.echo("  2. Add projects with: weld telegram project add <name> <path>")
        typer.echo("  3. Start the bot with: weld telegram serve")
    except PermissionError:
        typer.echo(f"Error: Permission denied writing to {config_path}", err=True)
        raise typer.Exit(1) from None
    except OSError as e:
        typer.echo(f"Error: Could not save configuration: {e}", err=True)
        raise typer.Exit(1) from None


@telegram_app.command()
def serve() -> None:
    """Start the Telegram bot server in long-polling mode.

    Loads configuration from ~/.config/weld/telegram.toml and starts
    the bot with all command handlers registered. The bot will run
    until interrupted with Ctrl+C.

    Requires:
    - Valid bot token (run 'weld telegram init' first)
    - At least one allowed user configured
    """
    _check_telegram_deps()

    from weld.telegram.config import get_config_path, load_config

    config_path = get_config_path()

    # Load and validate configuration
    if not config_path.exists():
        typer.echo(f"Configuration not found at {config_path}", err=True)
        typer.echo("Run 'weld telegram init' first to configure the bot.")
        raise typer.Exit(1)

    try:
        config = load_config(config_path)
    except Exception as e:
        typer.echo(f"Error loading configuration: {e}", err=True)
        raise typer.Exit(1) from None

    if not config.bot_token:
        typer.echo("Bot token not configured.", err=True)
        typer.echo("Run 'weld telegram init' to set up the bot token.")
        raise typer.Exit(1)

    # Check for allowed users
    if not config.auth.allowed_user_ids and not config.auth.allowed_usernames:
        typer.echo("Warning: No allowed users configured.", err=True)
        typer.echo("Add users with: weld telegram user add <user_id>")
        typer.echo("The bot will reject all messages until users are allowed.")

    typer.echo("Starting Telegram bot...")
    typer.echo("Press Ctrl+C to stop.")

    try:
        asyncio.run(_run_bot(config))
    except KeyboardInterrupt:
        typer.echo("\nBot stopped.")


async def _run_bot(config: "TelegramConfig") -> None:
    """Run the bot with graceful shutdown handling.

    Args:
        config: Validated TelegramConfig with bot token.
    """
    from aiogram.filters import Command, CommandObject
    from aiogram.types import Message

    from weld.telegram.auth import check_auth
    from weld.telegram.bot import (
        cancel_command,
        commit_command,
        create_bot,
        doctor_command,
        fetch_command,
        implement_command,
        interview_command,
        plan_command,
        push_command,
        run_consumer,
        status_command,
        use_command,
    )
    from weld.telegram.errors import TelegramAuthError
    from weld.telegram.format import MessageEditor
    from weld.telegram.queue import QueueManager
    from weld.telegram.state import StateStore

    bot, dp = create_bot(config.bot_token)  # type: ignore[arg-type]

    # Initialize state store and queue manager
    state_store = StateStore()
    await state_store.init()

    queue_manager: QueueManager[int] = QueueManager()

    # Auth middleware - check user is allowed before processing any message
    @dp.message.outer_middleware()  # type: ignore[arg-type]
    async def auth_middleware(handler: Any, event: Message, data: dict[str, Any]) -> Any:
        """Middleware to check user authorization."""
        if event.from_user is None:
            return None  # Ignore messages without user info

        try:
            check_auth(
                user_id=event.from_user.id,
                config=config,
                username=event.from_user.username,
            )
        except TelegramAuthError:
            logger.warning(
                f"Unauthorized access attempt: user_id={event.from_user.id}, "
                f"username={event.from_user.username}"
            )
            # Silently ignore unauthorized users
            return None

        return await handler(event, data)

    # Register command handlers
    @dp.message(Command("start"))
    async def start_handler(message: Message) -> None:
        """Handle /start command."""
        await message.answer(
            "Welcome to Weld Bot!\n\n"
            "Commands:\n"
            "  /use <project> - Switch project context\n"
            "  /status - Show current run status\n"
            "  /cancel - Cancel running/pending commands\n"
            "  /doctor - Run environment check\n"
            "  /plan - Generate implementation plan\n"
            "  /interview - Interactive spec refinement\n"
            "  /implement - Execute plan steps\n"
            "  /commit - Create commits with transcripts\n"
            "  /fetch <path> - Download a file\n"
            "  /push <path> - Upload a file (reply to document)"
        )

    @dp.message(Command("help"))
    async def help_handler(message: Message) -> None:
        """Handle /help command."""
        await message.answer(
            "*Weld Bot Help*\n\n"
            "*Project Management:*\n"
            "  `/use` - Show current project\n"
            "  `/use <name>` - Switch to project\n\n"
            "*Run Management:*\n"
            "  `/status` - Show queue and run status\n"
            "  `/cancel` - Cancel active/pending runs\n\n"
            "*Weld Commands:*\n"
            "  `/doctor` - Check environment\n"
            "  `/plan [spec.md]` - Generate plan\n"
            "  `/interview [spec.md]` - Refine spec\n"
            "  `/implement <plan.md>` - Execute plan\n"
            "  `/commit [-m msg]` - Commit changes\n\n"
            "*File Transfer:*\n"
            "  `/fetch <path>` - Download file\n"
            "  `/push <path>` - Upload file (reply to doc)"
        )

    @dp.message(Command("use"))
    async def use_handler(message: Message, command: CommandObject) -> None:
        """Handle /use command."""
        await use_command(message, command, state_store, config)

    @dp.message(Command("status"))
    async def status_handler(message: Message) -> None:
        """Handle /status command."""
        await status_command(message, state_store, queue_manager)

    @dp.message(Command("cancel"))
    async def cancel_handler(message: Message) -> None:
        """Handle /cancel command."""
        await cancel_command(message, state_store, queue_manager)

    @dp.message(Command("doctor"))
    async def doctor_handler(message: Message, command: CommandObject) -> None:
        """Handle /doctor command."""
        await doctor_command(message, command, state_store, queue_manager)

    @dp.message(Command("plan"))
    async def plan_handler(message: Message, command: CommandObject) -> None:
        """Handle /plan command."""
        await plan_command(message, command, state_store, queue_manager)

    @dp.message(Command("interview"))
    async def interview_handler(message: Message, command: CommandObject) -> None:
        """Handle /interview command."""
        await interview_command(message, command, state_store, queue_manager)

    @dp.message(Command("implement"))
    async def implement_handler(message: Message, command: CommandObject) -> None:
        """Handle /implement command."""
        await implement_command(message, command, state_store, queue_manager)

    @dp.message(Command("commit"))
    async def commit_handler(message: Message, command: CommandObject) -> None:
        """Handle /commit command."""
        await commit_command(message, command, state_store, queue_manager)

    @dp.message(Command("fetch"))
    async def fetch_handler(message: Message, command: CommandObject) -> None:
        """Handle /fetch command."""
        await fetch_command(message, command, config, bot)

    @dp.message(Command("push"))
    async def push_handler(message: Message, command: CommandObject) -> None:
        """Handle /push command."""
        await push_command(message, command, config, bot)

    # Queue consumer task
    async def queue_consumer() -> None:
        """Background task to process queued runs."""
        while True:
            # Process all active chats
            for chat_id in list(queue_manager.active_chat_ids()):
                run_id = await queue_manager.dequeue(chat_id, timeout=0.1)
                if run_id is None:
                    continue

                # Load the run from state store
                run = await state_store.get_run(run_id)
                if run is None:
                    logger.warning(f"Run {run_id} not found in state store")
                    continue

                # Get project path for working directory
                project = config.get_project(run.project_name)
                if project is None:
                    logger.error(f"Project {run.project_name} not found for run {run_id}")
                    # Mark run as failed since we can't execute without a project
                    run.status = "failed"
                    run.completed_at = datetime.now(UTC)
                    run.error = f"Project '{run.project_name}' not found in configuration"
                    try:
                        await state_store.update_run(run)
                    except Exception:
                        logger.exception(f"Failed to update run {run_id} status to failed")
                    continue

                # Create message editor for status updates
                # Bot is compatible with TelegramBot protocol at runtime
                editor = MessageEditor(bot)  # type: ignore[arg-type]

                # Execute the run with exception handling
                try:
                    await run_consumer(run, chat_id, editor, project.path, state_store)
                except Exception:
                    logger.exception(f"Unhandled exception in run_consumer for run {run_id}")

            # Delay between iterations to prevent CPU spinning
            await asyncio.sleep(1.0)

    # Periodic cleanup task
    async def cleanup_task() -> None:
        """Periodically clean up inactive queues."""
        while True:
            await asyncio.sleep(3600)  # Run every hour
            await queue_manager.cleanup_inactive()

    # Start background tasks
    consumer_task = asyncio.create_task(queue_consumer())
    cleanup_task_handle = asyncio.create_task(cleanup_task())

    try:
        # Start polling
        logger.info("Starting bot polling")
        await dp.start_polling(bot)
    finally:
        # Graceful shutdown
        logger.info("Shutting down bot")
        consumer_task.cancel()
        cleanup_task_handle.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await consumer_task

        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task_handle

        await queue_manager.shutdown()
        await state_store.close()
        await bot.session.close()
