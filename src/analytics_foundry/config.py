"""Config: default league ID, data paths, and startup validation."""

from __future__ import annotations

import logging
import os

from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.exceptions import ConfigurationError

_LOG = logging.getLogger(__name__)

# Default league ID when API requests omit league_id (Sleeper).
_BUILTIN_DEFAULT_LEAGUE = "1261894762944802816"


def get_default_league_id() -> str:
    """Return the configured default league ID (non-empty; falls back to built-in default)."""
    raw = os.environ.get("FOUNDRY_DEFAULT_LEAGUE_ID", _BUILTIN_DEFAULT_LEAGUE).strip()
    return raw or _BUILTIN_DEFAULT_LEAGUE


def get_retention_days() -> int | None:
    """Optional retention window in days (documentation / future pruning). None = disabled."""
    v = os.environ.get("FOUNDRY_RETENTION_DAYS", "").strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def prometheus_enabled() -> bool:
    return os.environ.get("FOUNDRY_PROMETHEUS", "").strip().lower() in ("1", "true", "yes")


def audit_log_enabled() -> bool:
    return os.environ.get("FOUNDRY_AUDIT_LOG", "").strip().lower() in ("1", "true", "yes")


def validate_startup_config() -> None:
    """Ensure data root is usable; log effective settings. Call once at app startup."""
    root = bronze_store.get_data_root()
    if root is not None:
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ConfigurationError(f"Cannot create or use FOUNDRY_DATA_DIR at {root}: {e}") from e
    _LOG.info(
        "startup config data_root=%s default_league_id=%s tenant=%s retention_days=%s",
        str(root) if root else None,
        get_default_league_id(),
        os.environ.get("FOUNDRY_TENANT_ID", "").strip() or None,
        get_retention_days(),
    )
