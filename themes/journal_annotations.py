"""Small annotation primitives shared by journal theme consumers."""

_PANEL_LABEL_LOCS = {
    "upper left": (0.03, 0.97, "left", "top"),
    "upper right": (0.97, 0.97, "right", "top"),
    "lower left": (0.03, 0.03, "left", "bottom"),
    "lower right": (0.97, 0.03, "right", "bottom"),
}


def panel_label(ax, text: str, loc: str = "upper left", color=None, box: bool = True, **kw):
    """Place readable in-panel text in axes-fraction corner coordinates."""
    loc_key = str(loc).lower().replace("_", " ").strip()
    if loc_key not in _PANEL_LABEL_LOCS:
        allowed = ", ".join(sorted(_PANEL_LABEL_LOCS))
        raise ValueError(f"Unsupported panel_label loc {loc!r}; expected one of: {allowed}")

    x, y, ha, va = _PANEL_LABEL_LOCS[loc_key]
    text_kwargs = {
        "transform": ax.transAxes,
        "ha": ha,
        "va": va,
        "color": "black" if color is None else color,
        "zorder": 20,
    }
    if box and "bbox" not in kw:
        text_kwargs["bbox"] = {
            "boxstyle": "round,pad=0.12",
            "facecolor": "white",
            "alpha": 0.72,
            "edgecolor": "none",
            "linewidth": 0.0,
        }
    text_kwargs.update(kw)
    return ax.text(x, y, text, **text_kwargs)
