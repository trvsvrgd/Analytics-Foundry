"""Pytest fixtures. Use a temporary data dir so tests don't touch ./data."""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def foundry_data_dir(tmp_path_factory):
    """Point FOUNDRY_DATA_DIR to a session tmp dir so bronze persistence is isolated."""
    tmp = tmp_path_factory.mktemp("foundry_data")
    os.environ["FOUNDRY_DATA_DIR"] = str(tmp)
    yield tmp
    os.environ.pop("FOUNDRY_DATA_DIR", None)
