"""Gmail adapter for raw personal email ingest."""

from __future__ import annotations

import base64
from typing import Any, Callable, Dict, List

from analytics_foundry.adapters.google_auth import build_google_service
from analytics_foundry.bronze import store as bronze_store

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GmailAdapter:
    """Pull recent Gmail messages into bronze as raw JSONL records."""

    SOURCE_ID = "gmail"
    TABLE = "emails"

    def __init__(self, service_factory: Callable[[], Any] | None = None):
        self._service_factory = service_factory or (
            lambda: build_google_service("gmail", "v1", [GMAIL_READONLY_SCOPE])
        )

    @property
    def source_id(self) -> str:
        return self.SOURCE_ID

    def ingest_to_bronze(self, **kwargs: Any) -> None:
        service = self._service_factory()
        max_results = int(kwargs.get("max_results") or 25)
        query = str(kwargs.get("query") or "newer_than:7d")
        messages = (
            service.users()
            .messages()
            .list(userId="me", maxResults=max_results, q=query)
            .execute()
            .get("messages", [])
        )
        records = []
        for message in messages:
            message_id = str(message.get("id") or "")
            if not message_id:
                continue
            raw = service.users().messages().get(userId="me", id=message_id, format="full").execute()
            records.append(_gmail_record(raw))
        if records:
            bronze_store.append_raw(self.SOURCE_ID, self.TABLE, records)


def _gmail_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    payload = raw.get("payload") or {}
    headers = _headers(payload.get("headers") or [])
    message_id = str(raw.get("id") or headers.get("Message-Id") or "")
    return {
        "record_id": f"gmail:{message_id}",
        "source": "gmail",
        "gmail_message_id": message_id,
        "thread_id": raw.get("threadId"),
        "subject": headers.get("Subject", ""),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "date": headers.get("Date", ""),
        "snippet": raw.get("snippet", ""),
        "text": _message_text(payload) or raw.get("snippet", ""),
        "raw": raw,
    }


def _headers(items: List[Dict[str, Any]]) -> Dict[str, str]:
    return {str(item.get("name") or ""): str(item.get("value") or "") for item in items}


def _message_text(payload: Dict[str, Any]) -> str:
    parts = payload.get("parts") or []
    body = payload.get("body") or {}
    if body.get("data"):
        return _decode_body(str(body["data"]))
    for part in parts:
        mime_type = str(part.get("mimeType") or "")
        if mime_type == "text/plain":
            data = ((part.get("body") or {}).get("data"))
            if data:
                return _decode_body(str(data))
    return ""


def _decode_body(value: str) -> str:
    padded = value + ("=" * (-len(value) % 4))
    try:
        return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")
    except (ValueError, OSError):
        return ""
