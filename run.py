"""Launch the Polar Air HCP Telegram bot.

Secrets from: Doppler (doppler run -- py run.py) or .env in the project folder.
Set DEBUG=1 for full request/response and LLM logging.
"""
import logging
import os
from pathlib import Path

# If not already set (e.g. by Doppler), load .env from project folder
if not os.getenv("TELEGRAM_BOT_TOKEN"):
    from dotenv import load_dotenv
    _script_dir = Path(__file__).resolve().parent
    _cwd = Path.cwd()
    load_dotenv(_script_dir / ".env")
    load_dotenv(_cwd / ".env")

if not os.getenv("TELEGRAM_BOT_TOKEN"):
    print("TELEGRAM_BOT_TOKEN not set.")
    print("Use Doppler: doppler run -- py run.py")
    print("Or add a .env file with TELEGRAM_BOT_TOKEN=... and HCP_API_KEY=...")
    raise SystemExit(1)

# Full debug when DEBUG=1 (intent, HCP, LLM, response path)
_debug = os.getenv("DEBUG", "").strip().lower() in ("1", "true", "yes")
if _debug:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

from src.main import get_application

if __name__ == "__main__":
    app = get_application()
    print("Polar Air HCP bot started. Listening for messages... (Ctrl+C to stop)", flush=True)
    if _debug:
        print("DEBUG=1: full logging enabled (intent, HCP, LLM).", flush=True)
    app.run_polling(drop_pending_updates=True)
