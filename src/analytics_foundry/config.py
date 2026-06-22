"""Config helpers for runtime environment overrides."""

import os

# Default league ID for data ingest when none is provided (e.g. API requests without league_id).
DEFAULT_LEAGUE_ID = os.environ.get("FOUNDRY_DEFAULT_LEAGUE_ID", "1261894762944802816")


def get_default_league_id() -> str:
    """Return the configured default league ID."""
    return DEFAULT_LEAGUE_ID


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
