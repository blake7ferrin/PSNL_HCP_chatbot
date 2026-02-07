"""Optional LLM layer for natural-language summaries. Uses OpenAI or OpenRouter (OpenAI-compatible)."""
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Lazy client so we don't require openai unless LLM is used
_client: Optional[Any] = None
_model: Optional[str] = None


def _ensure_env_loaded():
    """Load .env from project root so LLM keys are visible (idempotent)."""
    try:
        from dotenv import load_dotenv
        root = Path(__file__).resolve().parent.parent
        load_dotenv(root / ".env")
    except Exception:
        pass


def _get_client():
    global _client, _model
    if _client is not None:
        return _client, _model
    _ensure_env_loaded()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    openai_key = (os.getenv("OPENAI_API_KEY", "") or os.getenv("LLM_API_KEY", "")).strip()
    if openrouter_key:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
        )
        _model = os.getenv("LLM_MODEL", "").strip() or "openai/gpt-4o-mini"
        logger.debug("LLM: using OpenRouter model=%s", _model)
    elif openai_key:
        from openai import AsyncOpenAI
        _client = AsyncOpenAI(api_key=openai_key)
        _model = os.getenv("LLM_MODEL", "").strip() or "gpt-4o-mini"
        logger.debug("LLM: using OpenAI model=%s", _model)
    else:
        _client = False  # no key
        _model = None
        logger.debug("LLM: no OPENAI_API_KEY or OPENROUTER_API_KEY set; LLM summaries disabled")
    return _client, _model


def is_available() -> bool:
    """True if an LLM API key is set and we can call the model."""
    client, _ = _get_client()
    return client is not None and client is not False


async def format_jobs_list(data: Any, date_label: str, user_message: str = "") -> Optional[str]:
    """
    Ask the LLM to summarize a list of jobs in a short, admin-friendly way.
    Returns None on failure or if LLM not configured.
    """
    client, model = _get_client()
    if client is None or client is False:
        return None
    jobs = _extract_jobs(data)
    if not jobs:
        return None
    # Keep payload small: top 20 jobs, strip huge fields if needed
    trimmed = []
    for j in jobs[:20]:
        if isinstance(j, dict):
            trimmed.append({k: v for k, v in j.items() if v is not None and k not in ("created_at", "updated_at", "metadata")})
        else:
            trimmed.append(j)
    prompt = f"""You are a helpful assistant for an HVAC company admin using a Telegram bot. The user asked about scheduled jobs.

User question: {user_message or 'List jobs'}

Date/period: {date_label}

Raw job data from the API (JSON):
{json.dumps(trimmed, default=str)[:12000]}

Reply with a SHORT, scannable summary for Telegram (no code blocks). For each job include: who it's for (customer), address or location if present, and status. Use bullet points. Keep the whole reply under 1000 characters. Do not use markdown bold/italic that could break Telegram - use plain text or simple bullets."""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
        )
        text = (response.choices[0].message.content or "").strip()
        return text if text else None
    except Exception as e:
        logger.warning("LLM format_jobs_list failed: %s", e, exc_info=logger.isEnabledFor(logging.DEBUG))
        return None


def _extract_jobs(data: Any) -> list:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("jobs", "data", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


async def format_response(intent: str, data: Any, user_message: str = "", context: Optional[dict] = None) -> Optional[str]:
    """
    Generic: ask the LLM to format API data as a short reply for the user.
    intent: e.g. jobs_list, job_detail, estimates_list, ...
    context: optional e.g. {"date_label": "2026-01-26"}.
    Returns None on failure or if LLM not configured.
    """
    client, model = _get_client()
    if client is None or client is False:
        return None
    context = context or {}
    # Truncate large payloads
    payload = json.dumps(data, default=str)[:10000]
    prompt = f"""You are a helpful assistant for an HVAC company admin in a Telegram chat. The user asked a question and we have API data.

User question: {user_message or '(no question)'}
Intent: {intent}
Context: {json.dumps(context)}

API data (JSON):
{payload}

Reply with a SHORT, friendly summary for Telegram (under 800 characters). Use simple bullets or lines. Do not use markdown that could break Telegram (no unescaped _ or *). Plain text is fine."""

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        text = (response.choices[0].message.content or "").strip()
        return text if text else None
    except Exception as e:
        logger.warning("LLM format_response(%s) failed: %s", intent, e, exc_info=logger.isEnabledFor(logging.DEBUG))
        return None
