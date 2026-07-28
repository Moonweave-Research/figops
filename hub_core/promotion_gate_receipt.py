"""Canonical receipt candidate for pure promotion-gate decisions."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any, Final

SCHEMA_VERSION: Final = "figops-promotion-gate/1"
GATE_STATUSES: Final = frozenset({"blocked", "needs_revision", "needs_review", "eligible"})
GATE_OUTCOMES: Final = frozenset({"passed", "blocked", "needs_revision", "needs_review"})
GATE_CODE_ORDER: Final = (
    "WORKFLOW_PROMOTION_ALLOWED",
    "CANDIDATE_ARTIFACT_BOUND",
    "RUNTIME_MANIFEST_ELIGIBLE",
    "LINEAGE_RECEIPT_VALID",
    "POLICY_RESOLUTION_VALID",
    "PUBLICATION_READINESS_AUTOMATED",
    "HUMAN_REVIEW_SIGNOFF",
)
GATE_CODES: Final = frozenset(GATE_CODE_ORDER)
_RECEIPT_ID_RE: Final = re.compile(r"^promotion-gate:sha256:([0-9a-f]{64})$")
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_ID_RE: Final = re.compile(r"^(project|result\.figure):[0-9a-f]{32}$")
_PATH_LIKE_RE: Final = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]{1,2}|~(?:[\\/]|$)|(?:file|https?|runtime|raw):)", re.I)
_TEXT_LEAK_RE: Final = re.compile(
    r"(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|[\\/]{2}|~[\\/]|(?:file|https?|runtime|raw):)",
    re.I,
)
_CONTAINED_DESTINATION_RE: Final = re.compile(
    r"^(?!/)(?![A-Za-z]:)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$"
)
_PAYLOAD_FIELDS: Final = {
    "schema_version",
    "gate_status",
    "subject",
    "digests",
    "gates",
    "requested_destination",
}
_RECEIPT_FIELDS: Final = _PAYLOAD_FIELDS | {"receipt_id", "integrity"}


class PromotionGateReceiptError(ValueError):
    """Raised when a promotion-gate receipt candidate is not canonical."""


def _fail(message: str) -> None:
    raise PromotionGateReceiptError(f"promotion gate receipt {message}")


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("contains a non-finite number")
        return value
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFC", value)
        if any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized):
            _fail("contains a control character")
        return normalized
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                _fail("object keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in result:
                _fail("object keys must be unique after NFC normalization")
            result[normalized_key] = _canonical_value(child)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, memoryview, str)):
        return [_canonical_value(item) for item in value]
    _fail(f"contains unsupported JSON value {type(value).__name__}")


def canonical_promotion_gate_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Return the byte-stable JSON encoding used by gate reports and receipts."""

    normalized = _canonical_value(value)
    if not isinstance(normalized, Mapping):
        _fail("canonical input must be a mapping")
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def promotion_gate_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_promotion_gate_json_bytes(value)).hexdigest()


def _closed(value: Any, allowed: set[str] | frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{field} must be a mapping")
    keys = set(value)
    if any(not isinstance(key, str) for key in keys):
        _fail(f"{field} keys must be strings")
    if keys != allowed:
        _fail(f"{field} contains missing or unsupported fields")
    return value


def _validate_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail(f"{field} must be a lowercase SHA-256")
    return value


def _validate_opaque_id(value: Any, field: str, namespace: str) -> str:
    if not isinstance(value, str) or _OPAQUE_ID_RE.fullmatch(value) is None:
        _fail(f"{field} must be an opaque {namespace}:<128-bit-hex> identifier")
    prefix = value.partition(":")[0]
    if prefix != namespace:
        _fail(f"{field} must be an opaque {namespace}:<128-bit-hex> identifier")
    if _PATH_LIKE_RE.search(value) or ".." in value or "\\" in value or "/" in value:
        _fail(f"{field} must not contain a path, URI, runtime/raw reference, or traversal")
    return value


def _validate_safe_text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        _fail(f"{field} must be a string")
    if _TEXT_LEAK_RE.search(value) or ".." in value or "\\" in value:
        _fail(f"{field} must not contain a path, URI, runtime/raw reference, or traversal")
    lowered = value.casefold()
    for marker in ("secret=", "password=", "api_key=", "apikey=", "token="):
        if marker in lowered:
            _fail(f"{field} must not contain secret-like material")
    return value


def _validate_destination(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        _fail("requested_destination must be a string or null")
    if _PATH_LIKE_RE.search(value) or "\\" in value or _CONTAINED_DESTINATION_RE.fullmatch(value) is None:
        _fail("requested_destination must be a contained project-relative token")
    return value


def _derived_status(gates: list[dict[str, Any]]) -> str:
    outcomes = [gate["outcome"] for gate in gates]
    if "blocked" in outcomes:
        return "blocked"
    if "needs_revision" in outcomes:
        return "needs_revision"
    if "needs_review" in outcomes:
        return "needs_review"
    return "eligible"


def _validate_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = _closed(_canonical_value(value), _PAYLOAD_FIELDS, "payload")
    if payload["schema_version"] != SCHEMA_VERSION:
        _fail(f"schema_version must be {SCHEMA_VERSION!r}")
    gate_status = payload["gate_status"]
    if gate_status not in GATE_STATUSES:
        _fail("gate_status is outside the closed enum")
    subject = payload["subject"]
    if subject is not None:
        subject = dict(_closed(subject, {
            "project_id",
            "artifact_id",
            "artifact_sha256",
            "lineage_receipt_sha256",
            "evidence_digest",
            "resolved_policy_digest",
            "subject_digest",
        }, "subject"))
        for field in (
            "artifact_sha256",
            "lineage_receipt_sha256",
            "evidence_digest",
            "resolved_policy_digest",
            "subject_digest",
        ):
            _validate_sha(subject[field], f"subject.{field}")
        subject["project_id"] = _validate_opaque_id(subject["project_id"], "subject.project_id", "project")
        subject["artifact_id"] = _validate_opaque_id(
            subject["artifact_id"],
            "subject.artifact_id",
            "result.figure",
        )
    digests = dict(_closed(payload["digests"], {
        "report_sha256",
        "lineage_receipt_sha256",
        "publication_evidence_sha256",
        "resolved_policy_sha256",
        "review_receipt_sha256",
    }, "digests"))
    for field, digest in digests.items():
        if digest is not None:
            digests[field] = _validate_sha(digest, f"digests.{field}")
    gates = payload["gates"]
    if not isinstance(gates, list) or not gates:
        _fail("gates must be a non-empty array")
    normalized_gates: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, gate in enumerate(gates):
        item = dict(_closed(gate, {"code", "outcome", "evidence_ref", "message"}, f"gates[{index}]"))
        code = item["code"]
        outcome = item["outcome"]
        if code not in GATE_CODES:
            _fail(f"gates[{index}].code is outside the closed enum")
        if code in seen_codes:
            _fail("gates contain duplicate codes")
        seen_codes.add(code)
        if outcome not in GATE_OUTCOMES:
            _fail(f"gates[{index}].outcome is outside the closed enum")
        for field in ("evidence_ref", "message"):
            item[field] = _validate_safe_text(item[field], f"gates[{index}].{field}")
        normalized_gates.append(item)
    if seen_codes != GATE_CODES:
        _fail("gates must contain exactly the closed promotion gate code set")
    if [gate["code"] for gate in normalized_gates] != list(GATE_CODE_ORDER):
        _fail("gates must use the canonical promotion gate order")
    derived_status = _derived_status(normalized_gates)
    if gate_status != derived_status:
        _fail("gate_status must match the derived gate outcome precedence")
    if gate_status == "eligible":
        if subject is None:
            _fail("eligible receipt requires a bound subject")
        for field in ("lineage_receipt_sha256", "publication_evidence_sha256", "resolved_policy_sha256"):
            if digests[field] is None:
                _fail(f"eligible receipt requires digests.{field}")
    if subject is not None:
        digest_bindings = {
            "lineage_receipt_sha256": "lineage_receipt_sha256",
            "publication_evidence_sha256": "evidence_digest",
            "resolved_policy_sha256": "resolved_policy_digest",
        }
        for digest_field, subject_field in digest_bindings.items():
            if digests[digest_field] is not None and subject[subject_field] != digests[digest_field]:
                _fail(f"subject.{subject_field} must match digests.{digest_field}")
    destination = _validate_destination(payload["requested_destination"])
    return {
        "schema_version": SCHEMA_VERSION,
        "gate_status": gate_status,
        "subject": subject,
        "digests": digests,
        "gates": normalized_gates,
        "requested_destination": destination,
    }


def build_promotion_gate_receipt(
    *,
    gate_status: str,
    subject: Mapping[str, Any] | None,
    digests: Mapping[str, Any],
    gates: Sequence[Mapping[str, Any]],
    requested_destination: str | None = None,
) -> dict[str, Any]:
    """Build a self-identifying canonical receipt candidate without persisting it."""

    payload = _validate_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "gate_status": gate_status,
            "subject": subject,
            "digests": digests,
            "gates": list(gates),
            "requested_destination": requested_destination,
        }
    )
    payload_digest = promotion_gate_digest(payload)
    return {
        **payload,
        "receipt_id": f"promotion-gate:sha256:{payload_digest}",
        "integrity": {"canonical_sha256": payload_digest},
    }


def validate_promotion_gate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    normalized = _closed(_canonical_value(receipt), _RECEIPT_FIELDS, "receipt")
    payload = _validate_payload({key: normalized[key] for key in _PAYLOAD_FIELDS})
    expected_digest = promotion_gate_digest(payload)
    receipt_id = normalized["receipt_id"]
    if not isinstance(receipt_id, str) or _RECEIPT_ID_RE.fullmatch(receipt_id) is None:
        _fail("receipt_id must be promotion-gate:sha256:<lowercase-sha256>")
    if receipt_id != f"promotion-gate:sha256:{expected_digest}":
        _fail("receipt_id does not match canonical payload digest")
    integrity = _closed(normalized["integrity"], {"canonical_sha256"}, "integrity")
    if integrity["canonical_sha256"] != expected_digest:
        _fail("integrity.canonical_sha256 does not match canonical payload digest")
    return {**payload, "receipt_id": receipt_id, "integrity": {"canonical_sha256": expected_digest}}


def canonical_promotion_gate_receipt_bytes(receipt: Mapping[str, Any]) -> bytes:
    return canonical_promotion_gate_json_bytes(validate_promotion_gate_receipt(receipt))


__all__ = [
    "GATE_CODES",
    "GATE_CODE_ORDER",
    "GATE_OUTCOMES",
    "GATE_STATUSES",
    "PromotionGateReceiptError",
    "SCHEMA_VERSION",
    "build_promotion_gate_receipt",
    "canonical_promotion_gate_json_bytes",
    "canonical_promotion_gate_receipt_bytes",
    "promotion_gate_digest",
    "validate_promotion_gate_receipt",
]
