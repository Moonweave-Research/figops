"""Journal-minimum projections over policy-free live-figure observations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from themes.compliance import resolve_journal_compliance_tokens


def geometry_minimum_results(
    measurements: Sequence[Mapping[str, Any]] | None,
    *,
    validation_target: str,
    profile: str = "baseline",
) -> list[dict[str, Any]]:
    """Return required font, line, and height outcomes without mutating a figure."""

    tokens = resolve_journal_compliance_tokens(validation_target, profile)
    if tokens is None:
        return _unavailable_results("journal geometry minima are unavailable for the selected target/profile")
    observation, reason = _style_observation(measurements)
    if observation is None:
        return _unavailable_results(reason)

    font_sizes = _positive_values(observation.get("font_sizes"), "fontsize_pt")
    line_widths = _positive_values(observation.get("line_widths"), "linewidth_pt")
    height = _positive_number(observation.get("figure_height_mm"))
    if font_sizes is None or line_widths is None or height is None:
        return _unavailable_results("style geometry observations are malformed or incomplete")

    min_font = float(tokens["min_font_size_pt"])
    min_line = float(tokens["min_line_width_pt"])
    max_height = float(tokens["max_figure_height_mm"])
    observed_font = min(font_sizes) if font_sizes else None
    observed_line = min(line_widths) if line_widths else None
    return [
        _result(
            "minimum_font_size",
            "style_geometry_observations",
            "pass" if observed_font is None or observed_font >= min_font else "fail",
            observed_font,
            min_font,
            "the figure contains no visible text artists" if observed_font is None else None,
        ),
        _result(
            "minimum_line_width",
            "style_geometry_observations",
            "pass" if observed_line is None or observed_line >= min_line else "fail",
            observed_line,
            min_line,
            "the figure contains no visible line or edge artists" if observed_line is None else None,
        ),
        _result(
            "maximum_figure_height",
            "style_geometry_observations",
            "pass" if height <= max_height else "fail",
            height,
            max_height,
        ),
    ]


def _style_observation(
    measurements: Sequence[Mapping[str, Any]] | None,
) -> tuple[Mapping[str, Any] | None, str]:
    matches: list[Mapping[str, Any]] = []
    for item in measurements or ():
        metric_id = item.get("metric_id", item.get("id"))
        if str(metric_id or "").split("[", 1)[0] != "style_geometry_observations":
            continue
        matches.append(item)
    if len(matches) != 1:
        return None, "exactly one style geometry observation is required"
    item = matches[0]
    if item.get("availability") != "available" or not isinstance(item.get("value"), Mapping):
        return None, str(item.get("reason") or "style geometry observation is unavailable")
    return item["value"], ""


def _positive_values(value: Any, key: str) -> list[float] | None:
    if not isinstance(value, list):
        return None
    values: list[float] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        number = _positive_number(item.get(key))
        if number is None:
            return None
        values.append(number)
    return values


def _positive_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number > 0 else None


def _unavailable_results(reason: str) -> list[dict[str, Any]]:
    return [
        _result(check_id, "style_geometry_observations", "not_applicable", None, expected, reason)
        for check_id, expected in (
            ("minimum_font_size", None),
            ("minimum_line_width", None),
            ("maximum_figure_height", None),
        )
    ]


def _result(
    check_id: str,
    metric_id: str,
    status: str,
    observed: Any,
    expected: Any,
    reason: str | None = None,
) -> dict[str, Any]:
    item = {
        "check_id": check_id,
        "metric_id": metric_id,
        "status": status,
        "observed": observed,
        "expected": expected,
        "enforcement": "required",
    }
    if reason:
        item["reason"] = reason
    return item


__all__ = ["geometry_minimum_results"]
