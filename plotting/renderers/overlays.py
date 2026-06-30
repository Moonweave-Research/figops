from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties

from plotting.renderers.axes import visible_plot_axes
from plotting.renderers.labels import AVOID_OVERLAP_OFFSETS
from plotting.renderers.legend import apply_legend
from plotting.utils import annotate_significance


def has_statistical_overlays(spec: Any) -> bool:
    return bool(spec.fit_line or spec.ci_band or spec.fit_options or spec.significance_markers)


def has_manual_overlays(spec: Any) -> bool:
    return bool(spec.guide_curves or spec.fill_between)


def validate_manual_overlays(spec: Any) -> None:
    if not has_manual_overlays(spec):
        return
    plot_type = str(spec.plot_type or "").strip().lower()
    if plot_type not in {"line", "scatter", "xy"}:
        raise ValueError(
            f"manual overlays are only supported for plot_type 'line', 'scatter', or 'xy'; got {spec.plot_type!r}"
        )
    if spec.y_break_range is not None:
        raise ValueError("manual overlays do not support y_break_range")


def validate_statistical_overlays(points: list[dict], spec: Any) -> None:
    if not has_statistical_overlays(spec):
        return
    normalized_fit_options(spec.fit_options)
    if spec.fit_options and not (spec.fit_line or spec.ci_band):
        raise ValueError("fit_options requires fit_line or ci_band")
    plot_type = str(spec.plot_type or "").strip().lower()
    if plot_type not in {"line", "scatter", "xy"}:
        raise ValueError(
            f"statistical overlays are only supported for plot_type 'line', 'scatter', or 'xy'; got {spec.plot_type!r}"
        )
    if spec.y_break_range is not None:
        raise ValueError("statistical overlays do not support y_break_range")
    if spec.fit_line or spec.ci_band:
        min_points = 3 if spec.ci_band else 2
        numeric_xy_arrays(points, min_points=min_points, context="fit_line/ci_band")
    normalized_significance_markers(spec.significance_markers)


def numeric_xy_arrays(points: list[dict], *, min_points: int, context: str) -> tuple[np.ndarray, np.ndarray]:
    xs: list[float] = []
    ys: list[float] = []
    for point in points:
        try:
            x_val = float(point["x"])
            y_val = float(point["y"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{context} requires numeric x and y values") from exc
        if not math.isfinite(x_val) or not math.isfinite(y_val):
            raise ValueError(f"{context} requires finite x and y values")
        xs.append(x_val)
        ys.append(y_val)

    if len(xs) < min_points:
        raise ValueError(f"{context} requires at least {min_points} valid points")
    if len(set(xs)) < 2:
        raise ValueError(f"{context} requires at least two distinct x values")
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


def finite_float(value: object, *, context: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{context} must be finite")
    return number


def normalized_fit_options(value: object) -> dict[str, object]:
    if value in (None, {}, ()):
        return {}
    if not isinstance(value, dict):
        raise ValueError("fit_options must be an object")
    allowed_keys = {"model", "label", "color", "linestyle", "linewidth", "zorder", "ci_alpha", "ci_label"}
    unsupported = sorted(str(key) for key in value if key not in allowed_keys)
    if unsupported:
        raise ValueError(f"fit_options has unsupported key(s): {', '.join(unsupported)}")
    model = str(value.get("model") or "linear").strip().lower()
    if model != "linear":
        raise ValueError("fit_options.model must be 'linear'")
    normalized: dict[str, object] = {"model": "linear"}
    for key in ("label", "color", "linestyle", "ci_label"):
        if key not in value or value.get(key) is None:
            continue
        text = str(value[key]).strip()
        if text:
            normalized[key] = text
    if "linewidth" in value and value.get("linewidth") is not None:
        linewidth = finite_float(value["linewidth"], context="fit_options.linewidth")
        if linewidth <= 0:
            raise ValueError("fit_options.linewidth must be positive")
        normalized["linewidth"] = linewidth
    if "zorder" in value and value.get("zorder") is not None:
        normalized["zorder"] = finite_float(value["zorder"], context="fit_options.zorder")
    if "ci_alpha" in value and value.get("ci_alpha") is not None:
        ci_alpha = finite_float(value["ci_alpha"], context="fit_options.ci_alpha")
        if ci_alpha < 0 or ci_alpha > 1:
            raise ValueError("fit_options.ci_alpha must be between 0 and 1")
        normalized["ci_alpha"] = ci_alpha
    return normalized


def overlay_xy_arrays(overlay: dict, *, field_name: str) -> tuple[list[float], list[float]]:
    if not isinstance(overlay, dict):
        raise ValueError(f"{field_name} entries must be objects")
    points = overlay.get("points")
    if points is not None:
        if not isinstance(points, (list, tuple)):
            raise ValueError(f"{field_name}.points must be an array")
        xs: list[float] = []
        ys: list[float] = []
        if len(points) < 2:
            raise ValueError(f"{field_name}.points must contain at least two points")
        for index, point in enumerate(points):
            if not isinstance(point, dict):
                raise ValueError(f"{field_name}.points[{index}] must be an object")
            missing = [key for key in ("x", "y") if key not in point]
            if missing:
                raise ValueError(f"{field_name}.points[{index}] missing required field(s): {', '.join(missing)}")
            xs.append(finite_float(point["x"], context=f"{field_name}.points[{index}].x"))
            ys.append(finite_float(point["y"], context=f"{field_name}.points[{index}].y"))
        return xs, ys

    x_values = overlay.get("x")
    y_values = overlay.get("y")
    if not isinstance(x_values, (list, tuple)) or not isinstance(y_values, (list, tuple)):
        raise ValueError(f"{field_name} requires points or x/y arrays")
    if len(x_values) != len(y_values):
        raise ValueError(f"{field_name}.x and {field_name}.y must have the same length")
    if len(x_values) < 2:
        raise ValueError(f"{field_name}.x and {field_name}.y must contain at least two points")
    return (
        [finite_float(value, context=f"{field_name}.x[{index}]") for index, value in enumerate(x_values)],
        [finite_float(value, context=f"{field_name}.y[{index}]") for index, value in enumerate(y_values)],
    )


def fill_between_arrays(
    csv_path: Path,
    overlay: dict,
    *,
    field_name: str,
) -> tuple[list[float], list[float], list[float]]:
    if not isinstance(overlay, dict):
        raise ValueError(f"{field_name} entries must be objects")
    points = overlay.get("points")
    if points is not None:
        if not isinstance(points, (list, tuple)):
            raise ValueError(f"{field_name}.points must be an array")
        xs: list[float] = []
        y1s: list[float] = []
        y2s: list[float] = []
        if len(points) < 2:
            raise ValueError(f"{field_name}.points must contain at least two points")
        for index, point in enumerate(points):
            if not isinstance(point, dict):
                raise ValueError(f"{field_name}.points[{index}] must be an object")
            missing = [key for key in ("x", "y1", "y2") if key not in point]
            if missing:
                raise ValueError(f"{field_name}.points[{index}] missing required field(s): {', '.join(missing)}")
            xs.append(finite_float(point["x"], context=f"{field_name}.points[{index}].x"))
            y1s.append(finite_float(point["y1"], context=f"{field_name}.points[{index}].y1"))
            y2s.append(finite_float(point["y2"], context=f"{field_name}.points[{index}].y2"))
        return xs, y1s, y2s

    x_column = str(overlay.get("x_column") or "").strip()
    y1_column = str(overlay.get("y1_column") or "").strip()
    y2_column = str(overlay.get("y2_column") or "").strip()
    if not x_column or not y1_column or not y2_column:
        raise ValueError(f"{field_name} requires points or x_column, y1_column, and y2_column")
    xs: list[float] = []
    y1s: list[float] = []
    y2s: list[float] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        missing = [column for column in (x_column, y1_column, y2_column) if column not in headers]
        if missing:
            raise ValueError(f"{field_name} CSV column(s) missing: {', '.join(missing)}")
        for row_index, row in enumerate(reader, start=2):
            xs.append(finite_float(row[x_column], context=f"{field_name}.{x_column} row {row_index}"))
            y1s.append(finite_float(row[y1_column], context=f"{field_name}.{y1_column} row {row_index}"))
            y2s.append(finite_float(row[y2_column], context=f"{field_name}.{y2_column} row {row_index}"))
    if len(xs) < 2:
        raise ValueError(f"{field_name} requires at least two rows")
    return xs, y1s, y2s


def overlay_line_kwargs(overlay: dict) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "color": str(overlay.get("color") or "black"),
        "linewidth": float(overlay.get("linewidth", 1.0)),
        "linestyle": str(overlay.get("linestyle") or "-"),
        "zorder": float(overlay.get("zorder", 4)),
    }
    if overlay.get("label"):
        kwargs["label"] = str(overlay["label"])
    return kwargs


def draw_manual_overlays(ax, csv_path: Path, spec: Any) -> None:
    for index, overlay in enumerate(spec.fill_between or ()):
        region = dict(overlay)
        if not region.get("points") and not str(region.get("x_column") or "").strip():
            region["x_column"] = spec.x_column
        xs, y1s, y2s = fill_between_arrays(csv_path, region, field_name=f"fill_between[{index}]")
        kwargs: dict[str, object] = {
            "color": str(region.get("color") or "black"),
            "alpha": float(region.get("alpha", 0.15)),
            "linewidth": 0,
            "zorder": float(region.get("zorder", 1)),
        }
        if region.get("label"):
            kwargs["label"] = str(region["label"])
        artist = ax.fill_between(xs, y1s, y2s, **kwargs)
        tag_overlay_artist(artist, role="fill_between", label=str(region.get("label") or f"fill_between[{index}]"))

    for index, overlay in enumerate(spec.guide_curves or ()):
        xs, ys = overlay_xy_arrays(overlay, field_name=f"guide_curves[{index}]")
        ax.plot(xs, ys, **overlay_line_kwargs(overlay))

    if any(isinstance(overlay, dict) and overlay.get("label") for overlay in (*spec.fill_between, *spec.guide_curves)):
        apply_legend(ax, spec, n_series=1)


def tag_overlay_artist(artist, *, role: str, label: str) -> None:
    artist._graph_hub_overlay_role = role
    artist._graph_hub_overlay_label = label


def tag_annotation_text(artist, *, role: str) -> None:
    artist._graph_hub_annotation_text_role = role


CALLOUT_OFFSET_PRESETS: dict[str, tuple[float, float]] = {
    "above": (0.0, 10.0),
    "below": (0.0, -10.0),
    "left": (-10.0, 0.0),
    "right": (10.0, 0.0),
    "upper_left": (-8.0, 8.0),
    "upper_right": (8.0, 8.0),
    "lower_left": (-8.0, -8.0),
    "lower_right": (8.0, -8.0),
}


def reject_non_point_callout_fields(annotation: dict[str, object], index: int) -> None:
    unsupported = [
        key
        for key in ("xytext_offset", "placement_preset", "avoid_overlap")
        if key in annotation and annotation.get(key) is not None
    ]
    if unsupported:
        joined = ", ".join(unsupported)
        raise ValueError(f"annotations[{index}] {joined} only apply to point annotations")


def normalized_callout_offset(annotation: dict[str, object], index: int) -> tuple[float, float] | None:
    raw_offset = annotation.get("xytext_offset")
    if raw_offset is not None:
        if not isinstance(raw_offset, dict):
            raise ValueError(f"annotations[{index}].xytext_offset must be an object")
        try:
            dx = float(raw_offset["dx"])
            dy = float(raw_offset["dy"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"annotations[{index}].xytext_offset requires numeric dx and dy") from exc
        if not math.isfinite(dx) or not math.isfinite(dy):
            raise ValueError(f"annotations[{index}].xytext_offset dx and dy must be finite")
        return (dx, dy)
    preset = str(annotation.get("placement_preset") or "").strip().lower().replace("-", "_")
    if preset:
        if preset not in CALLOUT_OFFSET_PRESETS:
            allowed = ", ".join(sorted(CALLOUT_OFFSET_PRESETS))
            raise ValueError(f"annotations[{index}].placement_preset must be one of: {allowed}")
        return CALLOUT_OFFSET_PRESETS[preset]
    raw_avoid_overlap = annotation.get("avoid_overlap", False)
    if not isinstance(raw_avoid_overlap, bool):
        raise ValueError(f"annotations[{index}].avoid_overlap must be a boolean")
    if raw_avoid_overlap:
        return AVOID_OVERLAP_OFFSETS[index % len(AVOID_OVERLAP_OFFSETS)]
    return None


def normalized_span_annotation(
    annotation: dict[str, object],
    index: int,
    *,
    field: str,
    bounds: tuple[str, str],
) -> dict[str, object]:
    span = annotation[field]
    if not isinstance(span, dict):
        raise ValueError(f"annotations[{index}].{field} must be an object")
    lower_key, upper_key = bounds
    try:
        lower = float(span[lower_key])
        upper = float(span[upper_key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"annotations[{index}].{field} requires numeric {lower_key} and {upper_key}") from exc
    if not math.isfinite(lower) or not math.isfinite(upper):
        raise ValueError(f"annotations[{index}].{field} bounds must be finite")
    try:
        alpha = float(annotation.get("alpha", 0.12))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"annotations[{index}].alpha must be numeric") from exc
    return {
        "kind": field,
        lower_key: lower,
        upper_key: upper,
        "text": str(annotation.get("text") or "").strip(),
        "color": str(annotation.get("color") or "black"),
        "alpha": alpha,
    }


def normalized_annotations(annotations: object) -> tuple[dict[str, object], ...]:
    if annotations in (None, (), []):
        return ()
    if not isinstance(annotations, (list, tuple)):
        raise ValueError("annotations must be an array of objects")
    normalized: list[dict[str, object]] = []
    for index, annotation in enumerate(annotations):
        if not isinstance(annotation, dict):
            raise ValueError(f"annotations[{index}] must be an object")
        region = annotation.get("region")
        if region is not None:
            reject_non_point_callout_fields(annotation, index)
            if not isinstance(region, dict):
                raise ValueError(f"annotations[{index}].region must be an object")
            try:
                xmin = float(region["xmin"])
                xmax = float(region["xmax"])
                ymin = float(region["ymin"])
                ymax = float(region["ymax"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"annotations[{index}].region requires numeric xmin, xmax, ymin, ymax") from exc
            if not all(math.isfinite(value) for value in (xmin, xmax, ymin, ymax)):
                raise ValueError(f"annotations[{index}].region bounds must be finite")
            try:
                alpha = float(annotation.get("alpha", 0.12))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"annotations[{index}].alpha must be numeric") from exc
            normalized.append(
                {
                    "kind": "region",
                    "xmin": xmin,
                    "xmax": xmax,
                    "ymin": ymin,
                    "ymax": ymax,
                    "text": str(annotation.get("text") or "").strip(),
                    "color": str(annotation.get("color") or "black"),
                    "alpha": alpha,
                }
            )
            continue
        if annotation.get("hspan") is not None:
            reject_non_point_callout_fields(annotation, index)
            normalized.append(
                normalized_span_annotation(annotation, index, field="hspan", bounds=("ymin", "ymax"))
            )
            continue
        if annotation.get("vspan") is not None:
            reject_non_point_callout_fields(annotation, index)
            normalized.append(
                normalized_span_annotation(annotation, index, field="vspan", bounds=("xmin", "xmax"))
            )
            continue
        missing = [key for key in ("x", "y") if key not in annotation]
        if missing:
            raise ValueError(f"annotations[{index}] missing required field(s): {', '.join(missing)}")
        try:
            x = float(annotation["x"])
            y = float(annotation["y"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"annotations[{index}] x and y must be numeric") from exc
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError(f"annotations[{index}] x and y must be finite")
        text = str(annotation.get("text") or "").strip()
        arrow_to = annotation.get("arrow_to")
        if not text and arrow_to is None:
            raise ValueError(f"annotations[{index}] text must be non-empty unless arrow_to is provided")
        normalized_arrow = None
        if arrow_to is not None:
            if not isinstance(arrow_to, dict):
                raise ValueError(f"annotations[{index}].arrow_to must be an object")
            try:
                arrow_x = float(arrow_to["x"])
                arrow_y = float(arrow_to["y"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"annotations[{index}].arrow_to requires numeric x and y") from exc
            if not math.isfinite(arrow_x) or not math.isfinite(arrow_y):
                raise ValueError(f"annotations[{index}].arrow_to x and y must be finite")
            normalized_arrow = {"x": arrow_x, "y": arrow_y}
        arrowstyle = str(annotation.get("arrowstyle") or "->").strip() or "->"
        connectionstyle = str(annotation.get("connectionstyle") or "").strip()
        item = {
            "kind": "point",
            "x": x,
            "y": y,
            "text": text,
            "arrow_to": normalized_arrow,
            "color": str(annotation.get("color") or "black"),
            "arrowstyle": arrowstyle,
        }
        callout_offset = normalized_callout_offset(annotation, index)
        if callout_offset is not None:
            item["xytext_offset"] = callout_offset
        if connectionstyle:
            item["connectionstyle"] = connectionstyle
        normalized.append(item)
    return tuple(normalized)


def annotation_font_size() -> float:
    for key in ("xtick.labelsize", "legend.fontsize"):
        try:
            return float(FontProperties(size=plt.rcParams[key]).get_size_in_points())
        except (KeyError, ValueError, TypeError):
            continue
    return 6.5


def span_midpoint(lower: float, upper: float) -> float:
    return math.sqrt(lower * upper) if lower > 0 and upper > 0 else 0.5 * (lower + upper)


def draw_annotations(ax, spec: Any) -> None:
    font_size = annotation_font_size()
    for annotation in normalized_annotations(spec.annotations):
        color = str(annotation["color"])
        if annotation.get("kind") == "region":
            xmin = float(annotation["xmin"])
            xmax = float(annotation["xmax"])
            ymin = float(annotation["ymin"])
            ymax = float(annotation["ymax"])
            region_text = str(annotation["text"])
            artist = ax.fill_between(
                [xmin, xmax],
                ymin,
                ymax,
                color=color,
                alpha=float(annotation["alpha"]),
                linewidth=0,
                zorder=0,
            )
            tag_overlay_artist(artist, role="annotation_region", label=region_text or "region")
            if region_text:
                text_artist = ax.text(
                    span_midpoint(xmin, xmax),
                    span_midpoint(ymin, ymax),
                    region_text,
                    color=color,
                    fontsize=font_size,
                    ha="center",
                    va="center",
                    zorder=1,
                    clip_on=True,
                )
                tag_annotation_text(text_artist, role="annotation_region")
            continue
        if annotation.get("kind") == "hspan":
            ymin = float(annotation["ymin"])
            ymax = float(annotation["ymax"])
            artist = ax.axhspan(
                ymin,
                ymax,
                color=color,
                alpha=float(annotation["alpha"]),
                linewidth=0,
                zorder=0,
            )
            span_text = str(annotation["text"])
            tag_overlay_artist(artist, role="annotation_hspan", label=span_text or "hspan")
            if span_text:
                text_artist = ax.text(
                    0.5,
                    span_midpoint(ymin, ymax),
                    span_text,
                    transform=ax.get_yaxis_transform(),
                    color=color,
                    fontsize=font_size,
                    ha="center",
                    va="center",
                    zorder=1,
                    clip_on=True,
                )
                tag_annotation_text(text_artist, role="annotation_hspan")
            continue
        if annotation.get("kind") == "vspan":
            xmin = float(annotation["xmin"])
            xmax = float(annotation["xmax"])
            artist = ax.axvspan(
                xmin,
                xmax,
                color=color,
                alpha=float(annotation["alpha"]),
                linewidth=0,
                zorder=0,
            )
            span_text = str(annotation["text"])
            tag_overlay_artist(artist, role="annotation_vspan", label=span_text or "vspan")
            if span_text:
                text_artist = ax.text(
                    span_midpoint(xmin, xmax),
                    0.5,
                    span_text,
                    transform=ax.get_xaxis_transform(),
                    color=color,
                    fontsize=font_size,
                    ha="center",
                    va="center",
                    zorder=1,
                    clip_on=True,
                )
                tag_annotation_text(text_artist, role="annotation_vspan")
            continue
        x = float(annotation["x"])
        y = float(annotation["y"])
        text = str(annotation["text"])
        arrow_to = annotation.get("arrow_to")
        xytext_offset = annotation.get("xytext_offset")
        use_offset = isinstance(xytext_offset, tuple)
        if isinstance(arrow_to, dict) or use_offset:
            arrowprops = None
            if isinstance(arrow_to, dict):
                arrowprops = {
                    "arrowstyle": str(annotation.get("arrowstyle") or "->"),
                    "color": color,
                    "linewidth": 0.8,
                }
                if annotation.get("connectionstyle"):
                    arrowprops["connectionstyle"] = str(annotation["connectionstyle"])
                xy = (float(arrow_to["x"]), float(arrow_to["y"]))
            else:
                xy = (x, y)
            annotate_kwargs = {
                "xy": xy,
                "xytext": xytext_offset if use_offset else (x, y),
                "color": color,
                "fontsize": font_size,
                "ha": "left",
                "va": "bottom",
                "zorder": 6,
                "annotation_clip": True,
                "clip_on": True,
            }
            if arrowprops is not None:
                annotate_kwargs["arrowprops"] = arrowprops
            if use_offset:
                annotate_kwargs["textcoords"] = "offset points"
            text_artist = ax.annotate(text, **annotate_kwargs)
            tag_annotation_text(text_artist, role="annotation_point")
        else:
            text_artist = ax.text(
                x,
                y,
                text,
                color=color,
                fontsize=font_size,
                ha="left",
                va="bottom",
                zorder=6,
                clip_on=True,
            )
            tag_annotation_text(text_artist, role="annotation_point")


def draw_annotations_on_visible_axes(fig, fallback_ax, spec: Any) -> None:
    if not spec.annotations:
        return
    axes = visible_plot_axes(fig, fallback_ax)
    if spec.plot_type == "facet":
        axes = axes[:1]
    for axis in axes:
        draw_annotations(axis, spec)


def normalized_significance_markers(markers: object) -> tuple[dict[str, float | str | None], ...]:
    if markers in (None, (), []):
        return ()
    if not isinstance(markers, (list, tuple)):
        raise ValueError("significance_markers must be an array of objects")

    normalized = []
    for idx, marker in enumerate(markers):
        if not isinstance(marker, dict):
            raise ValueError(f"significance_markers[{idx}] must be an object")
        missing = [key for key in ("x1", "x2", "y") if key not in marker]
        if missing:
            raise ValueError(f"significance_markers[{idx}] missing required field(s): {', '.join(missing)}")
        try:
            x1 = float(marker["x1"])
            x2 = float(marker["x2"])
            y = float(marker["y"])
            h = float(marker["h"]) if marker.get("h") is not None else None
        except (TypeError, ValueError) as exc:
            raise ValueError(f"significance_markers[{idx}] x1, x2, y, and h must be numeric") from exc
        if not all(math.isfinite(value) for value in (x1, x2, y)) or (h is not None and not math.isfinite(h)):
            raise ValueError(f"significance_markers[{idx}] x1, x2, y, and h must be finite")
        label = str(marker.get("label") or marker.get("text") or "*")
        color = str(marker.get("color") or "black")
        normalized.append({"x1": x1, "x2": x2, "y": y, "h": h, "label": label, "color": color})
    return tuple(normalized)


def draw_statistical_overlays(ax, points: list[dict], spec: Any) -> None:
    if not has_statistical_overlays(spec):
        return
    if spec.fit_line or spec.ci_band:
        draw_linear_fit_overlay(ax, points, spec)
    for marker in normalized_significance_markers(spec.significance_markers):
        annotate_significance(
            ax,
            marker["x1"],
            marker["x2"],
            marker["y"],
            str(marker["label"]),
            h=marker["h"],
            color=str(marker["color"]),
        )


def draw_linear_fit_overlay(ax, points: list[dict], spec: Any) -> None:
    options = normalized_fit_options(spec.fit_options)
    xs, ys = numeric_xy_arrays(points, min_points=3 if spec.ci_band else 2, context="fit_line/ci_band")
    slope, intercept = np.polyfit(xs, ys, 1)
    x_grid = np.linspace(float(xs.min()), float(xs.max()), 200)
    y_grid = slope * x_grid + intercept
    fit_color = str(options.get("color") or "black")
    ax.plot(
        x_grid,
        y_grid,
        color=fit_color,
        linewidth=float(options.get("linewidth") or 1.0),
        linestyle=str(options.get("linestyle") or "-"),
        label=str(options.get("label") or "Linear fit"),
        zorder=float(options.get("zorder") if "zorder" in options else 4),
    )

    if not spec.ci_band:
        return

    dof = len(xs) - 2
    if dof <= 0:
        raise ValueError("ci_band requires at least 3 valid points")
    residuals = ys - (slope * xs + intercept)
    sxx = float(np.sum((xs - float(xs.mean())) ** 2))
    if sxx <= 0:
        raise ValueError("ci_band requires at least two distinct x values")
    residual_std = math.sqrt(float(np.sum(residuals**2)) / dof)
    se_mean = residual_std * np.sqrt((1 / len(xs)) + ((x_grid - float(xs.mean())) ** 2 / sxx))
    t_crit = t_critical_95(dof)
    ax.fill_between(
        x_grid,
        y_grid - t_crit * se_mean,
        y_grid + t_crit * se_mean,
        color=fit_color,
        alpha=float(options.get("ci_alpha") if "ci_alpha" in options else 0.12),
        linewidth=0,
        label=str(options.get("ci_label") or "95% CI"),
        zorder=1,
    )


def t_critical_95(dof: int) -> float:
    try:
        from scipy.stats import t

        return float(t.ppf(0.975, dof))
    except Exception:
        return 1.96
