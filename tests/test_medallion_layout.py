"""PLAN 1.2: Verify medallion layer modules exist and import; layout matches TECH_SPEC."""

import pytest


def test_bronze_imports():
    """Bronze layer is importable."""
    from analytics_foundry import bronze

    assert bronze.__name__ == "analytics_foundry.bronze"


def test_silver_imports():
    """Silver layer is importable."""
    from analytics_foundry import silver

    assert silver.__name__ == "analytics_foundry.silver"


def test_gold_imports():
    """Gold layer is importable."""
    from analytics_foundry import gold

    assert gold.__name__ == "analytics_foundry.gold"


def test_medallion_layout_matches_spec():
    """All three medallion layers under analytics_foundry; TECH_SPEC bronze/silver/gold description matches."""
    from analytics_foundry import bronze, silver, gold

    # Layout: bronze (raw), silver (cleaned/conformed), gold (aggregates/analytics)
    assert "raw" in bronze.__doc__.lower() or "ingest" in bronze.__doc__.lower()
    assert "clean" in silver.__doc__.lower() or "conform" in silver.__doc__.lower()
    assert "gold" in gold.__name__ and ("aggregat" in gold.__doc__.lower() or "analytic" in gold.__doc__.lower())
