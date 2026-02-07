"""Thin HCP API wrappers for estimates. Read-only."""
from typing import Any, Optional

from .client import HCPClient
from . import endpoints


async def list_estimates(
    client: Optional[HCPClient] = None,
    per_page: Optional[int] = None,
    page: Optional[int] = None,
    status: Optional[str] = None,
) -> Any:
    """List estimates with optional pagination and status filter (e.g. unscheduled, open)."""
    return await endpoints.list_estimates(
        client=client, per_page=per_page, page=page, status=status
    )


async def get_estimate(estimate_id: str, client: Optional[HCPClient] = None) -> Any:
    """Get a single estimate by id."""
    return await endpoints.get_estimate(estimate_id, client=client)
