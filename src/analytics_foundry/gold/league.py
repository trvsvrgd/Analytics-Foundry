"""Gold helpers for league-scoped data. API layer calls ensure_league_ingested before serving."""

from analytics_foundry.adapters import get_adapter


def ensure_league_ingested(league_id: str) -> None:
    """If league_id is present, ensure that league's data is in bronze (lazy fetch). No-op if adapter missing."""
    adapter = get_adapter("nfl_sleeper")
    if adapter is not None:
        adapter.ingest_to_bronze(league_id=league_id)
