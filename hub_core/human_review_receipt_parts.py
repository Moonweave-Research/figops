"""Subject, reviewer, concern, and waiver validation for review receipts."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .human_review_receipt_json import (
    authority_assertion,
    canonical_json_bytes,
    closed_mapping,
    digest,
    enum_value,
    fail,
    opaque_id,
    parse_timestamp,
    reject_path_like_subject,
    sha256,
    timestamp,
)
from .human_review_receipt_types import (
    CONCERN_CATEGORIES,
    CONCERN_SEVERITIES,
    CONCERN_STATUSES,
    DECISION_SCOPES,
    IDENTITY_KINDS,
    REVIEWER_ROLES,
)

SUBJECT_FIELDS = {
    "project_id",
    "artifact_id",
    "artifact_sha256",
    "lineage_receipt_sha256",
    "evidence_digest",
    "resolved_policy_digest",
    "subject_digest",
}
REVIEWER_FIELDS = {"principal_id", "role", "authority_assertion", "identity_kind"}
CONCERN_FIELDS = {"concern_id", "category", "severity", "status", "subject_digest", "finding_digest"}
WAIVER_FIELDS = {
    "waiver_id",
    "concern_id",
    "policy_rule",
    "rationale_digest",
    "authorized_principal_id",
    "authorized_role",
    "subject_digest",
    "expires_at",
}


def calculate_subject_digest(subject: Mapping[str, Any], decision_scope: str) -> str:
    scope = enum_value(decision_scope, "decision_scope", DECISION_SCOPES)
    partial = closed_mapping(subject, SUBJECT_FIELDS - {"subject_digest"}, "subject")
    normalized = {
        "project_id": opaque_id(partial["project_id"], "subject.project_id", "project"),
        "artifact_id": opaque_id(partial["artifact_id"], "subject.artifact_id", "result.figure"),
        "artifact_sha256": sha256(partial["artifact_sha256"], "subject.artifact_sha256"),
        "lineage_receipt_sha256": sha256(partial["lineage_receipt_sha256"], "subject.lineage_receipt_sha256"),
        "evidence_digest": sha256(partial["evidence_digest"], "subject.evidence_digest"),
        "resolved_policy_digest": sha256(partial["resolved_policy_digest"], "subject.resolved_policy_digest"),
    }
    for field, value in normalized.items():
        reject_path_like_subject(value, f"subject.{field}")
    return digest("subject", canonical_json_bytes({"decision_scope": scope, "subject": normalized}))


def build_review_subject(
    *,
    project_id: str,
    artifact_id: str,
    artifact_sha256: str,
    lineage_receipt_sha256: str,
    evidence_digest: str,
    resolved_policy_digest: str,
    decision_scope: str,
) -> dict[str, str]:
    subject = {
        "project_id": project_id,
        "artifact_id": artifact_id,
        "artifact_sha256": artifact_sha256,
        "lineage_receipt_sha256": lineage_receipt_sha256,
        "evidence_digest": evidence_digest,
        "resolved_policy_digest": resolved_policy_digest,
    }
    return {**subject, "subject_digest": calculate_subject_digest(subject, decision_scope)}


def build_reviewer(
    *,
    principal_id: str,
    role: str,
    authority_assertion: str,
    identity_kind: str = "local_attestation",
) -> dict[str, str]:
    return validate_reviewer(
        {
            "principal_id": principal_id,
            "role": role,
            "authority_assertion": authority_assertion,
            "identity_kind": identity_kind,
        }
    )


def validate_subject(value: Any, decision_scope: str) -> dict[str, str]:
    subject = closed_mapping(value, SUBJECT_FIELDS, "subject")
    normalized = {
        "project_id": opaque_id(subject["project_id"], "subject.project_id", "project"),
        "artifact_id": opaque_id(subject["artifact_id"], "subject.artifact_id", "result.figure"),
        "artifact_sha256": sha256(subject["artifact_sha256"], "subject.artifact_sha256"),
        "lineage_receipt_sha256": sha256(subject["lineage_receipt_sha256"], "subject.lineage_receipt_sha256"),
        "evidence_digest": sha256(subject["evidence_digest"], "subject.evidence_digest"),
        "resolved_policy_digest": sha256(subject["resolved_policy_digest"], "subject.resolved_policy_digest"),
        "subject_digest": sha256(subject["subject_digest"], "subject.subject_digest"),
    }
    for field, value in normalized.items():
        reject_path_like_subject(value, f"subject.{field}")
    partial = {key: normalized[key] for key in SUBJECT_FIELDS - {"subject_digest"}}
    if normalized["subject_digest"] != calculate_subject_digest(partial, decision_scope):
        fail("subject.subject_digest does not match the normalized subject and decision scope")
    return normalized


def validate_reviewer(value: Any) -> dict[str, str]:
    reviewer = closed_mapping(value, REVIEWER_FIELDS, "reviewer")
    return {
        "principal_id": opaque_id(reviewer["principal_id"], "reviewer.principal_id", "principal"),
        "role": enum_value(reviewer["role"], "reviewer.role", REVIEWER_ROLES),
        "authority_assertion": authority_assertion(reviewer["authority_assertion"]),
        "identity_kind": enum_value(reviewer["identity_kind"], "reviewer.identity_kind", IDENTITY_KINDS),
    }


def validate_concerns(value: Any, subject_digest: str) -> tuple[dict[str, str], ...]:
    if not isinstance(value, (list, tuple)):
        fail("concerns must be an array")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        field = f"concerns[{index}]"
        concern = closed_mapping(raw, CONCERN_FIELDS, field)
        item = {
            "concern_id": opaque_id(concern["concern_id"], f"{field}.concern_id", "concern"),
            "category": enum_value(concern["category"], f"{field}.category", CONCERN_CATEGORIES),
            "severity": enum_value(concern["severity"], f"{field}.severity", CONCERN_SEVERITIES),
            "status": enum_value(concern["status"], f"{field}.status", CONCERN_STATUSES),
            "subject_digest": sha256(concern["subject_digest"], f"{field}.subject_digest"),
            "finding_digest": sha256(concern["finding_digest"], f"{field}.finding_digest"),
        }
        if item["subject_digest"] != subject_digest:
            fail(f"{field}.subject_digest must match subject.subject_digest")
        if item["concern_id"] in seen:
            fail("concerns contains duplicate concern_id values")
        seen.add(item["concern_id"])
        normalized.append(item)
    return tuple(normalized)


def validate_waivers(value: Any, subject_digest: str, reviewed_at: str) -> tuple[dict[str, str], ...]:
    if not isinstance(value, (list, tuple)):
        fail("waivers must be an array")
    normalized: list[dict[str, str]] = []
    reviewed = parse_timestamp(reviewed_at)
    seen: set[str] = set()
    for index, raw in enumerate(value):
        field = f"waivers[{index}]"
        waiver = closed_mapping(raw, WAIVER_FIELDS, field)
        item = {
            "waiver_id": opaque_id(waiver["waiver_id"], f"{field}.waiver_id", "waiver"),
            "concern_id": opaque_id(waiver["concern_id"], f"{field}.concern_id", "concern"),
            "policy_rule": authority_assertion(waiver["policy_rule"], f"{field}.policy_rule"),
            "rationale_digest": sha256(waiver["rationale_digest"], f"{field}.rationale_digest"),
            "authorized_principal_id": opaque_id(
                waiver["authorized_principal_id"], f"{field}.authorized_principal_id", "principal"
            ),
            "authorized_role": enum_value(waiver["authorized_role"], f"{field}.authorized_role", REVIEWER_ROLES),
            "subject_digest": sha256(waiver["subject_digest"], f"{field}.subject_digest"),
            "expires_at": timestamp(waiver["expires_at"], f"{field}.expires_at"),
        }
        if item["subject_digest"] != subject_digest:
            fail(f"{field}.subject_digest must match subject.subject_digest")
        if parse_timestamp(item["expires_at"]) <= reviewed:
            fail(f"{field}.expires_at must be later than reviewed_at")
        if item["waiver_id"] in seen:
            fail("waivers contains duplicate waiver_id values")
        seen.add(item["waiver_id"])
        normalized.append(item)
    return tuple(normalized)


def validate_concern_waiver_links(
    decision: str,
    concerns: Sequence[Mapping[str, str]],
    waivers: Sequence[Mapping[str, str]],
) -> None:
    concern_by_id = {concern["concern_id"]: concern for concern in concerns}
    waiver_ids = [waiver["concern_id"] for waiver in waivers]
    if len(waiver_ids) != len(set(waiver_ids)):
        fail("waivers contains duplicate concern_id values")
    if set(waiver_ids) - set(concern_by_id):
        fail("waivers must reference existing concerns")
    for concern in concerns:
        has_waiver = concern["concern_id"] in waiver_ids
        if concern["status"] == "waived" and not has_waiver:
            fail("waived concerns require a matching waiver")
        if concern["status"] != "waived" and has_waiver:
            fail("waivers may only reference waived concerns")
        if concern["category"] == "scientific" and concern["severity"] == "required" and has_waiver:
            fail("required scientific concerns cannot be waived")
        if decision == "approve_for_promotion" and concern["status"] == "unresolved":
            fail("approve_for_promotion cannot record unresolved concerns")
