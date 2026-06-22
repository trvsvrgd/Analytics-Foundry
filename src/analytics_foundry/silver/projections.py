"""Silver: conformed weekly matchups and team statistics."""

from typing import Any, Dict, List
from analytics_foundry.bronze import store as bronze_store

NFL_WEEKLY_FEED = "nfl_weekly_feed"


def get_weekly_matchups() -> List[Dict[str, Any]]:
    """Return conformed weekly matchups. Dedup by matchup_id and week."""
    raw = bronze_store.get_raw(NFL_WEEKLY_FEED, "weekly_matchups")
    by_key = {}
    for rec in raw:
        mid = rec.get("matchup_id")
        week = rec.get("week") or 1
        if mid is None:
            continue
        conformed = {
            "matchup_id": int(mid),
            "week": int(week),
            "home_team": str(rec.get("home_team") or ""),
            "away_team": str(rec.get("away_team") or ""),
            "home_qb_backup": bool(rec.get("home_qb_backup", False)),
            "away_qb_backup": bool(rec.get("away_qb_backup", False)),
        }
        by_key[(conformed["matchup_id"], conformed["week"])] = conformed
    return list(by_key.values())


def get_team_stats() -> List[Dict[str, Any]]:
    """Return conformed team statistics. Dedup by team."""
    raw = bronze_store.get_raw(NFL_WEEKLY_FEED, "team_stats")
    by_key = {}
    for rec in raw:
        team = rec.get("team")
        if not team:
            continue
        conformed = {
            "team": str(team).upper(),
            "offensive_rank": int(rec.get("offensive_rank") or 16),
            "defensive_rank": int(rec.get("defensive_rank") or 16),
            "historical_win_rate": float(rec.get("historical_win_rate") or 0.5),
        }
        by_key[conformed["team"]] = conformed
    return list(by_key.values())
