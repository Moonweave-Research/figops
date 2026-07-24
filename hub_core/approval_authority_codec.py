"""Canonical encoding and validation for approval authority records.

The approval authority lifecycle lives in :mod:`approval_authority_lifecycle`.
This module owns the deterministic JSON representation and the immutable
binding that is signed by the process-local authority root.  Keeping these
operations separate makes the security boundary easier to audit while
retaining the same exceptions and canonical digest behaviour as the public
``approval_authority`` module.
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


__all__ = [
    "ApprovalAuthorityError",
    "ApprovalBinding",
    "approval_binding_digest",
    "canonical_approval_binding_bytes",
    "canonical_json_bytes",
    "canonical_plan_digest",
]
