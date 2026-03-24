"""
Reusable Graph Hub renderer for Athena bridge plots.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from themes.journal_theme import (
    apply_journal_theme,
    apply_publication_layout,
    get_legend_args,
    save_journal_fig,
    set_figure_size,
)

from plotting.utils import (
    compress_sample_label, 
    get_standard_legend_props,
    add_smart_inset, 
    auto_panel_tag, 
    apply_density_alpha
)
from .smart_layout import find_empty_quadrant, stagger_labels_2d, add_leader_line

try:
    from hub_core.provenance import embed_provenance_fingerprint as _embed_fingerprint
except Exception:
    _embed_fingerprint = None  # type: ignore[assignment]

# Journal column widths in mm; height derived at ratio 0.80.
_FORMAT_FIGSIZE_MM: dict[str, tuple[float, float]] = {
    "nature":  (89, 71),
    "science": (89, 71),
    "default": (89, 71),
    "ppt":     (152, 114),
}


def _figsize_for_format(target_format: str) -> tuple[float, float]:
    w_mm, h_mm = _FORMAT_FIGSIZE_MM.get(target_format, (89, 71))
    return set_figure_size(w_mm, h_mm)


def draw_zenith_plot(ax, x, y, label=None, kind='scatter', palette='Nature Energy', **kwargs):
    """
    최상의 품질을 보장하는 시각화 통합 래퍼입니다.
    - 자동 색상 지정 (CVD 세이프 팔레트)
    - 데이터 밀도 기반 투명도 조절
    - 자동 라벨/범례 위치 최적화
    """
    from themes.palettes import get_palette
    colors = get_palette(palette)
    
    # 데이터 밀도 기반 스타일링
    alpha, size = apply_density_alpha(len(x))
    
    # 기본 스타일 설정
    plot_kwargs = {
        'alpha': alpha,
        'label': label,
        'color': colors[0] if colors else 'blue'
    }
    plot_kwargs.update(kwargs)
    
    if kind == 'scatter':
        plot_kwargs.setdefault('s', size * 5)
        ax.scatter(x, y, **plot_kwargs)
    elif kind == 'line':
        ax.plot(x, y, **plot_kwargs)
        
    # 지능형 범례 배치 (라벨이 있는 경우)
    if label:
        quad = find_empty_quadrant(x, y)
        loc_map = {0: 'upper right', 1: 'upper left', 2: 'lower left', 3: 'lower right'}
        ax.legend(loc=loc_map[quad], frameon=False, fontsize='small')
        
    return ax

@dataclass(frozen=True)
class BridgeFigureSpec:
    csv_path: str
    output_path: str
    plot_type: str
    x_column: str
    y_column: str
    title: str
    x_axis_label: str = ""
    y_axis_label: str = ""
    label_column: str = ""
    series_column: str = ""
    yerr_column: str = ""
    compress_labels: bool = True
    legend_layout: str = "auto"
    target_format: str = "nature"
    font_scale: float = 1.0
    profile_name: str = "baseline"


def render_bridge_figure(spec: BridgeFigureSpec) -> str:
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
    _render_plot(ax, points, spec)
    _apply_axes_metadata(ax, spec)
    ax.set_title(spec.title)
    _apply_layout(fig, ax, spec)
    save_journal_fig(fig, output_path)  # dpi comes from apply_journal_theme rcParams
    plt.close(fig)
    if _embed_fingerprint is not None:
        _embed_fingerprint(
            str(output_path),
            {
                "generator": "Graph-Hub/bridge_renderer.py",
                "target_format": spec.target_format,
                "ts": datetime.utcnow().isoformat(),
            },
        )
    return str(output_path)


def _load_points(csv_path: Path, spec: BridgeFigureSpec) -> list[dict]:
    points: list[dict] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            points.append(
                {
                    "x": _parse_x_value(row[spec.x_column]),
                    "y": float(row[spec.y_column]),
                    "label": row[spec.label_column] if spec.label_column else "",
                    "series": row[spec.series_column] if spec.series_column else "",
                    "yerr": float(row[spec.yerr_column]) if spec.yerr_column else None,
                }
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


def _yerr_values(points: list[dict], spec: BridgeFigureSpec) -> list[float] | None:
    if not spec.yerr_column:
        return None
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
            )


def _render_xy_plot(ax, points: list[dict], spec: BridgeFigureSpec, *, line: bool) -> None:
    grouped = _group_points(points, spec)
    has_multi_series = any(key != "__single__" for key in grouped)

    for series_name, series_points in grouped.items():
        xs = [point["x"] for point in series_points]
        ys = [point["y"] for point in series_points]
        yerr = _yerr_values(series_points, spec)
        legend_label = (
            _display_label(series_name, compress_labels=spec.compress_labels)
            if has_multi_series
            else None
        )

        if line:
            if yerr is not None:
                ax.errorbar(xs, ys, yerr=yerr, fmt="o-", linewidth=1.2, capsize=3, label=legend_label)
            else:
                ax.plot(xs, ys, marker="o", linewidth=1.2, label=legend_label)
        else:
            if yerr is not None:
                ax.errorbar(xs, ys, yerr=yerr, fmt="o", linestyle="none", capsize=3, label=legend_label)
            else:
                ax.scatter(xs, ys, s=24, label=legend_label)

        if spec.label_column:
            _annotate_points(
                ax,
                xs,
                ys,
                [str(point["label"]) for point in series_points],
                compress_labels=spec.compress_labels,
            )

    if has_multi_series:
        ax.legend(**_legend_kwargs(spec, n_series=len(grouped)))


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
            xs = [
                category_to_position[point["x"]] + offset_start + series_index * width
                for point in series_points
            ]
            ys = [point["y"] for point in series_points]
            yerr = _yerr_values(series_points, spec)
            bars = ax.bar(
                xs,
                ys,
                width=width,
                yerr=yerr,
                capsize=3,
                label=_display_label(series_name, compress_labels=spec.compress_labels),
            )
            if spec.label_column:
                _annotate_points(
                    ax,
                    [bar.get_x() + bar.get_width() / 2 for bar in bars],
                    ys,
                    [str(point["label"]) for point in series_points],
                    compress_labels=spec.compress_labels,
                )
        ax.legend(**_legend_kwargs(spec, n_series=len(series_names)))
    else:
        ys = [point["y"] for point in points]
        yerr = _yerr_values(points, spec)
        bars = ax.bar(base_positions, ys, yerr=yerr, capsize=3)
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
    if spec.plot_type == "bar":
        _render_bar_plot(ax, points, spec)
        return
    if spec.plot_type == "scatter":
        _render_xy_plot(ax, points, spec, line=False)
        return
    _render_xy_plot(ax, points, spec, line=True)


def _display_label(value: object, *, compress_labels: bool = True) -> str:
    text = str(value)
    if not compress_labels:
        return text
    return compress_sample_label(text)


def _apply_axes_metadata(ax, spec: BridgeFigureSpec) -> None:
    ax.set_xlabel(spec.x_axis_label or spec.x_column)
    ax.set_ylabel(spec.y_axis_label or spec.y_column)


def _legend_kwargs(spec: BridgeFigureSpec, *, n_series: int) -> dict:
    layout = _resolved_legend_layout(spec)
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
    kwargs["ncol"] = min(max(n_series, 1), 2)
    return kwargs


def _apply_layout(fig, ax, spec: BridgeFigureSpec) -> None:
    legend = ax.get_legend()
    if legend is None:
        fig.tight_layout()
        return

    layout = _resolved_legend_layout(spec)
    if layout == "right_outside":
        apply_publication_layout("right_outside")
        return
    if layout == "top_outside":
        apply_publication_layout("top_outside")
        return
    if layout == "standard":
        apply_publication_layout("standard")
        return
    fig.tight_layout()


def _resolved_legend_layout(spec: BridgeFigureSpec) -> str:
    if spec.legend_layout != "auto":
        return spec.legend_layout
    if spec.target_format == "ppt":
        return "right_outside"
    return "top_outside"
