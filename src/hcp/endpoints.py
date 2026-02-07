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


# Paths to try: HCP Public API uses root paths (e.g. /jobs, /customers/{id}/addresses), no /v1 prefix
_JOBS_PATHS = ("jobs", "housecall/v1/jobs", "v1/jobs", "api/v1/jobs")


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


# Paths to try for single job GET (same variants as list)
_JOB_DETAIL_PATHS = ("jobs/{id}", "housecall/v1/jobs/{id}", "v1/jobs/{id}", "api/v1/jobs/{id}")


async def get_job(job_id: str, client: Optional[HCPClient] = None) -> Any:
    """Get a single job by id. Tries multiple API path variants on 404."""
    c = client or _client()
    last_error = None
    for path_tpl in _JOB_DETAIL_PATHS:
        path = path_tpl.format(id=job_id)
        try:
            return await c.get(path)
        except HCPClientError as e:
            last_error = e
            if e.status_code == 404:
                continue
            raise
    if last_error:
        raise last_error
    raise HCPClientError(f"Housecall Pro job {job_id} not found (tried multiple paths).")


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


# ---- Estimates (root paths first per HCP Public API) ----
_ESTIMATES_PATHS = ("estimates", "housecall/v1/estimates", "v1/estimates", "api/v1/estimates")
_ESTIMATE_DETAIL_PATHS = ("estimates/{id}", "housecall/v1/estimates/{id}", "v1/estimates/{id}", "api/v1/estimates/{id}")


async def list_estimates(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    status: Optional[str] = None,
) -> Any:
    """List estimates with optional pagination and status filter.
    When status is set, fetches estimates and filters client-side by estimate.status.
    """
    c = client or _client()
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    if not params and status:
        params["per_page"] = 500
    last_error = None
    for path in _ESTIMATES_PATHS:
        try:
            out = await c.get(path, params=params if params else None)
            if status and out:
                estimates = _list_from_response(out)
                status_lower = status.lower()
                filtered = [e for e in estimates if (e.get("status") or "").lower() == status_lower]
                if isinstance(out, dict):
                    out = {**out, "estimates": filtered}
                else:
                    out = {"estimates": filtered}
            return out
        except HCPClientError as e:
            last_error = e
            if e.status_code == 404:
                continue
            raise
    if last_error:
        raise last_error
    raise HCPClientError("Housecall Pro estimates endpoint not found (tried multiple paths).")


async def get_estimate(estimate_id: str, client: Optional[HCPClient] = None) -> Any:
    """Get a single estimate by id. Tries Housecall v1 API path variants on 404."""
    c = client or _client()
    last_error = None
    for path_tpl in _ESTIMATE_DETAIL_PATHS:
        path = path_tpl.format(id=estimate_id)
        try:
            return await c.get(path)
        except HCPClientError as e:
            last_error = e
            if e.status_code == 404:
                continue
            raise
    if last_error:
        raise last_error
    raise HCPClientError(f"Housecall Pro estimate {estimate_id} not found (tried multiple paths).")


# ---- Customers (root paths first per HCP Public API) ----
_CUSTOMERS_PATHS = ("customers", "housecall/v1/customers", "v1/customers", "api/v1/customers")
_CUSTOMER_DETAIL_PATHS = ("customers/{id}", "housecall/v1/customers/{id}", "v1/customers/{id}", "api/v1/customers/{id}")


async def _get_first_ok(c: HCPClient, paths: tuple[str, ...], **kwargs: Any) -> Any:
    """GET from first path that succeeds; on 404 try next. Raises last HCPClientError if all 404."""
    last_error = None
    for path in paths:
        try:
            return await c.get(path, **kwargs)
        except HCPClientError as e:
            last_error = e
            if e.status_code == 404:
                continue
            raise
    if last_error:
        raise last_error
    raise HCPClientError("Endpoint not found (tried multiple paths).")


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
    return await _get_first_ok(c, _CUSTOMERS_PATHS, params=params if params else None)


async def get_customer(customer_id: str, client: Optional[HCPClient] = None) -> Any:
    """Get a single customer by id. Tries Housecall v1 API path variants on 404."""
    c = client or _client()
    paths = tuple(p.format(id=customer_id) for p in _CUSTOMER_DETAIL_PATHS)
    return await _get_first_ok(c, paths)


# ---- Company / organization (root path first per HCP Public API) ----
_COMPANY_PATHS = ("company", "housecall/v1/company", "v1/company", "api/v1/company")


async def get_company(client: Optional[HCPClient] = None) -> Any:
    """Get company/organization info. May 404 if not in API."""
    c = client or _client()
    last_error = None
    for path in _COMPANY_PATHS:
        try:
            return await c.get(path)
        except HCPClientError as e:
            last_error = e
            if e.status_code == 404:
                continue
            raise
    return {}  # all 404 -> return empty


# ---- Employees (root path first; glossary: "Employee" = field techs & office admins) ----
_EMPLOYEES_PATHS = ("employees", "housecall/v1/employees", "v1/employees", "api/v1/employees")


async def list_employees(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List employees (field techs and office staff). May 404 if not in plan."""
    c = client or _client()
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    last_error = None
    for path in _EMPLOYEES_PATHS:
        try:
            return await c.get(path, params=params if params else None)
        except HCPClientError as e:
            last_error = e
            if e.status_code == 404:
                continue
            raise
    return {}


# Backward-compatible alias (HCP docs use "Employee")
list_pros = list_employees


# ---- Pricebook (root paths first: services / materials) ----
_SERVICES_PATHS = ("services", "housecall/v1/services", "v1/services", "api/v1/services")
_MATERIALS_PATHS = ("materials", "housecall/v1/materials", "v1/materials", "api/v1/materials")


async def list_services(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List pricebook services. May 404 if endpoint name differs in API."""
    c = client or _client()
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    try:
        return await _get_first_ok(c, _SERVICES_PATHS, params=params if params else None)
    except HCPClientError:
        return {}


async def list_materials(
    client: Optional[HCPClient] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List pricebook materials. May 404 if endpoint name differs in API."""
    c = client or _client()
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    try:
        return await _get_first_ok(c, _MATERIALS_PATHS, params=params if params else None)
    except HCPClientError:
        return {}


# ---- Appointments / schedule (root path first) ----
_APPOINTMENTS_PATHS = ("appointments", "housecall/v1/appointments", "v1/appointments", "api/v1/appointments")


async def list_appointments(
    client: Optional[HCPClient] = None,
    scheduled_start_date: Optional[str] = None,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List appointments/schedule. May 404 if endpoint name differs in API."""
    c = client or _client()
    params: dict[str, Any] = {}
    if scheduled_start_date is not None:
        params["scheduled_start_date"] = scheduled_start_date
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page
    try:
        return await _get_first_ok(c, _APPOINTMENTS_PATHS, params=params if params else None)
    except HCPClientError:
        return {}
