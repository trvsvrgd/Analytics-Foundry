"""Android selected-thread adapter for household messages."""

from __future__ import annotations

from typing import Any, Dict, List

from analytics_foundry.bronze import store as bronze_store


class AndroidMessagesAdapter:
    """Write selected Android SMS/MMS threads into bronze."""

    SOURCE_ID = "android_messages"
    TABLE = "threads"

    @property
    def source_id(self) -> str:
        return self.SOURCE_ID

    def ingest_to_bronze(self, **kwargs: Any) -> None:
        device_id = str(kwargs.get("device_id") or "android")
        threads = kwargs.get("threads") or []
        records = android_thread_records(device_id, threads)
        if records:
            bronze_store.append_raw(self.SOURCE_ID, self.TABLE, records)


def android_thread_records(device_id: str, threads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    records = []
    for thread in threads:
        thread_id = str(thread.get("thread_id") or thread.get("id") or "")
        if not thread_id:
            continue
        messages = thread.get("messages") or []
        records.append(
            {
                "record_id": f"android_messages:{device_id}:{thread_id}",
                "source": "android_messages",
                "device_id": device_id,
                "thread_id": thread_id,
                "display_name": str(thread.get("display_name") or thread_id),
                "participants": [
                    str(participant)
                    for participant in (thread.get("participants") or [])
                    if str(participant).strip()
                ],
                "message_count": len(messages),
                "messages": messages,
                "text": _thread_text(thread),
                "raw": thread,
            }
        )
    return records


def _thread_text(thread: Dict[str, Any]) -> str:
    lines = [str(thread.get("display_name") or "Message thread")]
    for message in thread.get("messages") or []:
        sender = str(message.get("sender") or "")
        sent_at = str(message.get("sent_at") or message.get("date") or "")
        body = str(message.get("body") or message.get("text") or "")
        lines.append(" | ".join(part for part in [sent_at, sender, body] if part))
    return "\n".join(lines)
