"""Analytics Foundry — generalized data science workbench (medallion architecture, sleeper-stream-scribe API)."""

__version__ = "0.1.0"

from . import bronze, silver, gold  # noqa: F401 — medallion layers

__all__ = ["__version__", "bronze", "silver", "gold"]
