"""Application errors for consistent handling and HTTP mapping."""


class FoundryError(Exception):
    """Base error for Foundry operations."""


class AdapterNotFoundError(FoundryError):
    """No adapter registered for the requested source."""


class IngestionError(FoundryError):
    """Bronze ingest failed (network, validation, or source error)."""


class ConfigurationError(FoundryError):
    """Invalid or inconsistent startup configuration."""
