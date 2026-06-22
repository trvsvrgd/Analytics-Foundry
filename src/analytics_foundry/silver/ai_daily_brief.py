"""Silver: cleaned, conformed AI Daily Brief transcripts."""

from typing import Any, Dict, List
from analytics_foundry.bronze import store as bronze_store

SOURCE_ID = "ai_daily_brief"
TABLE = "transcripts"

SILVER_TRANSCRIPT_KEYS = (
    "record_id",
    "date",
    "title",
    "teaser",
    "tags",
    "transcript_text",
    "word_count",
    "paragraph_count",
)


def get_cleaned_transcripts() -> List[Dict[str, Any]]:
    """Return silver AI Daily Brief transcripts, deduplicated by date (latest wins)."""
    raw = bronze_store.get_raw(SOURCE_ID, TABLE)
    by_date: Dict[str, Dict[str, Any]] = {}
    for rec in raw:
        date_str = rec.get("date")
        if not date_str:
            continue

        text = str(rec.get("transcript_text") or "")
        word_count = len(text.split())
        paragraph_count = len([p for p in text.split("\n") if p.strip()])

        conformed = {
            "record_id": str(rec.get("record_id") or f"aidb:{date_str}"),
            "date": str(date_str),
            "title": str(rec.get("title") or ""),
            "teaser": str(rec.get("teaser") or ""),
            "tags": list(rec.get("tags") or []),
            "transcript_text": text,
            "word_count": word_count,
            "paragraph_count": paragraph_count,
        }
        by_date[date_str] = conformed

    return sorted(by_date.values(), key=lambda x: x["date"])
