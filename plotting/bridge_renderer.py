"""
Reusable Graph Hub renderer for Athena bridge plots.
"""

from __future__ import annotations

import csv
import math
import os
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.font_manager import FontProperties

from hub_core.rendering import PLOT_TYPES, render_plot
from plotting.axis_break import _draw_break_marks
from plotting.renderers.bar import (
    BarRendererContext,
)
from plotting.renderers.bar import (
    aggregate_single_series_bar_points as _aggregate_single_series_bar_points,  # noqa: F401
)
from plotting.renderers.bar import (
    render_bar_plot as _render_bar_plot_impl,
)
from plotting.renderers.bar import (
    validate_bar_aggregate as _validate_bar_aggregate,  # noqa: F401
)
from plotting.renderers.broken_axis import BrokenAxisRendererContext
from plotting.renderers.broken_axis import annotate_broken_axis_points as _annotate_broken_axis_points_impl
from plotting.renderers.broken_axis import draw_broken_xy_series as _draw_broken_xy_series_impl
from plotting.renderers.broken_axis import draw_grouped_broken_xy as _draw_grouped_broken_xy_impl
from plotting.renderers.broken_axis import make_broken_y_axes as _make_broken_y_axes_impl
from plotting.renderers.common import first_seen_values as _first_seen_values  # noqa: F401
from plotting.renderers.common import format_order_values as _format_order_values  # noqa: F401
from plotting.renderers.common import group_points as _group_points  # noqa: F401
from plotting.renderers.common import normalize_order_value as _normalize_order_value  # noqa: F401
from plotting.renderers.common import optional_error_float as _optional_error_float  # noqa: F401
from plotting.renderers.common import resolve_explicit_order as _resolve_explicit_order  # noqa: F401
from plotting.renderers.common import yerr_values as _yerr_values  # noqa: F401
from plotting.renderers.distribution import render_box_plot as _render_box_plot  # noqa: F401
from plotting.renderers.distribution import render_violin_plot as _render_violin_plot  # noqa: F401
from plotting.renderers.facet import FacetRendererContext
from plotting.renderers.facet import expand_shared_facet_limits_for_markers as _expand_shared_facet_limits_impl
from plotting.renderers.facet import group_facet_points as _group_facet_points_impl
from plotting.renderers.facet import optional_positive_int as _optional_positive_int_impl
from plotting.renderers.facet import render_facet_plot as _render_facet_plot_impl
from plotting.renderers.facet import resolve_facet_grid as _resolve_facet_grid_impl
from plotting.renderers.heatmap import render_heatmap_plot as _render_heatmap_plot  # noqa: F401
from plotting.renderers.xy import XYRendererContext
from plotting.renderers.xy import line_marker_color_kwargs as _line_marker_color_kwargs  # noqa: F401
from plotting.renderers.xy import marker_color_kwargs as _marker_color_kwargs  # noqa: F401
from plotting.renderers.xy import render_xy_plot as _render_xy_plot_impl
from plotting.utils import (
    annotate_significance,
    apply_density_alpha,
    auto_panel_tag,
    compress_sample_label,
    get_standard_legend_props,
)
from themes.journal_theme import (
    DOUBLE_COLUMN,
    PUBLICATION_LAYOUT_SPECS_MM,
    SINGLE_COLUMN,
    apply_journal_theme,
    apply_publication_layout,
    get_legend_args,
    mm_to_inch,
    save_journal_fig,
    set_figure_size,
)
from themes.style_profiles import get_render_style_tokens, get_series_style

from .smart_layout import find_empty_quadrant

try:
    from hub_core.provenance import embed_provenance_fingerprint as _embed_fingerprint
    from hub_core.provenance import hash_csv_file as _hash_csv_file
except Exception:
    _embed_fingerprint = None  # type: ignore[assignment]
    _hash_csv_file = None  # type: ignore[assignment]
    warnings.warn(
        "hub_core.provenance not available; reproducibility fingerprinting disabled",
        stacklevel=1,
    )

_PANEL_LABELS = tuple("abcdefghijklmnopqrstuvwxyz")
_LEGEND_DATA_OVERLAP_WARN = 0.05
_SMART_LEGEND_INSIDE_CANDIDATES: tuple[str, ...] = (
    "upper right",
    "upper left",
    "lower left",
    "lower right",
    "center right",
    "center left",
    "lower center",
    "upper center",
)


def _deterministic_timestamp() -> str:
    """Return SOURCE_DATE_EPOCH if set, else current UTC time."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
    return datetime.now(tz=timezone.utc).isoformat()


# Journal column widths in mm; height derived at ratio 0.80.
_FORMAT_FIGSIZE_MM: dict[str, tuple[float, float]] = {
    "nature": (89, 71),
    "science": (89, 71),
    "default": (89, 71),
    "ppt": (152, 114),
}


def _figsize_for_format(target_format: str) -> tuple[float, float]:
    tokens, _meta = get_render_style_tokens(target_format, "baseline")
    if "figure_width_mm" in tokens:
        w_mm = float(tokens["figure_width_mm"])
        h_mm = float(tokens.get("figure_height_mm", w_mm * 0.8))
        return set_figure_size(w_mm, h_mm)
    w_mm, h_mm = _FORMAT_FIGSIZE_MM.get(target_format, (89, 71))
    return set_figure_size(w_mm, h_mm)


def _column_width_mm(target_format: str, column_width: str, profile_name: str = "baseline") -> float:
    width_key = str(column_width or "double").strip().lower()
    tokens, _meta = get_render_style_tokens(target_format, profile_name)
    column_widths = tokens.get("figure_column_widths_mm")
    if isinstance(column_widths, dict) and width_key in column_widths:
        return float(column_widths[width_key])
    return float(DOUBLE_COLUMN if width_key == "double" else SINGLE_COLUMN)


def _marker_tokens(spec: BridgeFigureSpec, *, small_panel: bool = False) -> tuple[float, float, float | None]:
    tokens, _meta = get_render_style_tokens(spec.target_format, spec.profile_name)
    marker_size = float(tokens.get("main_marker_size", plt.rcParams["lines.markersize"]))
    if small_panel:
        marker_size = float(tokens.get("facet_marker_size", marker_size))
    marker_edge_width = float(tokens.get("main_marker_edge_width", plt.rcParams["lines.markeredgewidth"]))
    margin_key = "facet_axis_marker_margin_fraction" if small_panel else "axis_marker_margin_fraction"
    marker_margin = tokens.get(margin_key)
    if marker_margin is None and small_panel:
        marker_margin = tokens.get("axis_marker_margin_fraction")
    return marker_size, marker_edge_width, float(marker_margin) if marker_margin is not None else None


def _scatter_marker_area(marker_size_pt: float) -> float:
    return math.pi * (marker_size_pt / 2.0) ** 2


def _apply_marker_axis_margin(ax, spec: BridgeFigureSpec, *, small_panel: bool = False) -> None:
    _marker_size, _marker_edge_width, margin = _marker_tokens(spec, small_panel=small_panel)
    if margin is None:
        return
    current_x, current_y = ax.margins()
    ax.margins(x=max(float(current_x), margin), y=max(float(current_y), margin))


def draw_zenith_plot(ax, x, y, label=None, kind="scatter", palette="Nature Energy", series_index=0, **kwargs):
    """
    최상의 품질을 보장하는 시각화 통합 래퍼입니다.
    - 자동 색상 지정 (CVD 세이프 팔레트)
    - 데이터 밀도 기반 투명도 조절
    - 자동 마커/선종류 순환 (multi-channel encoding)
    - 자동 라벨/범례 위치 최적화
    """
    from themes.palettes import get_palette

    colors = get_palette(palette)
    sty = get_series_style(series_index)

    # 데이터 밀도 기반 스타일링
    alpha, size = apply_density_alpha(len(x))

    # 기본 스타일 설정
    color = colors[series_index % len(colors)] if colors else "blue"
    plot_kwargs = {"alpha": alpha, "label": label, "color": color}
    plot_kwargs.update(kwargs)

    if kind == "scatter":
        plot_kwargs.setdefault("s", size * 5)
        plot_kwargs.setdefault("marker", sty["marker"])
        ax.scatter(x, y, **plot_kwargs)
    elif kind == "line":
        plot_kwargs.setdefault("marker", sty["marker"])
        plot_kwargs.setdefault("linestyle", sty["linestyle"])
        ax.plot(x, y, **plot_kwargs)

    # 지능형 범례 배치 (축 범위 기준으로 사분면 계산)
    if label:
        quad = find_empty_quadrant(x, y, x_lim=ax.get_xlim(), y_lim=ax.get_ylim())
        loc_map = {0: "upper right", 1: "upper left", 2: "lower left", 3: "lower right"}
        ax.legend(loc=loc_map[quad], frameon=False, fontsize="small")

    return ax


@dataclass(frozen=True)
class BridgeFigureSpec:
    csv_path: str
    output_path: str
    plot_type: str
    x_column: str
    y_column: str
    title: str
    z_column: str = ""
    x_axis_label: str = ""
    y_axis_label: str = ""
    label_column: str = ""
    series_column: str = ""
    x_scale: str = "linear"
    y_scale: str = "linear"
    annotations: tuple[dict, ...] = ()
    yerr_column: str = ""
    yerr_cap_width: float = 3.0
    yerr_minus_column: str = ""
    compress_labels: bool = True
    legend_layout: str = "auto"
    legend_options: dict | None = None
    axis_limits: dict | None = None
    tick_style: dict | None = None
    point_label_options: dict | None = None
    target_format: str = "nature"
    font_scale: float = 1.0
    profile_name: str = "baseline"
    physics_type: str = ""
    overlay_baselines: tuple[dict, ...] = ()
    y_break_range: tuple[float, float] | None = None
    facet_column: str = ""
    facet_scales: str = "fixed"
    facet_ncols: int | None = None
    facet_nrows: int | None = None
    category_order: tuple[float | str, ...] = ()
    facet_order: tuple[str, ...] = ()
    aggregate: str = ""
    annotate_values: bool = False
    fit_line: bool = False
    ci_band: bool = False
    fit_options: dict | None = None
    significance_markers: tuple[dict, ...] = ()
    series_styles: dict[str, dict] | None = None
    guide_curves: tuple[dict, ...] = ()
    fill_between: tuple[dict, ...] = ()


def render_bridge_figure(spec: BridgeFigureSpec) -> str:
    _saved_rc = plt.rcParams.copy()
    try:
        apply_journal_theme(
            target_format=spec.target_format,
            font_scale=spec.font_scale,
            profile_name=spec.profile_name,
        )

        csv_path = Path(spec.csv_path)
        output_path = Path(spec.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        points = _load_points(csv_path, spec)
        _validate_bar_aggregate(spec)
        _validate_manual_overlays(spec)
        _validate_statistical_overlays(points, spec)
        _validate_axis_scales(points, spec)
        _validate_axis_limits(points, spec)
        _normalized_tick_style(spec)
        _normalized_point_label_options(spec)
        _normalized_legend_options(spec)
        _normalized_annotations(spec.annotations)
        fig, ax = plt.subplots(figsize=_figsize_for_format(spec.target_format))
        try:
            if spec.y_break_range is not None:
                ax.set_visible(False)
                _render_broken_axis_plot(fig, points, spec)
                _apply_axis_scales_to_visible_axes(fig, ax, spec)
                _apply_axis_limits_to_visible_axes(fig, ax, spec)
                _apply_tick_style_to_visible_axes(fig, ax, spec)
                _draw_annotations_on_visible_axes(fig, ax, spec)
            else:
                _render_plot(ax, points, spec)
                _draw_manual_overlays(ax, csv_path, spec)
                _draw_statistical_overlays(ax, points, spec)
                _draw_overlay_baselines(ax, spec.overlay_baselines)
                _apply_axes_metadata(ax, spec)
                ax.set_title(spec.title)
                _apply_axis_scales_to_visible_axes(fig, ax, spec)
                _apply_axis_limits_to_visible_axes(fig, ax, spec)
                _apply_tick_style_to_visible_axes(fig, ax, spec)
                _draw_annotations_on_visible_axes(fig, ax, spec)
                _apply_layout(fig, ax, spec)
                _separate_top_legend_title(ax, spec)
            save_journal_fig(fig, output_path)
        finally:
            plt.close(fig)
    finally:
        plt.rcParams.update(_saved_rc)
    if _embed_fingerprint is not None:
        csv_hash = _hash_csv_file(spec.csv_path) if _hash_csv_file is not None else ""
        _embed_fingerprint(
            str(output_path),
            {
                "generator": "Graph-Hub/bridge_renderer.py",
                "target_format": spec.target_format,
                "ts": _deterministic_timestamp(),
                "csv_hash": csv_hash,
                "spec": {
                    "plot_type": spec.plot_type,
                    "x_column": spec.x_column,
                    "y_column": spec.y_column,
                    "target_format": spec.target_format,
                    "font_scale": spec.font_scale,
                    "profile_name": spec.profile_name,
                },
            },
        )
    return str(output_path)


@dataclass(frozen=True)
class PanelImageSpec:
    """Existing rendered figure file to embed as a panel."""

    image_path: str
    title: str = ""


@dataclass(frozen=True)
class MultiPanelSpec:
    """Specification for a multi-panel composite figure.

    Each element of ``panels`` is either a ``BridgeFigureSpec`` (rendered
    fresh from CSV) or a ``PanelImageSpec`` (existing image file).
    Grid is filled left-to-right, top-to-bottom; excess cells are hidden.

    Parameters
    ----------
    panels:
        Ordered tuple of panel specs.
    output_path:
        Destination file (PNG / TIFF / PDF).
    rows, cols:
        Grid dimensions.
    column_width:
        Target-format column key. Nature/default use ``"single"`` (89 mm) or
        ``"double"`` (183 mm); formats with explicit style tokens may also
        define values such as ``"full"`` or ``"triple"``.
    panel_height_mm:
        Height of each row in mm.
    panel_labels:
        If True, add bold **(a)**, **(b)**, … tags to each panel.
    compose_mode:
        ``"draft"`` keeps subplot auto-fitting, while ``"manuscript"``
        preserves a fixed plot box inside each panel slot.
    gutter_h_mm, gutter_v_mm:
        Absolute gutters used by manuscript compose mode.
    wspace, hspace:
        Fractional subplot spacing used by draft compose mode.
    width_ratios, height_ratios:
        Optional relative column/row weights. Draft mode forwards them to
        matplotlib GridSpec; manuscript mode uses them to divide the fixed
        journal-width canvas before preserving each panel box.
    shared_legend:
        If True, collect panel legends into one figure-level legend and remove
        duplicate per-panel legends.
    """

    panels: tuple[BridgeFigureSpec | PanelImageSpec, ...]
    output_path: str
    rows: int
    cols: int
    target_format: str = "nature"
    column_width: str = "double"
    panel_height_mm: float = 65.0
    panel_labels: bool = True
    font_scale: float = 1.0
    profile_name: str = "baseline"
    compose_mode: str = "draft"
    gutter_h_mm: float = 5.0
    gutter_v_mm: float = 5.0
    wspace: float = 0.35
    hspace: float = 0.45
    width_ratios: tuple[float, ...] = ()
    height_ratios: tuple[float, ...] = ()
    shared_legend: bool = False
    shared_legend_options: dict | None = None


def render_multipanel_figure(spec: MultiPanelSpec) -> str:
    """Compose multiple panels into a single publication figure."""
    _saved_rc = plt.rcParams.copy()
    try:
        compose_mode = _validated_compose_mode(spec)
        apply_journal_theme(
            target_format=spec.target_format,
            font_scale=spec.font_scale,
            profile_name=spec.profile_name,
        )
        if compose_mode == "manuscript":
            fig = _render_multipanel_manuscript(spec)
        else:
            fig = _render_multipanel_draft(spec)
        FigureCanvasAgg(fig)
        output_path = Path(spec.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            save_journal_fig(fig, output_path)
        finally:
            plt.close(fig)
            FigureCanvasAgg(fig)
    finally:
        plt.rcParams.update(_saved_rc)

    if _embed_fingerprint is not None:
        _embed_fingerprint(
            str(output_path),
            {
                "generator": "Graph-Hub/bridge_renderer.py::render_multipanel_figure",
                "rows": spec.rows,
                "cols": spec.cols,
                "n_panels": len(spec.panels),
                "ts": _deterministic_timestamp(),
            },
        )
    return str(output_path)


def _render_multipanel_draft(spec: MultiPanelSpec):
    col_mm = _column_width_mm(spec.target_format, spec.column_width, spec.profile_name)
    fig_w_in = mm_to_inch(col_mm)
    fig_h_in = mm_to_inch(spec.panel_height_mm * spec.rows)

    gridspec_kw: dict[str, tuple[float, ...]] = {}
    if spec.width_ratios:
        gridspec_kw["width_ratios"] = spec.width_ratios
    if spec.height_ratios:
        gridspec_kw["height_ratios"] = spec.height_ratios
    fig, axes = plt.subplots(
        spec.rows,
        spec.cols,
        figsize=(fig_w_in, fig_h_in),
        gridspec_kw=gridspec_kw or None,
    )
    axes_flat = np.asarray(axes).ravel().tolist()
    fig.subplots_adjust(wspace=spec.wspace, hspace=spec.hspace)

    for idx, ax in enumerate(axes_flat):
        if idx >= len(spec.panels):
            ax.set_visible(False)
            continue
        panel = spec.panels[idx]
        if isinstance(panel, PanelImageSpec):
            _render_image_panel(ax, panel)
        else:
            _render_csv_panel(fig, ax, panel)
        if spec.panel_labels and idx < len(_PANEL_LABELS):
            auto_panel_tag(ax, label=_PANEL_LABELS[idx])

    _apply_shared_legend(fig, spec)
    if hasattr(fig, "_graph_hub_layout_lock"):
        delattr(fig, "_graph_hub_layout_lock")
    return fig


def _validated_compose_mode(spec: MultiPanelSpec) -> str:
    compose_mode = str(spec.compose_mode or "draft").strip().lower()
    if compose_mode not in {"draft", "manuscript"}:
        raise ValueError(f"unsupported compose_mode {spec.compose_mode!r}; expected 'draft' or 'manuscript'")
    if spec.rows <= 0 or spec.cols <= 0:
        raise ValueError("rows and cols must be positive integers")
    if spec.panel_height_mm <= 0 or not math.isfinite(float(spec.panel_height_mm)):
        raise ValueError("panel_height_mm must be positive")
    if not math.isfinite(float(spec.wspace)) or not math.isfinite(float(spec.hspace)):
        raise ValueError("wspace and hspace must be finite")
    if spec.wspace < 0 or spec.hspace < 0:
        raise ValueError("wspace and hspace must be non-negative")
    if not math.isfinite(float(spec.gutter_h_mm)) or not math.isfinite(float(spec.gutter_v_mm)):
        raise ValueError("gutter_h_mm and gutter_v_mm must be finite")
    if spec.gutter_h_mm < 0 or spec.gutter_v_mm < 0:
        raise ValueError("gutter_h_mm and gutter_v_mm must be non-negative")
    _validated_layout_ratios(spec.width_ratios, expected_len=spec.cols, field_name="width_ratios")
    _validated_layout_ratios(spec.height_ratios, expected_len=spec.rows, field_name="height_ratios")
    shared_legend_options = _normalized_shared_legend_options(spec)
    if shared_legend_options and not spec.shared_legend:
        raise ValueError("shared_legend_options requires shared_legend=True")
    if compose_mode == "manuscript" and str(spec.target_format or "").lower() == "ppt":
        raise ValueError("manuscript compose is not supported for target_format='ppt'")
    return compose_mode


def _render_multipanel_manuscript(spec: MultiPanelSpec):
    panel_area_w_mm = _column_width_mm(spec.target_format, spec.column_width, spec.profile_name)
    panel_area_h_mm = (spec.panel_height_mm * spec.rows) + (spec.gutter_v_mm * max(spec.rows - 1, 0))
    shared_legend_options = _normalized_shared_legend_options(spec) if spec.shared_legend else {}
    shared_legend_position = str(shared_legend_options.get("position") or "top") if spec.shared_legend else ""
    legend_extra_h_mm = 12.0 if shared_legend_position in {"top", "bottom"} else 0.0
    legend_extra_w_mm = 30.0 if shared_legend_position == "right" else 0.0
    panel_area_bottom_mm = legend_extra_h_mm if shared_legend_position == "bottom" else 0.0
    fig_w_mm = panel_area_w_mm + legend_extra_w_mm
    fig_h_mm = panel_area_h_mm + legend_extra_h_mm
    fig = plt.figure(figsize=(mm_to_inch(fig_w_mm), mm_to_inch(fig_h_mm)))
    setattr(
        fig,
        "_graph_hub_layout_lock",
        {
            "compose_mode": "manuscript",
            "figure_width_mm": float(fig_w_mm),
            "figure_height_mm": float(fig_h_mm),
            "panel_area_width_mm": float(panel_area_w_mm),
            "panel_area_height_mm": float(panel_area_h_mm),
            "panel_area_bottom_mm": float(panel_area_bottom_mm),
            "panel_area_bottom": float(panel_area_bottom_mm / fig_h_mm),
            "panel_area_top": float((panel_area_bottom_mm + panel_area_h_mm) / fig_h_mm),
            "panel_area_right": float(panel_area_w_mm / fig_w_mm),
        },
    )

    col_widths_mm = _distributed_lengths_mm(
        panel_area_w_mm - (spec.gutter_h_mm * max(spec.cols - 1, 0)),
        spec.cols,
        spec.width_ratios,
    )
    row_heights_mm = _distributed_lengths_mm(
        spec.panel_height_mm * spec.rows,
        spec.rows,
        spec.height_ratios,
    )

    for idx, panel in enumerate(spec.panels):
        if idx >= spec.rows * spec.cols:
            break
        row_idx = idx // spec.cols
        col_idx = idx % spec.cols
        cell_w_mm = col_widths_mm[col_idx]
        cell_h_mm = row_heights_mm[row_idx]
        cell_left_mm = sum(col_widths_mm[:col_idx]) + (spec.gutter_h_mm * col_idx)
        cell_bottom_mm = (
            panel_area_bottom_mm
            + panel_area_h_mm
            - sum(row_heights_mm[: row_idx + 1])
            - (spec.gutter_v_mm * row_idx)
        )
        axis_rect = _manuscript_axis_rect(
            panel,
            fig_w_mm=fig_w_mm,
            fig_h_mm=fig_h_mm,
            cell_left_mm=cell_left_mm,
            cell_bottom_mm=cell_bottom_mm,
            cell_w_mm=cell_w_mm,
            cell_h_mm=cell_h_mm,
        )
        ax = fig.add_axes(axis_rect)
        if isinstance(panel, PanelImageSpec):
            _render_image_panel(ax, panel)
        else:
            _render_csv_panel(fig, ax, panel)
        if spec.panel_labels and idx < len(_PANEL_LABELS):
            auto_panel_tag(ax, label=_PANEL_LABELS[idx])

    _apply_shared_legend(fig, spec)
    return fig


def _validated_layout_ratios(values: tuple[float, ...], *, expected_len: int, field_name: str) -> None:
    if not values:
        return
    if len(values) != expected_len:
        raise ValueError(f"{field_name} must contain exactly {expected_len} value(s)")
    for value in values:
        if not math.isfinite(float(value)) or value <= 0:
            raise ValueError(f"{field_name} values must be positive finite numbers")


def _normalized_shared_legend_options(spec: MultiPanelSpec) -> dict[str, object]:
    raw_options = spec.shared_legend_options
    if raw_options in (None, {}, ()):
        return {}
    if not isinstance(raw_options, dict):
        raise ValueError("shared_legend_options must be an object")
    allowed = {"title", "order", "ncol", "position"}
    unsupported = sorted(set(raw_options) - allowed)
    if unsupported:
        raise ValueError(f"shared_legend_options has unsupported key(s): {', '.join(unsupported)}")
    normalized: dict[str, object] = {}
    if raw_options.get("title") is not None:
        normalized["title"] = str(raw_options["title"])
    if raw_options.get("order") is not None:
        order = raw_options["order"]
        if not isinstance(order, (list, tuple)):
            raise ValueError("shared_legend_options.order must be an array of labels")
        labels = tuple(str(label) for label in order if str(label).strip())
        if len(labels) != len(set(labels)):
            raise ValueError("shared_legend_options.order must not contain duplicate labels")
        normalized["order"] = labels
    if raw_options.get("ncol") is not None:
        if isinstance(raw_options["ncol"], bool) or not isinstance(raw_options["ncol"], int):
            raise ValueError("shared_legend_options.ncol must be an integer")
        ncol = raw_options["ncol"]
        if ncol < 1 or ncol > 8:
            raise ValueError("shared_legend_options.ncol must be between 1 and 8")
        normalized["ncol"] = ncol
    position = str(raw_options.get("position") or "top").strip().lower()
    if position not in {"top", "bottom", "right"}:
        raise ValueError("shared_legend_options.position must be top, bottom, or right")
    normalized["position"] = position
    return normalized


def _apply_shared_legend(fig, spec: MultiPanelSpec) -> None:
    if not spec.shared_legend:
        return
    options = _normalized_shared_legend_options(spec)
    position = str(options.get("position") or "top")
    raw_entries: dict[str, tuple[object, str]] = {}
    label_entries: dict[str, tuple[object, str]] = {}
    for ax in fig.axes:
        if not ax.get_visible():
            continue
        handles, labels = ax.get_legend_handles_labels()
        label_to_handle = {label: handle for handle, label in zip(handles, labels) if label and label != "_nolegend_"}
        for raw, label in getattr(ax, "_graph_hub_legend_entries", ()):
            if label in label_to_handle and raw not in raw_entries:
                raw_entries[str(raw)] = (label_to_handle[label], str(label))
        for label, handle in label_to_handle.items():
            label_entries.setdefault(str(label), (handle, str(label)))
        legend = ax.get_legend()
        if legend is not None:
            legend.remove()

    entries = raw_entries or label_entries
    if not entries:
        return
    ordered_keys = tuple(options.get("order") or ())
    missing = [key for key in ordered_keys if key not in entries]
    if missing:
        raise ValueError(f"shared_legend_options.order contains unknown legend key(s): {', '.join(missing)}")
    ordered = [entries[key] for key in ordered_keys]
    seen = set(ordered_keys)
    ordered.extend(entry for key, entry in entries.items() if key not in seen)
    handles, labels = zip(*ordered, strict=True)
    kwargs: dict[str, object] = {
        "handles": list(handles),
        "labels": list(labels),
        "frameon": False,
        "fontsize": plt.rcParams.get("legend.fontsize", 7.0),
        "ncol": int(options.get("ncol") or min(max(len(labels), 1), 4)),
    }
    if options.get("title") is not None:
        kwargs["title"] = options["title"]
    layout_lock = getattr(fig, "_graph_hub_layout_lock", {})
    is_manuscript = isinstance(layout_lock, dict) and layout_lock.get("compose_mode") == "manuscript"
    if position == "bottom":
        bottom_anchor = max(float(layout_lock.get("panel_area_bottom", 0.04)) - 0.02, 0.02) if is_manuscript else 0.02
        kwargs.update({"loc": "upper center", "bbox_to_anchor": (0.5, bottom_anchor)})
        if not is_manuscript:
            fig.subplots_adjust(bottom=max(float(fig.subplotpars.bottom), 0.18))
    elif position == "right":
        kwargs["ncol"] = int(options["ncol"]) if "ncol" in options else 1
        right_anchor = float(layout_lock.get("panel_area_right", 0.84)) + 0.02 if is_manuscript else 0.99
        kwargs.update({"loc": "center left", "bbox_to_anchor": (right_anchor, 0.5)})
        if not is_manuscript:
            fig.subplots_adjust(right=min(float(fig.subplotpars.right), 0.82))
    else:
        top_anchor = min(float(layout_lock.get("panel_area_top", 0.96)) + 0.02, 0.98) if is_manuscript else 0.98
        kwargs.update({"loc": "lower center", "bbox_to_anchor": (0.5, top_anchor)})
        if not is_manuscript:
            fig.subplots_adjust(top=min(float(fig.subplotpars.top), 0.86))
    legend = fig.legend(**kwargs)
    setattr(legend, "_graph_hub_legend_placement", f"shared_{position}")


def _distributed_lengths_mm(total_mm: float, count: int, ratios: tuple[float, ...]) -> tuple[float, ...]:
    effective_ratios = ratios or tuple(1.0 for _ in range(count))
    ratio_sum = sum(effective_ratios)
    return tuple(total_mm * (ratio / ratio_sum) for ratio in effective_ratios)


def _manuscript_axis_rect(
    panel: BridgeFigureSpec | PanelImageSpec,
    *,
    fig_w_mm: float,
    fig_h_mm: float,
    cell_left_mm: float,
    cell_bottom_mm: float,
    cell_w_mm: float,
    cell_h_mm: float,
) -> list[float]:
    box_width_mm, box_height_mm, margins_mm = _panel_geometry_mm(panel)
    if box_width_mm > cell_w_mm or box_height_mm > cell_h_mm:
        raise ValueError(
            "manuscript compose requires panel box to fit within its slot: "
            f"box=({box_width_mm:.1f}mm,{box_height_mm:.1f}mm), "
            f"slot=({cell_w_mm:.1f}mm,{cell_h_mm:.1f}mm)"
        )

    extra_w_mm = cell_w_mm - box_width_mm
    extra_h_mm = cell_h_mm - box_height_mm
    left_extra_mm, _ = _split_bias(extra_w_mm, margins_mm["left"], margins_mm["right"])
    bottom_extra_mm, _ = _split_bias(extra_h_mm, margins_mm["bottom"], margins_mm["top"])

    ax_left_mm = cell_left_mm + left_extra_mm
    ax_bottom_mm = cell_bottom_mm + bottom_extra_mm
    ax_width = box_width_mm / fig_w_mm
    ax_height = box_height_mm / fig_h_mm
    ax_left = ax_left_mm / fig_w_mm
    ax_bottom = ax_bottom_mm / fig_h_mm

    return [ax_left, ax_bottom, ax_width, ax_height]


def _panel_geometry_mm(panel: BridgeFigureSpec | PanelImageSpec) -> tuple[float, float, dict[str, float]]:
    if isinstance(panel, PanelImageSpec):
        layout_key = "standard"
    else:
        if str(panel.target_format or "").lower() == "ppt":
            raise ValueError("manuscript compose does not support PPT panel geometry")
        layout_key = _resolved_legend_layout(panel)
        if layout_key not in PUBLICATION_LAYOUT_SPECS_MM:
            raise ValueError(
                "manuscript compose requires fixed-layout panels; "
                f"got legend_layout={layout_key!r}. Use standard, top_outside, or right_outside."
            )

    spec = PUBLICATION_LAYOUT_SPECS_MM[layout_key]
    margins = {key: float(value) for key, value in spec["margins_mm"].items()}
    return float(spec["box_width_mm"]), float(spec["box_height_mm"]), margins


def _split_bias(total_mm: float, primary_mm: float, secondary_mm: float) -> tuple[float, float]:
    if total_mm <= 0:
        return 0.0, 0.0
    weight_sum = float(primary_mm + secondary_mm)
    if weight_sum <= 0:
        half = total_mm / 2.0
        return half, half
    primary = total_mm * (float(primary_mm) / weight_sum)
    return primary, total_mm - primary


def _render_csv_panel(fig, ax, panel: BridgeFigureSpec) -> None:
    """Render a single CSV-based panel into *ax* (multipanel helper)."""
    points = _load_points(Path(panel.csv_path), panel)
    _validate_axis_scales(points, panel)
    _validate_axis_limits(points, panel)
    _normalized_tick_style(panel)
    _normalized_legend_options(panel)
    _validate_manual_overlays(panel)
    _normalized_annotations(panel.annotations)
    _render_plot(ax, points, panel)
    _draw_manual_overlays(ax, Path(panel.csv_path), panel)
    _draw_overlay_baselines(ax, panel.overlay_baselines)
    _apply_axes_metadata(ax, panel)
    if panel.title:
        ax.set_title(panel.title)
    _apply_axis_scales(ax, panel)
    _apply_axis_limits(ax, panel)
    _apply_tick_style(ax, panel)
    _draw_annotations(ax, panel)
    _apply_layout(fig, ax, panel, allow_figure_layout=False)


def _render_image_panel(ax, panel: PanelImageSpec) -> None:
    """Load an existing image file and display it inside *ax*."""
    try:
        import numpy as np
        from PIL import Image

        with Image.open(panel.image_path) as img:
            img_arr = np.asarray(img)
    except ImportError:
        img_arr = plt.imread(panel.image_path)
    ax.imshow(img_arr)
    ax.set_axis_off()
    if panel.title:
        ax.set_title(panel.title)


def _load_points(csv_path: Path, spec: BridgeFigureSpec) -> list[dict]:
    points: list[dict] = []
    skipped = 0
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        required = [spec.x_column, spec.y_column]
        for col_attr in ("label_column", "series_column", "yerr_column", "yerr_minus_column", "facet_column"):
            col = getattr(spec, col_attr)
            if col:
                required.append(col)
        point_label_options = _normalized_point_label_options(spec)
        for option_key in ("priority_column", "skip_column"):
            col = point_label_options.get(option_key)
            if col:
                required.append(str(col))
        for region in spec.fill_between:
            for key in ("x_column", "y1_column", "y2_column"):
                col = region.get(key)
                if col:
                    required.append(str(col))
        if spec.plot_type == "heatmap" and spec.z_column:
            required.append(spec.z_column)
        missing = [c for c in required if c not in headers]
        if missing:
            raise ValueError(
                f"CSV {csv_path.name} is missing column(s): {', '.join(missing)}. Available: {', '.join(headers)}"
            )
        for row_num, row in enumerate(reader, start=2):
            try:
                y_val = float(row[spec.y_column])
                yerr_val = float(row[spec.yerr_column]) if spec.yerr_column else None
                yerr_minus_val = float(row[spec.yerr_minus_column]) if spec.yerr_minus_column else None
                z_val = float(row[spec.z_column]) if spec.z_column else None
            except (ValueError, TypeError):
                skipped += 1
                continue
            if not math.isfinite(y_val) or (yerr_val is not None and not math.isfinite(yerr_val)):
                skipped += 1
                continue
            if yerr_minus_val is not None and not math.isfinite(yerr_minus_val):
                skipped += 1
                continue
            if z_val is not None and not math.isfinite(z_val):
                skipped += 1
                continue
            points.append(
                {
                    "x": _parse_x_value(row[spec.x_column]),
                    "y": y_val,
                    "z": z_val,
                    "label": row[spec.label_column] if spec.label_column else "",
                    "series": row[spec.series_column] if spec.series_column else "",
                    "yerr": yerr_val,
                    "yerr_minus": yerr_minus_val,
                    "facet": row[spec.facet_column] if spec.facet_column else "",
                    "raw": dict(row),
                }
            )
    if skipped:
        warnings.warn(
            f"bridge_renderer: skipped {skipped} row(s) with NaN/inf in {csv_path.name}",
            stacklevel=2,
        )
    return points


def _parse_x_value(value: object) -> float | str:
    text = str(value).strip()
    if not text:
        return ""
    try:
        return float(text)
    except ValueError:
        return text


def _annotate_points(
    ax,
    xs: list[float],
    ys: list[float],
    labels: list[str],
    *,
    compress_labels: bool,
    point_label_options: dict | None = None,
    points: list[dict] | None = None,
) -> None:
    options = _normalized_point_label_options_dict(point_label_options)
    candidates, skipped = _point_label_candidates(xs, ys, labels, options=options, points=points)
    for display_index, item in enumerate(candidates):
        _draw_point_label(ax, item, options=options, display_index=display_index, compress_labels=compress_labels)
    if skipped:
        _record_point_label_skips(ax, skipped=skipped, total=len(labels), shown=len(candidates))


def _point_label_candidates(
    xs: list[float],
    ys: list[float],
    labels: list[str],
    *,
    options: dict[str, object],
    points: list[dict] | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    candidates: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    priority_column = str(options.get("priority_column") or "")
    skip_column = str(options.get("skip_column") or "")
    max_labels = options.get("max_labels")
    for index, (x, y, label) in enumerate(zip(xs, ys, labels)):
        if label:
            raw_row = {}
            if points is not None and index < len(points) and isinstance(points[index].get("raw"), dict):
                raw_row = points[index]["raw"]
            if skip_column and _truthy_label_skip(raw_row.get(skip_column)):
                skipped.append({"index": index, "label": str(label), "reason": "skip_column"})
                continue
            priority = 0.0
            if priority_column:
                raw_priority = raw_row.get(priority_column, 0)
                try:
                    priority = float(raw_priority)
                except (TypeError, ValueError) as exc:
                    message = f"point_label_options.priority_column {priority_column!r} must be numeric"
                    raise ValueError(message) from exc
                if not math.isfinite(priority):
                    raise ValueError(f"point_label_options.priority_column {priority_column!r} must be finite")
            candidates.append({"index": index, "x": x, "y": y, "label": label, "priority": priority})
    if max_labels is not None:
        ranked = sorted(candidates, key=lambda item: (-float(item["priority"]), int(item["index"])))
        keep_indices = {int(item["index"]) for item in ranked[: int(max_labels)]}
        skipped.extend(
            {"index": int(item["index"]), "label": str(item["label"]), "reason": "max_labels"}
            for item in candidates
            if int(item["index"]) not in keep_indices
        )
        candidates = [item for item in candidates if int(item["index"]) in keep_indices]
    return candidates, skipped


def _draw_point_label(
    ax,
    item: dict[str, object],
    *,
    options: dict[str, object],
    display_index: int,
    compress_labels: bool,
) -> None:
    label = str(item["label"])
    if not label:
        return
    xytext = _point_label_xytext(options, display_index)
    ax.annotate(
        _display_label(label, compress_labels=compress_labels),
        (item["x"], item["y"]),
        textcoords="offset points",
        xytext=xytext,
        ha="center",
        va="bottom",
        zorder=5,
    )


def _truthy_label_skip(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "skip", "hide"}


def _point_label_xytext(options: dict[str, object], index: int) -> tuple[float, float]:
    offset = options.get("offset")
    if isinstance(offset, tuple):
        return offset
    if options.get("fanout") == "compass":
        return _AVOID_OVERLAP_OFFSETS[index % len(_AVOID_OVERLAP_OFFSETS)]
    return (0.0, 4.0)


def _record_point_label_skips(
    ax,
    *,
    skipped: list[dict[str, object]],
    total: int,
    shown: int,
) -> None:
    prior = getattr(ax, "_graph_hub_point_label_skips", None)
    if not isinstance(prior, dict):
        prior = {"total_labels": 0, "shown_labels": 0, "skipped_labels": 0, "reasons": {}, "examples": []}
    prior["total_labels"] = int(prior.get("total_labels", 0)) + int(total)
    prior["shown_labels"] = int(prior.get("shown_labels", 0)) + int(shown)
    prior["skipped_labels"] = int(prior.get("skipped_labels", 0)) + len(skipped)
    reasons = prior.get("reasons")
    if not isinstance(reasons, dict):
        reasons = {}
    examples = prior.get("examples")
    if not isinstance(examples, list):
        examples = []
    for item in skipped:
        reason = str(item.get("reason") or "unknown")
        reasons[reason] = int(reasons.get(reason, 0)) + 1
        if len(examples) < 20:
            examples.append(
                {"index": int(item.get("index", -1)), "label": str(item.get("label") or ""), "reason": reason}
            )
    prior["reasons"] = reasons
    prior["examples"] = examples
    ax._graph_hub_point_label_skips = prior


def _series_style_override(spec: BridgeFigureSpec, series_name: object) -> dict[str, object]:
    styles = spec.series_styles or {}
    if not isinstance(styles, dict):
        return {}
    style = styles.get(str(series_name))
    if style is None and series_name == "__single__":
        style = styles.get("__single__") or styles.get("default")
    return dict(style) if isinstance(style, dict) else {}


def _style_float(sty: dict[str, object], key: str) -> float | None:
    if key not in sty:
        return None
    try:
        return float(sty[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"series_styles {key} must be numeric") from exc


def _series_style(spec: BridgeFigureSpec, series_index: int, series_name: object) -> dict[str, object]:
    style = dict(get_series_style(series_index))
    override = _series_style_override(spec, series_name)
    if "marker" in override:
        marker = str(override.get("marker") or "").strip()
        if marker:
            style["marker"] = marker
    if "linestyle" in override:
        style["linestyle"] = str(override.get("linestyle") or style.get("linestyle") or "-")
    if "hatch" in override:
        style["hatch"] = str(override.get("hatch") or "")
    if "color" in override:
        color = str(override.get("color") or "").strip()
        if color:
            style["color"] = color
    if "label" in override:
        label = str(override.get("label") or "").strip()
        if label:
            style["label"] = label
    for numeric_key in ("alpha", "size", "linewidth", "zorder"):
        if numeric_key in override:
            style[numeric_key] = _style_float(override, numeric_key)
    fill = str(override.get("fill") or "").strip().lower()
    markerfacecolor = override.get("facecolor", override.get("markerfacecolor"))
    markeredgecolor = override.get("edgecolor", override.get("markeredgecolor"))
    if markerfacecolor is None and "color" in style and fill not in {"none", "open"}:
        markerfacecolor = style["color"]
    if markeredgecolor is None and "color" in style:
        markeredgecolor = style["color"]
    if fill in {"none", "open"}:
        markerfacecolor = "none"
    elif fill in {"filled", "full"} and markerfacecolor is None:
        markerfacecolor = None
    if markerfacecolor is not None:
        style["markerfacecolor"] = str(markerfacecolor)
    if markeredgecolor is not None:
        style["markeredgecolor"] = str(markeredgecolor)
    return style


def _render_xy_plot(ax, points: list[dict], spec: BridgeFigureSpec, *, line: bool, small_panel: bool = False) -> None:
    context = XYRendererContext(
        marker_tokens=_marker_tokens,
        scatter_marker_area=_scatter_marker_area,
        series_style=_series_style,
        display_label=_display_label,
        annotate_points=_annotate_points,
        apply_legend=_apply_legend,
        apply_marker_axis_margin=_apply_marker_axis_margin,
        apply_axis_limits=_apply_axis_limits,
        apply_tick_style=_apply_tick_style,
    )
    _render_xy_plot_impl(ax, points, spec, line=line, small_panel=small_panel, context=context)


def _has_statistical_overlays(spec: BridgeFigureSpec) -> bool:
    return bool(spec.fit_line or spec.ci_band or spec.fit_options or spec.significance_markers)


def _has_manual_overlays(spec: BridgeFigureSpec) -> bool:
    return bool(spec.guide_curves or spec.fill_between)


def _validate_manual_overlays(spec: BridgeFigureSpec) -> None:
    if not _has_manual_overlays(spec):
        return
    plot_type = str(spec.plot_type or "").strip().lower()
    if plot_type not in {"line", "scatter", "xy"}:
        raise ValueError(
            f"manual overlays are only supported for plot_type 'line', 'scatter', or 'xy'; got {spec.plot_type!r}"
        )
    if spec.y_break_range is not None:
        raise ValueError("manual overlays do not support y_break_range")


def _validate_statistical_overlays(points: list[dict], spec: BridgeFigureSpec) -> None:
    if not _has_statistical_overlays(spec):
        return
    _normalized_fit_options(spec.fit_options)
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
        _numeric_xy_arrays(points, min_points=min_points, context="fit_line/ci_band")
    _normalized_significance_markers(spec.significance_markers)


def _numeric_xy_arrays(points: list[dict], *, min_points: int, context: str) -> tuple[np.ndarray, np.ndarray]:
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


def _finite_float(value: object, *, context: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{context} must be finite")
    return number


def _normalized_fit_options(value: object) -> dict[str, object]:
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
        linewidth = _finite_float(value["linewidth"], context="fit_options.linewidth")
        if linewidth <= 0:
            raise ValueError("fit_options.linewidth must be positive")
        normalized["linewidth"] = linewidth
    if "zorder" in value and value.get("zorder") is not None:
        normalized["zorder"] = _finite_float(value["zorder"], context="fit_options.zorder")
    if "ci_alpha" in value and value.get("ci_alpha") is not None:
        ci_alpha = _finite_float(value["ci_alpha"], context="fit_options.ci_alpha")
        if ci_alpha < 0 or ci_alpha > 1:
            raise ValueError("fit_options.ci_alpha must be between 0 and 1")
        normalized["ci_alpha"] = ci_alpha
    return normalized


def _overlay_xy_arrays(overlay: dict, *, field_name: str) -> tuple[list[float], list[float]]:
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
            xs.append(_finite_float(point["x"], context=f"{field_name}.points[{index}].x"))
            ys.append(_finite_float(point["y"], context=f"{field_name}.points[{index}].y"))
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
        [_finite_float(value, context=f"{field_name}.x[{index}]") for index, value in enumerate(x_values)],
        [_finite_float(value, context=f"{field_name}.y[{index}]") for index, value in enumerate(y_values)],
    )


def _fill_between_arrays(
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
            xs.append(_finite_float(point["x"], context=f"{field_name}.points[{index}].x"))
            y1s.append(_finite_float(point["y1"], context=f"{field_name}.points[{index}].y1"))
            y2s.append(_finite_float(point["y2"], context=f"{field_name}.points[{index}].y2"))
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
            xs.append(_finite_float(row[x_column], context=f"{field_name}.{x_column} row {row_index}"))
            y1s.append(_finite_float(row[y1_column], context=f"{field_name}.{y1_column} row {row_index}"))
            y2s.append(_finite_float(row[y2_column], context=f"{field_name}.{y2_column} row {row_index}"))
    if len(xs) < 2:
        raise ValueError(f"{field_name} requires at least two rows")
    return xs, y1s, y2s


def _overlay_line_kwargs(overlay: dict) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "color": str(overlay.get("color") or "black"),
        "linewidth": float(overlay.get("linewidth", 1.0)),
        "linestyle": str(overlay.get("linestyle") or "-"),
        "zorder": float(overlay.get("zorder", 4)),
    }
    if overlay.get("label"):
        kwargs["label"] = str(overlay["label"])
    return kwargs


def _draw_manual_overlays(ax, csv_path: Path, spec: BridgeFigureSpec) -> None:
    for index, overlay in enumerate(spec.fill_between or ()):
        region = dict(overlay)
        if not region.get("points") and not str(region.get("x_column") or "").strip():
            region["x_column"] = spec.x_column
        xs, y1s, y2s = _fill_between_arrays(csv_path, region, field_name=f"fill_between[{index}]")
        kwargs: dict[str, object] = {
            "color": str(region.get("color") or "black"),
            "alpha": float(region.get("alpha", 0.15)),
            "linewidth": 0,
            "zorder": float(region.get("zorder", 1)),
        }
        if region.get("label"):
            kwargs["label"] = str(region["label"])
        artist = ax.fill_between(xs, y1s, y2s, **kwargs)
        _tag_overlay_artist(artist, role="fill_between", label=str(region.get("label") or f"fill_between[{index}]"))

    for index, overlay in enumerate(spec.guide_curves or ()):
        xs, ys = _overlay_xy_arrays(overlay, field_name=f"guide_curves[{index}]")
        ax.plot(xs, ys, **_overlay_line_kwargs(overlay))

    if any(isinstance(overlay, dict) and overlay.get("label") for overlay in (*spec.fill_between, *spec.guide_curves)):
        _apply_legend(ax, spec, n_series=1)


def _tag_overlay_artist(artist, *, role: str, label: str) -> None:
    artist._graph_hub_overlay_role = role
    artist._graph_hub_overlay_label = label


def _tag_annotation_text(artist, *, role: str) -> None:
    artist._graph_hub_annotation_text_role = role


def _normalized_axis_scale(value: str, *, field_name: str) -> str:
    scale = str(value or "linear").strip().lower()
    if scale not in {"linear", "log"}:
        raise ValueError(f"{field_name} must be 'linear' or 'log'")
    return scale


def _validate_axis_scales(points: list[dict], spec: BridgeFigureSpec) -> None:
    x_scale = _normalized_axis_scale(spec.x_scale, field_name="x_scale")
    y_scale = _normalized_axis_scale(spec.y_scale, field_name="y_scale")
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


def _validate_axis_limits(points: list[dict], spec: BridgeFigureSpec) -> None:
    limits = _normalized_axis_limits(spec)
    for axis_name in ("x", "y"):
        if axis_name in limits and any(not isinstance(point[axis_name], (int, float)) for point in points):
            raise ValueError(f"axis_limits.{axis_name} requires numeric {axis_name} values")


def _apply_axis_scales(ax, spec: BridgeFigureSpec) -> None:
    x_scale = _normalized_axis_scale(spec.x_scale, field_name="x_scale")
    y_scale = _normalized_axis_scale(spec.y_scale, field_name="y_scale")
    if x_scale != "linear":
        ax.set_xscale(x_scale)
    if y_scale != "linear":
        ax.set_yscale(y_scale)


def _visible_plot_axes(fig, fallback_ax=None) -> list:
    axes = [ax for ax in fig.axes if ax.get_visible() and getattr(ax, "_graph_hub_role", "") != "colorbar"]
    if not axes and fallback_ax is not None:
        axes = [fallback_ax]
    return axes


def _apply_axis_scales_to_visible_axes(fig, fallback_ax, spec: BridgeFigureSpec) -> None:
    for axis in _visible_plot_axes(fig, fallback_ax):
        _apply_axis_scales(axis, spec)


def _normalized_axis_limit_pair(raw_pair: object, *, field_name: str) -> tuple[float | None, float | None]:
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


def _normalized_axis_limits(spec: BridgeFigureSpec) -> dict[str, tuple[float | None, float | None]]:
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
        lower, upper = _normalized_axis_limit_pair(raw_limits[axis_name], field_name=f"axis_limits.{axis_name}")
        scale = _normalized_axis_scale(getattr(spec, f"{axis_name}_scale"), field_name=f"{axis_name}_scale")
        if scale == "log" and any(value is not None and value <= 0 for value in (lower, upper)):
            raise ValueError(f"axis_limits.{axis_name} values must be > 0 when {axis_name}_scale='log'")
        normalized[axis_name] = (lower, upper)
    return normalized


def _apply_axis_limits(ax, spec: BridgeFigureSpec) -> None:
    limits = _normalized_axis_limits(spec)
    if "x" in limits:
        ax.set_xlim(*limits["x"])
    if "y" in limits:
        ax.set_ylim(*limits["y"])


def _apply_axis_limits_to_visible_axes(fig, fallback_ax, spec: BridgeFigureSpec) -> None:
    for axis in _visible_plot_axes(fig, fallback_ax):
        _apply_axis_limits(axis, spec)


def _normalized_tick_style(spec: BridgeFigureSpec) -> dict[str, object]:
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


def _axis_is_numeric(ax, axis_name: str) -> bool:
    values = ax.get_lines()
    for line in values:
        data = line.get_xdata() if axis_name == "x" else line.get_ydata()
        if len(data):
            return all(isinstance(value, (int, float, np.number)) for value in data)
    return True


def _apply_tick_style(ax, spec: BridgeFigureSpec) -> None:
    style = _normalized_tick_style(spec)
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
        _apply_tick_label_char_limit(ax, int(style["max_label_chars"]))


def _apply_tick_label_char_limit(ax, max_label_chars: int) -> None:
    base_formatter = ax.xaxis.get_major_formatter()
    original_labels: dict[int, str] = {}

    raw_label_map = getattr(ax, "_graph_hub_original_xtick_labels", {})

    def limited_formatter(value: float, position: int | None = None) -> str:
        formatted = str(base_formatter(value, position))
        original = str(raw_label_map.get(int(position), formatted)) if position is not None else formatted
        if position is not None:
            original_labels[int(position)] = original
        return _truncate_tick_label(formatted, max_label_chars)

    formatter = mticker.FuncFormatter(limited_formatter)
    formatter._graph_hub_original_formatter = base_formatter
    formatter._graph_hub_original_tick_labels = original_labels
    formatter._graph_hub_max_label_chars = int(max_label_chars)
    ax.xaxis.set_major_formatter(formatter)


def _truncate_tick_label(text: str, max_label_chars: int) -> str:
    if len(text) <= max_label_chars:
        return text
    return f"{text[: max_label_chars - 3]}..."


def _apply_tick_style_to_visible_axes(fig, fallback_ax, spec: BridgeFigureSpec) -> None:
    for axis in _visible_plot_axes(fig, fallback_ax):
        _apply_tick_style(axis, spec)


def _normalized_legend_options(spec: BridgeFigureSpec) -> dict[str, object]:
    raw_options = spec.legend_options
    if raw_options in (None, {}, []):
        return {}
    if not isinstance(raw_options, dict):
        raise ValueError("legend_options must be an object")
    allowed = {"title", "order", "ncol"}
    unsupported = sorted(set(raw_options) - allowed)
    if unsupported:
        raise ValueError(f"legend_options has unsupported key(s): {', '.join(unsupported)}")
    normalized: dict[str, object] = {}
    if raw_options.get("title") is not None:
        normalized["title"] = str(raw_options["title"])
    if raw_options.get("order") is not None:
        order = raw_options["order"]
        if not isinstance(order, (list, tuple)):
            raise ValueError("legend_options.order must be an array of labels")
        labels = tuple(str(label) for label in order if str(label).strip())
        if len(labels) != len(set(labels)):
            raise ValueError("legend_options.order must not contain duplicate labels")
        normalized["order"] = labels
    if raw_options.get("ncol") is not None:
        try:
            ncol = int(raw_options["ncol"])
        except (TypeError, ValueError) as exc:
            raise ValueError("legend_options.ncol must be an integer") from exc
        if ncol < 1 or ncol > 8:
            raise ValueError("legend_options.ncol must be between 1 and 8")
        normalized["ncol"] = ncol
    return normalized


def _normalized_point_label_options(spec: BridgeFigureSpec) -> dict[str, object]:
    return _normalized_point_label_options_dict(spec.point_label_options)


def _normalized_point_label_options_dict(raw_options: dict | None) -> dict[str, object]:
    if raw_options in (None, {}, []):
        return {}
    if not isinstance(raw_options, dict):
        raise ValueError("point_label_options must be an object")
    allowed = {"offset", "fanout", "max_labels", "priority_column", "skip_column"}
    unsupported = sorted(set(raw_options) - allowed)
    if unsupported:
        raise ValueError(f"point_label_options has unsupported key(s): {', '.join(unsupported)}")
    normalized: dict[str, object] = {}
    if raw_options.get("offset") is not None:
        offset = raw_options["offset"]
        if not isinstance(offset, dict):
            raise ValueError("point_label_options.offset must be an object")
        try:
            dx = float(offset["dx"])
            dy = float(offset["dy"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("point_label_options.offset requires numeric dx and dy") from exc
        if not math.isfinite(dx) or not math.isfinite(dy):
            raise ValueError("point_label_options.offset dx and dy must be finite")
        normalized["offset"] = (dx, dy)
    if raw_options.get("fanout") is not None:
        fanout = str(raw_options["fanout"]).strip().lower().replace("-", "_")
        if fanout not in {"none", "compass"}:
            raise ValueError("point_label_options.fanout must be 'none' or 'compass'")
        normalized["fanout"] = fanout
    if raw_options.get("max_labels") is not None:
        try:
            max_labels = int(raw_options["max_labels"])
        except (TypeError, ValueError) as exc:
            raise ValueError("point_label_options.max_labels must be an integer") from exc
        if max_labels < 1:
            raise ValueError("point_label_options.max_labels must be at least 1")
        normalized["max_labels"] = max_labels
    for key in ("priority_column", "skip_column"):
        if raw_options.get(key) is None or raw_options.get(key) == "":
            continue
        if not isinstance(raw_options[key], str):
            raise ValueError(f"point_label_options.{key} must be a string")
        column = raw_options[key].strip()
        if not column:
            raise ValueError(f"point_label_options.{key} must be a non-empty string when provided")
        normalized[key] = column
    return normalized


_CALLOUT_OFFSET_PRESETS: dict[str, tuple[float, float]] = {
    "above": (0.0, 10.0),
    "below": (0.0, -10.0),
    "left": (-10.0, 0.0),
    "right": (10.0, 0.0),
    "upper_left": (-8.0, 8.0),
    "upper_right": (8.0, 8.0),
    "lower_left": (-8.0, -8.0),
    "lower_right": (8.0, -8.0),
}
_AVOID_OVERLAP_OFFSETS: tuple[tuple[float, float], ...] = (
    (8.0, 8.0),
    (-8.0, 8.0),
    (8.0, -8.0),
    (-8.0, -8.0),
    (0.0, 12.0),
    (12.0, 0.0),
)


def _reject_non_point_callout_fields(annotation: dict[str, object], index: int) -> None:
    unsupported = [
        key
        for key in ("xytext_offset", "placement_preset", "avoid_overlap")
        if key in annotation and annotation.get(key) is not None
    ]
    if unsupported:
        joined = ", ".join(unsupported)
        raise ValueError(f"annotations[{index}] {joined} only apply to point annotations")


def _normalized_callout_offset(annotation: dict[str, object], index: int) -> tuple[float, float] | None:
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
        if preset not in _CALLOUT_OFFSET_PRESETS:
            allowed = ", ".join(sorted(_CALLOUT_OFFSET_PRESETS))
            raise ValueError(f"annotations[{index}].placement_preset must be one of: {allowed}")
        return _CALLOUT_OFFSET_PRESETS[preset]
    raw_avoid_overlap = annotation.get("avoid_overlap", False)
    if not isinstance(raw_avoid_overlap, bool):
        raise ValueError(f"annotations[{index}].avoid_overlap must be a boolean")
    if raw_avoid_overlap:
        return _AVOID_OVERLAP_OFFSETS[index % len(_AVOID_OVERLAP_OFFSETS)]
    return None


def _normalized_span_annotation(
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


def _normalized_annotations(annotations: object) -> tuple[dict[str, object], ...]:
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
            _reject_non_point_callout_fields(annotation, index)
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
            _reject_non_point_callout_fields(annotation, index)
            normalized.append(
                _normalized_span_annotation(annotation, index, field="hspan", bounds=("ymin", "ymax"))
            )
            continue
        if annotation.get("vspan") is not None:
            _reject_non_point_callout_fields(annotation, index)
            normalized.append(
                _normalized_span_annotation(annotation, index, field="vspan", bounds=("xmin", "xmax"))
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
        callout_offset = _normalized_callout_offset(annotation, index)
        if callout_offset is not None:
            item["xytext_offset"] = callout_offset
        if connectionstyle:
            item["connectionstyle"] = connectionstyle
        normalized.append(item)
    return tuple(normalized)


def _annotation_font_size() -> float:
    """Resolve the active style's small-text size in points.

    Annotations previously inherited matplotlib's default ``font.size`` (10 pt),
    which is off the style-token scale and trips the ``font_size_token_drift``
    geometry check. Reuse the active tick-label size so annotation text matches
    the rest of the figure.
    """
    for key in ("xtick.labelsize", "legend.fontsize"):
        try:
            return float(FontProperties(size=plt.rcParams[key]).get_size_in_points())
        except (KeyError, ValueError, TypeError):
            continue
    return 6.5


def _span_midpoint(lower: float, upper: float) -> float:
    return math.sqrt(lower * upper) if lower > 0 and upper > 0 else 0.5 * (lower + upper)


def _draw_annotations(ax, spec: BridgeFigureSpec) -> None:
    font_size = _annotation_font_size()
    for annotation in _normalized_annotations(spec.annotations):
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
            _tag_overlay_artist(artist, role="annotation_region", label=region_text or "region")
            if region_text:
                text_artist = ax.text(
                    _span_midpoint(xmin, xmax),
                    _span_midpoint(ymin, ymax),
                    region_text,
                    color=color,
                    fontsize=font_size,
                    ha="center",
                    va="center",
                    zorder=1,
                    clip_on=True,
                )
                _tag_annotation_text(text_artist, role="annotation_region")
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
            _tag_overlay_artist(artist, role="annotation_hspan", label=span_text or "hspan")
            if span_text:
                text_artist = ax.text(
                    0.5,
                    _span_midpoint(ymin, ymax),
                    span_text,
                    transform=ax.get_yaxis_transform(),
                    color=color,
                    fontsize=font_size,
                    ha="center",
                    va="center",
                    zorder=1,
                    clip_on=True,
                )
                _tag_annotation_text(text_artist, role="annotation_hspan")
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
            _tag_overlay_artist(artist, role="annotation_vspan", label=span_text or "vspan")
            if span_text:
                text_artist = ax.text(
                    _span_midpoint(xmin, xmax),
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
                _tag_annotation_text(text_artist, role="annotation_vspan")
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
            _tag_annotation_text(text_artist, role="annotation_point")
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
            _tag_annotation_text(text_artist, role="annotation_point")


def _draw_annotations_on_visible_axes(fig, fallback_ax, spec: BridgeFigureSpec) -> None:
    if not spec.annotations:
        return
    axes = _visible_plot_axes(fig, fallback_ax)
    if spec.plot_type == "facet":
        axes = axes[:1]
    for axis in axes:
        _draw_annotations(axis, spec)


def _normalized_significance_markers(markers: object) -> tuple[dict[str, float | str | None], ...]:
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


def _draw_statistical_overlays(ax, points: list[dict], spec: BridgeFigureSpec) -> None:
    if not _has_statistical_overlays(spec):
        return
    if spec.fit_line or spec.ci_band:
        _draw_linear_fit_overlay(ax, points, spec)
    for marker in _normalized_significance_markers(spec.significance_markers):
        annotate_significance(
            ax,
            marker["x1"],
            marker["x2"],
            marker["y"],
            str(marker["label"]),
            h=marker["h"],
            color=str(marker["color"]),
        )


def _draw_linear_fit_overlay(ax, points: list[dict], spec: BridgeFigureSpec) -> None:
    options = _normalized_fit_options(spec.fit_options)
    xs, ys = _numeric_xy_arrays(points, min_points=3 if spec.ci_band else 2, context="fit_line/ci_band")
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
    t_crit = _t_critical_95(dof)
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


def _t_critical_95(dof: int) -> float:
    try:
        from scipy.stats import t

        return float(t.ppf(0.975, dof))
    except Exception:
        return 1.96


def _render_broken_axis_plot(fig, points: list[dict], spec: BridgeFigureSpec) -> None:
    if not points:
        warnings.warn(
            f"bridge_renderer: no valid data points for {spec.title!r}, figure will be blank",
            stacklevel=2,
        )
        return

    plot_type = str(spec.plot_type or "line").strip().lower()
    plot_type_entry = PLOT_TYPES.get(plot_type)
    if plot_type_entry is None:
        raise ValueError(f"y_break_range requires registered plot_type; got {spec.plot_type!r}")
    if not plot_type_entry.capabilities.get("supports_broken_axis"):
        raise ValueError(f"plot_type {plot_type!r} does not support y_break_range")

    ax_top, ax_bot = _make_broken_y_axes(fig, points, spec.y_break_range)
    _draw_grouped_broken_xy(ax_top, ax_bot, points, spec, line=plot_type != "scatter")
    _draw_overlay_baselines(ax_top, spec.overlay_baselines)
    ax_bot.set_xlabel(spec.x_axis_label or spec.x_column)
    ax_top.set_ylabel(spec.y_axis_label or spec.y_column)
    ax_top.set_title(spec.title)
    _separate_top_legend_title(ax_top, spec)


def _broken_axis_context() -> BrokenAxisRendererContext:
    return BrokenAxisRendererContext(
        draw_break_marks=_draw_break_marks,
        marker_tokens=_marker_tokens,
        scatter_marker_area=_scatter_marker_area,
        series_style=_series_style,
        display_label=_display_label,
        normalized_point_label_options=_normalized_point_label_options,
        point_label_candidates=_point_label_candidates,
        draw_point_label=_draw_point_label,
        record_point_label_skips=_record_point_label_skips,
        apply_legend=_apply_legend,
    )


def _make_broken_y_axes(fig, points: list[dict], break_range: tuple[float, float] | None):
    return _make_broken_y_axes_impl(fig, points, break_range, context=_broken_axis_context())


def _draw_grouped_broken_xy(ax_top, ax_bot, points: list[dict], spec: BridgeFigureSpec, *, line: bool) -> None:
    _draw_grouped_broken_xy_impl(ax_top, ax_bot, points, spec, line=line, context=_broken_axis_context())


def _draw_broken_xy_series(
    ax,
    xs,
    ys,
    yerr,
    sty: dict,
    *,
    label: str | None,
    spec: BridgeFigureSpec,
    line: bool,
) -> None:
    _draw_broken_xy_series_impl(
        ax,
        xs,
        ys,
        yerr,
        sty,
        label=label,
        spec=spec,
        line=line,
        context=_broken_axis_context(),
    )


def _annotate_broken_axis_points(ax_top, ax_bot, series_points: list[dict], spec: BridgeFigureSpec) -> None:
    _annotate_broken_axis_points_impl(ax_top, ax_bot, series_points, spec, context=_broken_axis_context())


def _facet_renderer_context() -> FacetRendererContext:
    return FacetRendererContext(
        render_xy_plot=_render_xy_plot,
        display_label=_display_label,
        marker_tokens=_marker_tokens,
        apply_facet_headroom=_apply_facet_headroom,
    )


def _render_facet_plot(ax, points: list[dict], spec: BridgeFigureSpec) -> None:
    _render_facet_plot_impl(ax, points, spec, context=_facet_renderer_context())


def _resolve_facet_grid(n_facets: int, spec: BridgeFigureSpec) -> tuple[int, int]:
    return _resolve_facet_grid_impl(n_facets, spec)


def _optional_positive_int(value: int | None, name: str) -> int | None:
    return _optional_positive_int_impl(value, name)


def _expand_shared_facet_limits_for_markers(axes, spec: BridgeFigureSpec) -> None:
    _expand_shared_facet_limits_impl(axes, spec, context=_facet_renderer_context())


def _group_facet_points(points: list[dict]) -> dict[str, list[dict]]:
    return _group_facet_points_impl(points)


def _render_bar_plot(ax, points: list[dict], spec: BridgeFigureSpec) -> None:
    context = BarRendererContext(
        display_label=_display_label,
        series_style=_series_style,
        annotate_points=_annotate_points,
        apply_legend=_apply_legend,
    )
    _render_bar_plot_impl(ax, points, spec, context=context)


def _render_plot(ax, points: list[dict], spec: BridgeFigureSpec) -> None:
    if not points:
        warnings.warn(
            f"bridge_renderer: no valid data points for {spec.title!r}, figure will be blank",
            stacklevel=2,
        )
        return
    if spec.plot_type not in PLOT_TYPES:
        warnings.warn(
            f"bridge_renderer: unknown plot_type {spec.plot_type!r}, falling back to line plot",
            stacklevel=2,
        )
        spec = BridgeFigureSpec(**{**spec.__dict__, "plot_type": "line"})
    render_plot(ax, points, spec)


def _draw_overlay_baselines(ax, baselines: tuple[dict, ...]) -> None:
    """Draw literature reference baselines as dashed horizontal lines."""
    for bl in baselines:
        value = bl.get("value")
        if value is None:
            continue
        label = bl.get("label", "")
        ax.axhline(y=value, linestyle="--", color="gray", alpha=0.5, linewidth=0.8)
        if label:
            ax.annotate(
                label,
                xy=(0.02, value),
                xycoords=("axes fraction", "data"),
                fontsize=5,
                color="gray",
                alpha=0.7,
                verticalalignment="bottom",
            )


def _display_label(value: object, *, compress_labels: bool = True) -> str:
    text = str(value)
    if not compress_labels:
        return text
    return compress_sample_label(text)


def _apply_axes_metadata(ax, spec: BridgeFigureSpec) -> None:
    ax.set_xlabel(spec.x_axis_label or spec.x_column)
    ax.set_ylabel(spec.y_axis_label or spec.y_column)


def _separate_top_legend_title(ax, spec: BridgeFigureSpec) -> None:
    legend = ax.get_legend()
    if not spec.title or (
        _resolved_legend_layout(spec) != "top_outside"
        and getattr(legend, "_graph_hub_legend_placement", None) != "top_outside"
    ):
        return
    if legend is None:
        return

    fig = ax.figure
    pad_px = float(plt.rcParams.get("axes.titlepad", 6.0)) * fig.dpi / 72.0
    for _ in range(2):
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        title_bb = ax.title.get_window_extent(renderer)
        legend_bb = legend.get_window_extent(renderer)
        overlap_width = min(title_bb.x1, legend_bb.x1) - max(title_bb.x0, legend_bb.x0)
        overlap_height = min(title_bb.y1, legend_bb.y1) - max(title_bb.y0, legend_bb.y0)
        if overlap_width <= 0 or overlap_height <= 0:
            return

        axes_height = ax.get_window_extent(renderer).height
        if axes_height <= 0:
            return
        title_x, title_y = ax.title.get_position()
        ax.set_title(ax.title.get_text(), x=title_x, y=title_y + (overlap_height + pad_px) / axes_height)


def _find_best_legend_location(ax) -> dict:
    """
    데이터 포인트의 밀도를 분석하여 가장 비어있는 공간에 범례를 배치합니다. (Smart Legend Avoidance)
    """
    # 1. 데이터 포인트 추출 (Axes 좌표계 0~1)
    # 현재 그려진 모든 Line2D, PathCollection(scatter)에서 데이터를 가져옴
    x_data = []
    y_data = []

    # x, y축 범위 확인
    x_lim = ax.get_xlim()
    y_lim = ax.get_ylim()

    # ax.lines: plot()으로 추가된 데이터 라인만 (spine/grid/tick 제외)
    for line in ax.lines:
        x_data.extend(line.get_xdata())
        y_data.extend(line.get_ydata())
    # ax.collections: scatter/errorbar 등으로 추가된 컬렉션만
    for coll in ax.collections:
        if hasattr(coll, "get_offsets"):
            offsets = coll.get_offsets()
            if len(offsets) > 0:
                x_data.extend(offsets[:, 0])
                y_data.extend(offsets[:, 1])

    if not x_data:
        return {"loc": "best", "frameon": False}

    x_range = x_lim[1] - x_lim[0]
    y_range = y_lim[1] - y_lim[0]
    if x_range == 0 or y_range == 0:
        return {"loc": "best", "frameon": False}

    # 2. 점유 그리드 계산 (10x10)
    grid_size = 10
    grid = np.zeros((grid_size, grid_size))

    # 데이터를 0~1 사이로 정규화
    try:
        x_norm = (np.array(x_data) - x_lim[0]) / x_range
        y_norm = (np.array(y_data) - y_lim[0]) / y_range

        # 범위 밖 데이터 제거
        mask = (x_norm >= 0) & (x_norm <= 1) & (y_norm >= 0) & (y_norm <= 1)
        x_norm, y_norm = x_norm[mask], y_norm[mask]

        for xi, yi in zip(x_norm, y_norm):
            gx = min(int(xi * grid_size), grid_size - 1)
            gy = min(int(yi * grid_size), grid_size - 1)
            grid[gy, gx] += 1
    except (ValueError, ZeroDivisionError):
        return {"loc": "best", "frameon": False}

    # 3. 범례 크기(대략 3x2 그리드)를 고려한 최적 위치 탐색
    # (row, col)은 범례의 중심점 후보
    best_score = float("inf")
    best_pos = (grid_size - 1, grid_size - 1)  # Default to upper right

    # 범례가 차지할 대략적인 영역 (3x2 그리드)
    # 0.05 마진을 고려하여 1~8 범위 탐색
    for r in range(1, grid_size - 1):
        for c in range(1, grid_size - 1):
            # 주변 3x3 영역의 합계를 점수로 사용 (가중치 부여)
            r_start, r_end = max(0, r - 1), min(grid_size, r + 2)
            c_start, c_end = max(0, c - 1), min(grid_size, c + 2)
            score = np.sum(grid[r_start:r_end, c_start:c_end])

            # 구석진 곳 선호 (중심에서 멀어질수록 유리)
            dist_to_edge = min(r, grid_size - 1 - r, c, grid_size - 1 - c)
            score += dist_to_edge * 0.1

            if score < best_score:
                best_score = score
                best_pos = (r, c)

    # 4. 좌표 변환 및 반환
    # Matplotlib의 bbox_to_anchor는 (x, y) 형태
    target_x = best_pos[1] / grid_size
    target_y = best_pos[0] / grid_size

    # 마진 적용 (0.05 ~ 0.95 사이로 제한)
    target_x = max(0.05, min(0.95, target_x))
    target_y = max(0.05, min(0.95, target_y))

    # 5. 투명도 폴백 (데이터가 너무 많으면 배경 투명하게)
    is_crowded = best_score > (len(x_data) * 0.1)  # 전체 데이터의 10% 이상이 근처에 있으면

    legend_args = {
        "bbox_to_anchor": (target_x, target_y),
        "loc": "center",
        "bbox_transform": ax.transAxes,
        "frameon": True,
        "fontsize": "small",
    }

    if is_crowded:
        legend_args["framealpha"] = 0.7
    else:
        legend_args["frameon"] = False  # 비어있으면 깔끔하게 테두리 제거

    return legend_args


def _legend_data_overlap_fraction(ax) -> float:
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    legend = ax.get_legend()
    if legend is None or not legend.get_visible():
        return 0.0
    from hub_core.geometry_diagnostics import _box_area, _data_union_bbox, _extent, _inter_area

    legend_bb = _extent(legend, renderer)
    data_union = _data_union_bbox(ax, renderer)
    if legend_bb is None or data_union is None:
        return 0.0
    legend_area = _box_area(legend_bb)
    if legend_area <= 0:
        return 0.0
    return float(_inter_area(legend_bb, data_union) / legend_area)


def _legend_inside_axes(ax) -> bool:
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    legend = ax.get_legend()
    if legend is None or not legend.get_visible():
        return False
    legend_box = legend.get_window_extent(renderer)
    axes_box = ax.get_window_extent(renderer)
    return bool(
        legend_box.x0 >= axes_box.x0
        and legend_box.x1 <= axes_box.x1
        and legend_box.y0 >= axes_box.y0
        and legend_box.y1 <= axes_box.y1
    )


def _replace_legend(ax, **kwargs):
    legend = ax.get_legend()
    if legend is None:
        return None
    handles, labels = ax.get_legend_handles_labels()
    pairs = [(handle, label) for handle, label in zip(handles, labels) if label and label != "_nolegend_"]
    if not pairs:
        return legend
    legend.remove()
    handles, labels = zip(*pairs)
    return ax.legend(handles, labels, **kwargs)


def _avoid_smart_legend_data_collision(fig, ax, spec: BridgeFigureSpec) -> str:
    legend = ax.get_legend()
    if legend is None:
        return "none"
    if _legend_data_overlap_fraction(ax) <= _LEGEND_DATA_OVERLAP_WARN and _legend_inside_axes(ax):
        setattr(legend, "_graph_hub_legend_placement", "inside")
        return "inside"

    for loc in _SMART_LEGEND_INSIDE_CANDIDATES:
        candidate = _replace_legend(ax, loc=loc, frameon=False, fontsize="small")
        if candidate is None:
            return "none"
        fig.tight_layout(pad=0.5)
        if _legend_data_overlap_fraction(ax) <= _LEGEND_DATA_OVERLAP_WARN and _legend_inside_axes(ax):
            setattr(candidate, "_graph_hub_legend_placement", "inside")
            return "inside"

    ncol = min(max(len(ax.get_legend_handles_labels()[1]), 1), 3)
    fallback = _replace_legend(
        ax,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.02),
        ncol=ncol,
        frameon=False,
        fontsize=plt.rcParams.get("legend.fontsize", 7.0),
    )
    if fallback is not None:
        setattr(fallback, "_graph_hub_legend_placement", "top_outside")
    fig.tight_layout(pad=0.5)
    _separate_top_legend_title(ax, spec)
    return "top_outside"


def _legend_kwargs(ax, spec: BridgeFigureSpec, *, n_series: int) -> dict:
    layout = _resolved_legend_layout(spec)
    if layout == "smart":
        return _find_best_legend_location(ax)
    if layout == "right_outside":
        return get_legend_args("right_outside", ncol=1)
    if layout == "best":
        kwargs = dict(get_legend_args("standard"))
        kwargs["frameon"] = False
        return kwargs
    if layout == "standard":
        kwargs = dict(get_legend_args("standard"))
        kwargs["frameon"] = False
        return kwargs

    kwargs = dict(get_standard_legend_props())
    kwargs["ncol"] = min(max(n_series, 1), 4)
    return kwargs


def _apply_legend(ax, spec: BridgeFigureSpec, *, n_series: int) -> None:
    kwargs = _legend_kwargs(ax, spec, n_series=n_series)
    options = _normalized_legend_options(spec)
    if "title" in options:
        kwargs["title"] = options["title"]
    if "ncol" in options:
        kwargs["ncol"] = options["ncol"]
    try:
        handles, labels = ax.get_legend_handles_labels()
    except ValueError:
        ax.legend(**kwargs)
        return
    if options.get("order"):
        legend_entries = list(getattr(ax, "_graph_hub_legend_entries", ()))
        raw_to_label = {raw: label for raw, label in legend_entries}
        label_to_items = {label: (handle, label) for handle, label in zip(handles, labels)}
        ordered_keys = tuple(options["order"])
        missing = [raw for raw in ordered_keys if raw not in raw_to_label]
        if missing:
            raise ValueError(f"legend_options.order contains unknown series key(s): {', '.join(missing)}")
        ordered_labels = [raw_to_label[raw] for raw in ordered_keys]
        ordered_items = [label_to_items[label] for label in ordered_labels if label in label_to_items]
        ordered_label_set = set(ordered_labels)
        remaining_items = [
            (handle, label)
            for handle, label in zip(handles, labels)
            if label not in ordered_label_set
        ]
        if ordered_items:
            handles, labels = zip(*(ordered_items + remaining_items), strict=True)
            handles = list(handles)
            labels = list(labels)
    ax.legend(handles, labels, **kwargs)


def _apply_layout(fig, ax, spec: BridgeFigureSpec, *, allow_figure_layout: bool = True) -> None:
    if spec.plot_type == "facet":
        if allow_figure_layout:
            _apply_facet_headroom(fig, spec)
        return

    layout = _resolved_legend_layout(spec)
    if layout in ("right_outside", "top_outside", "standard"):
        if not allow_figure_layout:
            return
        # subplots_adjust 사용 — tight_layout과 충돌하므로 호출하지 않음
        apply_publication_layout(layout, fig=fig, target_format=spec.target_format)
        return

    if not allow_figure_layout:
        return
    legend = ax.get_legend()
    if legend is None:
        fig.tight_layout()
        return
    # smart 및 기타: tight_layout (pad=0.5로 여백 확보)
    try:
        fig.tight_layout(pad=0.5)
    except Exception:
        pass
    if layout == "smart":
        _avoid_smart_legend_data_collision(fig, ax, spec)


def _apply_facet_headroom(fig, spec: BridgeFigureSpec) -> None:
    try:
        if spec.title:
            fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.92), pad=0.5, h_pad=0.8, w_pad=0.6)
        else:
            fig.tight_layout(pad=0.5, h_pad=0.8, w_pad=0.6)
    except Exception:
        pass


def _resolved_legend_layout(spec: BridgeFigureSpec) -> str:
    if spec.legend_layout != "auto":
        return spec.legend_layout
    if spec.target_format == "ppt":
        return "right_outside"
    return "smart"  # nature/science 등 기본은 smart layout 적용
