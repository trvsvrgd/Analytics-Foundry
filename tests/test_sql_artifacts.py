"""Phase 2.3: SQL artifacts exist; medallion flow bronze → silver → gold preserved."""

import pytest

from analytics_foundry.sql_loader import get_sql_root, list_sql_files, medallion_layers, read_sql


def test_sql_root_exists():
    """sql/ directory exists."""
    root = get_sql_root()
    assert root.is_dir()
    assert root.name == "sql"


def test_medallion_layers_order():
    """Medallion order is bronze, silver, gold."""
    layers = medallion_layers()
    assert layers == ["bronze", "silver", "gold"]


def test_bronze_sql_files_exist():
    """Bronze layer has .sql files."""
    files = list_sql_files("bronze")
    assert len(files) >= 1
    assert any("nfl" in f or "players" in f for f in files)


def test_silver_sql_files_exist():
    """Silver layer has .sql files."""
    files = list_sql_files("silver")
    assert len(files) >= 1


def test_gold_sql_files_exist():
    """Gold layer has .sql files."""
    files = list_sql_files("gold")
    assert len(files) >= 1


def test_sql_contains_select():
    """SQL artifacts contain SELECT (view/transform)."""
    for layer in medallion_layers():
        for name in list_sql_files(layer):
            content = read_sql(layer, name)
            assert "SELECT" in content.upper(), f"{layer}/{name} should contain SELECT"


def test_sql_artifacts_medallion_flow():
    """SQL structure reflects bronze → silver → gold; no layer skipped."""
    root = get_sql_root()
    for layer in medallion_layers():
        layer_dir = root / layer
        assert layer_dir.is_dir(), f"sql/{layer} should exist"
