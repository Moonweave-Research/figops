import pytest


@pytest.fixture(autouse=True)
def clear_graph_hub_runtime_env(monkeypatch):
    monkeypatch.delenv("RESEARCH_HUB_RUNTIME_ROOT", raising=False)
    monkeypatch.delenv("RESEARCH_HUB_RUNTIME_HOME", raising=False)
