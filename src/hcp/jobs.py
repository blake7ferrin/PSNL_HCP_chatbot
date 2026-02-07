"""Thin HCP API wrappers for jobs. Read-only."""
from typing import Any, Optional

from .client import HCPClient
from . import endpoints


async def list_jobs(
    client: Optional[HCPClient] = None,
    scheduled_start_date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    per_page: Optional[int] = None,
) -> Any:
    """List jobs, optionally filtered by date range or single date."""
    if start_date and end_date:
        return await endpoints.list_jobs_in_date_range(
            start_date, end_date, client=client, max_fetched=per_page or 500
        )
    return await endpoints.list_jobs(
        client=client,
        scheduled_start_date=scheduled_start_date,
        status=status,
        per_page=per_page,
    )


async def get_job(job_id: str, client: Optional[HCPClient] = None) -> Any:
    """Get a single job by id."""
    return await endpoints.get_job(job_id, client=client)
