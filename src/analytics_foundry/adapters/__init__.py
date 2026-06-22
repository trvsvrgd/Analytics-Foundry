"""Pluggable source adapters: source → bronze. New domains implement the protocol without changing core pipeline."""

from analytics_foundry.adapters.protocol import SourceAdapter
from analytics_foundry.adapters.registry import get_adapter, register_adapter

__all__ = ["SourceAdapter", "register_adapter", "get_adapter"]
