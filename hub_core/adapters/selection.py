from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .athena import AthenaBridge, LegacyAthenaBridge, NullAthena
from .conventions import Conventions, GenericConventions, SurfurConventions
from .prefetch import GDrivePrefetcher, NoopPrefetcher, Prefetcher


class AdapterSelectionError(ValueError):
    pass


@dataclass(frozen=True)
class AdapterSelection:
    prefetcher: Prefetcher
    athena: AthenaBridge
    conventions: Conventions


def select_adapters(config: dict[str, Any] | None = None) -> AdapterSelection:
    raw_adapters = _config_adapters(config)
    prefetch_name = _adapter_name(
        raw_adapters,
        "prefetch",
        env_var="GRAPH_HUB_PREFETCH_ADAPTER",
        default="none",
    )
    athena_name = _adapter_name(
        raw_adapters,
        "athena",
        env_var="GRAPH_HUB_ATHENA_ADAPTER",
        default="off",
    )
    conventions_name = _adapter_name(
        raw_adapters,
        "conventions",
        env_var="GRAPH_HUB_CONVENTIONS_ADAPTER",
        default="generic",
    )

    return AdapterSelection(
        prefetcher=_build_prefetcher(prefetch_name),
        athena=_build_athena(athena_name),
        conventions=_build_conventions(conventions_name),
    )


def _config_adapters(config: dict[str, Any] | None) -> dict[str, Any]:
    if not config:
        return {}
    environment = config.get("environment", {})
    if not isinstance(environment, dict):
        return {}
    adapters = environment.get("adapters", {})
    if adapters is None:
        return {}
    if not isinstance(adapters, dict):
        raise AdapterSelectionError("environment.adapters must be a mapping.")
    return adapters


def _adapter_name(
    raw_adapters: dict[str, Any],
    key: str,
    *,
    env_var: str,
    default: str,
) -> str:
    raw_name = os.environ.get(env_var) or raw_adapters.get(key, default)
    return str(raw_name).strip().lower()


def _build_prefetcher(name: str) -> Prefetcher:
    if name in {"", "none", "noop", "off"}:
        return NoopPrefetcher()
    if name == "gdrive":
        return GDrivePrefetcher()
    raise AdapterSelectionError("Unknown prefetch adapter {!r}; expected one of: gdrive, none.".format(name))


def _build_athena(name: str) -> AthenaBridge:
    if name in {"", "none", "null", "off"}:
        return NullAthena()
    if name in {"legacy", "on"}:
        return LegacyAthenaBridge()
    raise AdapterSelectionError("Unknown athena adapter {!r}; expected one of: legacy, off.".format(name))


def _build_conventions(name: str) -> Conventions:
    if name in {"", "generic", "none"}:
        return GenericConventions()
    if name == "surfur":
        return SurfurConventions()
    raise AdapterSelectionError(
        "Unknown conventions adapter {!r}; expected one of: generic, surfur.".format(name)
    )
