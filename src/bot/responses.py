"""Format Housecall Pro API responses into short, human-readable messages for Telegram."""
import os
from typing import Any, Optional

from src.utils.formatting import format_money
from src.utils.time import format_single_time, format_dt_range, format_schedule_line, DEFAULT_USER_TZ
from src.compose.formatter import get_best_total_amount, get_best_money_fields

DEBUG = os.environ.get("DEBUG", "").strip().lower() in ("1", "true", "yes")

# Telegram Markdown (legacy): escape these so API content doesn't break parse_mode
_MD_ESCAPE = str.maketrans({"_": r"\_", "*": r"\*", "`": r"\`", "[": r"\[", "\\": r"\\"})


def _escape_md(s: str) -> str:
    """Escape Markdown special chars so Telegram doesn't fail parsing."""
    return s.translate(_MD_ESCAPE)


def _safe(value: Any, default: str = "—", escape: bool = True) -> str:
    if value is None:
        return default
    out = str(value).strip() or default
    return _escape_md(out) if escape else out


def _list(items: Any) -> list[Any]:
    """Get a list from API response (either direct list or dict with common keys)."""
    if items is None:
        return []
    if isinstance(items, list):
        return items
    if isinstance(items, dict):
        for key in ("jobs", "estimates", "customers", "employees", "pros", "services", "materials", "appointments", "data", "items"):
            if key in items and isinstance(items[key], list):
                return items[key]
    return []


def _one(item: Any) -> dict[str, Any]:
    """Get single resource from response (dict or wrapped in key like 'job', 'customer')."""
    if item is None:
        return {}
    if isinstance(item, dict):
        for key in ("job", "estimate", "customer", "company", "pro"):
            if key in item:
                return item[key] if isinstance(item[key], dict) else {}
        return item
    return {}


def _job_short_id(obj: dict) -> str:
    """Short, readable job id (avoid long hex strings)."""
    raw = obj.get("id") or obj.get("job_id") or obj.get("number") or ""
    s = str(raw).strip()
    if not s:
        return "?"
    if s.startswith("job_"):
        s = s[4:]
    if len(s) > 12:
        s = s[-8:]
    return _escape_md(s)


def _job_one_line(obj: dict) -> str:
    """One-line description: address, customer, or job name (tries many API shapes)."""
    # Address: nested or flat
    addr = obj.get("address")
    if isinstance(addr, dict):
        part = (
            addr.get("address_line_1")
            or addr.get("street") or addr.get("street_address")
            or addr.get("line1") or addr.get("address")
        )
        if part:
            city = addr.get("city") or addr.get("locality")
            if city:
                part = f"{part}, {city}"
            return _safe(part)
    if isinstance(addr, str) and addr.strip():
        return _safe(addr)
    # Property / location
    prop = obj.get("property") or obj.get("location")
    if isinstance(prop, dict):
        a = prop.get("address_line_1") or prop.get("street") or prop.get("address") or prop.get("name")
        if a:
            return _safe(str(a))
    if isinstance(prop, str) and prop.strip():
        return _safe(prop)
    # Customer name
    cust = obj.get("customer")
    if isinstance(cust, dict):
        name = cust.get("display_name") or cust.get("name") or (f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip())
        if name:
            return _safe(name)
    if isinstance(cust, str) and cust.strip():
        return _safe(cust)
    # Job name/description/title
    for key in ("name", "title", "description", "summary", "job_name"):
        v = obj.get(key)
        if v and str(v).strip():
            return _safe(str(v))
    # Status at least
    status = obj.get("status")
    if status:
        return _safe(status)
    return "—"


# ---- Jobs ----
def format_jobs_list(data: Any, date_label: str = "scheduled") -> str:
    """Format list of jobs (e.g. from list_jobs response)."""
    jobs = _list(data)
    total_fetched = isinstance(data, dict) and data.get("total_fetched")
    if not jobs:
        if total_fetched is not None and total_fetched > 0:
            return f"No jobs scheduled for {_escape_md(date_label)}. (I found {total_fetched} job(s) in your account; none on that date.)"
        return f"No jobs found for {_escape_md(date_label)}."

    lines = [f"*{len(jobs)} job(s) for {_escape_md(date_label)}:*"]
    for j in jobs[:25]:  # cap for Telegram message length
        obj = j if isinstance(j, dict) else {}
        jid = _job_short_id(obj)
        desc = _job_one_line(obj)
        status = _safe(obj.get("status"))
        if status and status != "—":
            lines.append(f"• #{jid}: {desc} ({status})")
        else:
            lines.append(f"• #{jid}: {desc}")
    if len(jobs) > 25:
        lines.append(f"_… and {len(jobs) - 25} more._")
    return "\n".join(lines)


def _job_scheduled_start_end(job: dict) -> tuple[Optional[str], Optional[str]]:
    """Extract scheduled start/end timestamps from job, including nested schedule/appointment. All treated as UTC."""
    start = (
        job.get("scheduled_start")
        or job.get("scheduled_start_date")
        or job.get("start_date")
        or job.get("scheduled_at")
    )
    end = job.get("scheduled_end") or job.get("scheduled_end_date")
    if start is None and isinstance(job.get("schedule"), dict):
        s = job["schedule"]
        start = start or s.get("scheduled_start") or s.get("scheduled_start_date")
        end = end or s.get("scheduled_end") or s.get("scheduled_end_date")
    if start is None and isinstance(job.get("appointment"), dict):
        a = job["appointment"]
        start = start or a.get("scheduled_start") or a.get("scheduled_start_date") or a.get("date")
        end = end or a.get("scheduled_end")
    return (start, end)


def format_job_detail(data: Any, tz_name: str = DEFAULT_USER_TZ) -> str:
    """Format a single job (from get_job response). Scheduled/times in user TZ; amounts via format_money only."""
    job = _one(data) or data if isinstance(data, dict) else {}
    if not job:
        return "Job not found."

    jid = job.get("id") or job.get("job_id") or "?"
    status = _safe(job.get("status"))
    addr = job.get("address")
    if isinstance(addr, dict):
        addr = ", ".join(filter(None, [addr.get("address_line_1"), addr.get("city"), addr.get("state"), addr.get("zip_code")]))
    else:
        addr = _safe(addr)
    start_ts, end_ts = _job_scheduled_start_end(job)
    if start_ts or end_ts:
        start_str, end_str, day_label = format_dt_range(start_ts, end_ts, tz_name=tz_name)
        scheduled = f"{day_label} {start_str}" + (f" – {end_str}" if end_str else "") if start_str else _safe(start_ts or end_ts)
    else:
        scheduled = _safe(start_ts or end_ts)
    customer = job.get("customer")
    if isinstance(customer, dict):
        customer = customer.get("display_name") or (customer.get("first_name", "") + " " + (customer.get("last_name", "") or "")).strip()
    customer = _safe(customer)

    lines = [
        f"*Job {jid}*",
        f"Status: {status}",
        f"Address: {addr}",
        f"Scheduled: {scheduled}",
        f"Customer: {customer}",
    ]
    total_val, outstanding_val = get_best_money_fields(job)
    if DEBUG:
        import logging
        logging.getLogger(__name__).debug(
            "job detail money: total_val=%s (type=%s), outstanding_val=%s (type=%s)",
            total_val, type(total_val).__name__ if total_val is not None else None,
            outstanding_val, type(outstanding_val).__name__ if outstanding_val is not None else None,
        )
    if total_val is not None:
        lines.append(f"Total: {format_money(total_val)}")
    if outstanding_val is not None:
        lines.append(f"Outstanding: {format_money(outstanding_val)}")
    return "\n".join(lines)


def format_job_time_only(data: Any, tz_name: str = DEFAULT_USER_TZ) -> str:
    """Format only the schedule line for a job (for 'what time is it at?' follow-up)."""
    job = _one(data) or data if isinstance(data, dict) else {}
    if not job:
        return "Job not found."
    start_ts, end_ts = _job_scheduled_start_end(job)
    arrival = job.get("arrival_window") or job.get("arrival_window_hours")
    if isinstance(job.get("schedule"), dict):
        arrival = arrival or job["schedule"].get("arrival_window") or job["schedule"].get("arrival_window_hours")
    return format_schedule_line(start_ts, end_ts, tz_name=tz_name, arrival_window_hours=arrival)


# ---- Estimates ----
def format_estimates_list(data: Any) -> str:
    """Format list of estimates."""
    estimates = _list(data)
    if not estimates:
        return "No estimates found."

    lines = [f"*{len(estimates)} estimate(s):*"]
    for e in estimates[:25]:
        obj = e if isinstance(e, dict) else {}
        eid = obj.get("id") or obj.get("estimate_id") or "?"
        status = _safe(obj.get("status"))
        total_val = get_best_total_amount(obj)
        total = " " + format_money(total_val) if total_val is not None else ""
        lines.append(f"• Estimate {eid}: {status}{total}")
    if len(estimates) > 25:
        lines.append(f"_… and {len(estimates) - 25} more._")
    return "\n".join(lines)


def format_estimate_detail(data: Any) -> str:
    """Format a single estimate. Amounts via format_money."""
    est = _one(data) or data if isinstance(data, dict) else {}
    if not est:
        return "Estimate not found."

    eid = est.get("id") or est.get("estimate_id") or "?"
    status = _safe(est.get("status"))
    total_val = get_best_total_amount(est)
    total = format_money(total_val) if total_val is not None else "—"
    lines = [f"*Estimate {eid}*", f"Status: {status}", f"Total: {total}"]
    return "\n".join(lines)


# ---- Customers ----
def format_customers_list(data: Any) -> str:
    """Format list of customers."""
    customers = _list(data)
    if not customers:
        return "No customers found."

    lines = [f"*{len(customers)} customer(s):*"]
    for c in customers[:25]:
        obj = c if isinstance(c, dict) else {}
        cid = obj.get("id") or obj.get("customer_id") or "?"
        name = obj.get("display_name") or (f"{obj.get('first_name', '')} {obj.get('last_name', '')}".strip()) or "—"
        lines.append(f"• Customer {cid}: {name}")
    if len(customers) > 25:
        lines.append(f"_… and {len(customers) - 25} more._")
    return "\n".join(lines)


def format_customer_detail(data: Any) -> str:
    """Format a single customer."""
    cust = _one(data) or data if isinstance(data, dict) else {}
    if not cust:
        return "Customer not found."

    cid = cust.get("id") or cust.get("customer_id") or "?"
    name = cust.get("display_name") or (f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip()) or "—"
    email = _safe(cust.get("email"))
    phone = _safe(cust.get("phone"))
    lines = [f"*Customer {cid}*", f"Name: {name}", f"Email: {email}", f"Phone: {phone}"]
    return "\n".join(lines)


# ---- Company ----
def format_company(data: Any) -> str:
    """Format company/organization info."""
    company = _one(data) or data if isinstance(data, dict) else {}
    if not company:
        return "Company info is not available from the API."

    name = _safe(company.get("name"))
    lines = [f"*Company*", f"Name: {name}"]
    for key in ("address", "phone", "email"):
        if key in company and company[key]:
            lines.append(f"{key.capitalize()}: {company[key]}")
    return "\n".join(lines)


# ---- Employees (HCP: field techs & office admins) ----
def format_employees_list(data: Any) -> str:
    """Format list of employees (per Housecall Pro API glossary)."""
    employees = _list(data)
    if not employees:
        return "No employees found."

    lines = [f"*{len(employees)} employee(s):*"]
    for p in employees[:25]:
        obj = p if isinstance(p, dict) else {}
        name = obj.get("display_name") or (f"{obj.get('first_name', '')} {obj.get('last_name', '')}".strip()) or obj.get("name") or "—"
        lines.append(f"• {name}")
    return "\n".join(lines)


# ---- Pricebook ----
def format_services_list(data: Any) -> str:
    """Format list of pricebook services."""
    services = _list(data)
    if not services:
        return "No services found in pricebook."

    lines = [f"*Services ({len(services)}):*"]
    for s in services[:20]:
        obj = s if isinstance(s, dict) else {}
        name = _safe(obj.get("name"))
        price = obj.get("price") or obj.get("amount")
        price_str = " — " + format_money(price) if price is not None else ""
        lines.append(f"• {name}{price_str}")
    return "\n".join(lines)


def format_materials_list(data: Any) -> str:
    """Format list of pricebook materials."""
    materials = _list(data)
    if not materials:
        return "No materials found in pricebook."

    lines = [f"*Materials ({len(materials)}):*"]
    for m in materials[:20]:
        obj = m if isinstance(m, dict) else {}
        name = _safe(obj.get("name"))
        price = obj.get("price") or obj.get("amount")
        price_str = " — " + format_money(price) if price is not None else ""
        lines.append(f"• {name}{price_str}")
    return "\n".join(lines)


# ---- Appointments / schedule ----
def format_appointments_list(data: Any, date_label: str = "scheduled", tz_name: str = DEFAULT_USER_TZ) -> str:
    """Format list of appointments. Times in user TZ."""
    appointments = _list(data)
    if not appointments:
        return f"No appointments found for {_escape_md(date_label)}."

    lines = [f"*Appointments for {_escape_md(date_label)}:*"]
    for a in appointments[:25]:
        obj = a if isinstance(a, dict) else {}
        ts = obj.get("scheduled_start") or obj.get("scheduled_start_date")
        time_str = format_single_time(ts, tz_name=tz_name) if ts else _safe(ts)
        job_id = obj.get("job_id") or obj.get("job", {}).get("id") if isinstance(obj.get("job"), dict) else None
        pro = obj.get("pro") or obj.get("technician")
        if isinstance(pro, dict):
            pro = pro.get("display_name") or pro.get("name")
        pro = _safe(pro)
        lines.append(f"• {time_str} — Job {job_id or '?'} — {pro}")
    return "\n".join(lines)


# ---- Stats / summary ----
def format_stats(counts: dict[str, int]) -> str:
    """Format a one-message stats summary. Keys: jobs_today, jobs_this_week, estimates, customers."""
    jobs_today = counts.get("jobs_today", 0)
    jobs_week = counts.get("jobs_this_week", 0)
    estimates = counts.get("estimates", 0)
    customers = counts.get("customers", 0)
    lines = [
        "*Quick stats*",
        f"• Jobs today: {jobs_today}",
        f"• Jobs this week: {jobs_week}",
        f"• Estimates: {estimates}",
        f"• Customers: {customers}",
    ]
    return "\n".join(lines)


def format_error(message: str) -> str:
    """Format an error message for the user (escaped for Markdown)."""
    return f"Sorry, I couldn't get that: {_escape_md(message)}"
