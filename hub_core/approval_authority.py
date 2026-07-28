"""Public compatibility facade for process-local approval authority.

The implementation is split between two focused modules:

* :mod:`approval_authority_codec` contains canonical JSON, digest, timestamp,
  and immutable binding validation.
* :mod:`approval_authority_lifecycle` contains the host-owned trust root,
  issuance/revocation/supersession, and fail-closed verification.

This facade intentionally re-exports the established public API.  Consumers
can continue importing from ``hub_core.approval_authority`` without changing
the class identities used by the trust boundary.
"""

from .approval_authority_codec import (
    ApprovalAuthorityError,
    ApprovalBinding,
    approval_binding_digest,
    canonical_approval_binding_bytes,
    canonical_json_bytes,
    canonical_plan_digest,
)
from .approval_authority_lifecycle import (
    ApprovalAuthority,
    ApprovalAuthorityRoot,
    ApprovalRecord,
    ApprovalVerificationResult,
    verify_approval,
    verify_approval_authority,
)

__all__ = [
    "ApprovalAuthority",
    "ApprovalAuthorityError",
    "ApprovalAuthorityRoot",
    "ApprovalBinding",
    "ApprovalRecord",
    "ApprovalVerificationResult",
    "approval_binding_digest",
    "canonical_approval_binding_bytes",
    "canonical_json_bytes",
    "canonical_plan_digest",
    "verify_approval",
    "verify_approval_authority",
]
