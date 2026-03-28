"""RBAC header helper (skeleton for future route guards)."""

from analytics_foundry.rbac import get_optional_role


def test_get_optional_role_accepts_known_roles():
    assert get_optional_role("admin") == "admin"
    assert get_optional_role("  viewer  ") == "viewer"


def test_get_optional_role_rejects_unknown():
    assert get_optional_role("superuser") is None
    assert get_optional_role(None) is None
