"""Per-chat memory: last intent, date range, entity IDs, conversation anchor."""
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

# Chat id -> ChatMemory (in-memory). Can be replaced by sqlite-backed store.
_store: dict[str, "ChatMemory"] = {}

DEFAULT_TZ = "America/Phoenix"

# Anchor date_range: tuple (start_date, end_date) or None
AnchorDateRange = tuple[date, date] | None


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
    last_anchor: Optional[dict[str, Any]] = None
    # When bot suggests an action ("Want me to list jobs from last week?"), store here; clear after confirm or topic change
    pending_action: Optional[dict[str, Any]] = None

    def to_context(self) -> dict[str, Any]:
        """Export for intent router (date as ISO string for JSON/sqlite)."""
        out = {
            "last_intent": self.last_intent,
            "last_start_date": self.last_start_date.isoformat() if self.last_start_date else None,
            "last_end_date": self.last_end_date.isoformat() if self.last_end_date else None,
            "last_date_label": self.last_date_label,
            "last_entity_ids": list(self.last_entity_ids),
            "last_entity_type": self.last_entity_type,
            "last_entity_id": self.last_entity_id,
            "timezone": self.timezone,
        }
        if self.last_anchor is not None:
            anchor = dict(self.last_anchor)
            if anchor.get("date_range"):
                s, e = anchor["date_range"]
                anchor["date_range"] = (s.isoformat() if hasattr(s, "isoformat") else s, e.isoformat() if hasattr(e, "isoformat") else e)
            out["last_anchor"] = anchor
        out["pending_action"] = self.pending_action
        return out

    def set_anchor(
        self,
        type_name: str,
        ids: list[str],
        *,
        date_range: AnchorDateRange = None,
        label: Optional[str] = None,
    ) -> None:
        """Set conversation anchor after a successful entity response (jobs list, job get, etc.)."""
        ids_list = list(ids)
        self.last_anchor = {
            "type": type_name,
            "id": ids_list[0] if ids_list else None,
            "ids": ids_list,
            "date_range": date_range,
            "label": label or "",
        }
        self.last_entity_ids = list(ids)
        self.last_entity_type = type_name
        self.last_entity_id = ids[0] if ids else None

    def get_anchor(self) -> Optional[dict[str, Any]]:
        """Return current anchor (type, ids, date_range, label) or None."""
        return self.last_anchor

    def clear_anchor(self) -> None:
        """Clear anchor when user explicitly changes topic (e.g. customers, estimates, help)."""
        self.last_anchor = None
        self.pending_action = None

    def set_pending_action(self, action: dict[str, Any]) -> None:
        """Store suggested action so 'yes please' can execute it."""
        self.pending_action = action

    def clear_pending_action(self) -> None:
        """Clear after executing or on topic change."""
        self.pending_action = None

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
