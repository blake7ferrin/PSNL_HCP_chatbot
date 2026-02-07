"""Optional quick reply keyboards for Telegram."""
from telegram import KeyboardButton, ReplyKeyboardMarkup

# Example quick queries for unknown intent or after help
DEFAULT_QUICK_QUERIES = [
    "Jobs today",
    "Next week",
    "List estimates",
]


def build_quick_reply_keyboard(choices: list[str] | None = None) -> ReplyKeyboardMarkup:
    """Build a one-time reply keyboard with suggested queries."""
    buttons = [KeyboardButton(text=c) for c in (choices or DEFAULT_QUICK_QUERIES)]
    return ReplyKeyboardMarkup(
        [buttons],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
