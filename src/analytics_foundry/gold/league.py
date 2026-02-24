"""Gold helpers for league-scoped data. API layer calls ensure_league_ingested before serving."""

from typing import Any, Dict

from analytics_foundry.adapters import get_adapter
from analytics_foundry.bronze import store as bronze_store

NFL_SLEEPER = "nfl_sleeper"


def ensure_league_ingested(league_id: str) -> None:
    """If league_id is present, ensure that league's data is in bronze (lazy fetch). No-op if adapter missing."""
    adapter = get_adapter("nfl_sleeper")
    if adapter is not None:
        adapter.ingest_to_bronze(league_id=league_id)


def validate_league(league_id: str) -> Dict[str, Any]:
    """Return {valid: bool, league_id: str, league_name: str} per API contract."""
    ensure_league_ingested(league_id)
    raw = bronze_store.get_raw(NFL_SLEEPER, "league")
    for r in raw:
        if r.get("league_id") == league_id:
            name = r.get("name") or r.get("league_name") or ""
            return {"valid": True, "league_id": league_id, "league_name": str(name)}
    return {"valid": False, "league_id": league_id, "league_name": ""}
