"""Compatible facade for the closed human review receipt domain."""

from __future__ import annotations

from .human_review_receipt_json import (
    opaque_concern_id,
    opaque_figure_artifact_id,
    opaque_principal_id,
    opaque_project_id,
    opaque_waiver_id,
)
from .human_review_receipt_parts import build_review_subject, build_reviewer, calculate_subject_digest
from .human_review_receipt_schema import (
    build_human_review_receipt,
    canonical_human_review_receipt_bytes,
    canonical_review_payload_bytes,
    human_review_receipt_digest,
    parse_human_review_receipt_bytes,
    validate_human_review_receipt,
)
from .human_review_receipt_types import (
    CONCERN_CATEGORIES,
    CONCERN_SEVERITIES,
    CONCERN_STATUSES,
    DECISION_SCOPES,
    DECISIONS,
    REVIEWER_ROLES,
    SCHEMA_VERSION,
    HumanReviewAuthorityBinding,
    HumanReviewReceiptError,
    HumanReviewReceiptIndex,
    HumanReviewVerificationPolicy,
    HumanReviewVerificationResult,
    HumanReviewWaiverBinding,
)
from .human_review_receipt_verification import verify_human_review_receipt

__all__ = [
    "CONCERN_CATEGORIES",
    "CONCERN_SEVERITIES",
    "CONCERN_STATUSES",
    "DECISIONS",
    "DECISION_SCOPES",
    "HumanReviewAuthorityBinding",
    "HumanReviewReceiptError",
    "HumanReviewReceiptIndex",
    "HumanReviewVerificationPolicy",
    "HumanReviewVerificationResult",
    "HumanReviewWaiverBinding",
    "REVIEWER_ROLES",
    "SCHEMA_VERSION",
    "build_human_review_receipt",
    "build_review_subject",
    "build_reviewer",
    "calculate_subject_digest",
    "canonical_human_review_receipt_bytes",
    "canonical_review_payload_bytes",
    "human_review_receipt_digest",
    "opaque_concern_id",
    "opaque_figure_artifact_id",
    "opaque_principal_id",
    "opaque_project_id",
    "opaque_waiver_id",
    "parse_human_review_receipt_bytes",
    "validate_human_review_receipt",
    "verify_human_review_receipt",
]
