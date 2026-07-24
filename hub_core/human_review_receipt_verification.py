"""Fail-closed verification for closed human review receipts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from .human_review_receipt_json import authority_assertion, fail, parse_timestamp, receipt_id, sha256, timestamp
from .human_review_receipt_schema import (
    normalize_expected_subject,
    parse_human_review_receipt_bytes,
    validate_human_review_receipt,
)
from .human_review_receipt_types import (
    CONCERN_CATEGORIES,
    CONCERN_SEVERITIES,
    REVIEWER_ROLES,
    HumanReviewAuthorityBinding,
    HumanReviewReceiptError,
    HumanReviewReceiptIndex,
    HumanReviewVerificationPolicy,
    HumanReviewVerificationResult,
    HumanReviewWaiverBinding,
)


def verify_human_review_receipt(
    receipt_or_bytes: Mapping[str, Any] | bytes | bytearray | memoryview,
    *,
    policy: HumanReviewVerificationPolicy,
    now: datetime | str | None = None,
    expected_subject: Mapping[str, Any] | None = None,
    expected_subject_digest: str | None = None,
    receipt_index: HumanReviewReceiptIndex | None = None,
    require_approval: bool = True,
) -> HumanReviewVerificationResult:
    try:
        receipt = _load_receipt(receipt_or_bytes)
        digest = receipt["integrity"]["canonical_sha256"]
        full_receipt_id = receipt["receipt_id"]
        _validate_policy(policy)
        if require_approval and receipt["decision"] != "approve_for_promotion":
            return HumanReviewVerificationResult(False, "decision_not_approval", full_receipt_id, digest)
        if not _reviewer_authorized(receipt, policy):
            return HumanReviewVerificationResult(False, "reviewer_not_authorized", full_receipt_id, digest)
        if receipt["reviewer"]["identity_kind"] == "local_attestation" and not policy.allow_local_attestation:
            return HumanReviewVerificationResult(False, "local_attestation_not_allowed", full_receipt_id, digest)
        time_result = _verify_times(receipt, _coerce_now(now), full_receipt_id, digest)
        if time_result is not None:
            return time_result
        if not _waivers_authorized(receipt, policy):
            return HumanReviewVerificationResult(False, "waiver_not_authorized", full_receipt_id, digest)
        subject_result = _verify_subjects(receipt, expected_subject, expected_subject_digest, full_receipt_id, digest)
        if subject_result is not None:
            return subject_result
        index_result = _verify_index(receipt_index, full_receipt_id, digest)
        return index_result or HumanReviewVerificationResult(True, "valid", full_receipt_id, digest)
    except (HumanReviewReceiptError, TypeError, ValueError, AttributeError) as exc:
        return HumanReviewVerificationResult(False, str(exc))


def _load_receipt(receipt_or_bytes: Mapping[str, Any] | bytes | bytearray | memoryview) -> dict[str, Any]:
    if isinstance(receipt_or_bytes, (bytes, bytearray, memoryview)):
        return parse_human_review_receipt_bytes(receipt_or_bytes)
    return validate_human_review_receipt(receipt_or_bytes)


def _validate_policy(policy: HumanReviewVerificationPolicy) -> None:
    if not isinstance(policy, HumanReviewVerificationPolicy):
        fail("verification policy must be a HumanReviewVerificationPolicy")
    if not isinstance(policy.allow_local_attestation, bool):
        fail("verification policy allow_local_attestation must be boolean")
    for binding in policy.reviewer_bindings:
        if not isinstance(binding, HumanReviewAuthorityBinding):
            fail("verification policy reviewer_bindings must contain HumanReviewAuthorityBinding entries")
        authority_assertion(binding.authority_assertion, "verification policy reviewer authority_assertion")
    for binding in policy.waiver_bindings:
        if not isinstance(binding, HumanReviewWaiverBinding):
            fail("verification policy waiver_bindings must contain HumanReviewWaiverBinding entries")
        authority_assertion(binding.policy_rule, "verification policy waiver policy_rule")
        if binding.authorized_role not in REVIEWER_ROLES:
            fail("verification policy waiver authorized_role is unsupported")
        if binding.concern_category not in CONCERN_CATEGORIES or binding.concern_severity not in CONCERN_SEVERITIES:
            fail("verification policy waiver concern binding is unsupported")


def _reviewer_authorized(receipt: Mapping[str, Any], policy: HumanReviewVerificationPolicy) -> bool:
    reviewer = receipt["reviewer"]
    actual = HumanReviewAuthorityBinding(
        decision_scope=receipt["decision_scope"],
        reviewer_role=reviewer["role"],
        authority_assertion=reviewer["authority_assertion"],
    )
    return actual in policy.reviewer_bindings


def _waivers_authorized(receipt: Mapping[str, Any], policy: HumanReviewVerificationPolicy) -> bool:
    concerns = {concern["concern_id"]: concern for concern in receipt["concerns"]}
    for waiver in receipt["waivers"]:
        concern = concerns[waiver["concern_id"]]
        actual = HumanReviewWaiverBinding(
            policy_rule=waiver["policy_rule"],
            authorized_role=waiver["authorized_role"],
            concern_category=concern["category"],
            concern_severity=concern["severity"],
        )
        if actual not in policy.waiver_bindings:
            return False
    return True


def _verify_times(
    receipt: Mapping[str, Any],
    check_time: datetime,
    full_receipt_id: str,
    digest: str,
) -> HumanReviewVerificationResult | None:
    if check_time < parse_timestamp(receipt["reviewed_at"]):
        return HumanReviewVerificationResult(False, "reviewed_at_in_future", full_receipt_id, digest)
    if check_time >= parse_timestamp(receipt["expires_at"]):
        return HumanReviewVerificationResult(False, "expired", full_receipt_id, digest)
    for waiver in receipt["waivers"]:
        if check_time >= parse_timestamp(waiver["expires_at"]):
            return HumanReviewVerificationResult(False, "waiver_expired", full_receipt_id, digest)
    return None


def _verify_subjects(
    receipt: Mapping[str, Any],
    expected_subject: Mapping[str, Any] | None,
    expected_subject_digest: str | None,
    full_receipt_id: str,
    digest: str,
) -> HumanReviewVerificationResult | None:
    if expected_subject is not None:
        expected = normalize_expected_subject(expected_subject, receipt["decision_scope"])
        if receipt["subject"] != expected:
            return HumanReviewVerificationResult(False, "subject_mismatch", full_receipt_id, digest)
    if expected_subject_digest is not None:
        expected_digest = sha256(expected_subject_digest, "expected_subject_digest")
        if receipt["subject"]["subject_digest"] != expected_digest:
            return HumanReviewVerificationResult(False, "subject_digest_mismatch", full_receipt_id, digest)
    return None


def _verify_index(
    index: HumanReviewReceiptIndex | None,
    full_receipt_id: str,
    digest: str,
) -> HumanReviewVerificationResult | None:
    if index is None:
        return None
    _validate_index(index)
    if full_receipt_id in index.revoked_receipt_ids:
        return HumanReviewVerificationResult(False, "revoked", full_receipt_id, digest)
    if full_receipt_id in index.superseded_receipt_ids:
        return HumanReviewVerificationResult(False, "superseded", full_receipt_id, digest)
    if index.current_receipt_ids is not None and full_receipt_id not in index.current_receipt_ids:
        return HumanReviewVerificationResult(False, "not_current", full_receipt_id, digest)
    return None


def _coerce_now(now: datetime | str | None) -> datetime:
    if now is None:
        return datetime.now(UTC).replace(microsecond=0)
    if isinstance(now, str):
        return parse_timestamp(timestamp(now, "now"))
    if now.tzinfo is None or now.utcoffset() is None:
        fail("now must be timezone-aware")
    return now.astimezone(UTC).replace(microsecond=0)


def _validate_index(index: HumanReviewReceiptIndex) -> None:
    if not isinstance(index, HumanReviewReceiptIndex):
        fail("receipt_index must be a HumanReviewReceiptIndex")
    for collection_name in ("revoked_receipt_ids", "superseded_receipt_ids"):
        for item in getattr(index, collection_name):
            receipt_id(item, f"receipt_index.{collection_name}[]")
    if index.current_receipt_ids is not None:
        for item in index.current_receipt_ids:
            receipt_id(item, "receipt_index.current_receipt_ids[]")
