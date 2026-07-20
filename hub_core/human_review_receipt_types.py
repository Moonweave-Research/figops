"""Shared types for the closed human review receipt domain."""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = "figops-human-review/1"

DECISIONS = frozenset({"approve_for_promotion", "request_revision", "decline"})
DECISION_SCOPES = frozenset(
    {
        "figure_scientific_and_communication",
        "figure_visual_communication",
        "scientific_claim_support",
    }
)
REVIEWER_ROLES = frozenset({"scientific_reviewer", "principal_investigator", "corresponding_author"})
CONCERN_CATEGORIES = frozenset({"scientific", "communication", "accessibility", "policy", "provenance"})
CONCERN_SEVERITIES = frozenset({"required", "advisory"})
CONCERN_STATUSES = frozenset({"resolved", "waived", "unresolved"})
IDENTITY_KINDS = frozenset({"local_attestation"})


class HumanReviewReceiptError(ValueError):
    """Raised when a human review receipt fails the closed contract."""


@dataclass(frozen=True, slots=True)
class HumanReviewAuthorityBinding:
    """Exact policy binding that authorizes a reviewer for one decision scope."""

    decision_scope: str
    reviewer_role: str
    authority_assertion: str


@dataclass(frozen=True, slots=True)
class HumanReviewWaiverBinding:
    """Exact policy binding that authorizes one class of concern waiver."""

    policy_rule: str
    authorized_role: str
    concern_category: str
    concern_severity: str


@dataclass(frozen=True, slots=True)
class HumanReviewVerificationPolicy:
    """Narrow verification policy for identity, reviewer authority, and waivers."""

    allow_local_attestation: bool
    reviewer_bindings: frozenset[HumanReviewAuthorityBinding] = frozenset()
    waiver_bindings: frozenset[HumanReviewWaiverBinding] = frozenset()


@dataclass(frozen=True, slots=True)
class HumanReviewReceiptIndex:
    """Storage-independent revocation/currentness facts supplied by a caller."""

    revoked_receipt_ids: frozenset[str] = frozenset()
    superseded_receipt_ids: frozenset[str] = frozenset()
    current_receipt_ids: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class HumanReviewVerificationResult:
    """Result of fail-closed human review receipt verification."""

    valid: bool
    reason: str
    receipt_id: str | None = None
    canonical_sha256: str | None = None
