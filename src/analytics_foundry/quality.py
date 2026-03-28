"""Lightweight data quality checks on silver- and bronze-layer shapes."""

from typing import Any

from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.silver import players as silver_players
from analytics_foundry.silver.players import SILVER_PLAYER_KEYS

NFL_SLEEPER = "nfl_sleeper"


def check_silver_players() -> dict[str, Any]:
    """Validate silver player rows: required keys, non-null player_id/name where applicable."""
    rows = silver_players.get_players()
    issues: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        pid = row.get("player_id")
        if not pid:
            issues.append({"index": i, "player_id": pid, "issue": "missing_or_empty_player_id"})
            continue
        for key in SILVER_PLAYER_KEYS:
            if key not in row:
                issues.append({"index": i, "player_id": pid, "issue": f"missing_key:{key}"})
    return {
        "layer": "silver",
        "table": "players",
        "row_count": len(rows),
        "issue_count": len(issues),
        "issues_sample": issues[:50],
    }


def check_bronze_players() -> dict[str, Any]:
    """Count bronze NFL player rows missing stable id (data quality signal)."""
    raw = bronze_store.get_raw(NFL_SLEEPER, "players")
    missing_id = sum(1 for r in raw if not r.get("player_id") and not r.get("id"))
    return {
        "layer": "bronze",
        "source_id": NFL_SLEEPER,
        "table": "players",
        "row_count": len(raw),
        "rows_missing_player_id": missing_id,
    }


def quality_summary() -> dict[str, Any]:
    """Aggregate checks for admin / pipeline health."""
    return {
        "silver_players": check_silver_players(),
        "bronze_players": check_bronze_players(),
    }
