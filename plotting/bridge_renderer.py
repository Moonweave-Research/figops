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

from hub_core.rendering import PLOT_TYPES, render_plot
from plotting.axis_break import _draw_break_marks
from plotting.utils import (
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
from themes.physics_colormap import resolve_colormap
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


# Journal column widths in mm; height derived at ratio 0.80.
_FORMAT_FIGSIZE_MM: dict[str, tuple[float, float]] = {
    "nature": (89, 71),
    "science": (89, 71),
    "default": (89, 71),
    "ppt": (152, 114),
}


def _figsize_for_format(target_format: str) -> tuple[float, float]:
    w_mm, h_mm = _FORMAT_FIGSIZE_MM.get(target_format, (89, 71))
    return set_figure_size(w_mm, h_mm)


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
    yerr_column: str = ""
    yerr_cap_width: float = 3.0
    yerr_minus_column: str = ""
    compress_labels: bool = True
    legend_layout: str = "auto"
    target_format: str = "nature"
    font_scale: float = 1.0
    profile_name: str = "baseline"
    physics_type: str = ""
    overlay_baselines: tuple[dict, ...] = ()
    y_break_range: tuple[float, float] | None = None
    facet_column: str = ""


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
        fig, ax = plt.subplots(figsize=_figsize_for_format(spec.target_format))
        try:
            if spec.y_break_range is not None:
                ax.set_visible(False)
                _render_broken_axis_plot(fig, points, spec)
            else:
                _render_plot(ax, points, spec)
                _draw_overlay_baselines(ax, spec.overlay_baselines)
                _apply_axes_metadata(ax, spec)
                ax.set_title(spec.title)
                _apply_layout(fig, ax, spec)
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
        ``"single"`` (89 mm) or ``"double"`` (183 mm).
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
        output_path = Path(spec.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            save_journal_fig(fig, output_path)
        finally:
            plt.close(fig)
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
    col_mm = DOUBLE_COLUMN if spec.column_width == "double" else SINGLE_COLUMN
    fig_w_in = mm_to_inch(col_mm)
    fig_h_in = mm_to_inch(spec.panel_height_mm * spec.rows)

    fig, axes = plt.subplots(spec.rows, spec.cols, figsize=(fig_w_in, fig_h_in))
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

    if hasattr(fig, "_graph_hub_layout_lock"):
        delattr(fig, "_graph_hub_layout_lock")
    return fig


def _validated_compose_mode(spec: MultiPanelSpec) -> str:
    compose_mode = str(spec.compose_mode or "draft").strip().lower()
    if compose_mode not in {"draft", "manuscript"}:
        raise ValueError(f"unsupported compose_mode {spec.compose_mode!r}; expected 'draft' or 'manuscript'")
    if spec.rows <= 0 or spec.cols <= 0:
        raise ValueError("rows and cols must be positive integers")
    if spec.panel_height_mm <= 0:
        raise ValueError("panel_height_mm must be positive")
    if spec.gutter_h_mm < 0 or spec.gutter_v_mm < 0:
        raise ValueError("gutter_h_mm and gutter_v_mm must be non-negative")
    if compose_mode == "manuscript" and str(spec.target_format or "").lower() == "ppt":
        raise ValueError("manuscript compose is not supported for target_format='ppt'")
    return compose_mode


def _render_multipanel_manuscript(spec: MultiPanelSpec):
    fig_w_mm = DOUBLE_COLUMN if spec.column_width == "double" else SINGLE_COLUMN
    fig_h_mm = (spec.panel_height_mm * spec.rows) + (spec.gutter_v_mm * max(spec.rows - 1, 0))
    fig = plt.figure(figsize=(mm_to_inch(fig_w_mm), mm_to_inch(fig_h_mm)))
    setattr(
        fig,
        "_graph_hub_layout_lock",
        {
            "compose_mode": "manuscript",
            "figure_width_mm": float(fig_w_mm),
            "figure_height_mm": float(fig_h_mm),
        },
    )

    cell_w_mm = (fig_w_mm - (spec.gutter_h_mm * max(spec.cols - 1, 0))) / spec.cols
    cell_h_mm = spec.panel_height_mm

    for idx, panel in enumerate(spec.panels):
        if idx >= spec.rows * spec.cols:
            break
        row_idx = idx // spec.cols
        col_idx = idx % spec.cols
        axis_rect = _manuscript_axis_rect(
            panel,
            row_idx=row_idx,
            col_idx=col_idx,
            fig_w_mm=fig_w_mm,
            fig_h_mm=fig_h_mm,
            cell_w_mm=cell_w_mm,
            cell_h_mm=cell_h_mm,
            gutter_h_mm=spec.gutter_h_mm,
            gutter_v_mm=spec.gutter_v_mm,
        )
        ax = fig.add_axes(axis_rect)
        if isinstance(panel, PanelImageSpec):
            _render_image_panel(ax, panel)
        else:
            _render_csv_panel(fig, ax, panel)
        if spec.panel_labels and idx < len(_PANEL_LABELS):
            auto_panel_tag(ax, label=_PANEL_LABELS[idx])

    return fig


def _manuscript_axis_rect(
    panel: BridgeFigureSpec | PanelImageSpec,
    *,
    row_idx: int,
    col_idx: int,
    fig_w_mm: float,
    fig_h_mm: float,
    cell_w_mm: float,
    cell_h_mm: float,
    gutter_h_mm: float,
    gutter_v_mm: float,
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

    cell_left_mm = col_idx * (cell_w_mm + gutter_h_mm)
    cell_bottom_mm = fig_h_mm - ((row_idx + 1) * cell_h_mm) - (row_idx * gutter_v_mm)

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
    _render_plot(ax, points, panel)
    _draw_overlay_baselines(ax, panel.overlay_baselines)
    _apply_axes_metadata(ax, panel)
    if panel.title:
        ax.set_title(panel.title)
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


def _group_points(points: list[dict], spec: BridgeFigureSpec) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for point in points:
        key = point["series"] if spec.series_column and point["series"] else "__single__"
        grouped.setdefault(str(key), []).append(point)
    return grouped


def _yerr_values(points: list[dict], spec: BridgeFigureSpec):
    if not spec.yerr_column and not spec.yerr_minus_column:
        return None
    if spec.yerr_minus_column:
        import numpy as np

        minus = [float(point["yerr_minus"]) for point in points]
        # When only the lower (minus) column is configured, mirror it onto the upper
        # bound so the configured error data is never silently dropped (symmetric from
        # the minus values). With both columns present, use them as asymmetric bounds.
        plus = [float(point["yerr"]) for point in points] if spec.yerr_column else minus
        return np.array([minus, plus])
    return [float(point["yerr"]) for point in points]


def _annotate_points(
    ax,
    xs: list[float],
    ys: list[float],
    labels: list[str],
    *,
    compress_labels: bool,
) -> None:
    for x, y, label in zip(xs, ys, labels):
        if label:
            ax.annotate(
                _display_label(label, compress_labels=compress_labels),
                (x, y),
                textcoords="offset points",
                xytext=(0, 4),
                ha="center",
                va="bottom",
                zorder=5,
            )


def _render_xy_plot(ax, points: list[dict], spec: BridgeFigureSpec, *, line: bool) -> None:
    grouped = _group_points(points, spec)
    has_multi_series = any(key != "__single__" for key in grouped)

    for idx, (series_name, series_points) in enumerate(grouped.items()):
        xs = [point["x"] for point in series_points]
        ys = [point["y"] for point in series_points]
        yerr = _yerr_values(series_points, spec)
        legend_label = _display_label(series_name, compress_labels=spec.compress_labels) if has_multi_series else None
        sty = get_series_style(idx)

        cap_size = spec.yerr_cap_width
        cap_thick = max(0.5, spec.yerr_cap_width * 0.4)
        if line:
            if yerr is not None:
                ax.errorbar(
                    xs,
                    ys,
                    yerr=yerr,
                    fmt=sty["marker"],
                    linestyle=sty["linestyle"],
                    linewidth=1.2,
                    capsize=cap_size,
                    capthick=cap_thick,
                    label=legend_label,
                )
            else:
                ax.plot(
                    xs,
                    ys,
                    marker=sty["marker"],
                    linestyle=sty["linestyle"],
                    linewidth=1.2,
                    label=legend_label,
                )
        else:
            if yerr is not None:
                ax.errorbar(
                    xs,
                    ys,
                    yerr=yerr,
                    fmt=sty["marker"],
                    linestyle="none",
                    capsize=cap_size,
                    capthick=cap_thick,
                    label=legend_label,
                )
            else:
                ax.scatter(xs, ys, s=24, marker=sty["marker"], label=legend_label)

        if spec.label_column:
            _annotate_points(
                ax,
                xs,
                ys,
                [str(point["label"]) for point in series_points],
                compress_labels=spec.compress_labels,
            )

    if has_multi_series:
        ax.legend(**_legend_kwargs(ax, spec, n_series=len(grouped)))


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


def _make_broken_y_axes(fig, points: list[dict], break_range: tuple[float, float] | None):
    if break_range is None:
        raise ValueError("y_break_range is required for broken-axis rendering")
    left, bottom, width, height = [0.125, 0.11, 0.775, 0.77]
    gap_fraction = 0.02
    top_h = height * 0.5 - gap_fraction / 2
    bot_h = height * 0.5 - gap_fraction / 2
    ax_top = fig.add_axes([left, bottom + bot_h + gap_fraction, width, top_h])
    ax_bot = fig.add_axes([left, bottom, width, bot_h], sharex=ax_top)

    break_start, break_end = break_range
    ys = [float(point["y"]) for point in points]
    y_max = max(ys) if ys else break_end
    y_min = min(ys) if ys else break_start
    full_range = max(y_max - y_min, abs(break_end - break_start), 1e-6)
    margin = full_range * 0.05

    ax_top.set_ylim(break_end - margin, y_max + margin)
    ax_bot.set_ylim(y_min - margin, break_start + margin)
    ax_top.spines["bottom"].set_visible(False)
    ax_bot.spines["top"].set_visible(False)
    ax_top.tick_params(labelbottom=False, bottom=False)
    ax_bot.tick_params(top=False)
    _draw_break_marks(ax_top, ax_bot, style="diagonal")
    return ax_top, ax_bot


def _draw_grouped_broken_xy(ax_top, ax_bot, points: list[dict], spec: BridgeFigureSpec, *, line: bool) -> None:
    grouped = _group_points(points, spec)
    has_multi_series = any(key != "__single__" for key in grouped)

    for idx, (series_name, series_points) in enumerate(grouped.items()):
        xs = [point["x"] for point in series_points]
        ys = [point["y"] for point in series_points]
        yerr = _yerr_values(series_points, spec)
        legend_label = _display_label(series_name, compress_labels=spec.compress_labels) if has_multi_series else None
        sty = get_series_style(idx)

        _draw_broken_xy_series(
            ax_top,
            xs,
            ys,
            yerr,
            sty,
            label=legend_label,
            spec=spec,
            line=line,
        )
        _draw_broken_xy_series(
            ax_bot,
            xs,
            ys,
            yerr,
            sty,
            label="_nolegend_",
            spec=spec,
            line=line,
        )

        if spec.label_column:
            _annotate_broken_axis_points(ax_top, ax_bot, series_points, spec)

    if has_multi_series:
        ax_top.legend(**_legend_kwargs(ax_top, spec, n_series=len(grouped)))


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
    cap_size = spec.yerr_cap_width
    cap_thick = max(0.5, spec.yerr_cap_width * 0.4)
    if line:
        if yerr is not None:
            ax.errorbar(
                xs,
                ys,
                yerr=yerr,
                fmt=sty["marker"],
                linestyle=sty["linestyle"],
                linewidth=1.2,
                capsize=cap_size,
                capthick=cap_thick,
                label=label,
            )
        else:
            ax.plot(
                xs,
                ys,
                marker=sty["marker"],
                linestyle=sty["linestyle"],
                linewidth=1.2,
                label=label,
            )
    elif yerr is not None:
        ax.errorbar(
            xs,
            ys,
            yerr=yerr,
            fmt=sty["marker"],
            linestyle="none",
            capsize=cap_size,
            capthick=cap_thick,
            label=label,
        )
    else:
        ax.scatter(xs, ys, s=24, marker=sty["marker"], label=label)


def _annotate_broken_axis_points(ax_top, ax_bot, series_points: list[dict], spec: BridgeFigureSpec) -> None:
    break_start, break_end = spec.y_break_range or (float("-inf"), float("inf"))
    top_points = [point for point in series_points if float(point["y"]) >= break_end]
    bot_points = [point for point in series_points if float(point["y"]) <= break_start]
    middle_points = [point for point in series_points if break_start < float(point["y"]) < break_end]

    if top_points:
        _annotate_points(
            ax_top,
            [point["x"] for point in top_points],
            [point["y"] for point in top_points],
            [str(point["label"]) for point in top_points],
            compress_labels=spec.compress_labels,
        )
    if bot_points:
        _annotate_points(
            ax_bot,
            [point["x"] for point in bot_points],
            [point["y"] for point in bot_points],
            [str(point["label"]) for point in bot_points],
            compress_labels=spec.compress_labels,
        )
    for point in middle_points:
        target = ax_top if abs(float(point["y"]) - break_end) < abs(float(point["y"]) - break_start) else ax_bot
        _annotate_points(
            target,
            [point["x"]],
            [point["y"]],
            [str(point["label"])],
            compress_labels=spec.compress_labels,
        )


def _render_heatmap_plot(ax, points: list[dict], spec: BridgeFigureSpec) -> None:
    xs = sorted({point["x"] for point in points})
    ys = sorted({point["y"] for point in points})
    x_index = {value: column for column, value in enumerate(xs)}
    y_index = {value: row for row, value in enumerate(ys)}
    grid = np.full((len(ys), len(xs)), np.nan)
    duplicate_cells = 0
    for point in points:
        row = y_index[point["y"]]
        column = x_index[point["x"]]
        if not math.isnan(grid[row, column]):
            duplicate_cells += 1
        grid[row, column] = point["z"]
    if duplicate_cells:
        warnings.warn(
            f"bridge_renderer: {duplicate_cells} duplicate (x,y) heatmap cell(s) overwritten (last value wins)",
            stacklevel=2,
        )

    cmap = resolve_colormap(spec.physics_type)
    mesh = ax.pcolormesh(xs, ys, grid, cmap=cmap, shading="auto")
    colorbar = ax.figure.colorbar(mesh, ax=ax)
    colorbar.ax._graph_hub_role = "colorbar"  # positive tag for geometry-diagnostics classification
    colorbar.set_label(spec.z_column)


def _render_facet_plot(ax, points: list[dict], spec: BridgeFigureSpec) -> None:
    if not spec.facet_column:
        raise ValueError("facet plot_type requires facet_column")
    if not points:
        warnings.warn(
            f"bridge_renderer: no valid data points for {spec.title!r}, figure will be blank",
            stacklevel=2,
        )
        return

    fig = ax.figure
    ax.set_visible(False)
    grouped = _group_facet_points(points)
    n_facets = len(grouped)
    n_cols = min(3, max(1, math.ceil(math.sqrt(n_facets))))
    n_rows = math.ceil(n_facets / n_cols)
    shared_x = None
    shared_y = None

    for idx, (facet_name, facet_points) in enumerate(grouped.items()):
        row_idx = idx // n_cols
        col_idx = idx % n_cols
        facet_ax = fig.add_subplot(n_rows, n_cols, idx + 1, sharex=shared_x, sharey=shared_y)
        if shared_x is None:
            shared_x = facet_ax
            shared_y = facet_ax
        _render_xy_plot(facet_ax, facet_points, spec, line=True)
        facet_ax.set_title(_display_label(facet_name, compress_labels=spec.compress_labels))
        if row_idx == n_rows - 1:
            facet_ax.set_xlabel(spec.x_axis_label or spec.x_column)
        else:
            facet_ax.set_xlabel("")
            facet_ax.tick_params(labelbottom=False)
        if col_idx == 0:
            facet_ax.set_ylabel(spec.y_axis_label or spec.y_column)
        else:
            facet_ax.set_ylabel("")
        if facet_ax.get_legend() is not None:
            facet_ax.get_legend().remove()

    if spec.title:
        fig.suptitle(spec.title)


def _group_facet_points(points: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for point in points:
        key = str(point.get("facet") or "")
        grouped.setdefault(key, []).append(point)
    return grouped


def _render_box_plot(ax, points: list[dict], spec: BridgeFigureSpec) -> None:
    from plotting.common_plots import plot_box_with_points

    plot_box_with_points(_points_to_distribution_frame(points, spec), spec.x_column, spec.y_column, ax=ax)


def _render_violin_plot(ax, points: list[dict], spec: BridgeFigureSpec) -> None:
    from plotting.common_plots import plot_violin_with_points

    plot_violin_with_points(_points_to_distribution_frame(points, spec), spec.x_column, spec.y_column, ax=ax)


def _points_to_distribution_frame(points: list[dict], spec: BridgeFigureSpec):
    import pandas as pd

    return pd.DataFrame(
        {
            spec.x_column: [point["x"] for point in points],
            spec.y_column: [point["y"] for point in points],
        }
    )


def _render_bar_plot(ax, points: list[dict], spec: BridgeFigureSpec) -> None:
    grouped = _group_points(points, spec)
    has_multi_series = any(key != "__single__" for key in grouped)
    categories: list[float | str] = []
    for point in points:
        if point["x"] not in categories:
            categories.append(point["x"])

    base_positions = list(range(len(categories)))
    category_to_position = {category: index for index, category in enumerate(categories)}

    if has_multi_series:
        series_names = list(grouped.keys())
        width = 0.8 / max(len(series_names), 1)
        offset_start = -0.4 + width / 2
        for series_index, series_name in enumerate(series_names):
            series_points = grouped[series_name]
            xs = [category_to_position[point["x"]] + offset_start + series_index * width for point in series_points]
            ys = [point["y"] for point in series_points]
            yerr = _yerr_values(series_points, spec)
            sty = get_series_style(series_index)
            bars = ax.bar(
                xs,
                ys,
                width=width,
                yerr=yerr,
                capsize=spec.yerr_cap_width,
                hatch=sty["hatch"],
                edgecolor="black",
                linewidth=0.5,
                label=_display_label(series_name, compress_labels=spec.compress_labels),
            )
            if spec.label_column:
                y_offset = max(abs(v) for v in ys) * 0.03 if ys else 0
                _annotate_points(
                    ax,
                    [bar.get_x() + bar.get_width() / 2 for bar in bars],
                    [y + y_offset for y in ys],
                    [str(point["label"]) for point in series_points],
                    compress_labels=spec.compress_labels,
                )
        ax.legend(**_legend_kwargs(ax, spec, n_series=len(series_names)))
    else:
        if len(points) > len(categories):
            # Duplicate categories overplot bars at the same x (last visually wins).
            # Surface it rather than silently aggregating, which could mask intent.
            warnings.warn(
                f"bridge_renderer: single-series bar has {len(points) - len(categories)} "
                "duplicate category value(s); bars overplot at the same x position",
                stacklevel=2,
            )
        row_positions = [category_to_position[point["x"]] for point in points]
        ys = [point["y"] for point in points]
        yerr = _yerr_values(points, spec)
        bars = ax.bar(
            row_positions,
            ys,
            yerr=yerr,
            capsize=spec.yerr_cap_width,
            edgecolor="black",
            linewidth=0.5,
        )
        if spec.label_column:
            _annotate_points(
                ax,
                [bar.get_x() + bar.get_width() / 2 for bar in bars],
                ys,
                [str(point["label"]) for point in points],
                compress_labels=spec.compress_labels,
            )

    ax.set_xticks(base_positions)
    tick_labels = [_display_label(category, compress_labels=spec.compress_labels) for category in categories]
    ax.set_xticklabels(tick_labels)
    if any(len(label) > 14 for label in tick_labels):
        for label in ax.get_xticklabels():
            label.set_rotation(20)
            label.set_ha("right")


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


def _apply_layout(fig, ax, spec: BridgeFigureSpec, *, allow_figure_layout: bool = True) -> None:
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


def _resolved_legend_layout(spec: BridgeFigureSpec) -> str:
    if spec.legend_layout != "auto":
        return spec.legend_layout
    if spec.target_format == "ppt":
        return "right_outside"
    return "smart"  # nature/science 등 기본은 smart layout 적용
