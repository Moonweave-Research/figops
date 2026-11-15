import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

HUB_ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    return tomllib.loads((HUB_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_packaging_metadata_declares_build_backend_and_owner_metadata():
    payload = _pyproject()

    assert payload["build-system"]["build-backend"] == "setuptools.build_meta"
    assert any(req.startswith("setuptools>=") for req in payload["build-system"]["requires"])
    assert payload["project"]["authors"] == [{"name": "Choemun Yeong"}]
    assert payload["project"]["maintainers"] == [{"name": "Moonweave Research"}]
    assert payload["project"]["license"] == "Apache-2.0"
    assert payload["project"]["license-files"] == ["LICENSE", "NOTICE"]


def test_packaging_metadata_pins_public_distribution_surface():
    payload = _pyproject()

    assert payload["project"]["name"] == "figops"
    assert payload["project"]["scripts"] == {
        "figops": "orchestrator:main",
        "figops-mcp": "figops_mcp_server:main",
        "graphhub": "orchestrator:main",
        "graphhub-mcp": "graphhub_mcp_server:main",
    }
    assert payload["tool"]["setuptools"]["py-modules"] == [
        "figops",
        "figops_mcp_server",
        "graphhub_mcp_server",
        "hub_uv",
        "orchestrator",
    ]
    assert payload["tool"]["setuptools"]["packages"]["find"]["include"] == [
        "hub_core*",
        "plotting*",
        "themes*",
    ]


@pytest.mark.parametrize(
    ("package", "vulnerable", "patched"),
    [
        ("certifi", "2026.2.25", "2026.10.18"),
        ("idna", "3.11", "3.15"),
        ("msgpack", "1.1.2", "1.2.3"),
        ("urllib3", "2.6.3", "2.8.0"),
    ],
)
def test_io_install_rejects_known_vulnerable_transitives(package, vulnerable, patched):
    requirements = {
        requirement.name: requirement
        for requirement in map(Requirement, _pyproject()["project"]["optional-dependencies"]["io"])
    }

    # Wheels do not carry uv.lock. An existing optional dependency must not
    # remain satisfiable at its known-vulnerable version during an upgrade.
    assert package in requirements
    assert vulnerable not in requirements[package].specifier
    assert patched in requirements[package].specifier
