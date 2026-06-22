"""Ambient context ingestion, evaluation, and review tests."""

import base64
from types import SimpleNamespace

from fastapi.testclient import TestClient

from analytics_foundry import workbench
from analytics_foundry.adapters import register_adapter
from analytics_foundry.adapters.android_messages import AndroidMessagesAdapter
from analytics_foundry.adapters.gmail import GmailAdapter
from analytics_foundry.adapters.google_calendar import GoogleCalendarAdapter
from analytics_foundry.api import app
from analytics_foundry.bronze import store as bronze_store


class ExecuteCall:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class FakeGmailMessages:
    def list(self, **kwargs):
        return ExecuteCall({"messages": [{"id": "m1"}]})

    def get(self, **kwargs):
        body = base64.urlsafe_b64encode(b"Dentist at 3 PM today").decode("utf-8").rstrip("=")
        return ExecuteCall(
            {
                "id": "m1",
                "threadId": "t1",
                "snippet": "Dentist at 3 PM",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Appointment"},
                        {"name": "From", "value": "clinic@example.test"},
                        {"name": "To", "value": "me@example.test"},
                        {"name": "Date", "value": "Sat, 13 Jun 2026 12:00:00 -0500"},
                    ],
                    "body": {"data": body},
                },
            }
        )


class FakeGmailUsers:
    def messages(self):
        return FakeGmailMessages()


class FakeGmailService:
    def users(self):
        return FakeGmailUsers()


class FakeCalendarEvents:
    def list(self, **kwargs):
        return ExecuteCall(
            {
                "items": [
                    {
                        "id": "e1",
                        "summary": "Soccer practice",
                        "description": "Bring cleats",
                        "location": "Field 2",
                        "start": {"dateTime": "2026-06-13T18:00:00-05:00"},
                        "end": {"dateTime": "2026-06-13T19:00:00-05:00"},
                    }
                ]
            }
        )


class FakeCalendarService:
    def events(self):
        return FakeCalendarEvents()


def test_gmail_adapter_writes_recent_email_to_bronze():
    bronze_store.clear()
    adapter = GmailAdapter(service_factory=lambda: FakeGmailService())

    adapter.ingest_to_bronze(max_results=1, query="newer_than:1d")

    rows = bronze_store.get_raw("gmail", "emails")
    assert len(rows) == 1
    assert rows[0]["record_id"] == "gmail:m1"
    assert rows[0]["subject"] == "Appointment"
    assert rows[0]["text"] == "Dentist at 3 PM today"


def test_google_calendar_adapter_writes_schedule_event_to_bronze():
    bronze_store.clear()
    adapter = GoogleCalendarAdapter(service_factory=lambda: FakeCalendarService())

    adapter.ingest_to_bronze(calendar_id="primary", max_results=1)

    rows = bronze_store.get_raw("google_calendar", "events")
    assert len(rows) == 1
    assert rows[0]["record_id"] == "google_calendar:primary:e1"
    assert rows[0]["summary"] == "Soccer practice"
    assert "Bring cleats" in rows[0]["text"]


def test_android_message_ingest_endpoint_writes_selected_threads_to_bronze():
    client = TestClient(app)
    bronze_store.clear()
    workbench.clear()
    register_adapter(AndroidMessagesAdapter)

    resp = client.post(
        "/admin/ambient/messages/ingest",
        json={
            "device_id": "pixel",
            "threads": [
                {
                    "thread_id": "42",
                    "display_name": "Household",
                    "participants": ["Mom", "+15555550123"],
                    "messages": [
                        {
                            "message_id": "1001",
                            "sender": "Mom",
                            "sent_at": "2026-06-13T18:00:00Z",
                            "body": "Practice moved to 6 tonight.",
                        }
                    ],
                }
            ],
        },
    )

    assert resp.status_code == 200
    assert resp.json()["table_id"] == "bronze:android_messages.threads"
    rows = bronze_store.get_raw("android_messages", "threads")
    assert rows[0]["thread_id"] == "42"
    assert "Practice moved" in rows[0]["text"]


def test_ambient_evaluate_routes_high_medium_low(monkeypatch):
    client = TestClient(app)
    bronze_store.clear()
    workbench.clear()
    bronze_store.append_raw("android_messages", "threads", [{"record_id": "sms_1", "text": "Dentist at 3"}])

    def fake_evaluate(rows, model):
        return SimpleNamespace(
            model=model,
            candidates=[
                {
                    "entity_type": "event",
                    "title": "Dentist appointment",
                    "groundedness": "High",
                    "evidence": ["Dentist at 3"],
                    "source_record_ids": ["sms_1"],
                },
                {
                    "entity_type": "task",
                    "title": "Buy poster board",
                    "groundedness": "Medium",
                    "evidence": ["Maybe poster board"],
                    "source_record_ids": ["sms_1"],
                    "confidence_reason": "Useful but missing date.",
                },
                {
                    "entity_type": "meal",
                    "title": "Tacos",
                    "groundedness": "Low",
                    "evidence": ["Taco?"],
                    "source_record_ids": ["sms_1"],
                },
            ],
        )

    monkeypatch.setattr("analytics_foundry.admin_routes._ambient_evaluate_records", fake_evaluate)

    resp = client.post(
        "/admin/ambient/evaluate",
        json={"table_id": "bronze:android_messages.threads", "model": "llama3.1:8b"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["high_count"] == 1
    assert data["medium_count"] == 1
    assert data["low_count"] == 1
    assert len(workbench.get_silver_ambient_candidates()) == 2
    assert len(workbench.get_gold_ambient_actions()) == 1
    alerts = client.get("/admin/alerts", params={"status": "open"}).json()
    assert alerts[0]["table_id"] == "silver:ambient_candidates"


def test_ambient_review_approve_edit_and_ignore(monkeypatch):
    client = TestClient(app)
    bronze_store.clear()
    workbench.clear()
    bronze_store.append_raw("android_messages", "threads", [{"record_id": "sms_1", "text": "Maybe buy milk"}])

    def fake_evaluate(rows, model):
        return SimpleNamespace(
            model=model,
            candidates=[
                {
                    "entity_type": "task",
                    "title": "Buy milk",
                    "groundedness": "Medium",
                    "evidence": ["Maybe buy milk"],
                    "source_record_ids": ["sms_1"],
                },
                {
                    "entity_type": "household_note",
                    "title": "Vague errand",
                    "groundedness": "Medium",
                    "evidence": ["Need to do that thing"],
                    "source_record_ids": ["sms_1"],
                },
            ],
        )

    monkeypatch.setattr("analytics_foundry.admin_routes._ambient_evaluate_records", fake_evaluate)
    client.post(
        "/admin/ambient/evaluate",
        json={"table_id": "bronze:android_messages.threads", "model": "llama3.1:8b"},
    )
    open_candidates = client.get("/admin/ambient/review").json()
    approve_id = open_candidates[0]["id"]
    ignore_id = open_candidates[1]["id"]

    approve = client.post(
        f"/admin/ambient/review/{approve_id}/approve",
        json={"updates": {"title": "Buy milk and eggs"}, "reviewer_note": "Added eggs from context."},
    )
    ignore = client.post(
        f"/admin/ambient/review/{ignore_id}/ignore",
        json={"reviewer_note": "Too vague."},
    )

    assert approve.status_code == 200
    assert approve.json()["action"]["title"] == "Buy milk and eggs"
    assert ignore.status_code == 200
    assert ignore.json()["candidate"]["review_status"] == "ignored"
    assert len(workbench.get_gold_ambient_actions()) == 1
