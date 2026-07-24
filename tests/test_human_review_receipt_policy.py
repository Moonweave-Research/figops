from __future__ import annotations

import pytest

from hub_core.human_review_receipt import (
    HumanReviewAuthorityBinding,
    HumanReviewReceiptError,
    HumanReviewReceiptIndex,
    HumanReviewVerificationPolicy,
    HumanReviewWaiverBinding,
    opaque_concern_id,
    opaque_principal_id,
    opaque_waiver_id,
    verify_human_review_receipt,
)
from tests.human_review_receipt_helpers import DEFAULT_AUTHORITY, advisory_waiver_fixture, policy, receipt, subject


def test_local_attestation_allowed_is_not_sufficient_without_reviewer_binding() -> None:
    review = receipt()
    denied = verify_human_review_receipt(
        review,
        policy=HumanReviewVerificationPolicy(allow_local_attestation=True),
        now="2026-07-21T00:00:00Z",
    )

    assert not denied.valid
    assert denied.reason == "reviewer_not_authorized"


def test_reviewer_role_scope_and_authority_must_match_policy_binding() -> None:
    review = receipt()
    wrong_scope = HumanReviewVerificationPolicy(
        allow_local_attestation=True,
        reviewer_bindings=frozenset(
            {
                HumanReviewAuthorityBinding(
                    decision_scope="figure_visual_communication",
                    reviewer_role="scientific_reviewer",
                    authority_assertion=DEFAULT_AUTHORITY,
                )
            }
        ),
    )
    wrong_role = policy(role="principal_investigator")
    wrong_authority = policy(authority="publication-policy/1")

    assert verify_human_review_receipt(review, policy=wrong_scope, now="2026-07-21T00:00:00Z").reason == (
        "reviewer_not_authorized"
    )
    assert verify_human_review_receipt(review, policy=wrong_role, now="2026-07-21T00:00:00Z").reason == (
        "reviewer_not_authorized"
    )
    assert verify_human_review_receipt(review, policy=wrong_authority, now="2026-07-21T00:00:00Z").reason == (
        "reviewer_not_authorized"
    )


def test_local_attestation_permission_is_still_required_after_reviewer_binding() -> None:
    review = receipt()
    denied = verify_human_review_receipt(
        review,
        policy=policy(allow_local_attestation=False),
        now="2026-07-21T00:00:00Z",
    )
    allowed = verify_human_review_receipt(review, policy=policy(), now="2026-07-21T00:00:00Z")

    assert denied.reason == "local_attestation_not_allowed"
    assert not denied.valid
    assert allowed.valid


def test_expired_non_approval_and_index_states_fail_verification() -> None:
    expired = verify_human_review_receipt(
        receipt(expires_at="2026-07-21T00:00:00Z"),
        policy=policy(),
        now="2026-07-21T00:00:00Z",
    )
    revision = verify_human_review_receipt(
        receipt(decision="request_revision"),
        policy=policy(),
        now="2026-07-21T00:00:00Z",
    )
    review = receipt()
    revoked = verify_human_review_receipt(
        review,
        policy=policy(),
        now="2026-07-21T00:00:00Z",
        receipt_index=HumanReviewReceiptIndex(revoked_receipt_ids=frozenset({review["receipt_id"]})),
    )

    assert expired.reason == "expired"
    assert revision.reason == "decision_not_approval"
    assert revoked.reason == "revoked"


def test_advisory_waiver_requires_policy_authorized_binding() -> None:
    concern, waiver, binding = advisory_waiver_fixture()
    review = receipt(subject=subject(), concerns=[concern], waivers=[waiver])
    no_waiver_policy = policy()
    wrong_rule_policy = policy(
        waiver_bindings=frozenset(
            {
                HumanReviewWaiverBinding(
                    policy_rule="publication-policy/1",
                    authorized_role="principal_investigator",
                    concern_category="accessibility",
                    concern_severity="advisory",
                )
            }
        )
    )
    authorized_policy = policy(waiver_bindings=frozenset({binding}))

    assert verify_human_review_receipt(review, policy=no_waiver_policy, now="2026-08-01T00:00:00Z").reason == (
        "waiver_not_authorized"
    )
    assert verify_human_review_receipt(review, policy=wrong_rule_policy, now="2026-08-01T00:00:00Z").reason == (
        "waiver_not_authorized"
    )
    assert verify_human_review_receipt(review, policy=authorized_policy, now="2026-08-01T00:00:00Z").valid
    assert verify_human_review_receipt(review, policy=authorized_policy, now="2026-09-01T00:00:00Z").reason == (
        "waiver_expired"
    )


def test_waiver_policy_rule_requires_explicit_positive_numeric_version() -> None:
    concern, waiver, binding = advisory_waiver_fixture()
    waiver["policy_rule"] = "lab-policy"
    with pytest.raises(HumanReviewReceiptError, match="versioned policy binding token"):
        receipt(subject=subject(), concerns=[concern], waivers=[waiver])

    review = receipt()
    malformed_policy = policy(
        waiver_bindings=frozenset(
            {
                HumanReviewWaiverBinding(
                    policy_rule="lab-policy",
                    authorized_role=binding.authorized_role,
                    concern_category=binding.concern_category,
                    concern_severity=binding.concern_severity,
                )
            }
        )
    )
    result = verify_human_review_receipt(review, policy=malformed_policy, now="2026-07-21T00:00:00Z")
    assert not result.valid
    assert "verification policy waiver policy_rule" in result.reason


def test_required_scientific_concern_cannot_be_waived_at_receipt_validation() -> None:
    review_subject = subject()
    concern_id = opaque_concern_id("required-scientific")
    concern = {
        "concern_id": concern_id,
        "category": "scientific",
        "severity": "required",
        "status": "waived",
        "subject_digest": review_subject["subject_digest"],
        "finding_digest": "5" * 64,
    }
    waiver = {
        "waiver_id": opaque_waiver_id("blocked-required-scientific-waiver"),
        "concern_id": concern_id,
        "policy_rule": DEFAULT_AUTHORITY,
        "rationale_digest": "6" * 64,
        "authorized_principal_id": opaque_principal_id("pi@example.invalid"),
        "authorized_role": "principal_investigator",
        "subject_digest": review_subject["subject_digest"],
        "expires_at": "2026-09-01T00:00:00Z",
    }

    with pytest.raises(HumanReviewReceiptError, match="required scientific concerns cannot be waived"):
        receipt(subject=review_subject, concerns=[concern], waivers=[waiver])


def test_unresolved_approval_concern_is_rejected() -> None:
    review_subject = subject()
    concern = {
        "concern_id": opaque_concern_id("axis-label-units"),
        "category": "communication",
        "severity": "required",
        "status": "unresolved",
        "subject_digest": review_subject["subject_digest"],
        "finding_digest": "5" * 64,
    }

    with pytest.raises(HumanReviewReceiptError, match="unresolved concerns"):
        receipt(subject=review_subject, concerns=[concern])


def test_malformed_policy_and_index_return_invalid_verification_results() -> None:
    review = receipt()
    bad_policy = verify_human_review_receipt(
        review,
        policy={"allow_local_attestation": True},  # type: ignore[arg-type]
        now="2026-07-21T00:00:00Z",
    )
    bad_index = verify_human_review_receipt(
        review,
        policy=policy(),
        now="2026-07-21T00:00:00Z",
        receipt_index={"revoked_receipt_ids": []},  # type: ignore[arg-type]
    )

    assert not bad_policy.valid
    assert "verification policy" in bad_policy.reason
    assert not bad_index.valid
    assert "receipt_index" in bad_index.reason
