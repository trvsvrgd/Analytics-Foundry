"""NFL/Sleeper adapter: broad ingest (players) and league-scoped ingest (league, rosters, matchups)."""

from collections.abc import Callable
from typing import Any

from analytics_foundry.bronze import store as bronze_store


def _default_fetch_players() -> dict[str, Any]:
    from analytics_foundry.adapters.sleeper_client import get_players_nfl

    return get_players_nfl()


def _default_fetch_league(league_id: str) -> dict[str, Any] | None:
    from analytics_foundry.adapters.sleeper_client import get_league

    return get_league(league_id)


def _default_fetch_rosters(league_id: str) -> list[dict[str, Any]]:
    from analytics_foundry.adapters.sleeper_client import get_rosters

    return get_rosters(league_id)


def _default_fetch_matchups(league_id: str, week: int = 1) -> list[dict[str, Any]]:
    from analytics_foundry.adapters.sleeper_client import get_matchups

    return get_matchups(league_id, week)


class NFLSleeperAdapter:
    """Sleeper NFL adapter: broad (players) and league-scoped (league, rosters, matchups) ingest to bronze."""

    SOURCE_ID = "nfl_sleeper"

    def __init__(
        self,
        fetch_players: Callable[[], dict[str, Any]] | None = None,
        fetch_league: Callable[[str], dict[str, Any] | None] | None = None,
        fetch_rosters: Callable[[str], list[dict[str, Any]]] | None = None,
        fetch_matchups: Callable[[str, int], list[dict[str, Any]]] | None = None,
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
        """Fetch NFL players; replace bronze players table (full snapshot refresh)."""
        data = self._fetch_players()
        if isinstance(data, dict):
            records = [
                {"player_id": k, **v} if isinstance(v, dict) else {"player_id": k, "raw": v}
                for k, v in data.items()
            ]
        else:
            records = data if isinstance(data, list) else []
        bronze_store.replace_raw_table(self.SOURCE_ID, "players", records)

    def _ingest_league_scoped(self, league_id: str) -> None:
        """Fetch league, rosters, matchups; refresh bronze rows for this league_id only."""
        partition = {"league_id": league_id}
        league = self._fetch_league(league_id)
        league_rows = [{"league_id": league_id, **league}] if league is not None else []
        bronze_store.replace_rows_matching(self.SOURCE_ID, "league", partition, league_rows)
        rosters = self._fetch_rosters(league_id)
        bronze_store.replace_rows_matching(
            self.SOURCE_ID,
            "rosters",
            partition,
            [{"league_id": league_id, **r} for r in rosters],
        )
        matchups = self._fetch_matchups(league_id, 1)
        bronze_store.replace_rows_matching(
            self.SOURCE_ID,
            "matchups",
            {"league_id": league_id, "week": 1},
            [{"league_id": league_id, "week": 1, **m} for m in matchups],
        )
