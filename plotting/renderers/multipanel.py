"""Multi-panel figure specifications and composition orchestration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg


@dataclass(frozen=True)
class PanelImageSpec:
    """Existing rendered figure file to embed as a panel."""

    image_path: str
    title: str = ""


@dataclass(frozen=True)
class MultiPanelSpec:
    """Specification for a publication-style multi-panel composite figure.

    Panels are filled left-to-right and top-to-bottom. ``draft`` composition
    uses subplot auto-fitting, while ``manuscript`` preserves fixed plot boxes
    within slots sized by the declared physical gutters and layout ratios.
    """

    panels: tuple[Any, ...]
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


@dataclass(frozen=True)
class MultipanelRendererContext:
    """Facade-owned collaborators used by multi-panel composition."""

    deterministic_timestamp: Callable[[], str]
    apply_journal_theme: Callable[..., Any]
    column_width_mm: Callable[..., float]
    mm_to_inch: Callable[[float], float]
    render_csv_panel: Callable[..., None]
    apply_shared_legend: Callable[..., None]
    auto_panel_tag: Callable[..., Any]
    normalized_shared_legend_options: Callable[..., dict[str, Any]]
    validated_layout_ratios: Callable[..., None]
    distributed_lengths_mm: Callable[..., tuple[float, ...]]
    manuscript_axis_rect: Callable[..., list[float]]
    save_journal_fig: Callable[..., Any]
    embed_fingerprint: Callable[..., Any] | None


_PANEL_LABELS = tuple("abcdefghijklmnopqrstuvwxyz")


def render_multipanel_figure(spec: MultiPanelSpec, context: MultipanelRendererContext) -> str:
    """Compose multiple panels into a single publication figure."""
    fingerprint_timestamp = context.deterministic_timestamp()
    saved_rc = plt.rcParams.copy()
    try:
        compose_mode = validated_compose_mode(spec, context)
        context.apply_journal_theme(
            target_format=spec.target_format,
            font_scale=spec.font_scale,
            profile_name=spec.profile_name,
        )
        if compose_mode == "manuscript":
            fig = render_multipanel_manuscript(spec, context)
        else:
            fig = render_multipanel_draft(spec, context)
        FigureCanvasAgg(fig)
        output_path = Path(spec.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            context.save_journal_fig(fig, output_path)
        finally:
            plt.close(fig)
            FigureCanvasAgg(fig)
    finally:
        plt.rcParams.update(saved_rc)

    if context.embed_fingerprint is not None:
        context.embed_fingerprint(
            str(output_path),
            {
                "generator": "Graph-Hub/bridge_renderer.py::render_multipanel_figure",
                "rows": spec.rows,
                "cols": spec.cols,
                "n_panels": len(spec.panels),
                "ts": fingerprint_timestamp,
            },
        )
    return str(output_path)


def render_multipanel_draft(spec: MultiPanelSpec, context: MultipanelRendererContext):
    col_mm = context.column_width_mm(spec.target_format, spec.column_width, spec.profile_name)
    fig_w_in = context.mm_to_inch(col_mm)
    fig_h_in = context.mm_to_inch(spec.panel_height_mm * spec.rows)

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
            render_image_panel(ax, panel)
        else:
            context.render_csv_panel(fig, ax, panel)
        if spec.panel_labels and idx < len(_PANEL_LABELS):
            context.auto_panel_tag(ax, label=_PANEL_LABELS[idx])

    context.apply_shared_legend(fig, spec)
    if hasattr(fig, "_graph_hub_layout_lock"):
        delattr(fig, "_graph_hub_layout_lock")
    return fig


def validated_compose_mode(spec: MultiPanelSpec, context: MultipanelRendererContext) -> str:
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
    context.validated_layout_ratios(spec.width_ratios, expected_len=spec.cols, field_name="width_ratios")
    context.validated_layout_ratios(spec.height_ratios, expected_len=spec.rows, field_name="height_ratios")
    shared_legend_options = context.normalized_shared_legend_options(spec)
    if shared_legend_options and not spec.shared_legend:
        raise ValueError("shared_legend_options requires shared_legend=True")
    if compose_mode == "manuscript" and str(spec.target_format or "").lower() == "ppt":
        raise ValueError("manuscript compose is not supported for target_format='ppt'")
    return compose_mode


def render_multipanel_manuscript(spec: MultiPanelSpec, context: MultipanelRendererContext):
    panel_area_w_mm = context.column_width_mm(spec.target_format, spec.column_width, spec.profile_name)
    panel_area_h_mm = (spec.panel_height_mm * spec.rows) + (spec.gutter_v_mm * max(spec.rows - 1, 0))
    shared_legend_options = context.normalized_shared_legend_options(spec) if spec.shared_legend else {}
    shared_legend_position = str(shared_legend_options.get("position") or "top") if spec.shared_legend else ""
    legend_extra_h_mm = 12.0 if shared_legend_position in {"top", "bottom"} else 0.0
    legend_extra_w_mm = 30.0 if shared_legend_position == "right" else 0.0
    panel_area_bottom_mm = legend_extra_h_mm if shared_legend_position == "bottom" else 0.0
    fig_w_mm = panel_area_w_mm + legend_extra_w_mm
    fig_h_mm = panel_area_h_mm + legend_extra_h_mm
    fig = plt.figure(figsize=(context.mm_to_inch(fig_w_mm), context.mm_to_inch(fig_h_mm)))
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

    col_widths_mm = context.distributed_lengths_mm(
        panel_area_w_mm - (spec.gutter_h_mm * max(spec.cols - 1, 0)),
        spec.cols,
        spec.width_ratios,
    )
    row_heights_mm = context.distributed_lengths_mm(
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
        ax = fig.add_axes(
            context.manuscript_axis_rect(
                panel,
                fig_w_mm=fig_w_mm,
                fig_h_mm=fig_h_mm,
                cell_left_mm=cell_left_mm,
                cell_bottom_mm=cell_bottom_mm,
                cell_w_mm=cell_w_mm,
                cell_h_mm=cell_h_mm,
            )
        )
        if isinstance(panel, PanelImageSpec):
            render_image_panel(ax, panel)
        else:
            context.render_csv_panel(fig, ax, panel)
        if spec.panel_labels and idx < len(_PANEL_LABELS):
            context.auto_panel_tag(ax, label=_PANEL_LABELS[idx])

    context.apply_shared_legend(fig, spec)
    return fig


def render_image_panel(ax, panel: PanelImageSpec) -> None:
    """Load an existing image file and display it inside *ax*."""
    try:
        from PIL import Image

        with Image.open(panel.image_path) as img:
            img_arr = np.asarray(img)
    except ImportError:
        img_arr = plt.imread(panel.image_path)
    ax.imshow(img_arr)
    ax.set_axis_off()
    if panel.title:
        ax.set_title(panel.title)
