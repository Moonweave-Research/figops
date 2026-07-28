"""Strict JSON and scalar helpers for policy resolution."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Mapping
from typing import Any, NoReturn

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]{1,2}|~[\\/]|(?:file|runtime|raw):)", re.I)


class PolicyResolutionError(ValueError):
    """Raised when policy inputs cannot resolve to one deterministic value."""


def parse_json_array(data: bytes | bytearray | memoryview) -> tuple[dict[str, Any], ...]:
    raw = bytes(data)
    if raw.startswith(b"\xef\xbb\xbf"):
        fail("JSON bytes must be UTF-8 without a BOM")
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyResolutionError(f"policy JSON is invalid: {exc}") from exc
    parsed = normalize_json_value(parsed)
    if not isinstance(parsed, list):
        fail("top-level policy JSON must be an array")
    return tuple(parsed)


def closed(value: Any, allowed: set[str], field: str, *, subset: bool = False) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        fail(f"{field} must be a mapping")
    keys = set(value)
    if any(not isinstance(key, str) for key in keys) or keys - allowed or (allowed - keys and not subset):
        fail(f"{field} contains unsupported or missing keys")
    return value


def set_value(value: Any, field: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        fail(f"{field}.allowed must be a non-empty array")
    normalized = tuple(normalize_json_value(item) for item in value)
    if len(set(normalized)) != len(normalized):
        fail(f"{field}.allowed contains duplicate values")
    return normalized


def normalize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        value = unicodedata.normalize("NFC", value)
        if _PATH_RE.search(value) or "\\" in value or value.startswith("../"):
            fail("policy input contains a path-like string")
        return value
    if isinstance(value, bool) or value is None or isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else fail("policy input contains non-finite number")
    if isinstance(value, list):
        return [normalize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalize_json_value(item) for item in value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            normalized = normalize_json_value(key)
            if not isinstance(normalized, str) or normalized in result:
                fail("policy object keys must be unique strings")
            result[normalized] = normalize_json_value(child)
        return result
    fail("policy input contains unsupported JSON value")


def token(value: Any, field: str) -> str:
    value = normalize_json_value(value)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        fail(f"{field} must be a canonical non-empty string")
    return value


def finite_number(value: Any, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        fail(f"{field} must be a finite number")
    return value


def sha256(value: Any, field: str) -> str:
    value = token(value, field)
    if _SHA256_RE.fullmatch(value) is None:
        fail(f"{field} must be a lowercase SHA-256 digest")
    return value


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def fail(message: str) -> NoReturn:
    raise PolicyResolutionError(f"policy resolution {message}")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyResolutionError(f"policy JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    raise PolicyResolutionError(f"policy JSON contains non-finite value {value}")
