"""Thin HCP API wrapper for company/organization info. Read-only."""
from typing import Any, Optional

from .client import HCPClient
from . import endpoints


async def get_company(client: Optional[HCPClient] = None) -> Any:
    """Get company/organization info. May return {} if not in API."""
    return await endpoints.get_company(client=client)
