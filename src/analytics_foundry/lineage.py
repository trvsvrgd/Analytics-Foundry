"""Static data lineage: which bronze sources feed silver/gold outputs."""

from typing import Any

# Medallion flow for NFL/Sleeper (documentation + admin UI).
LINEAGE: list[dict[str, Any]] = [
    {
        "output_layer": "silver",
        "output_name": "players",
        "sources": [{"layer": "bronze", "source_id": "nfl_sleeper", "table": "players"}],
        "transform": "silver/players.py::_to_silver_player + dedupe by player_id",
    },
    {
        "output_layer": "silver",
        "output_name": "league",
        "sources": [{"layer": "bronze", "source_id": "nfl_sleeper", "table": "league"}],
        "transform": "silver/league.py",
    },
    {
        "output_layer": "silver",
        "output_name": "rosters",
        "sources": [{"layer": "bronze", "source_id": "nfl_sleeper", "table": "rosters"}],
        "transform": "silver/rosters.py",
    },
    {
        "output_layer": "silver",
        "output_name": "injuries",
        "sources": [{"layer": "bronze", "source_id": "nfl_sleeper", "table": "players"}],
        "transform": "silver/injuries.py (injury fields on players)",
    },
    {
        "output_layer": "gold",
        "output_name": "available_players",
        "sources": [
            {"layer": "silver", "name": "players"},
            {"layer": "silver", "name": "rosters"},
        ],
        "transform": "gold/players.py::get_available_players",
    },
    {
        "output_layer": "gold",
        "output_name": "injury",
        "sources": [{"layer": "silver", "name": "injuries"}],
        "transform": "gold/injury.py",
    },
    {
        "output_layer": "gold",
        "output_name": "league_validation",
        "sources": [{"layer": "silver", "name": "league"}],
        "transform": "gold/league.py::validate_league",
    },
    {
        "output_layer": "gold",
        "output_name": "waiver_recommendations",
        "sources": [{"layer": "gold", "name": "available_players"}],
        "transform": "gold/recommendations.py",
    },
]


def list_lineage() -> list[dict[str, Any]]:
    """Return lineage entries for API/admin."""
    return list(LINEAGE)
