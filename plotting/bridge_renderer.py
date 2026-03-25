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
from themes.journal_theme import (
    apply_journal_theme,
    apply_publication_layout,
    get_legend_args,
    save_journal_fig,
    set_figure_size,
)
from themes.style_profiles import get_series_style

from plotting.utils import (
    add_smart_inset,
    apply_density_alpha,
    auto_panel_tag,
    compress_sample_label,
    get_standard_legend_props,
)

from .smart_layout import add_leader_line, find_empty_quadrant, stagger_labels_2d

try:
    from hub_core.provenance import embed_provenance_fingerprint as _embed_fingerprint
except Exception:
    _embed_fingerprint = None  # type: ignore[assignment]
    warnings.warn(
        "hub_core.provenance not available; reproducibility fingerprinting disabled",
        stacklevel=1,
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
    w_mm, h_mm = _FORMAT_FIGSIZE_MM.get(target_format, (89, 71))
    return set_figure_size(w_mm, h_mm)


def draw_zenith_plot(
    ax, x, y, label=None, kind="scatter", palette="Nature Energy", series_index=0, **kwargs
):
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

    # 지능형 범례 배치 (라벨이 있는 경우)
    if label:
        quad = find_empty_quadrant(x, y)
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
    try:
        _render_plot(ax, points, spec)
        _apply_axes_metadata(ax, spec)
        ax.set_title(spec.title)
        _apply_layout(fig, ax, spec)
        save_journal_fig(fig, output_path)  # dpi comes from apply_journal_theme rcParams
    finally:
        plt.close(fig)
    if _embed_fingerprint is not None:
        _embed_fingerprint(
            str(output_path),
            {
                "generator": "Graph-Hub/bridge_renderer.py",
                "target_format": spec.target_format,
                "ts": _deterministic_timestamp(),
            },
        )
    return str(output_path)


def _load_points(csv_path: Path, spec: BridgeFigureSpec) -> list[dict]:
    points: list[dict] = []
    skipped = 0
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        required = [spec.x_column, spec.y_column]
        for col_attr in ("label_column", "series_column", "yerr_column"):
            col = getattr(spec, col_attr)
            if col:
                required.append(col)
        missing = [c for c in required if c not in headers]
        if missing:
            raise ValueError(
                f"CSV {csv_path.name} is missing column(s): {', '.join(missing)}. "
                f"Available: {', '.join(headers)}"
            )
        for row_num, row in enumerate(reader, start=2):
            try:
                y_val = float(row[spec.y_column])
                yerr_val = float(row[spec.yerr_column]) if spec.yerr_column else None
            except (ValueError, TypeError):
                skipped += 1
                continue
            if not math.isfinite(y_val) or (yerr_val is not None and not math.isfinite(yerr_val)):
                skipped += 1
                continue
            points.append(
                {
                    "x": _parse_x_value(row[spec.x_column]),
                    "y": y_val,
                    "label": row[spec.label_column] if spec.label_column else "",
                    "series": row[spec.series_column] if spec.series_column else "",
                    "yerr": yerr_val,
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
        legend_label = (
            _display_label(series_name, compress_labels=spec.compress_labels) if has_multi_series else None
        )
        sty = get_series_style(idx)

        if line:
            if yerr is not None:
                ax.errorbar(
                    xs, ys, yerr=yerr,
                    fmt=sty["marker"], linestyle=sty["linestyle"],
                    linewidth=1.2, capsize=3, label=legend_label,
                )
            else:
                ax.plot(
                    xs, ys,
                    marker=sty["marker"], linestyle=sty["linestyle"],
                    linewidth=1.2, label=legend_label,
                )
        else:
            if yerr is not None:
                ax.errorbar(
                    xs, ys, yerr=yerr,
                    fmt=sty["marker"], linestyle="none",
                    capsize=3, label=legend_label,
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
            sty = get_series_style(series_index)
            bars = ax.bar(
                xs,
                ys,
                width=width,
                yerr=yerr,
                capsize=3,
                hatch=sty["hatch"],
                edgecolor="black",
                linewidth=0.5,
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
        ax.legend(**_legend_kwargs(ax, spec, n_series=len(series_names)))
    else:
        ys = [point["y"] for point in points]
        yerr = _yerr_values(points, spec)
        bars = ax.bar(
            base_positions, ys, yerr=yerr, capsize=3,
            edgecolor="black", linewidth=0.5,
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
    if spec.plot_type == "bar":
        _render_bar_plot(ax, points, spec)
        return
    if spec.plot_type == "scatter":
        _render_xy_plot(ax, points, spec, line=False)
        return
    if spec.plot_type not in ("line", "xy"):
        warnings.warn(
            f"bridge_renderer: unknown plot_type {spec.plot_type!r}, falling back to line plot",
            stacklevel=2,
        )
    _render_xy_plot(ax, points, spec, line=True)


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
    import numpy as np

    # 1. 데이터 포인트 추출 (Axes 좌표계 0~1)
    # 현재 그려진 모든 Line2D, PathCollection(scatter)에서 데이터를 가져옴
    x_data = []
    y_data = []

    # x, y축 범위 확인
    x_lim = ax.get_xlim()
    y_lim = ax.get_ylim()

    for artist in ax.get_children():
        if hasattr(artist, "get_offsets"):  # scatter points
            offsets = artist.get_offsets()
            if len(offsets) > 0:
                x_data.extend(offsets[:, 0])
                y_data.extend(offsets[:, 1])
        elif hasattr(artist, "get_xdata"):  # lines
            x_data.extend(artist.get_xdata())
            y_data.extend(artist.get_ydata())

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


def _apply_layout(fig, ax, spec: BridgeFigureSpec) -> None:
    legend = ax.get_legend()
    if legend is None:
        fig.tight_layout()
        return

    layout = _resolved_legend_layout(spec)
    if layout in ("right_outside", "top_outside", "standard"):
        # subplots_adjust 사용 — tight_layout과 충돌하므로 호출하지 않음
        apply_publication_layout(layout)
        return
    # smart 및 기타: tight_layout만 사용
    fig.tight_layout()


def _resolved_legend_layout(spec: BridgeFigureSpec) -> str:
    if spec.legend_layout != "auto":
        return spec.legend_layout
    if spec.target_format == "ppt":
        return "right_outside"
    return "smart"  # nature/science 등 기본은 smart layout 적용
