"""Bounded, contained verification for producer-owned calculation evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping

from .adapters import select_adapters
from .durable_receipt import (
    DurableReceipt,
    opaque_artifact_id,
    opaque_claim_id,
    opaque_receipt_id,
)
from .project_paths import (
    normalize_project_relative_path,
    open_verified_project_input,
    project_path_has_symlink_component,
    resolve_project_input,
    snapshot_project_input,
)

SCHEMA_VERSION = "figops_calculation_evidence/2"
CALCULATION_ARTIFACT_SCHEMA_VERSION = "figops_calculation_artifact/1"
LEGACY_SELF_HASH_SCHEMA_VERSION = "figops_calculation_evidence/1"
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
            raise ValueError("custom calculation evidence display labels require assertion.display_kind='custom'")
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


def _decode_closed_json(raw_bytes: bytes, *, name: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_bytes.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"calculation evidence {name} must contain valid closed UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"calculation evidence {name} must be a JSON object")
    return payload


def _normalize_calculation_artifact(raw_bytes: bytes) -> dict[str, Any]:
    payload = _decode_closed_json(raw_bytes, name="calculation artifact")
    schema_version = payload.get("schema_version")
    if schema_version not in {CALCULATION_ARTIFACT_SCHEMA_VERSION, LEGACY_SELF_HASH_SCHEMA_VERSION}:
        raise ValueError(f"calculation artifact must use schema_version {CALCULATION_ARTIFACT_SCHEMA_VERSION!r}")
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
        field: _strict_number(binding.get(field), f"marker_binding.{field}") for field in ("x1", "x2")
    }
    return {
        "schema_version": CALCULATION_ARTIFACT_SCHEMA_VERSION,
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
    }


_DESCRIPTOR_FIELDS = {"artifact_id", "role", "path", "sha256"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CALCULATION_ROLES = {"result.source_data", "result.table", "result.evidence"}


def _normalize_descriptor(value: Any, name: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"calculation evidence requires {name}")
    _require_closed_object(value, _DESCRIPTOR_FIELDS, name)
    if set(value) != _DESCRIPTOR_FIELDS:
        raise ValueError(f"calculation evidence {name} must contain artifact_id, role, path, and sha256")
    sha256 = _bounded_string(value.get("sha256"), f"{name}.sha256", limit=64)
    if not _SHA256_RE.fullmatch(sha256):
        raise ValueError(f"calculation evidence {name}.sha256 must be a lowercase SHA-256")
    return {
        "artifact_id": _bounded_string(value.get("artifact_id"), f"{name}.artifact_id"),
        "role": _bounded_string(value.get("role"), f"{name}.role"),
        "path": normalize_project_relative_path(value.get("path"), purpose=f"calculation evidence {name}.path"),
        "sha256": sha256,
    }


def _normalize_descriptors(value: Any, name: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError(f"calculation evidence {name} must be an array")
    records = [_normalize_descriptor(item, f"{name}[{index}]") for index, item in enumerate(value)]
    ids = [item["artifact_id"] for item in records]
    if len(ids) != len(set(ids)):
        raise ValueError(f"calculation evidence {name} contains duplicate artifact IDs")
    return records


def _verify_descriptor(
    root: str | Path,
    descriptor: Mapping[str, str],
    *,
    evidence_ref: str,
    capture: bool = False,
) -> bytes | None:
    declared = descriptor["path"]
    if declared == evidence_ref:
        raise ValueError("calculation evidence may not use its own document as a declared artifact")
    if project_path_has_symlink_component(root, declared, purpose="calculation evidence lineage artifact"):
        raise ValueError("calculation evidence lineage path must not traverse a symlink, junction, or reparse point")
    snapshot = snapshot_project_input(root, declared, purpose="calculation evidence lineage artifact")
    with open_verified_project_input(
        root,
        declared,
        expected_snapshot=snapshot,
        purpose="calculation evidence lineage artifact",
    ) as handle:
        hasher = hashlib.sha256()
        captured = bytearray()
        while chunk := handle.read(1024 * 1024):
            hasher.update(chunk)
            if capture:
                captured.extend(chunk)
                if len(captured) > MAX_EVIDENCE_BYTES:
                    raise ValueError("calculation artifact exceeds the 1 MiB structured artifact limit")
    actual = hasher.hexdigest()
    if actual != descriptor["sha256"]:
        raise ValueError(f"calculation evidence declared hash does not match artifact {descriptor['artifact_id']!r}")
    return bytes(captured) if capture else None


def _receipt_artifact(descriptor: Mapping[str, str]) -> dict[str, str]:
    return {
        "artifact_id": opaque_artifact_id(descriptor["role"], descriptor["artifact_id"]),
        "role": descriptor["role"],
        "sha256": descriptor["sha256"],
    }


def _normalize_payload(raw_bytes: bytes, *, artifact_ref: str, root: str | Path) -> dict[str, Any]:
    payload = _decode_closed_json(raw_bytes, name="lineage document")
    if payload.get("schema_version") == LEGACY_SELF_HASH_SCHEMA_VERSION:
        raise ValueError(
            "legacy calculation evidence is unverified because it self-hashes the evidence document; "
            "declare a durable calculation artifact and complete producer lineage"
        )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"calculation evidence must use schema_version {SCHEMA_VERSION!r}")
    _require_closed_object(
        payload,
        {
            "schema_version",
            "figops_version",
            "run_id",
            "timestamp",
            "git_sha256",
            "environment_lock_sha256",
            "claim_ids",
            "calculation_artifact",
            "producer",
            "input_artifacts",
            "output_artifacts",
        },
        "lineage document",
    )
    producer = payload.get("producer")
    if not isinstance(producer, dict) or set(producer) != {"script", "config"}:
        raise ValueError("calculation evidence producer must contain script and config descriptors only")
    script = _normalize_descriptor(producer["script"], "producer.script")
    config = _normalize_descriptor(producer["config"], "producer.config")
    if not script["role"].startswith("script."):
        raise ValueError("calculation evidence producer.script role must be a script role")
    if config["role"] != "config":
        raise ValueError("calculation evidence producer.config role must be 'config'")
    calculation = _normalize_descriptor(payload.get("calculation_artifact"), "calculation_artifact")
    if calculation["role"] not in _CALCULATION_ROLES:
        raise ValueError("calculation artifact must have a durable source-data, table, or evidence role")
    inputs = _normalize_descriptors(payload.get("input_artifacts"), "input_artifacts")
    outputs = _normalize_descriptors(payload.get("output_artifacts"), "output_artifacts")
    bound_output = next((item for item in outputs if item["artifact_id"] == calculation["artifact_id"]), None)
    if bound_output != calculation:
        raise ValueError("calculation evidence output_artifacts must contain the exact calculation artifact binding")
    claim_ids = payload.get("claim_ids")
    if not isinstance(claim_ids, list) or not claim_ids:
        raise ValueError("calculation evidence requires at least one stable claim ID")
    normalized_claim_ids = [_bounded_string(value, "claim_ids[]") for value in claim_ids]
    if len(normalized_claim_ids) != len(set(normalized_claim_ids)):
        raise ValueError("calculation evidence claim_ids contains duplicates")

    all_descriptors = [script, config, *inputs, *outputs]
    artifact_ids = [item["artifact_id"] for item in all_descriptors]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("calculation evidence lineage artifact IDs must be globally unique")
    paths = [item["path"] for item in all_descriptors]
    if len(paths) != len(set(paths)):
        raise ValueError("calculation evidence lineage paths must be unique")
    resolved = [
        resolve_project_input(root, item["path"], purpose="calculation evidence lineage artifact")
        for item in all_descriptors
    ]
    select_adapters({}).prefetcher.ensure_local([str(path) for path in resolved])
    calculation_bytes: bytes | None = None
    for item in all_descriptors:
        captured = _verify_descriptor(
            root,
            item,
            evidence_ref=artifact_ref,
            capture=item["artifact_id"] == calculation["artifact_id"],
        )
        if captured is not None:
            calculation_bytes = captured
    if calculation_bytes is None:  # Defensive: exact output binding above makes this unreachable.
        raise ValueError("calculation evidence did not resolve its durable calculation artifact")
    calculation_payload = _normalize_calculation_artifact(calculation_bytes)
    if calculation_payload["evidence_id"] not in normalized_claim_ids:
        raise ValueError("calculation artifact evidence_id must be one of the declared stable claim IDs")

    receipt = DurableReceipt(
        figops_version=_bounded_string(payload.get("figops_version"), "figops_version"),
        run_id=opaque_receipt_id("run", _bounded_string(payload.get("run_id"), "run_id")),
        timestamp=_bounded_string(payload.get("timestamp"), "timestamp"),
        git_sha256=_bounded_string(payload.get("git_sha256"), "git_sha256", limit=64),
        config_sha256=config["sha256"],
        script_sha256=script["sha256"],
        environment_lock_sha256=_bounded_string(
            payload.get("environment_lock_sha256"), "environment_lock_sha256", limit=64
        ),
        durable_artifact=_receipt_artifact(calculation),
        input_artifacts=[_receipt_artifact(item) for item in inputs],
        output_artifacts=[_receipt_artifact(item) for item in outputs],
        claim_ids=[opaque_claim_id(claim_id) for claim_id in normalized_claim_ids],
    )
    return {
        **calculation_payload,
        "evidence_id": calculation_payload["evidence_id"],
        "claim_ids": normalized_claim_ids,
        "analysis_artifact_sha256": calculation["sha256"],
        "calculation_artifact_id": calculation["artifact_id"],
        "calculation_artifact_role": calculation["role"],
        "artifact_ref": artifact_ref,
        "calculation_artifact_ref": calculation["path"],
        "producer_lineage": {"script": script, "config": config},
        "input_artifacts": inputs,
        "output_artifacts": outputs,
        "durable_receipt": receipt.to_dict(),
        "durable_receipt_sha256": receipt.canonical_sha256(),
        "verification_status": "verified",
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
        record = _normalize_payload(raw_bytes, artifact_ref=normalized, root=root)
        evidence_id = record["evidence_id"]
        if evidence_id in seen_ids:
            raise ValueError("calculation evidence bundle contains a duplicate evidence_id")
        seen_ids.add(evidence_id)
        records.append(record)
    return records


def verify_calculation_evidence(root: str | Path, declared_path: str) -> dict[str, Any]:
    """Compatibility wrapper for one evidence artifact."""

    return verify_calculation_evidence_bundle(root, [declared_path])[0]
