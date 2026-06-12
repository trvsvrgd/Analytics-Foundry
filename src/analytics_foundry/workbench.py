"""Low-code workbench metadata, quality checks, jobs, lineage, and model previews.

The workbench layer stores product-facing ETL objects as local JSON artifacts
under FOUNDRY_DATA_DIR/control_plane. If FOUNDRY_DATA_DIR is disabled, it falls
back to in-memory state so tests and embedded usage can still run.
"""

from __future__ import annotations

import json
import re
import time
import uuid
import csv
from io import StringIO
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from analytics_foundry.adapters import get_adapter
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.config import scheduler_enabled, scheduler_interval_seconds

RowsResolver = Callable[[str], List[Dict[str, Any]]]

_JSON_COLLECTIONS = {
    "jobs",
    "quality_rules",
    "alerts",
    "alert_delivery_targets",
    "models",
    "sources",
}
_JSONL_COLLECTIONS = {"runs", "quality_results", "alert_deliveries"}
_BUNDLE_FORMAT = "analytics_foundry.workbench.bundle"
_BUNDLE_VERSION = 1
_MEMORY_JSON: Dict[str, List[Dict[str, Any]]] = {name: [] for name in _JSON_COLLECTIONS}
_MEMORY_JSONL: Dict[str, List[Dict[str, Any]]] = {name: [] for name in _JSONL_COLLECTIONS}
_MEMORY_MODEL_ROWS: Dict[str, List[Dict[str, Any]]] = {}
ALERT_DELIVERY_KINDS = ["webhook", "slack_webhook"]
ALERT_SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}

SOURCE_CONNECTOR_TEMPLATES = [
    {
        "type": "file",
        "label": "Local file",
        "formats": ["csv", "tsv", "json", "jsonl"],
        "params": ["name", "source_id", "table_name", "filename", "content", "format"],
    },
    {
        "type": "api",
        "label": "Public JSON API",
        "formats": ["json"],
        "params": ["name", "source_id", "table_name", "url", "records_path"],
    },
]

RETENTION_SCOPES = ["bronze", "models", "run_history"]

QUALITY_TEMPLATES = [
    {
        "type": "required",
        "label": "Required field",
        "params": ["column"],
    },
    {
        "type": "unique",
        "label": "Unique key",
        "params": ["column"],
    },
    {
        "type": "accepted_values",
        "label": "Accepted values",
        "params": ["column", "values"],
    },
    {
        "type": "numeric_range",
        "label": "Numeric range",
        "params": ["column", "min", "max"],
    },
    {
        "type": "regex",
        "label": "Pattern match",
        "params": ["column", "pattern"],
    },
    {
        "type": "freshness",
        "label": "Freshness",
        "params": ["column", "max_age_seconds"],
    },
    {
        "type": "row_count_drift",
        "label": "Row count drift",
        "params": ["min_count", "max_count", "baseline_count", "max_percent_change"],
    },
    {
        "type": "referential",
        "label": "Referential check",
        "params": ["column", "reference_table_id", "reference_column"],
    },
]

MODEL_OPERATION_TEMPLATES = [
    {
        "type": "filter",
        "label": "Filter rows",
        "params": ["column", "operator", "value"],
    },
    {
        "type": "select",
        "label": "Choose columns",
        "params": ["columns"],
    },
    {
        "type": "rename",
        "label": "Rename columns",
        "params": ["mapping"],
    },
    {
        "type": "cast",
        "label": "Change type",
        "params": ["column", "to"],
    },
    {
        "type": "deduplicate",
        "label": "Deduplicate rows",
        "params": ["columns"],
    },
    {
        "type": "calculate",
        "label": "Calculate column",
        "params": ["column", "mode", "value"],
    },
    {
        "type": "group",
        "label": "Group and aggregate",
        "params": ["group_by", "aggregations"],
    },
    {
        "type": "join",
        "label": "Join tables",
        "params": ["source_table_id", "left_key", "right_key", "how"],
    },
    {
        "type": "union",
        "label": "Union tables",
        "params": ["source_table_id"],
    },
]

_CORE_LINEAGE: Dict[str, List[str]] = {
    "silver:players": ["bronze:nfl_sleeper.players"],
    "silver:league": ["bronze:nfl_sleeper.league"],
    "silver:rosters": ["bronze:nfl_sleeper.rosters"],
    "silver:injuries": ["silver:players"],
    "gold:available_players": ["silver:players", "silver:rosters"],
    "gold:injury": ["silver:injuries"],
}


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _control_root() -> Path | None:
    data_root = bronze_store.get_data_root()
    if data_root is None:
        return None
    return data_root / "control_plane"


def _json_path(name: str) -> Path | None:
    root = _control_root()
    return None if root is None else root / f"{name}.json"


def _jsonl_path(name: str) -> Path | None:
    root = _control_root()
    return None if root is None else root / f"{name}.jsonl"


def _read_json_collection(name: str) -> List[Dict[str, Any]]:
    if name not in _JSON_COLLECTIONS:
        raise ValueError(f"Unknown JSON collection: {name}")
    path = _json_path(name)
    if path is None:
        return [dict(item) for item in _MEMORY_JSON[name]]
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _write_json_collection(name: str, records: List[Dict[str, Any]]) -> None:
    if name not in _JSON_COLLECTIONS:
        raise ValueError(f"Unknown JSON collection: {name}")
    path = _json_path(name)
    if path is None:
        _MEMORY_JSON[name] = [dict(item) for item in records]
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _read_jsonl_collection(name: str) -> List[Dict[str, Any]]:
    if name not in _JSONL_COLLECTIONS:
        raise ValueError(f"Unknown JSONL collection: {name}")
    path = _jsonl_path(name)
    if path is None:
        return [dict(item) for item in _MEMORY_JSONL[name]]
    if not path.is_file():
        return []
    records: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if isinstance(item, dict):
                records.append(item)
    except (json.JSONDecodeError, OSError):
        return []
    return records


def _append_jsonl_collection(name: str, record: Dict[str, Any]) -> None:
    if name not in _JSONL_COLLECTIONS:
        raise ValueError(f"Unknown JSONL collection: {name}")
    path = _jsonl_path(name)
    if path is None:
        _MEMORY_JSONL[name].append(dict(record))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _write_jsonl_collection(name: str, records: List[Dict[str, Any]]) -> None:
    if name not in _JSONL_COLLECTIONS:
        raise ValueError(f"Unknown JSONL collection: {name}")
    path = _jsonl_path(name)
    if path is None:
        _MEMORY_JSONL[name] = [dict(item) for item in records]
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    tmp.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    tmp.replace(path)


def clear() -> None:
    """Clear workbench control-plane metadata. Intended for tests."""
    for name in _JSON_COLLECTIONS:
        _MEMORY_JSON[name] = []
        path = _json_path(name)
        if path is not None and path.is_file():
            path.unlink()
    for name in _JSONL_COLLECTIONS:
        _MEMORY_JSONL[name] = []
        path = _jsonl_path(name)
        if path is not None and path.is_file():
            path.unlink()
    _MEMORY_MODEL_ROWS.clear()
    model_root = _model_root()
    if model_root is not None and model_root.is_dir():
        for path in model_root.glob("*.jsonl"):
            path.unlink()


def export_bundle(include_history: bool = False) -> Dict[str, Any]:
    """Return a portable bundle of workbench control-plane metadata."""
    exported_at = _now()
    collections = {
        name: _read_json_collection(name)
        for name in sorted(_JSON_COLLECTIONS)
    }
    history = {
        name: _read_jsonl_collection(name)
        for name in sorted(_JSONL_COLLECTIONS)
    } if include_history else {}
    collection_counts = {name: len(records) for name, records in collections.items()}
    history_counts = {name: len(records) for name, records in history.items()}
    return {
        "format": _BUNDLE_FORMAT,
        "version": _BUNDLE_VERSION,
        "exported_at": exported_at,
        "exported_at_iso": _iso(exported_at),
        "include_history": bool(include_history),
        "collections": collections,
        "history": history,
        "record_counts": {
            "collections": collection_counts,
            "history": history_counts,
            "total": sum(collection_counts.values()) + sum(history_counts.values()),
        },
    }


def import_bundle(bundle: Dict[str, Any], mode: str = "merge") -> Dict[str, Any]:
    """Import a portable workbench metadata bundle."""
    if not isinstance(bundle, dict):
        raise ValueError("Import bundle must be a JSON object")
    if bundle.get("format") != _BUNDLE_FORMAT:
        raise ValueError("Unsupported import bundle format")
    if bundle.get("version") != _BUNDLE_VERSION:
        raise ValueError("Unsupported import bundle version")

    normalized_mode = str(mode or "merge").strip().lower()
    if normalized_mode not in {"merge", "replace"}:
        raise ValueError("Import mode must be merge or replace")

    collections_payload = bundle.get("collections") or {}
    history_payload = bundle.get("history") or {}
    if not isinstance(collections_payload, dict):
        raise ValueError("Import bundle collections must be an object")
    if not isinstance(history_payload, dict):
        raise ValueError("Import bundle history must be an object")

    unknown_collections = sorted(set(collections_payload) - _JSON_COLLECTIONS)
    if unknown_collections:
        raise ValueError(f"Unknown import collections: {', '.join(unknown_collections)}")
    unknown_history = sorted(set(history_payload) - _JSONL_COLLECTIONS)
    if unknown_history:
        raise ValueError(f"Unknown import history collections: {', '.join(unknown_history)}")

    imported_collections: Dict[str, Dict[str, int]] = {}
    for name, value in collections_payload.items():
        incoming = _bundle_records(value, f"collections.{name}")
        existing = [] if normalized_mode == "replace" else _read_json_collection(name)
        records = incoming if normalized_mode == "replace" else _merge_records(existing, incoming)
        _write_json_collection(name, records)
        imported_collections[name] = {"imported": len(incoming), "total": len(records)}

    imported_history: Dict[str, Dict[str, int]] = {}
    for name, value in history_payload.items():
        incoming = _bundle_records(value, f"history.{name}")
        existing = [] if normalized_mode == "replace" else _read_jsonl_collection(name)
        records = incoming if normalized_mode == "replace" else _merge_records(existing, incoming)
        _write_jsonl_collection(name, records)
        imported_history[name] = {"imported": len(incoming), "total": len(records)}

    return {
        "mode": normalized_mode,
        "imported_at": _now(),
        "collections": imported_collections,
        "history": imported_history,
        "record_counts": {
            "collections": {name: data["total"] for name, data in imported_collections.items()},
            "history": {name: data["total"] for name, data in imported_history.items()},
            "imported": sum(data["imported"] for data in imported_collections.values())
            + sum(data["imported"] for data in imported_history.values()),
        },
    }


def _bundle_records(value: Any, label: str) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"Import {label} must be a list")
    records = []
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"Import {label}[{idx}] must be an object")
        records.append(dict(item))
    return records


def _merge_records(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged = [dict(item) for item in existing]
    index = {_record_merge_key(item): idx for idx, item in enumerate(merged)}
    for record in incoming:
        key = _record_merge_key(record)
        if key in index:
            merged[index[key]] = dict(record)
        else:
            index[key] = len(merged)
            merged.append(dict(record))
    return merged


def _record_merge_key(record: Dict[str, Any]) -> tuple[str, str]:
    value = record.get("id")
    if value is not None:
        return ("id", str(value))
    return ("body", json.dumps(record, sort_keys=True, default=str))


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def data_root_info() -> Dict[str, Any]:
    """Return local storage paths and byte counts for the workbench settings view."""
    root = bronze_store.get_data_root()
    if root is None:
        return {
            "data_root": None,
            "exists": False,
            "bronze_path": None,
            "control_plane_path": None,
            "model_path": None,
            "total_bytes": 0,
            "bronze_bytes": 0,
            "control_plane_bytes": 0,
            "model_bytes": 0,
            "retention_scopes": RETENTION_SCOPES,
            "table_files": [],
            "history_files": [],
        }
    bronze_path = root / "bronze"
    control_path = root / "control_plane"
    model_path = root / "models"
    inventory = storage_inventory()
    return {
        "data_root": str(root),
        "exists": root.exists(),
        "bronze_path": str(bronze_path),
        "control_plane_path": str(control_path),
        "model_path": str(model_path),
        "total_bytes": _dir_size(root),
        "bronze_bytes": _dir_size(bronze_path),
        "control_plane_bytes": _dir_size(control_path),
        "model_bytes": _dir_size(model_path),
        "retention_scopes": RETENTION_SCOPES,
        "table_files": [item for item in inventory if item["scope"] in {"bronze", "models"}],
        "history_files": [item for item in inventory if item["scope"] == "run_history"],
    }


def runtime_diagnostics(
    adapter_ids: Iterable[str] | None = None,
    now: float | None = None,
) -> Dict[str, Any]:
    """Return deterministic runtime health and diagnostics for the admin UI."""
    current = _now() if now is None else float(now)
    storage = _storage_diagnostics()
    metadata = _metadata_diagnostics()
    adapters = _adapter_diagnostics(adapter_ids or ["nfl_sleeper"])
    scheduler = _scheduler_diagnostics(current)
    activity = _activity_diagnostics()
    sections = [storage, metadata, adapters, scheduler, activity]
    return {
        "status": _rollup_status(section["status"] for section in sections),
        "checked_at": current,
        "checked_at_iso": _iso(current),
        "storage": storage,
        "metadata": metadata,
        "adapters": adapters,
        "scheduler": scheduler,
        "activity": activity,
    }


def _storage_diagnostics() -> Dict[str, Any]:
    root = bronze_store.get_data_root()
    info = data_root_info()
    if root is None:
        return {
            "status": "warning",
            "message": "FOUNDRY_DATA_DIR is disabled; metadata is in memory only.",
            "writable": False,
            **info,
        }
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe_dir = root / "control_plane"
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe = probe_dir / ".diagnostics_write_test"
        probe.write_text("ok", encoding="utf-8")
        writable = probe.read_text(encoding="utf-8") == "ok"
        probe.unlink(missing_ok=True)
    except OSError as exc:
        return {
            "status": "error",
            "message": f"Data root is not writable: {exc}",
            "writable": False,
            **info,
        }
    return {
        "status": "ok" if writable else "error",
        "message": "Data root is writable." if writable else "Data root write probe failed.",
        "writable": writable,
        **data_root_info(),
    }


def _metadata_diagnostics() -> Dict[str, Any]:
    collections = []
    for name in sorted(_JSON_COLLECTIONS):
        collections.append(_json_collection_health(name))
    for name in sorted(_JSONL_COLLECTIONS):
        collections.append(_jsonl_collection_health(name))
    return {
        "status": _rollup_status(item["status"] for item in collections),
        "collection_count": len(collections),
        "total_records": sum(int(item.get("record_count") or 0) for item in collections),
        "collections": collections,
    }


def _json_collection_health(name: str) -> Dict[str, Any]:
    path = _json_path(name)
    base = {
        "name": name,
        "kind": "json",
        "path": str(path) if path is not None else None,
        "exists": bool(path and path.is_file()),
    }
    if path is None or not path.is_file():
        return {**base, "status": "ok", "record_count": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {**base, "status": "error", "record_count": 0, "message": str(exc)}
    if not isinstance(data, list):
        return {**base, "status": "error", "record_count": 0, "message": "Expected a JSON list"}
    invalid_count = sum(1 for item in data if not isinstance(item, dict))
    return {
        **base,
        "status": "warning" if invalid_count else "ok",
        "record_count": len(data) - invalid_count,
        "invalid_count": invalid_count,
    }


def _jsonl_collection_health(name: str) -> Dict[str, Any]:
    path = _jsonl_path(name)
    base = {
        "name": name,
        "kind": "jsonl",
        "path": str(path) if path is not None else None,
        "exists": bool(path and path.is_file()),
    }
    if path is None or not path.is_file():
        return {**base, "status": "ok", "record_count": 0, "invalid_count": 0}
    record_count = 0
    invalid_count = 0
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                invalid_count += 1
                continue
            if isinstance(item, dict):
                record_count += 1
            else:
                invalid_count += 1
    except OSError as exc:
        return {**base, "status": "error", "record_count": 0, "invalid_count": 0, "message": str(exc)}
    return {
        **base,
        "status": "warning" if invalid_count else "ok",
        "record_count": record_count,
        "invalid_count": invalid_count,
    }


def _adapter_diagnostics(adapter_ids: Iterable[str]) -> Dict[str, Any]:
    adapters = []
    for source_id in adapter_ids:
        adapter = get_adapter(str(source_id))
        adapters.append(
            {
                "source_id": str(source_id),
                "registered": adapter is not None,
                "status": "ok" if adapter is not None else "warning",
                "message": "Registered" if adapter is not None else "Adapter is not registered",
            }
        )
    return {
        "status": _rollup_status(item["status"] for item in adapters),
        "adapters": adapters,
    }


def _scheduler_diagnostics(now: float) -> Dict[str, Any]:
    status = scheduler_status(now)
    enabled = scheduler_enabled()
    return {
        "status": "ok" if enabled else "warning",
        "enabled": enabled,
        "interval_seconds": scheduler_interval_seconds(),
        "message": "Scheduler is enabled." if enabled else "Scheduler is disabled by environment.",
        **status,
    }


def _activity_diagnostics() -> Dict[str, Any]:
    recent_runs = list_runs(limit=20)
    failed_runs = [run for run in recent_runs if run.get("status") not in {None, "succeeded"}]
    open_alerts = list_alerts("open")
    status = "warning" if failed_runs or open_alerts else "ok"
    return {
        "status": status,
        "recent_run_count": len(recent_runs),
        "failed_run_count": len(failed_runs),
        "open_alert_count": len(open_alerts),
        "latest_run": recent_runs[0] if recent_runs else None,
        "latest_failed_run": failed_runs[0] if failed_runs else None,
    }


def _rollup_status(statuses: Iterable[str]) -> str:
    values = {str(status) for status in statuses}
    if "error" in values:
        return "error"
    if "warning" in values:
        return "warning"
    return "ok"


def storage_inventory() -> List[Dict[str, Any]]:
    """Return Foundry-owned files that can be inspected or retention-managed."""
    root = bronze_store.get_data_root()
    if root is None:
        return []
    root = root.resolve()
    items: List[Dict[str, Any]] = []

    bronze_root = root / "bronze"
    if bronze_root.is_dir():
        for path in sorted(bronze_root.glob("*/*.jsonl")):
            source_id = path.parent.name
            table = path.stem
            item = _storage_file_item(
                root,
                path,
                "bronze",
                table_id=table_id("bronze", table, source_id=source_id),
                source_id=source_id,
                table=table,
                label=f"{source_id}.{table}",
            )
            if item is not None:
                items.append(item)

    model_root = root / "models"
    if model_root.is_dir():
        for path in sorted(model_root.glob("*.jsonl")):
            model_id = path.stem
            model = get_model(model_id)
            item = _storage_file_item(
                root,
                path,
                "models",
                table_id=f"model:{model_id}",
                model_id=model_id,
                label=str((model or {}).get("name") or model_id),
            )
            if item is not None:
                items.append(item)

    control_root = root / "control_plane"
    if control_root.is_dir():
        for collection in ("runs", "quality_results", "alert_deliveries"):
            path = control_root / f"{collection}.jsonl"
            item = _storage_file_item(
                root,
                path,
                "run_history",
                collection=collection,
                label=collection,
            )
            if item is not None:
                items.append(item)

    return sorted(items, key=lambda item: (item["scope"], item["relative_path"]))


def preview_storage_cleanup(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return files that match a retention policy without deleting anything."""
    policy = _retention_policy(payload)
    root = bronze_store.get_data_root()
    candidates = []
    cutoff = policy["now"] - policy["older_than_seconds"]
    for item in storage_inventory():
        if item["scope"] not in policy["scopes"]:
            continue
        if policy.get("table_id") and not _storage_item_matches_target(item, policy["table_id"]):
            continue
        if float(item["mtime"]) <= cutoff:
            candidate = dict(item)
            candidate["age_seconds"] = max(0.0, policy["now"] - float(item["mtime"]))
            candidates.append(candidate)
    return {
        "data_root": str(root) if root is not None else None,
        "policy": policy,
        "candidate_count": len(candidates),
        "total_bytes": sum(int(item["size_bytes"]) for item in candidates),
        "candidates": candidates,
    }


def apply_storage_cleanup(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Delete Foundry-owned files matched by a retention policy."""
    preview = preview_storage_cleanup(payload)
    root = bronze_store.get_data_root()
    deleted = []
    errors = []
    if root is None:
        return {**preview, "deleted_count": 0, "deleted_bytes": 0, "deleted": [], "errors": []}
    root = root.resolve()
    for item in preview["candidates"]:
        path = Path(item["path"])
        if not _is_safe_storage_path(root, path):
            errors.append({"path": item["path"], "error": "Path is outside FOUNDRY_DATA_DIR"})
            continue
        try:
            if item["scope"] == "bronze":
                removed = bronze_store.delete_table(str(item["source_id"]), str(item["table"]))
            else:
                removed = False
                if path.is_file():
                    path.unlink()
                    removed = True
                if item["scope"] == "models":
                    _MEMORY_MODEL_ROWS.pop(_model_path_name(str(item["model_id"])), None)
                    _mark_model_storage_removed(str(item["model_id"]))
                if item["scope"] == "run_history":
                    collection = str(item.get("collection") or "")
                    if collection in _MEMORY_JSONL:
                        _MEMORY_JSONL[collection] = []
            if removed:
                deleted.append(item)
        except OSError as exc:
            errors.append({"path": item["path"], "error": str(exc)})
    return {
        **preview,
        "deleted_count": len(deleted),
        "deleted_bytes": sum(int(item["size_bytes"]) for item in deleted),
        "deleted": deleted,
        "errors": errors,
        "storage": data_root_info(),
    }


def _storage_file_item(root: Path, path: Path, scope: str, **metadata: Any) -> Dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        resolved = path.resolve()
        relative = resolved.relative_to(root.resolve())
        stat = resolved.stat()
    except (OSError, ValueError):
        return None
    return {
        "scope": scope,
        "path": str(resolved),
        "relative_path": relative.as_posix(),
        "size_bytes": stat.st_size,
        "mtime": stat.st_mtime,
        "mtime_iso": _iso(stat.st_mtime),
        **metadata,
    }


def _retention_policy(payload: Dict[str, Any]) -> Dict[str, Any]:
    scopes = _normalize_retention_scopes(payload.get("scopes"))
    raw_seconds = payload.get("older_than_seconds")
    if raw_seconds is None:
        raw_days = payload.get("older_than_days", 30)
        try:
            older_than_seconds = float(raw_days) * 86400
        except (TypeError, ValueError):
            raise ValueError("older_than_days must be a number")
    else:
        try:
            older_than_seconds = float(raw_seconds)
        except (TypeError, ValueError):
            raise ValueError("older_than_seconds must be a number")
    if older_than_seconds < 0:
        raise ValueError("Retention age must be non-negative")
    raw_now = payload.get("now")
    try:
        now_value = _now() if raw_now is None else float(raw_now)
    except (TypeError, ValueError):
        raise ValueError("now must be a Unix timestamp")
    table_target = payload.get("table_id") or payload.get("target_table_id")
    return {
        "scopes": scopes,
        "older_than_seconds": older_than_seconds,
        "older_than_days": older_than_seconds / 86400,
        "table_id": str(table_target) if table_target else None,
        "now": now_value,
    }


def _normalize_retention_scopes(value: Any) -> List[str]:
    aliases = {
        "model": "models",
        "models": "models",
        "bronze": "bronze",
        "history": "run_history",
        "run_history": "run_history",
        "control_plane": "run_history",
    }
    raw_values = value or RETENTION_SCOPES
    if isinstance(raw_values, str):
        raw_values = [part.strip() for part in raw_values.split(",") if part.strip()]
    scopes = []
    for raw in raw_values:
        scope = aliases.get(str(raw))
        if scope is None:
            raise ValueError(f"Unsupported retention scope: {raw}")
        if scope not in scopes:
            scopes.append(scope)
    return scopes or list(RETENTION_SCOPES)


def _storage_item_matches_target(item: Dict[str, Any], target: str) -> bool:
    target_value = str(target)
    return target_value in {
        str(item.get("table_id") or ""),
        str(item.get("relative_path") or ""),
        str(item.get("path") or ""),
        str(item.get("collection") or ""),
    }


def _is_safe_storage_path(root: Path, path: Path) -> bool:
    try:
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return resolved.is_file()


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def _model_root() -> Path | None:
    data_root = bronze_store.get_data_root()
    if data_root is None:
        return None
    return data_root / "models"


def model_storage_path(model_id: str) -> str | None:
    root = _model_root()
    if root is None:
        return None
    return str(root / f"{_model_path_name(model_id)}.jsonl")


def model_has_materialized_rows(model_id: str) -> bool:
    key = _model_path_name(model_id)
    if key in _MEMORY_MODEL_ROWS:
        return True
    path_value = model_storage_path(model_id)
    return bool(path_value and Path(path_value).is_file())


def get_materialized_model_rows(model_id: str) -> List[Dict[str, Any]]:
    key = _model_path_name(model_id)
    if key in _MEMORY_MODEL_ROWS:
        return [dict(row) for row in _MEMORY_MODEL_ROWS[key]]
    path_value = model_storage_path(model_id)
    if not path_value:
        return []
    path = Path(path_value)
    if not path.is_file():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
    except (json.JSONDecodeError, OSError):
        return []
    return rows


def _write_model_rows(model_id: str, rows: List[Dict[str, Any]]) -> str | None:
    key = _model_path_name(model_id)
    root = _model_root()
    if root is None:
        _MEMORY_MODEL_ROWS[key] = [dict(row) for row in rows]
        return None
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{key}.jsonl"
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)
    return str(path)


def _model_path_name(model_id: str) -> str:
    value = str(model_id)
    if value.startswith("model:"):
        value = value.split(":", 1)[1]
    return _slugify(value, "model")


def source_connector_templates() -> List[Dict[str, Any]]:
    return [dict(item) for item in SOURCE_CONNECTOR_TEMPLATES]


def list_sources() -> List[Dict[str, Any]]:
    return _read_json_collection("sources")


def get_source(source_id: str) -> Dict[str, Any] | None:
    for source in list_sources():
        if source.get("id") == source_id:
            return source
    return None


def preview_source(payload: Dict[str, Any], limit: int = 50) -> Dict[str, Any]:
    """Preview a low-code source connector without mutating bronze storage."""
    rows, source_meta = _source_rows(payload)
    source_id, table_name = _source_ids(payload, source_meta)
    stable_table_id = table_id("bronze", table_name, source_id=source_id)
    return {
        "connector": source_meta["connector"],
        "source_id": source_id,
        "name": str(payload.get("name") or source_meta.get("name") or source_id),
        "table_name": table_name,
        "table_id": stable_table_id,
        "format": source_meta.get("format"),
        "row_count": len(rows),
        "preview_rows": rows[:limit],
        "schema": infer_schema(rows[:limit]),
        "reusable": _source_is_reusable(source_meta),
    }


def ingest_source(payload: Dict[str, Any], record_run_history: bool = True) -> Dict[str, Any]:
    """Parse a low-code source and append its records to a bronze table."""
    rows, source_meta = _source_rows(payload)
    if not rows:
        raise ValueError("Source produced no rows")
    source_id, table_name = _source_ids(payload, source_meta)
    stable_table_id = table_id("bronze", table_name, source_id=source_id)
    bronze_store.append_raw(source_id, table_name, rows)
    source = _upsert_source(
        {
            "id": source_id,
            "name": str(payload.get("name") or source_meta.get("name") or source_id),
            "connector": source_meta["connector"],
            "format": source_meta.get("format"),
            "table_name": table_name,
            "table_id": stable_table_id,
            "config": _persistable_source_config(source_meta),
            "reusable": _source_is_reusable(source_meta),
            "last_row_count": len(rows),
            "last_schema": infer_schema(rows[:100]),
            "last_ingested_at": _now(),
        }
    )
    run = None
    if record_run_history:
        run = record_run(
            "source_ingest",
            target={"source_id": source_id, "table_id": stable_table_id},
            details={"row_count": len(rows), "connector": source_meta["connector"]},
        )
    return {
        "ok": True,
        "source": source,
        "table_id": stable_table_id,
        "row_count": len(rows),
        "run": run,
    }


def ingest_source_by_id(source_id: str, record_run_history: bool = True) -> Dict[str, Any]:
    """Re-run a saved reusable source by id."""
    source = get_source(source_id)
    if source is None:
        raise KeyError(source_id)
    if not source.get("reusable"):
        raise ValueError("Source cannot be re-run because its original content was uploaded")
    config = dict(source.get("config") or {})
    payload = {
        **config,
        "connector": source.get("connector"),
        "name": source.get("name"),
        "source_id": source.get("id"),
        "table_name": source.get("table_name"),
        "format": source.get("format"),
    }
    return ingest_source(payload, record_run_history=record_run_history)


def _upsert_source(record: Dict[str, Any]) -> Dict[str, Any]:
    records = list_sources()
    now = _now()
    out = dict(record)
    out["updated_at"] = now
    for idx, existing in enumerate(records):
        if existing.get("id") == out["id"]:
            out["created_at"] = existing.get("created_at") or now
            records[idx] = out
            _write_json_collection("sources", records)
            return out
    out["created_at"] = now
    records.append(out)
    _write_json_collection("sources", records)
    return out


def _source_rows(payload: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    connector = str(payload.get("connector") or payload.get("type") or "file").strip().lower()
    if connector == "file":
        return _file_source_rows(payload)
    if connector == "api":
        return _api_source_rows(payload)
    raise ValueError(f"Unsupported source connector: {connector}")


def _file_source_rows(payload: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    filename = str(payload.get("filename") or payload.get("path") or "")
    content = payload.get("content")
    path_value = payload.get("path")
    if content is None and path_value:
        path = Path(str(path_value)).expanduser()
        if not path.is_file():
            raise ValueError(f"File not found: {path}")
        content = path.read_text(encoding=str(payload.get("encoding") or "utf-8"))
        filename = path.name
    if content is None:
        raise ValueError("File source requires content or path")
    source_format = _infer_format(str(payload.get("format") or ""), filename, str(content))
    rows = _parse_structured_content(str(content), source_format, payload.get("records_path"))
    return rows, {
        "connector": "file",
        "format": source_format,
        "filename": filename,
        "path": str(path_value) if path_value else None,
        "name": Path(filename).stem if filename else None,
    }


def _api_source_rows(payload: Dict[str, Any]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    url = str(payload.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError("API source requires an http(s) URL")
    request = Request(url, headers={"User-Agent": "analytics-foundry/0.1"})
    try:
        with urlopen(request, timeout=15) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            content = response.read().decode(charset)
    except URLError as exc:
        raise ValueError(f"API request failed: {exc}") from exc
    rows = _parse_structured_content(content, "json", payload.get("records_path"))
    return rows, {
        "connector": "api",
        "format": "json",
        "url": url,
        "records_path": payload.get("records_path"),
        "name": url.rstrip("/").split("/")[-1] or "api_source",
    }


def _infer_format(requested: str, filename: str, content: str) -> str:
    value = requested.strip().lower()
    if value and value != "auto":
        return value
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix in {"csv", "tsv", "json", "jsonl", "ndjson"}:
        return "jsonl" if suffix == "ndjson" else suffix
    stripped = content.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return "json"
    return "csv"


def _parse_structured_content(
    content: str,
    source_format: str,
    records_path: Any = None,
) -> List[Dict[str, Any]]:
    normalized = content.lstrip("\ufeff")
    if source_format == "csv":
        return _parse_delimited(normalized, ",")
    if source_format == "tsv":
        return _parse_delimited(normalized, "\t")
    if source_format == "json":
        return _extract_json_records(json.loads(normalized), records_path)
    if source_format == "jsonl":
        rows = []
        for line in normalized.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.extend(_coerce_records(json.loads(line)))
        return rows
    raise ValueError(f"Unsupported source format: {source_format}")


def _parse_delimited(content: str, delimiter: str) -> List[Dict[str, Any]]:
    reader = csv.DictReader(StringIO(content), delimiter=delimiter)
    rows = []
    for row in reader:
        cleaned = {}
        for key, value in row.items():
            name = str(key).strip() if key is not None else "_extra"
            cleaned[name] = value
        rows.append(cleaned)
    return rows


def _extract_json_records(data: Any, records_path: Any = None) -> List[Dict[str, Any]]:
    value = data
    if records_path:
        for part in str(records_path).split("."):
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and part.isdigit():
                value = value[int(part)]
            else:
                raise ValueError(f"records_path not found: {records_path}")
    if isinstance(value, dict) and not records_path:
        for candidate in value.values():
            if isinstance(candidate, list) and candidate:
                return _coerce_records(candidate)
    return _coerce_records(value)


def _coerce_records(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [
            dict(item) if isinstance(item, dict) else {"value": item}
            for item in value
        ]
    if isinstance(value, dict):
        return [dict(value)]
    return [{"value": value}]


def _source_ids(payload: Dict[str, Any], source_meta: Dict[str, Any]) -> tuple[str, str]:
    source_seed = payload.get("source_id") or payload.get("name") or source_meta.get("name") or "personal_source"
    source_id = _slugify(str(source_seed), "personal_source")
    table_seed = payload.get("table_name") or payload.get("table") or source_meta.get("name") or source_id
    table_name = _slugify(str(table_seed), "records")
    return source_id, table_name


def _slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    return (slug or fallback)[:80]


def _persistable_source_config(source_meta: Dict[str, Any]) -> Dict[str, Any]:
    config = {"format": source_meta.get("format")}
    if source_meta["connector"] == "file":
        if source_meta.get("path"):
            config["path"] = source_meta["path"]
        if source_meta.get("filename"):
            config["filename"] = source_meta["filename"]
    if source_meta["connector"] == "api":
        config["url"] = source_meta.get("url")
        if source_meta.get("records_path"):
            config["records_path"] = source_meta["records_path"]
    return {key: value for key, value in config.items() if value is not None}


def _source_is_reusable(source_meta: Dict[str, Any]) -> bool:
    if source_meta["connector"] == "api":
        return bool(source_meta.get("url"))
    if source_meta["connector"] == "file":
        return bool(source_meta.get("path"))
    return False


def table_id(layer: str, name: str, source_id: str | None = None) -> str:
    if layer == "bronze":
        if not source_id:
            raise ValueError("Bronze table_id requires source_id")
        return f"bronze:{source_id}.{name}"
    return f"{layer}:{name}"


def parse_table_id(value: str) -> Dict[str, str]:
    """Parse a stable table id like bronze:nfl_sleeper.players or silver:players."""
    if ":" not in value:
        raise ValueError("Table id must include a layer prefix")
    layer, rest = value.split(":", 1)
    if layer == "bronze":
        if "." not in rest:
            raise ValueError("Bronze table id must be bronze:{source_id}.{table}")
        source_id, table = rest.split(".", 1)
        if not source_id or not table:
            raise ValueError("Bronze table id must include source_id and table")
        return {"layer": layer, "source_id": source_id, "name": table}
    if layer not in {"silver", "gold", "model"}:
        raise ValueError(f"Unsupported table layer: {layer}")
    if not rest:
        raise ValueError("Table id must include a table name")
    return {"layer": layer, "name": rest}


def bronze_storage_path(source_id: str, table: str) -> str | None:
    root = bronze_store.get_data_root()
    if root is None:
        return None
    return str(root / "bronze" / source_id / f"{table}.jsonl")


def infer_schema(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Infer lightweight schema metadata from JSON-like rows."""
    rows_list = list(rows)
    row_count = len(rows_list)
    order: List[str] = []
    stats: Dict[str, Dict[str, Any]] = {}
    for row in rows_list:
        for key, value in row.items():
            if key not in stats:
                order.append(key)
                stats[key] = {
                    "types": set(),
                    "non_null_count": 0,
                    "example": None,
                }
            if value is not None:
                stats[key]["types"].add(_value_type(value))
                stats[key]["non_null_count"] += 1
                if stats[key]["example"] is None and value != "":
                    stats[key]["example"] = value
            else:
                stats[key]["types"].add("null")
    schema = []
    for key in order:
        item = stats[key]
        non_null = item["non_null_count"]
        schema.append(
            {
                "name": key,
                "types": sorted(item["types"]) or ["unknown"],
                "nullable": non_null < row_count,
                "non_null_count": non_null,
                "example": item["example"],
            }
        )
    return schema


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def table_profile(
    stable_table_id: str,
    rows: List[Dict[str, Any]],
    storage_path: str | None = None,
) -> Dict[str, Any]:
    parsed = parse_table_id(stable_table_id)
    path = Path(storage_path) if storage_path else None
    size_bytes = path.stat().st_size if path is not None and path.is_file() else 0
    lineage = lineage_for_table(stable_table_id)
    return {
        "table_id": stable_table_id,
        "layer": parsed["layer"],
        "name": parsed["name"],
        "source_id": parsed.get("source_id"),
        "row_count": len(rows),
        "schema": infer_schema(rows),
        "freshness": _freshness(rows, path),
        "storage_path": str(path) if path is not None else None,
        "size_bytes": size_bytes,
        "upstream": lineage["upstream"],
        "downstream": lineage["downstream"],
    }


def _freshness(rows: List[Dict[str, Any]], storage_path: Path | None) -> Dict[str, Any]:
    if storage_path is not None and storage_path.is_file():
        ts = storage_path.stat().st_mtime
        return {"source": "storage_mtime", "timestamp": ts, "iso": _iso(ts)}
    latest = None
    for row in rows:
        for key in ("updated_at", "ingested_at", "timestamp", "created_at"):
            parsed = _parse_timestamp(row.get(key))
            if parsed is not None and (latest is None or parsed > latest):
                latest = parsed
    return {
        "source": "row_timestamp" if latest is not None else "unavailable",
        "timestamp": latest,
        "iso": _iso(latest),
    }


def list_lineage_edges() -> List[Dict[str, str]]:
    edges = []
    for downstream, upstream_list in _CORE_LINEAGE.items():
        for upstream in upstream_list:
            edges.append({"from": upstream, "to": downstream, "kind": "core"})
    for source in list_sources():
        if source.get("table_id") and source.get("id"):
            edges.append(
                {
                    "from": f"source:{source['id']}",
                    "to": source["table_id"],
                    "kind": "source",
                }
            )
    for model in list_models():
        target = model["target_table_id"]
        for upstream in _model_source_tables(model):
            edges.append({"from": upstream, "to": target, "kind": "model"})
    return edges


def lineage_for_table(stable_table_id: str) -> Dict[str, List[str]]:
    upstream = []
    downstream = []
    for edge in list_lineage_edges():
        if edge["to"] == stable_table_id:
            upstream.append(edge["from"])
        if edge["from"] == stable_table_id:
            downstream.append(edge["to"])
    return {"upstream": sorted(set(upstream)), "downstream": sorted(set(downstream))}


def create_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    jobs = _read_json_collection("jobs")
    ts = _now()
    schedule = _normalize_schedule(payload.get("schedule") or {"type": "manual"})
    configured_next = payload.get("next_run_at")
    job = {
        "id": _new_id("job"),
        "name": str(payload.get("name") or payload.get("kind") or "Untitled job"),
        "kind": str(payload.get("kind") or "quality_check"),
        "target": payload.get("target") or {},
        "schedule": schedule,
        "enabled": bool(payload.get("enabled", True)),
        "retry_count": int(payload.get("retry_count", 0) or 0),
        "retry_delay_seconds": int(payload.get("retry_delay_seconds", 60) or 60),
        "failed_attempts": 0,
        "created_at": ts,
        "updated_at": ts,
        "last_run_id": None,
        "last_status": None,
        "last_run_at": None,
        "next_run_at": float(configured_next) if configured_next is not None else _next_run_at(schedule, ts),
    }
    jobs.append(job)
    _write_json_collection("jobs", jobs)
    return job


def list_jobs() -> List[Dict[str, Any]]:
    return _read_json_collection("jobs")


def get_job(job_id: str) -> Dict[str, Any] | None:
    for job in list_jobs():
        if job.get("id") == job_id:
            return job
    return None


def mark_job_run(job_id: str, run: Dict[str, Any]) -> None:
    jobs = _read_json_collection("jobs")
    ts = run.get("finished_at") or run.get("timestamp") or _now()
    for job in jobs:
        if job.get("id") == job_id:
            status = run.get("status")
            if status == "succeeded":
                job["failed_attempts"] = 0
                next_run = _next_run_at(job.get("schedule") or {}, ts)
            else:
                failed_attempts = int(job.get("failed_attempts") or 0) + 1
                job["failed_attempts"] = failed_attempts
                retry_count = int(job.get("retry_count") or 0)
                if failed_attempts <= retry_count:
                    next_run = ts + int(job.get("retry_delay_seconds") or 60)
                else:
                    next_run = _next_run_at(job.get("schedule") or {}, ts)
            job["last_run_id"] = run["id"]
            job["last_status"] = status
            job["last_run_at"] = ts
            job["updated_at"] = _now()
            job["next_run_at"] = next_run
            break
    _write_json_collection("jobs", jobs)


def _next_run_at(schedule: Dict[str, Any], from_ts: float) -> float | None:
    schedule_type = str(schedule.get("type") or "manual").strip().lower()
    if schedule_type == "hourly":
        return from_ts + 3600
    if schedule_type == "daily":
        if schedule.get("time"):
            return _next_time_of_day_run(str(schedule["time"]), from_ts)
        return from_ts + 86400
    if schedule_type == "weekly":
        return _next_weekly_run(schedule, from_ts)
    if schedule_type == "interval":
        seconds = int(schedule.get("seconds") or schedule.get("interval_seconds") or 60)
        return from_ts + max(1, seconds)
    if schedule_type == "cron":
        return _next_cron_run(str(schedule.get("expression") or ""), from_ts)
    return None


def _normalize_schedule(schedule: Dict[str, Any]) -> Dict[str, Any]:
    schedule_type = str(schedule.get("type") or "manual").strip().lower()
    if schedule_type == "manual":
        return {"type": "manual"}
    if schedule_type == "interval":
        seconds = int(schedule.get("seconds") or schedule.get("interval_seconds") or 60)
        return {"type": "interval", "seconds": max(1, seconds)}
    if schedule_type == "hourly":
        return {"type": "hourly"}
    if schedule_type == "daily":
        normalized = {"type": "daily"}
        if schedule.get("time") or schedule.get("at"):
            normalized["time"] = _normalize_time_of_day(str(schedule.get("time") or schedule.get("at")))
        return normalized
    if schedule_type == "weekly":
        return {
            "type": "weekly",
            "day_of_week": _normalize_weekday(schedule.get("day_of_week")),
            "time": _normalize_time_of_day(str(schedule.get("time") or schedule.get("at") or "09:00")),
        }
    if schedule_type == "cron":
        expression = str(schedule.get("expression") or "").strip()
        _parse_cron_expression(expression)
        return {"type": "cron", "expression": expression}
    raise ValueError(f"Unsupported schedule type: {schedule_type}")


def _normalize_time_of_day(value: str) -> str:
    parts = value.strip().split(":")
    if len(parts) not in {2, 3}:
        raise ValueError("Schedule time must be HH:MM")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError("Schedule time must be HH:MM") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Schedule time must be between 00:00 and 23:59")
    return f"{hour:02d}:{minute:02d}"


def _next_time_of_day_run(value: str, from_ts: float) -> float:
    hour, minute = [int(part) for part in _normalize_time_of_day(value).split(":")]
    current = datetime.fromtimestamp(float(from_ts), tz=timezone.utc)
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate.timestamp() <= float(from_ts):
        candidate = candidate + _DAY
    return candidate.timestamp()


_WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "0": 0,
    "tuesday": 1,
    "tue": 1,
    "1": 1,
    "wednesday": 2,
    "wed": 2,
    "2": 2,
    "thursday": 3,
    "thu": 3,
    "3": 3,
    "friday": 4,
    "fri": 4,
    "4": 4,
    "saturday": 5,
    "sat": 5,
    "5": 5,
    "sunday": 6,
    "sun": 6,
    "6": 6,
    "7": 6,
}
_DAY = timedelta(days=1)


def _normalize_weekday(value: Any) -> str:
    raw = "monday" if value is None else str(value).strip().lower()
    if raw not in _WEEKDAYS:
        raise ValueError("Weekly schedule day_of_week must be a weekday name or 0-6")
    return ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][_WEEKDAYS[raw]]


def _next_weekly_run(schedule: Dict[str, Any], from_ts: float) -> float:
    day = _WEEKDAYS[_normalize_weekday(schedule.get("day_of_week"))]
    hour, minute = [int(part) for part in _normalize_time_of_day(str(schedule.get("time") or "09:00")).split(":")]
    current = datetime.fromtimestamp(float(from_ts), tz=timezone.utc)
    days_until = (day - current.weekday()) % 7
    candidate = (current + timedelta(days=days_until)).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )
    if candidate.timestamp() <= float(from_ts):
        candidate = candidate + timedelta(days=7)
    return candidate.timestamp()


def _next_cron_run(expression: str, from_ts: float) -> float:
    fields = _parse_cron_expression(expression)
    start = datetime.fromtimestamp(float(from_ts), tz=timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for offset in range(0, 366 * 24 * 60):
        candidate = start + timedelta(minutes=offset)
        if (
            candidate.minute in fields["minute"]
            and candidate.hour in fields["hour"]
            and candidate.day in fields["day"]
            and candidate.month in fields["month"]
            and candidate.weekday() in fields["weekday"]
        ):
            return candidate.timestamp()
    raise ValueError("Cron expression has no matching run time in the next year")


def _parse_cron_expression(expression: str) -> Dict[str, set[int]]:
    parts = expression.split()
    if len(parts) != 5:
        raise ValueError("Cron schedule must use five fields: minute hour day month weekday")
    return {
        "minute": _parse_cron_field(parts[0], 0, 59, "minute"),
        "hour": _parse_cron_field(parts[1], 0, 23, "hour"),
        "day": _parse_cron_field(parts[2], 1, 31, "day"),
        "month": _parse_cron_field(parts[3], 1, 12, "month"),
        "weekday": _normalize_cron_weekdays(_parse_cron_field(parts[4], 0, 7, "weekday")),
    }


def _normalize_cron_weekdays(values: set[int]) -> set[int]:
    return {6 if value in {0, 7} else value - 1 for value in values}


def _parse_cron_field(
    value: str,
    minimum: int,
    maximum: int,
    label: str,
) -> set[int]:
    values: set[int] = set()
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            raise ValueError(f"Cron {label} field is empty")
        base, step = (part.split("/", 1) + ["1"])[:2] if "/" in part else (part, "1")
        try:
            step_value = int(step)
        except ValueError as exc:
            raise ValueError(f"Cron {label} step must be a number") from exc
        if step_value < 1:
            raise ValueError(f"Cron {label} step must be at least 1")
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            start_raw, end_raw = base.split("-", 1)
            start = _cron_int(start_raw, label)
            end = _cron_int(end_raw, label)
        else:
            start = end = _cron_int(base, label)
        if start < minimum or start > maximum or end < minimum or end > maximum or start > end:
            raise ValueError(f"Cron {label} field is out of range")
        values.update(range(start, end + 1, step_value))
    return values


def _cron_int(value: str, label: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Cron {label} field must be numeric") from exc


def list_due_jobs(now: float | None = None) -> List[Dict[str, Any]]:
    """Return enabled jobs whose next_run_at is due."""
    current = _now() if now is None else float(now)
    due = []
    for job in list_jobs():
        next_run_at = job.get("next_run_at")
        if not job.get("enabled", True) or next_run_at is None:
            continue
        if float(next_run_at) <= current:
            due.append(job)
    return sorted(due, key=lambda item: float(item.get("next_run_at") or 0))


def scheduler_status(now: float | None = None) -> Dict[str, Any]:
    """Return a lightweight scheduler status summary."""
    current = _now() if now is None else float(now)
    jobs = list_jobs()
    enabled_jobs = [job for job in jobs if job.get("enabled", True)]
    due_jobs = list_due_jobs(current)
    future_runs = [
        float(job["next_run_at"])
        for job in enabled_jobs
        if job.get("next_run_at") is not None and float(job["next_run_at"]) > current
    ]
    return {
        "now": current,
        "job_count": len(jobs),
        "enabled_job_count": len(enabled_jobs),
        "due_count": len(due_jobs),
        "due_job_ids": [job["id"] for job in due_jobs],
        "next_due_at": min(future_runs) if future_runs else None,
    }


def record_run(
    kind: str,
    status: str = "succeeded",
    league_id: str | None = None,
    job_id: str | None = None,
    target: Dict[str, Any] | None = None,
    message: str | None = None,
    details: Dict[str, Any] | None = None,
    started_at: float | None = None,
    finished_at: float | None = None,
) -> Dict[str, Any]:
    finish = finished_at or _now()
    start = started_at or finish
    run = {
        "id": _new_id("run"),
        "kind": kind,
        "status": status,
        "league_id": league_id,
        "job_id": job_id,
        "target": target or {},
        "message": message or "",
        "details": details or {},
        "timestamp": finish,
        "started_at": start,
        "finished_at": finish,
        "duration_seconds": max(0.0, finish - start),
    }
    _append_jsonl_collection("runs", run)
    return run


def list_runs(limit: int = 50) -> List[Dict[str, Any]]:
    records = list(reversed(_read_jsonl_collection("runs")))
    return records[:limit]


def quality_templates() -> List[Dict[str, Any]]:
    return [dict(item) for item in QUALITY_TEMPLATES]


def quality_authoring_context(
    table: str,
    rows: List[Dict[str, Any]],
    reference_tables: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Return table-aware metadata for low-code quality rule authoring."""
    parse_table_id(table)
    columns = _quality_column_metadata(rows)
    return {
        "table_id": table,
        "row_count": len(rows),
        "columns": columns,
        "templates": _quality_templates_for_columns(columns),
        "reference_tables": reference_tables or [],
    }


def create_quality_rule(payload: Dict[str, Any]) -> Dict[str, Any]:
    rule_type = str(payload.get("type") or "")
    known_types = {template["type"] for template in QUALITY_TEMPLATES}
    if rule_type not in known_types:
        raise ValueError(f"Unsupported quality rule type: {rule_type}")
    table = str(payload.get("table_id") or "")
    parse_table_id(table)
    ts = _now()
    rule = {
        "id": _new_id("rule"),
        "name": str(payload.get("name") or rule_type.replace("_", " ").title()),
        "table_id": table,
        "type": rule_type,
        "column": payload.get("column"),
        "params": payload.get("params") or {},
        "severity": str(payload.get("severity") or "error"),
        "enabled": bool(payload.get("enabled", True)),
        "created_at": ts,
        "updated_at": ts,
    }
    rules = _read_json_collection("quality_rules")
    rules.append(rule)
    _write_json_collection("quality_rules", rules)
    return rule


def list_quality_rules(table: str | None = None) -> List[Dict[str, Any]]:
    rules = _read_json_collection("quality_rules")
    if table is not None:
        rules = [rule for rule in rules if rule.get("table_id") == table]
    return rules


def run_quality_rules(
    table: str,
    rows_resolver: RowsResolver,
    rule_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    rows = rows_resolver(table)
    rules = [
        rule
        for rule in list_quality_rules(table)
        if rule.get("enabled", True)
        and (rule_ids is None or str(rule.get("id")) in set(rule_ids))
    ]
    results = []
    for rule in rules:
        result = evaluate_rule(rule, rows, rows_resolver)
        _append_jsonl_collection("quality_results", result)
        if result["status"] in {"failed", "error"}:
            create_alert(
                title=f"Quality check {result['status']}: {rule['name']}",
                message=result["message"],
                severity=rule.get("severity") or "error",
                table_id=table,
                rule_id=rule["id"],
                run_id=result["id"],
            )
        results.append(result)
    return results


def list_quality_results(table: str | None = None, limit: int = 100) -> List[Dict[str, Any]]:
    records = list(reversed(_read_jsonl_collection("quality_results")))
    if table is not None:
        records = [record for record in records if record.get("table_id") == table]
    return records[:limit]


def evaluate_rule(
    rule: Dict[str, Any],
    rows: List[Dict[str, Any]],
    rows_resolver: RowsResolver | None = None,
) -> Dict[str, Any]:
    rule_type = str(rule.get("type") or "")
    column = rule.get("column") or (rule.get("params") or {}).get("column")
    params = rule.get("params") or {}
    failures: List[Dict[str, Any]] = []
    status = "passed"
    message = "Rule passed"
    try:
        if rule_type == "required":
            failures = _row_failures(rows, lambda row: _is_blank(row.get(str(column))), column)
        elif rule_type == "unique":
            failures = _unique_failures(rows, str(column))
        elif rule_type == "accepted_values":
            accepted = set(params.get("values") or [])
            failures = _row_failures(rows, lambda row: row.get(str(column)) not in accepted, column)
        elif rule_type == "numeric_range":
            failures = _numeric_range_failures(rows, str(column), params)
        elif rule_type == "regex":
            pattern = re.compile(str(params.get("pattern") or ""))
            failures = _row_failures(
                rows,
                lambda row: pattern.search(str(row.get(str(column)) or "")) is None,
                column,
            )
        elif rule_type == "freshness":
            failures, message = _freshness_failures(rows, str(column), params)
        elif rule_type == "row_count_drift":
            failures, message = _row_count_drift_failures(rows, params)
        elif rule_type == "referential":
            failures = _referential_failures(rows, str(column), params, rows_resolver)
        else:
            status = "error"
            message = f"Unsupported rule type: {rule_type}"
    except Exception as exc:  # Defensive: failed checks should report, not crash the UI.
        status = "error"
        message = str(exc)
    if status != "error" and failures:
        status = "failed"
        message = f"{len(failures)} row(s) failed"
    checked_at = _now()
    return {
        "id": _new_id("qres"),
        "rule_id": rule.get("id"),
        "rule_name": rule.get("name"),
        "table_id": rule.get("table_id"),
        "status": status,
        "severity": rule.get("severity") or "error",
        "checked_at": checked_at,
        "row_count": len(rows),
        "failed_count": len(failures),
        "message": message,
        "sample_failures": failures[:10],
        "sample_failed_rows": [
            failure["row"]
            for failure in failures[:10]
            if isinstance(failure.get("row"), dict)
        ],
    }


def _row_failures(
    rows: List[Dict[str, Any]],
    predicate: Callable[[Dict[str, Any]], bool],
    column: Any,
) -> List[Dict[str, Any]]:
    failures = []
    col = str(column)
    for idx, row in enumerate(rows):
        if predicate(row):
            failures.append(_failure_sample(idx, col, row.get(col), row))
    return failures


def _unique_failures(rows: List[Dict[str, Any]], column: str) -> List[Dict[str, Any]]:
    seen: Dict[Any, int] = {}
    failures = []
    for idx, row in enumerate(rows):
        value = row.get(column)
        if _is_blank(value):
            continue
        if value in seen:
            failures.append(_failure_sample(idx, column, value, row))
        else:
            seen[value] = idx
    return failures


def _numeric_range_failures(
    rows: List[Dict[str, Any]],
    column: str,
    params: Dict[str, Any],
) -> List[Dict[str, Any]]:
    min_value = params.get("min")
    max_value = params.get("max")
    failures = []
    for idx, row in enumerate(rows):
        value = _to_float(row.get(column))
        if value is None:
            failures.append(_failure_sample(idx, column, row.get(column), row))
            continue
        if min_value is not None and value < float(min_value):
            failures.append(_failure_sample(idx, column, row.get(column), row))
        elif max_value is not None and value > float(max_value):
            failures.append(_failure_sample(idx, column, row.get(column), row))
    return failures


def _freshness_failures(
    rows: List[Dict[str, Any]],
    column: str,
    params: Dict[str, Any],
) -> tuple[List[Dict[str, Any]], str]:
    max_age = float(params.get("max_age_seconds") or 0)
    if max_age <= 0:
        return [], "No max_age_seconds configured"
    latest = None
    for row in rows:
        parsed = _parse_timestamp(row.get(column))
        if parsed is not None and (latest is None or parsed > latest):
            latest = parsed
    if latest is None:
        return [{"row_index": None, "column": column, "value": None}], "No parseable timestamp"
    age = _now() - latest
    if age > max_age:
        return [
            {"row_index": None, "column": column, "value": _iso(latest), "age_seconds": age}
        ], f"Latest timestamp is {int(age)} seconds old"
    return [], "Rule passed"


def _row_count_drift_failures(
    rows: List[Dict[str, Any]],
    params: Dict[str, Any],
) -> tuple[List[Dict[str, Any]], str]:
    count = len(rows)
    min_count = params.get("min_count")
    max_count = params.get("max_count")
    if min_count is not None and count < int(min_count):
        return [{"row_index": None, "column": "row_count", "value": count}], "Row count below minimum"
    if max_count is not None and count > int(max_count):
        return [{"row_index": None, "column": "row_count", "value": count}], "Row count above maximum"
    baseline = params.get("baseline_count")
    max_pct = params.get("max_percent_change")
    if baseline is not None and max_pct is not None:
        baseline_num = float(baseline)
        if baseline_num == 0 and count != 0:
            return [{"row_index": None, "column": "row_count", "value": count}], "Baseline was zero"
        if baseline_num != 0:
            pct_change = abs(count - baseline_num) / baseline_num * 100
            if pct_change > float(max_pct):
                return [
                    {
                        "row_index": None,
                        "column": "row_count",
                        "value": count,
                        "percent_change": pct_change,
                    }
                ], "Row count changed beyond threshold"
    return [], "Rule passed"


def _referential_failures(
    rows: List[Dict[str, Any]],
    column: str,
    params: Dict[str, Any],
    rows_resolver: RowsResolver | None,
) -> List[Dict[str, Any]]:
    if rows_resolver is None:
        raise ValueError("Referential checks require a rows resolver")
    reference_table = str(params.get("reference_table_id") or "")
    reference_column = str(params.get("reference_column") or "")
    if not reference_table or not reference_column:
        raise ValueError("reference_table_id and reference_column are required")
    reference_values = {
        row.get(reference_column)
        for row in rows_resolver(reference_table)
        if not _is_blank(row.get(reference_column))
    }
    failures = []
    for idx, row in enumerate(rows):
        value = row.get(column)
        if _is_blank(value):
            continue
        if value not in reference_values:
            failures.append(_failure_sample(idx, column, value, row))
    return failures


def _failure_sample(
    row_index: int | None,
    column: str,
    value: Any,
    row: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    sample = {"row_index": row_index, "column": column, "value": value}
    if row is not None:
        sample["row"] = _sample_row(row)
    return sample


def _sample_row(row: Dict[str, Any]) -> Dict[str, Any]:
    sample: Dict[str, Any] = {}
    for idx, (key, value) in enumerate(row.items()):
        if idx >= 20:
            sample["_truncated"] = True
            break
        if isinstance(value, str) and len(value) > 200:
            sample[key] = value[:200] + "..."
        else:
            sample[key] = value
    return sample


def _quality_column_metadata(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    schema = infer_schema(rows)
    columns = []
    for column in schema:
        name = str(column["name"])
        values = [row.get(name) for row in rows if not _is_blank(row.get(name))]
        numeric_count = sum(1 for value in values if _to_float(value) is not None)
        timestamp_count = sum(1 for value in values if _looks_like_timestamp_value(name, value))
        non_blank_count = len(values)
        distinct_values = _distinct_quality_values(values)
        column_kind = "text"
        if non_blank_count and timestamp_count >= max(1, int(non_blank_count * 0.6)):
            column_kind = "timestamp"
        elif non_blank_count and numeric_count >= max(1, int(non_blank_count * 0.8)):
            column_kind = "numeric"
        elif len(distinct_values) <= 20:
            column_kind = "categorical"
        columns.append(
            {
                **column,
                "quality_kind": column_kind,
                "distinct_values": distinct_values[:20],
                "suggested_rules": _suggested_rules_for_quality_kind(column_kind),
            }
        )
    return columns


def _distinct_quality_values(values: List[Any]) -> List[Any]:
    distinct = []
    seen = set()
    for value in values:
        key = json.dumps(value, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        distinct.append(value)
        if len(distinct) >= 50:
            break
    return distinct


def _suggested_rules_for_quality_kind(kind: str) -> List[str]:
    rules = ["required", "unique", "accepted_values", "referential"]
    if kind == "numeric":
        rules.append("numeric_range")
    if kind == "timestamp":
        rules.append("freshness")
    if kind in {"text", "categorical"}:
        rules.append("regex")
    return rules


def _looks_like_timestamp_value(column_name: str, value: Any) -> bool:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return False
    name = column_name.lower()
    if any(part in name for part in ("time", "date", "_at", "timestamp")):
        return True
    if isinstance(value, str):
        raw = value.strip()
        return any(token in raw for token in ("-", "T", ":", "Z", "+"))
    return False


def _quality_templates_for_columns(columns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_kind = {
        "numeric": [column["name"] for column in columns if column.get("quality_kind") == "numeric"],
        "timestamp": [column["name"] for column in columns if column.get("quality_kind") == "timestamp"],
        "text": [column["name"] for column in columns if column.get("quality_kind") in {"text", "categorical"}],
        "all": [column["name"] for column in columns],
    }
    templates = []
    for template in quality_templates():
        rule_type = template["type"]
        if rule_type == "row_count_drift":
            compatible = []
            requires_column = False
        elif rule_type == "numeric_range":
            compatible = by_kind["numeric"]
            requires_column = True
        elif rule_type == "freshness":
            compatible = by_kind["timestamp"]
            requires_column = True
        elif rule_type == "regex":
            compatible = by_kind["text"]
            requires_column = True
        else:
            compatible = by_kind["all"]
            requires_column = True
        templates.append(
            {
                **template,
                "requires_column": requires_column,
                "compatible_columns": compatible,
            }
        )
    return templates


def _is_blank(value: Any) -> bool:
    return value is None or value == ""


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            pass
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    return None


def alert_delivery_templates() -> List[Dict[str, Any]]:
    """Return supported external alert delivery adapters."""
    return [
        {
            "kind": "webhook",
            "label": "Generic webhook",
            "params": ["name", "url", "severities", "enabled"],
        },
        {
            "kind": "slack_webhook",
            "label": "Slack-style webhook",
            "params": ["name", "url", "severities", "enabled"],
        },
    ]


def create_alert_delivery_target(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a persisted alert delivery target."""
    kind = str(payload.get("kind") or "webhook")
    if kind not in ALERT_DELIVERY_KINDS:
        raise ValueError(f"Unsupported alert delivery kind: {kind}")
    url = str(payload.get("url") or "").strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("Alert delivery target URL must start with http:// or https://")
    headers = payload.get("headers") or {}
    if not isinstance(headers, dict):
        raise ValueError("headers must be an object")
    ts = _now()
    target = {
        "id": _new_id("delivery"),
        "name": str(payload.get("name") or kind.replace("_", " ").title()),
        "kind": kind,
        "url": url,
        "headers": {str(key): str(value) for key, value in headers.items()},
        "severities": _normalize_alert_severities(payload.get("severities")),
        "enabled": bool(payload.get("enabled", True)),
        "timeout_seconds": max(1, int(payload.get("timeout_seconds", 10) or 10)),
        "created_at": ts,
        "updated_at": ts,
        "last_status": None,
        "last_delivered_at": None,
        "last_error": None,
    }
    targets = _read_json_collection("alert_delivery_targets")
    targets.append(target)
    _write_json_collection("alert_delivery_targets", targets)
    return target


def list_alert_delivery_targets() -> List[Dict[str, Any]]:
    return _read_json_collection("alert_delivery_targets")


def get_alert_delivery_target(target_id: str) -> Dict[str, Any] | None:
    for target in list_alert_delivery_targets():
        if target.get("id") == target_id:
            return target
    return None


def set_alert_delivery_target_enabled(target_id: str, enabled: bool) -> Dict[str, Any] | None:
    targets = list_alert_delivery_targets()
    updated = None
    for target in targets:
        if target.get("id") == target_id:
            target["enabled"] = bool(enabled)
            target["updated_at"] = _now()
            updated = target
            break
    _write_json_collection("alert_delivery_targets", targets)
    return updated


def test_alert_delivery_target(target_id: str) -> Dict[str, Any] | None:
    """Send a synthetic alert through one target and return the delivery log row."""
    target = get_alert_delivery_target(target_id)
    if target is None:
        return None
    alert = {
        "id": "alert_test",
        "title": "Analytics Foundry test alert",
        "message": "Delivery target test from the local Workbench.",
        "severity": "info",
        "status": "test",
        "table_id": None,
        "rule_id": None,
        "run_id": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    deliveries = deliver_alert(alert, target_ids=[target_id], force=True)
    return deliveries[0] if deliveries else None


def deliver_alert(
    alert: Dict[str, Any],
    target_ids: List[str] | None = None,
    force: bool = False,
) -> List[Dict[str, Any]]:
    """Deliver an alert to matching external targets and record delivery attempts."""
    selected_targets = []
    target_filter = set(target_ids or [])
    for target in list_alert_delivery_targets():
        if target_filter and str(target.get("id")) not in target_filter:
            continue
        if not force and not target.get("enabled", True):
            continue
        if not force and not _alert_target_accepts_severity(target, str(alert.get("severity") or "info")):
            continue
        selected_targets.append(target)

    deliveries = []
    for target in selected_targets:
        deliveries.append(_deliver_alert_to_target(alert, target))
    return deliveries


def create_alert(
    title: str,
    message: str,
    severity: str = "error",
    table_id: str | None = None,
    rule_id: str | None = None,
    run_id: str | None = None,
) -> Dict[str, Any]:
    alerts = _read_json_collection("alerts")
    ts = _now()
    alert = {
        "id": _new_id("alert"),
        "title": title,
        "message": message,
        "severity": severity,
        "status": "open",
        "table_id": table_id,
        "rule_id": rule_id,
        "run_id": run_id,
        "created_at": ts,
        "updated_at": ts,
        "delivery_status": "none",
        "delivery_attempt_count": 0,
    }
    alerts.insert(0, alert)
    _write_json_collection("alerts", alerts)
    deliveries = deliver_alert(alert)
    if deliveries:
        delivery_status = _summarize_delivery_status(deliveries)
        _update_alert_delivery_status(alert["id"], delivery_status, len(deliveries))
        alert["delivery_status"] = delivery_status
        alert["delivery_attempt_count"] = len(deliveries)
    return alert


def list_alerts(status: str | None = None) -> List[Dict[str, Any]]:
    alerts = _read_json_collection("alerts")
    if status is not None:
        alerts = [alert for alert in alerts if alert.get("status") == status]
    return alerts


def acknowledge_alert(alert_id: str) -> Dict[str, Any] | None:
    alerts = _read_json_collection("alerts")
    found = None
    for alert in alerts:
        if alert.get("id") == alert_id:
            alert["status"] = "acknowledged"
            alert["updated_at"] = _now()
            found = alert
            break
    _write_json_collection("alerts", alerts)
    return found


def list_alert_deliveries(
    alert_id: str | None = None,
    target_id: str | None = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    records = list(reversed(_read_jsonl_collection("alert_deliveries")))
    if alert_id is not None:
        records = [record for record in records if record.get("alert_id") == alert_id]
    if target_id is not None:
        records = [record for record in records if record.get("target_id") == target_id]
    return records[:limit]


def _deliver_alert_to_target(alert: Dict[str, Any], target: Dict[str, Any]) -> Dict[str, Any]:
    start = _now()
    payload = _alert_delivery_payload(alert, target)
    headers = {
        "Content-Type": "application/json",
        **(target.get("headers") or {}),
    }
    request = Request(
        str(target["url"]),
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    delivery = {
        "id": _new_id("delivery_attempt"),
        "alert_id": alert.get("id"),
        "target_id": target.get("id"),
        "target_name": target.get("name"),
        "kind": target.get("kind"),
        "url": target.get("url"),
        "status": "failed",
        "message": "",
        "response_status": None,
        "created_at": start,
        "finished_at": start,
        "duration_seconds": 0.0,
    }
    try:
        with urlopen(request, timeout=int(target.get("timeout_seconds") or 10)) as response:
            status_code = response.getcode() if hasattr(response, "getcode") else getattr(response, "status", None)
            delivery["status"] = "succeeded"
            delivery["response_status"] = status_code
            delivery["message"] = f"Delivered with HTTP {status_code}" if status_code else "Delivered"
    except Exception as exc:
        delivery["message"] = str(exc)
    finish = _now()
    delivery["finished_at"] = finish
    delivery["duration_seconds"] = max(0.0, finish - start)
    _append_jsonl_collection("alert_deliveries", delivery)
    _update_alert_delivery_target_status(target["id"], delivery)
    return delivery


def _alert_delivery_payload(alert: Dict[str, Any], target: Dict[str, Any]) -> Dict[str, Any]:
    if target.get("kind") == "slack_webhook":
        return {
            "text": f"[{str(alert.get('severity') or 'info').upper()}] {alert.get('title')}: {alert.get('message')}",
        }
    return {
        "event": "analytics_foundry.alert",
        "alert": alert,
    }


def _normalize_alert_severities(value: Any) -> List[str]:
    raw_values = value or ["warning", "error"]
    if isinstance(raw_values, str):
        raw_values = [part.strip() for part in raw_values.split(",") if part.strip()]
    severities = []
    for raw in raw_values:
        severity = str(raw).strip().lower()
        if severity not in ALERT_SEVERITY_ORDER:
            raise ValueError(f"Unsupported alert severity: {raw}")
        if severity not in severities:
            severities.append(severity)
    return severities or ["warning", "error"]


def _alert_target_accepts_severity(target: Dict[str, Any], severity: str) -> bool:
    allowed = set(_normalize_alert_severities(target.get("severities")))
    return severity.lower() in allowed


def _summarize_delivery_status(deliveries: List[Dict[str, Any]]) -> str:
    successes = sum(1 for delivery in deliveries if delivery.get("status") == "succeeded")
    if successes == len(deliveries):
        return "delivered"
    if successes == 0:
        return "failed"
    return "partial"


def _update_alert_delivery_status(alert_id: str, delivery_status: str, attempt_count: int) -> None:
    alerts = _read_json_collection("alerts")
    for alert in alerts:
        if alert.get("id") == alert_id:
            alert["delivery_status"] = delivery_status
            alert["delivery_attempt_count"] = attempt_count
            alert["updated_at"] = _now()
            break
    _write_json_collection("alerts", alerts)


def _update_alert_delivery_target_status(target_id: str, delivery: Dict[str, Any]) -> None:
    targets = list_alert_delivery_targets()
    for target in targets:
        if target.get("id") == target_id:
            target["last_status"] = delivery.get("status")
            target["last_delivered_at"] = delivery.get("finished_at")
            target["last_error"] = delivery.get("message") if delivery.get("status") != "succeeded" else None
            target["updated_at"] = _now()
            break
    _write_json_collection("alert_delivery_targets", targets)


def model_operation_templates() -> List[Dict[str, Any]]:
    return [dict(item) for item in MODEL_OPERATION_TEMPLATES]


def create_model(payload: Dict[str, Any]) -> Dict[str, Any]:
    source = str(payload.get("source_table_id") or "")
    parse_table_id(source)
    ts = _now()
    model_id = _new_id("model")
    model = {
        "id": model_id,
        "name": str(payload.get("name") or "Untitled model"),
        "source_table_id": source,
        "target_table_id": str(payload.get("target_table_id") or f"model:{model_id}"),
        "operations": payload.get("operations") or [],
        "created_at": ts,
        "updated_at": ts,
    }
    parse_table_id(model["target_table_id"])
    models = _read_json_collection("models")
    models.append(model)
    _write_json_collection("models", models)
    return model


def list_models() -> List[Dict[str, Any]]:
    return _read_json_collection("models")


def get_model(model_id: str) -> Dict[str, Any] | None:
    for model in list_models():
        if (
            model.get("id") == model_id
            or model.get("target_table_id") == model_id
            or model.get("target_table_id") == f"model:{model_id}"
        ):
            return model
    return None


def materialize_model(
    model_id: str,
    rows_resolver: RowsResolver,
    record_run_history: bool = True,
) -> Dict[str, Any]:
    """Run a saved low-code model and overwrite its durable model table."""
    model = get_model(model_id)
    if model is None:
        raise KeyError(model_id)
    rows = _evaluate_model_rows(model, rows_resolver)
    storage_path = _write_model_rows(model["id"], rows)
    schema = infer_schema(rows[:100])
    updated_model = _update_model(
        model["id"],
        {
            "last_materialized_at": _now(),
            "last_row_count": len(rows),
            "last_schema": schema,
            "storage_path": storage_path,
        },
    )
    run = None
    if record_run_history:
        run = record_run(
            "model_materialize",
            target={"model_id": model["id"], "table_id": model["target_table_id"]},
            details={"row_count": len(rows)},
        )
    return {
        "ok": True,
        "model": updated_model,
        "table_id": model["target_table_id"],
        "row_count": len(rows),
        "schema": schema,
        "storage_path": storage_path,
        "run": run,
    }


def _update_model(model_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    models = list_models()
    for idx, model in enumerate(models):
        if model.get("id") == model_id:
            updated = dict(model)
            updated.update(updates)
            updated["updated_at"] = _now()
            models[idx] = updated
            _write_json_collection("models", models)
            return updated
    raise KeyError(model_id)


def _mark_model_storage_removed(model_id: str) -> None:
    model = get_model(model_id)
    if model is None:
        return
    _update_model(
        model["id"],
        {
            "storage_path": None,
            "last_materialized_at": None,
            "last_row_count": None,
            "last_schema": [],
        },
    )


def preview_model(
    model_id: str,
    rows_resolver: RowsResolver,
    limit: int = 100,
) -> Dict[str, Any]:
    model = get_model(model_id)
    if model is None:
        raise KeyError(model_id)
    rows = _evaluate_model_rows(model, rows_resolver)
    return {
        "model": model,
        "rows": rows[:limit],
        "row_count": len(rows),
        "limit": limit,
        "schema": infer_schema(rows[:limit]),
    }


def _evaluate_model_rows(
    model: Dict[str, Any],
    rows_resolver: RowsResolver,
) -> List[Dict[str, Any]]:
    rows = [dict(row) for row in rows_resolver(model["source_table_id"])]
    return apply_model_operations(rows, model.get("operations") or [], rows_resolver)


def apply_model_operations(
    rows: List[Dict[str, Any]],
    operations: List[Dict[str, Any]],
    rows_resolver: RowsResolver,
) -> List[Dict[str, Any]]:
    current = rows
    for op in operations:
        op_type = str(op.get("type") or "")
        params = op.get("params") or {}
        if op_type == "filter":
            current = _apply_filter(current, params)
        elif op_type == "select":
            columns = [str(col) for col in params.get("columns") or []]
            current = [{col: row.get(col) for col in columns} for row in current]
        elif op_type == "rename":
            current = _apply_rename(current, params.get("mapping") or {})
        elif op_type == "cast":
            current = _apply_cast(current, str(params.get("column") or ""), str(params.get("to") or "string"))
        elif op_type == "deduplicate":
            current = _apply_deduplicate(current, [str(col) for col in params.get("columns") or []])
        elif op_type == "calculate":
            current = _apply_calculate(current, params)
        elif op_type == "group":
            current = _apply_group(current, params)
        elif op_type == "join":
            current = _apply_join(current, params, rows_resolver)
        elif op_type == "union":
            source_table = str(params.get("source_table_id") or "")
            current = current + [dict(row) for row in rows_resolver(source_table)]
        else:
            raise ValueError(f"Unsupported model operation: {op_type}")
    return current


def _apply_filter(rows: List[Dict[str, Any]], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    column = str(params.get("column") or "")
    operator = str(params.get("operator") or "equals")
    value = params.get("value")
    values = params.get("values") or []
    return [
        row
        for row in rows
        if _compare(row.get(column), operator, value, values)
    ]


def _compare(actual: Any, operator: str, value: Any, values: List[Any]) -> bool:
    if operator == "equals":
        return actual == value
    if operator == "not_equals":
        return actual != value
    if operator == "contains":
        return str(value).lower() in str(actual or "").lower()
    if operator == "in":
        return actual in values
    if operator == "not_blank":
        return not _is_blank(actual)
    actual_num = _to_float(actual)
    value_num = _to_float(value)
    if actual_num is None or value_num is None:
        return False
    if operator == "gt":
        return actual_num > value_num
    if operator == "gte":
        return actual_num >= value_num
    if operator == "lt":
        return actual_num < value_num
    if operator == "lte":
        return actual_num <= value_num
    return False


def _apply_rename(rows: List[Dict[str, Any]], mapping: Dict[str, str]) -> List[Dict[str, Any]]:
    renamed = []
    for row in rows:
        out = {}
        for key, value in row.items():
            out[str(mapping.get(key) or key)] = value
        renamed.append(out)
    return renamed


def _apply_cast(rows: List[Dict[str, Any]], column: str, target_type: str) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        new_row = dict(row)
        new_row[column] = _cast_value(new_row.get(column), target_type)
        out.append(new_row)
    return out


def _cast_value(value: Any, target_type: str) -> Any:
    if value is None:
        return None
    try:
        if target_type == "integer":
            return int(value)
        if target_type == "number":
            return float(value)
        if target_type == "boolean":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"true", "1", "yes", "y"}
        return str(value)
    except (TypeError, ValueError):
        return None


def _apply_deduplicate(rows: List[Dict[str, Any]], columns: List[str]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for row in rows:
        key = tuple(row.get(col) for col in columns) if columns else tuple(sorted(row.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _apply_calculate(rows: List[Dict[str, Any]], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    column = str(params.get("column") or "")
    mode = str(params.get("mode") or "constant")
    out = []
    for row in rows:
        new_row = dict(row)
        if mode == "copy":
            new_row[column] = row.get(str(params.get("source_column") or ""))
        elif mode == "coalesce":
            new_row[column] = next(
                (row.get(str(col)) for col in params.get("columns") or [] if not _is_blank(row.get(str(col)))),
                params.get("default"),
            )
        else:
            new_row[column] = params.get("value")
        out.append(new_row)
    return out


def _apply_group(rows: List[Dict[str, Any]], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    group_by = [str(col) for col in params.get("group_by") or []]
    aggregations = params.get("aggregations") or [{"function": "count", "as": "row_count"}]
    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    for row in rows:
        key = tuple(row.get(col) for col in group_by)
        grouped.setdefault(key, []).append(row)
    out = []
    for key, group_rows in grouped.items():
        record = {col: value for col, value in zip(group_by, key)}
        for agg in aggregations:
            func = str(agg.get("function") or "count")
            column = agg.get("column")
            output_name = str(agg.get("as") or f"{func}_{column or 'rows'}")
            values = [_to_float(row.get(str(column))) for row in group_rows] if column else []
            values = [value for value in values if value is not None]
            if func == "count":
                record[output_name] = len(group_rows)
            elif func == "sum":
                record[output_name] = sum(values)
            elif func == "avg":
                record[output_name] = sum(values) / len(values) if values else None
            elif func == "min":
                record[output_name] = min(values) if values else None
            elif func == "max":
                record[output_name] = max(values) if values else None
        out.append(record)
    return out


def _apply_join(
    rows: List[Dict[str, Any]],
    params: Dict[str, Any],
    rows_resolver: RowsResolver,
) -> List[Dict[str, Any]]:
    source_table = str(params.get("source_table_id") or "")
    left_key = str(params.get("left_key") or "")
    right_key = str(params.get("right_key") or left_key)
    how = str(params.get("how") or "inner")
    right_rows = [dict(row) for row in rows_resolver(source_table)]
    lookup: Dict[Any, List[Dict[str, Any]]] = {}
    for row in right_rows:
        lookup.setdefault(row.get(right_key), []).append(row)
    out = []
    for left in rows:
        matches = lookup.get(left.get(left_key), [])
        if not matches and how == "left":
            out.append(dict(left))
            continue
        for right in matches:
            merged = dict(left)
            for key, value in right.items():
                merged[key if key not in merged else f"right_{key}"] = value
            out.append(merged)
    return out


def _model_source_tables(model: Dict[str, Any]) -> List[str]:
    sources = [model.get("source_table_id")]
    for op in model.get("operations") or []:
        params = op.get("params") or {}
        if op.get("type") in {"join", "union"} and params.get("source_table_id"):
            sources.append(params.get("source_table_id"))
    return sorted({str(source) for source in sources if source})
