from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


def group_points(points: list[dict], spec: Any) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for point in points:
        key = point["series"] if spec.series_column and point["series"] else "__single__"
        grouped.setdefault(str(key), []).append(point)
    return grouped


def first_seen_values(values: Sequence[float | str]) -> list[float | str]:
    ordered: list[float | str] = []
    for value in values:
        if value not in ordered:
            ordered.append(value)
    return ordered


def format_order_values(values: Sequence[float | str]) -> str:
    return ", ".join(str(value) for value in values)


def resolve_explicit_order(
    data_order: Sequence[float | str],
    explicit_order: Sequence[float | str],
    *,
    field_name: str,
) -> list[float | str]:
    if not explicit_order:
        return list(data_order)
    explicit = [normalize_order_value(value, data_order) for value in explicit_order]
    duplicates = [value for index, value in enumerate(explicit) if value in explicit[:index]]
    if duplicates:
        raise ValueError(f"{field_name} contains duplicate value(s): {format_order_values(duplicates)}")
    missing = [value for value in data_order if value not in explicit]
    if missing:
        raise ValueError(f"{field_name} is missing data category value(s): {format_order_values(missing)}")
    extra = [value for value in explicit if value not in data_order]
    if extra:
        raise ValueError(f"{field_name} includes value(s) not present in data: {format_order_values(extra)}")
    return explicit


def normalize_order_value(value: float | str, data_order: Sequence[float | str]) -> float | str:
    if value in data_order:
        return value
    if any(isinstance(item, float) for item in data_order):
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            pass
        else:
            if numeric in data_order:
                return numeric
    text = str(value)
    if text in data_order:
        return text
    return value


def optional_error_float(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def yerr_values(points: list[dict], spec: Any):
    if not spec.yerr_column and not spec.yerr_minus_column:
        return None
    if spec.yerr_minus_column:
        minus = [optional_error_float(point.get("yerr_minus")) for point in points]
        if any(value is None for value in minus):
            return None
        # When only the lower (minus) column is configured, mirror it onto the upper
        # bound so the configured error data is never silently dropped (symmetric from
        # the minus values). With both columns present, use them as asymmetric bounds.
        plus = [optional_error_float(point.get("yerr")) for point in points] if spec.yerr_column else minus
        if any(value is None for value in plus):
            return None
        return np.array([minus, plus])
    yerr = [optional_error_float(point.get("yerr")) for point in points]
    if any(value is None for value in yerr):
        return None
    return yerr
