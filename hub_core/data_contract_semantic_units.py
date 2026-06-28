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


def check_unit_coherence_constraint(
    col,
    raw_check,
    stripped_to_actual,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
    append_calculation_check,
    append_failed_calculation_check,
):
    if not isinstance(raw_check, dict):
        message = f"Column '{col}': unit_coherence must be a mapping"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="unit_coherence",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    expected_unit = raw_check.get("expected_unit")
    terms = raw_check.get("terms")
    if not isinstance(expected_unit, str) or not expected_unit.strip():
        message = f"Column '{col}': unit_coherence.expected_unit must be a non-empty string"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="unit_coherence",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []
    if not isinstance(terms, list) or not terms:
        message = f"Column '{col}': unit_coherence.terms must be a non-empty list"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="unit_coherence",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    combined: dict[str, int] = {}
    term_payloads = []
    for idx, term in enumerate(terms, 1):
        if not isinstance(term, dict):
            message = f"Column '{col}': unit_coherence.terms[{idx}] must be a mapping"
            append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="unit_coherence",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        term_column = term.get("column")
        term_unit = term.get("unit")
        exponent = term.get("exponent", 1)
        if not isinstance(term_column, str) or not term_column.strip() or term_column.strip() not in stripped_to_actual:
            message = f"Column '{col}': unit_coherence term column not found: {term_column!r}"
            append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="unit_coherence",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        if not isinstance(term_unit, str) or not term_unit.strip():
            message = f"Column '{col}': unit_coherence term unit must be a non-empty string"
            append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="unit_coherence",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent == 0:
            message = f"Column '{col}': unit_coherence term exponent must be a non-zero integer"
            append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="unit_coherence",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        try:
            term_signature = parse_unit_signature(term_unit)
        except ValueError as exc:
            message = f"Column '{col}': unit_coherence term unit parse failed: {exc}"
            append_failed_calculation_check(
                calculation_checks,
                csv_rel_path=csv_rel_path,
                name="unit_coherence",
                target=col,
                source_config_path=source_config_path,
                message=message,
            )
            return [message], []
        for unit, power in term_signature.items():
            combined[unit] = combined.get(unit, 0) + power * exponent
            if combined[unit] == 0:
                del combined[unit]
        term_payloads.append({"column": term_column.strip(), "unit": term_unit.strip(), "exponent": exponent})

    try:
        expected_signature = parse_unit_signature(expected_unit)
    except ValueError as exc:
        message = f"Column '{col}': unit_coherence expected_unit parse failed: {exc}"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="unit_coherence",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    observed = format_unit_signature(combined)
    expected = format_unit_signature(expected_signature)
    if combined == expected_signature:
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="unit_coherence",
            target=col,
            group_by=[],
            source_config_path=source_config_path,
            status="passed",
            manual_review_needed=False,
            message=f"Related units combine to expected unit '{expected}'",
            violations=[],
        )
        return [], []

    message = f"Column '{col}': unit_coherence expected '{expected}', got '{observed}'"
    violation = {
        "column": col,
        "value": observed,
        "expected": expected,
        "terms": term_payloads,
        "violation_type": "unit_coherence",
    }
    append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="unit_coherence",
        target=col,
        group_by=[],
        source_config_path=source_config_path,
        status="failed",
        manual_review_needed=False,
        message=message,
        violations=[violation],
    )
    return [message], [
        {
            "row": "*",
            "column": col,
            "value": observed,
            "expected": expected,
            "violation_type": "unit_coherence",
        }
    ]


def check_axis_unit_constraint(
    col,
    raw_check,
    *,
    calculation_checks=None,
    csv_rel_path: str,
    source_config_path: str,
    unit_checker,
    append_calculation_check,
    append_failed_calculation_check,
    json_safe_value,
):
    if not isinstance(raw_check, dict):
        message = f"Column '{col}': axis_unit must be a mapping"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="axis_unit",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    data_unit = raw_check.get("data_unit")
    display_unit = raw_check.get("display_unit")
    if (
        not isinstance(data_unit, str)
        or not data_unit.strip()
        or not isinstance(display_unit, str)
        or not display_unit.strip()
    ):
        message = f"Column '{col}': axis_unit data_unit and display_unit must be non-empty strings"
        append_failed_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="axis_unit",
            target=col,
            source_config_path=source_config_path,
            message=message,
        )
        return [message], []

    result = unit_checker(col, data_unit.strip(), display_unit.strip())
    if result == "incompatible":
        message = f"Column '{col}': axis_unit '{data_unit}' is incompatible with display unit '{display_unit}'"
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="axis_unit",
            target=col,
            group_by=[],
            source_config_path=source_config_path,
            status="failed",
            manual_review_needed=False,
            message=message,
            violations=[
                {
                    "column": col,
                    "value": data_unit,
                    "expected": display_unit,
                    "violation_type": "axis_unit_incompatible",
                }
            ],
        )
        return [message], [
            {
                "row": "*",
                "column": col,
                "value": data_unit,
                "expected": display_unit,
                "violation_type": "axis_unit_incompatible",
            }
        ]

    if result == "skip":
        message = f"Column '{col}': axis_unit check skipped; manual review required"
        append_calculation_check(
            calculation_checks,
            csv_rel_path=csv_rel_path,
            name="axis_unit",
            target=col,
            group_by=[],
            source_config_path=source_config_path,
            status="skipped",
            manual_review_needed=True,
            message=message,
            violations=[],
        )
        return [], []

    if isinstance(result, tuple):
        factor, from_unit, to_unit = result
        message = f"Axis unit '{from_unit}' is compatible with '{to_unit}' (x{factor})"
        violations = [{"conversion_factor": json_safe_value(factor), "from_unit": from_unit, "to_unit": to_unit}]
    else:
        message = f"Axis unit '{data_unit}' matches display unit '{display_unit}'"
        violations = []
    append_calculation_check(
        calculation_checks,
        csv_rel_path=csv_rel_path,
        name="axis_unit",
        target=col,
        group_by=[],
        source_config_path=source_config_path,
        status="passed",
        manual_review_needed=False,
        message=message,
        violations=violations,
    )
    return [], []
