"""Tests for the low-code workbench control-plane surfaces."""

import json
import os
from datetime import datetime, timezone
from urllib.error import URLError
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import analytics_foundry.admin_routes as admin_routes
from analytics_foundry import workbench
from analytics_foundry.api import app
from analytics_foundry.bronze import store as bronze_store


def ts(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp()


class MockWebhookResponse:
    def __init__(self, status_code=202):
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return self.status_code


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_state():
    bronze_store.clear()
    workbench.clear()
    yield
    workbench.clear()
    bronze_store.clear()


def test_table_profiles_include_schema_storage_and_lineage(client):
    bronze_store.append_raw(
        "nfl_sleeper",
        "players",
        [
            {
                "player_id": "p1",
                "display_name": "Alice",
                "position": "WR",
                "updated_at": "2026-06-06T00:00:00Z",
            }
        ],
    )

    resp = client.get("/admin/tables")
    assert resp.status_code == 200
    bronze = resp.json()["bronze"]
    players = next(t for t in bronze if t["table_id"] == "bronze:nfl_sleeper.players")

    assert players["row_count"] == 1
    assert players["storage_path"].replace("\\", "/").endswith("bronze/nfl_sleeper/players.jsonl")
    assert players["freshness"]["source"] == "storage_mtime"
    assert "silver:players" in players["downstream"]
    assert {col["name"] for col in players["schema"]} >= {"player_id", "display_name"}

    profile = client.get("/admin/table-profiles/bronze:nfl_sleeper.players")
    assert profile.status_code == 200
    assert profile.json()["table_id"] == "bronze:nfl_sleeper.players"


def test_quality_rule_run_records_result_and_alert(client):
    bronze_store.append_raw(
        "demo",
        "users",
        [{"id": "1", "name": "Ada"}, {"id": "2", "name": ""}],
    )

    rule_resp = client.post(
        "/admin/quality/rules",
        json={
            "table_id": "bronze:demo.users",
            "type": "required",
            "name": "Name is present",
            "column": "name",
        },
    )
    assert rule_resp.status_code == 200
    rule = rule_resp.json()

    run_resp = client.post("/admin/quality/run", json={"table_id": "bronze:demo.users"})
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert data["run"]["status"] == "failed"
    assert data["results"][0]["rule_id"] == rule["id"]
    assert data["results"][0]["status"] == "failed"
    assert data["results"][0]["failed_count"] == 1

    alerts = client.get("/admin/alerts", params={"status": "open"}).json()
    assert len(alerts) == 1
    assert alerts[0]["table_id"] == "bronze:demo.users"

    ack = client.post(f"/admin/alerts/{alerts[0]['id']}/ack")
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"


def test_quality_authoring_context_exposes_column_kinds_and_compatible_rules(client):
    bronze_store.append_raw(
        "demo",
        "metrics",
        [
            {"id": "1", "score": "8.5", "status": "open", "updated_at": "2026-06-08T12:00:00Z"},
            {"id": "2", "score": "9.0", "status": "closed", "updated_at": "2026-06-08T12:05:00Z"},
        ],
    )

    resp = client.get("/admin/quality/authoring-context/bronze:demo.metrics")
    assert resp.status_code == 200
    context = resp.json()
    columns = {column["name"]: column for column in context["columns"]}
    assert columns["score"]["quality_kind"] == "numeric"
    assert columns["updated_at"]["quality_kind"] == "timestamp"
    assert columns["status"]["quality_kind"] == "categorical"
    assert columns["status"]["distinct_values"] == ["open", "closed"]

    templates = {template["type"]: template for template in context["templates"]}
    assert "score" in templates["numeric_range"]["compatible_columns"]
    assert "status" not in templates["numeric_range"]["compatible_columns"]
    assert "updated_at" in templates["freshness"]["compatible_columns"]
    assert templates["row_count_drift"]["requires_column"] is False
    assert context["reference_tables"][0]["table_id"] == "bronze:demo.metrics"
    assert set(context["reference_tables"][0]["columns"]) >= {"id", "score", "status", "updated_at"}


def test_quality_result_includes_failed_row_samples(client):
    bronze_store.append_raw(
        "demo",
        "users",
        [{"id": "1", "name": "Ada"}, {"id": "2", "name": ""}],
    )
    rule = client.post(
        "/admin/quality/rules",
        json={
            "table_id": "bronze:demo.users",
            "type": "required",
            "name": "Name is present",
            "column": "name",
        },
    ).json()

    data = client.post("/admin/quality/run", json={"table_id": "bronze:demo.users"}).json()
    result = data["results"][0]
    assert result["rule_id"] == rule["id"]
    assert result["sample_failures"][0]["row_index"] == 1
    assert result["sample_failures"][0]["row"] == {"id": "2", "name": ""}
    assert result["sample_failed_rows"] == [{"id": "2", "name": ""}]


def test_alert_delivery_target_sends_quality_alert_to_webhook(client):
    target_resp = client.post(
        "/admin/alerts/delivery-targets",
        json={
            "name": "Ops webhook",
            "kind": "webhook",
            "url": "https://hooks.example.test/foundry",
            "severities": ["error"],
        },
    )
    assert target_resp.status_code == 200
    target = target_resp.json()

    bronze_store.append_raw("demo", "users", [{"id": "1", "name": ""}])
    client.post(
        "/admin/quality/rules",
        json={
            "table_id": "bronze:demo.users",
            "type": "required",
            "name": "Name is present",
            "column": "name",
        },
    )

    with patch("analytics_foundry.workbench.urlopen", return_value=MockWebhookResponse(202)) as mocked:
        run_resp = client.post("/admin/quality/run", json={"table_id": "bronze:demo.users"})

    assert run_resp.status_code == 200
    assert mocked.call_count == 1
    request = mocked.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "https://hooks.example.test/foundry"
    assert payload["event"] == "analytics_foundry.alert"
    assert payload["alert"]["title"] == "Quality check failed: Name is present"
    assert payload["alert"]["table_id"] == "bronze:demo.users"

    alerts = client.get("/admin/alerts", params={"status": "open"}).json()
    assert alerts[0]["delivery_status"] == "delivered"
    assert alerts[0]["delivery_attempt_count"] == 1

    deliveries = client.get("/admin/alerts/deliveries").json()
    assert len(deliveries) == 1
    assert deliveries[0]["alert_id"] == alerts[0]["id"]
    assert deliveries[0]["target_id"] == target["id"]
    assert deliveries[0]["status"] == "succeeded"
    assert deliveries[0]["response_status"] == 202

    targets = client.get("/admin/alerts/delivery-targets").json()
    assert targets[0]["last_status"] == "succeeded"
    assert targets[0]["last_error"] is None


def test_alert_delivery_failure_is_logged_without_blocking_failed_job(client):
    client.post(
        "/admin/alerts/delivery-targets",
        json={
            "name": "Down webhook",
            "kind": "webhook",
            "url": "https://hooks.example.test/down",
            "severities": ["error"],
        },
    )
    client.post(
        "/admin/jobs",
        json={
            "name": "Missing source",
            "kind": "source_ingest",
            "target": {"source_id": "missing"},
            "schedule": {"type": "hourly"},
            "next_run_at": 100.0,
        },
    )

    with patch("analytics_foundry.workbench.urlopen", side_effect=URLError("webhook down")):
        run_resp = client.post("/admin/scheduler/run-due", params={"now": 100})

    assert run_resp.status_code == 200
    assert run_resp.json()["executed"][0]["run"]["status"] == "failed"

    alerts = client.get("/admin/alerts", params={"status": "open"}).json()
    assert alerts[0]["title"] == "Job failed: Missing source"
    assert alerts[0]["delivery_status"] == "failed"

    deliveries = client.get("/admin/alerts/deliveries").json()
    assert deliveries[0]["status"] == "failed"
    assert "webhook down" in deliveries[0]["message"]

    targets = client.get("/admin/alerts/delivery-targets").json()
    assert targets[0]["last_status"] == "failed"
    assert "webhook down" in targets[0]["last_error"]


def test_slack_style_alert_delivery_target_test_sends_text_payload(client):
    target = client.post(
        "/admin/alerts/delivery-targets",
        json={
            "name": "Slack hook",
            "kind": "slack_webhook",
            "url": "https://hooks.example.test/slack",
            "enabled": False,
        },
    ).json()

    with patch("analytics_foundry.workbench.urlopen", return_value=MockWebhookResponse(200)) as mocked:
        test_resp = client.post(f"/admin/alerts/delivery-targets/{target['id']}/test")

    assert test_resp.status_code == 200
    assert test_resp.json()["status"] == "succeeded"
    request = mocked.call_args.args[0]
    payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "https://hooks.example.test/slack"
    assert "Analytics Foundry test alert" in payload["text"]


def test_quality_check_job_persists_definition_and_run(client):
    bronze_store.append_raw("demo", "users", [{"id": "1"}])
    client.post(
        "/admin/quality/rules",
        json={
            "table_id": "bronze:demo.users",
            "type": "required",
            "column": "id",
        },
    )

    create_resp = client.post(
        "/admin/jobs",
        json={
            "name": "Check users",
            "kind": "quality_check",
            "target": {"table_id": "bronze:demo.users"},
            "schedule": {"type": "daily"},
        },
    )
    assert create_resp.status_code == 200
    job = create_resp.json()
    assert job["next_run_at"] is not None

    run_resp = client.post(f"/admin/jobs/{job['id']}/run")
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert data["run"]["status"] == "succeeded"
    assert data["job"]["last_status"] == "succeeded"

    runs = client.get("/admin/runs").json()
    assert runs[0]["job_id"] == job["id"]
    assert runs[0]["kind"] == "quality_check"


def test_scheduler_run_due_runs_due_enabled_job(client):
    bronze_store.append_raw("demo", "users", [{"id": "1"}])
    client.post(
        "/admin/quality/rules",
        json={
            "table_id": "bronze:demo.users",
            "type": "required",
            "column": "id",
        },
    )
    job = client.post(
        "/admin/jobs",
        json={
            "name": "Scheduled users check",
            "kind": "quality_check",
            "target": {"table_id": "bronze:demo.users"},
            "schedule": {"type": "hourly"},
            "next_run_at": 100.0,
        },
    ).json()

    status_resp = client.get("/admin/scheduler/status", params={"now": 100})
    assert status_resp.status_code == 200
    assert status_resp.json()["due_job_ids"] == [job["id"]]

    run_resp = client.post("/admin/scheduler/run-due", params={"now": 100})
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert data["executed_count"] == 1
    assert data["executed"][0]["run"]["status"] == "succeeded"
    assert data["executed"][0]["details"]["trigger"] == "scheduler"
    assert data["executed"][0]["job"]["last_status"] == "succeeded"
    assert data["executed"][0]["job"]["next_run_at"] == 3700.0


def test_daily_time_schedule_sets_next_run(monkeypatch, client):
    monkeypatch.setattr(workbench, "_now", lambda: ts(2026, 1, 1, 8, 30))

    resp = client.post(
        "/admin/jobs",
        json={
            "name": "Morning check",
            "kind": "quality_check",
            "target": {"table_id": "bronze:demo.users"},
            "schedule": {"type": "daily", "time": "09:15"},
        },
    )

    assert resp.status_code == 200
    job = resp.json()
    assert job["schedule"] == {"type": "daily", "time": "09:15"}
    assert job["next_run_at"] == ts(2026, 1, 1, 9, 15)


def test_weekly_schedule_rolls_to_next_week(monkeypatch, client):
    monkeypatch.setattr(workbench, "_now", lambda: ts(2026, 1, 5, 10, 0))

    resp = client.post(
        "/admin/jobs",
        json={
            "name": "Weekly check",
            "kind": "quality_check",
            "target": {"table_id": "bronze:demo.users"},
            "schedule": {"type": "weekly", "day_of_week": "monday", "time": "09:00"},
        },
    )

    assert resp.status_code == 200
    job = resp.json()
    assert job["schedule"] == {"type": "weekly", "day_of_week": "monday", "time": "09:00"}
    assert job["next_run_at"] == ts(2026, 1, 12, 9, 0)


def test_default_weekly_ingest_jobs_are_seeded_idempotently():
    result = workbench.ensure_default_ingest_jobs(now=ts(2026, 1, 5, 8, 0))

    assert result["created_count"] == 4
    jobs = workbench.list_jobs()
    by_key = {job["default_key"]: job for job in jobs}
    assert set(by_key) == {
        "weekly_nfl_sleeper_broad",
        "weekly_nfl_feed",
        "weekly_default_league",
        "weekly_ai_daily_brief",
    }
    assert by_key["weekly_nfl_sleeper_broad"]["target"]["source_id"] == "nfl_sleeper"
    assert by_key["weekly_nfl_feed"]["target"]["source_id"] == "nfl_weekly_feed"
    assert by_key["weekly_ai_daily_brief"]["target"]["source_id"] == "ai_daily_brief"
    assert by_key["weekly_default_league"]["target"]["league_id"]
    assert all(job["schedule"]["type"] == "weekly" for job in jobs)

    second = workbench.ensure_default_ingest_jobs(now=ts(2026, 1, 5, 8, 5))

    assert second["created_count"] == 0
    assert len(workbench.list_jobs()) == 4


def test_startup_catchup_runs_overdue_jobs_and_reports_status(client):
    class DemoAdapter:
        def ingest_to_bronze(self, **kwargs):
            bronze_store.append_raw("demo_adapter", "items", [{"id": "1"}])

    job = client.post(
        "/admin/jobs",
        json={
            "name": "Overdue adapter sync",
            "kind": "adapter_ingest",
            "target": {"source_id": "demo_adapter", "params": {}},
            "schedule": {"type": "hourly"},
            "next_run_at": 100.0,
        },
    ).json()

    with patch("analytics_foundry.admin_routes.get_adapter", return_value=DemoAdapter()):
        status = admin_routes.run_startup_catchup_once(now=100)

    assert status["status"] == "completed"
    assert status["executed_count"] == 1
    assert status["executed_jobs"][0]["id"] == job["id"]
    assert bronze_store.get_raw("demo_adapter", "items") == [{"id": "1"}]
    runs = workbench.list_runs()
    assert runs[0]["details"]["trigger"] == "startup_catchup"
    assert runs[0]["status"] == "succeeded"
    alerts = workbench.list_alerts("open")
    assert alerts[0]["severity"] == "info"
    assert "Startup catch-up ran" in alerts[0]["title"]

    api_status = client.get("/admin/scheduler/startup-catchup")
    assert api_status.status_code == 200
    assert api_status.json()["executed_count"] == 1


def test_cron_schedule_sets_next_run(monkeypatch, client):
    monkeypatch.setattr(workbench, "_now", lambda: ts(2026, 1, 1, 0, 1))

    resp = client.post(
        "/admin/jobs",
        json={
            "name": "Quarter hour check",
            "kind": "quality_check",
            "target": {"table_id": "bronze:demo.users"},
            "schedule": {"type": "cron", "expression": "*/15 * * * *"},
        },
    )

    assert resp.status_code == 200
    job = resp.json()
    assert job["schedule"] == {"type": "cron", "expression": "*/15 * * * *"}
    assert job["next_run_at"] == ts(2026, 1, 1, 0, 15)


def test_invalid_cron_schedule_returns_400(client):
    resp = client.post(
        "/admin/jobs",
        json={
            "name": "Broken schedule",
            "kind": "quality_check",
            "target": {"table_id": "bronze:demo.users"},
            "schedule": {"type": "cron", "expression": "* * *"},
        },
    )

    assert resp.status_code == 400
    assert "Cron schedule must use five fields" in resp.json()["detail"]


def test_scheduler_ignores_disabled_due_job(client):
    job = client.post(
        "/admin/jobs",
        json={
            "name": "Disabled check",
            "kind": "quality_check",
            "target": {"table_id": "bronze:demo.users"},
            "schedule": {"type": "hourly"},
            "enabled": False,
            "next_run_at": 100.0,
        },
    ).json()

    status = client.get("/admin/scheduler/status", params={"now": 100}).json()
    assert job["id"] not in status["due_job_ids"]
    assert status["due_count"] == 0

    run_resp = client.post("/admin/scheduler/run-due", params={"now": 100})
    assert run_resp.status_code == 200
    assert run_resp.json()["executed_count"] == 0


def test_scheduler_failed_job_uses_retry_delay_and_alert(client):
    job = client.post(
        "/admin/jobs",
        json={
            "name": "Missing source",
            "kind": "source_ingest",
            "target": {"source_id": "missing"},
            "schedule": {"type": "hourly"},
            "retry_count": 1,
            "retry_delay_seconds": 5,
            "next_run_at": 100.0,
        },
    ).json()

    first = client.post("/admin/scheduler/run-due", params={"now": 100})
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["executed_count"] == 1
    failed_job = first_data["executed"][0]["job"]
    assert first_data["executed"][0]["run"]["status"] == "failed"
    assert failed_job["failed_attempts"] == 1
    assert failed_job["next_run_at"] == 105.0

    alerts = client.get("/admin/alerts", params={"status": "open"}).json()
    assert len(alerts) == 1
    assert alerts[0]["title"] == "Job failed: Missing source"

    early = client.post("/admin/scheduler/run-due", params={"now": 104})
    assert early.status_code == 200
    assert early.json()["executed_count"] == 0

    second = client.post("/admin/scheduler/run-due", params={"now": 105})
    assert second.status_code == 200
    second_job = second.json()["executed"][0]["job"]
    assert second_job["failed_attempts"] == 2
    assert second_job["next_run_at"] == 3705.0


def test_low_code_model_preview_and_lineage(client):
    bronze_store.append_raw(
        "demo",
        "players",
        [
            {"id": "1", "position": "WR", "score": "8"},
            {"id": "2", "position": "QB", "score": "7"},
            {"id": "3", "position": "WR", "score": "9"},
        ],
    )

    create_resp = client.post(
        "/admin/models",
        json={
            "name": "WR scores",
            "source_table_id": "bronze:demo.players",
            "operations": [
                {
                    "type": "filter",
                    "params": {"column": "position", "operator": "equals", "value": "WR"},
                },
                {"type": "cast", "params": {"column": "score", "to": "number"}},
                {"type": "select", "params": {"columns": ["id", "score"]}},
            ],
        },
    )
    assert create_resp.status_code == 200
    model = create_resp.json()

    preview_resp = client.post(f"/admin/models/{model['id']}/preview")
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["row_count"] == 2
    assert preview["rows"] == [{"id": "1", "score": 8.0}, {"id": "3", "score": 9.0}]

    lineage = client.get(f"/admin/lineage/{model['target_table_id']}").json()
    assert lineage["upstream"] == ["bronze:demo.players"]


def test_model_materialize_creates_durable_model_table(client):
    bronze_store.append_raw(
        "demo",
        "players",
        [
            {"id": "1", "position": "WR", "score": "8"},
            {"id": "2", "position": "QB", "score": "7"},
            {"id": "3", "position": "WR", "score": "9"},
        ],
    )
    model = client.post(
        "/admin/models",
        json={
            "name": "Materialized WR scores",
            "source_table_id": "bronze:demo.players",
            "operations": [
                {
                    "type": "filter",
                    "params": {"column": "position", "operator": "equals", "value": "WR"},
                },
                {"type": "select", "params": {"columns": ["id", "score"]}},
            ],
        },
    ).json()

    materialize_resp = client.post(f"/admin/models/{model['id']}/materialize")
    assert materialize_resp.status_code == 200
    materialized = materialize_resp.json()
    assert materialized["table_id"] == model["target_table_id"]
    assert materialized["row_count"] == 2
    assert materialized["storage_path"].replace("\\", "/").endswith(f"models/{model['id']}.jsonl")

    bronze_store.append_raw("demo", "players", [{"id": "4", "position": "WR", "score": "10"}])
    preview = client.post(f"/admin/models/{model['id']}/preview").json()
    assert preview["row_count"] == 3

    sample = client.get(f"/admin/tables/model/{model['id']}").json()
    assert sample["rows"] == [{"id": "1", "score": "8"}, {"id": "3", "score": "9"}]

    tables = client.get("/admin/tables").json()
    model_table = next(t for t in tables["models"] if t["table_id"] == model["target_table_id"])
    assert model_table["row_count"] == 2
    assert model_table["size_bytes"] > 0
    assert model_table["freshness"]["source"] == "storage_mtime"
    assert model_table["upstream"] == ["bronze:demo.players"]


def test_model_materialize_job_updates_job_and_model_table(client):
    bronze_store.append_raw("demo", "orders", [{"id": "1", "status": "open"}])
    model = client.post(
        "/admin/models",
        json={
            "name": "Open orders",
            "source_table_id": "bronze:demo.orders",
            "operations": [
                {
                    "type": "filter",
                    "params": {"column": "status", "operator": "equals", "value": "open"},
                }
            ],
        },
    ).json()
    job = client.post(
        "/admin/jobs",
        json={
            "name": "Materialize open orders",
            "kind": "model_materialize",
            "target": {"model_id": model["id"]},
            "schedule": {"type": "daily"},
        },
    ).json()

    run_resp = client.post(f"/admin/jobs/{job['id']}/run")
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert data["run"]["status"] == "succeeded"
    assert data["details"]["row_count"] == 1
    assert data["job"]["last_status"] == "succeeded"
    assert client.get(f"/admin/tables/model/{model['id']}").json()["rows"] == [
        {"id": "1", "status": "open"}
    ]


def test_storage_endpoint_reports_local_data_paths(client):
    bronze_store.append_raw("demo", "items", [{"id": "1"}])

    resp = client.get("/admin/storage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data_root"]
    assert data["bronze_path"].replace("\\", "/").endswith("bronze")
    assert data["control_plane_path"].replace("\\", "/").endswith("control_plane")
    assert data["total_bytes"] >= data["bronze_bytes"] > 0
    assert data["table_files"][0]["table_id"] == "bronze:demo.items"


def test_storage_retention_preview_and_cleanup_are_scoped(client):
    bronze_store.append_raw("old_source", "events", [{"id": "old"}])
    bronze_store.append_raw("new_source", "events", [{"id": "new"}])
    old_path = workbench.bronze_storage_path("old_source", "events")
    new_path = workbench.bronze_storage_path("new_source", "events")
    assert old_path is not None
    assert new_path is not None

    root = workbench.data_root_info()["data_root"]
    unrelated = os.path.join(root, "unrelated.jsonl")
    with open(unrelated, "w", encoding="utf-8") as f:
        f.write('{"keep": true}\n')

    now = 2_000_000.0
    old_ts = now - (3 * 86400)
    os.utime(old_path, (old_ts, old_ts))
    os.utime(unrelated, (old_ts, old_ts))

    preview_resp = client.post(
        "/admin/storage/retention/preview",
        json={"scopes": ["bronze"], "older_than_days": 1, "now": now},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["candidate_count"] == 1
    assert preview["candidates"][0]["table_id"] == "bronze:old_source.events"

    cleanup_resp = client.post(
        "/admin/storage/cleanup",
        json={"scopes": ["bronze"], "older_than_days": 1, "now": now, "confirm": True},
    )
    assert cleanup_resp.status_code == 200
    cleanup = cleanup_resp.json()
    assert cleanup["deleted_count"] == 1
    assert cleanup["deleted"][0]["table_id"] == "bronze:old_source.events"
    assert not os.path.exists(old_path)
    assert os.path.exists(new_path)
    assert os.path.exists(unrelated)
    assert bronze_store.get_raw("old_source", "events") == []
    assert bronze_store.get_raw("new_source", "events") == [{"id": "new"}]


def test_storage_cleanup_run_history_preserves_metadata_definitions(client):
    bronze_store.append_raw("demo", "users", [{"id": "1"}])
    job = client.post(
        "/admin/jobs",
        json={
            "name": "Keep job metadata",
            "kind": "quality_check",
            "target": {"table_id": "bronze:demo.users"},
            "schedule": {"type": "manual"},
        },
    ).json()
    run_resp = client.post(f"/admin/jobs/{job['id']}/run")
    assert run_resp.status_code == 200
    assert client.get("/admin/runs").json()

    root = workbench.data_root_info()["data_root"]
    runs_path = os.path.join(root, "control_plane", "runs.jsonl")
    jobs_path = os.path.join(root, "control_plane", "jobs.json")
    now = 2_000_000.0
    old_ts = now - (3 * 86400)
    os.utime(runs_path, (old_ts, old_ts))
    os.utime(jobs_path, (old_ts, old_ts))

    cleanup_resp = client.post(
        "/admin/storage/cleanup",
        json={"scopes": ["run_history"], "older_than_days": 1, "now": now, "confirm": True},
    )
    assert cleanup_resp.status_code == 200
    cleanup = cleanup_resp.json()
    assert cleanup["deleted_count"] == 1
    assert cleanup["deleted"][0]["collection"] == "runs"
    assert client.get("/admin/runs").json() == []
    assert client.get("/admin/jobs").json()[0]["id"] == job["id"]
    assert os.path.exists(jobs_path)


def test_file_source_preview_and_ingest_creates_bronze_table_and_lineage(client):
    payload = {
        "connector": "file",
        "name": "Weekly Spend",
        "source_id": "weekly_spend",
        "table_name": "expenses",
        "filename": "expenses.csv",
        "content": "id,amount,category\n1,12.50,coffee\n2,44.00,books\n",
    }

    preview_resp = client.post("/admin/sources/preview", json=payload)
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["table_id"] == "bronze:weekly_spend.expenses"
    assert preview["row_count"] == 2
    assert preview["preview_rows"][0] == {"id": "1", "amount": "12.50", "category": "coffee"}
    assert ("weekly_spend", "expenses", 2) not in bronze_store.list_tables()

    ingest_resp = client.post("/admin/sources/ingest", json=payload)
    assert ingest_resp.status_code == 200
    result = ingest_resp.json()
    assert result["ok"] is True
    assert result["row_count"] == 2
    assert result["source"]["reusable"] is False
    assert ("weekly_spend", "expenses", 2) in bronze_store.list_tables()

    profile = client.get("/admin/table-profiles/bronze:weekly_spend.expenses").json()
    assert profile["upstream"] == ["source:weekly_spend"]
    assert {col["name"] for col in profile["schema"]} == {"id", "amount", "category"}


def test_path_source_can_be_saved_and_rerun_as_job(client, tmp_path):
    source_file = tmp_path / "users.jsonl"
    source_file.write_text('{"id":"u1","name":"Ada"}\n{"id":"u2","name":"Grace"}\n', encoding="utf-8")

    ingest_resp = client.post(
        "/admin/sources/ingest",
        json={
            "connector": "file",
            "name": "Users",
            "source_id": "users_file",
            "table_name": "users",
            "path": str(source_file),
            "format": "jsonl",
        },
    )
    assert ingest_resp.status_code == 200
    source = ingest_resp.json()["source"]
    assert source["reusable"] is True
    assert source["config"]["path"] == str(source_file)

    job_resp = client.post(
        "/admin/jobs",
        json={
            "name": "Refresh users file",
            "kind": "source_ingest",
            "target": {"source_id": "users_file"},
            "schedule": {"type": "hourly"},
        },
    )
    assert job_resp.status_code == 200
    job = job_resp.json()

    run_resp = client.post(f"/admin/jobs/{job['id']}/run")
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert data["run"]["status"] == "succeeded"
    assert data["details"]["row_count"] == 2
    assert len(bronze_store.get_raw("users_file", "users")) == 4


def test_api_source_preview_extracts_records_path(client):
    class MockHeaders:
        def get_content_charset(self):
            return "utf-8"

    class MockResponse:
        headers = MockHeaders()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"data":{"items":[{"id":"a"},{"id":"b"}]}}'

    with patch("analytics_foundry.workbench.urlopen", return_value=MockResponse()):
        resp = client.post(
            "/admin/sources/preview",
            json={
                "connector": "api",
                "name": "Example API",
                "source_id": "example_api",
                "table_name": "items",
                "url": "https://example.test/items",
                "records_path": "data.items",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["table_id"] == "bronze:example_api.items"
    assert data["row_count"] == 2
    assert data["preview_rows"] == [{"id": "a"}, {"id": "b"}]


def test_runtime_diagnostics_reports_storage_adapter_scheduler_and_metadata():
    with TestClient(app) as c:
        resp = c.get("/admin/diagnostics", params={"now": 100})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["storage"]["writable"] is True
    assert data["metadata"]["collection_count"] == 9
    assert data["metadata"]["total_records"] == 4
    adapter_status = {adapter["source_id"]: adapter for adapter in data["adapters"]["adapters"]}
    assert adapter_status["nfl_sleeper"]["registered"] is True
    assert adapter_status["nfl_weekly_feed"]["registered"] is True
    assert adapter_status["ai_daily_brief"]["registered"] is True
    assert data["scheduler"]["enabled"] is True
    assert data["scheduler"]["job_count"] == 4
    assert data["activity"]["open_alert_count"] == 0


def test_runtime_diagnostics_flags_invalid_metadata_file(client):
    root = bronze_store.get_data_root()
    assert root is not None
    control_root = root / "control_plane"
    control_root.mkdir(parents=True, exist_ok=True)
    (control_root / "jobs.json").write_text("{invalid json", encoding="utf-8")

    resp = client.get("/admin/diagnostics")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "error"
    assert data["metadata"]["status"] == "error"
    jobs = next(item for item in data["metadata"]["collections"] if item["name"] == "jobs")
    assert jobs["status"] == "error"


def test_metadata_bundle_round_trips_across_data_roots(client, tmp_path):
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    bronze_store.set_data_root(root_a)
    try:
        workbench.clear()
        bronze_store.clear()
        source_resp = client.post(
            "/admin/sources/ingest",
            json={
                "connector": "file",
                "name": "Demo users",
                "source_id": "demo_users",
                "table_name": "users",
                "filename": "users.csv",
                "format": "csv",
                "content": "id,name\n1,\n2,Ada\n",
            },
        )
        assert source_resp.status_code == 200
        source = source_resp.json()["source"]

        rule_resp = client.post(
            "/admin/quality/rules",
            json={
                "table_id": "bronze:demo_users.users",
                "type": "required",
                "name": "Name required",
                "column": "name",
            },
        )
        assert rule_resp.status_code == 200
        rule = rule_resp.json()

        model_resp = client.post(
            "/admin/models",
            json={
                "name": "User names",
                "source_table_id": "bronze:demo_users.users",
                "operations": [{"type": "select", "params": {"columns": ["id", "name"]}}],
            },
        )
        assert model_resp.status_code == 200
        model = model_resp.json()

        job_resp = client.post(
            "/admin/jobs",
            json={
                "name": "Check user names",
                "kind": "quality_check",
                "target": {"table_id": "bronze:demo_users.users"},
                "schedule": {"type": "manual"},
            },
        )
        assert job_resp.status_code == 200
        job = job_resp.json()

        quality_resp = client.post("/admin/quality/run", json={"table_id": "bronze:demo_users.users"})
        assert quality_resp.status_code == 200
        assert quality_resp.json()["run"]["status"] == "failed"
        alert = client.get("/admin/alerts", params={"status": "open"}).json()[0]

        target_resp = client.post(
            "/admin/alerts/delivery-targets",
            json={
                "name": "Ops hook",
                "kind": "webhook",
                "url": "https://hooks.example.test/foundry",
                "severities": ["error"],
            },
        )
        assert target_resp.status_code == 200
        target = target_resp.json()

        bundle_resp = client.get("/admin/export", params={"include_history": True})
        assert bundle_resp.status_code == 200
        bundle = bundle_resp.json()
        assert bundle["format"] == "analytics_foundry.workbench.bundle"
        assert bundle["record_counts"]["collections"]["jobs"] == 1
        assert bundle["record_counts"]["history"]["quality_results"] == 1

        bronze_store.set_data_root(root_b)
        workbench.clear()
        bronze_store.clear()
        import_resp = client.post("/admin/import", json={"mode": "replace", "bundle": bundle})
        assert import_resp.status_code == 200
        assert import_resp.json()["record_counts"]["imported"] >= 7

        assert client.get("/admin/sources").json()[0]["id"] == source["id"]
        assert client.get("/admin/quality/rules").json()[0]["id"] == rule["id"]
        assert client.get("/admin/models").json()[0]["id"] == model["id"]
        assert client.get("/admin/jobs").json()[0]["id"] == job["id"]
        assert client.get("/admin/alerts").json()[0]["id"] == alert["id"]
        assert client.get("/admin/alerts/delivery-targets").json()[0]["id"] == target["id"]
        assert client.get("/admin/runs").json()[0]["kind"] == "quality_check"
        assert client.get("/admin/quality/results").json()[0]["rule_id"] == rule["id"]
    finally:
        bronze_store.set_data_root(None)


def test_metadata_bundle_merge_deduplicates_records(client):
    job_resp = client.post(
        "/admin/jobs",
        json={
            "name": "Daily check",
            "kind": "quality_check",
            "target": {"table_id": "bronze:demo.users"},
            "schedule": {"type": "manual"},
        },
    )
    assert job_resp.status_code == 200
    bundle = client.get("/admin/export").json()

    first_import = client.post("/admin/import", json={"mode": "merge", "bundle": bundle})
    second_import = client.post("/admin/import", json={"mode": "merge", "bundle": bundle})

    assert first_import.status_code == 200
    assert second_import.status_code == 200
    assert [job["id"] for job in client.get("/admin/jobs").json()] == [job_resp.json()["id"]]


def test_metadata_import_rejects_invalid_bundle(client):
    resp = client.post(
        "/admin/import",
        json={"mode": "merge", "bundle": {"format": "other", "version": 1, "collections": {}}},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Unsupported import bundle format"
