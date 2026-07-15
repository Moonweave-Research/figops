from __future__ import annotations

import math
from typing import Any

LEGEND_LAYOUT_PRESETS = {"auto", "smart", "standard", "best", "top_outside", "right_outside"}
_ANNOTATION_CLAIM_KEYS = {
    "annotation_kind",
    "calculation_evidence_id",
    "analysis_artifact_sha256",
    "test_metadata",
}


def _normalized_annotation_claim_fields(annotation: dict[str, Any], index: int) -> dict[str, Any]:
    kind = str(annotation.get("annotation_kind") or "auto").strip().lower()
    if kind not in {"auto", "literal", "statistical_claim"}:
        raise ValueError(f"annotations[{index}].annotation_kind is unsupported.")
    normalized: dict[str, Any] = {}
    if "annotation_kind" in annotation:
        normalized["annotation_kind"] = kind
    for key in ("calculation_evidence_id", "analysis_artifact_sha256"):
        if key not in annotation:
            continue
        value = annotation[key]
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise ValueError(f"annotations[{index}].{key} must be a bounded non-empty string.")
        if key == "analysis_artifact_sha256" and (
            len(value) != 64 or any(character not in "0123456789abcdefABCDEF" for character in value)
        ):
            raise ValueError(f"annotations[{index}].analysis_artifact_sha256 must be a SHA-256 hex digest.")
        normalized[key] = value.lower() if key == "analysis_artifact_sha256" else value
    if "test_metadata" in annotation:
        metadata = annotation["test_metadata"]
        if not isinstance(metadata, dict) or set(metadata) != {"test_name", "model"}:
            raise ValueError(f"annotations[{index}].test_metadata must contain only test_name and model.")
        normalized_metadata: dict[str, str] = {}
        for key in ("test_name", "model"):
            value = metadata[key]
            if not isinstance(value, str) or not value.strip() or len(value) > 256:
                raise ValueError(f"annotations[{index}].test_metadata.{key} must be bounded and non-empty.")
            normalized_metadata[key] = value
        normalized["test_metadata"] = normalized_metadata
    return normalized


def _validated_plot_argument_compatibility(
    *,
    plot_type: str,
    raw_annotate_values: Any,
    raw_bar_error_column: Any,
    raw_yerr_column: Any,
    raw_yerr_minus_column: Any,
    raw_yerr_cap_width: Any,
    series_column: str,
    label_column: str,
    point_label_options: dict[str, Any],
    guide_curves: list[dict[str, Any]],
    fill_between: list[dict[str, Any]],
) -> dict[str, Any]:
    annotate_values = raw_annotate_values
    bar_error_column = ""
    yerr_column = ""
    yerr_minus_column = ""
    yerr_cap_width = 3.0
    errors: list[str] = []
    if not isinstance(annotate_values, bool):
        errors.append("annotate_values must be a boolean.")
        annotate_values = False
    elif annotate_values and plot_type != "heatmap":
        errors.append("annotate_values is only supported for plot_type 'heatmap'.")
    if raw_bar_error_column is not None and raw_bar_error_column != "":
        if not isinstance(raw_bar_error_column, str):
            errors.append("bar_error_column must be a string.")
        else:
            bar_error_column = raw_bar_error_column.strip()
            if not bar_error_column:
                errors.append("bar_error_column must be a non-empty string when provided.")
            elif plot_type != "bar":
                errors.append("bar_error_column is only supported for plot_type 'bar'.")
    for raw_error_column, field_name in (
        (raw_yerr_column, "yerr_column"),
        (raw_yerr_minus_column, "yerr_minus_column"),
    ):
        if raw_error_column is None or raw_error_column == "":
            continue
        if not isinstance(raw_error_column, str):
            errors.append(f"{field_name} must be a string.")
            continue
        stripped_error_column = raw_error_column.strip()
        if not stripped_error_column:
            errors.append(f"{field_name} must be a non-empty string when provided.")
            continue
        if plot_type not in {"line", "scatter", "xy"}:
            errors.append(f"{field_name} is only supported for plot_type 'line', 'scatter', or 'xy'.")
            continue
        if field_name == "yerr_column":
            yerr_column = stripped_error_column
        else:
            yerr_minus_column = stripped_error_column
    if raw_yerr_cap_width is not None:
        try:
            yerr_cap_width = float(raw_yerr_cap_width)
        except (TypeError, ValueError):
            errors.append("yerr_cap_width must be numeric.")
        else:
            if yerr_cap_width < 0:
                errors.append("yerr_cap_width must be non-negative.")
    if yerr_column and bar_error_column:
        errors.append("Use yerr_column for line/scatter/xy or bar_error_column for bar, not both.")
    if series_column and plot_type not in {"line", "scatter", "xy"}:
        errors.append("series_column is only supported for plot_type 'line', 'scatter', or 'xy'.")
    if label_column and plot_type not in {"line", "scatter", "xy", "bar"}:
        errors.append("label_column is only supported for plot_type 'line', 'scatter', 'xy', or 'bar'.")
    if point_label_options and not label_column:
        errors.append("point_label_options requires label_column.")
    if (guide_curves or fill_between) and plot_type not in {"line", "scatter", "xy"}:
        errors.append("guide_curves and fill_between are only supported for plot_type 'line', 'scatter', or 'xy'.")
    return {
        "annotate_values": annotate_values,
        "bar_error_column": bar_error_column,
        "yerr_column": yerr_column,
        "yerr_minus_column": yerr_minus_column,
        "yerr_cap_width": yerr_cap_width,
        "errors": errors,
    }


def _normalized_legend_layout_arg(value: Any, *, field_name: str) -> str:
    layout = str(value or "auto").strip().lower()
    if layout not in LEGEND_LAYOUT_PRESETS:
        allowed = ", ".join(sorted(LEGEND_LAYOUT_PRESETS))
        raise ValueError(f"{field_name} must be one of: {allowed}.")
    return layout


def _normalized_axis_scale_arg(value: Any, *, field_name: str) -> str:
    scale = str(value or "linear").strip().lower()
    if scale not in {"linear", "log"}:
        raise ValueError(f"{field_name} must be 'linear' or 'log'.")
    return scale


def _normalized_secondary_y_arg(value: Any) -> dict[str, Any] | None:
    if value in (None, {}, []):
        return None
    if not isinstance(value, dict):
        raise ValueError("secondary_y must be an object.")
    unsupported = sorted(set(value) - {"enabled", "column", "axis_label", "scale", "series_label", "limits"})
    if unsupported:
        raise ValueError(f"secondary_y has unsupported key(s): {', '.join(unsupported)}.")
    if value.get("enabled") is False:
        return None
    column = str(value.get("column") or "").strip()
    if not column:
        raise ValueError("secondary_y.column is required when secondary_y is enabled.")
    scale = _normalized_axis_scale_arg(value.get("scale"), field_name="secondary_y.scale")
    item: dict[str, Any] = {"column": column, "scale": scale}
    axis_label = str(value.get("axis_label") or "").strip()
    if axis_label:
        item["axis_label"] = axis_label
    series_label = str(value.get("series_label") or "").strip()
    if series_label:
        item["series_label"] = series_label
    raw_limits = value.get("limits")
    if raw_limits not in (None, {}, []):
        item["limits"] = _normalized_axis_limits_arg(
            {"y": raw_limits},
            field_name="secondary_y.limits",
            x_scale="linear",
            y_scale=scale,
        )["y"]
    return item


def _normalized_axis_limits_arg(
    value: Any, *, field_name: str, x_scale: str, y_scale: str
) -> dict[str, dict[str, float]]:
    if value in (None, {}, []):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object keyed by x and/or y.")
    unsupported = sorted(set(value) - {"x", "y"})
    if unsupported:
        raise ValueError(f"{field_name} has unsupported key(s): {', '.join(unsupported)}.")
    normalized: dict[str, dict[str, float]] = {}
    for axis_name, scale in (("x", x_scale), ("y", y_scale)):
        raw_pair = value.get(axis_name)
        if raw_pair in (None, {}):
            continue
        if not isinstance(raw_pair, dict):
            raise ValueError(f"{field_name}.{axis_name} must be an object with min and/or max.")
        unsupported_pair = sorted(set(raw_pair) - {"min", "max"})
        if unsupported_pair:
            raise ValueError(
                f"{field_name}.{axis_name} has unsupported key(s): {', '.join(unsupported_pair)}."
            )
        if not any(key in raw_pair for key in ("min", "max")):
            raise ValueError(f"{field_name}.{axis_name} must contain min and/or max.")
        item: dict[str, float] = {}
        for key in ("min", "max"):
            if raw_pair.get(key) is None or raw_pair.get(key) == "":
                continue
            try:
                numeric = float(raw_pair[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name}.{axis_name}.{key} must be numeric.") from exc
            if not math.isfinite(numeric):
                raise ValueError(f"{field_name}.{axis_name}.{key} must be finite.")
            if scale == "log" and numeric <= 0:
                raise ValueError(f"{field_name}.{axis_name}.{key} must be > 0 when {axis_name}_scale='log'.")
            item[key] = numeric
        if "min" in item and "max" in item and item["min"] >= item["max"]:
            raise ValueError(f"{field_name}.{axis_name}.min must be less than {field_name}.{axis_name}.max.")
        if item:
            normalized[axis_name] = item
    return normalized


def _normalized_tick_style_arg(value: Any, *, field_name: str) -> dict[str, Any]:
    if value in (None, {}, []):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object.")
    allowed = {"rotation", "format", "max_label_chars"}
    unsupported = sorted(set(value) - allowed)
    if unsupported:
        raise ValueError(f"{field_name} has unsupported key(s): {', '.join(unsupported)}.")
    normalized: dict[str, Any] = {}
    if value.get("rotation") is not None:
        try:
            rotation = float(value["rotation"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name}.rotation must be numeric.") from exc
        if not math.isfinite(rotation) or not -360 <= rotation <= 360:
            raise ValueError(f"{field_name}.rotation must be finite and between -360 and 360.")
        normalized["rotation"] = rotation
    if value.get("format") is not None:
        tick_format = str(value["format"]).strip().lower()
        if tick_format not in {"default", "plain", "scientific", "compact"}:
            raise ValueError(f"{field_name}.format must be default, plain, scientific, or compact.")
        normalized["format"] = tick_format
    if value.get("max_label_chars") is not None:
        try:
            max_label_chars = int(value["max_label_chars"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name}.max_label_chars must be an integer.") from exc
        if max_label_chars < 4:
            raise ValueError(f"{field_name}.max_label_chars must be at least 4.")
        normalized["max_label_chars"] = max_label_chars
    return normalized


def _normalized_multipanel_layout_options_arg(
    value: Any, *, rows: int, cols: int, field_name: str
) -> dict[str, Any]:
    if value in (None, {}, []):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object.")
    allowed = {"wspace", "hspace", "gutter_h_mm", "gutter_v_mm", "width_ratios", "height_ratios"}
    unsupported = sorted(set(value) - allowed)
    if unsupported:
        raise ValueError(f"{field_name} has unsupported key(s): {', '.join(unsupported)}.")
    normalized: dict[str, Any] = {}
    for key in ("wspace", "hspace", "gutter_h_mm", "gutter_v_mm"):
        if value.get(key) is None:
            continue
        try:
            numeric = float(value[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name}.{key} must be numeric.") from exc
        if not math.isfinite(numeric) or numeric < 0:
            raise ValueError(f"{field_name}.{key} must be a non-negative finite number.")
        normalized[key] = numeric
    for key, expected_len in (("width_ratios", cols), ("height_ratios", rows)):
        if value.get(key) is None:
            continue
        raw_values = value[key]
        if not isinstance(raw_values, list) or not raw_values:
            raise ValueError(f"{field_name}.{key} must be a non-empty array.")
        if len(raw_values) != expected_len:
            raise ValueError(f"{field_name}.{key} must contain exactly {expected_len} value(s).")
        ratios: list[float] = []
        for raw_value in raw_values:
            try:
                numeric = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field_name}.{key} values must be numeric.") from exc
            if not math.isfinite(numeric) or numeric <= 0:
                raise ValueError(f"{field_name}.{key} values must be positive finite numbers.")
            ratios.append(numeric)
        normalized[key] = tuple(ratios)
    return normalized


def _normalized_shared_legend_options_arg(value: Any, *, field_name: str) -> dict[str, Any]:
    if value in (None, {}, []):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object.")
    allowed = {"title", "order", "ncol", "position"}
    unsupported = sorted(set(value) - allowed)
    if unsupported:
        raise ValueError(f"{field_name} has unsupported key(s): {', '.join(unsupported)}.")
    normalized: dict[str, Any] = {}
    if value.get("title") is not None:
        normalized["title"] = str(value["title"])
    if value.get("order") is not None:
        order = value["order"]
        if not isinstance(order, (list, tuple)):
            raise ValueError(f"{field_name}.order must be an array of labels.")
        labels = tuple(str(label) for label in order if str(label).strip())
        if len(labels) != len(set(labels)):
            raise ValueError(f"{field_name}.order must not contain duplicate labels.")
        normalized["order"] = labels
    if value.get("ncol") is not None:
        if isinstance(value["ncol"], bool) or not isinstance(value["ncol"], int):
            raise ValueError(f"{field_name}.ncol must be an integer.")
        ncol = value["ncol"]
        if ncol < 1 or ncol > 8:
            raise ValueError(f"{field_name}.ncol must be between 1 and 8.")
        normalized["ncol"] = ncol
    position = str(value.get("position") or "top").strip().lower()
    if position not in {"top", "bottom", "right"}:
        raise ValueError(f"{field_name}.position must be top, bottom, or right.")
    normalized["position"] = position
    return normalized


def _normalized_multipanel_render_settings(arguments: dict[str, Any], *, panel_count: int) -> dict[str, Any]:
    rows = int(arguments.get("rows") or 1)
    cols = int(arguments.get("cols") or (panel_count if panel_count else 1))
    panel_height_mm = float(arguments.get("panel_height_mm") or 65.0)
    font_scale = float(arguments.get("font_scale") or 1.0)
    layout_options = _normalized_multipanel_layout_options_arg(
        arguments.get("layout_options"),
        rows=rows,
        cols=cols,
        field_name="layout_options",
    )
    raw_shared_legend = arguments.get("shared_legend", False)
    if not isinstance(raw_shared_legend, bool):
        raise ValueError("shared_legend must be a boolean.")
    shared_legend_options = _normalized_shared_legend_options_arg(
        arguments.get("shared_legend_options"),
        field_name="shared_legend_options",
    )
    return {
        "rows": rows,
        "cols": cols,
        "panel_height_mm": panel_height_mm,
        "font_scale": font_scale,
        "layout_options": layout_options,
        "shared_legend": raw_shared_legend,
        "shared_legend_options": shared_legend_options,
    }


def _normalized_legend_options_arg(value: Any, *, field_name: str) -> dict[str, Any]:
    if value in (None, {}, []):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object.")
    allowed = {"title", "order", "ncol"}
    unsupported = sorted(set(value) - allowed)
    if unsupported:
        raise ValueError(f"{field_name} has unsupported key(s): {', '.join(unsupported)}.")
    normalized: dict[str, Any] = {}
    if value.get("title") is not None:
        normalized["title"] = str(value["title"])
    if value.get("order") is not None:
        order = value["order"]
        if not isinstance(order, (list, tuple)):
            raise ValueError(f"{field_name}.order must be an array of labels.")
        labels = tuple(str(label) for label in order if str(label).strip())
        if len(labels) != len(set(labels)):
            raise ValueError(f"{field_name}.order must not contain duplicate labels.")
        normalized["order"] = labels
    if value.get("ncol") is not None:
        try:
            ncol = int(value["ncol"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name}.ncol must be an integer.") from exc
        if ncol < 1 or ncol > 8:
            raise ValueError(f"{field_name}.ncol must be between 1 and 8.")
        normalized["ncol"] = ncol
    return normalized


def _normalized_point_label_options_arg(value: Any, *, field_name: str) -> dict[str, Any]:
    if value in (None, {}, []):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object.")
    unsupported = sorted(set(value) - {"offset", "fanout", "max_labels", "priority_column", "skip_column"})
    if unsupported:
        raise ValueError(f"{field_name} has unsupported key(s): {', '.join(unsupported)}.")
    normalized: dict[str, Any] = {}
    if value.get("offset") is not None:
        offset = value["offset"]
        if not isinstance(offset, dict) or "dx" not in offset or "dy" not in offset:
            raise ValueError(f"{field_name}.offset must contain dx and dy.")
        try:
            dx = float(offset["dx"])
            dy = float(offset["dy"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name}.offset dx and dy must be numeric.") from exc
        if not math.isfinite(dx) or not math.isfinite(dy):
            raise ValueError(f"{field_name}.offset dx and dy must be finite.")
        normalized["offset"] = {"dx": dx, "dy": dy}
    if value.get("fanout") is not None:
        fanout = str(value["fanout"]).strip().lower().replace("-", "_")
        if fanout not in {"none", "compass"}:
            raise ValueError(f"{field_name}.fanout must be 'none' or 'compass'.")
        normalized["fanout"] = fanout
    if value.get("max_labels") is not None:
        try:
            max_labels = int(value["max_labels"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name}.max_labels must be an integer.") from exc
        if max_labels < 1:
            raise ValueError(f"{field_name}.max_labels must be at least 1.")
        normalized["max_labels"] = max_labels
    for key in ("priority_column", "skip_column"):
        if value.get(key) is None or value.get(key) == "":
            continue
        if not isinstance(value[key], str):
            raise ValueError(f"{field_name}.{key} must be a string.")
        column = value[key].strip()
        if not column:
            raise ValueError(f"{field_name}.{key} must be a non-empty string when provided.")
        normalized[key] = column
    return normalized


def _normalized_span_annotation_arg(
    annotation: dict[str, Any],
    index: int,
    *,
    field: str,
    bounds: tuple[str, str],
) -> dict[str, Any]:
    span = annotation[field]
    lower_key, upper_key = bounds
    if not isinstance(span, dict) or lower_key not in span or upper_key not in span:
        raise ValueError(f"annotations[{index}].{field} must contain {lower_key} and {upper_key}.")
    item: dict[str, Any] = {field: {lower_key: span[lower_key], upper_key: span[upper_key]}}
    claim_fields = _normalized_annotation_claim_fields(annotation, index)
    item.update(claim_fields)
    if annotation.get("text"):
        raw_text = str(annotation["text"])
        item["text"] = raw_text if claim_fields.get("annotation_kind") == "literal" else raw_text.strip()
    if "color" in annotation:
        item["color"] = str(annotation.get("color") or "black")
    if "alpha" in annotation:
        item["alpha"] = annotation["alpha"]
    return item


def _normalized_series_style_args(value: Any) -> dict[str, dict[str, str]]:
    if value in (None, {}, []):
        return {}
    if not isinstance(value, dict):
        raise ValueError("series_styles must be an object keyed by series label.")
    allowed_keys = {
        "marker",
        "fill",
        "facecolor",
        "edgecolor",
        "markerfacecolor",
        "markeredgecolor",
        "linestyle",
        "hatch",
        "color",
        "alpha",
        "size",
        "linewidth",
        "zorder",
        "label",
    }
    normalized: dict[str, dict[str, str]] = {}
    for series_name, style in value.items():
        key = str(series_name).strip()
        if not key:
            raise ValueError("series_styles keys must be non-empty series labels.")
        if not isinstance(style, dict):
            raise ValueError(f"series_styles[{key!r}] must be an object.")
        item: dict[str, str] = {}
        for style_key, raw_style_value in style.items():
            if style_key not in allowed_keys:
                raise ValueError(
                    f"series_styles[{key!r}] has unsupported key {style_key!r}; "
                    f"supported keys: {', '.join(sorted(allowed_keys))}."
                )
            if raw_style_value is None:
                continue
            text = str(raw_style_value).strip()
            if text:
                item[style_key] = text
        if item:
            normalized[key] = item
    return normalized


def _normalized_fit_options_arg(value: Any) -> dict[str, Any]:
    if value in (None, {}, []):
        return {}
    if not isinstance(value, dict):
        raise ValueError("fit_options must be an object.")
    allowed_keys = {"model", "label", "color", "linestyle", "linewidth", "zorder", "ci_alpha", "ci_label"}
    unsupported = sorted(set(value) - allowed_keys)
    if unsupported:
        raise ValueError(f"fit_options has unsupported key(s): {', '.join(unsupported)}.")
    normalized: dict[str, Any] = {"model": "linear"}
    if value.get("model") is not None:
        model = str(value["model"]).strip().lower()
        if model != "linear":
            raise ValueError("fit_options.model must be 'linear'.")
    for key in ("label", "color", "linestyle", "ci_label"):
        if value.get(key) is None:
            continue
        text = str(value[key]).strip()
        if text:
            normalized[key] = text
    for key in ("linewidth", "zorder", "ci_alpha"):
        if value.get(key) is None:
            continue
        try:
            numeric = float(value[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"fit_options.{key} must be numeric.") from exc
        if not math.isfinite(numeric):
            raise ValueError(f"fit_options.{key} must be finite.")
        if key == "linewidth" and numeric <= 0:
            raise ValueError("fit_options.linewidth must be positive.")
        if key == "ci_alpha" and not 0 <= numeric <= 1:
            raise ValueError("fit_options.ci_alpha must be between 0 and 1.")
        normalized[key] = numeric
    return normalized


def _normalized_guide_curve_args(value: Any) -> tuple[dict[str, Any], ...]:
    if value in (None, (), []):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("guide_curves must be an array of objects.")
    normalized: list[dict[str, Any]] = []
    for index, overlay in enumerate(value):
        if not isinstance(overlay, dict):
            raise ValueError(f"guide_curves[{index}] must be an object.")
        item: dict[str, Any] = {}
        if overlay.get("points") is not None:
            points = overlay["points"]
            if not isinstance(points, (list, tuple)):
                raise ValueError(f"guide_curves[{index}].points must be an array.")
            item["points"] = list(points)
        else:
            if not isinstance(overlay.get("x"), (list, tuple)) or not isinstance(overlay.get("y"), (list, tuple)):
                raise ValueError(f"guide_curves[{index}] requires points or x/y arrays.")
            item["x"] = list(overlay["x"])
            item["y"] = list(overlay["y"])
        for key in ("color", "linestyle", "linewidth", "label", "zorder"):
            if key in overlay:
                item[key] = overlay[key]
        item.setdefault("color", "black")
        normalized.append(item)
    return tuple(normalized)


def _normalized_fill_between_args(value: Any) -> tuple[dict[str, Any], ...]:
    if value in (None, (), []):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("fill_between must be an array of objects.")
    normalized: list[dict[str, Any]] = []
    for index, overlay in enumerate(value):
        if not isinstance(overlay, dict):
            raise ValueError(f"fill_between[{index}] must be an object.")
        allowed = {"points", "x_column", "y1_column", "y2_column", "color", "alpha", "label", "zorder", "band_kind"}
        if set(overlay) - allowed:
            raise ValueError(f"fill_between[{index}] contains unsupported fields.")
        item: dict[str, Any] = {}
        if overlay.get("points") is not None:
            points = overlay["points"]
            if not isinstance(points, (list, tuple)):
                raise ValueError(f"fill_between[{index}].points must be an array.")
            item["points"] = list(points)
        else:
            missing = [key for key in ("x_column", "y1_column", "y2_column") if not str(overlay.get(key) or "").strip()]
            if missing:
                raise ValueError(
                    f"fill_between[{index}] requires points or column field(s): {', '.join(missing)}."
                )
            item["x_column"] = str(overlay["x_column"]).strip()
            item["y1_column"] = str(overlay["y1_column"]).strip()
            item["y2_column"] = str(overlay["y2_column"]).strip()
        for key in ("color", "alpha", "label", "zorder"):
            if key in overlay:
                item[key] = overlay[key]
        item.setdefault("alpha", 0.2)
        if "band_kind" in overlay:
            band_kind = str(overlay["band_kind"]).strip().lower()
            if band_kind not in {"literal", "confidence_interval"}:
                raise ValueError(f"fill_between[{index}].band_kind is unsupported.")
            item["band_kind"] = band_kind
        normalized.append(item)
    return tuple(normalized)


def _fill_between_required_columns(
    fill_between: tuple[dict[str, Any], ...],
    *,
    existing: tuple[str, ...] = (),
) -> list[str]:
    seen = {str(column).strip() for column in existing if str(column or "").strip()}
    columns: list[str] = []
    for overlay in fill_between:
        for key in ("x_column", "y1_column", "y2_column"):
            column = str(overlay.get(key) or "").strip()
            if column and column not in seen:
                seen.add(column)
                columns.append(column)
    return columns


def _normalized_annotation_args(value: Any) -> tuple[dict[str, Any], ...]:
    if value in (None, (), []):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("annotations must be an array of objects.")
    normalized: list[dict[str, Any]] = []
    for index, annotation in enumerate(value):
        if not isinstance(annotation, dict):
            raise ValueError(f"annotations[{index}] must be an object.")
        allowed = {
            "x", "y", "text", "arrow_to", "arrowstyle", "connectionstyle", "xytext_offset",
            "placement_preset", "avoid_overlap", "color", "alpha", "region", "hspan", "vspan",
            *_ANNOTATION_CLAIM_KEYS,
        }
        if set(annotation) - allowed:
            raise ValueError(f"annotations[{index}] contains unsupported fields.")
        claim_fields = _normalized_annotation_claim_fields(annotation, index)
        if annotation.get("region") is not None:
            _reject_non_point_callout_args(annotation, index)
            region = annotation["region"]
            if not isinstance(region, dict) or any(key not in region for key in ("xmin", "xmax", "ymin", "ymax")):
                raise ValueError(f"annotations[{index}].region must contain xmin, xmax, ymin, ymax.")
            region_item: dict[str, Any] = {"region": {key: region[key] for key in ("xmin", "xmax", "ymin", "ymax")}}
            region_item.update(claim_fields)
            if annotation.get("text"):
                raw_text = str(annotation["text"])
                region_item["text"] = raw_text if claim_fields.get("annotation_kind") == "literal" else raw_text.strip()
            if "color" in annotation:
                region_item["color"] = str(annotation.get("color") or "black")
            if "alpha" in annotation:
                region_item["alpha"] = annotation["alpha"]
            normalized.append(region_item)
            continue
        if annotation.get("hspan") is not None:
            _reject_non_point_callout_args(annotation, index)
            normalized.append(
                _normalized_span_annotation_arg(annotation, index, field="hspan", bounds=("ymin", "ymax"))
            )
            continue
        if annotation.get("vspan") is not None:
            _reject_non_point_callout_args(annotation, index)
            normalized.append(
                _normalized_span_annotation_arg(annotation, index, field="vspan", bounds=("xmin", "xmax"))
            )
            continue
        missing = [key for key in ("x", "y") if key not in annotation]
        if missing:
            raise ValueError(f"annotations[{index}] missing required field(s): {', '.join(missing)}.")
        item = {
            "x": annotation["x"],
            "y": annotation["y"],
            "text": (
                str(annotation.get("text") or "")
                if claim_fields.get("annotation_kind") == "literal"
                else str(annotation.get("text") or "").strip()
            ),
            **claim_fields,
        }
        arrow_to = annotation.get("arrow_to")
        if not item["text"] and arrow_to is None:
            raise ValueError(f"annotations[{index}] text must be non-empty unless arrow_to is provided.")
        if "color" in annotation:
            item["color"] = str(annotation.get("color") or "black")
        if arrow_to is not None:
            if not isinstance(arrow_to, dict) or "x" not in arrow_to or "y" not in arrow_to:
                raise ValueError(f"annotations[{index}].arrow_to must contain x and y.")
            item["arrow_to"] = {"x": arrow_to["x"], "y": arrow_to["y"]}
        if "arrowstyle" in annotation:
            item["arrowstyle"] = str(annotation.get("arrowstyle") or "->").strip() or "->"
        if annotation.get("connectionstyle"):
            item["connectionstyle"] = str(annotation["connectionstyle"]).strip()
        if annotation.get("xytext_offset") is not None:
            offset = annotation["xytext_offset"]
            if not isinstance(offset, dict) or "dx" not in offset or "dy" not in offset:
                raise ValueError(f"annotations[{index}].xytext_offset must contain dx and dy.")
            item["xytext_offset"] = {"dx": offset["dx"], "dy": offset["dy"]}
        if annotation.get("placement_preset"):
            preset = str(annotation["placement_preset"]).strip().lower().replace("-", "_")
            allowed_presets = {
                "above",
                "below",
                "left",
                "right",
                "upper_left",
                "upper_right",
                "lower_left",
                "lower_right",
            }
            if preset not in allowed_presets:
                raise ValueError(f"annotations[{index}].placement_preset has unsupported value {preset!r}.")
            item["placement_preset"] = preset
        if "avoid_overlap" in annotation:
            if not isinstance(annotation["avoid_overlap"], bool):
                raise ValueError(f"annotations[{index}].avoid_overlap must be a boolean.")
            item["avoid_overlap"] = annotation["avoid_overlap"]
        normalized.append(item)
    return tuple(normalized)


def _reject_non_point_callout_args(annotation: dict[str, Any], index: int) -> None:
    unsupported = [
        key
        for key in ("xytext_offset", "placement_preset", "avoid_overlap")
        if key in annotation and annotation.get(key) is not None
    ]
    if unsupported:
        joined = ", ".join(unsupported)
        raise ValueError(f"annotations[{index}] {joined} only apply to point annotations.")
