"""In-memory bronze store: raw records per source and table. Tests can inspect after ingest."""

from typing import Any, Dict, List, Tuple

_RAW: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}


def append_raw(source_id: str, table: str, records: List[Dict[str, Any]]) -> None:
    """Append raw records to a bronze table. Same (source_id, table) appends to same list."""
    key = (source_id, table)
    if key not in _RAW:
        _RAW[key] = []
    _RAW[key].extend(records)


def get_raw(source_id: str, table: str) -> List[Dict[str, Any]]:
    """Return all raw records for (source_id, table). Empty list if never written."""
    return _RAW.get((source_id, table), []).copy()


def clear() -> None:
    """Clear all bronze raw data (for tests)."""
    _RAW.clear()
