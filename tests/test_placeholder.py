"""Placeholder test so pytest runs successfully (PLAN 1.1)."""

import pytest


def test_placeholder_passes():
    """One passing test to verify pytest and layout."""
    assert True


def test_analytics_foundry_import():
    """Verify package is importable."""
    import analytics_foundry

    assert analytics_foundry.__version__ == "0.1.0"
