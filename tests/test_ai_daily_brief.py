"""Tests for AI Daily Brief ingestion and medallion transformations."""

import pytest
from fastapi.testclient import TestClient

from analytics_foundry.adapters.ai_daily_brief import AiDailyBriefAdapter
from analytics_foundry.bronze import store as bronze_store
from analytics_foundry.silver import ai_daily_brief as silver_aidb
from analytics_foundry.gold import ai_daily_brief as gold_aidb
from analytics_foundry.api import app


class FakeResponse:
    def __init__(self, json_data=None, text_data=None, status_code=200):
        self._json_data = json_data
        self._text_data = text_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code != 200:
            raise Exception("HTTP Error")

    def json(self):
        return self._json_data

    @property
    def text(self):
        return self._text_data


class FakeHttpxClient:
    def __init__(self, responses):
        self.responses = responses

    def get(self, url, **kwargs):
        if url in self.responses:
            return self.responses[url]
        raise Exception(f"Unexpected GET request to {url}")


@pytest.fixture(autouse=True)
def clean_stores():
    bronze_store.clear()
    yield
    bronze_store.clear()


def test_ai_daily_brief_adapter_ingestion():
    """AiDailyBriefAdapter fetches agent.json index and transcripts to bronze."""
    agent_json = {
        "editions": [
            {
                "date": "2026-06-13",
                "title": "Fable 5 Shut Down by US Government",
                "teaser": "The US government forced Anthropic to shut down...",
                "tags": ["policy", "business", "models"],
                "transcript": "https://aidailybrief.ai/e/2026-06-13/transcript.md",
            },
            {
                "date": "2026-06-12",
                "title": "The AI Chart Everyone Is Getting Wrong",
                "teaser": "SpaceX prices...",
                "tags": ["business"],
                "transcript": "https://aidailybrief.ai/e/2026-06-12/transcript.md",
            }
        ]
    }
    client = FakeHttpxClient({
        "https://aidailybrief.ai/agent.json": FakeResponse(json_data=agent_json),
        "https://aidailybrief.ai/e/2026-06-13/transcript.md": FakeResponse(text_data="Fable 5 transcript text..."),
        "https://aidailybrief.ai/e/2026-06-12/transcript.md": FakeResponse(text_data="Chart transcript text..."),
    })

    adapter = AiDailyBriefAdapter(client=client)
    adapter.ingest_to_bronze()

    rows = bronze_store.get_raw("ai_daily_brief", "transcripts")
    assert len(rows) == 2
    # Records should be in chronological order (oldest first: 2026-06-12, then 2026-06-13)
    assert rows[0]["date"] == "2026-06-12"
    assert rows[0]["transcript_text"] == "Chart transcript text..."
    assert rows[1]["date"] == "2026-06-13"
    assert rows[1]["transcript_text"] == "Fable 5 transcript text..."


def test_ai_daily_brief_adapter_avoids_duplicates():
    """AiDailyBriefAdapter avoids ingesting already-existing transcripts."""
    bronze_store.append_raw("ai_daily_brief", "transcripts", [
        {"date": "2026-06-12", "record_id": "aidb:2026-06-12", "transcript_text": "already here"}
    ])

    agent_json = {
        "editions": [
            {
                "date": "2026-06-13",
                "title": "Fable 5 Shut Down by US Government",
                "teaser": "The US government forced Anthropic to shut down...",
                "tags": ["policy", "business", "models"],
                "transcript": "https://aidailybrief.ai/e/2026-06-13/transcript.md",
            },
            {
                "date": "2026-06-12",
                "title": "The AI Chart Everyone Is Getting Wrong",
                "teaser": "SpaceX prices...",
                "tags": ["business"],
                "transcript": "https://aidailybrief.ai/e/2026-06-12/transcript.md",
            }
        ]
    }
    client = FakeHttpxClient({
        "https://aidailybrief.ai/agent.json": FakeResponse(json_data=agent_json),
        "https://aidailybrief.ai/e/2026-06-13/transcript.md": FakeResponse(text_data="Fable 5 transcript text..."),
    })

    adapter = AiDailyBriefAdapter(client=client)
    adapter.ingest_to_bronze()

    rows = bronze_store.get_raw("ai_daily_brief", "transcripts")
    assert len(rows) == 2
    assert rows[0]["transcript_text"] == "already here"
    assert rows[1]["date"] == "2026-06-13"


def test_silver_cleaned_transcripts():
    """Silver conformed daily briefs output conforms to expected schema and calculates word/paragraph counts."""
    bronze_store.append_raw("ai_daily_brief", "transcripts", [
        {
            "date": "2026-06-13",
            "title": "Fable 5 Shut Down",
            "teaser": "Teaser text",
            "tags": ["policy"],
            "transcript_text": "Hello world\nThis is paragraph two."
        }
    ])

    result = silver_aidb.get_cleaned_transcripts()
    assert len(result) == 1
    t = result[0]
    for key in silver_aidb.SILVER_TRANSCRIPT_KEYS:
        assert key in t
    assert t["record_id"] == "aidb:2026-06-13"
    assert t["word_count"] == 6
    assert t["paragraph_count"] == 2


def test_gold_mba_coursework_impact():
    """Gold MBA coursework impact includes conformed metrics for known and future dates."""
    # Test known date
    bronze_store.append_raw("ai_daily_brief", "transcripts", [
        {
            "date": "2026-06-13",
            "title": "Fable 5 Shut Down by US Government",
            "teaser": "Anthropic cutoff",
            "tags": ["policy"],
            "transcript_text": "Fable 5 shutdown by US..."
        },
        # Future/unknown date
        {
            "date": "2026-06-14",
            "title": "Future AI Breakthrough",
            "teaser": "Future breakthrough",
            "tags": ["models"],
            "transcript_text": "Nvidia announced a new chip with massive compute and gpu capabilities."
        }
    ])

    result = gold_aidb.get_mba_impact()
    assert len(result) == 2

    # Verify curated known date
    r_known = [r for r in result if r["date"] == "2026-06-13"][0]
    assert "watershed moment" in r_known["key_takeaway"]
    assert "Sovereign AI" in r_known["business_topics"]
    assert len(r_known["discussion_questions"]) == 3
    assert r_known["relevance_score"] == 10

    # Verify fallback future date
    r_future = [r for r in result if r["date"] == "2026-06-14"][0]
    assert r_future["key_takeaway"] == "Future breakthrough"
    assert "Geopolitical Compute Supply Chains" in r_future["business_topics"]
    assert r_future["relevance_score"] == 8


def test_gold_product_strategy_impact():
    """Gold PM strategy impact includes conformed metrics for known and future dates."""
    bronze_store.append_raw("ai_daily_brief", "transcripts", [
        {
            "date": "2026-06-13",
            "title": "Fable 5 Shut Down",
            "teaser": "cutoff",
            "tags": ["policy"],
            "transcript_text": "shutdown"
        },
        {
            "date": "2026-06-14",
            "title": "Future Breakthrough",
            "teaser": "future",
            "tags": ["models"],
            "transcript_text": "breakthrough"
        }
    ])

    result = gold_aidb.get_product_strategy_impact()
    assert len(result) == 2

    r_known = [r for r in result if r["date"] == "2026-06-13"][0]
    assert "failover routing" in r_known["platform_impact"]
    assert "KYC" in r_known["pm_domain_impact"]
    assert "Implement dynamic API failover" in r_known["action_items"][0]
    assert "Single-model dependency" in r_known["pm_takeaway"]

    r_future = [r for r in result if r["date"] == "2026-06-14"][0]
    assert "model availability" in r_future["platform_impact"]
    assert "flexible, multi-model architectures" in r_future["pm_domain_impact"]
    assert "prompt caching" in r_future["action_items"][0]


def test_admin_api_endpoints():
    """Admin UI routing and table profiles serve the new daily brief tables."""
    client = TestClient(app)

    # Ingest some fake transcript to check route resolution
    bronze_store.append_raw("ai_daily_brief", "transcripts", [
        {
            "date": "2026-06-13",
            "title": "Fable 5 Shut Down",
            "teaser": "cutoff",
            "tags": ["policy"],
            "transcript_text": "shutdown"
        }
    ])

    # 1. Verify /admin/tables lists new tables
    tables_resp = client.get("/admin/tables")
    assert tables_resp.status_code == 200
    data = tables_resp.json()
    
    # Check new silver table exists
    silver_table_ids = [t["table_id"] for t in data["silver"]]
    assert "silver:ai_daily_brief_cleaned" in silver_table_ids

    # Check new gold tables exist
    gold_table_ids = [t["table_id"] for t in data["gold"]]
    assert "gold:mba_coursework_impact" in gold_table_ids
    assert "gold:ai_platform_product_strategy" in gold_table_ids

    # 2. Verify sampling endpoint returns rows for new tables
    sample_silver = client.get("/admin/tables/silver/ai_daily_brief_cleaned")
    assert sample_silver.status_code == 200
    assert len(sample_silver.json()["rows"]) == 1
    assert sample_silver.json()["rows"][0]["title"] == "Fable 5 Shut Down"

    sample_gold = client.get("/admin/tables/gold/mba_coursework_impact")
    assert sample_gold.status_code == 200
    assert len(sample_gold.json()["rows"]) == 1
    assert "watershed moment" in sample_gold.json()["rows"][0]["key_takeaway"]
