"""Optional tracked league IDs under the data root (meta/leagues.json)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from analytics_foundry.bronze import store as bronze_store

_LOCK = threading.Lock()
_META_NAME = "leagues.json"


def _meta_path() -> Path | None:
    root = bronze_store.get_data_root()
    if root is None:
        return None
    meta = root / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    return meta / _META_NAME


def _default_payload() -> dict[str, Any]:
    return {"leagues": []}


def _load() -> dict[str, Any]:
    p = _meta_path()
    if p is None or not p.is_file():
        return _default_payload()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("leagues"), list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return _default_payload()


def _save(data: dict[str, Any]) -> None:
    p = _meta_path()
    if p is None:
        raise OSError("FOUNDRY_DATA_DIR unset; cannot persist leagues registry")
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def list_leagues() -> list[dict[str, Any]]:
    """Return tracked leagues [{league_id, label?}, ...]."""
    with _LOCK:
        data = _load()
    return list(data.get("leagues", []))


def add_league(league_id: str, label: str | None = None) -> dict[str, Any]:
    """Add league_id if not already present."""
    league_id = league_id.strip()
    if not league_id:
        raise ValueError("league_id required")
    with _LOCK:
        data = _load()
        leagues: list[dict[str, Any]] = list(data.get("leagues", []))
        if any(x.get("league_id") == league_id for x in leagues):
            return {"ok": True, "duplicate": True, "league_id": league_id}
        entry: dict[str, Any] = {"league_id": league_id}
        if label:
            entry["label"] = label
        leagues.append(entry)
        data["leagues"] = leagues
        _save(data)
    return {"ok": True, "duplicate": False, "league_id": league_id}


def remove_league(league_id: str) -> dict[str, Any]:
    """Remove a tracked league_id."""
    league_id = league_id.strip()
    with _LOCK:
        data = _load()
        leagues = [x for x in data.get("leagues", []) if x.get("league_id") != league_id]
        removed = len(data.get("leagues", [])) - len(leagues)
        data["leagues"] = leagues
        _save(data)
    return {"ok": True, "removed": removed}
