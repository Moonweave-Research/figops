"""Unit parsing and compatibility helpers for semantic data-contract checks."""

from __future__ import annotations

import re
from typing import Any

_UNIT_TOKEN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\^(-?\d+))?$")


def parse_unit_signature(unit: str) -> dict[str, int]:
    raw = str(unit).replace(" ", "")
    if not raw:
        raise ValueError("unit must be non-empty")

    signature: dict[str, int] = {}
    pending = ""
    operator = 1
    for char in raw + "*":
        if char in "*/":
            if not pending:
                raise ValueError(f"malformed unit expression '{unit}'")
            if pending != "1":
                match = _UNIT_TOKEN_RE.match(pending)
                if not match:
                    raise ValueError(f"unsupported unit token '{pending}'")
                base, exponent_text = match.groups()
                exponent = int(exponent_text or "1") * operator
                signature[base] = signature.get(base, 0) + exponent
                if signature[base] == 0:
                    del signature[base]
            pending = ""
            operator = 1 if char == "*" else -1
        else:
            pending += char
    return signature


def format_unit_signature(signature: dict[str, int]) -> str:
    if not signature:
        return "1"
    return "*".join(
        f"{unit}^{exponent}" if exponent != 1 else unit
        for unit, exponent in sorted(signature.items())
    )


def check_unit_compatibility(
    col_name: str,
    actual_unit_str: str,
    expected_unit_str: str,
    *,
    pint_available: bool,
    ureg: Any,
    log_func,
    dimensionality_error: type[Exception] | tuple[type[Exception], ...],
):
    """
    Validate unit compatibility using a supplied Pint registry.

    Returns:
        "ok"            -- same unit
        (factor, a, b)  -- compatible, conversion factor returned
        "incompatible"  -- dimensionality mismatch
        "skip"          -- Pint unavailable or unit parsing failed
    """
    if not pint_available:
        log_func(f"      ⚠️  Column '{col_name}': unit check skipped (pint not installed)")
        return "skip"

    try:
        expected = ureg.parse_expression(expected_unit_str)
        actual = ureg.parse_expression(actual_unit_str)
    except Exception:
        log_func(f"      ⚠️  Column '{col_name}': could not parse units ('{actual_unit_str}' or '{expected_unit_str}')")
        return "skip"

    if actual.units == expected.units:
        return "ok"

    try:
        factor = actual.to(expected.units).magnitude
        return (factor, actual_unit_str, expected_unit_str)
    except dimensionality_error:
        return "incompatible"
