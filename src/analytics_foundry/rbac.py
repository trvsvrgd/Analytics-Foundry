"""RBAC skeleton: optional role from header for future route guards."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Header

RoleName = Literal["admin", "analyst", "viewer"]


def get_optional_role(
    x_foundry_role: Annotated[str | None, Header(alias="X-Foundry-Role")] = None,
) -> RoleName | None:
    """Parse X-Foundry-Role header if present; invalid values treated as None."""
    if not x_foundry_role:
        return None
    v = x_foundry_role.strip().lower()
    if v in ("admin", "analyst", "viewer"):
        return v  # type: ignore[return-value]
    return None
