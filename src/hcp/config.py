"""Housecall Pro API configuration (explicit, no magic fallbacks)."""
from dataclasses import dataclass
import os

DEFAULT_BASE_URL = "https://api.housecallpro.com"
DEFAULT_STRATEGY = "public"  # "public" (no prefix) or "legacy" (requires explicit prefix)
DEFAULT_LEGACY_PREFIX = "v1"


@dataclass(frozen=True)
class HCPConfig:
    """Resolved HCP API configuration."""
    base_url: str
    api_prefix: str
    strategy: str


def _normalize_prefix(prefix: str) -> str:
    return prefix.strip().strip("/")


def get_hcp_config() -> HCPConfig:
    base_url = (os.getenv("HCP_API_BASE_URL", "") or DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    strategy = (os.getenv("HCP_API_VERSION_STRATEGY", "") or DEFAULT_STRATEGY).strip().lower() or DEFAULT_STRATEGY
    prefix_env = os.getenv("HCP_API_PREFIX", "").strip()
    api_prefix = ""
    if prefix_env:
        api_prefix = _normalize_prefix(prefix_env)
        strategy = "legacy"
    elif strategy == "legacy":
        # Explicitly configured legacy mode defaults to /v1
        api_prefix = DEFAULT_LEGACY_PREFIX
    return HCPConfig(base_url=base_url.rstrip("/"), api_prefix=api_prefix, strategy=strategy)


def build_path(resource: str, *, config: HCPConfig | None = None) -> str:
    """Build a resource path with configured prefix (if any)."""
    cfg = config or get_hcp_config()
    resource = resource.lstrip("/")
    if cfg.api_prefix:
        return f"{cfg.api_prefix}/{resource}"
    return resource
