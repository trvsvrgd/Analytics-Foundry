"""Optional multi-tenant data root (FOUNDRY_TENANT_ID)."""


from analytics_foundry.bronze import store as bronze_store


def test_data_root_includes_tenant(monkeypatch):
    monkeypatch.setenv("FOUNDRY_TENANT_ID", "acme_corp")
    root = bronze_store.get_data_root()
    assert root is not None
    assert root.name == "acme_corp"
    assert root.parent.name == "tenants"
