"""Versioned, policy-neutral evidence-envelope validation."""
from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from typing import Any, NoReturn

from .evidence_artifact_section import ArtifactSectionError, validate_artifacts
from .evidence_semantics import validate_cross_evidence_consistency

EVIDENCE_VERSION = "2.0"
MAX_EVIDENCE_DEPTH = 16
MAX_EVIDENCE_ITEMS = 10_000
MAX_EVIDENCE_SERIALIZED_BYTES = 64 * 1024

_PRODUCER_STATUSES = {"passed", "warning", "failed", "skipped"}
_FAILURE_STAGES = set("CONFIG VALIDATE CONTRACT EXECUTE PLOT EXPORT TIMEOUT TRANSFER LEGACY".split())
_SUMMARY_STATUSES = {"passed", "warning", "failed", "skipped"}
_FINDING_SEVERITIES = {"hard", "advisory", "informational"}
_FINDING_OUTCOMES = {"blocked", "needs_revision", "informational"}
_PROVENANCE_HASH_FIELDS = (
    "input_sha256",
    "config_sha256",
    "script_sha256",
    "environment_sha256",
    "output_sha256",
)
_AVAILABILITY = {"available", "unavailable", "not_applicable", "unknown"}
_POLICY_KEYS = {"passed", "severity", "outcome", "hard", "blocked"}
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class EvidenceContractError(ValueError):
    """Stable public error raised for an invalid evidence envelope."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(message)


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise EvidenceContractError(code, path, f"{path} {detail}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("TYPE_MAPPING", path, "must be a mapping")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("TYPE_LIST", path, "must be a list")
    return value


def _closed(item: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(item) - allowed)
    if unknown:
        _fail("UNKNOWN_FIELD", f"{path}.{unknown[0]}", "is not allowed")


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("NONEMPTY_STRING", path, "must be a non-empty string")
    return value


def _sha256(value: Any, path: str) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail("SHA256_INVALID", path, "must be a 64-character hexadecimal SHA-256")


def _check_bounds(root: Mapping[str, Any]) -> None:
    count = 0
    ancestors: set[int] = set()

    def visit(value: Any, path: str, depth: int) -> None:
        nonlocal count
        if depth > MAX_EVIDENCE_DEPTH:
            _fail("MAX_DEPTH", path, f"exceeds maximum depth {MAX_EVIDENCE_DEPTH}")
        if isinstance(value, (Mapping, list)):
            identity = id(value)
            if identity in ancestors:
                _fail("CYCLIC_VALUE", path, "must not contain a cycle")
            ancestors.add(identity)
            values = value.values() if isinstance(value, Mapping) else value
            if isinstance(value, Mapping):
                for key in value:
                    if not isinstance(key, str):
                        _fail("KEY_TYPE", path, "must use string keys")
            for index, child in enumerate(values):
                count += 1
                if count > MAX_EVIDENCE_ITEMS:
                    _fail("MAX_ITEMS", path, f"exceeds maximum item count {MAX_EVIDENCE_ITEMS}")
                visit(child, f"{path}[{index}]", depth + 1)
            ancestors.remove(identity)

    visit(root, "evidence", 0)
    try:
        encoded = json.dumps(
            root,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        _fail("JSON_INVALID", "evidence", f"must be finite JSON: {exc}")
    if len(encoded) > MAX_EVIDENCE_SERIALIZED_BYTES:
        _fail(
            "MAX_BYTES",
            "evidence",
            f"exceeds maximum serialized size {MAX_EVIDENCE_SERIALIZED_BYTES}",
        )


def _reject_policy_fields(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in _POLICY_KEYS:
                _fail("POLICY_FIELD_FORBIDDEN", child_path, "is policy-owned")
            _reject_policy_fields(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_policy_fields(child, f"{path}[{index}]")


def _measurement_id(item: Mapping[str, Any], path: str) -> str:
    has_id = "id" in item
    has_metric_id = "metric_id" in item
    if has_id and has_metric_id:
        _fail("METRIC_ID_AMBIGUOUS", path, "must not contain both id and metric_id")
    key = "id" if has_id else "metric_id"
    return _nonempty_string(item.get(key), f"{path}.{key}")


def _validate_measurements(value: Any) -> set[str]:
    measurements = _list(value, "evidence.measurements")
    identifiers: set[str] = set()
    allowed = {"id", "metric_id", "availability", "value", "unit", "scope", "reason"}
    for index, raw in enumerate(measurements):
        path = f"evidence.measurements[{index}]"
        item = _mapping(raw, path)
        _closed(item, allowed, path)
        identifier = _measurement_id(item, path)
        if identifier in identifiers:
            _fail("METRIC_ID_DUPLICATE", path, f"duplicates measurement {identifier!r}")
        identifiers.add(identifier)
        availability = item.get("availability")
        if availability not in _AVAILABILITY:
            _fail("AVAILABILITY_INVALID", f"{path}.availability", "has an invalid value")
        if availability == "available":
            if "value" not in item:
                _fail("VALUE_REQUIRED", f"{path}.value", "is required when available")
        else:
            if "value" in item:
                _fail("VALUE_FORBIDDEN", f"{path}.value", "is forbidden when unavailable")
            _nonempty_string(item.get("reason"), f"{path}.reason")

        _reject_policy_fields(item, path)
    return identifiers


def _validate_policy_projections(value: Any, identifiers: set[str]) -> None:
    policies = _list(value, "evidence.policy_projections")
    allowed = {"id", "version", "measurement_refs", "resolved", "findings", "status"}
    for index, raw in enumerate(policies):
        path = f"evidence.policy_projections[{index}]"
        item = _mapping(raw, path)
        _closed(item, allowed, path)
        _nonempty_string(item.get("id"), f"{path}.id")
        _nonempty_string(item.get("version"), f"{path}.version")
        refs = _list(item.get("measurement_refs"), f"{path}.measurement_refs")
        seen: set[str] = set()
        for ref_index, ref in enumerate(refs):
            ref_path = f"{path}.measurement_refs[{ref_index}]"
            ref = _nonempty_string(ref, ref_path)
            if ref not in identifiers:
                _fail("METRIC_REF_UNKNOWN", ref_path, f"references unknown measurement {ref!r}")
            if ref in seen:
                _fail("METRIC_REF_DUPLICATE", ref_path, f"duplicates measurement {ref!r}")
            seen.add(ref)
        if "resolved" in item:
            resolved = _mapping(item["resolved"], f"{path}.resolved")
            for name, raw_resolution in resolved.items():
                resolution_path = f"{path}.resolved.{name}"
                resolution = _mapping(raw_resolution, resolution_path)
                _closed(resolution, {"value", "source", "reason"}, resolution_path)
                if "value" not in resolution:
                    _fail("RESOLVED_VALUE_REQUIRED", f"{resolution_path}.value", "is required")
                _nonempty_string(resolution.get("source"), f"{resolution_path}.source")
        if "findings" in item:
            findings = _list(item["findings"], f"{path}.findings")
            for finding_index, raw_finding in enumerate(findings):
                finding_path = f"{path}.findings[{finding_index}]"
                finding = _mapping(raw_finding, finding_path)
                _closed(
                    finding,
                    {"code", "metric_id", "severity", "outcome", "message"},
                    finding_path,
                )
                _nonempty_string(finding.get("code"), f"{finding_path}.code")
                metric_id = _nonempty_string(finding.get("metric_id"), f"{finding_path}.metric_id")
                _nonempty_string(finding.get("message"), f"{finding_path}.message")
                severity = finding.get("severity")
                if severity not in _FINDING_SEVERITIES:
                    _fail(
                        "FINDING_SEVERITY_INVALID",
                        f"{finding_path}.severity",
                        "has an invalid value",
                    )
                outcome = finding.get("outcome")
                if outcome not in _FINDING_OUTCOMES:
                    _fail(
                        "FINDING_OUTCOME_INVALID",
                        f"{finding_path}.outcome",
                        "has an invalid value",
                    )
                if metric_id not in seen:
                    _fail(
                        "METRIC_REF_UNDECLARED",
                        f"{finding_path}.metric_id",
                        "must be declared in measurement_refs",
                    )


def _validate_artifacts(value: Any) -> tuple[str | None, bool]:
    try:
        return validate_artifacts(value)
    except ArtifactSectionError as exc:
        _fail(exc.code, exc.path, exc.detail)


def _validate_provenance(value: Any, *, require_hashes: bool) -> None:
    provenance = _mapping(value, "evidence.provenance")
    hash_fields = set(_PROVENANCE_HASH_FIELDS)
    _closed(
        provenance,
        hash_fields | {"status", "reason", "unavailable_fields"},
        "evidence.provenance",
    )
    if require_hashes:
        for field in _PROVENANCE_HASH_FIELDS:
            if field not in provenance:
                _fail(
                    "PROVENANCE_HASH_REQUIRED",
                    f"evidence.provenance.{field}",
                    "is required",
                )
    status = provenance.get("status")
    if status not in _PRODUCER_STATUSES | {"unavailable"}:
        _fail("PROVENANCE_STATUS_INVALID", "evidence.provenance.status", "has an invalid value")
    for field in hash_fields.intersection(provenance):
        _sha256(provenance[field], f"evidence.provenance.{field}")
    unavailable = _list(
        provenance.get("unavailable_fields"),
        "evidence.provenance.unavailable_fields",
    )
    for index, field in enumerate(unavailable):
        if not isinstance(field, str) or field not in hash_fields:
            _fail(
                "PROVENANCE_FIELD_UNKNOWN",
                f"evidence.provenance.unavailable_fields[{index}]",
                "is unknown",
            )
    missing = [field for field in _PROVENANCE_HASH_FIELDS if field not in provenance]
    if status == "passed":
        for field in missing:
            _fail(
                "PROVENANCE_HASH_REQUIRED",
                f"evidence.provenance.{field}",
                "is required",
            )
    if len(unavailable) != len(set(unavailable)) or set(unavailable) != set(missing):
        _fail(
            "PROVENANCE_UNAVAILABLE_MISMATCH",
            "evidence.provenance.unavailable_fields",
            "must list each and only missing hash field exactly once",
        )
    if status in {"skipped", "unavailable"}:
        _nonempty_string(provenance.get("reason"), "evidence.provenance.reason")


def _validate_resolved_policy(value: Any) -> None:
    if value is None:
        return
    policy = _mapping(value, "evidence.resolved_policy")
    _closed(policy, {"id", "version", "source", "parameters"}, "evidence.resolved_policy")
    _nonempty_string(policy.get("id"), "evidence.resolved_policy.id")
    _nonempty_string(policy.get("version"), "evidence.resolved_policy.version")
    _nonempty_string(policy.get("source"), "evidence.resolved_policy.source")
    if "parameters" in policy:
        _mapping(policy["parameters"], "evidence.resolved_policy.parameters")


def _validate_summary(value: Any, path: str) -> None:
    summary = _mapping(value, path)
    _closed(summary, {"status", "checks", "reason"}, path)
    status = summary.get("status")
    if status not in _SUMMARY_STATUSES:
        _fail("SUMMARY_STATUS_INVALID", f"{path}.status", "has an invalid value")
    checks = _list(summary.get("checks"), f"{path}.checks")
    check_statuses: list[str] = []
    for index, raw in enumerate(checks):
        check_path = f"{path}.checks[{index}]"
        check = _mapping(raw, check_path)
        _closed(check, {"id", "status", "message"}, check_path)
        _nonempty_string(check.get("id"), f"{check_path}.id")
        _nonempty_string(check.get("message"), f"{check_path}.message")
        check_status = check.get("status")
        if check_status not in _SUMMARY_STATUSES:
            _fail(
                "SUMMARY_CHECK_STATUS_INVALID",
                f"{check_path}.status",
                "has an invalid value",
            )
        check_statuses.append(check_status)
    if status == "skipped":
        _nonempty_string(summary.get("reason"), f"{path}.reason")
    consistent = {
        "passed": bool(check_statuses) and set(check_statuses) <= {"passed", "skipped"},
        "warning": "warning" in check_statuses and "failed" not in check_statuses,
        "failed": "failed" in check_statuses,
        "skipped": not check_statuses,
    }[status]
    if not consistent:
        _fail(
            "SUMMARY_AGGREGATE_CONFLICT",
            f"{path}.status",
            "is inconsistent with check statuses",
        )


def _validate_mutation_ledger(value: Any) -> None:
    if value is None:
        return
    ledger = _list(value, "evidence.mutation_ledger")
    required = {
        "mutation_id",
        "transform",
        "mode",
        "before",
        "after",
        "policy_id",
        "reason",
    }
    identifiers: set[str] = set()
    for index, raw in enumerate(ledger):
        path = f"evidence.mutation_ledger[{index}]"
        item = _mapping(raw, path)
        _closed(item, required, path)
        for field in sorted(required):
            if field not in item:
                _fail("MUTATION_FIELD_REQUIRED", f"{path}.{field}", "is required")
        identifier = _nonempty_string(item.get("mutation_id"), f"{path}.mutation_id")
        if identifier in identifiers:
            _fail("MUTATION_ID_DUPLICATE", f"{path}.mutation_id", "must be unique")
        identifiers.add(identifier)
        for field in ("transform", "mode", "policy_id", "reason"):
            _nonempty_string(item.get(field), f"{path}.{field}")


def _validate_exact(value: Any) -> None:
    if value is None:
        return
    exact = _mapping(value, "evidence.exact_reproducibility")
    _closed(
        exact,
        {
            "status",
            "algorithm",
            "reference_sha256",
            "candidate_sha256",
            "artifact_sha256",
            "checked",
            "matched",
            "reason",
        },
        "evidence.exact_reproducibility",
    )
    for field in ("reference_sha256", "candidate_sha256", "artifact_sha256"):
        if field in exact:
            _sha256(exact[field], f"evidence.exact_reproducibility.{field}")
    modern = (
        exact.get("status") in {"same", "different", "unavailable", "skipped"}
        or "reference_sha256" in exact
        or "candidate_sha256" in exact
    )
    if modern:
        if exact.get("status") not in {"same", "different", "unavailable", "skipped"}:
            _fail(
                "EXACT_STATUS_INVALID",
                "evidence.exact_reproducibility.status",
                "has an invalid value",
            )
        if exact.get("status") in {"same", "different"}:
            _nonempty_string(exact.get("algorithm"), "evidence.exact_reproducibility.algorithm")
            for field in ("reference_sha256", "candidate_sha256"):
                if field not in exact:
                    _fail("EXACT_HASH_REQUIRED", f"evidence.exact_reproducibility.{field}", "is required")
        else:
            _nonempty_string(exact.get("reason"), "evidence.exact_reproducibility.reason")


def _validate_visual(value: Any) -> None:
    if value is None:
        return
    visual = _mapping(value, "evidence.visual_comparison")
    _closed(
        visual,
        {"status", "algorithm", "reference_artifact", "candidate_artifact", "metrics", "reason"},
        "evidence.visual_comparison",
    )
    status = visual.get("status")
    if status not in {"available", "unavailable", "skipped"}:
        _fail("VISUAL_STATUS_INVALID", "evidence.visual_comparison.status", "has an invalid value")
    if status == "available":
        algorithm = _mapping(visual.get("algorithm"), "evidence.visual_comparison.algorithm")
        _closed(algorithm, {"name", "version"}, "evidence.visual_comparison.algorithm")
        _nonempty_string(algorithm.get("name"), "evidence.visual_comparison.algorithm.name")
        _nonempty_string(algorithm.get("version"), "evidence.visual_comparison.algorithm.version")
        for field in ("reference_artifact", "candidate_artifact"):
            _nonempty_string(visual.get(field), f"evidence.visual_comparison.{field}")
        metrics = _mapping(visual.get("metrics"), "evidence.visual_comparison.metrics")
        _reject_policy_fields(metrics, "evidence.visual_comparison.metrics")
    else:
        _nonempty_string(visual.get("reason"), "evidence.visual_comparison.reason")


def validate_evidence_envelope(envelope: Any) -> None:
    """Validate an evidence v2 envelope or raise :class:`EvidenceContractError`."""
    root = _mapping(envelope, "evidence")
    _check_bounds(root)
    _closed(
        root,
        {
            "version",
            "producer",
            "measurements",
            "policy_projections",
            "artifacts",
            "provenance",
            "resolved_policy",
            "mutation_ledger",
            "exact_reproducibility",
            "visual_comparison",
            "data_contract_summary",
            "calculation_summary",
        },
        "evidence",
    )
    if root.get("version") != EVIDENCE_VERSION:
        _fail("VERSION_UNSUPPORTED", "evidence.version", f"must be {EVIDENCE_VERSION!r}")

    producer = _mapping(root.get("producer"), "evidence.producer")
    _closed(producer, {"status", "kind", "version", "failure_stage", "reason"}, "evidence.producer")
    status = producer.get("status")
    if status not in _PRODUCER_STATUSES:
        _fail("PRODUCER_STATUS_INVALID", "evidence.producer.status", "has an invalid value")
    for field in ("kind", "version"):
        _nonempty_string(producer.get(field), f"evidence.producer.{field}")
    failure_stage = producer.get("failure_stage")
    if failure_stage is not None and status != "failed":
        _fail("FAILURE_STAGE_CONFLICT", "evidence.producer.failure_stage", "requires failed status")
    if status == "failed":
        _nonempty_string(failure_stage, "evidence.producer.failure_stage")
        if failure_stage not in _FAILURE_STAGES:
            _fail(
                "FAILURE_STAGE_INVALID",
                "evidence.producer.failure_stage",
                "has an invalid value",
            )

    for field in ("data_contract_summary", "calculation_summary"):
        if field not in root:
            _fail("FIELD_REQUIRED", f"evidence.{field}", "is required")
        _validate_summary(root[field], f"evidence.{field}")

    identifiers = _validate_measurements(root.get("measurements"))
    _validate_policy_projections(root.get("policy_projections"), identifiers)
    artifact_status, artifacts_exist = _validate_artifacts(root.get("artifacts"))
    allowed_artifact_states = {
        "passed": {"passed"},
        "warning": {"passed", "warning", "unavailable"},
        "failed": {"failed", "unavailable"},
        "skipped": {"skipped", "unavailable"},
    }
    if artifact_status is not None and artifact_status not in allowed_artifact_states[status]:
        _fail(
            "ARTIFACT_PRODUCER_CONFLICT",
            "evidence.artifacts.status",
            f"is inconsistent with producer status {status!r}",
        )
    _validate_provenance(
        root.get("provenance"),
        require_hashes=artifact_status in {"passed", "warning"} and artifacts_exist,
    )
    _validate_resolved_policy(root.get("resolved_policy"))
    _validate_mutation_ledger(root.get("mutation_ledger"))
    if "exact_reproducibility" not in root:
        _fail("FIELD_REQUIRED", "evidence.exact_reproducibility", "is required")
    if "visual_comparison" not in root:
        _fail("FIELD_REQUIRED", "evidence.visual_comparison", "is required")
    _validate_exact(root["exact_reproducibility"])
    _validate_visual(root["visual_comparison"])
    validate_cross_evidence_consistency(root, _fail)


def _canonicalize_measurement_ids(envelope: dict[str, Any]) -> None:
    for measurement in envelope.get("measurements", []):
        if isinstance(measurement, dict) and "metric_id" in measurement and "id" not in measurement:
            measurement["id"] = measurement.pop("metric_id")


def normalize_evidence_envelope(envelope: Any, *, allow_legacy: bool = False) -> dict[str, Any]:
    """Return a validated JSON-safe deep copy, optionally adapting legacy evidence."""
    if not isinstance(envelope, Mapping):
        _fail("TYPE_MAPPING", "evidence", "must be a mapping")
    if envelope.get("version") != EVIDENCE_VERSION:
        if not allow_legacy:
            _fail("LEGACY_DISABLED", "evidence.version", "requires allow_legacy=True")
        normalized = adapt_legacy_evidence(envelope)
    else:
        normalized = copy.deepcopy(dict(envelope))
        _canonicalize_measurement_ids(normalized)
    validate_evidence_envelope(normalized)
    return normalized


def _legacy_status(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("status")
    return str(value).strip().lower() if value is not None else ""


def _legacy_unavailable(reason: str) -> dict[str, Any]:
    return {"status": "skipped", "reason": reason, "entries": []}


def adapt_legacy_evidence(legacy: Any) -> dict[str, Any]:
    """Convert legacy evidence without inventing availability, hashes, or pass states."""
    source = _mapping(legacy, "legacy evidence")
    geometry = source.get("geometry_checks", source.get("geometry", []))
    if isinstance(geometry, Mapping):
        geometry = [
            dict(value, id=key) if isinstance(value, Mapping) else {"id": key, "value": value}
            for key, value in geometry.items()
        ]
    if geometry is None:
        geometry = []
    if not isinstance(geometry, list):
        _fail(
            "LEGACY_GEOMETRY_INVALID",
            "legacy evidence.geometry_checks",
            "must be a mapping or list",
        )

    measurements: list[dict[str, Any]] = []
    for index, raw in enumerate(geometry):
        check = dict(raw) if isinstance(raw, Mapping) else {"value": raw}
        identifier = str(check.pop("id", check.pop("metric_id", check.pop("name", f"geometry.{index}"))))
        for key in _POLICY_KEYS:
            check.pop(key, None)
        availability = check.pop("availability", None)
        if availability not in _AVAILABILITY:
            availability = "available" if "value" in check else "unavailable"
        measurement = {"id": identifier, "availability": availability}
        for key in ("value", "unit", "scope", "reason"):
            if key in check:
                measurement[key] = check[key]
        if availability != "available":
            measurement.pop("value", None)
            measurement.setdefault("reason", "legacy evidence did not record this measurement")
        measurements.append(measurement)

    legacy_status = _legacy_status(source.get("producer", source.get("status")))
    producer_status = {
        "ok": "warning",
        "passed": "warning",
        "warning": "warning",
        "failed": "failed",
        "error": "failed",
        "skipped": "skipped",
        "unavailable": "skipped",
    }.get(legacy_status, "warning")
    producer: dict[str, Any] = {
        "status": producer_status,
        "kind": "legacy-adapter",
        "version": EVIDENCE_VERSION,
        "reason": "legacy evidence lacks mandatory v2 completeness fields",
    }
    if producer_status == "failed":
        failure_stage = source.get("failure_stage")
        producer["failure_stage"] = (str(failure_stage).strip() if failure_stage is not None else "LEGACY") or "LEGACY"

    missing_artifact_reason = "legacy evidence did not include verified artifact entries"
    if producer_status == "skipped":
        artifacts = _legacy_unavailable(missing_artifact_reason)
    else:
        artifacts = {
            "status": "unavailable",
            "reason": missing_artifact_reason,
            "entries": [],
        }
    legacy_artifacts = source.get("artifacts")
    if isinstance(legacy_artifacts, Mapping) and _legacy_status(legacy_artifacts) in {"failed", "error"}:
        reason = legacy_artifacts.get("reason")
        artifacts = {
            "status": "failed",
            "reason": (
                reason.strip()
                if isinstance(reason, str) and reason.strip()
                else "legacy artifact evidence reported failure"
            ),
            "entries": [],
        }
    legacy_provenance = source.get("provenance")
    if isinstance(legacy_provenance, Mapping):
        provenance_status = _legacy_status(legacy_provenance)
        if provenance_status == "error":
            provenance_status = "failed"
        if provenance_status not in {
            "passed",
            "warning",
            "failed",
            "skipped",
            "unavailable",
        }:
            provenance_status = "warning"
        raw_reason = legacy_provenance.get("reason")
        provenance = {
            "status": provenance_status,
            "reason": (
                raw_reason.strip()
                if isinstance(raw_reason, str) and raw_reason.strip()
                else "legacy evidence did not include complete provenance hashes"
            ),
        }
        for field in _PROVENANCE_HASH_FIELDS:
            value = legacy_provenance.get(field)
            if isinstance(value, str) and _SHA256.fullmatch(value):
                provenance[field] = copy.deepcopy(legacy_provenance[field])
        unavailable = [field for field in _PROVENANCE_HASH_FIELDS if field not in provenance]
        if provenance_status == "passed" and unavailable:
            provenance["status"] = "warning"
        provenance["unavailable_fields"] = unavailable
    else:
        provenance = {
            "status": "skipped",
            "reason": "legacy evidence did not include complete provenance hashes",
            "unavailable_fields": list(_PROVENANCE_HASH_FIELDS),
        }
    baseline = source.get("baseline_comparison")
    result = {
        "version": EVIDENCE_VERSION,
        "producer": producer,
        "measurements": measurements,
        "policy_projections": [],
        "artifacts": artifacts,
        "provenance": provenance,
        "data_contract_summary": {
            "status": "skipped",
            "checks": [],
            "reason": "legacy evidence did not include a normalized data-contract summary",
        },
        "calculation_summary": {
            "status": "skipped",
            "checks": [],
            "reason": "legacy evidence did not include a normalized calculation summary",
        },
        "exact_reproducibility": (copy.deepcopy(baseline) if isinstance(baseline, Mapping) else None),
        "visual_comparison": None,
    }
    validate_evidence_envelope(result)
    return result
