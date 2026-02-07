"""Tests for HCP endpoint discovery."""
import pytest

from src.hcp.client import HCPClientError
from src.hcp.config import HCPConfig
from src.hcp.discovery import probe_endpoints


class FakeClient:
    def __init__(self, responses: dict[str, object]):
        self.responses = responses
        self.calls: list[tuple[str, object]] = []

    async def get(self, path: str, params=None):
        self.calls.append((path, params))
        resp = self.responses.get(path)
        if isinstance(resp, Exception):
            raise resp
        if resp is None:
            raise HCPClientError("not found", status_code=404)
        return resp


@pytest.mark.asyncio
async def test_probe_endpoints_ok_with_prefix():
    cfg = HCPConfig(base_url="https://api.housecallpro.com", api_prefix="v1", strategy="legacy")
    client = FakeClient({"v1/jobs": {"jobs": []}})
    result = await probe_endpoints(client=client, config=cfg)
    assert result.ok is True
    assert result.working_prefix == "v1"


@pytest.mark.asyncio
async def test_probe_endpoints_auth_error():
    cfg = HCPConfig(base_url="https://api.housecallpro.com", api_prefix="", strategy="public")
    err = HCPClientError("unauthorized", status_code=401)
    client = FakeClient({"company": err})
    result = await probe_endpoints(client=client, config=cfg)
    assert result.ok is False
    assert result.reason == "auth"
