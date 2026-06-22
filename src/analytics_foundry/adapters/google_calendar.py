"""Google Calendar adapter for raw schedule ingest."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

from analytics_foundry.adapters.google_auth import build_google_service
from analytics_foundry.bronze import store as bronze_store

CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


class GoogleCalendarAdapter:
    """Pull upcoming calendar events into bronze as raw JSONL records."""

    SOURCE_ID = "google_calendar"
    TABLE = "events"

    def __init__(self, service_factory: Callable[[], Any] | None = None):
        self._service_factory = service_factory or (
            lambda: build_google_service("calendar", "v3", [CALENDAR_READONLY_SCOPE])
        )

    @property
    def source_id(self) -> str:
        return self.SOURCE_ID

    def ingest_to_bronze(self, **kwargs: Any) -> None:
        service = self._service_factory()
        calendar_id = str(kwargs.get("calendar_id") or "primary")
        max_results = int(kwargs.get("max_results") or 50)
        time_min = str(kwargs.get("time_min") or datetime.now(timezone.utc).isoformat())
        events = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
            .get("items", [])
        )
        records = [_calendar_record(event, calendar_id) for event in events]
        if records:
            bronze_store.append_raw(self.SOURCE_ID, self.TABLE, records)


def _calendar_record(event: Dict[str, Any], calendar_id: str) -> Dict[str, Any]:
    event_id = str(event.get("id") or "")
    return {
        "record_id": f"google_calendar:{calendar_id}:{event_id}",
        "source": "google_calendar",
        "calendar_id": calendar_id,
        "event_id": event_id,
        "summary": event.get("summary", ""),
        "description": event.get("description", ""),
        "location": event.get("location", ""),
        "start": event.get("start") or {},
        "end": event.get("end") or {},
        "attendees": event.get("attendees") or [],
        "updated": event.get("updated"),
        "html_link": event.get("htmlLink"),
        "text": _event_text(event),
        "raw": event,
    }


def _event_text(event: Dict[str, Any]) -> str:
    start = (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date") or ""
    end = (event.get("end") or {}).get("dateTime") or (event.get("end") or {}).get("date") or ""
    parts = [
        str(event.get("summary") or ""),
        str(event.get("description") or ""),
        str(event.get("location") or ""),
        str(start),
        str(end),
    ]
    return "\n".join(part for part in parts if part.strip())
