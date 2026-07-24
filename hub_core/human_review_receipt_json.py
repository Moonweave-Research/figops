"""JSON, canonicalization, and scalar helpers for human review receipts."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any, Mapping, NoReturn

from .human_review_receipt_types import HumanReviewReceiptError

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_32_RE = re.compile(r"^[0-9a-f]{32}$")
_RECEIPT_ID_RE = re.compile(r"^review:sha256:([0-9a-f]{64})$")
_AUTHORITY_ASSERTION_RE = re.compile(r"^[a-z][a-z0-9-]*/[1-9][0-9]*$")
_RFC3339_UTC_SECONDS_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
_ABSOLUTE_OR_MUTABLE_REF_RE = re.compile(
    r"^(?:[A-Za-z]:[\\/]|[\\/]{1,2}|~(?:[\\/]|$)|(?:file|https?|runtime|raw):)",
    re.IGNORECASE,
)
_DOMAIN_PREFIX = b"figops-human-review-v1\0"


def fail(message: str) -> NoReturn:
    raise HumanReviewReceiptError(f"human review receipt {message}")


def closed_mapping(value: Any, allowed: set[str] | frozenset[str], field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        fail(f"{field} must be a mapping")
    keys = set(value)
    non_string = [key for key in keys if not isinstance(key, str)]
    if non_string:
        fail(f"{field} keys must be strings")
    missing = sorted(allowed - keys)
    unknown = sorted(keys - allowed)
    if missing or unknown:
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if unknown:
            detail.append(f"unsupported {', '.join(unknown)}")
        fail(f"{field} contains {' and '.join(detail)}")
    return value


def text(value: Any, field: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value:
        fail(f"{field} must be a non-empty string")
    value = unicodedata.normalize("NFC", value)
    if value != value.strip() or len(value) > max_length:
        fail(f"{field} must be canonical and at most {max_length} characters")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        fail(f"{field} may not contain control characters")
    return value


def sha256(value: Any, field: str) -> str:
    value = text(value, field, max_length=64)
    if _SHA256_RE.fullmatch(value) is None:
        fail(f"{field} must be a lowercase SHA-256 digest")
    return value


def receipt_id(value: Any, field: str) -> str:
    value = text(value, field, max_length=78)
    if _RECEIPT_ID_RE.fullmatch(value) is None:
        fail(f"{field} must be review:sha256:<lowercase-sha256>")
    return value


def opaque_id(value: Any, field: str, namespace: str) -> str:
    value = text(value, field, max_length=len(namespace) + 33)
    prefix, separator, suffix = value.partition(":")
    if prefix != namespace or separator != ":" or _OPAQUE_32_RE.fullmatch(suffix) is None:
        fail(f"{field} must be an opaque {namespace}:<128-bit-hex> identifier")
    return value


def enum_value(value: Any, field: str, allowed: frozenset[str]) -> str:
    value = text(value, field, max_length=64)
    if value not in allowed:
        fail(f"{field} has an unsupported value")
    return value


def timestamp(value: Any, field: str) -> str:
    value = text(value, field, max_length=20)
    if _RFC3339_UTC_SECONDS_RE.fullmatch(value) is None:
        fail(f"{field} must be an RFC 3339 UTC timestamp with seconds precision and Z suffix")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise HumanReviewReceiptError(f"human review receipt {field} must be a real timestamp") from exc
    return value


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def authority_assertion(value: Any, field: str = "reviewer.authority_assertion") -> str:
    value = text(value, field, max_length=64)
    if _AUTHORITY_ASSERTION_RE.fullmatch(value) is None:
        fail(f"{field} must be a versioned policy binding token")
    return value


def reject_path_like_subject(value: str, field: str) -> None:
    if _ABSOLUTE_OR_MUTABLE_REF_RE.search(value) or ".." in value or "\\" in value or "/" in value:
        fail(f"{field} must not contain an absolute path, runtime/raw URI, or mutable path-like reference")


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise HumanReviewReceiptError(f"human review receipt must be finite JSON: {exc}") from exc


def digest(domain: str, payload: bytes) -> str:
    return hashlib.sha256(_DOMAIN_PREFIX + domain.encode("ascii") + b"\0" + payload).hexdigest()


def opaque_domain_id(namespace: str, value: Any) -> str:
    value = text(value, f"{namespace}_source_id", max_length=1024)
    return f"{namespace}:{digest(f'opaque:{namespace}', value.encode('utf-8'))[:32]}"


def opaque_project_id(value: Any) -> str:
    return opaque_domain_id("project", value)


def opaque_principal_id(value: Any) -> str:
    return opaque_domain_id("principal", value)


def opaque_figure_artifact_id(value: Any) -> str:
    return opaque_domain_id("result.figure", value)


def opaque_concern_id(value: Any) -> str:
    return opaque_domain_id("concern", value)


def opaque_waiver_id(value: Any) -> str:
    return opaque_domain_id("waiver", value)


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                fail("JSON object keys must be strings")
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in result:
                raise HumanReviewReceiptError(
                    f"human review receipt contains duplicate JSON key after NFC normalization {normalized_key!r}"
                )
            result[normalized_key] = _normalize_json_value(child)
        return result
    if value is None or isinstance(value, bool):
        return value
    fail("may contain only strings, booleans, null, arrays, and objects")


def _json_pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HumanReviewReceiptError(f"human review receipt contains duplicate JSON key {key!r}")
        result[key] = value
    return result


def _json_constant(value: str) -> NoReturn:
    raise HumanReviewReceiptError(f"human review receipt contains non-finite JSON value {value}")


def parse_json_bytes(data: bytes | bytearray | memoryview) -> Mapping[str, Any]:
    try:
        raw = bytes(data)
    except (TypeError, ValueError) as exc:
        raise HumanReviewReceiptError("human review receipt JSON input must be bytes") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        fail("JSON bytes must be UTF-8 without a BOM")
    try:
        decoded = raw.decode("utf-8")
        parsed = json.loads(decoded, object_pairs_hook=_json_pairs_no_duplicates, parse_constant=_json_constant)
    except UnicodeDecodeError as exc:
        raise HumanReviewReceiptError("human review receipt JSON bytes must be valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise HumanReviewReceiptError(f"human review receipt JSON is invalid: {exc.msg}") from exc
    normalized = _normalize_json_value(parsed)
    if not isinstance(normalized, Mapping):
        fail("top-level JSON value must be an object")
    return normalized
