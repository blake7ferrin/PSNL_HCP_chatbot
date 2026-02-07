"""Per-chat conversation memory (SQLite-backed by default)."""
from typing import Optional

from .store import (
    AnchorDateRange,
    ChatState,
    ConversationAnchor,
    InMemoryStore,
    MemoryStore,
    PendingAction,
)
from .sqlite_store import SQLiteMemoryStore

_store: Optional[MemoryStore] = None


def _default_store() -> MemoryStore:
    return SQLiteMemoryStore()


def set_memory_store(store: MemoryStore) -> None:
    global _store
    _store = store


def get_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = _default_store()
    return _store


def get_chat_memory(chat_id: str) -> ChatState:
    return get_store().get(chat_id)


def save_chat_memory(state: ChatState) -> None:
    get_store().save(state)


__all__ = [
    "AnchorDateRange",
    "ChatState",
    "ConversationAnchor",
    "InMemoryStore",
    "MemoryStore",
    "PendingAction",
    "get_chat_memory",
    "save_chat_memory",
    "set_memory_store",
]
