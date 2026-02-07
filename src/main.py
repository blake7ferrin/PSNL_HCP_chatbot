"""Entry point: load config and start the Telegram bot."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (folder that contains run.py), so it works no matter where you run from
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


def get_application():
    """Build the Telegram Application (handlers in telegram.handlers)."""
    from telegram.ext import Application, MessageHandler, CommandHandler, filters

    from src.telegram.handlers import handle_message, handle_command, handle_whoami, handle_health

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", handle_command))
    app.add_handler(CommandHandler("help", handle_command))
    app.add_handler(CommandHandler("whoami", handle_whoami))
    app.add_handler(CommandHandler("health", handle_health))
    # ALL so we're always called; we ignore non-text inside handle_message
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    return app


def main() -> None:
    """Sync entry point: builds app and runs polling (run_polling manages the event loop)."""
    app = get_application()
    print("Polar Air HCP bot started. (Ctrl+C to stop)", flush=True)
    app.run_polling(drop_pending_updates=True)
