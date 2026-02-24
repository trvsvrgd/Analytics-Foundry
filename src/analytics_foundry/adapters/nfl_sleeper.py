"""NFL/Sleeper adapter: broad ingest (players) and league-scoped ingest (league, rosters, matchups)."""

from typing import Any, Callable, Dict, List, Optional

from analytics_foundry.adapters.protocol import SourceAdapter
from analytics_foundry.bronze import store as bronze_store


def _default_fetch_players() -> Dict[str, Any]:
    from analytics_foundry.adapters.sleeper_client import get_players_nfl

    return get_players_nfl()


def _default_fetch_league(league_id: str) -> Optional[Dict[str, Any]]:
    from analytics_foundry.adapters.sleeper_client import get_league

    return get_league(league_id)


def _default_fetch_rosters(league_id: str) -> List[Dict[str, Any]]:
    from analytics_foundry.adapters.sleeper_client import get_rosters

    return get_rosters(league_id)


def _default_fetch_matchups(league_id: str, week: int = 1) -> List[Dict[str, Any]]:
    from analytics_foundry.adapters.sleeper_client import get_matchups

    return get_matchups(league_id, week)


class NFLSleeperAdapter:
    """Sleeper NFL adapter: broad (players) and league-scoped (league, rosters, matchups) ingest to bronze."""

    SOURCE_ID = "nfl_sleeper"

    def __init__(
        self,
        fetch_players: Optional[Callable[[], Dict[str, Any]]] = None,
        fetch_league: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
        fetch_rosters: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
        fetch_matchups: Optional[Callable[[str, int], List[Dict[str, Any]]]] = None,
    ):
        self._fetch_players = fetch_players or _default_fetch_players
        self._fetch_league = fetch_league or _default_fetch_league
        self._fetch_rosters = fetch_rosters or _default_fetch_rosters
        self._fetch_matchups = fetch_matchups or _default_fetch_matchups

    @property
    def source_id(self) -> str:
        return self.SOURCE_ID

    def ingest_to_bronze(self, **kwargs: Any) -> None:
        """Broad ingest (no league_id) or league-scoped ingest (league_id=...)."""
        league_id = kwargs.get("league_id")
        if league_id:
            self._ingest_league_scoped(league_id)
        else:
            self._ingest_broad()

    def _ingest_broad(self) -> None:
        """Fetch NFL players (and injuries if available); write to bronze."""
        data = self._fetch_players()
        if isinstance(data, dict):
            records = [{"player_id": k, **v} if isinstance(v, dict) else {"player_id": k, "raw": v} for k, v in data.items()]
        else:
            records = data if isinstance(data, list) else []
        bronze_store.append_raw(self.SOURCE_ID, "players", records)

    def _ingest_league_scoped(self, league_id: str) -> None:
        """Fetch league, rosters, matchups for league_id; write to bronze."""
        league = self._fetch_league(league_id)
        if league is not None:
            bronze_store.append_raw(self.SOURCE_ID, "league", [{"league_id": league_id, **league}])
        rosters = self._fetch_rosters(league_id)
        bronze_store.append_raw(self.SOURCE_ID, "rosters", [{"league_id": league_id, **r} for r in rosters])
        matchups = self._fetch_matchups(league_id, 1)
        bronze_store.append_raw(self.SOURCE_ID, "matchups", [{"league_id": league_id, "week": 1, **m} for m in matchups])
