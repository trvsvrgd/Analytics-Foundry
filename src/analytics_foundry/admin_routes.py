"""Admin API for Foundry UI: ingest, tables, transformations, runs (stub). Unauthenticated for local/dev."""

import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from analytics_foundry.adapters import get_adapter
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.config import get_default_league_id
from analytics_foundry.gold import injury as gold_injury
from analytics_foundry.gold import league as gold_league
from analytics_foundry.gold import players as gold_players
from analytics_foundry.gold import recommendations as gold_recommendations
from analytics_foundry.health import get_pipeline_health
from analytics_foundry.leagues_store import add_league, list_leagues, remove_league
from analytics_foundry.lineage import list_lineage
from analytics_foundry.quality import quality_summary
from analytics_foundry.silver import injuries as silver_injuries
from analytics_foundry.silver import league as silver_league
from analytics_foundry.silver import players as silver_players
from analytics_foundry.silver import rosters as silver_rosters
from analytics_foundry.sql_loader import list_sql_files, medallion_layers, read_sql
from analytics_foundry.telemetry import get_recent_logs

router = APIRouter(prefix="/admin", tags=["admin"])

# Stub: in-memory run history (last league + last broad sync)
_RUNS: list[dict[str, Any]] = []
_DEFAULT_SAMPLE_LIMIT = 100


class IngestLeagueBody(BaseModel):
    league_id: str


class IngestLeaguesBody(BaseModel):
    """One or more league IDs (comma-separated string or list)."""
    league_ids: str | list[str]


class LeagueTrackBody(BaseModel):
    """Register a league ID in local meta (requires persisted data dir)."""
    league_id: str
    label: str | None = None


def _record_run(kind: str, league_id: str | None = None) -> None:
    _RUNS.insert(0, {
        "kind": kind,
        "league_id": league_id,
        "timestamp": time.time(),
    })
    while len(_RUNS) > 50:
        _RUNS.pop()


@router.get("/config")
def admin_config() -> dict[str, Any]:
    """Return config values for the admin UI (e.g. default league ID)."""
    return {"default_league_id": get_default_league_id()}


@router.get("/pipeline/health")
def admin_pipeline_health() -> dict[str, Any]:
    """Pipeline status: adapter, data root, bronze freshness, quality summary."""
    pipe = get_pipeline_health()
    pipe["quality"] = quality_summary()
    return pipe


@router.get("/logs")
def admin_logs(limit: int = Query(100, ge=1, le=500)) -> list[dict[str, Any]]:
    """Recent structured log lines captured in memory (for local admin)."""
    return get_recent_logs(limit=limit)


@router.get("/lineage")
def admin_lineage() -> dict[str, Any]:
    """Bronze/silver/gold lineage for NFL/Sleeper pipelines."""
    return {"entries": list_lineage()}


@router.get("/quality")
def admin_quality() -> dict[str, Any]:
    """Data quality summary (null keys, schema checks)."""
    return quality_summary()


@router.get("/leagues")
def admin_list_tracked_leagues() -> dict[str, Any]:
    """League IDs stored in meta/leagues.json (optional registry)."""
    return {"leagues": list_leagues()}


@router.post("/leagues")
def admin_track_league(body: LeagueTrackBody) -> dict[str, Any]:
    """Add a league_id to the local registry."""
    try:
        return add_league(body.league_id, body.label)
    except OSError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/leagues/{league_id:path}")
def admin_untrack_league(league_id: str) -> dict[str, Any]:
    """Remove a league_id from the registry."""
    try:
        return remove_league(league_id)
    except OSError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.post("/ingest/league")
def admin_ingest_league(body: IngestLeagueBody) -> dict[str, Any]:
    """Trigger league-scoped ingest for the given league_id. Uses ensure_league_ingested."""
    gold_league.ensure_league_ingested(body.league_id)
    _record_run("league", body.league_id)
    return {"ok": True, "league_id": body.league_id}


def _parse_league_ids(raw: str | list[str]) -> list[str]:
    """Parse league_ids from string (comma/newline separated) or list."""
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    ids = []
    for part in raw.replace("\n", ",").split(","):
        pid = part.strip()
        if pid:
            ids.append(pid)
    return ids


@router.post("/ingest/leagues")
def admin_ingest_leagues(body: IngestLeaguesBody) -> dict[str, Any]:
    """Trigger league-scoped ingest for one or more league IDs."""
    ids = _parse_league_ids(body.league_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="At least one league_id required")
    for lid in ids:
        gold_league.ensure_league_ingested(lid)
        _record_run("league", lid)
    return {"ok": True, "league_ids": ids}


@router.post("/ingest/broad")
def admin_ingest_broad() -> dict[str, Any]:
    """Trigger broad NFL ingest (no league_id). Calls adapter ingest_to_bronze()."""
    adapter = get_adapter("nfl_sleeper")
    if adapter is None:
        raise HTTPException(status_code=503, detail="nfl_sleeper adapter not registered")
    adapter.ingest_to_bronze()
    _record_run("broad")
    return {"ok": True}


@router.get("/tables")
def admin_list_tables() -> dict[str, Any]:
    """List medallion datasets: bronze from store; silver/gold as fixed list with row_count or N/A."""
    bronze = [
        {"layer": "bronze", "source_id": s, "table": t, "row_count": n}
        for s, t, n in bronze_store.list_tables()
    ]
    silver_tables = [
        ("players", lambda: len(silver_players.get_players())),
        ("league", lambda: len(silver_league.get_leagues())),
        ("rosters", lambda: len(silver_rosters.get_rosters())),
        ("injuries", lambda: len(silver_injuries.get_injuries())),
    ]
    silver = [
        {"layer": "silver", "name": n, "row_count": fn()}
        for n, fn in silver_tables
    ]
    gold_available = gold_players.get_available_players()
    gold_injury_list = gold_injury.get_injury_report()
    lid = get_default_league_id()
    waiver_sample = gold_recommendations.get_waiver_recommendations(league_id=lid, limit=500)
    gold = [
        {"layer": "gold", "name": "available_players", "row_count": len(gold_available)},
        {"layer": "gold", "name": "injury", "row_count": len(gold_injury_list)},
        {"layer": "gold", "name": "waiver_recommendations", "row_count": len(waiver_sample)},
    ]
    return {"bronze": bronze, "silver": silver, "gold": gold}


@router.get("/tables/{layer}/{source_or_name}")
def admin_sample_table_two_segments(
    layer: str,
    source_or_name: str,
    table: str | None = None,
    league_id: str | None = None,
    limit: int = Query(_DEFAULT_SAMPLE_LIMIT, ge=1, le=500),
) -> dict[str, Any]:
    """Sample table: bronze requires table (source_or_name=source_id); gold/silver use source_or_name as name."""
    sample_limit = min(limit, _DEFAULT_SAMPLE_LIMIT) if layer != "gold" else limit
    if layer == "bronze":
        if table is None:
            raise HTTPException(
                status_code=400,
                detail="Bronze sample requires path: /admin/tables/bronze/{source_id}/{table}",
            )
        rows = bronze_store.get_raw(source_or_name, table)[:sample_limit]
        return {
            "layer": layer,
            "source_id": source_or_name,
            "table": table,
            "rows": rows,
            "limit": sample_limit,
        }
    if layer == "silver":
        if source_or_name == "players":
            rows = silver_players.get_players()[:sample_limit]
        elif source_or_name == "league":
            rows = silver_league.get_leagues()[:sample_limit]
        elif source_or_name == "rosters":
            rows = silver_rosters.get_rosters()[:sample_limit]
        elif source_or_name == "injuries":
            rows = silver_injuries.get_injuries()[:sample_limit]
        else:
            raise HTTPException(status_code=404, detail=f"Unknown silver table: {source_or_name}")
        return {"layer": layer, "name": source_or_name, "rows": rows, "limit": sample_limit}
    if layer == "gold":
        if source_or_name == "available_players":
            lid = league_id or get_default_league_id()
            rows = gold_players.get_available_players(league_id=lid)[:sample_limit]
        elif source_or_name == "injury":
            rows = gold_injury.get_injury_report()[:sample_limit]
        elif source_or_name == "waiver_recommendations":
            lid = league_id or get_default_league_id()
            rows = gold_recommendations.get_waiver_recommendations(league_id=lid, limit=sample_limit)
        else:
            raise HTTPException(status_code=404, detail=f"Unknown gold table: {source_or_name}")
        return {"layer": layer, "name": source_or_name, "rows": rows, "limit": sample_limit}
    raise HTTPException(status_code=400, detail=f"Unknown layer: {layer}")


@router.get("/tables/{layer}/{source_or_name}/{table}")
def admin_sample_bronze(
    layer: str, source_or_name: str, table: str
) -> dict[str, Any]:
    """Sample bronze table: GET /admin/tables/bronze/{source_id}/{table}."""
    if layer != "bronze":
        raise HTTPException(status_code=400, detail="Three-segment path is for bronze only")
    limit = _DEFAULT_SAMPLE_LIMIT
    rows = bronze_store.get_raw(source_or_name, table)[:limit]
    return {"layer": "bronze", "source_id": source_or_name, "table": table, "rows": rows, "limit": limit}


@router.get("/transformations")
def admin_list_transformations() -> dict[str, Any]:
    """List SQL transformation files by layer (from sql_loader)."""
    out = {}
    for layer in medallion_layers():
        files = list_sql_files(layer)
        out[layer] = [f.replace(".sql", "") for f in files]
    return out


@router.get("/transformations/{layer}/{name}")
def admin_get_transformation(layer: str, name: str) -> dict[str, Any]:
    """Return SQL content for sql/<layer>/<name>.sql."""
    if layer not in medallion_layers():
        raise HTTPException(status_code=400, detail=f"Unknown layer: {layer}")
    try:
        content = read_sql(layer, name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Transformation not found: {layer}/{name}") from e
    return {"layer": layer, "name": name, "sql": content}


@router.get("/runs")
def admin_list_runs() -> list[dict[str, Any]]:
    """Stub: return in-memory run history (last syncs). No scheduler yet."""
    return [{"kind": r["kind"], "league_id": r.get("league_id"), "timestamp": r["timestamp"]} for r in _RUNS]


@router.get("/league/validate")
def admin_validate_league(league_id: str) -> dict[str, Any]:
    """Validate league ID (same as POST /league/validate). For UI convenience."""
    return gold_league.validate_league(league_id)


_ADMIN_UI_ROOT = Path(__file__).resolve().parent / "admin_ui"


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def admin_ui_index():
    """Serve admin UI at GET /admin and GET /admin/."""
    index = _ADMIN_UI_ROOT / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Admin UI not found")
    return FileResponse(index, media_type="text/html")
