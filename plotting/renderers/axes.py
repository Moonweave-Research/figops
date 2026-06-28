from __future__ import annotations

import math
from typing import Any

import matplotlib.ticker as mticker
import numpy as np


def normalized_axis_scale(value: str, *, field_name: str) -> str:
    scale = str(value or "linear").strip().lower()
    if scale not in {"linear", "log"}:
        raise ValueError(f"{field_name} must be 'linear' or 'log'")
    return scale


def validate_axis_scales(points: list[dict], spec: Any) -> None:
    x_scale = normalized_axis_scale(spec.x_scale, field_name="x_scale")
    y_scale = normalized_axis_scale(spec.y_scale, field_name="y_scale")
    if x_scale == "linear" and y_scale == "linear":
        return
    for axis_name, scale in (("x", x_scale), ("y", y_scale)):
        if scale != "log":
            continue
        bad_values = []
        for point in points:
            value = point[axis_name]
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                bad_values.append(value)
                continue
            if not math.isfinite(numeric) or numeric <= 0:
                bad_values.append(value)
        if bad_values:
            raise ValueError(f"{axis_name}_scale='log' requires finite numeric {axis_name} values > 0")


def validate_axis_limits(points: list[dict], spec: Any) -> None:
    limits = normalized_axis_limits(spec)
    for axis_name in ("x", "y"):
        if axis_name in limits and any(not isinstance(point[axis_name], (int, float)) for point in points):
            raise ValueError(f"axis_limits.{axis_name} requires numeric {axis_name} values")


def apply_axis_scales(ax: Any, spec: Any) -> None:
    x_scale = normalized_axis_scale(spec.x_scale, field_name="x_scale")
    y_scale = normalized_axis_scale(spec.y_scale, field_name="y_scale")
    if x_scale != "linear":
        ax.set_xscale(x_scale)
    if y_scale != "linear":
        ax.set_yscale(y_scale)


def visible_plot_axes(fig: Any, fallback_ax: Any = None) -> list:
    axes = [ax for ax in fig.axes if ax.get_visible() and getattr(ax, "_graph_hub_role", "") != "colorbar"]
    if not axes and fallback_ax is not None:
        axes = [fallback_ax]
    return axes


def apply_axis_scales_to_visible_axes(fig: Any, fallback_ax: Any, spec: Any) -> None:
    for axis in visible_plot_axes(fig, fallback_ax):
        apply_axis_scales(axis, spec)


def normalized_axis_limit_pair(raw_pair: object, *, field_name: str) -> tuple[float | None, float | None]:
    if not isinstance(raw_pair, dict):
        raise ValueError(f"{field_name} must be an object with min and/or max")
    if not any(key in raw_pair for key in ("min", "max")):
        raise ValueError(f"{field_name} must contain min and/or max")
    unsupported = sorted(set(raw_pair) - {"min", "max"})
    if unsupported:
        raise ValueError(f"{field_name} has unsupported key(s): {', '.join(unsupported)}")
    limits: list[float | None] = []
    for key in ("min", "max"):
        value = raw_pair.get(key)
        if value is None or value == "":
            limits.append(None)
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name}.{key} must be numeric") from exc
        if not math.isfinite(numeric):
            raise ValueError(f"{field_name}.{key} must be finite")
        limits.append(numeric)
    lower, upper = limits
    if lower is not None and upper is not None and lower >= upper:
        raise ValueError(f"{field_name}.min must be less than {field_name}.max")
    return lower, upper


def normalized_axis_limits(spec: Any) -> dict[str, tuple[float | None, float | None]]:
    raw_limits = spec.axis_limits
    if raw_limits in (None, {}, []):
        return {}
    if not isinstance(raw_limits, dict):
        raise ValueError("axis_limits must be an object keyed by x and/or y")
    unsupported = sorted(set(raw_limits) - {"x", "y"})
    if unsupported:
        raise ValueError(f"axis_limits has unsupported key(s): {', '.join(unsupported)}")
    normalized: dict[str, tuple[float | None, float | None]] = {}
    for axis_name in ("x", "y"):
        if axis_name not in raw_limits or raw_limits[axis_name] in (None, {}):
            continue
        lower, upper = normalized_axis_limit_pair(raw_limits[axis_name], field_name=f"axis_limits.{axis_name}")
        scale = normalized_axis_scale(getattr(spec, f"{axis_name}_scale"), field_name=f"{axis_name}_scale")
        if scale == "log" and any(value is not None and value <= 0 for value in (lower, upper)):
            raise ValueError(f"axis_limits.{axis_name} values must be > 0 when {axis_name}_scale='log'")
        normalized[axis_name] = (lower, upper)
    return normalized


def apply_axis_limits(ax: Any, spec: Any) -> None:
    limits = normalized_axis_limits(spec)
    if "x" in limits:
        ax.set_xlim(*limits["x"])
    if "y" in limits:
        ax.set_ylim(*limits["y"])


def apply_axis_limits_to_visible_axes(fig: Any, fallback_ax: Any, spec: Any) -> None:
    for axis in visible_plot_axes(fig, fallback_ax):
        apply_axis_limits(axis, spec)


def normalized_tick_style(spec: Any) -> dict[str, object]:
    raw_style = spec.tick_style
    if raw_style in (None, {}, []):
        return {}
    if not isinstance(raw_style, dict):
        raise ValueError("tick_style must be an object")
    allowed = {"rotation", "format", "max_label_chars"}
    unsupported = sorted(set(raw_style) - allowed)
    if unsupported:
        raise ValueError(f"tick_style has unsupported key(s): {', '.join(unsupported)}")
    normalized: dict[str, object] = {}
    if raw_style.get("rotation") is not None:
        try:
            rotation = float(raw_style["rotation"])
        except (TypeError, ValueError) as exc:
            raise ValueError("tick_style.rotation must be numeric") from exc
        if not math.isfinite(rotation) or not -360 <= rotation <= 360:
            raise ValueError("tick_style.rotation must be finite and between -360 and 360")
        normalized["rotation"] = rotation
    if raw_style.get("format") is not None:
        tick_format = str(raw_style["format"]).strip().lower()
        if tick_format not in {"default", "plain", "scientific", "compact"}:
            raise ValueError("tick_style.format must be default, plain, scientific, or compact")
        normalized["format"] = tick_format
    if raw_style.get("max_label_chars") is not None:
        try:
            max_label_chars = int(raw_style["max_label_chars"])
        except (TypeError, ValueError) as exc:
            raise ValueError("tick_style.max_label_chars must be an integer") from exc
        if max_label_chars < 4:
            raise ValueError("tick_style.max_label_chars must be at least 4")
        normalized["max_label_chars"] = max_label_chars
    return normalized


def axis_is_numeric(ax: Any, axis_name: str) -> bool:
    values = ax.get_lines()
    for line in values:
        data = line.get_xdata() if axis_name == "x" else line.get_ydata()
        if len(data):
            return all(isinstance(value, (int, float, np.number)) for value in data)
    return True


def apply_tick_style(ax: Any, spec: Any) -> None:
    style = normalized_tick_style(spec)
    if not style:
        return
    if "rotation" in style:
        rotation = float(style["rotation"])
        for label in ax.get_xticklabels():
            label.set_rotation(rotation)
            if rotation:
                label.set_ha("right")
    tick_format = style.get("format")
    if tick_format and tick_format != "default":
        for axis in (ax.xaxis, ax.yaxis):
            if tick_format == "plain":
                formatter = mticker.ScalarFormatter(useOffset=False)
                formatter.set_scientific(False)
                axis.set_major_formatter(formatter)
            elif tick_format == "scientific":
                formatter = mticker.ScalarFormatter(useMathText=True)
                formatter.set_scientific(True)
                formatter.set_powerlimits((0, 0))
                axis.set_major_formatter(formatter)
            elif tick_format == "compact":
                axis.set_major_formatter(mticker.EngFormatter())
    if "max_label_chars" in style:
        apply_tick_label_char_limit(ax, int(style["max_label_chars"]))


def apply_tick_label_char_limit(ax: Any, max_label_chars: int) -> None:
    base_formatter = ax.xaxis.get_major_formatter()
    original_labels: dict[int, str] = {}

    raw_label_map = getattr(ax, "_graph_hub_original_xtick_labels", {})

    def limited_formatter(value: float, position: int | None = None) -> str:
        formatted = str(base_formatter(value, position))
        original = str(raw_label_map.get(int(position), formatted)) if position is not None else formatted
        if position is not None:
            original_labels[int(position)] = original
        return truncate_tick_label(formatted, max_label_chars)

    formatter = mticker.FuncFormatter(limited_formatter)
    formatter._graph_hub_original_formatter = base_formatter
    formatter._graph_hub_original_tick_labels = original_labels
    formatter._graph_hub_max_label_chars = int(max_label_chars)
    ax.xaxis.set_major_formatter(formatter)


def truncate_tick_label(text: str, max_label_chars: int) -> str:
    if len(text) <= max_label_chars:
        return text
    return f"{text[: max_label_chars - 3]}..."


def apply_tick_style_to_visible_axes(fig: Any, fallback_ax: Any, spec: Any) -> None:
    for axis in visible_plot_axes(fig, fallback_ax):
        apply_tick_style(axis, spec)
