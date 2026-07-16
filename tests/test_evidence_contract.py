from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from hub_core.evidence_contract import (
    EVIDENCE_VERSION,
    MAX_EVIDENCE_DEPTH,
    MAX_EVIDENCE_ITEMS,
    MAX_EVIDENCE_SERIALIZED_BYTES,
    EvidenceContractError,
    adapt_legacy_evidence,
    normalize_evidence_envelope,
    validate_evidence_envelope,
)

_PROVENANCE_HASH_FIELDS = (
    "input_sha256",
    "config_sha256",
    "script_sha256",
    "environment_sha256",
    "output_sha256",
)


def _minimal_envelope() -> dict[str, Any]:
    return {
        "version": EVIDENCE_VERSION,
        "producer": {
            "status": "warning",
            "kind": "test-render",
            "version": "1.0",
        },
        "measurements": [],
        "policy_projections": [],
        "artifacts": {
            "status": "unavailable",
            "reason": "no artifact was produced by this warning envelope",
            "entries": [],
        },
        "provenance": {
            "status": "skipped",
            "reason": "this warning fixture did not produce an artifact",
            "unavailable_fields": list(_PROVENANCE_HASH_FIELDS),
        },
        "data_contract_summary": {
            "status": "skipped",
            "checks": [],
            "reason": "no data contract was selected",
        },
        "calculation_summary": {
            "status": "skipped",
            "checks": [],
            "reason": "no calculation checks were selected",
        },
        "exact_reproducibility": None,
        "visual_comparison": None,
    }


def _available_artifact() -> dict[str, Any]:
    return {
        "logical_role": "primary",
        "relative_path": "figures/figure.png",
        "media_type": "image/png",
        "byte_size": 1_024,
        "sha256": "a" * 64,
        "width": 640,
        "height": 480,
        "header_valid": True,
        "dimensions_valid": True,
        "availability": "available",
    }


def _artifact_with_role(role: str, sha256: str) -> dict[str, Any]:
    artifact = _available_artifact()
    artifact["logical_role"] = role
    artifact["relative_path"] = f"figures/{role}.png"
    artifact["sha256"] = sha256
    return artifact


def _complete_provenance() -> dict[str, Any]:
    return {
        "status": "passed",
        "input_sha256": "1" * 64,
        "config_sha256": "2" * 64,
        "script_sha256": "3" * 64,
        "environment_sha256": "4" * 64,
        "output_sha256": "a" * 64,
        "unavailable_fields": [],
    }


def _incomplete_provenance(status: str, *, present_fields: tuple[str, ...] = ()) -> dict[str, Any]:
    record: dict[str, Any] = {
        "status": status,
        "reason": f"provenance collection completed with {status}",
        "unavailable_fields": [field for field in _PROVENANCE_HASH_FIELDS if field not in present_fields],
    }
    for index, field in enumerate(present_fields, start=1):
        record[field] = f"{index:x}" * 64
    return record


def _passed_envelope() -> dict[str, Any]:
    envelope = _minimal_envelope()
    envelope["producer"] = {
        "status": "passed",
        "kind": "test-render",
        "version": "1.0",
    }
    envelope["artifacts"] = {
        "status": "passed",
        "entries": [_available_artifact()],
    }
    envelope["provenance"] = _complete_provenance()
    return envelope


def _artifact_envelope(entry: dict[str, Any] | None = None) -> dict[str, Any]:
    envelope = _minimal_envelope()
    envelope["artifacts"] = {
        "status": "passed",
        "entries": [entry if entry is not None else _available_artifact()],
    }
    return envelope


def _artifacts_for_status(status: str) -> dict[str, Any]:
    if status in {"passed", "warning"}:
        return {"status": status, "entries": [_available_artifact()]}
    return {
        "status": status,
        "reason": f"artifact production is {status}",
        "entries": [],
    }


def _state_envelope(producer_status: str, artifact_status: str) -> dict[str, Any]:
    envelope = _minimal_envelope()
    envelope["producer"] = {
        "status": producer_status,
        "kind": "test-render",
        "version": "1.0",
    }
    if producer_status == "failed":
        envelope["producer"]["failure_stage"] = "PLOT"
    envelope["artifacts"] = _artifacts_for_status(artifact_status)
    if artifact_status in {"passed", "warning"}:
        envelope["provenance"] = _complete_provenance()
    return envelope


def _normalized_summary(status: str, check_statuses: list[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": status,
        "checks": [
            {
                "id": f"check-{index}",
                "status": check_status,
                "message": f"check-{index} completed with {check_status}",
            }
            for index, check_status in enumerate(check_statuses)
        ],
    }
    if status == "skipped":
        summary["reason"] = "summary producer was intentionally skipped"
    return summary


def test_valid_minimal_envelope() -> None:
    validate_evidence_envelope(_minimal_envelope())


def test_producer_warning_is_valid() -> None:
    validate_evidence_envelope(_minimal_envelope())


def test_skipped_native_producer_status_is_valid() -> None:
    envelope = _minimal_envelope()
    envelope["producer"]["status"] = "skipped"

    validate_evidence_envelope(envelope)


@pytest.mark.parametrize("status", ["ok", "unavailable"])
def test_native_v2_rejects_legacy_producer_statuses(status: str) -> None:
    envelope = _minimal_envelope()
    envelope["producer"]["status"] = status

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "PRODUCER_STATUS_INVALID"


def test_unavailable_measurement_is_valid() -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [
        {
            "id": "geometry.legend_overlap",
            "availability": "unavailable",
            "reason": "diagnostic was skipped within the render budget",
        }
    ]

    validate_evidence_envelope(envelope)


def test_malformed_top_level_is_rejected() -> None:
    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope([])


@pytest.mark.parametrize("field", ["data_contract_summary", "calculation_summary"])
def test_native_v2_requires_normalized_summary_fields(field: str) -> None:
    envelope = _minimal_envelope()
    envelope.pop(field)

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "FIELD_REQUIRED"
    assert raised.value.path == f"evidence.{field}"


@pytest.mark.parametrize("field", ["data_contract_summary", "calculation_summary"])
def test_normalized_summary_must_be_a_mapping(field: str) -> None:
    envelope = _minimal_envelope()
    envelope[field] = []

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("field", ["data_contract_summary", "calculation_summary"])
@pytest.mark.parametrize("status", ["ok", "unavailable", "unknown", 1])
def test_normalized_summary_rejects_status_outside_closed_enum(field: str, status: object) -> None:
    envelope = _minimal_envelope()
    envelope[field]["status"] = status

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("field", ["data_contract_summary", "calculation_summary"])
def test_normalized_summary_requires_checks_list(field: str) -> None:
    envelope = _minimal_envelope()
    envelope[field]["checks"] = {}

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("field", ["data_contract_summary", "calculation_summary"])
@pytest.mark.parametrize("reason", [None, "", "   "])
def test_skipped_normalized_summary_requires_nonempty_reason(field: str, reason: str | None) -> None:
    envelope = _minimal_envelope()
    if reason is None:
        envelope[field].pop("reason")
    else:
        envelope[field]["reason"] = reason

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("field", ["data_contract_summary", "calculation_summary"])
@pytest.mark.parametrize(
    ("status", "check_statuses"),
    [
        ("passed", ["passed"]),
        ("warning", ["passed", "warning"]),
        ("failed", ["passed", "failed"]),
        ("skipped", []),
    ],
)
def test_normalized_summary_accepts_consistent_aggregate_and_check_statuses(
    field: str, status: str, check_statuses: list[str]
) -> None:
    envelope = _minimal_envelope()
    envelope[field] = _normalized_summary(status, check_statuses)

    validate_evidence_envelope(envelope)


@pytest.mark.parametrize("field", ["data_contract_summary", "calculation_summary"])
@pytest.mark.parametrize("missing", ["id", "status", "message"])
def test_normalized_summary_check_requires_closed_fields(field: str, missing: str) -> None:
    envelope = _minimal_envelope()
    summary = _normalized_summary("passed", ["passed"])
    summary["checks"][0].pop(missing)
    envelope[field] = summary

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("field", ["data_contract_summary", "calculation_summary"])
def test_normalized_summary_check_rejects_unknown_fields(field: str) -> None:
    envelope = _minimal_envelope()
    summary = _normalized_summary("passed", ["passed"])
    summary["checks"][0]["manual_review_needed"] = False
    envelope[field] = summary

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("field", ["data_contract_summary", "calculation_summary"])
@pytest.mark.parametrize("check_status", ["ok", "unavailable", "unknown", 1])
def test_normalized_summary_check_rejects_status_outside_closed_enum(field: str, check_status: object) -> None:
    envelope = _minimal_envelope()
    summary = _normalized_summary("passed", ["passed"])
    summary["checks"][0]["status"] = check_status
    envelope[field] = summary

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("field", ["data_contract_summary", "calculation_summary"])
@pytest.mark.parametrize(
    ("status", "check_statuses"),
    [
        ("passed", ["warning"]),
        ("passed", ["failed"]),
        ("warning", ["passed"]),
        ("warning", ["failed"]),
        ("failed", ["passed"]),
        ("failed", ["warning"]),
        ("skipped", ["skipped"]),
    ],
)
def test_normalized_summary_rejects_aggregate_detail_inconsistency(
    field: str, status: str, check_statuses: list[str]
) -> None:
    envelope = _minimal_envelope()
    envelope[field] = _normalized_summary(status, check_statuses)

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_wrong_version_is_rejected() -> None:
    envelope = _minimal_envelope()
    envelope["version"] = "1.0"

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("status", [1, "unknown"])
def test_malformed_producer_status_is_rejected(status: object) -> None:
    envelope = _minimal_envelope()
    envelope["producer"]["status"] = status

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("field", ["kind", "version"])
def test_native_producer_requires_kind_and_version(field: str) -> None:
    envelope = _minimal_envelope()
    envelope["producer"].pop(field)

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_malformed_producer_container_is_rejected() -> None:
    envelope = _minimal_envelope()
    envelope["producer"] = []

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_passed_producer_rejects_failed_artifact_status() -> None:
    envelope = _passed_envelope()
    envelope["artifacts"] = {
        "status": "failed",
        "reason": "renderer did not create the declared output",
        "entries": [],
    }

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "ARTIFACT_PRODUCER_CONFLICT"


@pytest.mark.parametrize(
    "artifacts",
    [
        {},
        {"entries": [_available_artifact()]},
        {"status": "passed"},
        {"status": "passed", "entries": []},
    ],
)
def test_passed_producer_rejects_missing_artifact_status_or_verified_entries(
    artifacts: dict[str, Any],
) -> None:
    envelope = _passed_envelope()
    envelope["artifacts"] = copy.deepcopy(artifacts)
    envelope["provenance"] = {}

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_passed_producer_rejects_verified_artifact_without_full_provenance() -> None:
    envelope = _passed_envelope()
    envelope["provenance"] = {}

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "PROVENANCE_HASH_REQUIRED"


@pytest.mark.parametrize("status", ["passed", "warning", "skipped"])
def test_failure_stage_requires_failed_producer_status(status: str) -> None:
    envelope = _minimal_envelope()
    envelope["producer"] = {
        "status": status,
        "kind": "test-render",
        "version": "1.0",
        "failure_stage": "PLOT",
    }

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "FAILURE_STAGE_CONFLICT"


@pytest.mark.parametrize("failure_stage", [None, "", "   "])
def test_failed_producer_requires_nonempty_failure_stage(
    failure_stage: str | None,
) -> None:
    envelope = _minimal_envelope()
    envelope["producer"] = {
        "status": "failed",
        "kind": "test-render",
        "version": "1.0",
    }
    if failure_stage is not None:
        envelope["producer"]["failure_stage"] = failure_stage

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_failed_producer_with_failure_stage_is_valid() -> None:
    envelope = _state_envelope("failed", "failed")

    validate_evidence_envelope(envelope)


@pytest.mark.parametrize(
    ("producer_status", "artifact_status"),
    [
        ("passed", "passed"),
        ("warning", "passed"),
        ("warning", "warning"),
        ("warning", "unavailable"),
        ("failed", "failed"),
        ("failed", "unavailable"),
        ("skipped", "skipped"),
        ("skipped", "unavailable"),
    ],
)
def test_producer_artifact_state_matrix_accepts_consistent_pairs(producer_status: str, artifact_status: str) -> None:
    validate_evidence_envelope(_state_envelope(producer_status, artifact_status))


@pytest.mark.parametrize(
    ("producer_status", "artifact_status"),
    [
        ("passed", "warning"),
        ("passed", "failed"),
        ("passed", "skipped"),
        ("passed", "unavailable"),
        ("warning", "failed"),
        ("warning", "skipped"),
        ("failed", "passed"),
        ("failed", "warning"),
        ("failed", "skipped"),
        ("skipped", "passed"),
        ("skipped", "warning"),
        ("skipped", "failed"),
    ],
)
def test_producer_artifact_state_matrix_rejects_inconsistent_pairs(producer_status: str, artifact_status: str) -> None:
    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(_state_envelope(producer_status, artifact_status))


@pytest.mark.parametrize(
    "failure_stage",
    [
        "CONFIG",
        "VALIDATE",
        "CONTRACT",
        "EXECUTE",
        "PLOT",
        "EXPORT",
        "TIMEOUT",
        "TRANSFER",
        "LEGACY",
    ],
)
def test_failed_producer_accepts_closed_failure_stage_enum(failure_stage: str) -> None:
    envelope = _state_envelope("failed", "failed")
    envelope["producer"]["failure_stage"] = failure_stage

    validate_evidence_envelope(envelope)


@pytest.mark.parametrize("failure_stage", ["plot", "UNKNOWN", "", "   ", 1, True])
def test_failed_producer_rejects_failure_stage_outside_closed_enum(
    failure_stage: object,
) -> None:
    envelope = _state_envelope("failed", "failed")
    envelope["producer"]["failure_stage"] = failure_stage

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_malformed_measurements_container_is_rejected() -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = {}

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_malformed_policy_container_is_rejected() -> None:
    envelope = _minimal_envelope()
    envelope["policy_projections"] = {}

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("field", ["artifacts", "provenance"])
def test_malformed_mapping_container_is_rejected(field: str) -> None:
    envelope = _minimal_envelope()
    envelope[field] = []

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_evidence_depth_bound_is_enforced() -> None:
    envelope = _minimal_envelope()
    nested: Any = 0
    for _ in range(MAX_EVIDENCE_DEPTH + 1):
        nested = [nested]
    envelope["measurements"] = nested

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "MAX_DEPTH"


def test_evidence_item_bound_is_enforced() -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [0] * (MAX_EVIDENCE_ITEMS + 1)

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "MAX_ITEMS"


def test_evidence_serialized_size_bound_is_enforced() -> None:
    envelope = _minimal_envelope()
    envelope["producer"]["reason"] = "x" * (MAX_EVIDENCE_SERIALIZED_BYTES + 1)

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "MAX_BYTES"


def test_duplicate_measurement_id_is_rejected() -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [
        {"id": "geometry.clipping", "availability": "available", "value": 0},
        {"id": "geometry.clipping", "availability": "available", "value": 1},
    ]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_available_measurement_requires_value() -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [{"id": "geometry.clipping", "availability": "available"}]

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "VALUE_REQUIRED"


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_unavailable_measurement_requires_nonempty_reason(reason: str | None) -> None:
    envelope = _minimal_envelope()
    measurement: dict[str, Any] = {
        "id": "geometry.clipping",
        "availability": "unavailable",
    }
    if reason is not None:
        measurement["reason"] = reason
    envelope["measurements"] = [measurement]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_measurement_values_are_rejected(value: float) -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [
        {
            "id": "geometry.clipping",
            "availability": "available",
            "value": value,
        }
    ]

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "JSON_INVALID"


@pytest.mark.parametrize("policy_field", ["passed", "severity", "outcome", "hard", "blocked"])
def test_measurements_cannot_contain_policy_fields(policy_field: str) -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [
        {
            "id": "geometry.clipping",
            "availability": "available",
            "value": 0,
            policy_field: "passed",
        }
    ]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("policy_field", ["passed", "hard", "blocked"])
def test_measurements_cannot_hide_policy_fields_in_nested_raw_data(
    policy_field: str,
) -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [
        {
            "id": "geometry.clipping",
            "availability": "available",
            "value": 0,
            "scope": {"producer_policy": {policy_field: True}},
        }
    ]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_policy_projection_cannot_reference_unknown_measurement() -> None:
    envelope = _minimal_envelope()
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": ["geometry.missing"],
        }
    ]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize(
    ("severity", "outcome"),
    [
        ("hard", "blocked"),
        ("advisory", "needs_revision"),
        ("informational", "informational"),
    ],
)
def test_policy_finding_accepts_closed_severity_and_outcome_enums(severity: str, outcome: str) -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [{"id": "geometry.clipping", "availability": "available", "value": 1}]
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": ["geometry.clipping"],
            "findings": [
                {
                    "code": "CLIPPING_DETECTED",
                    "metric_id": "geometry.clipping",
                    "message": "One artist is outside the declared figure bounds.",
                    "severity": severity,
                    "outcome": outcome,
                }
            ],
        }
    ]

    validate_evidence_envelope(envelope)


@pytest.mark.parametrize("field", ["code", "metric_id", "message", "severity", "outcome"])
def test_policy_finding_requires_every_contract_field(field: str) -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [{"id": "geometry.clipping", "availability": "available", "value": 1}]
    finding = {
        "code": "CLIPPING_DETECTED",
        "metric_id": "geometry.clipping",
        "message": "One artist is outside the declared figure bounds.",
        "severity": "hard",
        "outcome": "blocked",
    }
    finding.pop(field)
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": ["geometry.clipping"],
            "findings": [finding],
        }
    ]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("severity", ["major", "info", "critical", "human"])
def test_policy_finding_rejects_severity_outside_closed_enum(severity: str) -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [{"id": "geometry.clipping", "availability": "available", "value": 1}]
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": ["geometry.clipping"],
            "findings": [
                {
                    "code": "CLIPPING_DETECTED",
                    "metric_id": "geometry.clipping",
                    "message": "Clipping requires a policy decision.",
                    "severity": severity,
                    "outcome": "blocked",
                }
            ],
        }
    ]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("outcome", ["approved", "review", "pass", "failed"])
def test_policy_finding_rejects_outcome_outside_closed_enum(outcome: str) -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [{"id": "geometry.clipping", "availability": "available", "value": 1}]
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": ["geometry.clipping"],
            "findings": [
                {
                    "code": "CLIPPING_DETECTED",
                    "metric_id": "geometry.clipping",
                    "message": "Clipping requires a policy decision.",
                    "severity": "hard",
                    "outcome": outcome,
                }
            ],
        }
    ]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_policy_finding_metric_must_be_declared_in_projection_refs() -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [
        {"id": "geometry.clipping", "availability": "available", "value": 1},
        {"id": "geometry.crowding", "availability": "available", "value": 1},
    ]
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": ["geometry.clipping"],
            "findings": [
                {
                    "code": "CROWDING_DETECTED",
                    "metric_id": "geometry.crowding",
                    "message": "Crowding is advisory under the selected policy.",
                    "severity": "advisory",
                    "outcome": "needs_revision",
                }
            ],
        }
    ]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize(
    "field",
    [
        "logical_role",
        "relative_path",
        "media_type",
        "byte_size",
        "sha256",
        "width",
        "height",
        "header_valid",
        "dimensions_valid",
    ],
)
def test_available_artifact_requires_integrity_fields(field: str) -> None:
    artifact = _available_artifact()
    artifact.pop(field)

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(_artifact_envelope(artifact))


def test_available_vector_artifact_types_pixel_dimensions_as_unavailable() -> None:
    artifact = _available_artifact()
    artifact.update(
        {
            "relative_path": "figures/figure.pdf",
            "media_type": "application/pdf",
            "dimension_availability": "unavailable",
            "dimension_reason": "PDF has no intrinsic pixel grid",
        }
    )
    for field in ("width", "height", "dimensions_valid"):
        artifact.pop(field)
    envelope = _artifact_envelope(artifact)
    envelope["producer"]["status"] = "passed"
    envelope["provenance"] = _complete_provenance()

    validate_evidence_envelope(envelope)


def test_vector_dimension_unavailability_requires_reason_and_forbids_claimed_dimensions() -> None:
    artifact = _available_artifact()
    artifact.update(
        {
            "relative_path": "figures/figure.pdf",
            "media_type": "application/pdf",
            "dimension_availability": "unavailable",
        }
    )
    artifact.pop("height")
    artifact.pop("dimensions_valid")

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(_artifact_envelope(artifact))


def test_vector_artifact_cannot_claim_forged_pixel_dimensions() -> None:
    artifact = _available_artifact()
    artifact.update(
        {
            "relative_path": "figures/figure.pdf",
            "media_type": "application/pdf",
            "dimension_availability": "available",
        }
    )

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(_artifact_envelope(artifact))

    assert raised.value.code == "ARTIFACT_DIMENSION_CONFLICT"


def test_raster_artifact_cannot_hide_verified_dimensions() -> None:
    artifact = _available_artifact()
    artifact.update(
        {
            "dimension_availability": "unavailable",
            "dimension_reason": "producer chose not to report dimensions",
        }
    )
    for field in ("width", "height", "dimensions_valid"):
        artifact.pop(field)

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(_artifact_envelope(artifact))

    assert raised.value.code == "ARTIFACT_DIMENSION_CONFLICT"


@pytest.mark.parametrize(
    "relative_path",
    ["../escape.png", "figures/../../escape.png", "/tmp/escape.png", r"C:\tmp\escape.png"],
)
def test_artifact_path_must_be_safe_and_relative(relative_path: str) -> None:
    artifact = _available_artifact()
    artifact["relative_path"] = relative_path

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(_artifact_envelope(artifact))


@pytest.mark.parametrize("media_type", ["image", "not-a-mime", "text/plain"])
def test_artifact_media_type_must_be_valid_for_the_declared_file(media_type: str) -> None:
    artifact = _available_artifact()
    artifact["media_type"] = media_type

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(_artifact_envelope(artifact))


@pytest.mark.parametrize("byte_size", [0, -1, True, 1.5, "1024"])
def test_artifact_size_must_be_a_positive_integer(byte_size: object) -> None:
    artifact = _available_artifact()
    artifact["byte_size"] = byte_size

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(_artifact_envelope(artifact))

    assert raised.value.code == "ARTIFACT_SIZE_INVALID"


@pytest.mark.parametrize("field", ["width", "height"])
@pytest.mark.parametrize("dimension", [0, -1, True, 1.5, "640"])
def test_artifact_dimensions_must_be_positive_integers(field: str, dimension: object) -> None:
    artifact = _available_artifact()
    artifact[field] = dimension

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(_artifact_envelope(artifact))


@pytest.mark.parametrize("field", ["header_valid", "dimensions_valid"])
@pytest.mark.parametrize("value", [False, None, 1, "true"])
def test_artifact_integrity_flags_must_be_literal_true(field: str, value: object) -> None:
    artifact = _available_artifact()
    artifact[field] = value

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(_artifact_envelope(artifact))

    assert raised.value.code == "ARTIFACT_VALIDATION_REQUIRED"


@pytest.mark.parametrize("sha256", ["", "a" * 63, "g" * 64, 123])
def test_artifact_hash_must_be_sha256(sha256: object) -> None:
    artifact = _available_artifact()
    artifact["sha256"] = sha256

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(_artifact_envelope(artifact))

    assert raised.value.code == "SHA256_INVALID"


def test_passed_artifact_status_requires_an_entry() -> None:
    envelope = _minimal_envelope()
    envelope["artifacts"] = {"status": "passed", "entries": []}

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_unavailable_artifact_entry_requires_reason_and_cannot_claim_integrity() -> None:
    artifact = _available_artifact()
    artifact["availability"] = "unavailable"
    artifact["reason"] = "output was not created"

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(_artifact_envelope(artifact))


def test_passed_producer_with_complete_artifact_and_provenance_is_valid() -> None:
    validate_evidence_envelope(_passed_envelope())


@pytest.mark.parametrize(
    "hash_field",
    [
        "input_sha256",
        "config_sha256",
        "script_sha256",
        "environment_sha256",
        "output_sha256",
    ],
)
@pytest.mark.parametrize(
    ("producer_status", "artifact_status"),
    [("passed", "passed"), ("warning", "passed"), ("warning", "warning")],
)
def test_produced_artifact_requires_complete_provenance_hashes(
    hash_field: str, producer_status: str, artifact_status: str
) -> None:
    envelope = _state_envelope(producer_status, artifact_status)
    envelope["provenance"].pop(hash_field)

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "PROVENANCE_HASH_REQUIRED"
    assert raised.value.path == f"evidence.provenance.{hash_field}"


def test_provenance_status_is_always_required() -> None:
    envelope = _state_envelope("skipped", "unavailable")
    envelope["provenance"].pop("status")

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_empty_provenance_record_is_rejected() -> None:
    envelope = _state_envelope("skipped", "unavailable")
    envelope["provenance"] = {}

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_passed_provenance_with_all_five_hashes_is_valid() -> None:
    envelope = _state_envelope("skipped", "unavailable")
    envelope["provenance"] = _complete_provenance()

    validate_evidence_envelope(envelope)


@pytest.mark.parametrize("hash_field", _PROVENANCE_HASH_FIELDS)
def test_passed_provenance_requires_all_five_hashes(hash_field: str) -> None:
    envelope = _state_envelope("skipped", "unavailable")
    envelope["provenance"] = _complete_provenance()
    envelope["provenance"].pop(hash_field)

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("status", ["skipped", "unavailable"])
def test_nonproducing_provenance_requires_reason_and_complete_unavailable_fields(
    status: str,
) -> None:
    envelope = _state_envelope("skipped", "unavailable")
    envelope["provenance"] = _incomplete_provenance(status)

    validate_evidence_envelope(envelope)


@pytest.mark.parametrize("status", ["skipped", "unavailable"])
@pytest.mark.parametrize("reason", [None, "", "   "])
def test_nonproducing_provenance_requires_nonempty_reason(status: str, reason: str | None) -> None:
    envelope = _state_envelope("skipped", "unavailable")
    record = _incomplete_provenance(status)
    if reason is None:
        record.pop("reason")
    else:
        record["reason"] = reason
    envelope["provenance"] = record

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("status", ["warning", "failed", "skipped", "unavailable"])
def test_incomplete_provenance_accepts_exact_missing_hash_accounting(status: str) -> None:
    envelope = _state_envelope("skipped", "unavailable")
    envelope["provenance"] = _incomplete_provenance(status, present_fields=("input_sha256",))

    validate_evidence_envelope(envelope)


@pytest.mark.parametrize("status", ["warning", "failed", "skipped", "unavailable"])
def test_incomplete_provenance_rejects_unlisted_missing_hash(status: str) -> None:
    envelope = _state_envelope("skipped", "unavailable")
    record = _incomplete_provenance(status, present_fields=("input_sha256",))
    record["unavailable_fields"].remove("config_sha256")
    envelope["provenance"] = record

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("status", ["warning", "failed", "skipped", "unavailable"])
def test_incomplete_provenance_rejects_available_hash_listed_as_unavailable(
    status: str,
) -> None:
    envelope = _state_envelope("skipped", "unavailable")
    record = _incomplete_provenance(status, present_fields=("input_sha256",))
    record["unavailable_fields"].append("input_sha256")
    envelope["provenance"] = record

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("status", ["warning", "failed", "skipped", "unavailable"])
def test_incomplete_provenance_rejects_duplicate_unavailable_fields(status: str) -> None:
    envelope = _state_envelope("skipped", "unavailable")
    record = _incomplete_provenance(status, present_fields=("input_sha256",))
    record["unavailable_fields"].append("config_sha256")
    envelope["provenance"] = record

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_exact_reproducibility_and_visual_comparison_remain_separate() -> None:
    envelope = _passed_envelope()
    envelope["artifacts"]["entries"].extend(
        [
            _artifact_with_role("reference", "b" * 64),
            _artifact_with_role("candidate", "c" * 64),
        ]
    )
    envelope["exact_reproducibility"] = {
        "status": "different",
        "algorithm": "sha256",
        "reference_sha256": "a" * 64,
        "candidate_sha256": "b" * 64,
    }
    envelope["visual_comparison"] = {
        "status": "available",
        "algorithm": {"name": "pixel-diff", "version": "1.0"},
        "reference_artifact": "reference",
        "candidate_artifact": "candidate",
        "metrics": {"different_pixel_ratio": 0.01},
    }

    normalized = normalize_evidence_envelope(envelope)

    assert normalized["exact_reproducibility"] == envelope["exact_reproducibility"]
    assert normalized["visual_comparison"] == envelope["visual_comparison"]
    assert normalized["exact_reproducibility"] is not normalized["visual_comparison"]


def test_policy_projection_status_uses_closed_enum() -> None:
    envelope = _minimal_envelope()
    envelope["policy_projections"] = [
        {
            "id": "policy",
            "version": "1",
            "measurement_refs": [],
            "status": "approved",
        }
    ]

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "POLICY_STATUS_INVALID"


@pytest.mark.parametrize(
    ("status", "reference", "candidate", "algorithm"),
    [
        ("same", "a" * 64, "b" * 64, "sha256"),
        ("different", "a" * 64, "a" * 64, "sha256"),
        ("same", "a" * 64, "a" * 64, "md5"),
    ],
)
def test_exact_status_algorithm_and_hashes_must_be_consistent(
    status: str,
    reference: str,
    candidate: str,
    algorithm: str,
) -> None:
    envelope = _minimal_envelope()
    envelope["exact_reproducibility"] = {
        "status": status,
        "algorithm": algorithm,
        "reference_sha256": reference,
        "candidate_sha256": candidate,
    }

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_visual_comparison_must_reference_verified_artifact_roles() -> None:
    envelope = _minimal_envelope()
    envelope["visual_comparison"] = {
        "status": "available",
        "algorithm": {"name": "pixel-diff", "version": "1"},
        "reference_artifact": "missing-reference",
        "candidate_artifact": "missing-candidate",
        "metrics": {},
    }

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "VISUAL_ARTIFACT_UNKNOWN"


def test_primary_artifact_sha_must_match_output_provenance() -> None:
    envelope = _passed_envelope()
    envelope["provenance"]["output_sha256"] = "f" * 64

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "PRIMARY_OUTPUT_HASH_CONFLICT"


@pytest.mark.parametrize("status", ["same", "different"])
def test_exact_comparison_cannot_claim_result_without_complete_hashes(
    status: str,
) -> None:
    envelope = _minimal_envelope()
    envelope["exact_reproducibility"] = {"status": status, "algorithm": "sha256"}

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_exact_comparison_rejects_one_sided_hash() -> None:
    envelope = _minimal_envelope()
    envelope["exact_reproducibility"] = {
        "status": "same",
        "algorithm": "sha256",
        "reference_sha256": "a" * 64,
    }

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "EXACT_HASH_REQUIRED"


@pytest.mark.parametrize("status", ["unavailable", "skipped"])
def test_unavailable_exact_comparison_requires_reason(status: str) -> None:
    envelope = _minimal_envelope()
    envelope["exact_reproducibility"] = {"status": status}

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_unavailable_exact_comparison_with_reason_is_valid() -> None:
    envelope = _minimal_envelope()
    envelope["exact_reproducibility"] = {
        "status": "unavailable",
        "reason": "no reference artifact was selected",
    }

    validate_evidence_envelope(envelope)


@pytest.mark.parametrize(
    "missing_field",
    ["algorithm", "reference_artifact", "candidate_artifact", "metrics"],
)
def test_available_visual_comparison_requires_complete_evidence(
    missing_field: str,
) -> None:
    envelope = _minimal_envelope()
    visual = {
        "status": "available",
        "algorithm": {"name": "pixel-diff", "version": "1.0"},
        "reference_artifact": "artifact://reference.png",
        "candidate_artifact": "artifact://candidate.png",
        "metrics": {"different_pixel_ratio": 0.01},
    }
    visual.pop(missing_field)
    envelope["visual_comparison"] = visual

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("status", ["unavailable", "skipped"])
def test_unavailable_visual_comparison_requires_reason(status: str) -> None:
    envelope = _minimal_envelope()
    envelope["visual_comparison"] = {"status": status}

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_unavailable_visual_comparison_with_reason_is_valid() -> None:
    envelope = _minimal_envelope()
    envelope["visual_comparison"] = {
        "status": "unavailable",
        "reason": "visual comparison policy was not selected",
    }

    validate_evidence_envelope(envelope)


@pytest.mark.parametrize("policy_field", ["passed", "severity", "outcome", "hard", "blocked"])
def test_visual_comparison_metrics_cannot_contain_recursive_policy_fields(
    policy_field: str,
) -> None:
    envelope = _minimal_envelope()
    envelope["visual_comparison"] = {
        "status": "available",
        "algorithm": {"name": "pixel-diff", "version": "1.0"},
        "reference_artifact": "artifact://reference.png",
        "candidate_artifact": "artifact://candidate.png",
        "metrics": {
            "different_pixel_ratio": 0.01,
            "raw_regions": [{"region": "panel-a", "policy": {policy_field: True}}],
        },
    }

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_normalization_is_a_json_roundtrip_safe_deep_copy() -> None:
    envelope = _minimal_envelope()
    envelope["measurements"] = [
        {
            "id": "geometry.clipping",
            "availability": "available",
            "value": 0,
            "unit": "count",
            "scope": {"panel": "A"},
        }
    ]
    expected = json.loads(json.dumps(envelope))

    normalized = normalize_evidence_envelope(envelope)
    envelope["measurements"][0]["scope"]["panel"] = "mutated"

    assert normalized == expected
    assert normalized is not envelope
    assert normalized["measurements"] is not envelope["measurements"]


def test_research_ops_policy_preserves_explicit_false_opt_out() -> None:
    envelope = _minimal_envelope()
    envelope["policy_projections"] = [
        {
            "id": "research-ops-v4",
            "version": "4",
            "measurement_refs": [],
            "resolved": {
                "project_role": {"value": "module", "source": "project_config"},
                "tier_3": {"value": False, "source": "explicit_project_opt_out"},
            },
        }
    ]

    normalized = normalize_evidence_envelope(envelope)
    tier_3 = normalized["policy_projections"][0]["resolved"]["tier_3"]

    assert tier_3 == {"value": False, "source": "explicit_project_opt_out"}
    assert tier_3["value"] is False


def test_resolved_policy_with_identity_version_and_source_is_valid() -> None:
    envelope = _minimal_envelope()
    envelope["resolved_policy"] = {
        "id": "research-ops-v4",
        "version": "4",
        "source": "project_config",
        "parameters": {},
    }

    validate_evidence_envelope(envelope)


@pytest.mark.parametrize("field", ["id", "version", "source"])
def test_resolved_policy_requires_identity_version_and_source(field: str) -> None:
    envelope = _minimal_envelope()
    policy = {
        "id": "research-ops-v4",
        "version": "4",
        "source": "project_config",
    }
    policy.pop(field)
    envelope["resolved_policy"] = policy

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize(
    "resolution",
    [
        False,
        {"source": "explicit_project_opt_out"},
        {"value": False},
        {"value": False, "source": "explicit_project_opt_out", "enabled": False},
    ],
)
def test_explicit_false_opt_out_requires_resolution_structure(
    resolution: object,
) -> None:
    envelope = _minimal_envelope()
    envelope["policy_projections"] = [
        {
            "id": "research-ops-v4",
            "version": "4",
            "measurement_refs": [],
            "resolved": {"tier_3": resolution},
        }
    ]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_valid_mutation_ledger_is_preserved() -> None:
    envelope = _minimal_envelope()
    envelope["mutation_ledger"] = [
        {
            "mutation_id": "label-map-1",
            "transform": "label_map",
            "mode": "apply",
            "before": "ABC_DEF",
            "after": "ABC DEF",
            "policy_id": "explicit-label-map",
            "reason": "explicit display-label mapping",
        }
    ]

    normalized = normalize_evidence_envelope(envelope)

    assert normalized["mutation_ledger"] == envelope["mutation_ledger"]


@pytest.mark.parametrize(
    "field",
    ["mutation_id", "transform", "mode", "before", "after", "policy_id", "reason"],
)
def test_mutation_ledger_requires_core_fields(field: str) -> None:
    envelope = _minimal_envelope()
    mutation = {
        "mutation_id": "label-map-1",
        "transform": "label_map",
        "mode": "apply",
        "before": "ABC_DEF",
        "after": "ABC DEF",
        "policy_id": "explicit-label-map",
        "reason": "explicit display-label mapping",
    }
    mutation.pop(field)
    envelope["mutation_ledger"] = [mutation]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_mutation_ledger_rejects_duplicate_ids() -> None:
    envelope = _minimal_envelope()
    mutation = {
        "mutation_id": "label-map-1",
        "transform": "label_map",
        "mode": "apply",
        "before": "ABC_DEF",
        "after": "ABC DEF",
        "policy_id": "explicit-label-map",
        "reason": "explicit display-label mapping",
    }
    envelope["mutation_ledger"] = [mutation, copy.deepcopy(mutation)]

    with pytest.raises(EvidenceContractError) as raised:
        validate_evidence_envelope(envelope)

    assert raised.value.code == "MUTATION_ID_DUPLICATE"


@pytest.mark.parametrize(
    "field",
    ["mutation_id", "transform", "mode", "policy_id", "reason"],
)
def test_mutation_ledger_requires_nonempty_string_metadata(field: str) -> None:
    envelope = _minimal_envelope()
    mutation = {
        "mutation_id": "label-map-1",
        "transform": "label_map",
        "mode": "apply",
        "before": "ABC_DEF",
        "after": "ABC DEF",
        "policy_id": "explicit-label-map",
        "reason": "explicit display-label mapping",
    }
    mutation[field] = ""
    envelope["mutation_ledger"] = [mutation]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


@pytest.mark.parametrize("legacy_field", ["source", "target", "mapping"])
def test_mutation_ledger_rejects_noncanonical_legacy_aliases(legacy_field: str) -> None:
    envelope = _minimal_envelope()
    envelope["mutation_ledger"] = [
        {
            "mutation_id": "label-map-1",
            "transform": "label_map",
            "mode": "apply",
            "before": "ABC_DEF",
            "after": "ABC DEF",
            "policy_id": "explicit-label-map",
            "reason": "explicit display-label mapping",
            legacy_field: "legacy value",
        }
    ]

    with pytest.raises(EvidenceContractError):
        validate_evidence_envelope(envelope)


def test_legacy_geometry_mapping_becomes_severity_free_measurement() -> None:
    legacy = {
        "status": "ok",
        "geometry_checks": {
            "geometry.clipping": {
                "value": 0,
                "unit": "count",
                "availability": "available",
                "severity": "hard",
                "outcome": "passed",
            }
        },
    }

    normalized = adapt_legacy_evidence(legacy)

    assert normalized["measurements"] == [
        {
            "id": "geometry.clipping",
            "availability": "available",
            "value": 0,
            "unit": "count",
        }
    ]


def test_legacy_missing_producer_never_defaults_to_passed() -> None:
    normalized = adapt_legacy_evidence({})

    assert normalized["producer"]["status"] == "warning"
    assert normalized["producer"]["status"] != "passed"


def test_legacy_ok_without_verified_artifact_or_provenance_normalizes_to_warning() -> None:
    normalized = adapt_legacy_evidence({"status": "ok"})

    assert normalized["producer"]["status"] == "warning"
    assert normalized["artifacts"]["status"] == "unavailable"
    assert normalized["provenance"]["status"] == "skipped"
    validate_evidence_envelope(normalized)


def test_legacy_failure_artifact_stage_and_provenance_are_preserved() -> None:
    legacy = {
        "status": "failed",
        "failure_stage": "PLOT",
        "artifacts": {
            "status": "failed",
            "reason": "declared output was not created",
            "entries": [],
        },
        "provenance": {
            "status": "failed",
            "reason": "output hash could not be recorded",
            "input_sha256": "1" * 64,
        },
    }

    normalized = adapt_legacy_evidence(legacy)

    assert normalized["producer"]["status"] == "failed"
    assert normalized["producer"]["failure_stage"] == "PLOT"
    assert normalized["artifacts"]["status"] == "failed"
    assert normalized["artifacts"]["reason"] == legacy["artifacts"]["reason"]
    assert normalized["provenance"]["status"] == "failed"
    assert normalized["provenance"]["reason"] == legacy["provenance"]["reason"]
    assert normalized["provenance"]["input_sha256"] == "1" * 64


def test_legacy_passed_and_other_policy_keys_are_stripped_from_raw_measurement() -> None:
    legacy = {
        "status": "ok",
        "geometry_checks": {
            "geometry.clipping": {
                "availability": "available",
                "value": 0,
                "passed": True,
                "hard": True,
                "blocked": False,
                "severity": "hard",
                "outcome": "passed",
            }
        },
    }

    normalized = adapt_legacy_evidence(legacy)
    measurement = normalized["measurements"][0]

    assert measurement == {
        "id": "geometry.clipping",
        "availability": "available",
        "value": 0,
    }
    assert not {"passed", "hard", "blocked", "severity", "outcome"}.intersection(measurement)


def test_legacy_baseline_maps_only_to_exact_reproducibility() -> None:
    baseline = {
        "checked": True,
        "matched": False,
        "status": "manual_review_needed",
        "algorithm": "sha256",
        "artifact_sha256": "b" * 64,
    }
    legacy = {"status": "ok", "baseline_comparison": copy.deepcopy(baseline)}

    normalized = adapt_legacy_evidence(legacy)

    assert normalized["exact_reproducibility"] == baseline
    assert normalized["visual_comparison"] is None
    assert "baseline" not in normalized


def test_normalization_rejects_legacy_when_adapter_is_disabled() -> None:
    with pytest.raises(EvidenceContractError):
        normalize_evidence_envelope({"status": "ok"}, allow_legacy=False)


def test_contract_error_exposes_stable_code_path_and_message() -> None:
    errors: list[EvidenceContractError] = []
    for _ in range(2):
        envelope = _minimal_envelope()
        envelope["version"] = "1.0"
        with pytest.raises(EvidenceContractError) as raised:
            validate_evidence_envelope(envelope)
        errors.append(raised.value)

    first, second = errors
    assert isinstance(first.code, str) and first.code
    assert first.path == "evidence.version"
    assert isinstance(first.message, str) and first.message
    assert str(first) == first.message
    assert (first.code, first.path, first.message) == (second.code, second.path, second.message)


def _wp0_durable_diagnostics() -> dict[str, object]:
    output = {"artifact_id": "calc-1", "role": "result.source_data", "sha256": "9" * 64}
    return {
        "figops_version": "0.20.0",
        "run_id": "run-1",
        "timestamp": "2026-07-15T00:00:00Z",
        "git_sha256": "1" * 64,
        "config_sha256": "2" * 64,
        "script_sha256": "3" * 64,
        "environment_lock_sha256": "4" * 64,
        "durable_artifact": output,
        "input_artifacts": [{"artifact_id": "raw-1", "role": "raw", "sha256": "5" * 64}],
        "output_artifacts": [output],
        "claim_ids": ["claim:figure-1:p-value"],
        "manifest_id": "manifest-a1b2",
        "manifest_sha256": "6" * 64,
        "logs": ["C:/Users/researcher/runtime/job.log"],
        "sample_rows": [{"restricted": "secret"}],
    }


def test_durable_receipt_normalizes_diagnostics_and_hides_runtime_root() -> None:
    from hub_core.durable_receipt import DurableReceipt

    serialized = DurableReceipt.from_runtime_diagnostics(_wp0_durable_diagnostics()).canonical_bytes()

    assert b"C:/Users" not in serialized
    assert b"sample_rows" not in serialized
    assert b"logs" not in serialized


def test_calculation_receipt_binds_durable_artifact_and_lineage() -> None:
    from hub_core.durable_receipt import DurableReceipt

    receipt = DurableReceipt.from_runtime_diagnostics(_wp0_durable_diagnostics())
    payload = receipt.to_dict()

    assert payload["durable_artifact"] == payload["output_artifacts"][0]
    assert payload["producer"] == {
        "config_sha256": "2" * 64,
        "script_sha256": "3" * 64,
        "environment_lock_sha256": "4" * 64,
    }
    assert payload["input_artifacts"][0]["role"] == "raw"
    assert payload["input_artifacts"][0]["sha256"] == "5" * 64
    assert payload["input_artifacts"][0]["artifact_id"].startswith("raw:")
    assert payload["claim_ids"][0].startswith("claim:")
    assert "durable_receipt_sha256" not in payload


def test_receipt_verifies_after_runtime_tree_deletion(tmp_path) -> None:
    import shutil

    from hub_core.durable_receipt import DurableReceipt, receipt_sha256, verify_receipt

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "manifest.json").write_text("disposable detail", encoding="utf-8")
    receipt = DurableReceipt.from_runtime_diagnostics(_wp0_durable_diagnostics())
    digest = receipt_sha256(receipt)

    shutil.rmtree(runtime)

    assert verify_receipt(receipt, digest)
