"""Config helpers for runtime environment overrides, default league ID, data paths, and startup validation."""

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


def get_admin_api_key() -> str | None:
    """Return optional admin API key. Empty or unset means admin auth is disabled."""
    value = os.environ.get("FOUNDRY_ADMIN_API_KEY")
    if value is None or not value.strip():
        return None
    return value.strip()


def admin_auth_enabled() -> bool:
    """Return whether optional admin auth is enabled."""
    return get_admin_api_key() is not None


def scheduler_enabled() -> bool:
    """Return whether the in-process local scheduler is enabled."""
    return os.environ.get("FOUNDRY_SCHEDULER_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def scheduler_interval_seconds() -> float:
    """Return the configured scheduler polling interval in seconds."""
    raw = os.environ.get("FOUNDRY_SCHEDULER_INTERVAL_SECONDS", "60")
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 60.0


def get_ambient_ollama_base_url() -> str:
    """Return the Ollama base URL used by ambient confidence evaluation."""
    return os.environ.get("AMBIENT_OLLAMA_BASE_URL", "http://localhost:11434").strip() or "http://localhost:11434"


def get_ambient_ollama_model() -> str | None:
    """Return the optional default Ollama model for ambient evaluation."""
    value = os.environ.get("AMBIENT_OLLAMA_MODEL")
    if value is None or not value.strip():
        return None
    return value.strip()


def get_google_credentials_path() -> str:
    """Return local OAuth client credentials path for Google Workspace adapters."""
    return os.environ.get("FOUNDRY_GOOGLE_CREDENTIALS_PATH", "google_credentials.json")


def get_google_token_dir() -> str:
    """Return local OAuth token directory for Google Workspace adapters."""
    return os.environ.get("FOUNDRY_GOOGLE_TOKEN_DIR", ".foundry_google_tokens")


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
