from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from hub_core.artifact_audit import (
    MAX_AUDIT_OUTPUT_BYTES,
    PUBLICATION_READINESS_POLICY,
    audit_artifact_evidence,
)


def _envelope() -> dict[str, Any]:
    return {
        "version": "2.0",
        "producer": {
            "status": "passed",
            "kind": "test-render",
            "version": "1.0",
        },
        "measurements": [],
        "policy_projections": [],
        "artifacts": {
            "status": "passed",
            "entries": [
                {
                    "logical_role": "primary",
                    "relative_path": "figures/figure.png",
                    "media_type": "image/png",
                    "byte_size": 1024,
                    "sha256": "a" * 64,
                    "width": 640,
                    "height": 480,
                    "header_valid": True,
                    "dimensions_valid": True,
                    "availability": "available",
                }
            ],
        },
        "provenance": {
            "status": "passed",
            "input_sha256": "1" * 64,
            "config_sha256": "2" * 64,
            "script_sha256": "3" * 64,
            "environment_sha256": "4" * 64,
            "output_sha256": "a" * 64,
            "unavailable_fields": [],
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


def _summary(status: str, *checks: tuple[str, str]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "checks": [
            {"id": check_id, "status": check_status, "message": f"{check_id}: {check_status}"}
            for check_id, check_status in checks
        ],
    }
    if status == "skipped":
        payload["reason"] = "the summary was not requested"
    return payload


def _finding_codes(report: dict[str, Any]) -> set[str]:
    return {str(item["code"]) for item in report["findings"]}


def _with_publication_projection(envelope: dict[str, Any]) -> dict[str, Any]:
    envelope["resolved_policy"] = {
        "id": "publication-readiness-v2",
        "version": "2",
        "source": "caller",
        "parameters": {"review": True},
    }
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": [],
            "resolved": {"review": {"value": True, "source": "resolved_policy"}},
        }
    ]
    return envelope


def test_clean_kernel_never_claims_approval() -> None:
    report = audit_artifact_evidence(_envelope(), policy_packs=[])

    assert report["status"] == "needs_review"
    assert report["manual_review_required"] is True
    assert report["selected_policy_ids"] == []
    assert report["findings"] == []
    assert report["summary"]["status"] == "needs_review"
    assert report["summary"]["finding_counts"] == {"hard": 0, "major": 0, "info": 0}
    assert report["summary"]["gate_counts"] == {"blocked": 0, "needs_revision": 0, "needs_review": 6}
    assert report["summary"]["findings_truncated"] is False
    assert "approved" not in repr(report).lower()
    assert "publishable" not in repr(report).lower()


def test_empty_policy_does_not_run_geometry_or_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    envelope = _envelope()
    envelope["measurements"] = [
        {
            "id": "geometry.optional_probe",
            "availability": "unavailable",
            "reason": "the optional renderer was not installed",
        }
    ]
    monkeypatch.setattr(
        "hub_core.artifact_audit.evaluate_publication_readiness",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("readiness policy was not selected")),
    )

    report = audit_artifact_evidence(envelope, policy_packs=[])

    assert report["status"] == "needs_review"
    assert report["findings"] == []


def test_forged_summary_aggregate_is_blocked_by_evidence_contract() -> None:
    envelope = _envelope()
    envelope["data_contract_summary"] = _summary("passed", ("raw_integrity", "failed"))

    report = audit_artifact_evidence(envelope)

    assert report["status"] == "blocked"
    assert "EVIDENCE_CONTRACT_SUMMARY_AGGREGATE_CONFLICT" in _finding_codes(report)
    assert report["evidence_digest"] is None
    assert report["summary"]["finding_counts"]["hard"] == 1


def test_forged_producer_status_cannot_hide_failed_artifact_detail() -> None:
    envelope = _envelope()
    envelope["artifacts"] = {
        "status": "failed",
        "reason": "the declared output was absent",
        "entries": [],
    }

    report = audit_artifact_evidence(envelope)

    assert report["status"] == "blocked"
    assert "EVIDENCE_CONTRACT_ARTIFACT_PRODUCER_CONFLICT" in _finding_codes(report)


def test_valid_failed_envelope_runs_producer_artifact_and_provenance_gates() -> None:
    envelope = _envelope()
    envelope["producer"] = {
        "status": "failed",
        "kind": "test-render",
        "version": "1.0",
        "failure_stage": "EXPORT",
        "reason": "export failed",
    }
    envelope["artifacts"] = {
        "status": "failed",
        "reason": "no verified output bytes exist",
        "entries": [],
    }
    envelope["provenance"] = {
        "status": "failed",
        "reason": "output hash is unavailable after export failure",
        "input_sha256": "1" * 64,
        "config_sha256": "2" * 64,
        "script_sha256": "3" * 64,
        "environment_sha256": "4" * 64,
        "unavailable_fields": ["output_sha256"],
    }

    report = audit_artifact_evidence(envelope)

    assert report["status"] == "blocked"
    assert _finding_codes(report) == {
        "PRODUCER_FAILED",
        "ARTIFACT_INTEGRITY_FAILED",
        "PROVENANCE_INCOMPLETE",
    }
    assert {item["source"] for item in report["findings"]} == {
        "producer",
        "artifact_integrity",
        "provenance",
    }


def test_kernel_recomputes_data_integrity_from_every_detail_check() -> None:
    envelope = _envelope()
    envelope["data_contract_summary"] = _summary(
        "warning",
        ("ordinary-range-check", "passed"),
        ("raw_integrity.strict", "warning"),
    )

    report = audit_artifact_evidence(envelope, policy_packs=[])

    assert report["status"] == "needs_revision"
    assert _finding_codes(report) == {"RAW_OR_DATA_INTEGRITY_WARNING"}
    assert report["findings"][0]["evidence_ref"] == "data_contract_summary.checks[1]"


@pytest.mark.parametrize("check_id", ["statistical_claim_linkage", "evidence_link", "producer-check-17"])
def test_unsupported_claim_linkage_is_an_immutable_hard_gate(check_id: str) -> None:
    envelope = _envelope()
    envelope["calculation_summary"] = _summary(
        "failed",
        (check_id, "failed"),
    )

    report = audit_artifact_evidence(envelope, policy_packs=[])

    assert report["status"] == "blocked"
    assert _finding_codes(report) == {"UNSUPPORTED_CLAIM_OR_CALCULATION_FAILED"}
    assert report["findings"][0]["source"] == "claim_linkage"


def test_alternate_raw_integrity_id_cannot_evade_fail_closed_summary() -> None:
    envelope = _envelope()
    envelope["data_contract_summary"] = _summary("failed", ("checksum-seal-v7", "failed"))

    report = audit_artifact_evidence(envelope)

    assert report["status"] == "blocked"
    assert _finding_codes(report) == {"RAW_OR_DATA_INTEGRITY_FAILED"}


@pytest.mark.parametrize(
    "policy_packs",
    [
        ["unknown-policy"],
        [PUBLICATION_READINESS_POLICY, PUBLICATION_READINESS_POLICY],
        [""],
        "publication-readiness-v1",
    ],
)
def test_policy_pack_selection_is_closed_and_explicit(policy_packs: Any) -> None:
    with pytest.raises(ValueError):
        audit_artifact_evidence(_envelope(), policy_packs=policy_packs)


def test_explicit_publication_policy_delegates_to_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_readiness(evidence: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        calls.append({"evidence": evidence, **kwargs})
        return {
            "readiness_status": "needs_revision",
            "findings": [
                {
                    "code": "LAYOUT_REVIEW",
                    "severity": "major",
                    "source": "layout_report",
                    "message": "Review the selected layout rule.",
                    "evidence_ref": "layout_report.checks[0]",
                    "recommended_action": "Revise the layout.",
                }
            ],
        }

    monkeypatch.setattr("hub_core.artifact_audit.evaluate_publication_readiness", fake_readiness)

    report = audit_artifact_evidence(
        _envelope(),
        policy_packs=[PUBLICATION_READINESS_POLICY],
        project_id="project-a",
        figure_id="figure-1",
    )

    assert len(calls) == 1
    assert calls[0]["project_id"] == "project-a"
    assert calls[0]["figure_id"] == "figure-1"
    assert calls[0]["policy_ids"] == ("publication-readiness-v2",)
    assert report["status"] == "needs_revision"
    assert report["selected_policy_ids"] == [PUBLICATION_READINESS_POLICY]
    assert report["findings"][0]["policy_id"] == PUBLICATION_READINESS_POLICY


def test_publication_policy_applies_real_canonical_projection() -> None:
    envelope = _envelope()
    envelope["measurements"] = [
        {
            "id": "tick_label_overlaps[axis=0]",
            "availability": "available",
            "value": 1,
            "unit": "count",
            "scope": "axis=0",
        }
    ]
    envelope["policy_projections"] = [
        {
            "id": "publication-readiness-v2",
            "version": "2",
            "measurement_refs": ["tick_label_overlaps[axis=0]"],
            "resolved": {"overlap": {"value": "review", "source": "resolved_policy"}},
            "findings": [
                {
                    "code": "TICK_OVERLAP",
                    "metric_id": "tick_label_overlaps[axis=0]",
                    "severity": "advisory",
                    "outcome": "needs_revision",
                    "message": "Tick labels overlap.",
                }
            ],
        }
    ]
    envelope["resolved_policy"] = {
        "id": "publication-readiness-v2",
        "version": "2",
        "source": "caller",
        "parameters": {"overlap": "review"},
    }

    kernel_only = audit_artifact_evidence(copy.deepcopy(envelope), policy_packs=[])
    with_policy = audit_artifact_evidence(
        envelope,
        policy_packs=[PUBLICATION_READINESS_POLICY],
    )

    assert kernel_only["status"] == "needs_review"
    assert kernel_only["findings"] == []
    assert with_policy["status"] == "needs_revision"
    assert "TICK_OVERLAP" in _finding_codes(with_policy)


def test_informational_geometry_under_explicit_policy_is_not_blocking() -> None:
    envelope = _envelope()
    envelope["measurements"] = [
        {
            "id": "geometry.optional_probe",
            "availability": "unavailable",
            "reason": "the optional renderer was not installed",
        }
    ]

    report = audit_artifact_evidence(
        _with_publication_projection(envelope),
        policy_packs=[PUBLICATION_READINESS_POLICY],
    )

    assert report["status"] == "needs_review"
    geometry = [item for item in report["findings"] if item["source"] == "geometry_diagnostics"]
    assert geometry
    assert {item["severity"] for item in geometry} == {"info"}
    assert all(item["policy_id"] == PUBLICATION_READINESS_POLICY for item in geometry)


def test_all_emitted_evidence_text_is_path_sanitized_and_secret_redacted() -> None:
    envelope = _envelope()
    envelope["producer"] = {
        "status": "warning",
        "kind": "test-render",
        "version": "1.0",
        "reason": r"read C:\Users\Alice\private\raw.csv with api_key=SUPERSECRET",
    }
    envelope["artifacts"]["status"] = "warning"
    envelope["artifacts"]["reason"] = r"C:\Users\Alice\private\figure.png token=TOKENVALUE"
    envelope["calculation_summary"] = _summary(
        "warning",
        ("evidence_link", "warning"),
    )
    envelope["calculation_summary"]["checks"][0]["message"] = (
        r"C:\Users\Alice\private\calc.json authorization=Bearer-Secret"
    )

    report = audit_artifact_evidence(envelope)
    rendered = json.dumps(report, ensure_ascii=False)

    assert "C:\\Users\\Alice" not in rendered
    assert "SUPERSECRET" not in rendered
    assert "TOKENVALUE" not in rendered
    assert "Bearer-Secret" not in rendered
    assert "[PATH]" in rendered
    assert "[REDACTED]" in rendered


@pytest.mark.parametrize("detail_count", [400, 800])
def test_large_detail_sets_keep_full_verdict_counts_but_bound_output(detail_count: int) -> None:
    envelope = _envelope()
    envelope["calculation_summary"] = {
        "status": "failed",
        "checks": [
            {"id": "e", "status": "failed", "message": "m"}
            for _ in range(detail_count)
        ],
    }

    report = audit_artifact_evidence(envelope)
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    assert report["status"] == "blocked"
    assert report["summary"]["finding_count"] == detail_count
    assert report["summary"]["findings_returned"] <= 48
    assert report["summary"]["findings_omitted"] == detail_count - len(report["findings"])
    assert report["summary"]["findings_truncated"] is True
    assert len(encoded) <= MAX_AUDIT_OUTPUT_BYTES
    assert report["summary"]["serialized_bytes"] == len(encoded)


def test_summary_is_recomputed_from_findings_not_caller_aggregate() -> None:
    envelope = _envelope()
    envelope["producer"] = {
        "status": "warning",
        "kind": "test-render",
        "version": "1.0",
        "reason": "producer output requires revision",
    }
    envelope["artifacts"]["status"] = "warning"

    report = audit_artifact_evidence(envelope)

    assert report["status"] == "needs_revision"
    assert report["summary"]["status"] == "needs_revision"
    assert report["summary"]["finding_counts"]["major"] == 2
    assert all(item["status"] in {"blocked", "needs_revision", "needs_review"} for item in report["gates"])
