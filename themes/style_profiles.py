"""
Reusable style profiles for publication plots.

The theme engine (journal_theme.py) controls global rcParams.
This module provides profile-specific tokens that plotting scripts can
share to keep "look-and-feel" consistent across projects.
"""

import os
from copy import deepcopy

DEFAULT_PROFILE = "baseline"

# ── Multi-channel encoding cycles (CVD / greyscale accessibility) ──
# 색상과 독립적으로 시리즈를 구분할 수 있도록 마커·선종류를 자동 순환
MARKER_CYCLE = ("o", "s", "^", "D", "v", "P", "X", "*")
LINESTYLE_CYCLE = ("-", "--", "-.", ":")
HATCH_CYCLE = ("//", "\\\\", "xx", "++", "..", "oo", "**", "OO")


def get_series_style(index: int) -> dict:
    """Return marker + linestyle + hatch for the *index*-th data series."""
    return {
        "marker": MARKER_CYCLE[index % len(MARKER_CYCLE)],
        "linestyle": LINESTYLE_CYCLE[index % len(LINESTYLE_CYCLE)],
        "hatch": HATCH_CYCLE[index % len(HATCH_CYCLE)],
    }

STYLE_PROFILES = {
    "baseline": {
        "description": "Default hub style",
        "rc_overrides": {},
        "tokens": {
            "forward_color": "#d62728",
            "reverse_color": "#1f77b4",
            "accent_color": "#111111",
            "neutral_color": "#7f8c8d",
            "wt_colors": {},
            "main_line_width": 1.2,
            "main_marker_size": 5.0,
            "main_marker_edge_width": 0.6,
            "error_cap_size": 2.0,
            "error_line_width": 0.8,
            "jitter_size": 14.0,
            "jitter_line_width": 0.6,
            "jitter_alpha": 0.75,
            "jitter_sigma": 0.07,
            "violin_kde_points": 100,
            "violin_kde_bw_method": "scott",
            "violin_width": 0.5,
            "bar_edge_width": 0.5,
            "grid_y": False,
            "grid_color": "#e0e0e0",
            "grid_line_style": ":",
            "grid_line_width": 0.3,
            "grid_alpha": 0.8,
            "zero_line_style": "--",
            "zero_line_width": 0.4,
            "zero_line_alpha": 0.4,
            "figure_height_mm": 68.0,
            "timeseries_panel_height_mm": 45.0,
            "timeseries_line_width": 0.8,
            "timeseries_alpha": 0.9,
            "timeseries_palette": ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"],
        },
    },
    "resistance_premium": {
        "description": "Profile copied from resistance publication style",
        "rc_overrides": {
            "axes.titlesize": 8.5,
            "axes.labelsize": 7.5,
            "legend.fontsize": 6.5,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "lines.linewidth": 1.1,
            "axes.linewidth": 0.5,
        },
        "tokens": {
            "forward_color": "#e74c3c",
            "reverse_color": "#2980b9",
            "accent_color": "#2c3e50",
            "neutral_color": "#7f8c8d",
            "wt_colors": {
                60: "#2c3e50",
                70: "#2980b9",
                75: "#e74c3c",
                80: "#f39c12",
                85: "#8e44ad",
            },
            "main_line_width": 1.4,
            "main_marker_size": 5.5,
            "main_marker_edge_width": 0.65,
            "error_cap_size": 2.0,
            "error_line_width": 0.9,
            "jitter_size": 15.0,
            "jitter_line_width": 0.6,
            "jitter_alpha": 0.65,
            "jitter_sigma": 0.07,
            "violin_kde_points": 100,
            "violin_kde_bw_method": "scott",
            "violin_width": 0.5,
            "bar_edge_width": 0.55,
            "grid_y": True,
            "grid_color": "#e0e0e0",
            "grid_line_style": ":",
            "grid_line_width": 0.35,
            "grid_alpha": 0.85,
            "zero_line_style": "--",
            "zero_line_width": 0.45,
            "zero_line_alpha": 0.45,
            "figure_height_mm": 70.0,
            "timeseries_panel_height_mm": 47.0,
            "timeseries_line_width": 1.05,
            "timeseries_alpha": 0.85,
            "timeseries_palette": ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00"],
        },
    },
}

TARGET_FORMAT_PROFILE_TOKENS = {
    "nature": {
        "baseline": {
            "main_marker_size": 3.2,
            "facet_marker_size": 2.4,
            "axis_marker_margin_fraction": 0.06,
            "facet_axis_marker_margin_fraction": 0.16,
            "violin_kde_points": 256,
            "violin_kde_bw_method": "scott",
            "violin_width": 0.52,
        },
    },
    "science": {
        "baseline": {
            # Science/AAAS figure-preparation widths: single-column figures are
            # prepared at ~5.5 cm final width.
            "figure_width_mm": 55.0,
            # Height is a Graph Hub assumption, preserving the existing 0.80
            # width:height bridge-render ratio for Science's 55 mm single column.
            "figure_height_mm": 44.0,
            # Science/AAAS figure-preparation widths: 5.5 cm single column,
            # 12 cm double/intermediate width, and 18.3 cm full/triple width.
            "figure_column_widths_mm": {"single": 55.0, "double": 120.0, "full": 183.0, "triple": 183.0},
            # Science uses compact final-size graphics; 3 pt markers keep
            # plotted points legible at 55 mm without dominating 6.5-7 pt text.
            "main_marker_size": 3.0,
            # Smaller facets need slightly smaller markers to avoid edge clipping
            # when Science single-column panels are subdivided.
            "facet_marker_size": 2.2,
            # Thin marker edges preserve marker shape at final-size reduction.
            "main_marker_edge_width": 0.5,
            # Science line art should remain crisp but not heavy at final size;
            # 0.9 pt is an assumption within the repo's existing journal range.
            "main_line_width": 0.9,
            # Dense time-series traces get a slightly lighter stroke than the
            # main line token to preserve local detail in small Science panels.
            "timeseries_line_width": 0.75,
            # Error bars follow the lighter Science line-art stroke assumption.
            "error_line_width": 0.7,
            # Compact caps are scaled for 55 mm single-column panels.
            "error_cap_size": 1.8,
            # Scatter jitter area is reduced from the generic baseline for small
            # Science panels while keeping points visible.
            "jitter_size": 10.0,
            # Jitter outlines follow the marker edge width.
            "jitter_line_width": 0.5,
            # Bar outlines are slightly lighter than Nature's 0.5 pt default.
            "bar_edge_width": 0.45,
            # KDE resolution is raised above generic baseline but below Nature's
            # stricter 256-point track; this is a repo assumption for smooth
            # Science violin plots at small final widths.
            "violin_kde_points": 192,
            # Narrower violins reduce crowding in compact Science figures.
            "violin_width": 0.48,
            # Science-specific default is explicit; viridis is perceptually
            # uniform and already the repo fallback for unknown physics types.
            "default_colormap": "viridis",
        },
    },
    "acs": {
        "baseline": {
            # ACS artwork guidance uses one-column graphics around 3.25 in;
            # convert directly to millimetres for Graph Hub's width tokens.
            "figure_width_mm": 82.55,
            # Height is a Graph Hub assumption, preserving the existing 0.80
            # width:height bridge-render ratio for ACS's 82.55 mm single column.
            "figure_height_mm": 66.04,
            # ACS journal artwork is commonly prepared for one-column (~3.25 in)
            # and two-column (~7 in) widths; no separate triple width is assumed.
            "figure_column_widths_mm": {"single": 82.55, "double": 177.8, "full": 177.8},
            # ACS single-column figures are close to Nature's width but often
            # carry chemical/spectral detail; use a modest 3.4 pt marker.
            "main_marker_size": 3.4,
            # Facet markers stay below the main marker size to avoid crowding
            # in subdivided ACS figure panels.
            "facet_marker_size": 2.6,
            # ACS line-art guidance sets a 0.5 pt minimum; 0.55 pt marker edges
            # keep symbols visible without exceeding compact final artwork.
            "main_marker_edge_width": 0.55,
            # Main plotted lines use 1.0 pt, comfortably above ACS's 0.5 pt
            # minimum while matching the repo's existing journal scale.
            "main_line_width": 1.0,
            # Time-series traces use the repo baseline 0.8 pt for dense spectra
            # and response curves in ACS-sized columns.
            "timeseries_line_width": 0.8,
            # Error bars stay above the ACS 0.5 pt minimum while remaining
            # lighter than primary data strokes.
            "error_line_width": 0.75,
            # Cap size follows the generic baseline because ACS width is near
            # the repo's default single-column scale.
            "error_cap_size": 2.0,
            # Jitter points are smaller than the generic baseline to avoid
            # overplotting in ACS one-column categorical plots.
            "jitter_size": 12.0,
            # Jitter outlines follow the ACS marker edge width.
            "jitter_line_width": 0.55,
            # Bar outlines match the ACS line-art minimum.
            "bar_edge_width": 0.5,
            # KDE resolution is raised above generic baseline for smoother
            # ACS distribution plots; this is a repo assumption, not an ACS spec.
            "violin_kde_points": 192,
            # Keep the generic violin width for ACS because its single column is
            # near Graph Hub's default journal scale.
            "violin_width": 0.5,
            # ACS-specific default is explicit; viridis is perceptually uniform
            # and already Graph Hub's fallback for unknown physics types.
            "default_colormap": "viridis",
        },
    },
    "wiley": {
        "baseline": {
            # Wiley Advanced Materials-family figures commonly target 8.4 cm
            # single-column artwork; store widths in Graph Hub's mm tokens.
            "figure_width_mm": 84.0,
            # Height is a Graph Hub assumption, preserving the existing 0.80
            # width:height bridge-render ratio for Wiley's 84 mm single column.
            "figure_height_mm": 67.2,
            # Wiley Advanced Materials-family anchors: 8.4 cm single column and
            # 17.4 cm double column; no separate triple width is modeled here.
            "figure_column_widths_mm": {"single": 84.0, "double": 174.0, "full": 174.0},
            # Wiley single-column width is close to ACS/Nature but slightly
            # broader than ACS; use a 3.5 pt marker for compact readability.
            "main_marker_size": 3.5,
            # Facet markers stay smaller than the main marker size to prevent
            # crowding in multi-panel Advanced Materials-style figures.
            "facet_marker_size": 2.7,
            # Marker edges are kept above hairline weight while preserving
            # symbol interiors at final publication size.
            "main_marker_edge_width": 0.55,
            # Main plotted lines use a conservative 1.0 pt journal-scale stroke.
            "main_line_width": 1.0,
            # Dense time-series traces get a slightly lighter stroke than the
            # main line token while staying visible in 84 mm columns.
            "timeseries_line_width": 0.85,
            # Error bars follow the repo's readable journal stroke scale.
            "error_line_width": 0.8,
            # Cap size follows the generic baseline for Wiley's near-default
            # single-column width.
            "error_cap_size": 2.0,
            # Jitter points are reduced from generic baseline to avoid
            # overplotting while remaining visible at Wiley figure scale.
            "jitter_size": 12.5,
            # Jitter outlines follow the marker edge width.
            "jitter_line_width": 0.55,
            # Bar outlines are slightly heavier than Science's compact track
            # for Wiley's larger column widths.
            "bar_edge_width": 0.55,
            # KDE resolution is raised above generic baseline for smoother
            # distribution plots; this is a repo assumption, not a Wiley spec.
            "violin_kde_points": 192,
            # Keep the generic violin width because Wiley single columns are
            # close to Graph Hub's default journal scale.
            "violin_width": 0.5,
            # Wiley-specific default is explicit; viridis is perceptually
            # uniform and already Graph Hub's fallback for unknown physics types.
            "default_colormap": "viridis",
        },
    },
}

PROFILE_ALIASES = {
    "default": "baseline",
    "base": "baseline",
    "premium": "resistance_premium",
    "resistance": "resistance_premium",
    "wiley": "baseline",
    "cell": "baseline",
    "cell_press": "baseline",
}


def resolve_profile_name(profile_name=None):
    raw = profile_name
    if raw is None:
        raw = os.environ.get("THEME_PROFILE", DEFAULT_PROFILE)
    key = str(raw).strip().lower() if raw is not None else DEFAULT_PROFILE
    key = PROFILE_ALIASES.get(key, key)
    if key not in STYLE_PROFILES:
        key = DEFAULT_PROFILE
    return key


def get_style_profile(profile_name=None):
    key = resolve_profile_name(profile_name)
    return deepcopy(STYLE_PROFILES[key]), key


def get_profile_tokens(profile_name=None):
    profile, key = get_style_profile(profile_name)
    return profile.get("tokens", {}), key


def get_render_style_tokens(target_format="nature", profile_name=None):
    target_key = str(target_format or "nature").strip().lower()
    profile_tokens, profile_key = get_profile_tokens(profile_name)
    tokens = deepcopy(profile_tokens)
    tokens.update(TARGET_FORMAT_PROFILE_TOKENS.get(target_key, {}).get(profile_key, {}))
    return tokens, {"target_format": target_key, "profile": profile_key}


def get_profile_rc_overrides(profile_name=None):
    profile, key = get_style_profile(profile_name)
    return profile.get("rc_overrides", {}), key


def list_profiles():
    return sorted(STYLE_PROFILES.keys())
