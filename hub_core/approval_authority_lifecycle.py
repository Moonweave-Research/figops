"""Issuance, lifecycle, and verification for process-local approvals.

The codec module owns canonical data and validation primitives.  This module
owns the mutable in-process index and the exact-root checks that make an
approval authoritative.  Records retain the root object itself as an
identity-bearing capability; serialising or copying a record never grants
authority to a different root.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

from .approval_authority_codec import (
    _RECEIPT_ID_RE,
    ApprovalAuthorityError,
    ApprovalBinding,
    _checked_plan_digest,
    _field_digest,
    _freeze_json,
    _identity,
    _parse_timestamp,
    _text,
    _timestamp,
    _valid_digest,
    approval_binding_digest,
    canonical_plan_digest,
)


@dataclass(frozen=True, slots=True, init=False)
class ApprovalRecord:
    """Immutable approval record minted by an authority root."""

    receipt_id: str
    binding: ApprovalBinding
    _authority_owner: object

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - public construction is forbidden
        raise TypeError("ApprovalRecord instances must be issued by ApprovalAuthorityRoot")

    @classmethod
    def _mint(cls, owner: object, receipt_id: str, binding: ApprovalBinding) -> "ApprovalRecord":
        record = object.__new__(cls)
        object.__setattr__(record, "receipt_id", receipt_id)
        object.__setattr__(record, "binding", binding)
        object.__setattr__(record, "_authority_owner", owner)
        return record

    @property
    def plan_digest(self) -> str:
        return self.binding.plan_digest

    @property
    def current(self) -> bool:
        return self.binding.current

    @property
    def revoked(self) -> bool:
        return self.binding.revoked

    @property
    def superseded(self) -> bool:
        return self.binding.superseded

    @property
    def canonical_digest(self) -> str:
        return approval_binding_digest(self.binding)


@dataclass(frozen=True, slots=True)
class ApprovalVerificationResult:
    """Fail-closed result returned by :func:`verify_approval_authority`."""

    valid: bool
    reason: str
    receipt_id: str | None = None
    record: ApprovalRecord | None = None

    def __bool__(self) -> bool:
        return self.valid


class _AuthorityState:
    """Mutable lifecycle index entry; never exposed as an authority value."""

    __slots__ = ("record", "current", "revoked", "superseded_by")

    def __init__(self, record: ApprovalRecord) -> None:
        self.record = record
        self.current = True
        self.revoked = False
        self.superseded_by: str | None = None


class ApprovalAuthorityRoot:
    """Host-owned, process-local trust root and approval index."""

    __slots__ = ("_records",)

    def __init__(self) -> None:
        self._records: dict[str, _AuthorityState] = {}

    def __copy__(self) -> "ApprovalAuthorityRoot":  # pragma: no cover - defensive boundary
        raise TypeError("ApprovalAuthorityRoot cannot be copied")

    def __deepcopy__(self, memo: dict[int, Any]) -> "ApprovalAuthorityRoot":  # pragma: no cover
        raise TypeError("ApprovalAuthorityRoot cannot be copied")

    def issue_approval(
        self,
        plan: Mapping[str, Any],
        *,
        reviewer_identity: str,
        reviewer_role: str,
        issued_at: str | datetime,
        expires_at: str | datetime,
        supersedes: str | None = None,
    ) -> ApprovalRecord:
        plan_digest = _checked_plan_digest(plan)
        project_root_identity = _identity(plan, "project_root_identity")
        config_identity = _identity(plan, "config_identity", allow_none=True)
        config_sha256 = plan.get("config_sha256")
        if config_sha256 is not None:
            config_sha256 = _valid_digest(config_sha256, "plan config_sha256")
        reviewer_identity = _text(reviewer_identity, "reviewer_identity")
        reviewer_role = _text(reviewer_role, "reviewer_role", max_length=128)
        issued_at = _timestamp(issued_at, "issued_at")
        expires_at = _timestamp(expires_at, "expires_at")
        if _parse_timestamp(expires_at) <= _parse_timestamp(issued_at):
            raise ApprovalAuthorityError("approval authority expires_at must be later than issued_at")
        supersedes = None if supersedes is None else _text(supersedes, "supersedes", max_length=80)
        if supersedes is not None:
            if _RECEIPT_ID_RE.fullmatch(supersedes) is None:
                raise ApprovalAuthorityError("approval authority supersedes must be an approval receipt id")
            old = self._records.get(supersedes)
            if old is None:
                raise ApprovalAuthorityError("approval authority supersedes references an unknown receipt id")
            if old.revoked:
                raise ApprovalAuthorityError("approval authority a revoked approval cannot be superseded")
            if not old.current:
                raise ApprovalAuthorityError("approval authority only a current approval can be superseded")

        binding = ApprovalBinding(
            plan_digest=plan_digest,
            project_root_identity=project_root_identity,
            config_sha256=config_sha256,
            config_identity=config_identity,
            reviewed_entries_digest=_field_digest(plan, "reviewed_entries", "entries"),
            approved_mappings_digest=_field_digest(plan, "approved_mappings"),
            config_diff_digest=_field_digest(plan, "config_diff"),
            hardcoded_unresolved_references_digest=_field_digest(plan, "hardcoded_unresolved_references"),
            unresolved_proposals_digest=_field_digest(plan, "unresolved_proposals"),
            reviewer_identity=reviewer_identity,
            reviewer_role=reviewer_role,
            issued_at=issued_at,
            expires_at=expires_at,
            supersedes=supersedes,
        )
        receipt_id = f"approval:sha256:{approval_binding_digest(binding)}"
        if receipt_id in self._records:
            raise ApprovalAuthorityError(
                "approval authority an approval with the same immutable binding already exists"
            )
        record = ApprovalRecord._mint(self, receipt_id, binding)
        self._records[receipt_id] = _AuthorityState(record)
        if supersedes is not None:
            old = self._records[supersedes]
            old.current = False
            old.superseded_by = receipt_id
        return record

    def issue(self, plan: Mapping[str, Any], **kwargs: Any) -> ApprovalRecord:
        """Short alias for :meth:`issue_approval`."""

        return self.issue_approval(plan, **kwargs)

    def revoke(self, receipt_id: str) -> None:
        state = self._state_for(receipt_id)
        if state.revoked:
            return
        state.revoked = True
        state.current = False

    def revoke_approval(self, receipt_id: str) -> None:
        self.revoke(receipt_id)

    def supersede(self, receipt_id: str, plan: Mapping[str, Any], **kwargs: Any) -> ApprovalRecord:
        kwargs["supersedes"] = receipt_id
        return self.issue_approval(plan, **kwargs)

    def supersede_approval(self, receipt_id: str, plan: Mapping[str, Any], **kwargs: Any) -> ApprovalRecord:
        return self.supersede(receipt_id, plan, **kwargs)

    def get(self, receipt_id: str) -> ApprovalRecord | None:
        state = self._records.get(receipt_id)
        return None if state is None else state.record

    def lookup(self, receipt_id: str) -> ApprovalRecord | None:
        """Return an immutable record snapshot without exposing the index."""

        return self.get(receipt_id)

    def records(self) -> tuple[ApprovalRecord, ...]:
        return tuple(state.record for state in self._records.values())

    def _state_for(self, receipt_id: str) -> _AuthorityState:
        if not isinstance(receipt_id, str) or _RECEIPT_ID_RE.fullmatch(receipt_id) is None:
            raise ApprovalAuthorityError(
                "approval authority receipt_id must be an approval:sha256:<lowercase-sha256> identifier"
            )
        state = self._records.get(receipt_id)
        if state is None:
            raise ApprovalAuthorityError("approval authority unknown receipt_id")
        return state

    def _lookup(self, receipt_id: str) -> _AuthorityState | None:
        if not isinstance(receipt_id, str):
            return None
        return self._records.get(receipt_id)


def _result(
    valid: bool,
    reason: str,
    receipt_id: str | None,
    record: ApprovalRecord | None = None,
) -> ApprovalVerificationResult:
    return ApprovalVerificationResult(valid, reason, receipt_id, record)


def verify_approval_authority(
    plan: Mapping[str, Any],
    receipt_id: str,
    trusted_root: ApprovalAuthorityRoot | None = None,
    now: str | datetime | None = None,
) -> ApprovalVerificationResult:
    """Verify an approval against an exact host-owned root and current plan."""

    if type(trusted_root) is not ApprovalAuthorityRoot:
        return _result(False, "missing_or_untrusted_root", receipt_id if isinstance(receipt_id, str) else None)
    if not isinstance(receipt_id, str) or _RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        return _result(False, "missing_or_invalid_receipt_id", receipt_id if isinstance(receipt_id, str) else None)
    state = trusted_root._lookup(receipt_id)
    if state is None:
        return _result(False, "unknown_receipt_id", receipt_id)
    record = state.record
    if record._authority_owner is not trusted_root:
        return _result(False, "untrusted_record", receipt_id, record)
    if not isinstance(plan, Mapping):
        return _result(False, "invalid_plan", receipt_id, record)
    try:
        plan_digest = canonical_plan_digest(plan)
        if any(field in plan and plan[field] != plan_digest for field in ("digest", "plan_digest")):
            return _result(False, "plan_digest_mismatch", receipt_id, record)
        if plan_digest != record.binding.plan_digest:
            return _result(False, "plan_digest_mismatch", receipt_id, record)
        if _freeze_json(plan.get("project_root_identity")) != record.binding.project_root_identity:
            return _result(False, "project_root_identity_mismatch", receipt_id, record)
        config_sha256 = plan.get("config_sha256")
        if config_sha256 is not None:
            config_sha256 = _valid_digest(config_sha256, "plan config_sha256")
        if config_sha256 != record.binding.config_sha256:
            return _result(False, "config_sha256_mismatch", receipt_id, record)
        if _freeze_json(plan.get("config_identity")) != record.binding.config_identity:
            return _result(False, "config_identity_mismatch", receipt_id, record)
        checks = (
            ("reviewed_entries_digest", _field_digest(plan, "reviewed_entries", "entries")),
            ("approved_mappings_digest", _field_digest(plan, "approved_mappings")),
            ("config_diff_digest", _field_digest(plan, "config_diff")),
            ("hardcoded_unresolved_references_digest", _field_digest(plan, "hardcoded_unresolved_references")),
            ("unresolved_proposals_digest", _field_digest(plan, "unresolved_proposals")),
        )
        for field, actual in checks:
            if actual != getattr(record.binding, field):
                return _result(False, f"{field}_mismatch", receipt_id, record)
        check_time = (
            _parse_timestamp(_timestamp(now, "now"))
            if now is not None
            else datetime.now(UTC).replace(microsecond=0)
        )
        if check_time < _parse_timestamp(record.binding.issued_at):
            return _result(False, "issued_in_future", receipt_id, record)
        if check_time >= _parse_timestamp(record.binding.expires_at):
            return _result(False, "expired", receipt_id, record)
    except (ApprovalAuthorityError, TypeError, ValueError):
        return _result(False, "invalid_plan", receipt_id, record)
    if state.revoked or record.binding.revoked:
        return _result(False, "revoked", receipt_id, record)
    if state.superseded_by is not None or record.binding.superseded:
        return _result(False, "superseded", receipt_id, record)
    if not state.current or not record.binding.current:
        return _result(False, "not_current", receipt_id, record)
    return _result(True, "valid", receipt_id, record)


verify_approval = verify_approval_authority
ApprovalAuthority = ApprovalAuthorityRoot


__all__ = [
    "ApprovalAuthority",
    "ApprovalAuthorityRoot",
    "ApprovalRecord",
    "ApprovalVerificationResult",
    "verify_approval",
    "verify_approval_authority",
]
