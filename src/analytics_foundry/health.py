"""Health, readiness, and pipeline status for operations."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from analytics_foundry.adapters import get_adapter
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.config import get_default_league_id


def get_liveness() -> dict[str, str]:
    """Process is up."""
    return {"status": "ok"}


def get_readiness() -> dict[str, Any]:
    """Adapter registered and bronze store initialized."""
    adapter = get_adapter("nfl_sleeper")
    return {
        "ready": adapter is not None,
        "adapter": "nfl_sleeper",
        "adapter_registered": adapter is not None,
    }


def _latest_bronze_mtime(root: Path | None) -> float | None:
    if root is None:
        return None
    bronze = root / "bronze"
    if not bronze.is_dir():
        return None
    latest: float | None = None
    try:
        for p in bronze.rglob("*.jsonl"):
            try:
                m = p.stat().st_mtime
                if latest is None or m > latest:
                    latest = m
            except OSError:
                continue
    except OSError:
        return latest
    return latest


def get_pipeline_health() -> dict[str, Any]:
    """Data freshness and counts for admin dashboards."""
    root = bronze_store.get_data_root()
    tables = bronze_store.list_tables()
    mtime = _latest_bronze_mtime(root)
    now = time.time()
    stale_seconds = (now - mtime) if mtime is not None else None
    return {
        "adapter_registered": get_adapter("nfl_sleeper") is not None,
        "data_root": str(root) if root else None,
        "default_league_id": get_default_league_id(),
        "bronze_table_count": len(tables),
        "bronze_total_rows": sum(t[2] for t in tables),
        "bronze_latest_mtime": mtime,
        "bronze_stale_seconds": stale_seconds,
    }
