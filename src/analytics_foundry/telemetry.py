"""In-memory log ring buffer and optional Prometheus text metrics."""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections import deque
from typing import Any

_LOG_BUFFER: deque[dict[str, Any]] = deque(maxlen=500)
_BUFFER_LOCK = threading.Lock()
_COUNTERS: dict[str, int] = {}
_COUNTERS_LOCK = threading.Lock()


class RingBufferHandler(logging.Handler):
    """Append structured log records to an in-memory deque for admin inspection."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = {
                "ts": time.time(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                payload["exc_info"] = "".join(traceback.format_exception(*record.exc_info))
            with _BUFFER_LOCK:
                _LOG_BUFFER.append(payload)
        except Exception:
            self.handleError(record)


def get_recent_logs(limit: int = 100) -> list[dict[str, Any]]:
    """Return most recent log entries (newest first)."""
    with _BUFFER_LOCK:
        items = list(_LOG_BUFFER)
    items.reverse()
    return items[:limit]


def incr_counter(name: str, delta: int = 1) -> None:
    with _COUNTERS_LOCK:
        _COUNTERS[name] = _COUNTERS.get(name, 0) + delta


def prometheus_text() -> str:
    """Minimal Prometheus exposition format for process counters."""
    lines: list[str] = []
    with _COUNTERS_LOCK:
        snapshot = dict(_COUNTERS)
    for k, v in sorted(snapshot.items()):
        safe = k.replace("-", "_")
        lines.append(f"# TYPE foundry_{safe} counter")
        lines.append(f"foundry_{safe} {v}")
    return "\n".join(lines) + ("\n" if lines else "")
