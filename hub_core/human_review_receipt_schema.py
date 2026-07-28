"""Closed schema construction and canonicalization for human review receipts."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence

from .human_review_receipt_json import (
    canonical_json_bytes,
    closed_mapping,
    enum_value,
    fail,
    parse_json_bytes,
    parse_timestamp,
    receipt_id,
    sha256,
    timestamp,
)
from .human_review_receipt_parts import (
    SUBJECT_FIELDS,
    calculate_subject_digest,
    validate_concern_waiver_links,
    validate_concerns,
    validate_reviewer,
    validate_subject,
    validate_waivers,
)
from .human_review_receipt_types import DECISION_SCOPES, DECISIONS, SCHEMA_VERSION

TOP_LEVEL_FIELDS = {
    "schema_version",
    "receipt_id",
    "decision",
    "decision_scope",
    "subject",
    "reviewer",
    "reviewed_at",
    "expires_at",
    "concerns",
    "waivers",
    "supersedes",
    "integrity",
}
PAYLOAD_FIELDS = TOP_LEVEL_FIELDS - {"receipt_id", "integrity"}


def validated_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = closed_mapping(value, PAYLOAD_FIELDS, "payload")
    if payload["schema_version"] != SCHEMA_VERSION:
        fail(f"schema_version must be {SCHEMA_VERSION!r}")
    decision = enum_value(payload["decision"], "decision", DECISIONS)
    decision_scope = enum_value(payload["decision_scope"], "decision_scope", DECISION_SCOPES)
    subject = validate_subject(payload["subject"], decision_scope)
    reviewer = validate_reviewer(payload["reviewer"])
    reviewed_at = timestamp(payload["reviewed_at"], "reviewed_at")
    expires_at = timestamp(payload["expires_at"], "expires_at")
    if parse_timestamp(expires_at) <= parse_timestamp(reviewed_at):
        fail("expires_at must be later than reviewed_at")
    concerns = validate_concerns(payload["concerns"], subject["subject_digest"])
    waivers = validate_waivers(payload["waivers"], subject["subject_digest"], reviewed_at)
    validate_concern_waiver_links(decision, concerns, waivers)
    supersedes = payload["supersedes"]
    if supersedes is not None:
        supersedes = receipt_id(supersedes, "supersedes")
    return {
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "decision_scope": decision_scope,
        "subject": subject,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "expires_at": expires_at,
        "concerns": [dict(item) for item in concerns],
        "waivers": [dict(item) for item in waivers],
        "supersedes": supersedes,
    }


def canonical_review_payload_bytes(receipt_or_payload: Mapping[str, Any]) -> bytes:
    if not isinstance(receipt_or_payload, Mapping):
        fail("must be a mapping")
    payload = {key: receipt_or_payload[key] for key in receipt_or_payload if key not in {"receipt_id", "integrity"}}
    return canonical_json_bytes(validated_payload(payload))


def human_review_receipt_digest(receipt_or_payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_review_payload_bytes(receipt_or_payload)).hexdigest()


def validate_human_review_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    receipt = closed_mapping(value, TOP_LEVEL_FIELDS, "receipt")
    payload = validated_payload({key: receipt[key] for key in PAYLOAD_FIELDS})
    payload_digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    full_receipt_id = receipt_id(receipt["receipt_id"], "receipt_id")
    integrity = closed_mapping(receipt["integrity"], {"canonical_sha256"}, "integrity")
    canonical_sha256 = sha256(integrity["canonical_sha256"], "integrity.canonical_sha256")
    if full_receipt_id != f"review:sha256:{payload_digest}":
        fail("receipt_id does not match canonical payload digest")
    if canonical_sha256 != payload_digest:
        fail("integrity.canonical_sha256 does not match canonical payload digest")
    return {**payload, "receipt_id": full_receipt_id, "integrity": {"canonical_sha256": canonical_sha256}}


def build_human_review_receipt(
    *,
    decision: str,
    decision_scope: str,
    subject: Mapping[str, Any],
    reviewer: Mapping[str, Any],
    reviewed_at: str,
    expires_at: str,
    concerns: Sequence[Mapping[str, Any]] = (),
    waivers: Sequence[Mapping[str, Any]] = (),
    supersedes: str | None = None,
) -> dict[str, Any]:
    payload = validated_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "decision": decision,
            "decision_scope": decision_scope,
            "subject": subject,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "expires_at": expires_at,
            "concerns": concerns,
            "waivers": waivers,
            "supersedes": supersedes,
        }
    )
    payload_digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return {
        **payload,
        "receipt_id": f"review:sha256:{payload_digest}",
        "integrity": {"canonical_sha256": payload_digest},
    }


def canonical_human_review_receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    return canonical_json_bytes(validate_human_review_receipt(receipt))


def parse_human_review_receipt_bytes(data: bytes | bytearray | memoryview) -> dict[str, Any]:
    return validate_human_review_receipt(parse_json_bytes(data))


def normalize_expected_subject(expected_subject: Mapping[str, Any], decision_scope: str) -> dict[str, str]:
    if not isinstance(expected_subject, Mapping):
        fail("expected_subject must be a mapping")
    if set(expected_subject) == SUBJECT_FIELDS - {"subject_digest"}:
        subject = dict(expected_subject)
        subject["subject_digest"] = calculate_subject_digest(subject, decision_scope)
        return validate_subject(subject, decision_scope)
    return validate_subject(expected_subject, decision_scope)
