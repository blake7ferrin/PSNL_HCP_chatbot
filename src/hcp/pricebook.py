"""Thin HCP API wrappers for pricebook (services, materials). Read-only."""
from typing import Any, Optional

from .client import HCPClient
from . import endpoints


async def list_services(
    client: Optional[HCPClient] = None,
    per_page: Optional[int] = None,
    page: Optional[int] = None,
) -> Any:
    """List pricebook services."""
    return await endpoints.list_services(client=client, per_page=per_page, page=page)


async def list_materials(
    client: Optional[HCPClient] = None,
    per_page: Optional[int] = None,
    page: Optional[int] = None,
) -> Any:
    """List pricebook materials."""
    return await endpoints.list_materials(client=client, per_page=per_page, page=page)
