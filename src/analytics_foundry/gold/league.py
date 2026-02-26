"""Gold helpers for league-scoped data. API layer calls ensure_league_ingested before serving."""

from typing import Any, Dict

from analytics_foundry.adapters import get_adapter
from analytics_foundry.silver import league as silver_league


def ensure_league_ingested(league_id: str) -> None:
    """If league_id is present, ensure that league's data is in bronze (lazy fetch). No-op if adapter missing."""
    adapter = get_adapter("nfl_sleeper")
    if adapter is not None:
        adapter.ingest_to_bronze(league_id=league_id)


def validate_league(league_id: str) -> Dict[str, Any]:
    """Return {valid: bool, league_id: str, league_name: str} per API contract."""
    ensure_league_ingested(league_id)
    lg = silver_league.get_league(league_id)
    if lg is not None:
        return {"valid": True, "league_id": league_id, "league_name": lg["name"]}
    return {"valid": False, "league_id": league_id, "league_name": ""}
