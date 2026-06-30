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
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg

from hub_core.rendering import PLOT_TYPES, render_plot
from plotting.axis_break import _draw_break_marks
from plotting.renderers.axes import apply_axis_limits as _apply_axis_limits  # noqa: F401
from plotting.renderers.axes import apply_axis_limits_to_visible_axes as _apply_axis_limits_to_visible_axes
from plotting.renderers.axes import apply_axis_scales as _apply_axis_scales  # noqa: F401
from plotting.renderers.axes import apply_axis_scales_to_visible_axes as _apply_axis_scales_to_visible_axes
from plotting.renderers.axes import apply_tick_label_char_limit as _apply_tick_label_char_limit  # noqa: F401
from plotting.renderers.axes import apply_tick_style as _apply_tick_style  # noqa: F401
from plotting.renderers.axes import apply_tick_style_to_visible_axes as _apply_tick_style_to_visible_axes
from plotting.renderers.axes import axis_is_numeric as _axis_is_numeric  # noqa: F401
from plotting.renderers.axes import normalized_axis_limit_pair as _normalized_axis_limit_pair  # noqa: F401
from plotting.renderers.axes import normalized_axis_limits as _normalized_axis_limits  # noqa: F401
from plotting.renderers.axes import normalized_axis_scale as _normalized_axis_scale  # noqa: F401
from plotting.renderers.axes import normalized_tick_style as _normalized_tick_style
from plotting.renderers.axes import truncate_tick_label as _truncate_tick_label  # noqa: F401
from plotting.renderers.axes import validate_axis_limits as _validate_axis_limits
from plotting.renderers.axes import validate_axis_scales as _validate_axis_scales
from plotting.renderers.axes import visible_plot_axes as _visible_plot_axes  # noqa: F401
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
from plotting.renderers.figure_style import apply_marker_axis_margin as _apply_marker_axis_margin
from plotting.renderers.figure_style import column_width_mm as _column_width_mm
from plotting.renderers.figure_style import figsize_for_format as _figsize_for_format
from plotting.renderers.figure_style import marker_tokens as _marker_tokens
from plotting.renderers.figure_style import scatter_marker_area as _scatter_marker_area
from plotting.renderers.heatmap import render_heatmap_plot as _render_heatmap_plot  # noqa: F401
from plotting.renderers.labels import annotate_points as _annotate_points  # noqa: F401
from plotting.renderers.labels import display_label as _display_label  # noqa: F401
from plotting.renderers.labels import draw_point_label as _draw_point_label  # noqa: F401
from plotting.renderers.labels import normalized_point_label_options_dict as _normalized_point_label_options_dict
from plotting.renderers.labels import point_label_candidates as _point_label_candidates  # noqa: F401
from plotting.renderers.labels import point_label_xytext as _point_label_xytext  # noqa: F401
from plotting.renderers.labels import record_point_label_skips as _record_point_label_skips  # noqa: F401
from plotting.renderers.labels import truthy_label_skip as _truthy_label_skip  # noqa: F401
from plotting.renderers.legend import apply_legend as _apply_legend
from plotting.renderers.legend import avoid_smart_legend_data_collision as _avoid_smart_legend_data_collision
from plotting.renderers.legend import find_best_legend_location as _find_best_legend_location  # noqa: F401
from plotting.renderers.legend import legend_data_overlap_fraction as _legend_data_overlap_fraction  # noqa: F401
from plotting.renderers.legend import legend_inside_axes as _legend_inside_axes  # noqa: F401
from plotting.renderers.legend import legend_kwargs as _legend_kwargs  # noqa: F401
from plotting.renderers.legend import normalized_legend_options as _normalized_legend_options
from plotting.renderers.legend import replace_legend as _replace_legend  # noqa: F401
from plotting.renderers.legend import resolved_legend_layout as _resolved_legend_layout
from plotting.renderers.legend import separate_top_legend_title as _separate_top_legend_title
from plotting.renderers.multipanel_layout import distributed_lengths_mm as _distributed_lengths_mm
from plotting.renderers.multipanel_layout import manuscript_axis_rect as _manuscript_axis_rect_impl
from plotting.renderers.multipanel_layout import panel_geometry_mm as _panel_geometry_mm_impl
from plotting.renderers.multipanel_layout import split_bias as _split_bias  # noqa: F401
from plotting.renderers.multipanel_layout import validated_layout_ratios as _validated_layout_ratios
from plotting.renderers.overlays import annotation_font_size as _annotation_font_size  # noqa: F401
from plotting.renderers.overlays import draw_annotations as _draw_annotations
from plotting.renderers.overlays import draw_annotations_on_visible_axes as _draw_annotations_on_visible_axes
from plotting.renderers.overlays import draw_linear_fit_overlay as _draw_linear_fit_overlay  # noqa: F401
from plotting.renderers.overlays import draw_manual_overlays as _draw_manual_overlays
from plotting.renderers.overlays import draw_statistical_overlays as _draw_statistical_overlays
from plotting.renderers.overlays import fill_between_arrays as _fill_between_arrays  # noqa: F401
from plotting.renderers.overlays import finite_float as _finite_float  # noqa: F401
from plotting.renderers.overlays import normalized_annotations as _normalized_annotations
from plotting.renderers.overlays import normalized_callout_offset as _normalized_callout_offset  # noqa: F401
from plotting.renderers.overlays import (
    normalized_significance_markers as _normalized_significance_markers,  # noqa: F401
)
from plotting.renderers.overlays import normalized_span_annotation as _normalized_span_annotation  # noqa: F401
from plotting.renderers.overlays import numeric_xy_arrays as _numeric_xy_arrays  # noqa: F401
from plotting.renderers.overlays import overlay_line_kwargs as _overlay_line_kwargs  # noqa: F401
from plotting.renderers.overlays import overlay_xy_arrays as _overlay_xy_arrays  # noqa: F401
from plotting.renderers.overlays import (
    reject_non_point_callout_fields as _reject_non_point_callout_fields,  # noqa: F401
)
from plotting.renderers.overlays import span_midpoint as _span_midpoint  # noqa: F401
from plotting.renderers.overlays import t_critical_95 as _t_critical_95  # noqa: F401
from plotting.renderers.overlays import tag_annotation_text as _tag_annotation_text  # noqa: F401
from plotting.renderers.overlays import tag_overlay_artist as _tag_overlay_artist  # noqa: F401
from plotting.renderers.overlays import validate_manual_overlays as _validate_manual_overlays
from plotting.renderers.overlays import validate_statistical_overlays as _validate_statistical_overlays
from plotting.renderers.shared_legend import apply_shared_legend as _apply_shared_legend
from plotting.renderers.shared_legend import normalized_shared_legend_options as _normalized_shared_legend_options
from plotting.renderers.xy import XYRendererContext
from plotting.renderers.xy import line_marker_color_kwargs as _line_marker_color_kwargs  # noqa: F401
from plotting.renderers.xy import marker_color_kwargs as _marker_color_kwargs  # noqa: F401
from plotting.renderers.xy import render_xy_plot as _render_xy_plot_impl
from plotting.utils import (
    apply_density_alpha,
    auto_panel_tag,
)
from themes.journal_theme import (
    PUBLICATION_LAYOUT_SPECS_MM,
    apply_journal_theme,
    apply_publication_layout,
    mm_to_inch,
    save_journal_fig,
)
from themes.style_profiles import get_series_style

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


def _deterministic_timestamp() -> str:
    """Return SOURCE_DATE_EPOCH if set, else current UTC time."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is not None:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
    return datetime.now(tz=timezone.utc).isoformat()


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
    return _manuscript_axis_rect_impl(
        panel,
        fig_w_mm=fig_w_mm,
        fig_h_mm=fig_h_mm,
        cell_left_mm=cell_left_mm,
        cell_bottom_mm=cell_bottom_mm,
        cell_w_mm=cell_w_mm,
        cell_h_mm=cell_h_mm,
        panel_image_type=PanelImageSpec,
        publication_layout_specs_mm=PUBLICATION_LAYOUT_SPECS_MM,
        resolved_legend_layout=_resolved_legend_layout,
    )


def _panel_geometry_mm(panel: BridgeFigureSpec | PanelImageSpec) -> tuple[float, float, dict[str, float]]:
    return _panel_geometry_mm_impl(
        panel,
        panel_image_type=PanelImageSpec,
        publication_layout_specs_mm=PUBLICATION_LAYOUT_SPECS_MM,
        resolved_legend_layout=_resolved_legend_layout,
    )


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


def _normalized_point_label_options(spec: BridgeFigureSpec) -> dict[str, object]:
    return _normalized_point_label_options_dict(spec.point_label_options)
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


def _apply_axes_metadata(ax, spec: BridgeFigureSpec) -> None:
    ax.set_xlabel(spec.x_axis_label or spec.x_column)
    ax.set_ylabel(spec.y_axis_label or spec.y_column)


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
