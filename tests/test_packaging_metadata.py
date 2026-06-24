import tomllib
from pathlib import Path

HUB_ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    return tomllib.loads((HUB_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_packaging_metadata_declares_build_backend_and_owner_metadata():
    payload = _pyproject()

    assert payload["build-system"]["build-backend"] == "setuptools.build_meta"
    assert any(req.startswith("setuptools>=") for req in payload["build-system"]["requires"])
    assert payload["project"]["authors"] == [{"name": "Choemun Yeong"}]
    assert payload["project"]["maintainers"] == [{"name": "Moonweave Research"}]
    assert payload["project"]["license-files"] == ["LICENSE", "NOTICE"]


def test_packaging_metadata_pins_public_distribution_surface():
    payload = _pyproject()

    assert payload["project"]["name"] == "graph-making-hub"
    assert payload["project"]["scripts"] == {
        "graphhub": "orchestrator:main",
        "graphhub-mcp": "graphhub_mcp_server:main",
    }
    assert payload["tool"]["setuptools"]["py-modules"] == [
        "graphhub_mcp_server",
        "hub_uv",
        "orchestrator",
    ]
    assert payload["tool"]["setuptools"]["packages"]["find"]["include"] == [
        "hub_core*",
        "plotting*",
        "themes*",
    ]
