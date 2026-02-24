"""PLAN 1.3: Adapter interface exists; stub can be registered and instantiated."""

import pytest


def test_source_adapter_protocol_exists():
    """Adapter interface (SourceAdapter protocol) exists."""
    from analytics_foundry.adapters import SourceAdapter

    assert SourceAdapter is not None


def test_stub_implements_protocol():
    """Stub adapter implements SourceAdapter protocol."""
    from analytics_foundry.adapters.protocol import SourceAdapter
    from analytics_foundry.adapters.stub import StubSourceAdapter

    stub = StubSourceAdapter()
    assert isinstance(stub, SourceAdapter)
    assert stub.source_id == "stub"


def test_stub_can_be_instantiated():
    """Stub can be instantiated and ingest_to_bronze is callable."""
    from analytics_foundry.adapters.stub import StubSourceAdapter

    stub = StubSourceAdapter()
    stub.ingest_to_bronze()
    stub.ingest_to_bronze(league_id="123")


def test_stub_can_be_registered_and_retrieved():
    """Stub can be registered and retrieved via get_adapter."""
    from analytics_foundry.adapters import get_adapter, register_adapter
    from analytics_foundry.adapters.registry import clear_registry
    from analytics_foundry.adapters.stub import StubSourceAdapter

    clear_registry()
    register_adapter(StubSourceAdapter)
    adapter = get_adapter("stub")
    assert adapter is not None
    assert adapter.source_id == "stub"
    clear_registry()
