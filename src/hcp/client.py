"""Async HTTP client for Housecall Pro API. Read-only (GET only).

API reference: https://docs.housecallpro.com/ (Housecall Pro Public API).
Auth: Bearer token (API key for MAX/XL Pros). Base URL: https://api.housecallpro.com

This module must not implement POST, PATCH, PUT, or DELETE. All data access
is read-only for the Polar Air admin chatbot.
"""
import os
import time
from typing import Any, Optional

import httpx

# Enforce read-only: only GET is allowed. Do not add write methods.
ALLOWED_METHODS = frozenset({"GET"})

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
RETRY_BACKOFF = 1.0


class HCPClientError(Exception):
    """Raised when the HCP API returns an error or client is misconfigured."""
    def __init__(self, message: str, status_code: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class HCPClient:
    """Read-only client for Housecall Pro API. Uses Bearer token auth, retries, timeouts."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.housecallpro.com",
        token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        self.base_url = base_url.rstrip("/")
        self._token = token or os.getenv("HCP_API_KEY")
        if not self._token:
            raise ValueError("HCP API token required: set HCP_API_KEY or pass token=")
        self._timeout = timeout
        self._max_retries = max(0, max_retries)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        """
        Perform a GET request with retries. Only GET is allowed (read-only).
        path: e.g. "/v1/jobs" (leading slash optional).
        Returns parsed JSON or raises HCPClientError.
        """
        if "GET" not in ALLOWED_METHODS:
            raise HCPClientError("Read-only client: GET is the only allowed method")
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, headers=self._headers(), params=params or {})
                return self._handle_response(response)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < self._max_retries:
                    time.sleep(RETRY_BACKOFF * (attempt + 1))
                else:
                    raise HCPClientError(
                        f"Request failed after {self._max_retries + 1} attempts: {e!s}"
                    ) from e
        if last_error:
            raise HCPClientError(str(last_error)) from last_error
        raise HCPClientError("Request failed")

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.status_code == 401:
            raise HCPClientError(
                "Housecall Pro authentication failed. Check your API key.",
                status_code=401,
                body=response.text,
            )
        if response.status_code == 429:
            raise HCPClientError(
                "Housecall Pro rate limit reached. Please try again in a moment.",
                status_code=429,
                body=response.text,
            )
        if response.status_code >= 400:
            url = str(response.request.url) if response.request else "?"
            raise HCPClientError(
                f"Housecall Pro API error: {response.status_code} for GET {url}",
                status_code=response.status_code,
                body=response.text,
            )
        if not response.content:
            return {}
        return response.json()
