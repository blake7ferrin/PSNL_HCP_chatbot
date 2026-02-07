"""Integration-style tests for HCP endpoints with a fake client."""
import pytest

from src.hcp import endpoints
from src.hcp.client import HCPClientError


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
async def test_list_jobs_uses_configured_prefix(monkeypatch):
    monkeypatch.setenv("HCP_API_PREFIX", "v1")
    client = FakeClient({"v1/jobs": {"jobs": []}})
    data = await endpoints.list_jobs(client=client)
    assert data["jobs"] == []
    assert client.calls[0][0] == "v1/jobs"


@pytest.mark.asyncio
async def test_list_jobs_404_returns_clear_message(monkeypatch):
    monkeypatch.delenv("HCP_API_PREFIX", raising=False)
    client = FakeClient({"jobs": HCPClientError("missing", status_code=404)})
    with pytest.raises(HCPClientError) as excinfo:
        await endpoints.list_jobs(client=client)
    assert "HCP endpoint not found for this account" in str(excinfo.value)
