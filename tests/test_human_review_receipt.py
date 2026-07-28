from __future__ import annotations

import json
import unicodedata
from datetime import UTC, datetime

import pytest

from hub_core.human_review_receipt import (
    HumanReviewReceiptError,
    build_review_subject,
    build_reviewer,
    canonical_human_review_receipt_bytes,
    canonical_review_payload_bytes,
    human_review_receipt_digest,
    opaque_figure_artifact_id,
    opaque_principal_id,
    opaque_project_id,
    parse_human_review_receipt_bytes,
    validate_human_review_receipt,
    verify_human_review_receipt,
)
from tests.human_review_receipt_helpers import policy, receipt, reviewer, subject


def test_happy_path_constructs_canonical_bytes_digest_and_verifies() -> None:
    review = receipt()

    payload_bytes = canonical_review_payload_bytes(review)
    full_bytes = canonical_human_review_receipt_bytes(review)
    digest = human_review_receipt_digest(review)
    verification = verify_human_review_receipt(
        full_bytes,
        policy=policy(),
        now="2026-07-21T00:00:00Z",
        expected_subject=review["subject"],
        expected_subject_digest=review["subject"]["subject_digest"],
    )

    assert b"receipt_id" not in payload_bytes
    assert b"integrity" not in payload_bytes
    assert json.loads(full_bytes)["integrity"] == {"canonical_sha256": digest}
    assert review["receipt_id"] == f"review:sha256:{digest}"
    assert verification.valid


def test_parser_rejects_duplicate_json_keys() -> None:
    review = receipt()
    duplicate = (
        b'{"schema_version":"figops-human-review/1","schema_version":"figops-human-review/1",'
        + canonical_human_review_receipt_bytes(review).lstrip(b"{")
    )

    with pytest.raises(HumanReviewReceiptError, match="duplicate JSON key"):
        parse_human_review_receipt_bytes(duplicate)


def test_parser_rejects_bom_non_finite_json_and_non_bytes() -> None:
    with pytest.raises(HumanReviewReceiptError, match="without a BOM"):
        parse_human_review_receipt_bytes(b"\xef\xbb\xbf{}")
    with pytest.raises(HumanReviewReceiptError, match="non-finite"):
        parse_human_review_receipt_bytes(b'{"schema_version":NaN}')
    with pytest.raises(HumanReviewReceiptError, match="input must be bytes"):
        parse_human_review_receipt_bytes(None)  # type: ignore[arg-type]


def test_unknown_top_level_and_nested_fields_fail_closed() -> None:
    review = receipt()
    review["unexpected"] = "value"
    with pytest.raises(HumanReviewReceiptError, match="unsupported unexpected"):
        validate_human_review_receipt(review)

    review = receipt()
    review["reviewer"] = {**review["reviewer"], "display_name": "Dr. Reviewer"}
    with pytest.raises(HumanReviewReceiptError, match="reviewer contains unsupported display_name"):
        validate_human_review_receipt(review)


def test_tampering_with_payload_or_integrity_breaks_verification() -> None:
    review = receipt()
    review["decision"] = "decline"
    result = verify_human_review_receipt(review, policy=policy(), now="2026-07-21T00:00:00Z")
    assert not result.valid
    assert "receipt_id does not match" in result.reason

    review = receipt()
    review["integrity"] = {"canonical_sha256": "0" * 64}
    with pytest.raises(HumanReviewReceiptError, match="integrity.canonical_sha256 does not match"):
        validate_human_review_receipt(review)


def test_subject_mismatch_and_replay_are_rejected() -> None:
    review = receipt()
    replay_subject = build_review_subject(
        project_id=opaque_project_id("different-project"),
        artifact_id=review["subject"]["artifact_id"],
        artifact_sha256=review["subject"]["artifact_sha256"],
        lineage_receipt_sha256=review["subject"]["lineage_receipt_sha256"],
        evidence_digest=review["subject"]["evidence_digest"],
        resolved_policy_digest=review["subject"]["resolved_policy_digest"],
        decision_scope=review["decision_scope"],
    )

    result = verify_human_review_receipt(
        review,
        policy=policy(),
        now="2026-07-21T00:00:00Z",
        expected_subject=replay_subject,
    )

    assert not result.valid
    assert result.reason == "subject_mismatch"


def test_subject_digest_binds_decision_scope() -> None:
    review_subject = subject("figure_visual_communication")
    with pytest.raises(HumanReviewReceiptError, match="subject.subject_digest does not match"):
        receipt(decision_scope="figure_scientific_and_communication", subject=review_subject)


def test_malformed_ids_hashes_and_path_like_subject_values_are_rejected() -> None:
    with pytest.raises(HumanReviewReceiptError, match="subject.artifact_sha256"):
        build_review_subject(
            project_id=opaque_project_id("project-17"),
            artifact_id=opaque_figure_artifact_id("figure-1"),
            artifact_sha256="A" * 64,
            lineage_receipt_sha256="2" * 64,
            evidence_digest="3" * 64,
            resolved_policy_digest="4" * 64,
            decision_scope="figure_scientific_and_communication",
        )

    with pytest.raises(HumanReviewReceiptError, match="subject.project_id"):
        build_review_subject(
            project_id="C:/research/project",
            artifact_id=opaque_figure_artifact_id("figure-1"),
            artifact_sha256="1" * 64,
            lineage_receipt_sha256="2" * 64,
            evidence_digest="3" * 64,
            resolved_policy_digest="4" * 64,
            decision_scope="figure_scientific_and_communication",
        )


def test_timestamp_requires_utc_seconds_and_real_expiry_order() -> None:
    with pytest.raises(HumanReviewReceiptError, match="reviewed_at"):
        receipt(reviewed_at="2026-07-20T00:00:00+09:00")
    with pytest.raises(HumanReviewReceiptError, match="reviewed_at"):
        receipt(reviewed_at="2026-07-20T00:00:00.123Z")
    with pytest.raises(HumanReviewReceiptError, match="expires_at must be later"):
        receipt(expires_at="2026-07-20T00:00:00Z")


def test_nfc_string_normalization_is_used_for_canonical_payloads() -> None:
    decomposed = "reviewer-e\u0301@example.invalid"
    normalized_reviewer = reviewer(unicodedata.normalize("NFD", decomposed))
    review = receipt(reviewer=normalized_reviewer)
    parsed = parse_human_review_receipt_bytes(
        json.dumps(review, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )

    assert unicodedata.is_normalized("NFC", parsed["reviewer"]["principal_id"])
    assert parsed == review


def test_direct_malformed_mapping_inputs_raise_domain_errors_or_invalid_results() -> None:
    with pytest.raises(HumanReviewReceiptError, match="must be a mapping"):
        canonical_review_payload_bytes(None)  # type: ignore[arg-type]
    with pytest.raises(HumanReviewReceiptError, match="keys must be strings"):
        validate_human_review_receipt({1: "bad"})
    result = verify_human_review_receipt(None, policy=policy(), now="2026-07-21T00:00:00Z")  # type: ignore[arg-type]
    assert not result.valid
    assert "must be a mapping" in result.reason


def test_local_attestation_cannot_be_mislabeled_as_verified_identity() -> None:
    with pytest.raises(HumanReviewReceiptError, match="reviewer.identity_kind"):
        build_reviewer(
            principal_id=opaque_principal_id("reviewer@example.invalid"),
            role="scientific_reviewer",
            authority_assertion="lab-policy/1",
            identity_kind="federated_verified",
        )


def test_authority_assertion_requires_explicit_positive_numeric_version() -> None:
    with pytest.raises(HumanReviewReceiptError, match="versioned policy binding token"):
        build_reviewer(
            principal_id=opaque_principal_id("reviewer@example.invalid"),
            role="scientific_reviewer",
            authority_assertion="lab-policy",
        )

    with pytest.raises(HumanReviewReceiptError, match="versioned policy binding token"):
        build_reviewer(
            principal_id=opaque_principal_id("reviewer@example.invalid"),
            role="scientific_reviewer",
            authority_assertion="lab-policy/0",
        )


def test_timezone_aware_datetime_now_is_supported() -> None:
    result = verify_human_review_receipt(receipt(), policy=policy(), now=datetime(2026, 7, 21, tzinfo=UTC))
    assert result.valid
