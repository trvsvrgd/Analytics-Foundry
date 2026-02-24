"""Bronze store: raw records per source and table. In-memory with optional local file persistence."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

_RAW: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

# Override for tests; when None, get_data_root() reads from env.
_DATA_ROOT_OVERRIDE: str | None = None


def get_data_root() -> Path | None:
    """Return path to data directory, or None for in-memory only. Reads env each call."""
    if _DATA_ROOT_OVERRIDE is not None:
        return Path(_DATA_ROOT_OVERRIDE).resolve() if _DATA_ROOT_OVERRIDE.strip() else None
    v = os.environ.get("FOUNDRY_DATA_DIR", "data")
    if not v or not str(v).strip():
        return None
    return Path(v).resolve()


def set_data_root(path: str | Path | None) -> None:
    """Set data root (for tests). None = use env / default."""
    global _DATA_ROOT_OVERRIDE
    _DATA_ROOT_OVERRIDE = str(path) if path else None


def _bronze_path(source_id: str, table: str) -> Path | None:
    root = get_data_root()
    if root is None:
        return None
    return root / "bronze" / source_id / f"{table}.jsonl"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _load_table(source_id: str, table: str) -> None:
    """Load one table from disk into _RAW if it exists and key not already populated."""
    key = (source_id, table)
    if key in _RAW:
        return
    p = _bronze_path(source_id, table)
    if p is None or not p.is_file():
        return
    rows = []
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except (json.JSONDecodeError, OSError):
        pass
    _RAW[key] = rows


def load_from_disk() -> None:
    """Load all bronze tables from the data directory into memory. No-op if no data root."""
    root = get_data_root()
    if root is None:
        return
    bronze_dir = root / "bronze"
    if not bronze_dir.is_dir():
        return
    for source_dir in bronze_dir.iterdir():
        if not source_dir.is_dir():
            continue
        source_id = source_dir.name
        for f in source_dir.iterdir():
            if f.suffix == ".jsonl":
                table = f.stem
                _load_table(source_id, table)


def append_raw(source_id: str, table: str, records: List[Dict[str, Any]]) -> None:
    """Append raw records to a bronze table. Persists to local file if FOUNDRY_DATA_DIR is set."""
    key = (source_id, table)
    if key not in _RAW:
        _RAW[key] = []
    _RAW[key].extend(records)

    p = _bronze_path(source_id, table)
    if p is not None:
        _ensure_dir(p.parent)
        with open(p, "a", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def get_raw(source_id: str, table: str) -> List[Dict[str, Any]]:
    """Return all raw records for (source_id, table). Loads from disk if not in memory and data root set."""
    _load_table(source_id, table)
    return _RAW.get((source_id, table), []).copy()


def list_tables() -> List[Tuple[str, str, int]]:
    """Return list of (source_id, table, row_count). Includes tables on disk if data root set."""
    root = get_data_root()
    if root is not None:
        bronze_dir = root / "bronze"
        if bronze_dir.is_dir():
            for source_dir in bronze_dir.iterdir():
                if source_dir.is_dir():
                    for f in source_dir.iterdir():
                        if f.suffix == ".jsonl":
                            _load_table(source_dir.name, f.stem)
    return [
        (source_id, table, len(rows))
        for (source_id, table), rows in _RAW.items()
    ]


def clear() -> None:
    """Clear all bronze data from memory and remove persisted files (for tests)."""
    root = get_data_root()
    for (source_id, table) in list(_RAW.keys()):
        p = _bronze_path(source_id, table)
        if p is not None and p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    _RAW.clear()
