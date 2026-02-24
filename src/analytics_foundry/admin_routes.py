"""Admin API for Foundry UI: ingest, tables, transformations, runs (stub). Unauthenticated for local/dev."""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from analytics_foundry.adapters import get_adapter
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.gold import injury as gold_injury
from analytics_foundry.gold import league as gold_league
from analytics_foundry.gold import players as gold_players
from analytics_foundry.sql_loader import list_sql_files, medallion_layers, read_sql

router = APIRouter(prefix="/admin", tags=["admin"])

# Stub: in-memory run history (last league + last broad sync)
_RUNS: List[Dict[str, Any]] = []
_DEFAULT_SAMPLE_LIMIT = 100


class IngestLeagueBody(BaseModel):
    league_id: str


def _record_run(kind: str, league_id: Optional[str] = None) -> None:
    _RUNS.insert(0, {
        "kind": kind,
        "league_id": league_id,
        "timestamp": time.time(),
    })
    while len(_RUNS) > 50:
        _RUNS.pop()


@router.post("/ingest/league")
def admin_ingest_league(body: IngestLeagueBody) -> Dict[str, Any]:
    """Trigger league-scoped ingest for the given league_id. Uses ensure_league_ingested."""
    gold_league.ensure_league_ingested(body.league_id)
    _record_run("league", body.league_id)
    return {"ok": True, "league_id": body.league_id}


@router.post("/ingest/broad")
def admin_ingest_broad() -> Dict[str, Any]:
    """Trigger broad NFL ingest (no league_id). Calls adapter ingest_to_bronze()."""
    adapter = get_adapter("nfl_sleeper")
    if adapter is None:
        raise HTTPException(status_code=503, detail="nfl_sleeper adapter not registered")
    adapter.ingest_to_bronze()
    _record_run("broad")
    return {"ok": True}


@router.get("/tables")
def admin_list_tables() -> Dict[str, Any]:
    """List medallion datasets: bronze from store; silver/gold as fixed list with row_count or N/A."""
    bronze = [
        {"layer": "bronze", "source_id": s, "table": t, "row_count": n}
        for s, t, n in bronze_store.list_tables()
    ]
    silver_names = [f.replace(".sql", "") for f in list_sql_files("silver")]
    silver = [
        {"layer": "silver", "name": n, "row_count": None}
        for n in silver_names
    ]
    gold_available = gold_players.get_available_players()
    gold_injury_list = gold_injury.get_injury_report()
    gold = [
        {"layer": "gold", "name": "available_players", "row_count": len(gold_available)},
        {"layer": "gold", "name": "injury", "row_count": len(gold_injury_list)},
    ]
    return {"bronze": bronze, "silver": silver, "gold": gold}


@router.get("/tables/{layer}/{source_or_name}")
def admin_sample_table_two_segments(
    layer: str, source_or_name: str, table: Optional[str] = None
) -> Dict[str, Any]:
    """Sample table: bronze requires table (source_or_name=source_id); gold/silver use source_or_name as name."""
    limit = _DEFAULT_SAMPLE_LIMIT
    if layer == "bronze":
        if table is None:
            raise HTTPException(
                status_code=400,
                detail="Bronze sample requires path: /admin/tables/bronze/{source_id}/{table}",
            )
        rows = bronze_store.get_raw(source_or_name, table)[:limit]
        return {"layer": layer, "source_id": source_or_name, "table": table, "rows": rows, "limit": limit}
    if layer == "silver":
        return {"layer": layer, "name": source_or_name, "rows": [], "limit": limit, "note": "Silver samples not implemented"}
    if layer == "gold":
        if source_or_name == "available_players":
            rows = gold_players.get_available_players()[:limit]
        elif source_or_name == "injury":
            rows = gold_injury.get_injury_report()[:limit]
        else:
            raise HTTPException(status_code=404, detail=f"Unknown gold table: {source_or_name}")
        return {"layer": layer, "name": source_or_name, "rows": rows, "limit": limit}
    raise HTTPException(status_code=400, detail=f"Unknown layer: {layer}")


@router.get("/tables/{layer}/{source_or_name}/{table}")
def admin_sample_bronze(
    layer: str, source_or_name: str, table: str
) -> Dict[str, Any]:
    """Sample bronze table: GET /admin/tables/bronze/{source_id}/{table}."""
    if layer != "bronze":
        raise HTTPException(status_code=400, detail="Three-segment path is for bronze only")
    limit = _DEFAULT_SAMPLE_LIMIT
    rows = bronze_store.get_raw(source_or_name, table)[:limit]
    return {"layer": "bronze", "source_id": source_or_name, "table": table, "rows": rows, "limit": limit}


@router.get("/transformations")
def admin_list_transformations() -> Dict[str, Any]:
    """List SQL transformation files by layer (from sql_loader)."""
    out = {}
    for layer in medallion_layers():
        files = list_sql_files(layer)
        out[layer] = [f.replace(".sql", "") for f in files]
    return out


@router.get("/transformations/{layer}/{name}")
def admin_get_transformation(layer: str, name: str) -> Dict[str, Any]:
    """Return SQL content for sql/<layer>/<name>.sql."""
    if layer not in medallion_layers():
        raise HTTPException(status_code=400, detail=f"Unknown layer: {layer}")
    try:
        content = read_sql(layer, name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Transformation not found: {layer}/{name}")
    return {"layer": layer, "name": name, "sql": content}


@router.get("/runs")
def admin_list_runs() -> List[Dict[str, Any]]:
    """Stub: return in-memory run history (last syncs). No scheduler yet."""
    return [{"kind": r["kind"], "league_id": r.get("league_id"), "timestamp": r["timestamp"]} for r in _RUNS]


@router.get("/league/validate")
def admin_validate_league(league_id: str) -> Dict[str, Any]:
    """Validate league ID (same as POST /league/validate). For UI convenience."""
    return gold_league.validate_league(league_id)


_ADMIN_UI_ROOT = Path(__file__).resolve().parent / "admin_ui"


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def admin_ui_index():
    """Serve admin UI at GET /admin and GET /admin/."""
    index = _ADMIN_UI_ROOT / "index.html"
    if not index.is_file():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Admin UI not found")
    return FileResponse(index, media_type="text/html")
