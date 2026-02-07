"""Endpoint discovery and diagnostics (explicit, minimal probes)."""
from dataclasses import dataclass
from typing import Optional
import logging

from .client import HCPClient, HCPClientError
from .config import HCPConfig, build_path, get_hcp_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    working_prefix: Optional[str]
    reason: str
    status_code: Optional[int] = None


def _reason_for_error(err: HCPClientError) -> str:
    code = err.status_code
    if code == 401:
        return "auth"
    if code == 403:
        return "forbidden"
    if code == 404:
        return "endpoint_not_found"
    if code == 429:
        return "rate_limited"
    return "error"


async def probe_endpoints(
    *,
    client: Optional[HCPClient] = None,
    config: Optional[HCPConfig] = None,
) -> ProbeResult:
    """
    Probe a small set of safe endpoints with the configured prefix only.
    Returns ProbeResult(ok=True, working_prefix=...) on success, otherwise reason.
    """
    cfg = config or get_hcp_config()
    c = client or HCPClient(base_url=cfg.base_url)
    prefix = cfg.api_prefix or None
    probes = [
        ("company", None),
        ("jobs", {"per_page": 1}),
        ("customers", {"per_page": 1}),
    ]
    last_error: Optional[HCPClientError] = None
    for resource, params in probes:
        path = build_path(resource, config=cfg)
        try:
            await c.get(path, params=params)
            return ProbeResult(ok=True, working_prefix=prefix, reason="ok")
        except HCPClientError as e:
            last_error = e
            reason = _reason_for_error(e)
            logger.debug("probe %s failed: %s (%s)", path, reason, e.status_code)
            # For auth/forbidden/rate limit, fail fast with diagnosis
            if reason in ("auth", "forbidden", "rate_limited"):
                return ProbeResult(ok=False, working_prefix=prefix, reason=reason, status_code=e.status_code)
            # 404: try next resource in the probe list
            continue
    if last_error:
        reason = _reason_for_error(last_error)
        return ProbeResult(ok=False, working_prefix=prefix, reason=reason, status_code=last_error.status_code)
    return ProbeResult(ok=False, working_prefix=prefix, reason="unknown")
