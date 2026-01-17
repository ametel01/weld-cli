"""Telegram bot CLI commands."""

import asyncio
import logging
import tomllib

import typer
from pydantic import ValidationError

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
