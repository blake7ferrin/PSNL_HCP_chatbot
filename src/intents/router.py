"""Parse user text + context -> Intent. Handles follow-ups via context."""
import re
from typing import Any, Optional

from .schema import (
    Intent,
    IntentFilters,
    INTENT_JOBS_LIST,
    INTENT_JOB_GET,
    INTENT_JOB_TIME,
    INTENT_ESTIMATES_LIST,
    INTENT_ESTIMATE_GET,
    INTENT_CUSTOMERS_SEARCH,
    INTENT_CUSTOMER_GET,
    INTENT_PRICEBOOK_SEARCH,
    INTENT_COMPANY_INFO,
    INTENT_SCHEDULE,
    INTENT_STATS,
    INTENT_HELP,
    INTENT_AGGREGATION_UNSUPPORTED,
    INTENT_CONFIRM,
    INTENT_UNKNOWN,
)
from .dateparse import parse_human_date, DEFAULT_TZ


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


# Keywords/phrases per intent (lowercase)
_HELP_KEYWORDS = ("help", "what can you do", "commands", "support", "hi", "hello")
_JOBS_KEYWORDS = ("job", "jobs", "scheduled", "schedule", "calendar", "appointments", "any day", "anything on")
_ESTIMATE_KEYWORDS = ("estimate", "estimates", "quote", "quotes")
_CUSTOMER_KEYWORDS = ("customer", "customers", "client", "clients")
_COMPANY_KEYWORDS = ("company", "business", "organization", "setup", "settings", "company info")
_PRICEBOOK_KEYWORDS = ("pricebook", "price book", "prices", "services", "materials", "price list")
_EMPLOYEES_KEYWORDS = ("employees", "employee", "technicians", "technician", "team", "staff")

_CONFIRM_PHRASES = ("yes", "yes please", "sure", "ok", "okay", "do it", "sounds good")

_ID_PREFIXES = {
    "job": "job_",
    "estimate": "est_",
    "customer": "cus_",
}


def _extract_id(text: str, prefix: str) -> Optional[str]:
    """Extract id after a prefix like 'job' or 'estimate'."""
    normalized = _normalize(text)
    prefix = prefix.lower()
    patterns = [
        rf"\b{re.escape(prefix)}\s*#?\s*(\w+)",
        rf"\b(?:number|#|id)\s*(\w+)\s*(?:{re.escape(prefix)})?",
    ]
    for pat in patterns:
        m = re.search(pat, normalized)
        if m:
            return m.group(1).strip()
    return None


def _is_valid_entity_id(entity_type: str, entity_id: str) -> bool:
    s = str(entity_id).strip()
    if not s:
        return False
    lower = s.lower()
    for etype, prefix in _ID_PREFIXES.items():
        if lower.startswith(prefix):
            return etype == entity_type
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", s))


def _is_confirm(text: str) -> bool:
    normalized = _normalize(text)
    normalized = re.sub(r"[!?.]+$", "", normalized).strip()
    return normalized in _CONFIRM_PHRASES


def _parse_list_index(text: str) -> Optional[int]:
    """Parse 'the second one', 'number 3', 'the first job', '2nd' -> 1-based index."""
    normalized = _normalize(text)
    # Prefer multi-syllable ordinals so "the second one" -> 2 not 1
    ordinals_long_first = [
        ("second", 2), ("2nd", 2), ("third", 3), ("3rd", 3),
        ("fourth", 4), ("4th", 4), ("fifth", 5), ("5th", 5),
        ("first", 1), ("1st", 1), ("one", 1), ("two", 2), ("three", 3), ("four", 4), ("five", 5),
    ]
    for word, num in ordinals_long_first:
        if re.search(rf"\b(?:the\s+)?{word}\b", normalized):
            return num
    m = re.search(r"\b(?:number|#|no\.?)\s*(\d+)\b", normalized)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(\d+)(?:st|nd|rd|th)?\s*(?:one|job|estimate|customer)?\b", normalized)
    if m:
        return int(m.group(1))
    return None


def route(
    user_text: str,
    *,
    context: Optional[dict[str, Any]] = None,
    tz_name: str = DEFAULT_TZ,
) -> Intent:
    """
    Map user message + context to an Intent.

    context can contain:
      - last_intent: str (e.g. jobs.list)
      - last_start_date, last_end_date: date or ISO str (for follow-up "Tuesday")
      - last_entity_ids: list[str] (for "the second one" -> resolve to id)
      - timezone: str (override tz_name)
    """
    context = context or {}
    if not user_text or not user_text.strip():
        return Intent(INTENT_UNKNOWN, confidence=0.0)

    normalized = _normalize(user_text)
    last_intent = context.get("last_intent")
    last_start = context.get("last_start_date")
    last_end = context.get("last_end_date")
    last_entity_ids = context.get("last_entity_ids") or []
    last_entity_type = context.get("last_entity_type")
    last_entity_id = context.get("last_entity_id")
    tz = context.get("timezone") or tz_name

    # ---- Pre-routed resolved entity (from conversation anchor + reference phrase) ----
    resolved = context.get("resolved_entity")
    if resolved:
        re_ids = resolved.get("ids") or []
        re_type = resolved.get("type") or "job"
        re_ids = [rid for rid in re_ids if _is_valid_entity_id(re_type, str(rid))]
        _TOTAL_KW = ("total", "amount", "cost", "price")
        if re_type == "job":
            if len(re_ids) == 0:
                return Intent(INTENT_UNKNOWN, raw_slots={"clarification": "no_job"})
            if len(re_ids) == 1:
                _TIME_KW = ("time", "what time", "when", "arrival", "arrival window")
                if any(k in normalized for k in _TIME_KW):
                    return Intent(INTENT_JOB_TIME, entity_id=re_ids[0])
                focus = "money" if any(k in normalized for k in _TOTAL_KW) else None
                return Intent(INTENT_JOB_GET, entity_id=re_ids[0], focus=focus)
            # multiple ids: resolve ordinal or ask for clarification
            list_index = _parse_list_index(user_text)
            # "that one" / "the one" are references, not "the first one" — don't resolve to index 1
            if list_index == 1 and ("that one" in normalized or "the one" in normalized):
                list_index = None
            if list_index is not None and 1 <= list_index <= len(re_ids):
                focus = "money" if any(k in normalized for k in _TOTAL_KW) else None
                resolved_id = re_ids[list_index - 1]
                if _is_valid_entity_id("job", resolved_id):
                    return Intent(INTENT_JOB_GET, entity_id=resolved_id, focus=focus)
                return Intent(INTENT_UNKNOWN, raw_slots={"clarification": "no_job"})
            return Intent(INTENT_UNKNOWN, raw_slots={"clarification": "multiple_jobs"})
    # Reference phrase but no anchor (e.g. "that one" with no previous list)
    if context.get("reference_phrase_used"):
        return Intent(INTENT_UNKNOWN, raw_slots={"clarification": "no_job"})

    # ---- Confirm / acknowledgement ----
    if _is_confirm(user_text):
        return Intent(INTENT_CONFIRM)

    # ---- "What time is it at?" / time query with last job context ----
    _TIME_QUERY_KEYWORDS = ("time", "what time", "when", "arrival", "arrival window")
    if any(k in normalized for k in _TIME_QUERY_KEYWORDS):
        if last_entity_type == "job" and last_entity_id:
            return Intent(INTENT_JOB_TIME, entity_id=last_entity_id)
        return Intent(
            INTENT_UNKNOWN,
            confidence=0.5,
            raw_slots={"hint": "Which job? Try “time for job <id>” or ask for “next week” first."},
        )

    # ---- "What's the total on that one?" / "details on next week's job?" -> job.get from context ----
    _DETAILS_TOTAL_KEYWORDS = ("total", "details", "info", "amount")
    _THAT_ONE_PHRASES = ("that one", "the one", "that job", "next week", "next weeks")
    if (
        last_intent == INTENT_JOBS_LIST
        and (last_entity_id or last_entity_ids)
        and any(k in normalized for k in _DETAILS_TOTAL_KEYWORDS)
        and any(p in normalized for p in _THAT_ONE_PHRASES)
    ):
        eid = last_entity_id or (last_entity_ids[0] if last_entity_ids else None)
        if eid:
            return Intent(INTENT_JOB_GET, entity_id=eid)

    # Normalize last_start/last_end to date if they're strings
    if isinstance(last_start, str):
        try:
            from datetime import date
            last_start = date.fromisoformat(last_start)
        except ValueError:
            last_start = None
    if isinstance(last_end, str):
        try:
            from datetime import date
            last_end = date.fromisoformat(last_end)
        except ValueError:
            last_end = None

    # ---- Date range + aggregation (before Help so "revenue this week" isn't matched by "hi" in "this") ----
    date_range_early = parse_human_date(user_text, context_start=last_start, context_end=last_end, tz_name=tz)
    _AGGREGATION_PHRASES = ("collected", "revenue", "how much did we make", "how much we made", "total collected", "our total")
    if date_range_early and any(p in normalized for p in _AGGREGATION_PHRASES):
        filters_agg = IntentFilters()
        filters_agg.start_date = date_range_early.start
        filters_agg.end_date = date_range_early.end
        filters_agg.date_label = date_range_early.label
        return Intent(INTENT_AGGREGATION_UNSUPPORTED, filters=filters_agg)

    # ---- Help (skip ordinal phrases like "the third one") ----
    looks_like_ordinal_request = bool(re.search(r"\b(?:the\s+)?(?:first|second|third|fourth|fifth)\s+one\b", normalized))
    if not looks_like_ordinal_request and any(k in normalized for k in _HELP_KEYWORDS) and not _extract_id(user_text, "job"):
        return Intent(INTENT_HELP)

    # ---- job.get by id: "job 12345", "get job 456" (not "jobs today" -> id "s") ----
    job_id = _extract_id(user_text, "job")
    if job_id:
        if not _is_valid_entity_id("job", job_id):
            return Intent(INTENT_UNKNOWN, raw_slots={"hint": "That doesn't look like a job ID."})
        return Intent(INTENT_JOB_GET, entity_id=job_id)

    # ---- estimate.get by id ----
    estimate_id = _extract_id(user_text, "estimate")
    if estimate_id:
        if not _is_valid_entity_id("estimate", estimate_id):
            return Intent(INTENT_UNKNOWN, raw_slots={"hint": "That doesn't look like an estimate ID."})
        return Intent(INTENT_ESTIMATE_GET, entity_id=estimate_id)

    # ---- customer.get by id ----
    customer_id = _extract_id(user_text, "customer")
    if customer_id:
        if not _is_valid_entity_id("customer", customer_id):
            return Intent(INTENT_UNKNOWN, raw_slots={"hint": "That doesn't look like a customer ID."})
        return Intent(INTENT_CUSTOMER_GET, entity_id=customer_id)

    # ---- "The second one" / "details for #2" -> resolve from last list ----
    list_index = _parse_list_index(user_text)
    last_anchor = context.get("last_anchor")
    if list_index is not None and not last_entity_ids:
        # Ordinal phrase with no context - never say "No previous list" if anchor exists
        if re.search(r"\b(?:the\s+)?(?:first|second|third|fourth|fifth|one|two|three)\b", normalized):
            if last_anchor:
                return Intent(INTENT_UNKNOWN, raw_slots={"clarification": "no_job"})
            return Intent(
                INTENT_UNKNOWN,
                confidence=0.5,
                raw_slots={"list_index": list_index, "hint": "Which job do you mean? Try asking for \"jobs next week\" first."},
            )
    elif list_index is not None and last_entity_ids:
        idx = list_index - 1
        if 0 <= idx < len(last_entity_ids):
            resolved_id = last_entity_ids[idx]
            if last_intent == INTENT_JOBS_LIST:
                if _is_valid_entity_id("job", resolved_id):
                    return Intent(INTENT_JOB_GET, entity_id=resolved_id)
            if last_intent == INTENT_ESTIMATES_LIST:
                if _is_valid_entity_id("estimate", resolved_id):
                    return Intent(INTENT_ESTIMATE_GET, entity_id=resolved_id)
            if last_intent == INTENT_CUSTOMERS_SEARCH:
                if _is_valid_entity_id("customer", resolved_id):
                    return Intent(INTENT_CUSTOMER_GET, entity_id=resolved_id)
        if last_anchor:
            return Intent(INTENT_UNKNOWN, raw_slots={"clarification": "no_job"})
        return Intent(
            INTENT_UNKNOWN,
            confidence=0.5,
            raw_slots={"list_index": list_index, "hint": "Which job do you mean? Try asking for \"jobs next week\" first."},
        )

    # ---- Date range for jobs/schedule ----
    date_range = parse_human_date(
        user_text,
        context_start=last_start,
        context_end=last_end,
        tz_name=tz,
    )
    filters = IntentFilters()
    if date_range:
        filters.start_date = date_range.start
        filters.end_date = date_range.end
        filters.date_label = date_range.label

    # Jobs/schedule intents with date (or follow-up: "what about Tuesday?" with last_intent + date_range)
    # "busy" = is X busy tomorrow? / who's busy next week? -> jobs for that date (person filter not yet supported)
    jobs_or_schedule = (
        any(j in normalized for j in ("job", "jobs", "scheduled", "schedule", "calendar", "appointments", "busy"))
        or "any day" in normalized
        or "anything on" in normalized
        or "what's on" in normalized
        or "whats on" in normalized
        or "what about" in normalized
    )
    follow_up_with_date = date_range and last_intent == INTENT_JOBS_LIST
    if (jobs_or_schedule or follow_up_with_date) and (date_range or last_intent == INTENT_JOBS_LIST):
        if not filters.start_date and last_start:
            filters.start_date = last_start
            filters.end_date = last_end or last_start
            filters.date_label = context.get("last_date_label") or "that period"
        elif not filters.start_date:
            from datetime import date
            today = date.today()
            filters.start_date = today
            filters.end_date = today
            filters.date_label = "today"
        return Intent(INTENT_JOBS_LIST, filters=filters)

    # ---- Stats ----
    if any(k in normalized for k in ("stats", "statistics", "summary", "dashboard", "overview", "numbers", "count", "how's it looking")):
        return Intent(INTENT_STATS)

    # ---- Company ----
    if any(k in normalized for k in _COMPANY_KEYWORDS):
        return Intent(INTENT_COMPANY_INFO)

    # ---- Pricebook ----
    if any(k in normalized for k in _PRICEBOOK_KEYWORDS):
        return Intent(INTENT_PRICEBOOK_SEARCH)

    # ---- Estimates list (optionally unscheduled / open) ----
    if any(k in normalized for k in _ESTIMATE_KEYWORDS):
        filters = IntentFilters()
        if "unscheduled" in normalized:
            filters.status = "unscheduled"
        elif "open" in normalized:
            filters.status = "open"
        return Intent(INTENT_ESTIMATES_LIST, filters=filters)

    # ---- Customers list ----
    if any(k in normalized for k in _CUSTOMER_KEYWORDS):
        return Intent(INTENT_CUSTOMERS_SEARCH)

    # ---- Jobs list (generic: today default) ----
    if any(k in normalized for k in _JOBS_KEYWORDS):
        if not filters.start_date:
            from datetime import date
            today = date.today()
            filters.start_date = today
            filters.end_date = today
            filters.date_label = "today"
        return Intent(INTENT_JOBS_LIST, filters=filters)

    return Intent(INTENT_UNKNOWN, confidence=0.0)
