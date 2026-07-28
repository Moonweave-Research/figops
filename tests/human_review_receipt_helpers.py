from __future__ import annotations

from typing import Any

from hub_core.human_review_receipt import (
    HumanReviewAuthorityBinding,
    HumanReviewVerificationPolicy,
    HumanReviewWaiverBinding,
    build_human_review_receipt,
    build_review_subject,
    build_reviewer,
    opaque_concern_id,
    opaque_figure_artifact_id,
    opaque_principal_id,
    opaque_project_id,
    opaque_waiver_id,
)

DEFAULT_SCOPE = "figure_scientific_and_communication"
DEFAULT_AUTHORITY = "lab-policy/1"


def subject(decision_scope: str = DEFAULT_SCOPE) -> dict[str, str]:
    return build_review_subject(
        project_id=opaque_project_id("project-17"),
        artifact_id=opaque_figure_artifact_id("figure-1.svg"),
        artifact_sha256="1" * 64,
        lineage_receipt_sha256="2" * 64,
        evidence_digest="3" * 64,
        resolved_policy_digest="4" * 64,
        decision_scope=decision_scope,
    )


def reviewer(
    principal_source: str = "reviewer@example.invalid",
    *,
    role: str = "scientific_reviewer",
) -> dict[str, str]:
    return build_reviewer(
        principal_id=opaque_principal_id(principal_source),
        role=role,
        authority_assertion=DEFAULT_AUTHORITY,
    )


def policy(
    *,
    allow_local_attestation: bool = True,
    role: str = "scientific_reviewer",
    authority: str = DEFAULT_AUTHORITY,
    waiver_bindings: frozenset[HumanReviewWaiverBinding] = frozenset(),
) -> HumanReviewVerificationPolicy:
    return HumanReviewVerificationPolicy(
        allow_local_attestation=allow_local_attestation,
        reviewer_bindings=frozenset(
            {
                HumanReviewAuthorityBinding(
                    decision_scope=DEFAULT_SCOPE,
                    reviewer_role=role,
                    authority_assertion=authority,
                )
            }
        ),
        waiver_bindings=waiver_bindings,
    )


def receipt(**overrides: object) -> dict[str, Any]:
    decision_scope = str(overrides.pop("decision_scope", DEFAULT_SCOPE))
    payload: dict[str, Any] = {
        "decision": "approve_for_promotion",
        "decision_scope": decision_scope,
        "subject": overrides.pop("subject", subject(decision_scope)),
        "reviewer": reviewer(),
        "reviewed_at": "2026-07-20T00:00:00Z",
        "expires_at": "2026-10-18T00:00:00Z",
        "concerns": [],
        "waivers": [],
        "supersedes": None,
    }
    payload.update(overrides)
    return build_human_review_receipt(**payload)


def advisory_waiver_fixture() -> tuple[dict[str, str], dict[str, str], HumanReviewWaiverBinding]:
    review_subject = subject()
    concern_id = opaque_concern_id("color-waiver")
    concern = {
        "concern_id": concern_id,
        "category": "accessibility",
        "severity": "advisory",
        "status": "waived",
        "subject_digest": review_subject["subject_digest"],
        "finding_digest": "5" * 64,
    }
    waiver = {
        "waiver_id": opaque_waiver_id("color-waiver-approval"),
        "concern_id": concern_id,
        "policy_rule": DEFAULT_AUTHORITY,
        "rationale_digest": "6" * 64,
        "authorized_principal_id": opaque_principal_id("pi@example.invalid"),
        "authorized_role": "principal_investigator",
        "subject_digest": review_subject["subject_digest"],
        "expires_at": "2026-09-01T00:00:00Z",
    }
    binding = HumanReviewWaiverBinding(
        policy_rule=DEFAULT_AUTHORITY,
        authorized_role="principal_investigator",
        concern_category="accessibility",
        concern_severity="advisory",
    )
    return concern, waiver, binding
