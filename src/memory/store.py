"""Conversation state models and in-memory store."""
from dataclasses import dataclass, field
from datetime import date
import logging
import re
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)

DEFAULT_TZ = "America/Phoenix"

_ID_PREFIXES = {
    "job": "job_",
    "estimate": "est_",
    "customer": "cus_",
}


def _is_valid_id_for_type(entity_type: str, entity_id: str) -> bool:
    if not entity_id:
        return False
    s = str(entity_id).strip()
    if not s:
        return False
    lower = s.lower()
    for etype, prefix in _ID_PREFIXES.items():
        if lower.startswith(prefix):
            return etype == entity_type
    # Allow common numeric/slug identifiers when no explicit prefix is used.
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", s))


def _filter_ids(entity_type: str, ids: list[str]) -> list[str]:
    out = [str(i) for i in ids if _is_valid_id_for_type(entity_type, str(i))]
    if len(out) != len(ids):
        logger.debug("filtered ids for type=%s: %s -> %s", entity_type, ids, out)
    return out


@dataclass
class AnchorDateRange:
    start: date
    end: date

    def to_dict(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> Optional["AnchorDateRange"]:
        if not raw:
            return None
        try:
            start = date.fromisoformat(str(raw.get("start")))
            end = date.fromisoformat(str(raw.get("end")))
            return AnchorDateRange(start=start, end=end)
        except Exception:
            return None


@dataclass
class ConversationAnchor:
    type: str
    ids: list[str]
    label: Optional[str] = None
    date_range: Optional[AnchorDateRange] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "ids": list(self.ids),
            "label": self.label,
            "date_range": self.date_range.to_dict() if self.date_range else None,
        }

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> Optional["ConversationAnchor"]:
        if not raw:
            return None
        type_name = raw.get("type")
        ids = raw.get("ids") or []
        if not isinstance(ids, list) or not type_name:
            return None
        return ConversationAnchor(
            type=str(type_name),
            ids=[str(i) for i in ids],
            label=raw.get("label"),
            date_range=AnchorDateRange.from_dict(raw.get("date_range") or {}),
        )


@dataclass
class PendingAction:
    intent_type: str
    params: dict[str, Any]
    label: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"intent_type": self.intent_type, "params": self.params, "label": self.label}

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> Optional["PendingAction"]:
        if not raw:
            return None
        intent_type = raw.get("intent_type")
        params = raw.get("params") or {}
        if not intent_type or not isinstance(params, dict):
            return None
        return PendingAction(intent_type=str(intent_type), params=dict(params), label=raw.get("label"))


@dataclass
class ChatState:
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
    last_anchor: Optional[ConversationAnchor] = None
    pending_action: Optional[PendingAction] = None

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
        if self.last_anchor:
            out["last_anchor"] = self.last_anchor.to_dict()
        if self.pending_action:
            out["pending_action"] = self.pending_action.to_dict()
        return out

    def set_anchor(
        self,
        type_name: str,
        ids: list[str],
        *,
        date_range: Optional[AnchorDateRange] = None,
        label: Optional[str] = None,
    ) -> None:
        """Set conversation anchor after a successful entity response."""
        clean_ids = _filter_ids(type_name, ids)
        self.last_anchor = ConversationAnchor(
            type=type_name,
            ids=clean_ids,
            date_range=date_range,
            label=label or None,
        )
        self.last_entity_ids = list(clean_ids)
        self.last_entity_type = type_name
        self.last_entity_id = clean_ids[0] if clean_ids else None

    def clear_anchor(self) -> None:
        """Clear anchor when user explicitly changes topic (e.g. customers, estimates, help)."""
        self.last_anchor = None

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
        if entity_type and entity_ids is not None:
            self.last_entity_ids = _filter_ids(entity_type, list(entity_ids))
        elif entity_ids is not None:
            self.last_entity_ids = list(entity_ids)
        if entity_type is not None:
            self.last_entity_type = entity_type
        if entity_type and entity_id is not None:
            valid = _filter_ids(entity_type, [entity_id])
            self.last_entity_id = valid[0] if valid else None
        elif entity_id is not None:
            self.last_entity_id = entity_id

    def set_pending_action(self, action: Optional[PendingAction]) -> None:
        self.pending_action = action

    def clear_pending_action(self) -> None:
        self.pending_action = None


class MemoryStore(Protocol):
    def get(self, chat_id: str) -> ChatState: ...
    def save(self, state: ChatState) -> None: ...
    def close(self) -> None: ...


class InMemoryStore:
    """Simple in-memory store for tests or local runs."""

    def __init__(self) -> None:
        self._store: dict[str, ChatState] = {}

    def get(self, chat_id: str) -> ChatState:
        key = str(chat_id)
        if key not in self._store:
            self._store[key] = ChatState(chat_id=key)
        return self._store[key]

    def save(self, state: ChatState) -> None:
        self._store[str(state.chat_id)] = state

    def close(self) -> None:
        self._store = {}
