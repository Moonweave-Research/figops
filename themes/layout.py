"""Publication layout helpers for journal-quality figures."""

from __future__ import annotations

import copy

import matplotlib.pyplot as plt

_LAYOUT_LOCK_ATTR = "_graph_hub_layout_lock"

_PUBLICATION_LAYOUT_SPECS_MM = {
    "standard": {
        "box_width_mm": 70.0,
        "box_height_mm": 55.0,
        "margins_mm": {"left": 14.0, "right": 5.0, "bottom": 12.0, "top": 8.0},
    },
    "top_outside": {
        "box_width_mm": 70.0,
        "box_height_mm": 55.0,
        "margins_mm": {"left": 14.0, "right": 5.0, "bottom": 12.0, "top": 20.0},
    },
    # PPT/default right-side legend keeps the older ratio workflow unless an
    # explicit absolute-mm box is requested by the caller.
    "right_outside": {
        "box_width_mm": 70.0,
        "box_height_mm": 55.0,
        "margins_mm": {"left": 14.0, "right": 18.0, "bottom": 12.0, "top": 8.0},
    },
    # Internal project preset: square 50x50 mm plot box for standalone panels.
    "surfur_square": {
        "box_width_mm": 50.0,
        "box_height_mm": 50.0,
        "margins_mm": {"left": 12.0, "right": 4.0, "bottom": 10.0, "top": 6.0},
    },
}
PUBLICATION_LAYOUT_SPECS_MM = copy.deepcopy(_PUBLICATION_LAYOUT_SPECS_MM)

_LEGACY_LAYOUT_RATIOS = {
    "top_outside": {"left": 0.18, "right": 0.95, "bottom": 0.22, "top": 0.76},
    "right_outside": {"left": 0.15, "right": 0.75, "bottom": 0.18, "top": 0.92},
    "standard": {"left": 0.15, "right": 0.95, "bottom": 0.15, "top": 0.90},
}


def _mm_to_inch(mm: float) -> float:
    return mm / 25.4


def _figure_size_mm(fig):
    width_in, height_in = fig.get_size_inches()
    return width_in * 25.4, height_in * 25.4


def _lock_publication_layout(fig, *, layout_type, target_format, box_width_mm, box_height_mm, margins_mm):
    setattr(
        fig,
        _LAYOUT_LOCK_ATTR,
        {
            "layout_type": layout_type,
            "target_format": target_format,
            "box_width_mm": float(box_width_mm),
            "box_height_mm": float(box_height_mm),
            "margins_mm": {k: float(v) for k, v in margins_mm.items()},
        },
    )


def _apply_legacy_publication_layout(fig, layout_type):
    ratios = _LEGACY_LAYOUT_RATIOS.get(layout_type, _LEGACY_LAYOUT_RATIOS["standard"])
    fig.subplots_adjust(**ratios)
    if hasattr(fig, _LAYOUT_LOCK_ATTR):
        delattr(fig, _LAYOUT_LOCK_ATTR)
    return ratios


# Multi-panel grid specs (unified source, 2026-04-10). Project-specific
# exceptions should be explicit call-site kwargs, not hidden project overrides.
MULTI_PANEL_GRID_SPECS_MM: dict[str, dict[str, float]] = {
    "triplet": {
        "box_width_mm": 44.0,
        "box_height_mm": 44.0,
        "left_mm": 12.0,
        "right_mm": 6.0,
        "bottom_mm": 12.0,
        "top_mm": 8.0,
        "wspace_mm": 14.0,
        "hspace_mm": 10.0,
    },
    "pair": {
        "box_width_mm": 72.0,
        "box_height_mm": 72.0,
        "left_mm": 12.0,
        "right_mm": 6.0,
        "bottom_mm": 12.0,
        "top_mm": 8.0,
        "wspace_mm": 14.0,
        "hspace_mm": 10.0,
    },
    "quad": {
        "box_width_mm": 70.0,
        "box_height_mm": 70.0,
        "left_mm": 12.0,
        "right_mm": 9.0,
        "bottom_mm": 12.0,
        "top_mm": 8.0,
        "wspace_mm": 14.0,
        "hspace_mm": 10.0,
    },
    "triplet_cell": {
        "box_width_mm": 44.0,
        "box_height_mm": 44.0,
        "left_mm": 10.0,
        "right_mm": 5.0,
        "bottom_mm": 12.0,
        "top_mm": 8.0,
        "wspace_mm": 0.0,
        "hspace_mm": 0.0,
    },
    "solo": {
        "box_width_mm": 70.0,
        "box_height_mm": 55.0,
        "left_mm": 14.0,
        "right_mm": 6.0,
        "bottom_mm": 14.0,
        "top_mm": 8.0,
        "wspace_mm": 0.0,
        "hspace_mm": 0.0,
    },
}


def apply_panel_grid_layout(
    fig,
    *,
    nrows: int,
    ncols: int,
    layout_type: str,
    box_width_mm: float | None = None,
    box_height_mm: float | None = None,
    **overrides,
) -> dict[str, float]:
    """Set deterministic multi-panel layout with absolute mm dimensions."""
    if layout_type not in MULTI_PANEL_GRID_SPECS_MM:
        raise KeyError(f"Unknown layout_type {layout_type!r}. Available: {sorted(MULTI_PANEL_GRID_SPECS_MM)}")
    spec = dict(MULTI_PANEL_GRID_SPECS_MM[layout_type])
    if box_width_mm is not None:
        spec["box_width_mm"] = float(box_width_mm)
    if box_height_mm is not None:
        spec["box_height_mm"] = float(box_height_mm)
    for key, value in overrides.items():
        if key in spec:
            spec[key] = float(value)

    figure_width_mm = (
        spec["left_mm"] + spec["right_mm"] + ncols * spec["box_width_mm"] + max(ncols - 1, 0) * spec["wspace_mm"]
    )
    figure_height_mm = (
        spec["bottom_mm"] + spec["top_mm"] + nrows * spec["box_height_mm"] + max(nrows - 1, 0) * spec["hspace_mm"]
    )

    fig.set_size_inches(figure_width_mm / 25.4, figure_height_mm / 25.4, forward=True)
    fig.subplots_adjust(
        left=spec["left_mm"] / figure_width_mm,
        right=1.0 - (spec["right_mm"] / figure_width_mm),
        bottom=spec["bottom_mm"] / figure_height_mm,
        top=1.0 - (spec["top_mm"] / figure_height_mm),
        wspace=(spec["wspace_mm"] / spec["box_width_mm"]) if ncols > 1 else 0.0,
        hspace=(spec["hspace_mm"] / spec["box_height_mm"]) if nrows > 1 else 0.0,
    )
    return {
        "figure_width_mm": figure_width_mm,
        "figure_height_mm": figure_height_mm,
        "box_width_mm": spec["box_width_mm"],
        "box_height_mm": spec["box_height_mm"],
    }


def apply_publication_layout(
    layout_type="top_outside",
    *,
    fig=None,
    target_format="nature",
    box_width_mm=None,
    box_height_mm=None,
    margins_mm=None,
    resize_figure=True,
):
    """
    Publication figure layout with deterministic axes-box sizing.

    For non-PPT publication formats, the data box is fixed in absolute mm and
    the figure canvas is derived from margins + box size.
    """
    fig = fig or plt.gcf()
    normalized_format = str(target_format or "nature").lower()

    if normalized_format == "ppt" and box_width_mm is None and box_height_mm is None and margins_mm is None:
        return _apply_legacy_publication_layout(fig, layout_type)

    layout_spec = PUBLICATION_LAYOUT_SPECS_MM.get(layout_type, PUBLICATION_LAYOUT_SPECS_MM["standard"])
    resolved_box_width = float(box_width_mm or layout_spec["box_width_mm"])
    resolved_box_height = float(box_height_mm or layout_spec["box_height_mm"])
    resolved_margins = dict(layout_spec["margins_mm"])
    if margins_mm:
        resolved_margins.update({k: float(v) for k, v in margins_mm.items()})

    figure_width_mm = resolved_margins["left"] + resolved_box_width + resolved_margins["right"]
    figure_height_mm = resolved_margins["bottom"] + resolved_box_height + resolved_margins["top"]

    if resize_figure:
        fig.set_size_inches(_mm_to_inch(figure_width_mm), _mm_to_inch(figure_height_mm), forward=True)
    else:
        current_w_mm, current_h_mm = _figure_size_mm(fig)
        figure_width_mm = current_w_mm
        figure_height_mm = current_h_mm

    left = resolved_margins["left"] / figure_width_mm
    right = 1.0 - (resolved_margins["right"] / figure_width_mm)
    bottom = resolved_margins["bottom"] / figure_height_mm
    top = 1.0 - (resolved_margins["top"] / figure_height_mm)
    fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
    _lock_publication_layout(
        fig,
        layout_type=layout_type,
        target_format=normalized_format,
        box_width_mm=resolved_box_width,
        box_height_mm=resolved_box_height,
        margins_mm=resolved_margins,
    )
    return {
        "left": left,
        "right": right,
        "bottom": bottom,
        "top": top,
        "figure_width_mm": figure_width_mm,
        "figure_height_mm": figure_height_mm,
        "box_width_mm": resolved_box_width,
        "box_height_mm": resolved_box_height,
    }


def get_legend_args(layout_type="top_outside", ncol=2):
    """Return legend kwargs optimized for a publication layout preset."""
    fontsize = plt.rcParams.get("legend.fontsize", 7.0)
    if layout_type == "top_outside":
        return {
            "fontsize": fontsize,
            "loc": "lower center",
            "bbox_to_anchor": (0.5, 1.02),
            "ncol": ncol,
            "frameon": False,
        }
    if layout_type == "right_outside":
        return {"fontsize": fontsize, "loc": "center left", "bbox_to_anchor": (1.02, 0.5), "ncol": 1, "frameon": False}
    return {"fontsize": fontsize, "loc": "best"}
