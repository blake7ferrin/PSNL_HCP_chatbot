"""Read-only Housecall Pro API endpoint wrappers. GET only.

Endpoint paths and semantics follow the official API reference:
https://docs.housecallpro.com/ (Housecall Pro Public API)
"""
from typing import Any, Optional
import logging

from .client import HCPClient, HCPClientError
from .config import HCPConfig, build_path, get_hcp_config

logger = logging.getLogger(__name__)


# Default client instance (token from env). Caller can inject a client for tests.
def _client_and_config(client: Optional[HCPClient] = None) -> tuple[HCPClient, HCPConfig]:
    cfg = get_hcp_config()
    return (client or HCPClient(base_url=cfg.base_url), cfg)


def _path(resource: str, cfg: HCPConfig) -> str:
    return build_path(resource, config=cfg)


def _raise_not_found(resource: str, err: HCPClientError) -> None:
    logger.warning("hcp endpoint not found for resource=%s status=%s", resource, err.status_code)
    raise HCPClientError(
        "HCP endpoint not found for this account. Check API plan (MAX) and base URL.",
        status_code=err.status_code,
        body=err.body,
    ) from err


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
    """Extract list from API response (jobs, estimates, etc.). HCP may use pagination keys like results."""
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("jobs", "estimates", "customers", "data", "items", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


async def list_jobs(
    client: Optional[HCPClient] = None,
    scheduled_start_date: Optional[str] = None,
    status: Optional[str] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List jobs. Date filter is always applied client-side (API often 404s with date param)."""
    c, cfg = _client_and_config(client)
    params: dict[str, Any] = {}
    if status is not None:
        params["status"] = status
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    path = _path("jobs", cfg)
    try:
        out = await c.get(path, params=params if params else None)
    except HCPClientError as e:
        if e.status_code == 404:
            _raise_not_found("jobs", e)
        raise
    if scheduled_start_date is not None:
        all_jobs = _list_from_response(out)
        matched = _jobs_matching_date(out, scheduled_start_date)
        if isinstance(out, dict):
            out = {**out, "jobs": matched, "total_fetched": len(all_jobs)}
        else:
            out = {"jobs": matched, "total_fetched": len(all_jobs)}
    return out


async def get_job(job_id: str, client: Optional[HCPClient] = None) -> Any:
    """Get a single job by id."""
    c, cfg = _client_and_config(client)
    path = _path(f"jobs/{job_id}", cfg)
    try:
        return await c.get(path)
    except HCPClientError as e:
        if e.status_code == 404:
            _raise_not_found("jobs", e)
        raise


async def count_jobs_in_date_range(
    start_iso: str,
    end_iso: str,
    client: Optional[HCPClient] = None,
    max_fetched: int = 500,
) -> int:
    """Count jobs with scheduled date in [start_iso, end_iso]. Fetches one page (up to max_fetched)."""
    data = await list_jobs(client=client, per_page=max_fetched)
    jobs = _list_from_response(data)
    return sum(
        1
        for j in jobs
        for d in (_job_start_date_str(j if isinstance(j, dict) else {}),)
        if d and start_iso <= d <= end_iso
    )


async def list_jobs_in_date_range(
    start_iso: str,
    end_iso: str,
    client: Optional[HCPClient] = None,
    max_fetched: int = 500,
) -> Any:
    """List jobs with scheduled date in [start_iso, end_iso]. Same response shape as list_jobs."""
    data = await list_jobs(client=client, per_page=max_fetched)
    jobs = _list_from_response(data)
    filtered = [
        j for j in jobs
        for d in (_job_start_date_str(j if isinstance(j, dict) else {}),)
        if d and start_iso <= d <= end_iso
    ]
    return {"jobs": filtered, "total_fetched": len(jobs)}


async def list_estimates(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    status: Optional[str] = None,
) -> Any:
    """List estimates with optional pagination and status filter.
    When status is set, fetches estimates and filters client-side by estimate.status.
    """
    c, cfg = _client_and_config(client)
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    if not params and status:
        params["per_page"] = 500
    path = _path("estimates", cfg)
    try:
        out = await c.get(path, params=params if params else None)
    except HCPClientError as e:
        if e.status_code == 404:
            _raise_not_found("estimates", e)
        raise
    if status and out:
        estimates = _list_from_response(out)
        status_lower = status.lower()
        filtered = [e for e in estimates if (e.get("status") or "").lower() == status_lower]
        if isinstance(out, dict):
            out = {**out, "estimates": filtered}
        else:
            out = {"estimates": filtered}
    return out


async def get_estimate(estimate_id: str, client: Optional[HCPClient] = None) -> Any:
    """Get a single estimate by id."""
    c, cfg = _client_and_config(client)
    path = _path(f"estimates/{estimate_id}", cfg)
    try:
        return await c.get(path)
    except HCPClientError as e:
        if e.status_code == 404:
            _raise_not_found("estimates", e)
        raise


async def list_customers(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List customers with optional pagination."""
    c, cfg = _client_and_config(client)
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    path = _path("customers", cfg)
    try:
        return await c.get(path, params=params if params else None)
    except HCPClientError as e:
        if e.status_code == 404:
            _raise_not_found("customers", e)
        raise


async def get_customer(customer_id: str, client: Optional[HCPClient] = None) -> Any:
    """Get a single customer by id."""
    c, cfg = _client_and_config(client)
    path = _path(f"customers/{customer_id}", cfg)
    try:
        return await c.get(path)
    except HCPClientError as e:
        if e.status_code == 404:
            _raise_not_found("customers", e)
        raise


async def get_company(client: Optional[HCPClient] = None) -> Any:
    """Get company/organization info. May 404 if not in API."""
    c, cfg = _client_and_config(client)
    path = _path("company", cfg)
    try:
        return await c.get(path)
    except HCPClientError as e:
        if e.status_code == 404:
            _raise_not_found("company", e)
        raise


async def list_employees(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List employees (field techs and office staff). May 404 if not in plan."""
    c, cfg = _client_and_config(client)
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    path = _path("employees", cfg)
    try:
        return await c.get(path, params=params if params else None)
    except HCPClientError as e:
        if e.status_code == 404:
            _raise_not_found("employees", e)
        raise


# Backward-compatible alias (HCP docs use "Employee")
list_pros = list_employees


async def list_services(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List pricebook services. May 404 if endpoint name differs in API."""
    c, cfg = _client_and_config(client)
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    path = _path("services", cfg)
    try:
        return await c.get(path, params=params if params else None)
    except HCPClientError as e:
        if e.status_code == 404:
            _raise_not_found("services", e)
        raise


async def list_materials(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List pricebook materials. May 404 if endpoint name differs in API."""
    c, cfg = _client_and_config(client)
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    path = _path("materials", cfg)
    try:
        return await c.get(path, params=params if params else None)
    except HCPClientError as e:
        if e.status_code == 404:
            _raise_not_found("materials", e)
        raise


async def list_appointments(
    client: Optional[HCPClient] = None,
    scheduled_start_date: Optional[str] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List appointments/schedule. May 404 if endpoint name differs in API."""
    c, cfg = _client_and_config(client)
    params: dict[str, Any] = {}
    if scheduled_start_date is not None:
        params["scheduled_start_date"] = scheduled_start_date
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    path = _path("appointments", cfg)
    try:
        return await c.get(path, params=params if params else None)
    except HCPClientError as e:
        if e.status_code == 404:
            _raise_not_found("appointments", e)
        raise
