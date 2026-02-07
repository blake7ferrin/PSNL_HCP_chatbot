"""Read-only Housecall Pro API endpoint wrappers. GET only.

Endpoint paths and semantics follow the official API reference:
https://docs.housecallpro.com/ (Housecall Pro Public API)
"""
from typing import Any, Optional

from .client import HCPClient, HCPClientError


# Default client instance (token from env). Caller can inject a client for tests.
def _client() -> HCPClient:
    return HCPClient()


def _job_start_date_str(obj: dict) -> Optional[str]:
    """Get the scheduled/start date of a job as YYYY-MM-DD, or None. Handles many API shapes."""
    # Common field names (flat and nested)
    start = (
        obj.get("scheduled_start_date")
        or obj.get("scheduled_start")
        or obj.get("start_date")
        or obj.get("scheduled_at")
        or obj.get("appointment_date")
        or obj.get("date")
        or obj.get("start_time")
    )
    if start is None and isinstance(obj.get("schedule"), dict):
        start = obj["schedule"].get("scheduled_start") or obj["schedule"].get("scheduled_start_date")
    if start is None and isinstance(obj.get("appointment"), dict):
        start = obj["appointment"].get("scheduled_start") or obj["appointment"].get("date")
    if start is None:
        return None
    if isinstance(start, str):
        # "2026-01-30" or "2026-01-30T14:00:00Z"
        return start.split("T")[0].split(" ")[0][:10]
    return None


def _jobs_matching_date(jobs_data: Any, date_str: str) -> list:
    """Filter jobs list to those scheduled on date_str (YYYY-MM-DD). Handles various API shapes."""
    jobs = _list_from_response(jobs_data)
    out = []
    for j in jobs:
        obj = j if isinstance(j, dict) else {}
        start = _job_start_date_str(obj)
        if start == date_str:
            out.append(j)
    return out


def _list_from_response(data: Any) -> list:
    """Extract list from API response (jobs, estimates, etc.)."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("jobs", "estimates", "customers", "data", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


# Paths to try for jobs (some APIs use api/v1 prefix or no version)
_JOBS_PATHS = ("v1/jobs", "api/v1/jobs", "jobs")


async def _get_jobs_raw(c: HCPClient, path: str, params: Optional[dict]) -> Any:
    """GET jobs from one path. Raises HCPClientError on failure."""
    return await c.get(path, params=params)


async def list_jobs(
    client: Optional[HCPClient] = None,
    scheduled_start_date: Optional[str] = None,
    status: Optional[str] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List jobs. Date filter is always applied client-side (API often 404s with date param)."""
    c = client or _client()
    params: dict[str, Any] = {}
    if status is not None:
        params["status"] = status
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    last_error = None
    for path in _JOBS_PATHS:
        try:
            out = await _get_jobs_raw(c, path, params if params else None)
            if scheduled_start_date is not None:
                all_jobs = _list_from_response(out)
                matched = _jobs_matching_date(out, scheduled_start_date)
                if isinstance(out, dict):
                    out = {**out, "jobs": matched, "total_fetched": len(all_jobs)}
                else:
                    out = {"jobs": matched, "total_fetched": len(all_jobs)}
            return out
        except HCPClientError as e:
            last_error = e
            if e.status_code == 404:
                continue
            raise
    if last_error:
        raise last_error
    raise HCPClientError("Housecall Pro jobs endpoint not found (tried multiple paths).")


async def get_job(job_id: str, client: Optional[HCPClient] = None) -> Any:
    """Get a single job by id."""
    c = client or _client()
    return await c.get(f"v1/jobs/{job_id}")


# ---- Estimates ----
async def list_estimates(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List estimates with optional pagination."""
    c = client or _client()
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    return await c.get("v1/estimates", params=params if params else None)


async def get_estimate(estimate_id: str, client: Optional[HCPClient] = None) -> Any:
    """Get a single estimate by id."""
    c = client or _client()
    return await c.get(f"v1/estimates/{estimate_id}")


# ---- Customers ----
async def list_customers(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List customers with optional pagination."""
    c = client or _client()
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    return await c.get("v1/customers", params=params if params else None)


async def get_customer(customer_id: str, client: Optional[HCPClient] = None) -> Any:
    """Get a single customer by id."""
    c = client or _client()
    return await c.get(f"v1/customers/{customer_id}")


# ---- Company / organization ----
async def get_company(client: Optional[HCPClient] = None) -> Any:
    """Get company/organization info. May 404 if not in API."""
    c = client or _client()
    try:
        return await c.get("v1/company")
    except HCPClientError as e:
        if e.status_code == 404:
            return {}
        raise


# ---- Employees (docs.housecallpro.com glossary: "Employee" = field techs & office admins) ----
async def list_employees(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List employees (field techs and office staff). May 404 if not in plan."""
    c = client or _client()
    try:
        params: dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if per_page is not None:
            params["per_page"] = per_page
        return await c.get("v1/employees", params=params if params else None)
    except HCPClientError as e:
        if e.status_code == 404:
            return {}
        raise


# Backward-compatible alias (HCP docs use "Employee")
list_pros = list_employees


# ---- Pricebook (services / materials) ----
async def list_services(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List pricebook services. May 404 if endpoint name differs in API."""
    c = client or _client()
    try:
        params: dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if per_page is not None:
            params["per_page"] = per_page
        return await c.get("v1/services", params=params if params else None)
    except HCPClientError as e:
        if e.status_code == 404:
            return {}
        raise


async def list_materials(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List pricebook materials. May 404 if endpoint name differs in API."""
    c = client or _client()
    try:
        params: dict[str, Any] = {}
        if page is not None:
            params["page"] = page
        if per_page is not None:
            params["per_page"] = per_page
        return await c.get("v1/materials", params=params if params else None)
    except HCPClientError as e:
        if e.status_code == 404:
            return {}
        raise


# ---- Appointments / schedule ----
async def list_appointments(
    client: Optional[HCPClient] = None,
    scheduled_start_date: Optional[str] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List appointments/schedule. May 404 if endpoint name differs in API."""
    c = client or _client()
    try:
        params: dict[str, Any] = {}
        if scheduled_start_date is not None:
            params["scheduled_start_date"] = scheduled_start_date
        if page is not None:
            params["page"] = page
        if per_page is not None:
            params["per_page"] = per_page
        return await c.get("v1/appointments", params=params if params else None)
    except HCPClientError as e:
        if e.status_code == 404:
            return {}
        raise
