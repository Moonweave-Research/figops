from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from hub_core.durable_receipt import DurableReceipt, opaque_artifact_id, opaque_claim_id, opaque_receipt_id
from hub_core.human_review_receipt import (
    HumanReviewAuthorityBinding,
    HumanReviewVerificationPolicy,
    build_human_review_receipt,
    build_review_subject,
    build_reviewer,
    opaque_figure_artifact_id,
    opaque_principal_id,
    opaque_project_id,
)
from hub_core.policy_resolution import resolve_policy_set
from hub_core.promotion_gate import GATE_CODE_ORDER, evaluate_promotion_gate
from hub_core.promotion_gate_receipt import (
    PromotionGateReceiptError,
    build_promotion_gate_receipt,
    canonical_promotion_gate_receipt_bytes,
    promotion_gate_digest,
    validate_promotion_gate_receipt,
)
from hub_core.workflow_intent import infer_workflow_intent

ARTIFACT_SHA = "1" * 64
EVIDENCE_SHA = "2" * 64
DEFAULT_SCOPE = "figure_scientific_and_communication"
DEFAULT_AUTHORITY = "lab-policy/1"


def _layer(source: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": source,
        "policy_id": f"{source}-policy",
        "version": "1",
        "parameters": parameters,
    }


def _candidate(artifact_sha: str = ARTIFACT_SHA) -> dict[str, str]:
    return {
        "project_id": opaque_project_id("project-17"),
        "artifact_id": opaque_figure_artifact_id("figure-1.png"),
        "role": "result.figure",
        "sha256": artifact_sha,
    }


def _manifest(artifact_sha: str = ARTIFACT_SHA) -> dict[str, Any]:
    return {
        "publication_status": "verified",
        "promotion_eligible": True,
        "manual_review_needed": False,
        "evidence": {
            "artifacts": {
                "entries": [
                    {
                        "logical_role": "primary",
                        "sha256": artifact_sha,
                    }
                ]
            }
        },
        "claim_inventory": {
            "schema_version": "figops_claim_inventory/1",
            "status": "verified",
            "promotion_eligible": True,
            "manual_review_needed": False,
            "errors": [],
            "claims": [],
            "explicit_no_claims": True,
        },
    }


def _lineage(artifact_sha: str = ARTIFACT_SHA) -> DurableReceipt:
    figure = {
        "artifact_id": opaque_artifact_id("result.figure", "figure-1.png"),
        "role": "result.figure",
        "sha256": artifact_sha,
    }
    return DurableReceipt(
        figops_version="0.20.0",
        run_id=opaque_receipt_id("run", "job-1"),
        timestamp="2026-07-20T00:00:00Z",
        git_sha256="3" * 64,
        config_sha256="4" * 64,
        script_sha256="5" * 64,
        environment_lock_sha256="6" * 64,
        durable_artifact=figure,
        input_artifacts=[
            {
                "artifact_id": opaque_artifact_id("raw", "input-set"),
                "role": "raw",
                "sha256": "7" * 64,
            }
        ],
        output_artifacts=[figure],
        claim_ids=[opaque_claim_id("explicit-no-claims")],
    )


def _policy(*, human_signoff_required: bool):
    return resolve_policy_set([_layer("project", {"human_signoff_required": human_signoff_required})])


def _readiness(status: str = "needs_review", evidence_sha: str = EVIDENCE_SHA) -> dict[str, Any]:
    return {
        "schema_version": "publication_readiness/1",
        "readiness_status": status,
        "evidence_digest": evidence_sha,
        "manual_review_required": True,
        "gates": [],
        "findings": [],
    }


def _review_policy() -> HumanReviewVerificationPolicy:
    return HumanReviewVerificationPolicy(
        allow_local_attestation=True,
        reviewer_bindings=frozenset(
            {
                HumanReviewAuthorityBinding(
                    decision_scope=DEFAULT_SCOPE,
                    reviewer_role="scientific_reviewer",
                    authority_assertion=DEFAULT_AUTHORITY,
                )
            }
        ),
    )


def _review(candidate: dict[str, str], lineage: DurableReceipt, policy) -> dict[str, Any]:
    subject = build_review_subject(
        project_id=candidate["project_id"],
        artifact_id=candidate["artifact_id"],
        artifact_sha256=candidate["sha256"],
        lineage_receipt_sha256=lineage.canonical_sha256(),
        evidence_digest=EVIDENCE_SHA,
        resolved_policy_digest=policy.canonical_sha256(),
        decision_scope=DEFAULT_SCOPE,
    )
    return build_human_review_receipt(
        decision="approve_for_promotion",
        decision_scope=DEFAULT_SCOPE,
        subject=subject,
        reviewer=build_reviewer(
            principal_id=opaque_principal_id("reviewer@example.invalid"),
            role="scientific_reviewer",
            authority_assertion=DEFAULT_AUTHORITY,
        ),
        reviewed_at="2026-07-20T00:00:00Z",
        expires_at="2026-10-18T00:00:00Z",
        concerns=[],
        waivers=[],
        supersedes=None,
    )


def _valid_receipt_kwargs() -> dict[str, Any]:
    candidate = _candidate()
    lineage = _lineage()
    policy = _policy(human_signoff_required=False)
    subject = build_review_subject(
        project_id=candidate["project_id"],
        artifact_id=candidate["artifact_id"],
        artifact_sha256=candidate["sha256"],
        lineage_receipt_sha256=lineage.canonical_sha256(),
        evidence_digest=EVIDENCE_SHA,
        resolved_policy_digest=policy.canonical_sha256(),
        decision_scope=DEFAULT_SCOPE,
    )
    return {
        "gate_status": "eligible",
        "subject": subject,
        "digests": {
            "report_sha256": "9" * 64,
            "lineage_receipt_sha256": lineage.canonical_sha256(),
            "publication_evidence_sha256": EVIDENCE_SHA,
            "resolved_policy_sha256": policy.canonical_sha256(),
            "review_receipt_sha256": None,
        },
        "gates": [
            {
                "code": code,
                "outcome": "passed",
                "evidence_ref": code.lower(),
                "message": "passed",
            }
            for code in GATE_CODE_ORDER
        ],
        "requested_destination": "results/publication/Fig1.png",
    }


def _base_kwargs(*, signoff_required: bool = True) -> dict[str, Any]:
    candidate = _candidate()
    lineage = _lineage()
    policy = _policy(human_signoff_required=signoff_required)
    return {
        "workflow_intent": infer_workflow_intent(requested_intent="promotion"),
        "candidate_artifact": candidate,
        "runtime_manifest": _manifest(),
        "durable_lineage_receipt": lineage,
        "resolved_policy": policy,
        "publication_readiness_report": _readiness(),
        "review_policy": _review_policy(),
        "now": "2026-07-21T00:00:00Z",
    }


def test_valid_signoff_required_gate_is_eligible_and_receipt_bytes_are_stable() -> None:
    candidate = _candidate()
    lineage = _lineage()
    policy = _policy(human_signoff_required=True)
    review = _review(candidate, lineage, policy)

    report = evaluate_promotion_gate(
        workflow_intent=infer_workflow_intent(requested_intent="promotion"),
        candidate_artifact=candidate,
        runtime_manifest=_manifest(),
        durable_lineage_receipt=lineage,
        resolved_policy=policy,
        publication_readiness_report=_readiness(),
        review_receipt=review,
        review_policy=_review_policy(),
        now="2026-07-21T00:00:00Z",
        requested_destination="results/publication/Fig1.png",
    )
    repeated = evaluate_promotion_gate(
        workflow_intent=infer_workflow_intent(requested_intent="promotion"),
        candidate_artifact=dict(reversed(list(candidate.items()))),
        runtime_manifest=_manifest(),
        durable_lineage_receipt=lineage.to_dict(),
        resolved_policy=policy,
        publication_readiness_report=dict(reversed(list(_readiness().items()))),
        review_receipt=json.loads(json.dumps(review)),
        review_policy=_review_policy(),
        now="2026-07-21T00:00:00Z",
        requested_destination="results/publication/Fig1.png",
    )

    assert report["gate_status"] == "eligible"
    assert [gate["code"] for gate in report["gates"]] == list(GATE_CODE_ORDER)
    assert canonical_promotion_gate_receipt_bytes(report["receipt_candidate"]) == (
        canonical_promotion_gate_receipt_bytes(repeated["receipt_candidate"])
    )
    validated = validate_promotion_gate_receipt(report["receipt_candidate"])
    payload_digest = promotion_gate_digest(
        {key: validated[key] for key in validated if key not in {"receipt_id", "integrity"}}
    )
    assert validated["receipt_id"] == f"promotion-gate:sha256:{payload_digest}"
    assert hashlib.sha256(canonical_promotion_gate_receipt_bytes(validated)).hexdigest()


def test_missing_required_signoff_remains_needs_review_and_never_eligible() -> None:
    report = evaluate_promotion_gate(**_base_kwargs(signoff_required=True))

    signoff_gate = next(gate for gate in report["gates"] if gate["code"] == "HUMAN_REVIEW_SIGNOFF")
    assert report["gate_status"] == "needs_review"
    assert signoff_gate["outcome"] == "needs_review"
    assert report["receipt_candidate"]["gate_status"] == "needs_review"


def test_invalid_review_receipt_blocks_with_verifier_reason() -> None:
    candidate = _candidate()
    lineage = _lineage()
    policy = _policy(human_signoff_required=True)
    mismatched_review = _review({**candidate, "sha256": "8" * 64}, lineage, policy)

    report = evaluate_promotion_gate(
        workflow_intent=infer_workflow_intent(requested_intent="promotion"),
        candidate_artifact=candidate,
        runtime_manifest=_manifest(),
        durable_lineage_receipt=lineage,
        resolved_policy=policy,
        publication_readiness_report=_readiness(),
        review_receipt=mismatched_review,
        review_policy=_review_policy(),
        now="2026-07-21T00:00:00Z",
    )

    signoff_gate = next(gate for gate in report["gates"] if gate["code"] == "HUMAN_REVIEW_SIGNOFF")
    assert report["gate_status"] == "blocked"
    assert signoff_gate["outcome"] == "blocked"
    assert "subject_mismatch" in signoff_gate["message"]


def test_missing_lineage_and_policy_evidence_block_in_declared_precedence_order() -> None:
    report = evaluate_promotion_gate(
        workflow_intent=infer_workflow_intent(requested_intent="promotion"),
        candidate_artifact=_candidate(),
        runtime_manifest=_manifest(),
        durable_lineage_receipt=None,
        resolved_policy=None,
        publication_readiness_report=_readiness(),
        now="2026-07-21T00:00:00Z",
    )

    failed_codes = [gate["code"] for gate in report["gates"] if gate["outcome"] == "blocked"]
    assert report["gate_status"] == "blocked"
    assert failed_codes == ["LINEAGE_RECEIPT_VALID", "POLICY_RESOLUTION_VALID"]


def test_automated_needs_revision_takes_precedence_over_missing_optional_signoff() -> None:
    report = evaluate_promotion_gate(
        **{
            **_base_kwargs(signoff_required=False),
            "publication_readiness_report": _readiness("needs_revision"),
        }
    )

    assert report["gate_status"] == "needs_revision"
    readiness_gate = next(gate for gate in report["gates"] if gate["code"] == "PUBLICATION_READINESS_AUTOMATED")
    assert readiness_gate["outcome"] == "needs_revision"


@pytest.mark.parametrize(
    ("field", "replacement", "blocked_code"),
    [
        (
            "workflow_intent",
            infer_workflow_intent(requested_intent="promotion").to_dict(),
            "WORKFLOW_PROMOTION_ALLOWED",
        ),
        ("resolved_policy", _policy(human_signoff_required=False).to_json(), "POLICY_RESOLUTION_VALID"),
    ],
)
def test_forged_policy_or_workflow_mappings_fail_closed(
    field: str,
    replacement: dict[str, Any],
    blocked_code: str,
) -> None:
    report = evaluate_promotion_gate(
        **{
            **_base_kwargs(signoff_required=False),
            field: replacement,
        }
    )

    gate = next(item for item in report["gates"] if item["code"] == blocked_code)
    assert report["gate_status"] == "blocked"
    assert gate["outcome"] == "blocked"


@pytest.mark.parametrize(
    "claim_inventory",
    [
        {
            "schema_version": "figops_claim_inventory/1",
            "status": "verified",
            "promotion_eligible": True,
            "manual_review_needed": False,
            "errors": [],
            "explicit_no_claims": True,
        },
        {
            "schema_version": "figops_claim_inventory/1",
            "status": "verified",
            "promotion_eligible": True,
            "manual_review_needed": False,
            "errors": [],
            "claims": [],
            "explicit_no_claims": False,
        },
    ],
)
def test_incomplete_claim_inventory_blocks_existing_machine_eligibility(claim_inventory: dict[str, Any]) -> None:
    manifest = _manifest()
    manifest["claim_inventory"] = claim_inventory

    report = evaluate_promotion_gate(
        **{
            **_base_kwargs(signoff_required=False),
            "runtime_manifest": manifest,
        }
    )

    runtime_gate = next(gate for gate in report["gates"] if gate["code"] == "RUNTIME_MANIFEST_ELIGIBLE")
    assert report["gate_status"] == "blocked"
    assert runtime_gate["outcome"] == "blocked"


@pytest.mark.parametrize(
    "claim_inventory",
    [
        {
            "schema_version": "figops_claim_inventory/1",
            "status": "verified",
            "promotion_eligible": True,
            "errors": [],
            "claims": [{"claim_id": "claim-1"}],
        },
        {
            "schema_version": "figops_claim_inventory/1",
            "status": "verified",
            "promotion_eligible": True,
            "manual_review_needed": False,
            "claims": [{"claim_id": "claim-1"}],
        },
    ],
)
def test_nonempty_claim_inventory_missing_review_or_errors_fields_blocks(claim_inventory: dict[str, Any]) -> None:
    manifest = _manifest()
    manifest["claim_inventory"] = claim_inventory

    report = evaluate_promotion_gate(
        **{
            **_base_kwargs(signoff_required=False),
            "runtime_manifest": manifest,
        }
    )

    runtime_gate = next(gate for gate in report["gates"] if gate["code"] == "RUNTIME_MANIFEST_ELIGIBLE")
    assert report["gate_status"] == "blocked"
    assert runtime_gate["outcome"] == "blocked"


def test_receipt_status_cannot_be_forged_against_gate_outcome_precedence() -> None:
    blocked_gate_kwargs = _valid_receipt_kwargs()
    blocked_gate_kwargs["gates"][0] = {
        **blocked_gate_kwargs["gates"][0],
        "outcome": "blocked",
    }
    with pytest.raises(PromotionGateReceiptError, match="derived gate outcome precedence"):
        build_promotion_gate_receipt(**blocked_gate_kwargs)

    false_blocked_kwargs = _valid_receipt_kwargs()
    false_blocked_kwargs["gate_status"] = "blocked"
    with pytest.raises(PromotionGateReceiptError, match="derived gate outcome precedence"):
        build_promotion_gate_receipt(**false_blocked_kwargs)


def test_eligible_receipt_requires_bound_subject_and_required_digests() -> None:
    no_subject = _valid_receipt_kwargs()
    no_subject["subject"] = None
    with pytest.raises(PromotionGateReceiptError, match="bound subject"):
        build_promotion_gate_receipt(**no_subject)

    missing_digests = _valid_receipt_kwargs()
    for field in ("lineage_receipt_sha256", "publication_evidence_sha256", "resolved_policy_sha256"):
        forged = {
            **missing_digests,
            "digests": {
                **missing_digests["digests"],
                field: None,
            },
        }
        with pytest.raises(PromotionGateReceiptError, match=f"digests.{field}"):
            build_promotion_gate_receipt(**forged)


@pytest.mark.parametrize(
    ("digest_field", "expected_subject_field"),
    [
        ("lineage_receipt_sha256", "lineage_receipt_sha256"),
        ("publication_evidence_sha256", "evidence_digest"),
        ("resolved_policy_sha256", "resolved_policy_digest"),
    ],
)
def test_receipt_subject_digest_bindings_must_match_receipt_digests(
    digest_field: str,
    expected_subject_field: str,
) -> None:
    forged = _valid_receipt_kwargs()
    forged["digests"] = {
        **forged["digests"],
        digest_field: "0" * 64,
    }

    with pytest.raises(PromotionGateReceiptError, match=f"subject.{expected_subject_field}"):
        build_promotion_gate_receipt(**forged)


@pytest.mark.parametrize("destination", ["/tmp/x", "C:/secret", "../publication/Fig1.png", "runtime:job/Fig1.png"])
def test_receipt_requested_destination_rejects_absolute_uri_and_traversal(destination: str) -> None:
    with pytest.raises(PromotionGateReceiptError, match="requested_destination"):
        build_promotion_gate_receipt(**{**_valid_receipt_kwargs(), "requested_destination": destination})

    receipt = build_promotion_gate_receipt(**_valid_receipt_kwargs())
    receipt["requested_destination"] = destination
    with pytest.raises(PromotionGateReceiptError, match="requested_destination"):
        validate_promotion_gate_receipt(receipt)


def test_receipt_gate_codes_are_closed_and_gate_text_rejects_path_like_leaks() -> None:
    unknown_code = _valid_receipt_kwargs()
    unknown_code["gates"][0] = {**unknown_code["gates"][0], "code": "FUTURE_GATE"}
    with pytest.raises(PromotionGateReceiptError, match="closed enum"):
        build_promotion_gate_receipt(**unknown_code)

    leaky_message = _valid_receipt_kwargs()
    leaky_message["gates"][0] = {**leaky_message["gates"][0], "message": "see C:/secret"}
    with pytest.raises(PromotionGateReceiptError, match="path|URI"):
        build_promotion_gate_receipt(**leaky_message)


def test_receipt_gate_array_must_use_canonical_precedence_order() -> None:
    reversed_gates = _valid_receipt_kwargs()
    reversed_gates["gates"] = list(reversed(reversed_gates["gates"]))

    with pytest.raises(PromotionGateReceiptError, match="canonical promotion gate order"):
        build_promotion_gate_receipt(**reversed_gates)


def test_invalid_decision_scope_blocks_instead_of_eligible_without_subject() -> None:
    report = evaluate_promotion_gate(
        **{
            **_base_kwargs(signoff_required=False),
            "decision_scope": "not_a_supported_scope",
        }
    )

    review_gate = next(gate for gate in report["gates"] if gate["code"] == "HUMAN_REVIEW_SIGNOFF")
    assert report["gate_status"] == "blocked"
    assert report["subject"] is None
    assert report["receipt_candidate"]["subject"] is None
    assert review_gate["outcome"] == "blocked"
    assert review_gate["evidence_ref"] == "review_subject"


@pytest.mark.parametrize(
    ("override", "expected_message"),
    [
        ({"review_policy": {"allow_local_attestation": True}}, "HumanReviewVerificationPolicy"),
        ({"now": []}, "invalid"),
        ({"receipt_index": {}}, "invalid"),
    ],
)
def test_malformed_review_verification_inputs_fail_closed(override: dict[str, Any], expected_message: str) -> None:
    candidate = _candidate()
    lineage = _lineage()
    policy = _policy(human_signoff_required=True)
    report = evaluate_promotion_gate(
        **{
            **_base_kwargs(signoff_required=True),
            "review_receipt": _review(candidate, lineage, policy),
            **override,
        }
    )

    review_gate = next(gate for gate in report["gates"] if gate["code"] == "HUMAN_REVIEW_SIGNOFF")
    assert report["gate_status"] == "blocked"
    assert review_gate["outcome"] == "blocked"
    assert expected_message in review_gate["message"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_id", "C:/secret"),
        ("artifact_id", "/tmp/x"),
        ("artifact_id", "runtime:job/Fig1.png"),
    ],
)
def test_receipt_subject_rejects_path_like_or_non_opaque_ids(field: str, value: str) -> None:
    candidate = _candidate()
    lineage = _lineage()
    policy = _policy(human_signoff_required=False)
    subject = build_review_subject(
        project_id=candidate["project_id"],
        artifact_id=candidate["artifact_id"],
        artifact_sha256=candidate["sha256"],
        lineage_receipt_sha256=lineage.canonical_sha256(),
        evidence_digest=EVIDENCE_SHA,
        resolved_policy_digest=policy.canonical_sha256(),
        decision_scope=DEFAULT_SCOPE,
    )
    subject[field] = value

    with pytest.raises(PromotionGateReceiptError, match="opaque|path|URI|runtime"):
        build_promotion_gate_receipt(
            gate_status="eligible",
            subject=subject,
            digests={
                "report_sha256": "9" * 64,
                "lineage_receipt_sha256": lineage.canonical_sha256(),
                "publication_evidence_sha256": EVIDENCE_SHA,
                "resolved_policy_sha256": policy.canonical_sha256(),
                "review_receipt_sha256": None,
            },
            gates=[
                {
                    "code": code,
                    "outcome": "passed",
                    "evidence_ref": code.lower(),
                    "message": "passed",
                }
                for code in GATE_CODE_ORDER
            ],
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_id", "C:/secret"),
        ("artifact_id", "/tmp/x"),
        ("artifact_id", "result.figure:nothex"),
    ],
)
def test_path_like_candidate_ids_fail_closed_before_receipt_subject_binding(field: str, value: str) -> None:
    candidate = _candidate()
    candidate[field] = value
    report = evaluate_promotion_gate(
        **{
            **_base_kwargs(signoff_required=False),
            "candidate_artifact": candidate,
        }
    )

    candidate_gate = next(gate for gate in report["gates"] if gate["code"] == "CANDIDATE_ARTIFACT_BOUND")
    assert report["gate_status"] == "blocked"
    assert candidate_gate["outcome"] == "blocked"
    assert report["subject"] is None
    assert report["receipt_candidate"]["subject"] is None
