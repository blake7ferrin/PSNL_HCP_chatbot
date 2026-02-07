"""Map user text to intent and parameters. Keyword/heuristic rules, no LLM."""
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional


@dataclass
class IntentResult:
    """Result of intent parsing."""
    intent: str
    params: dict[str, Any]


# Intent names used by the bot
INTENT_JOBS_TODAY = "jobs_today"
INTENT_JOBS_BY_DATE = "jobs_by_date"
INTENT_JOB_DETAIL = "job_detail"
INTENT_ESTIMATES_LIST = "estimates_list"
INTENT_ESTIMATE_DETAIL = "estimate_detail"
INTENT_CUSTOMERS_LIST = "customers_list"
INTENT_CUSTOMER_DETAIL = "customer_detail"
INTENT_COMPANY_INFO = "company_info"
INTENT_EMPLOYEES_LIST = "employees_list"
INTENT_PRICEBOOK = "pricebook"
INTENT_SCHEDULE = "schedule"
INTENT_HELP = "help"
INTENT_UNKNOWN = "unknown"


# Keywords/phrases that suggest intents (lowercase)
JOBS_KEYWORDS = ("job", "jobs", "today's jobs", "tomorrow's jobs", "jobs today", "jobs tomorrow", "scheduled jobs")
ESTIMATE_KEYWORDS = ("estimate", "estimates", "quote", "quotes")
CUSTOMER_KEYWORDS = ("customer", "customers", "client", "clients")
COMPANY_KEYWORDS = ("company", "business", "organization", "setup", "settings", "company info")
PRICEBOOK_KEYWORDS = ("pricebook", "price book", "prices", "services", "materials", "price list")
EMPLOYEES_KEYWORDS = ("employees", "employee", "technicians", "technician", "team", "staff")
SCHEDULE_KEYWORDS = ("schedule", "scheduling", "calendar", "appointments", "who's working", "technicians today")
HELP_KEYWORDS = ("help", "what can you do", "commands", "support")


def _normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


_MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _parse_date(token: str) -> Optional[str]:
    """Return YYYY-MM-DD for relative or absolute date, or None."""
    token = token.strip().lower()
    today = date.today()
    if token in ("today", "todays"):
        return today.isoformat()
    if token in ("tomorrow", "tomorrows"):
        return (today + timedelta(days=1)).isoformat()
    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", token):
        return token
    # MM/DD or MM/DD/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{4}))?$", token)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else today.year
        try:
            d = date(year, month, day)
            return d.isoformat()
        except ValueError:
            pass
    return None


def _parse_date_from_text(text: str) -> Optional[str]:
    """Try to find a date like 'Jan 30', 'Jan. 30th', 'January 30' in text. Returns YYYY-MM-DD."""
    normalized = _normalize(text)
    today = date.today()
    # e.g. "jan 30", "jan. 30", "january 30th", "jan 30th 2026"
    m = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
        r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s*\.?\s*(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(\d{4}))?\b",
        normalized,
        re.I,
    )
    if not m:
        return None
    month_str, day_str, year_str = m.group(1).lower(), m.group(2), m.group(3)
    month = _MONTH_NAMES.get(month_str)
    if month is None:
        return None
    day = int(day_str)
    year = int(year_str) if year_str else today.year
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _extract_id(text: str, prefix: str) -> Optional[str]:
    """Extract id after a prefix like 'job' or 'estimate' (e.g. 'job 123' -> '123')."""
    text = _normalize(text)
    prefix = prefix.lower()
    # "job 12345" or "job #12345" or "estimate 678"
    patterns = [
        rf"\b{re.escape(prefix)}\s*#?\s*(\w+)",
        rf"\b(?:number|#|id)\s*(\w+)\s*(?:{re.escape(prefix)})?",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return None


def parse_intent(text: str) -> IntentResult:
    """
    Map user message to intent and parameters.
    Returns IntentResult(intent, params). intent may be INTENT_UNKNOWN.
    """
    if not text or not text.strip():
        return IntentResult(INTENT_UNKNOWN, {})

    normalized = _normalize(text)

    # Help
    if any(k in normalized for k in HELP_KEYWORDS):
        return IntentResult(INTENT_HELP, {})

    # Job by id: "job 12345", "job #123", "get job 456"
    job_id = _extract_id(text, "job")
    if job_id and job_id.isdigit():
        return IntentResult(INTENT_JOB_DETAIL, {"job_id": job_id})

    # Estimate by id
    estimate_id = _extract_id(text, "estimate")
    if estimate_id and (estimate_id.isdigit() or estimate_id.isalnum()):
        return IntentResult(INTENT_ESTIMATE_DETAIL, {"estimate_id": estimate_id})

    # Customer by id (e.g. "customer 789")
    customer_id = _extract_id(text, "customer")
    if customer_id and (customer_id.isdigit() or customer_id.isalnum()):
        return IntentResult(INTENT_CUSTOMER_DETAIL, {"customer_id": customer_id})

    # Date extraction for jobs/schedule: "jobs for 2025-02-08", "tomorrow's jobs", "Friday Jan 30th"
    date_str = _parse_date_from_text(normalized)
    if date_str and any(j in normalized for j in ("job", "jobs")):
        return IntentResult(INTENT_JOBS_BY_DATE, {"date": date_str})
    if date_str and any(s in normalized for s in SCHEDULE_KEYWORDS):
        return IntentResult(INTENT_SCHEDULE, {"date": date_str})
    words = normalized.split()
    for i, w in enumerate(words):
        d = _parse_date(w)
        if d is not None:
            if any(j in normalized for j in ("job", "jobs")):
                return IntentResult(INTENT_JOBS_BY_DATE, {"date": d})
            if any(s in normalized for s in SCHEDULE_KEYWORDS):
                return IntentResult(INTENT_SCHEDULE, {"date": d})
            break

    # Today's jobs / jobs today / today jobs
    if any(phrase in normalized for phrase in ("today's jobs", "jobs today", "today jobs", "jobs for today")):
        return IntentResult(INTENT_JOBS_TODAY, {})
    # Tomorrow's jobs
    if any(phrase in normalized for phrase in ("tomorrow's jobs", "jobs tomorrow", "tomorrow jobs")):
        return IntentResult(INTENT_JOBS_BY_DATE, {"date": (date.today() + timedelta(days=1)).isoformat()})

    # Jobs (generic list - could default to today)
    if any(k in normalized for k in JOBS_KEYWORDS):
        return IntentResult(INTENT_JOBS_TODAY, {})

    # Estimates list
    if any(k in normalized for k in ESTIMATE_KEYWORDS):
        return IntentResult(INTENT_ESTIMATES_LIST, {})

    # Customers list
    if any(k in normalized for k in CUSTOMER_KEYWORDS):
        return IntentResult(INTENT_CUSTOMERS_LIST, {})

    # Company
    if any(k in normalized for k in COMPANY_KEYWORDS):
        return IntentResult(INTENT_COMPANY_INFO, {})

    # Employees (HCP glossary: field techs & office admins)
    if any(k in normalized for k in EMPLOYEES_KEYWORDS):
        return IntentResult(INTENT_EMPLOYEES_LIST, {})

    # Pricebook
    if any(k in normalized for k in PRICEBOOK_KEYWORDS):
        return IntentResult(INTENT_PRICEBOOK, {})

    # Schedule
    if any(k in normalized for k in SCHEDULE_KEYWORDS):
        return IntentResult(INTENT_SCHEDULE, {"date": date.today().isoformat()})

    return IntentResult(INTENT_UNKNOWN, {})


def get_help_message() -> str:
    """Return a short list of supported questions for the user."""
    return (
        "I can answer read-only questions about Polar Air's Housecall Pro data. Try asking:\n\n"
        "• *Jobs* – \"Today's jobs\", \"Jobs for tomorrow\", \"Job 12345\"\n"
        "• *Estimates* – \"List estimates\", \"Estimate 678\"\n"
        "• *Customers* – \"List customers\", \"Customer 789\"\n"
        "• *Company* – \"Company info\", \"Company setup\"\n"
        "• *Employees* – \"List employees\", \"Technicians\", \"Team\"\n"
        "• *Pricebook* – \"Pricebook\", \"Services\", \"Materials\"\n"
        "• *Schedule* – \"Schedule today\", \"Appointments\"\n\n"
        "I only read data; I don't create or change anything."
    )
