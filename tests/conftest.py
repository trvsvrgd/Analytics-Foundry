"""Pytest fixtures. Use a temporary data dir so tests don't touch ./data."""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def foundry_data_dir(tmp_path_factory):
    """Point FOUNDRY_DATA_DIR to a session tmp dir so bronze persistence is isolated."""
    tmp = tmp_path_factory.mktemp("foundry_data")
    admin_api_key = os.environ.pop("FOUNDRY_ADMIN_API_KEY", None)
    os.environ["FOUNDRY_DATA_DIR"] = str(tmp)
    yield tmp
    os.environ.pop("FOUNDRY_DATA_DIR", None)
    if admin_api_key is not None:
        os.environ["FOUNDRY_ADMIN_API_KEY"] = admin_api_key
