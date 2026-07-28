"""Shared low-level helpers for conservative dependency scanners.

This module intentionally contains no language-specific parsing.  Python and
R scanners use the same bounded path predicates and deterministic result
ordering so the facade can preserve one stable evidence contract.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_PATH_SUFFIXES = {
    ".csv",
    ".tsv",
    ".txt",
    ".dat",
    ".parquet",
    ".json",
    ".jsonl",
    ".xlsx",
    ".xls",
    ".h5",
    ".hdf5",
    ".feather",
    ".pkl",
    ".pickle",
    ".rds",
    ".rda",
    ".rdata",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".pdf",
    ".eps",
    ".tif",
    ".tiff",
    ".py",
    ".r",
}


def _is_external_url(value: str) -> bool:
    """Return whether a literal names a remote URL rather than a project path."""

    return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value.strip()))


def _looks_like_path(value: str) -> bool:
    """Return true only for an obvious file/path literal.

    Labels, package names, and arbitrary prose are intentionally ignored.  A
    URL is not treated as a project dependency because it cannot be safely
    materialised by a copy-only project migration.
    """

    text = value.strip()
    if not text or len(text) > 4096 or _is_external_url(text):
        return False
    if text.startswith(("./", "../", "/", "~/", "\\")) or "/" in text or "\\" in text:
        return True
    return Path(text).suffix.lower() in _PATH_SUFFIXES


def _is_static_local_path(value: str) -> bool:
    """Recognise any non-empty local literal passed to a path-bearing API.

    A suffix is not required here: ``read_csv("input")``, ``open("README")``,
    and ``Path("workspace")`` are all explicit path references.  The broader
    ``_looks_like_path`` predicate remains intentionally conservative for
    string literals found outside a recognised path API.
    """

    text = value.strip()
    return bool(text) and len(text) <= 4096 and not _is_external_url(text)


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return deterministic scanner evidence without duplicate findings."""

    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in items:
        # A path literal found through a recognised file API and through the
        # fallback literal walk is one dependency, not two.  Keep separate
        # source locations, however, because two calls on different lines may
        # require independent review.
        if item.get("kind") == "path_literal":
            key = (
                item.get("kind"),
                item.get("path"),
            )
        elif item.get("kind") == "hardcoded_path":
            key = (
                item.get("kind"),
                item.get("path"),
                item.get("line"),
                item.get("column"),
            )
        else:
            key = tuple((field, item.get(field)) for field in sorted(item))
        unique.setdefault(key, item)
    return sorted(
        unique.values(),
        key=lambda item: (
            int(item.get("line", 0) or 0),
            int(item.get("column", 0) or 0),
            str(item.get("kind", "")),
            str(item.get("path", item.get("reference", ""))),
            str(item.get("source", "")),
        ),
    )


__all__ = [
    "_PATH_SUFFIXES",
    "_deduplicate",
    "_is_external_url",
    "_is_static_local_path",
    "_looks_like_path",
]
