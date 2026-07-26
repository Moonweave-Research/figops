"""Pure deterministic evaluator for publication promotion admission."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from .durable_receipt import DurableReceipt
from .human_review_receipt import (
    HumanReviewReceiptIndex,
    HumanReviewVerificationPolicy,
    build_review_subject,
    verify_human_review_receipt,
)
from .policy_resolution_types import ResolvedPolicySet
from .promotion_gate_receipt import (
    SCHEMA_VERSION,
    build_promotion_gate_receipt,
    canonical_promotion_gate_json_bytes,
    promotion_gate_digest,
)
from .publication_readiness import evidence_digest
from .workflow_intent import WorkflowIntent

GateStatus = str
GateOutcome = str

GATE_CODE_ORDER: Final = (
    "WORKFLOW_PROMOTION_ALLOWED",
    "CANDIDATE_ARTIFACT_BOUND",
    "RUNTIME_MANIFEST_ELIGIBLE",
    "LINEAGE_RECEIPT_VALID",
    "POLICY_RESOLUTION_VALID",
    "PUBLICATION_READINESS_AUTOMATED",
    "HUMAN_REVIEW_SIGNOFF",
)
GATE_CODE_PRECEDENCE: Final = {code: index for index, code in enumerate(GATE_CODE_ORDER)}
GATE_CODE_OWNERS: Final = {
    "WORKFLOW_PROMOTION_ALLOWED": "hub_core.workflow_intent",
    "CANDIDATE_ARTIFACT_BOUND": "hub_core.promotion_gate",
    "RUNTIME_MANIFEST_ELIGIBLE": "hub_core.result_promotion",
    "LINEAGE_RECEIPT_VALID": "hub_core.durable_receipt",
    "POLICY_RESOLUTION_VALID": "hub_core.policy_resolution",
    "PUBLICATION_READINESS_AUTOMATED": "hub_core.publication_readiness",
    "HUMAN_REVIEW_SIGNOFF": "hub_core.human_review_receipt",
}
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_ID_RE: Final = re.compile(r"^(project|result\.figure):[0-9a-f]{32}$")
_PATH_LIKE_ID_RE: Final = re.compile(
    r"^(?:[A-Za-z]:[\\/]|[\\/]{1,2}|~(?:[\\/]|$)|(?:file|https?|runtime|raw):)",
    re.I,
)
_DESTINATION_RE: Final = re.compile(r"^(?!/)(?![A-Za-z]:)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")


@dataclass(frozen=True, slots=True)
class _Gate:
    code: str
    outcome: GateOutcome
    evidence_ref: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "outcome": self.outcome,
            "evidence_ref": self.evidence_ref,
            "message": self.message,
        }


def _sha256(value: Any) -> str | None:
    if isinstance(value, str) and _SHA256_RE.fullmatch(value):
        return value
    return None


def _digest_or_none(value: Mapping[str, Any] | None) -> str | None:
    if value is None:
        return None
    try:
        return promotion_gate_digest(value)
    except Exception:
        return None


def _opaque_id(value: Any, namespace: str) -> str | None:
    if not isinstance(value, str) or _OPAQUE_ID_RE.fullmatch(value) is None:
        return None
    if value.partition(":")[0] != namespace:
        return None
    if _PATH_LIKE_ID_RE.search(value) or ".." in value or "\\" in value or "/" in value:
        return None
    return value


def _gate(code: str, outcome: GateOutcome, evidence_ref: str, message: str) -> _Gate:
    if code not in GATE_CODE_PRECEDENCE:
        raise ValueError(f"unknown promotion gate code: {code}")
    return _Gate(code, outcome, evidence_ref, message)


def _workflow_gate(workflow_intent: WorkflowIntent | Mapping[str, Any]) -> _Gate:
    if not isinstance(workflow_intent, WorkflowIntent):
        return _gate(
            "WORKFLOW_PROMOTION_ALLOWED",
            "blocked",
            "workflow_intent",
            "Workflow intent must be a validated WorkflowIntent instance.",
        )
    intent = workflow_intent.to_dict()
    if intent.get("promotion_allowed") is True and intent.get("fail_closed") is False and intent.get("legacy") is False:
        return _gate(
            "WORKFLOW_PROMOTION_ALLOWED",
            "passed",
            "workflow_intent.promotion_allowed",
            "Workflow intent allows a promotion admission decision.",
        )
    return _gate(
        "WORKFLOW_PROMOTION_ALLOWED",
        "blocked",
        "workflow_intent.promotion_allowed",
        "Only an explicit non-legacy promotion workflow can enter the promotion gate.",
    )


def _candidate_gate(candidate_artifact: Mapping[str, Any]) -> tuple[_Gate, dict[str, str] | None]:
    if not isinstance(candidate_artifact, Mapping):
        return (
            _gate(
                "CANDIDATE_ARTIFACT_BOUND",
                "blocked",
                "candidate_artifact",
                "Candidate artifact evidence is missing or malformed.",
            ),
            None,
        )
    required = {"project_id", "artifact_id", "role", "sha256"}
    if not required <= set(candidate_artifact):
        return (
            _gate(
                "CANDIDATE_ARTIFACT_BOUND",
                "blocked",
                "candidate_artifact",
                "Candidate artifact must declare project_id, artifact_id, role, and sha256.",
            ),
            None,
        )
    digest = _sha256(candidate_artifact.get("sha256"))
    project_id = _opaque_id(candidate_artifact.get("project_id"), "project")
    artifact_id = _opaque_id(candidate_artifact.get("artifact_id"), "result.figure")
    if candidate_artifact.get("role") != "result.figure" or digest is None or project_id is None or artifact_id is None:
        return (
            _gate(
                "CANDIDATE_ARTIFACT_BOUND",
                "blocked",
                "candidate_artifact",
                "Candidate artifact must be a result.figure with opaque IDs and a lowercase SHA-256.",
            ),
            None,
        )
    return (
        _gate(
            "CANDIDATE_ARTIFACT_BOUND",
            "passed",
            "candidate_artifact",
            "Candidate artifact has a stable result.figure identity and digest.",
        ),
        {
            "project_id": project_id,
            "artifact_id": artifact_id,
            "artifact_sha256": digest,
        },
    )


def _primary_artifact_digest(manifest: Mapping[str, Any]) -> str | None:
    evidence = manifest.get("evidence")
    artifacts = evidence.get("artifacts") if isinstance(evidence, Mapping) else None
    entries = artifacts.get("entries") if isinstance(artifacts, Mapping) else None
    if not isinstance(entries, list):
        return None
    primary = [item for item in entries if isinstance(item, Mapping) and item.get("logical_role") == "primary"]
    if len(primary) != 1:
        return None
    return _sha256(primary[0].get("sha256"))


def _runtime_manifest_gate(
    runtime_manifest: Mapping[str, Any],
    candidate: Mapping[str, str] | None,
) -> _Gate:
    if not isinstance(runtime_manifest, Mapping):
        return _gate(
            "RUNTIME_MANIFEST_ELIGIBLE",
            "blocked",
            "runtime_manifest",
            "Runtime manifest eligibility facts are missing or malformed.",
        )
    eligible = (
        runtime_manifest.get("promotion_eligible") is True
        and runtime_manifest.get("publication_status") == "verified"
        and runtime_manifest.get("manual_review_needed") is False
    )
    claim_inventory = runtime_manifest.get("claim_inventory")
    claims = claim_inventory.get("claims") if isinstance(claim_inventory, Mapping) else None
    claims_valid = (
        isinstance(claim_inventory, Mapping)
        and claim_inventory.get("status") == "verified"
        and claim_inventory.get("promotion_eligible") is True
        and claim_inventory.get("manual_review_needed") is False
        and claim_inventory.get("errors") in ([], ())
        and isinstance(claims, list)
        and (bool(claims) or claim_inventory.get("explicit_no_claims") is True)
    )
    primary_digest = _primary_artifact_digest(runtime_manifest)
    matches_candidate = candidate is not None and primary_digest == candidate["artifact_sha256"]
    if eligible and claims_valid and matches_candidate:
        return _gate(
            "RUNTIME_MANIFEST_ELIGIBLE",
            "passed",
            "runtime_manifest.promotion_eligible",
            "Runtime manifest carries the existing machine eligibility facts.",
        )
    return _gate(
        "RUNTIME_MANIFEST_ELIGIBLE",
        "blocked",
        "runtime_manifest",
        "Existing result-promotion eligibility, claim, or primary-artifact facts do not match.",
    )


def _lineage_gate(
    durable_lineage_receipt: DurableReceipt | Mapping[str, Any] | None,
    candidate: Mapping[str, str] | None,
) -> tuple[_Gate, str | None]:
    if durable_lineage_receipt is None:
        return (
            _gate(
                "LINEAGE_RECEIPT_VALID",
                "blocked",
                "durable_lineage_receipt",
                "Durable lineage receipt evidence is missing.",
            ),
            None,
        )
    try:
        receipt = (
            durable_lineage_receipt
            if isinstance(durable_lineage_receipt, DurableReceipt)
            else DurableReceipt.from_dict(durable_lineage_receipt)
        )
        digest = receipt.canonical_sha256()
    except Exception as exc:
        return (
            _gate(
                "LINEAGE_RECEIPT_VALID",
                "blocked",
                "durable_lineage_receipt",
                f"Durable lineage receipt is invalid: {exc}",
            ),
            None,
        )
    if (
        candidate is not None
        and receipt.durable_artifact["role"] == "result.figure"
        and receipt.durable_artifact["sha256"] == candidate["artifact_sha256"]
    ):
        return (
            _gate(
                "LINEAGE_RECEIPT_VALID",
                "passed",
                "durable_lineage_receipt",
                "Durable lineage receipt binds the candidate figure digest.",
            ),
            digest,
        )
    return (
        _gate(
            "LINEAGE_RECEIPT_VALID",
            "blocked",
            "durable_lineage_receipt.durable_artifact",
            "Durable lineage receipt does not bind the candidate result.figure digest.",
        ),
        digest,
    )


def _policy_json(
    resolved_policy: ResolvedPolicySet | Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(resolved_policy, ResolvedPolicySet):
        return None, None
    payload = resolved_policy.to_json()
    return payload, resolved_policy.canonical_sha256()


def _policy_gate(
    resolved_policy: ResolvedPolicySet | Mapping[str, Any] | None,
) -> tuple[_Gate, bool, str | None]:
    payload, digest = _policy_json(resolved_policy)
    if payload is None or digest is None:
        return (
            _gate(
                "POLICY_RESOLUTION_VALID",
                "blocked",
                "resolved_policy",
                "Resolved policy must be a validated ResolvedPolicySet instance.",
            ),
            False,
            None,
        )
    parameters = payload.get("parameters")
    signoff = parameters.get("human_signoff_required") if isinstance(parameters, Mapping) else None
    signoff_value = signoff.get("value") if isinstance(signoff, Mapping) else None
    if payload.get("schema_version") != "figops-resolved-policy-set/1" or not isinstance(signoff_value, bool):
        return (
            _gate(
                "POLICY_RESOLUTION_VALID",
                "blocked",
                "resolved_policy",
                "Resolved policy must be a canonical policy-set projection with human_signoff_required.",
            ),
            False,
            digest,
        )
    return (
        _gate(
            "POLICY_RESOLUTION_VALID",
            "passed",
            "resolved_policy",
            "Resolved policy is canonical and signoff requirement is explicit.",
        ),
        signoff_value,
        digest,
    )


def _readiness_gate(publication_readiness_report: Mapping[str, Any] | None) -> tuple[_Gate, str | None]:
    if not isinstance(publication_readiness_report, Mapping):
        return (
            _gate(
                "PUBLICATION_READINESS_AUTOMATED",
                "blocked",
                "publication_readiness_report",
                "Publication readiness report is missing or malformed.",
            ),
            None,
        )
    try:
        report_digest = promotion_gate_digest(dict(publication_readiness_report))
    except Exception:
        report_digest = None
    evidence = _sha256(publication_readiness_report.get("evidence_digest"))
    status = publication_readiness_report.get("readiness_status")
    if publication_readiness_report.get("schema_version") != "publication_readiness/1" or evidence is None:
        return (
            _gate(
                "PUBLICATION_READINESS_AUTOMATED",
                "blocked",
                "publication_readiness_report",
                "Publication readiness report must expose schema_version and evidence_digest.",
            ),
            report_digest,
        )
    if status == "blocked":
        return (
            _gate(
                "PUBLICATION_READINESS_AUTOMATED",
                "blocked",
                "publication_readiness_report.readiness_status",
                "Required automated publication-readiness evidence is blocked.",
            ),
            report_digest,
        )
    if status == "needs_revision":
        return (
            _gate(
                "PUBLICATION_READINESS_AUTOMATED",
                "needs_revision",
                "publication_readiness_report.readiness_status",
                "Automated publication-readiness findings require revision.",
            ),
            report_digest,
        )
    if status == "needs_review":
        return (
            _gate(
                "PUBLICATION_READINESS_AUTOMATED",
                "passed",
                "publication_readiness_report.readiness_status",
                "Automated readiness evidence has reached the human-review boundary.",
            ),
            report_digest,
        )
    return (
        _gate(
            "PUBLICATION_READINESS_AUTOMATED",
            "blocked",
            "publication_readiness_report.readiness_status",
            "Publication readiness status is outside the closed enum.",
        ),
        report_digest,
    )


def _review_gate(
    *,
    human_signoff_required: bool,
    review_receipt: Mapping[str, Any] | bytes | bytearray | memoryview | None,
    review_policy: HumanReviewVerificationPolicy | None,
    now: datetime | str | None,
    expected_subject: Mapping[str, str] | None,
    receipt_index: HumanReviewReceiptIndex | None,
) -> tuple[_Gate, str | None]:
    if not human_signoff_required:
        return (
            _gate(
                "HUMAN_REVIEW_SIGNOFF",
                "passed",
                "resolved_policy.parameters.human_signoff_required",
                "Selected policy does not require a human signoff receipt.",
            ),
            None,
        )
    if review_receipt is None:
        return (
            _gate(
                "HUMAN_REVIEW_SIGNOFF",
                "needs_review",
                "review_receipt",
                "Selected policy requires a current affirmative human signoff receipt.",
            ),
            None,
        )
    if not isinstance(review_policy, HumanReviewVerificationPolicy):
        return (
            _gate(
                "HUMAN_REVIEW_SIGNOFF",
                "blocked",
                "review_policy",
                "Review receipt requires a validated HumanReviewVerificationPolicy instance.",
            ),
            None,
        )
    try:
        result = verify_human_review_receipt(
            review_receipt,
            policy=review_policy,
            now=now,
            expected_subject=expected_subject,
            receipt_index=receipt_index,
            require_approval=True,
        )
    except Exception:
        return (
            _gate(
                "HUMAN_REVIEW_SIGNOFF",
                "blocked",
                "review_receipt",
                "Human review receipt verification failed closed.",
            ),
            None,
        )
    if result.valid:
        return (
            _gate(
                "HUMAN_REVIEW_SIGNOFF",
                "passed",
                "review_receipt",
                "Human review receipt is current, affirmative, authorized, and subject-bound.",
            ),
            result.canonical_sha256,
        )
    return (
        _gate(
            "HUMAN_REVIEW_SIGNOFF",
            "blocked",
            "review_receipt",
            f"Human review receipt is invalid: {result.reason}",
        ),
        result.canonical_sha256,
    )


def _status(gates: list[_Gate]) -> GateStatus:
    outcomes = [gate.outcome for gate in gates]
    if "blocked" in outcomes:
        return "blocked"
    if "needs_revision" in outcomes:
        return "needs_revision"
    if "needs_review" in outcomes:
        return "needs_review"
    return "eligible"


def _requested_destination(value: str | None) -> tuple[str | None, _Gate | None]:
    if value is None:
        return None, None
    normalized = value.replace("\\", "/").strip()
    if not normalized or _DESTINATION_RE.fullmatch(normalized) is None:
        return normalized, _gate(
            "CANDIDATE_ARTIFACT_BOUND",
            "blocked",
            "requested_destination",
            "Requested destination must be a contained project-relative reference.",
        )
    return normalized, None


def evaluate_promotion_gate(
    *,
    workflow_intent: WorkflowIntent | Mapping[str, Any],
    candidate_artifact: Mapping[str, Any],
    runtime_manifest: Mapping[str, Any],
    durable_lineage_receipt: DurableReceipt | Mapping[str, Any] | None,
    resolved_policy: ResolvedPolicySet | Mapping[str, Any] | None,
    publication_readiness_report: Mapping[str, Any] | None,
    review_receipt: Mapping[str, Any] | bytes | bytearray | memoryview | None = None,
    review_policy: HumanReviewVerificationPolicy | None = None,
    now: datetime | str | None = None,
    receipt_index: HumanReviewReceiptIndex | None = None,
    decision_scope: str = "figure_scientific_and_communication",
    requested_destination: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic promotion-gate report and receipt candidate.

    This function performs no filesystem mutation and never invokes promotion.
    Callers must supply already verified evidence objects.
    """

    destination, destination_gate = _requested_destination(requested_destination)
    candidate_gate, candidate = _candidate_gate(candidate_artifact)
    runtime_gate = _runtime_manifest_gate(runtime_manifest, candidate)
    lineage_gate, lineage_digest = _lineage_gate(durable_lineage_receipt, candidate)
    policy_gate, signoff_required, policy_digest = _policy_gate(resolved_policy)
    readiness_gate, readiness_report_digest = _readiness_gate(publication_readiness_report)
    evidence_sha = (
        _sha256(publication_readiness_report.get("evidence_digest"))
        if isinstance(publication_readiness_report, Mapping)
        else None
    )
    subject = None
    subject_binding_failed = False
    if candidate is not None and lineage_digest is not None and evidence_sha is not None and policy_digest is not None:
        try:
            subject = build_review_subject(
                project_id=candidate["project_id"],
                artifact_id=candidate["artifact_id"],
                artifact_sha256=candidate["artifact_sha256"],
                lineage_receipt_sha256=lineage_digest,
                evidence_digest=evidence_sha,
                resolved_policy_digest=policy_digest,
                decision_scope=decision_scope,
            )
        except Exception:
            subject = None
            subject_binding_failed = True
    if subject_binding_failed:
        review_gate, review_digest = (
            _gate(
                "HUMAN_REVIEW_SIGNOFF",
                "blocked",
                "review_subject",
                "Review subject binding failed.",
            ),
            None,
        )
    else:
        review_gate, review_digest = _review_gate(
            human_signoff_required=signoff_required,
            review_receipt=review_receipt,
            review_policy=review_policy,
            now=now,
            expected_subject=subject,
            receipt_index=receipt_index,
        )
    gates = [
        _workflow_gate(workflow_intent),
        candidate_gate,
        runtime_gate,
        lineage_gate,
        policy_gate,
        readiness_gate,
        review_gate,
    ]
    if destination_gate is not None:
        gates[GATE_CODE_PRECEDENCE[destination_gate.code]] = destination_gate
    gates.sort(key=lambda item: GATE_CODE_PRECEDENCE[item.code])
    gate_status = _status(gates)
    gates_payload = [gate.as_dict() for gate in gates]
    digests = {
        "lineage_receipt_sha256": lineage_digest,
        "publication_evidence_sha256": evidence_sha,
        "resolved_policy_sha256": policy_digest,
        "review_receipt_sha256": review_digest,
    }
    report_payload = {
        "schema_version": SCHEMA_VERSION,
        "gate_status": gate_status,
        "subject": subject,
        "digests": {**digests, "readiness_report_sha256": readiness_report_digest},
        "gates": gates_payload,
        "requested_destination": destination,
    }
    report_sha = promotion_gate_digest(report_payload)
    receipt_digests = {
        "report_sha256": report_sha,
        **digests,
    }
    receipt = build_promotion_gate_receipt(
        gate_status=gate_status,
        subject=subject,
        digests=receipt_digests,
        gates=gates_payload,
        requested_destination=destination,
    )
    return {
        **report_payload,
        "report_sha256": report_sha,
        "receipt_candidate": receipt,
    }


def evaluate_promotion_gate_from_evidence(
    *,
    publication_evidence: Mapping[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Compatibility helper for callers that have normalized evidence but no report.

    It records the normalized evidence digest only; callers that need full
    readiness findings should pass ``publication_readiness_report`` directly.
    """

    digest = evidence_digest(publication_evidence)
    report = {
        "schema_version": "publication_readiness/1",
        "readiness_status": "needs_review",
        "evidence_digest": digest,
        "manual_review_required": True,
        "gates": [],
        "findings": [],
    }
    return evaluate_promotion_gate(publication_readiness_report=report, **kwargs)


def render_promotion_gate_json(report: Mapping[str, Any]) -> str:
    """Render a byte-stable, human-readable JSON report."""

    return canonical_promotion_gate_json_bytes(dict(report)).decode("utf-8") + "\n"


__all__ = [
    "GATE_CODE_ORDER",
    "GATE_CODE_OWNERS",
    "GATE_CODE_PRECEDENCE",
    "GateOutcome",
    "GateStatus",
    "evaluate_promotion_gate",
    "evaluate_promotion_gate_from_evidence",
    "render_promotion_gate_json",
]
