"""Process-local approval authority for reviewed structure plans.

This module deliberately keeps approval authority separate from runtime,
durable-result, and evidence receipts.  A record is only authoritative when it
was minted by the exact host-owned :class:`ApprovalAuthorityRoot` supplied to
the verifier.  Copying a record to a mapping (or serialising it to JSON) never
creates authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Mapping, NoReturn

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_ID_RE = re.compile(r"^approval:sha256:[0-9a-f]{64}$")
_UTC_TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


class ApprovalAuthorityError(ValueError):
    """Raised when an approval authority contract cannot be constructed."""


def _fail(message: str) -> NoReturn:
    raise ApprovalAuthorityError(f"approval authority {message}")


def _jsonable(value: Any) -> Any:
    """Convert immutable values back to plain deterministic JSON values."""

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                _fail("JSON object keys must be strings")
            result[key] = _jsonable(child)
        return result
    if isinstance(value, tuple):
        return [_jsonable(child) for child in value]
    if isinstance(value, list):
        return [_jsonable(child) for child in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("JSON values must be finite")
        return value
    _fail(f"JSON value has unsupported type {type(value).__name__}")


def _freeze_json(value: Any) -> Any:
    """Deep-freeze JSON data so records cannot be changed through aliases."""

    if isinstance(value, Mapping):
        result = {key: _freeze_json(child) for key, child in value.items()}
        if any(not isinstance(key, str) for key in result):
            _fail("JSON object keys must be strings")
        return MappingProxyType(result)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(child) for child in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("JSON values must be finite")
        return value
    _fail(f"JSON value has unsupported type {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for a JSON-compatible value."""

    try:
        return json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ApprovalAuthorityError(f"JSON canonicalization failed: {exc}") from exc


def _sha256_bytes(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _valid_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(f"{field} must be a lowercase SHA-256 digest")
    return value


def _text(value: Any, field: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > max_length:
        _fail(f"{field} must be a non-empty canonical string")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        _fail(f"{field} may not contain control characters")
    return value


def _timestamp(value: Any, field: str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            _fail(f"{field} must be timezone-aware")
        value = value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not isinstance(value, str) or _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        _fail(f"{field} must be an RFC 3339 UTC timestamp with seconds precision and Z suffix")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ApprovalAuthorityError(f"approval authority {field} must be a real timestamp") from exc
    return value


def _parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def canonical_plan_digest(plan: Mapping[str, Any]) -> str:
    """Hash a plan excluding its self-referential ``digest`` fields.

    Structure plans use ``digest``; callers using ``plan_digest`` receive the
    same treatment.  A declared digest, when present, must match this value.
    """

    if not isinstance(plan, Mapping):
        _fail("plan must be a mapping")
    payload = {key: value for key, value in plan.items() if key not in {"digest", "plan_digest"}}
    return _sha256_bytes(payload)


def _checked_plan_digest(plan: Mapping[str, Any]) -> str:
    digest = canonical_plan_digest(plan)
    for field in ("digest", "plan_digest"):
        if field in plan and plan[field] != digest:
            _fail(f"plan {field} is stale or invalid")
    return digest


def _field_digest(plan: Mapping[str, Any], *fields: str) -> str:
    for field in fields:
        if field in plan:
            return _sha256_bytes(plan[field])
    # Omission is distinct from an explicitly reviewed empty list.
    return _sha256_bytes({"__missing_field__": fields[0]})


def _identity(plan: Mapping[str, Any], field: str, *, allow_none: bool = False) -> Any:
    value = plan.get(field)
    if value is None and allow_none:
        return None
    if value is None:
        _fail(f"plan {field} is required")
    return _freeze_json(value)


@dataclass(frozen=True, slots=True)
class ApprovalBinding:
    """Immutable canonical binding for one host-issued approval."""

    plan_digest: str
    project_root_identity: Any
    config_sha256: str | None
    config_identity: Any
    reviewed_entries_digest: str
    approved_mappings_digest: str
    config_diff_digest: str
    hardcoded_unresolved_references_digest: str
    unresolved_proposals_digest: str
    reviewer_identity: str
    reviewer_role: str
    issued_at: str
    expires_at: str
    current: bool = True
    revoked: bool = False
    superseded: bool = False
    superseded_by: str | None = None
    supersedes: str | None = None

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "plan_digest": self.plan_digest,
            "project_root_identity": _jsonable(self.project_root_identity),
            "config_sha256": self.config_sha256,
            "config_identity": _jsonable(self.config_identity),
            "reviewed_entries_digest": self.reviewed_entries_digest,
            "approved_mappings_digest": self.approved_mappings_digest,
            "config_diff_digest": self.config_diff_digest,
            "hardcoded_unresolved_references_digest": self.hardcoded_unresolved_references_digest,
            "unresolved_proposals_digest": self.unresolved_proposals_digest,
            "reviewer_identity": self.reviewer_identity,
            "reviewer_role": self.reviewer_role,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "current": self.current,
            "revoked": self.revoked,
            "superseded": self.superseded,
            "superseded_by": self.superseded_by,
            "supersedes": self.supersedes,
        }


def canonical_approval_binding_bytes(binding: ApprovalBinding) -> bytes:
    if not isinstance(binding, ApprovalBinding):
        _fail("binding must be an ApprovalBinding")
    return canonical_json_bytes(binding.canonical_payload())


def approval_binding_digest(binding: ApprovalBinding) -> str:
    return hashlib.sha256(canonical_approval_binding_bytes(binding)).hexdigest()


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
            _fail("expires_at must be later than issued_at")
        supersedes = None if supersedes is None else _text(supersedes, "supersedes", max_length=80)
        if supersedes is not None:
            if _RECEIPT_ID_RE.fullmatch(supersedes) is None:
                _fail("supersedes must be an approval receipt id")
            old = self._records.get(supersedes)
            if old is None:
                _fail("supersedes references an unknown receipt id")
            if old.revoked:
                _fail("a revoked approval cannot be superseded")
            if not old.current:
                _fail("only a current approval can be superseded")

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
            _fail("an approval with the same immutable binding already exists")
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
            _fail("receipt_id must be an approval:sha256:<lowercase-sha256> identifier")
        state = self._records.get(receipt_id)
        if state is None:
            _fail("unknown receipt_id")
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
            (
                "hardcoded_unresolved_references_digest",
                _field_digest(plan, "hardcoded_unresolved_references"),
            ),
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
