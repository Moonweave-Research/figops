"""Manuscript multipanel layout math for bridge rendering."""

from __future__ import annotations

import math
from typing import Any, Callable

LegendLayoutResolver = Callable[[Any], str]


def validated_layout_ratios(values: tuple[float, ...], *, expected_len: int, field_name: str) -> None:
    if not values:
        return
    if len(values) != expected_len:
        raise ValueError(f"{field_name} must contain exactly {expected_len} value(s)")
    for value in values:
        if not math.isfinite(float(value)) or value <= 0:
            raise ValueError(f"{field_name} values must be positive finite numbers")


def distributed_lengths_mm(total_mm: float, count: int, ratios: tuple[float, ...]) -> tuple[float, ...]:
    effective_ratios = ratios or tuple(1.0 for _ in range(count))
    ratio_sum = sum(effective_ratios)
    return tuple(total_mm * (ratio / ratio_sum) for ratio in effective_ratios)


def manuscript_axis_rect(
    panel: Any,
    *,
    fig_w_mm: float,
    fig_h_mm: float,
    cell_left_mm: float,
    cell_bottom_mm: float,
    cell_w_mm: float,
    cell_h_mm: float,
    panel_image_type: type,
    publication_layout_specs_mm: dict[str, Any],
    resolved_legend_layout: LegendLayoutResolver,
) -> list[float]:
    box_width_mm, box_height_mm, margins_mm = panel_geometry_mm(
        panel,
        panel_image_type=panel_image_type,
        publication_layout_specs_mm=publication_layout_specs_mm,
        resolved_legend_layout=resolved_legend_layout,
    )
    if box_width_mm > cell_w_mm or box_height_mm > cell_h_mm:
        raise ValueError(
            "manuscript compose requires panel box to fit within its slot: "
            f"box=({box_width_mm:.1f}mm,{box_height_mm:.1f}mm), "
            f"slot=({cell_w_mm:.1f}mm,{cell_h_mm:.1f}mm)"
        )

    extra_w_mm = cell_w_mm - box_width_mm
    extra_h_mm = cell_h_mm - box_height_mm
    left_extra_mm, _ = split_bias(extra_w_mm, margins_mm["left"], margins_mm["right"])
    bottom_extra_mm, _ = split_bias(extra_h_mm, margins_mm["bottom"], margins_mm["top"])

    ax_left_mm = cell_left_mm + left_extra_mm
    ax_bottom_mm = cell_bottom_mm + bottom_extra_mm
    ax_width = box_width_mm / fig_w_mm
    ax_height = box_height_mm / fig_h_mm
    ax_left = ax_left_mm / fig_w_mm
    ax_bottom = ax_bottom_mm / fig_h_mm

    return [ax_left, ax_bottom, ax_width, ax_height]


def panel_geometry_mm(
    panel: Any,
    *,
    panel_image_type: type,
    publication_layout_specs_mm: dict[str, Any],
    resolved_legend_layout: LegendLayoutResolver,
) -> tuple[float, float, dict[str, float]]:
    if isinstance(panel, panel_image_type):
        layout_key = "standard"
    else:
        if str(panel.target_format or "").lower() == "ppt":
            raise ValueError("manuscript compose does not support PPT panel geometry")
        layout_key = resolved_legend_layout(panel)
        if layout_key not in publication_layout_specs_mm:
            raise ValueError(
                "manuscript compose requires fixed-layout panels; "
                f"got legend_layout={layout_key!r}. Use standard, top_outside, or right_outside."
            )

    spec = publication_layout_specs_mm[layout_key]
    margins = {key: float(value) for key, value in spec["margins_mm"].items()}
    return float(spec["box_width_mm"]), float(spec["box_height_mm"]), margins


def split_bias(total_mm: float, primary_mm: float, secondary_mm: float) -> tuple[float, float]:
    if total_mm <= 0:
        return 0.0, 0.0
    weight_sum = float(primary_mm + secondary_mm)
    if weight_sum <= 0:
        half = total_mm / 2.0
        return half, half
    primary = total_mm * (float(primary_mm) / weight_sum)
    return primary, total_mm - primary
