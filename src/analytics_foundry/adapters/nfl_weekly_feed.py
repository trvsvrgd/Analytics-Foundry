"""NFL Weekly Feed adapter: ingests team statistics/rankings and weekly matchup details."""

from typing import Any, Callable, Dict, List, Optional
from analytics_foundry.adapters.protocol import SourceAdapter
from analytics_foundry.bronze import store as bronze_store

DEFAULT_MATCHUPS = [
    {"matchup_id": 1, "week": 1, "home_team": "KC", "away_team": "LAC", "home_qb_backup": False, "away_qb_backup": True},
    {"matchup_id": 2, "week": 1, "home_team": "BUF", "away_team": "NYJ", "home_qb_backup": False, "away_qb_backup": False},
    {"matchup_id": 3, "week": 1, "home_team": "GB", "away_team": "CHI", "home_qb_backup": True, "away_qb_backup": False},
    {"matchup_id": 4, "week": 1, "home_team": "SF", "away_team": "SEA", "home_qb_backup": False, "away_qb_backup": False},
]

DEFAULT_TEAM_STATS = [
    {"team": "KC", "offensive_rank": 2, "defensive_rank": 5, "historical_win_rate": 0.75},
    {"team": "LAC", "offensive_rank": 15, "defensive_rank": 22, "historical_win_rate": 0.45},
    {"team": "BUF", "offensive_rank": 4, "defensive_rank": 3, "historical_win_rate": 0.68},
    {"team": "NYJ", "offensive_rank": 32, "defensive_rank": 10, "historical_win_rate": 0.30},
    {"team": "GB", "offensive_rank": 12, "defensive_rank": 14, "historical_win_rate": 0.55},
    {"team": "CHI", "offensive_rank": 28, "defensive_rank": 25, "historical_win_rate": 0.35},
    {"team": "SF", "offensive_rank": 1, "defensive_rank": 1, "historical_win_rate": 0.80},
    {"team": "SEA", "offensive_rank": 18, "defensive_rank": 18, "historical_win_rate": 0.50},
]

DEFAULT_PLAYER_STATS = [
    # Buy-low/breakout WR candidate: high route run, low targets, high snaps week-over-week increase
    {"player_id": "p_wr1", "week": 2, "snaps_pct": 0.85, "snaps_pct_prev": 0.40, "routes_run_pct": 0.90, "targets": 2, "carries": 0, "actual_points": 4.2, "expected_points": 14.5, "touchdowns": 0},
    # Overperforming/sell-high RB candidate: low expected points, high touchdowns/actual points
    {"player_id": "p_rb1", "week": 2, "snaps_pct": 0.70, "snaps_pct_prev": 0.65, "routes_run_pct": 0.30, "targets": 5, "carries": 18, "actual_points": 26.5, "expected_points": 12.0, "touchdowns": 3},
    # A standard backup RB
    {"player_id": "p_rb_backup", "week": 2, "snaps_pct": 0.10, "snaps_pct_prev": 0.08, "routes_run_pct": 0.05, "targets": 1, "carries": 2, "actual_points": 1.5, "expected_points": 1.2, "touchdowns": 0},
    # A starter marked as injured
    {"player_id": "p_kc_rb1", "week": 2, "snaps_pct": 0.00, "snaps_pct_prev": 0.60, "routes_run_pct": 0.00, "targets": 0, "carries": 0, "actual_points": 0.0, "expected_points": 0.0, "touchdowns": 0},
]

DEFAULT_DEPTH_CHARTS = [
    {"team": "KC", "position": "RB", "players": ["p_kc_rb1", "p_kc_rb2", "p_kc_rb3"]},
    {"team": "KC", "position": "WR", "players": ["p_kc_wr1", "p_kc_wr2", "p_kc_wr3"]},
    {"team": "BUF", "position": "QB", "players": ["p_buf_qb1", "p_buf_qb2"]},
    {"team": "SF", "position": "RB", "players": ["p_sf_rb1", "p_sf_rb2"]},
]

DEFAULT_VEGAS_WEATHER = [
    {"home_team": "KC", "away_team": "LAC", "over_under": 48.5, "implied_total_home": 26.5, "implied_total_away": 22.0, "wind_speed": 5, "is_dome": False, "weather_summary": "Sunny"},
    {"home_team": "BUF", "away_team": "NYJ", "over_under": 42.0, "implied_total_home": 24.5, "implied_total_away": 17.5, "wind_speed": 18, "is_dome": False, "weather_summary": "Windy"},
    {"home_team": "GB", "away_team": "CHI", "over_under": 44.0, "implied_total_home": 23.0, "implied_total_away": 21.0, "wind_speed": 0, "is_dome": True, "weather_summary": "Dome"},
]

DEFAULT_FAAB_HISTORY = [
    {"roster_id": 1, "remaining_faab": 85, "bid_history": [{"player_id": "p_wr1", "bid": 15, "success": True}, {"player_id": "p_rb2", "bid": 5, "success": False}]},
    {"roster_id": 2, "remaining_faab": 40, "bid_history": [{"player_id": "p_wr1", "bid": 25, "success": False}]},
    {"roster_id": 3, "remaining_faab": 95, "bid_history": []},
]


class NFLWeeklyFeedAdapter:
    """NFL Weekly Feed adapter: pulls stats and matchups to bronze."""

    SOURCE_ID = "nfl_weekly_feed"

    def __init__(
        self,
        fetch_matchups: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        fetch_team_stats: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        fetch_player_stats: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        fetch_depth_charts: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        fetch_vegas_weather: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        fetch_faab_history: Optional[Callable[[], List[Dict[str, Any]]]] = None,
    ):
        self._fetch_matchups = fetch_matchups or (lambda: DEFAULT_MATCHUPS)
        self._fetch_team_stats = fetch_team_stats or (lambda: DEFAULT_TEAM_STATS)
        self._fetch_player_stats = fetch_player_stats or (lambda: DEFAULT_PLAYER_STATS)
        self._fetch_depth_charts = fetch_depth_charts or (lambda: DEFAULT_DEPTH_CHARTS)
        self._fetch_vegas_weather = fetch_vegas_weather or (lambda: DEFAULT_VEGAS_WEATHER)
        self._fetch_faab_history = fetch_faab_history or (lambda: DEFAULT_FAAB_HISTORY)

    @property
    def source_id(self) -> str:
        return self.SOURCE_ID

    def ingest_to_bronze(self, **kwargs: Any) -> None:
        """Fetch matchups, stats, depth charts, vegas weather, and faab history, then save to bronze."""
        matchups = self._fetch_matchups()
        stats = self._fetch_team_stats()
        player_stats = self._fetch_player_stats()
        depth_charts = self._fetch_depth_charts()
        vegas_weather = self._fetch_vegas_weather()
        faab_history = self._fetch_faab_history()
        
        bronze_store.append_raw(self.SOURCE_ID, "weekly_matchups", matchups)
        bronze_store.append_raw(self.SOURCE_ID, "team_stats", stats)
        bronze_store.append_raw(self.SOURCE_ID, "player_weekly_stats", player_stats)
        bronze_store.append_raw(self.SOURCE_ID, "depth_charts", depth_charts)
        bronze_store.append_raw(self.SOURCE_ID, "vegas_weather", vegas_weather)
        bronze_store.append_raw(self.SOURCE_ID, "faab_history", faab_history)
