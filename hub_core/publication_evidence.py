"""Bounded, path-free evidence ingestion for publication readiness.

The adapter intentionally knows nothing about MCP.  It accepts the mapping
shape emitted by render manifests and exposes only review-relevant evidence.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath
from typing import Any, Final

from .artifact_integrity import inspect_manifest_artifacts
from .provenance_inputs import provenance_hash_coverage
from .redaction import redact_secrets

MAX_READINESS_MANIFEST_BYTES: Final = 4 * 1024 * 1024
_MAX_DEPTH: Final = 24
_MAX_ITEMS: Final = 50_000
_MAX_STRING_LENGTH: Final = 256_000
_SHA256_RE: Final = re.compile(r"^[0-9a-fA-F]{64}$")
_UNC_PATH_RE: Final = re.compile(r"\\\\[^\\\s]+\\[^\\\s]+(?:\\[^\s\"'<>]*)*")
_WINDOWS_ABSOLUTE_PATH_RE: Final = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s\"'<>]+")
_POSIX_ABSOLUTE_PATH_RE: Final = re.compile(r"(?<![A-Za-z0-9:])/(?:[^\s/\"'<>]+/?)+")
_RELATIVE_BACKSLASH_PATH_RE: Final = re.compile(
    r"^(?!.*(?:^|\\)\.\.(?:\\|$))[A-Za-z0-9_.-]+(?:\\[A-Za-z0-9_.-]+)+$"
)
_PATH_PLACEHOLDER: Final = "[PATH]"
_PATH_KEYS: Final = {
    "path",
    "paths",
    "root",
    "roots",
    "directory",
    "directories",
    "dir",
    "dirs",
    "uri",
    "uris",
}
_EVIDENCE_FIELDS: Final = (
    "geometry_diagnostics",
    "visual_preflight_status",
    "layout_report",
    "calculation_checks",
    "baseline_comparison",
    "artifact_status",
    "failure_stage",
    "style_summary",
    "raw_integrity_status",
    "canonical_docs_registry",
    "research_ops_policy",
    "exact_reproducibility",
    "visual_comparison",
    "data_contract",
)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _is_path_key(key: str) -> bool:
    normalized = key.casefold()
    return normalized in _PATH_KEYS or normalized.endswith("_path") or normalized.endswith("_paths")


def _is_absolute_path_text(value: str) -> bool:
    if value.startswith(("/", "\\\\")):
        return True
    return PureWindowsPath(value).is_absolute()


def _sanitize_path_text(value: str) -> str:
    """Remove embedded absolute paths and canonicalize unambiguous relative paths."""
    sanitized = _UNC_PATH_RE.sub(_PATH_PLACEHOLDER, value)
    sanitized = _WINDOWS_ABSOLUTE_PATH_RE.sub(_PATH_PLACEHOLDER, sanitized)
    sanitized = _POSIX_ABSOLUTE_PATH_RE.sub(_PATH_PLACEHOLDER, sanitized)
    if _RELATIVE_BACKSLASH_PATH_RE.fullmatch(sanitized):
        return sanitized.replace("\\", "/")
    return sanitized


def _safe_value(value: Any, *, depth: int = 0, counter: list[int] | None = None) -> Any:
    if depth > _MAX_DEPTH:
        raise ValueError("readiness evidence exceeds maximum nesting depth")
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > _MAX_ITEMS:
        raise ValueError("readiness evidence exceeds maximum item count")

    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("readiness evidence contains a non-finite number")
        return value
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LENGTH:
            raise ValueError("readiness evidence contains an oversized string")
        sanitized = _sanitize_path_text(value)
        if _is_absolute_path_text(sanitized):
            raise ValueError("readiness evidence contains an absolute path")
        return sanitized
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("readiness evidence object keys must be strings")
            if _is_path_key(key):
                continue
            result[key] = _safe_value(child, depth=depth + 1, counter=counter)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth=depth + 1, counter=counter) for item in value]
    raise TypeError(f"unsupported readiness evidence value: {type(value).__name__}")


def _provenance_hashes(value: Any, *, depth: int = 0) -> Any:
    if depth > _MAX_DEPTH:
        raise ValueError("provenance exceeds maximum nesting depth")
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("provenance object keys must be strings")
            if key.casefold().endswith("sha256"):
                if isinstance(child, str) and _SHA256_RE.fullmatch(child):
                    result[key] = child.lower()
                continue
            nested = _provenance_hashes(child, depth=depth + 1)
            if nested not in ({}, []):
                result[key] = nested
        return result
    if isinstance(value, (list, tuple)):
        result = [_provenance_hashes(item, depth=depth + 1) for item in value]
        return [item for item in result if item not in ({}, [])]
    return {}


def readiness_evidence_from_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return the allowlisted, path-free evidence contained in *manifest*."""
    if not isinstance(manifest, Mapping):
        raise TypeError("readiness manifest must be an object")

    normalized: dict[str, Any] = {"schema_version": "publication_evidence/1"}
    for field in _EVIDENCE_FIELDS:
        if field in manifest:
            normalized[field] = _safe_value(redact_secrets(manifest[field]))

    project_id = manifest.get("project_id")
    if isinstance(project_id, str) and project_id.strip():
        normalized["project_id"] = _safe_value(redact_secrets(project_id.strip()))
    figure_id = manifest.get("figure_id")
    selected = manifest.get("selected_figure")
    if not (isinstance(figure_id, str) and figure_id.strip()) and isinstance(selected, Mapping):
        figure_id = selected.get("id")
    if isinstance(figure_id, str) and figure_id.strip():
        normalized["figure_id"] = _safe_value(redact_secrets(figure_id.strip()))

    provenance = manifest.get("provenance")
    if provenance is not None:
        if not isinstance(provenance, Mapping):
            raise TypeError("manifest provenance must be an object")
        hashes = _provenance_hashes(provenance)
        if hashes:
            normalized["provenance"] = hashes
        normalized["provenance_coverage"] = provenance_hash_coverage(provenance)
    return normalized


def readiness_evidence_from_verified_manifest(
    manifest: Mapping[str, Any],
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Normalize already-verified manifest bytes without reopening the JSON file."""

    evidence = readiness_evidence_from_manifest(manifest)
    if "artifact_status" in manifest or manifest.get("figures"):
        evidence["artifact_integrity"] = inspect_manifest_artifacts(manifest, manifest_path)
    return evidence


def load_readiness_manifest(path: str | Path) -> dict[str, Any]:
    """Load a bounded UTF-8 JSON manifest and normalize its evidence."""
    manifest_path = Path(path)
    size = manifest_path.stat().st_size
    if size > MAX_READINESS_MANIFEST_BYTES:
        raise ValueError("readiness manifest exceeds the maximum size")
    raw = manifest_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("readiness manifest must be UTF-8 JSON") from exc
    try:
        manifest = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"unsupported JSON constant: {value}")
            ),
        )
    except json.JSONDecodeError as exc:
        raise ValueError("readiness manifest must contain valid JSON") from exc
    if not isinstance(manifest, dict):
        raise ValueError("readiness manifest must contain a JSON object")
    return readiness_evidence_from_verified_manifest(manifest, manifest_path)
