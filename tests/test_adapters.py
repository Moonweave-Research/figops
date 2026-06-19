import os
from unittest.mock import patch

import pytest

from hub_core.adapters import (
    AdapterSelectionError,
    GDrivePrefetcher,
    GenericConventions,
    NoopPrefetcher,
    NullAthena,
    SurfurConventions,
    select_adapters,
)
from hub_core.config_parser import validate_config


def _minimal_config() -> dict:
    return {"project": {"name": "Adapter Test"}}


def test_select_adapters_defaults_to_generic_noop_null():
    with patch.dict(os.environ, {}, clear=True):
        adapters = select_adapters({})

    assert isinstance(adapters.prefetcher, NoopPrefetcher)
    assert isinstance(adapters.athena, NullAthena)
    assert isinstance(adapters.conventions, GenericConventions)


def test_select_adapters_accepts_environment_config_opt_ins():
    config = {
        "environment": {
            "adapters": {
                "prefetch": "gdrive",
                "athena": "off",
                "conventions": "surfur",
            }
        }
    }

    with patch.dict(os.environ, {}, clear=True):
        adapters = select_adapters(config)

    assert isinstance(adapters.prefetcher, GDrivePrefetcher)
    assert isinstance(adapters.athena, NullAthena)
    assert isinstance(adapters.conventions, SurfurConventions)


def test_select_adapters_env_overrides_config():
    config = {
        "environment": {
            "adapters": {
                "prefetch": "none",
                "athena": "off",
                "conventions": "generic",
            }
        }
    }
    env = {
        "GRAPH_HUB_PREFETCH_ADAPTER": "gdrive",
        "GRAPH_HUB_CONVENTIONS_ADAPTER": "surfur",
    }

    with patch.dict(os.environ, env, clear=True):
        adapters = select_adapters(config)

    assert isinstance(adapters.prefetcher, GDrivePrefetcher)
    assert isinstance(adapters.conventions, SurfurConventions)


def test_select_adapters_rejects_unknown_names():
    config = {"environment": {"adapters": {"prefetch": "magic"}}}

    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(AdapterSelectionError, match="prefetch"):
            select_adapters(config)


def test_validate_config_accepts_adapter_config():
    config = _minimal_config()
    config["environment"] = {
        "adapters": {
            "prefetch": "gdrive",
            "athena": "off",
            "conventions": "surfur",
        }
    }

    assert validate_config(config) == []


def test_validate_config_rejects_unknown_adapter_config():
    config = _minimal_config()
    config["environment"] = {"adapters": {"conventions": "researchos"}}

    errors = validate_config(config)

    assert any("environment.adapters.conventions" in error for error in errors)
