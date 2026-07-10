"""Recursive redaction for failure artifacts that must remain diagnostically useful."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Final

_SENSITIVE_KEYS: Final = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "auth_token",
        "authorization",
        "bearer_token",
        "client_key",
        "client_secret",
        "cookie",
        "credential",
        "credentials",
        "id_token",
        "password",
        "passwd",
        "private_key",
        "refresh_token",
        "secret",
        "secret_key",
        "secret_token",
        "session_token",
        "token",
    }
)
_SENSITIVE_FIELD: Final = (
    r"(?:api[_-]?key|authorization|cookie|credentials?|password|passwd|secret|token|"
    r"(?:access|auth|bearer|client|id|private|refresh|secret|session)[_-](?:key|password|secret|token))"
)
_CREDENTIAL_URL: Final = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/@\s:]+(?::[^@/\s]*)?@", re.IGNORECASE)
_ASSIGNMENT_SECRET: Final = re.compile(
    rf"(?i)(?<![a-z0-9_])(?P<key>{_SENSITIVE_FIELD})\s*(?P<sep>[:=])\s*[^\s,&;]+"
)
_BEARER_SECRET: Final = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_BASIC_SECRET: Final = re.compile(r"(?i)\bAuthorization\s*:\s*Basic\s+[^\s,;]+")
_QUOTED_SECRET_VALUE: Final = re.compile(
    rf"(?i)(?<![a-z0-9_])(?P<prefix>[\"']?{_SENSITIVE_FIELD}[\"']?\s*:\s*)"
    r"(?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*')"
)
_REDACTED: Final = "[REDACTED]"


def redact_secrets(value: object) -> object:
    """Return a JSON-compatible copy with secret-bearing keys and values removed."""
    if isinstance(value, Mapping):
        return {
            str(key): _REDACTED if _is_sensitive_key(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_secrets(item) for item in value]
    return value


def redact_text(value: str) -> str:
    """Redact credentialed URLs and conventional credential assignments in text."""
    basic_safe = _BASIC_SECRET.sub("Authorization: Basic [REDACTED]", value)
    bearer_safe = _BEARER_SECRET.sub("Bearer [REDACTED]", basic_safe)
    credential_safe = _CREDENTIAL_URL.sub(r"\g<scheme>[REDACTED]@", bearer_safe)
    quoted_safe = _QUOTED_SECRET_VALUE.sub(r"\g<prefix>[REDACTED]", credential_safe)
    return _ASSIGNMENT_SECRET.sub(
        lambda match: f"{match.group('key')}{match.group('sep')}{_REDACTED}", quoted_safe
    )


def _is_sensitive_key(value: str) -> bool:
    normalized = re.sub(r"[-.\s]+", "_", value.casefold()).strip("_")
    return normalized in _SENSITIVE_KEYS


def redact_locals(
    locals_map: Mapping[str, object],
    allowlisted_keys: frozenset[str] | None = None,
) -> dict[str, object]:
    """Persist only explicitly allowlisted locals, always passed through recursive redaction."""
    allowed = allowlisted_keys or frozenset()
    return {key: redact_secrets(value) for key, value in locals_map.items() if key in allowed}
