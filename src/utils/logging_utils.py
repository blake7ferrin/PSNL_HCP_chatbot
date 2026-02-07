"""Structured logging helpers with PII redaction."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
_ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9.\- ]+\s+(?:st|street|ave|avenue|rd|road|blvd|boulevard|ln|lane|dr|drive|ct|court|way|pkwy|parkway|pl|place)\b",
    re.IGNORECASE,
)


def _redact_text(text: str) -> str:
    if not text:
        return text
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = _ADDRESS_RE.sub("[REDACTED_ADDRESS]", text)
    return text


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def log_event(logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    payload = {"event": event, **fields}
    safe = _redact(payload)
    logger.log(level, json.dumps(safe, separators=(",", ":")))
