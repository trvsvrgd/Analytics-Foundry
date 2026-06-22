import httpx
import logging
from typing import Any, Dict, List, Optional
from analytics_foundry.bronze import store as bronze_store

logger = logging.getLogger(__name__)


class AiDailyBriefAdapter:
    """Adapter to ingest daily briefs from aidailybrief.ai."""

    SOURCE_ID = "ai_daily_brief"
    TABLE = "transcripts"

    def __init__(self, client: Optional[httpx.Client] = None):
        self.client = client or httpx.Client(timeout=30.0)

    @property
    def source_id(self) -> str:
        return self.SOURCE_ID

    def ingest_to_bronze(self, **kwargs: Any) -> None:
        """Fetch index of briefs from agent.json and ingest new transcripts."""
        index_url = kwargs.get("index_url") or "https://aidailybrief.ai/agent.json"
        try:
            resp = self.client.get(index_url)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.exception("Failed to fetch agent.json index")
            raise RuntimeError(f"Failed to fetch AIDB index: {exc}")

        editions = data.get("editions", [])
        if not editions:
            logger.warning("No editions found in agent.json")
            return

        # Check existing records to avoid duplicates
        existing = bronze_store.get_raw(self.SOURCE_ID, self.TABLE)
        existing_dates = {rec["date"] for rec in existing if "date" in rec}

        new_records = []
        for ed in editions:
            date_str = ed.get("date")
            if not date_str or date_str in existing_dates:
                continue

            transcript_url = ed.get("transcript")
            if not transcript_url:
                continue

            # Fetch transcript markdown
            try:
                t_resp = self.client.get(transcript_url)
                t_resp.raise_for_status()
                transcript_text = t_resp.text
            except Exception as exc:
                logger.error(f"Failed to fetch transcript for date {date_str} from {transcript_url}: {exc}")
                continue

            record = {
                "record_id": f"aidb:{date_str}",
                "date": date_str,
                "title": ed.get("title", ""),
                "teaser": ed.get("teaser", ""),
                "tags": ed.get("tags", []),
                "transcript_url": transcript_url,
                "transcript_text": transcript_text,
            }
            new_records.append(record)

        if new_records:
            # Append in reverse order (oldest to newest) to maintain chronological order
            new_records.reverse()
            bronze_store.append_raw(self.SOURCE_ID, self.TABLE, new_records)
            logger.info(f"Ingested {len(new_records)} new transcripts into bronze")
