"""Thin HCP API wrappers for customers. Read-only."""
from typing import Any, Optional

from .client import HCPClient
from . import endpoints


async def list_customers(
    client: Optional[HCPClient] = None,
    per_page: Optional[int] = None,
    page: Optional[int] = None,
) -> Any:
    """List customers with optional pagination."""
    return await endpoints.list_customers(client=client, per_page=per_page, page=page)


async def get_customer(customer_id: str, client: Optional[HCPClient] = None) -> Any:
    """Get a single customer by id."""
    return await endpoints.get_customer(customer_id, client=client)
