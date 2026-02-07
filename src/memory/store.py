"""Per-chat memory: last intent, date range, entity IDs. In-memory; design allows sqlite later."""
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

# Chat id -> ChatMemory (in-memory). Can be replaced by sqlite-backed store.
_store: dict[str, "ChatMemory"] = {}

DEFAULT_TZ = "America/Phoenix"


@dataclass
class ChatMemory:
    """Per-chat state for follow-up resolution."""
    chat_id: str
    last_intent: Optional[str] = None
    last_start_date: Optional[date] = None
    last_end_date: Optional[date] = None
    last_date_label: Optional[str] = None
    last_entity_ids: list[str] = field(default_factory=list)
    last_entity_type: Optional[str] = None
    last_entity_id: Optional[str] = None
    timezone: str = DEFAULT_TZ

    def to_context(self) -> dict[str, Any]:
        """Export for intent router (date as ISO string for JSON/sqlite)."""
        return {
            "last_intent": self.last_intent,
            "last_start_date": self.last_start_date.isoformat() if self.last_start_date else None,
            "last_end_date": self.last_end_date.isoformat() if self.last_end_date else None,
            "last_date_label": self.last_date_label,
            "last_entity_ids": list(self.last_entity_ids),
            "last_entity_type": self.last_entity_type,
            "last_entity_id": self.last_entity_id,
            "timezone": self.timezone,
        }

    def update_after_intent(
        self,
        intent: str,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        date_label: Optional[str] = None,
        entity_ids: Optional[list[str]] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> None:
        """Update memory after handling an intent (list or get)."""
        self.last_intent = intent
        if start_date is not None:
            self.last_start_date = start_date
        if end_date is not None:
            self.last_end_date = end_date
        if date_label is not None:
            self.last_date_label = date_label
        if entity_ids is not None:
            self.last_entity_ids = list(entity_ids)
        if entity_type is not None:
            self.last_entity_type = entity_type
        if entity_id is not None:
            self.last_entity_id = entity_id


def get_chat_memory(chat_id: str) -> ChatMemory:
    """Get or create in-memory chat state. chat_id should be str (e.g. Telegram chat id)."""
    key = str(chat_id)
    if key not in _store:
        _store[key] = ChatMemory(chat_id=key)
    return _store[key]


def set_chat_timezone(chat_id: str, tz_name: str) -> None:
    """Set timezone for a chat (e.g. from user settings)."""
    mem = get_chat_memory(chat_id)
    mem.timezone = tz_name or DEFAULT_TZ
