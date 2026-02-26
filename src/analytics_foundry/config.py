"""Config: default league ID and optional overrides. Set FOUNDRY_DEFAULT_LEAGUE_ID env var to override."""

import os

# Default league ID for data ingest when none is provided (e.g. API requests without league_id).
DEFAULT_LEAGUE_ID = os.environ.get("FOUNDRY_DEFAULT_LEAGUE_ID", "1261894762944802816")


def get_default_league_id() -> str:
    """Return the configured default league ID."""
    return DEFAULT_LEAGUE_ID
