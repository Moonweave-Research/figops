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
