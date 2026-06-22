"""Structured logging setup (optional JSON) and ring-buffer handler for admin."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from analytics_foundry.telemetry import RingBufferHandler


class JsonFormatter(logging.Formatter):
    """One JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, self.datefmt),
        }
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """Configure root logging once. Idempotent for repeated lifespan in tests."""
    level_name = os.environ.get("FOUNDRY_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if getattr(root, "_foundry_configured", False):
        root.setLevel(level)
        return
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    if os.environ.get("FOUNDRY_LOG_JSON", "").strip().lower() in ("1", "true", "yes"):
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root.handlers.clear()
    root.addHandler(handler)
    ring = RingBufferHandler()
    ring.setLevel(logging.INFO)
    ring.setFormatter(logging.Formatter())
    root.addHandler(ring)
    root._foundry_configured = True  # type: ignore[attr-defined]
