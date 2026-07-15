"""Bounded, contained verification for producer-owned calculation evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from .adapters import select_adapters
from .project_paths import (
    normalize_project_relative_path,
    open_verified_project_input,
    project_path_has_symlink_component,
    resolve_project_input,
    snapshot_project_input,
)

SCHEMA_VERSION = "figops_calculation_evidence/1"
MAX_EVIDENCE_BYTES = 1024 * 1024
MAX_EVIDENCE_FILES = 32
MAX_EVIDENCE_STRING_LENGTH = 256


def _require_closed_object(payload: dict[str, Any], allowed: set[str], name: str) -> None:
    if set(payload) - allowed:
        raise ValueError(f"calculation evidence {name} contains unsupported fields")


def _bounded_string(value: Any, name: str, *, limit: int = MAX_EVIDENCE_STRING_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"calculation evidence requires a non-empty {name}")
    if len(value) > limit:
        raise ValueError(f"calculation evidence {name} exceeds {limit} characters")
    return value


def _strict_number(value: Any, name: str, *, probability: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"calculation evidence {name} must be a JSON number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"calculation evidence {name} must be finite")
    if probability and not 0.0 <= number <= 1.0:
        raise ValueError(f"calculation evidence {name} must be between 0 and 1")
    return number


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("calculation evidence JSON contains duplicate object keys")
        result[key] = value
    return result


_P_LABEL_RE = re.compile(r"^p(<=|<|=)([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)$", re.IGNORECASE)
_STAR_LABEL_RE = re.compile(r"^\*{1,4}$")


def _validate_display_semantics(
    display_label: str,
    *,
    operator: str,
    threshold: float,
    p_value: float,
    star_thresholds: Any,
    display_kind: Any,
) -> tuple[str, dict[str, float] | None]:
    if display_kind is not None and display_kind not in {"exact", "threshold", "stars", "custom"}:
        raise ValueError("calculation evidence assertion.display_kind is unsupported")
    compact = "".join(display_label.split()).replace("≤", "<=").replace("＜", "<").replace("＝", "=")
    match = _P_LABEL_RE.fullmatch(compact)
    if match:
        label_operator, raw_value = match.groups()
        label_value = float(raw_value)
        if not math.isfinite(label_value) or not 0.0 <= label_value <= 1.0:
            raise ValueError("calculation evidence assertion.display_label contains an invalid probability")
        if label_operator == "=":
            if display_kind not in (None, "exact"):
                raise ValueError("calculation evidence assertion.display_kind contradicts display_label")
            if label_value != p_value:
                raise ValueError("calculation evidence assertion.display_label contradicts result.p_value")
            resolved_kind = "exact"
        else:
            if display_kind not in (None, "threshold"):
                raise ValueError("calculation evidence assertion.display_kind contradicts display_label")
            expected_operator = {"lt": "<", "le": "<=", "eq": "="}[operator]
            if label_operator != expected_operator or label_value != threshold:
                raise ValueError("calculation evidence assertion.display_label contradicts its structured assertion")
            resolved_kind = "threshold"
        if star_thresholds not in (None, {}):
            raise ValueError("calculation evidence star_thresholds is only valid for a star display label")
        return resolved_kind, None

    if compact and set(compact) == {"*"} and not _STAR_LABEL_RE.fullmatch(compact):
        raise ValueError("calculation evidence star display supports one to four explicitly mapped stars")
    if not _STAR_LABEL_RE.fullmatch(compact):
        if display_kind != "custom" or star_thresholds not in (None, {}):
            raise ValueError(
                "custom calculation evidence display labels require assertion.display_kind='custom'"
            )
        return "custom", None
    if display_kind not in (None, "stars"):
        raise ValueError("calculation evidence assertion.display_kind contradicts display_label")
    if operator not in {"lt", "le"} or not isinstance(star_thresholds, dict):
        raise ValueError("calculation evidence star display requires an explicit threshold mapping")
    _require_closed_object(star_thresholds, {"*", "**", "***", "****"}, "assertion.star_thresholds")
    normalized: dict[str, float] = {}
    for symbol, value in star_thresholds.items():
        normalized[symbol] = _strict_number(value, f"assertion.star_thresholds.{symbol}", probability=True)
    if compact not in normalized or normalized[compact] != threshold:
        raise ValueError("calculation evidence star display does not map exactly to its assertion threshold")
    return "stars", normalized


def _normalize_payload(raw_bytes: bytes, *, artifact_ref: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"calculation evidence must contain valid closed UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"calculation evidence must use schema_version {SCHEMA_VERSION!r}")
    _require_closed_object(
        payload,
        {
            "schema_version",
            "evidence_id",
            "producer",
            "test_metadata",
            "result",
            "assertion",
            "marker_binding",
        },
        "document",
    )
    evidence_id = _bounded_string(payload.get("evidence_id"), "evidence_id")
    producer = _bounded_string(payload.get("producer"), "producer")

    metadata = payload.get("test_metadata")
    if not isinstance(metadata, dict):
        raise ValueError("calculation evidence requires test_metadata")
    _require_closed_object(metadata, {"test_name", "model"}, "test_metadata")
    test_name = _bounded_string(metadata.get("test_name"), "test_metadata.test_name")
    model = _bounded_string(metadata.get("model"), "test_metadata.model")

    result = payload.get("result")
    if not isinstance(result, dict) or result.get("status") != "passed":
        raise ValueError("calculation evidence result.status must be 'passed'")
    _require_closed_object(result, {"status", "p_value"}, "result")
    p_value = _strict_number(result.get("p_value"), "result.p_value", probability=True)

    assertion = payload.get("assertion")
    if not isinstance(assertion, dict) or assertion.get("metric") != "p_value":
        raise ValueError("calculation evidence requires a p_value assertion")
    _require_closed_object(
        assertion,
        {"metric", "operator", "threshold", "display_label", "display_kind", "star_thresholds"},
        "assertion",
    )
    operator = assertion.get("operator")
    if operator not in {"lt", "le", "eq"}:
        raise ValueError("calculation evidence assertion.operator must be one of: lt, le, eq")
    threshold = _strict_number(assertion.get("threshold"), "assertion.threshold", probability=True)
    display_label = _bounded_string(assertion.get("display_label"), "assertion.display_label", limit=128)
    satisfied = {
        "lt": p_value < threshold,
        "le": p_value <= threshold,
        "eq": p_value == threshold,
    }[operator]
    if not satisfied:
        raise ValueError("calculation evidence p_value does not satisfy its declared assertion")
    display_kind, star_thresholds = _validate_display_semantics(
        display_label,
        operator=operator,
        threshold=threshold,
        p_value=p_value,
        star_thresholds=assertion.get("star_thresholds"),
        display_kind=assertion.get("display_kind"),
    )

    binding = payload.get("marker_binding")
    if not isinstance(binding, dict):
        raise ValueError("calculation evidence requires marker_binding")
    _require_closed_object(binding, {"x1", "x2"}, "marker_binding")
    normalized_binding = {
        field: _strict_number(binding.get(field), f"marker_binding.{field}")
        for field in ("x1", "x2")
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "producer": producer,
        "test_metadata": {"test_name": test_name, "model": model},
        "result": {"status": "passed", "p_value": p_value},
        "assertion": {
            "metric": "p_value",
            "operator": operator,
            "threshold": threshold,
            "display_label": display_label,
            "display_kind": display_kind,
            **({"star_thresholds": star_thresholds} if star_thresholds is not None else {}),
        },
        "marker_binding": normalized_binding,
        "analysis_artifact_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "artifact_ref": artifact_ref,
    }


def verify_calculation_evidence_bundle(
    root: str | Path,
    declared_paths: list[str] | tuple[str, ...],
) -> list[dict[str, Any]]:
    """Verify up to 32 evidence inputs with one trusted prefetch and one open each."""

    if not isinstance(declared_paths, (list, tuple)) or not declared_paths:
        return []
    if len(declared_paths) > MAX_EVIDENCE_FILES:
        raise ValueError(f"calculation evidence bundle exceeds {MAX_EVIDENCE_FILES} files")

    canonical: list[str] = []
    resolved_paths: list[Path] = []
    for declared_path in declared_paths:
        normalized = normalize_project_relative_path(
            declared_path,
            purpose="calculation evidence artifact",
        )
        if normalized in canonical:
            continue
        if project_path_has_symlink_component(root, normalized, purpose="calculation evidence artifact"):
            raise ValueError("calculation evidence path must not traverse a symlink, junction, or reparse point")
        resolved = resolve_project_input(root, normalized, purpose="calculation evidence artifact")
        canonical.append(normalized)
        resolved_paths.append(resolved)

    # Adapter selection is launcher/server owned. No public argument can widen it.
    prefetcher = select_adapters({}).prefetcher
    prefetcher.ensure_local([str(path) for path in resolved_paths])

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    total_bytes = 0
    for normalized in canonical:
        if project_path_has_symlink_component(root, normalized, purpose="calculation evidence artifact"):
            raise ValueError("calculation evidence path changed to a symlink, junction, or reparse point")
        snapshot = snapshot_project_input(root, normalized, purpose="calculation evidence artifact")
        if project_path_has_symlink_component(root, normalized, purpose="calculation evidence artifact"):
            raise ValueError("calculation evidence path changed to a symlink, junction, or reparse point")
        remaining = MAX_EVIDENCE_BYTES - total_bytes
        with open_verified_project_input(
            root,
            normalized,
            expected_snapshot=snapshot,
            purpose="calculation evidence artifact",
        ) as handle:
            raw_bytes = handle.read(remaining + 1)
        total_bytes += len(raw_bytes)
        if total_bytes > MAX_EVIDENCE_BYTES:
            raise ValueError("calculation evidence bundle exceeds the 1 MiB evidence limit")
        record = _normalize_payload(raw_bytes, artifact_ref=normalized)
        evidence_id = record["evidence_id"]
        if evidence_id in seen_ids:
            raise ValueError("calculation evidence bundle contains a duplicate evidence_id")
        seen_ids.add(evidence_id)
        records.append(record)
    return records


def verify_calculation_evidence(root: str | Path, declared_path: str) -> dict[str, Any]:
    """Compatibility wrapper for one evidence artifact."""

    return verify_calculation_evidence_bundle(root, [declared_path])[0]
