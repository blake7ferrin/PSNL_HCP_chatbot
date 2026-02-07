"""Turn API data into Telegram-ready text: grouped by day, next actions, escape-safe."""
import logging
from collections import defaultdict
from datetime import date
from typing import Any, Optional

from src.utils.formatting import format_money
from src.utils.time import format_single_time, DEFAULT_USER_TZ

from .templates import get_phrase
from . import suggestions

logger = logging.getLogger(__name__)


def get_best_total_amount(obj: Any) -> Any:
    """
    Extract best total/amount from HCP job/estimate/invoice object for format_money.
    Priority: total_amount -> total -> amount_due -> balance_due -> nested invoice totals.
    """
    total, _ = get_best_money_fields(obj)
    return total


def _sum_line_items(job_obj: dict, key_choices: tuple[str, ...] = ("total", "amount", "price", "total_price")) -> Optional[Any]:
    """Sum totals from line_items or similar list if present. Returns first non-zero sum found."""
    for list_key in ("line_items", "lines", "items", "charges"):
        items = job_obj.get(list_key)
        if not isinstance(items, list):
            continue
        for key in key_choices:
            total = 0
            for it in items:
                if not isinstance(it, dict):
                    continue
                v = it.get(key)
                if v is not None:
                    try:
                        total += int(v) if isinstance(v, (int, float)) else int(float(v))
                    except (TypeError, ValueError):
                        pass
            if total != 0:
                return total
    return None


def get_best_money_fields(job_obj: Any) -> tuple[Any, Any]:
    """
    Get (total_val, outstanding_val) for a job. All values must be passed through format_money().
    Tries common HCP/API field names: invoice.total, job.total_amount, line_items sum, etc.
    """
    if not job_obj or not isinstance(job_obj, dict):
        return (None, None)
    # Unwrap if API returns { "job": { ... } }
    if "job" in job_obj and isinstance(job_obj["job"], dict):
        job_obj = job_obj["job"]
    total_val = None
    outstanding_val = None
    inv = job_obj.get("invoice")
    if isinstance(inv, dict):
        total_val = (
            inv.get("total") or inv.get("amount_total") or inv.get("total_amount")
            or inv.get("amount") or inv.get("grand_total")
            or inv.get("total_price") or inv.get("price_total")
        )
    if total_val is None:
        total_val = (
            job_obj.get("total_amount") or job_obj.get("total")
            or job_obj.get("amount") or job_obj.get("grand_total")
            or job_obj.get("total_amount_cents")
            or job_obj.get("total_price") or job_obj.get("price_total")
            or job_obj.get("invoice_total")
        )
    if total_val is None:
        total_val = _sum_line_items(job_obj)
    outstanding_val = job_obj.get("balance_due") or job_obj.get("amount_due")
    if outstanding_val is not None and total_val is not None and outstanding_val == total_val:
        outstanding_val = None
    if total_val is None and isinstance(inv, dict):
        total_val = inv.get("balance_due") or inv.get("amount_due")
    if total_val is None:
        total_val = job_obj.get("amount_due") or job_obj.get("balance_due")
    if total_val is None:
        logger.debug(
            "job total not found; job keys=%s invoice keys=%s",
            list(job_obj.keys()) if job_obj else [],
            list(inv.keys()) if isinstance(inv, dict) else None,
        )
    return (total_val, outstanding_val)

# Telegram Markdown: escape these so API content doesn't break parse_mode
_MD_ESCAPE = str.maketrans({"_": r"\_", "*": r"\*", "`": r"\`", "[": r"\[", "\\": r"\\"})


def _escape_md(s: str) -> str:
    return s.translate(_MD_ESCAPE)


def _safe(value: Any, default: str = "—", escape: bool = True) -> str:
    if value is None:
        return default
    out = str(value).strip() or default
    return _escape_md(out) if escape else out


def _list_from_response(data: Any) -> list:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("jobs", "estimates", "customers", "data", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def _job_start_date_str(obj: dict) -> Optional[str]:
    start = (
        obj.get("scheduled_start_date")
        or obj.get("scheduled_start")
        or obj.get("start_date")
        or obj.get("scheduled_at")
    )
    if start is None and isinstance(obj.get("schedule"), dict):
        start = obj["schedule"].get("scheduled_start") or obj["schedule"].get("scheduled_start_date")
    if start is None:
        return None
    if isinstance(start, str):
        return start.split("T")[0][:10]
    return None


def _job_time_str(obj: dict, tz_name: str = DEFAULT_USER_TZ) -> str:
    start = obj.get("scheduled_start") or obj.get("scheduled_start_date") or obj.get("start_time")
    if start is None and isinstance(obj.get("schedule"), dict):
        start = obj["schedule"].get("scheduled_start")
    if not start:
        return ""
    return format_single_time(start, tz_name=tz_name) or str(start)[:16]


def _job_customer_name(obj: dict) -> str:
    cust = obj.get("customer")
    if isinstance(cust, dict):
        return cust.get("display_name") or (f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip()) or "—"
    if isinstance(cust, str) and cust.strip():
        return cust
    return "—"


def _job_city(obj: dict) -> str:
    addr = obj.get("address")
    if isinstance(addr, dict):
        return (addr.get("city") or addr.get("locality") or "").strip() or ""
    return ""


def _job_tech(obj: dict) -> str:
    pro = obj.get("pro") or obj.get("technician") or obj.get("assigned_to")
    if isinstance(pro, dict):
        return pro.get("display_name") or pro.get("name") or ""
    return str(pro) if pro else ""


def _job_short_id(obj: dict) -> str:
    raw = obj.get("id") or obj.get("job_id") or obj.get("number") or ""
    s = str(raw).strip()
    if s.startswith("job_"):
        s = s[4:]
    if len(s) > 12:
        s = s[-8:]
    return _escape_md(s) if s else "?"


def _format_one_job_line(obj: dict, tz_name: str = DEFAULT_USER_TZ) -> str:
    jid = _job_short_id(obj)
    time_str = _job_time_str(obj, tz_name=tz_name)
    customer = _safe(_job_customer_name(obj))
    city = _job_city(obj)
    if city:
        location = f"{customer}, {_safe(city)}"
    else:
        location = customer
    status = _safe(obj.get("status"))
    tech = _safe(_job_tech(obj))
    parts = [f"#{jid}"]
    if time_str:
        parts.append(time_str)
    parts.append(location)
    if status and status != "—":
        parts.append(f"({status})")
    if tech and tech != "—":
        parts.append(f"→ {tech}")
    return " • ".join(parts)


def format_jobs_list_by_day(
    jobs_data: Any,
    date_label: str,
    *,
    include_suggestions: bool = True,
    max_per_day: int = 50,
    tz_name: str = DEFAULT_USER_TZ,
) -> str:
    """
    Format job list grouped by day. Each job: time, customer, city, status, tech.
    Appends a short "next actions" section with 2–3 suggestions.
    """
    jobs = _list_from_response(jobs_data)
    if not jobs:
        no_phrase = get_phrase("no_results")
        if date_label and "that period" in no_phrase:
            block = no_phrase.replace("that period", _escape_md(date_label))
        elif date_label and "that range" in no_phrase:
            block = no_phrase.replace("that range", _escape_md(date_label))
        elif date_label and no_phrase.strip() == "No jobs.":
            block = f"No jobs for {_escape_md(date_label)}."
        else:
            block = no_phrase
        if include_suggestions:
            sugs = suggestions.ops_coach_suggestions(jobs_data, date_label=date_label)
            block += "\n\n" + get_phrase("next_actions_header") + "\n• " + "\n• ".join(sugs)
        return block

    by_day: dict[str, list] = defaultdict(list)
    for j in jobs:
        obj = j if isinstance(j, dict) else {}
        d = _job_start_date_str(obj)
        if d:
            by_day[d].append(obj)

    lines = []
    greeting = get_phrase("greeting")
    if greeting:
        lines.append(greeting)
    for day_iso in sorted(by_day.keys()):
        day_jobs = by_day[day_iso][:max_per_day]
        try:
            d = date.fromisoformat(day_iso)
            day_title = d.strftime("%a %b %d")
        except ValueError:
            day_title = day_iso
        lines.append(f"\n*{_escape_md(day_title)}*")
        for obj in day_jobs:
            lines.append(_format_one_job_line(obj, tz_name=tz_name))
        if len(by_day[day_iso]) > max_per_day:
            lines.append(f"_… and {len(by_day[day_iso]) - max_per_day} more_")

    if include_suggestions:
        sugs = suggestions.ops_coach_suggestions(jobs_data, date_label=date_label)
        lines.append("\n" + get_phrase("next_actions_header"))
        for s in sugs:
            lines.append("• " + s)

    return "\n".join(lines).strip()


def format_help_message() -> str:
    """Help / capabilities text with example queries."""
    return (
        "I’m your read-only Polar Air HCP assistant. I can look up:\n\n"
        "• *Jobs* — \"Jobs today\", \"Next week\", \"Any day next week\", \"Job #12345\"\n"
        "• *Estimates* — \"List estimates\", \"Estimate 678\"\n"
        "• *Customers* — \"List customers\", \"Customer 789\"\n"
        "• *Company* — \"Company info\"\n"
        "• *Pricebook* — \"Services\", \"Materials\"\n"
        "• *Schedule* — \"Schedule tomorrow\", \"This weekend\"\n\n"
        "You can ask follow-ups like \"What about Tuesday?\" or \"Details for the second one.\"\n\n"
        "Commands: /start, /help, /whoami (your Telegram ID), /health\n\n"
        "I only read data; I don’t create or change anything."
    )


def format_unknown_capabilities(*, with_buttons_hint: bool = False) -> str:
    """Confident fallback: what we can do, not apology."""
    text = (
        "I can't calculate that directly yet, but here's what I *can* help with:\n"
        "jobs, estimates, customers, company, pricebook, and schedule.\n\n"
        "Try: _Jobs today_, _Next week_, _List estimates_, or _Help_."
    )
    if with_buttons_hint:
        text += "\n\nYou can also use the quick replies below."
    return text


def format_aggregation_unsupported(
    date_label: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> str:
    """
    When user asks for total collected / revenue for a period: explain why we can't,
    reference context (date range), offer alternatives, one follow-up suggestion.
    No job list — user can ask for it explicitly.
    """
    period_ref = date_label
    if start_date and end_date:
        try:
            period_ref = f"{date_label} ({start_date.strftime('%b %d')}–{end_date.strftime('%b %d')})"
        except (AttributeError, TypeError):
            pass
    line1 = (
        "I can't calculate total collected amounts yet — Housecall Pro doesn't expose "
        "a single \"collected total\" endpoint."
    )
    line2 = (
        f"For {_escape_md(period_ref)}, I can list jobs with their invoice totals, "
        "or show completed jobs from that period."
    )
    sugs = suggestions.money_aggregation_suggestions(date_label)
    line3 = sugs[0] if sugs else "Want me to list jobs for that period instead?"
    return f"{line1}\n\n{line2}\n\n{line3}"


def extract_job_ids_from_list(jobs_data: Any) -> list[str]:
    """Extract ordered list of job ids from list response (for memory / 'the second one')."""
    jobs = _list_from_response(jobs_data)
    ids = []
    for j in jobs:
        obj = j if isinstance(j, dict) else {}
        jid = obj.get("id") or obj.get("job_id")
        if jid is not None:
            ids.append(str(jid))
    return ids
