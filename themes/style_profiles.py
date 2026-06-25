"""
Reusable style profiles for publication plots.

The theme engine (journal_theme.py) controls global rcParams.
This module provides profile-specific tokens that plotting scripts can
share to keep "look-and-feel" consistent across projects.
"""

import os
from copy import deepcopy

from cycler import cycler

DEFAULT_PROFILE = "baseline"
INTERNAL_RESISTANCE_PROFILE = "_".join(("resistance", "premium"))

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
    "publication": {
        "description": (
            "Journal-safe polished look: CVD-safe Okabe-Ito series palette and white "
            "marker edges. Pairs with any target_format; figure width, font floors, and "
            "line weights stay governed by the journal track and enforced by QA."
        ),
        "rc_overrides": {
            "axes.prop_cycle": cycler(
                color=[
                    "#0072B2",
                    "#D55E00",
                    "#009E73",
                    "#E69F00",
                    "#56B4E9",
                    "#CC79A7",
                    "#7F7F7F",
                    "#000000",
                ]
            ),
            "lines.markeredgecolor": "white",
            "lines.markeredgewidth": 0.5,
            "axes.titlesize": 8.0,
            "axes.labelsize": 7.5,
            "legend.fontsize": 6.5,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "lines.linewidth": 1.2,
            "axes.linewidth": 0.6,
        },
        "tokens": {
            "forward_color": "#D55E00",
            "reverse_color": "#0072B2",
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
            "timeseries_palette": ["#0072B2", "#D55E00", "#009E73", "#E69F00", "#CC79A7"],
        },
    },
    INTERNAL_RESISTANCE_PROFILE: {
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
            # Nature Communications final page column widths: 88 mm single
            # column and 180 mm double column.
            # Source: https://www.nature.com/ncomms/submit/how-to-submit
            "figure_width_mm": 88.0,
            # Width-only NatComms correction; preserve Graph Hub's existing
            # Nature single-panel render height.
            "figure_height_mm": 71.0,
            # Nature Communications does not define a separate 1.5-column slot
            # on the submission page above, so only single and double/full
            # widths are encoded here.
            "figure_column_widths_mm": {"single": 88.0, "double": 180.0, "full": 180.0},
            # Nature artwork minimum text size: 5 pt.
            # Source: https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/
            "min_font_size_pt": 5.0,
            # Nature artwork minimum line weight: 0.25 pt.
            # Source: https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/
            "min_line_width_pt": 0.25,
            # Nature full-page maximum artwork height: 247 mm.
            # Source: https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/
            "max_figure_height_mm": 247.0,
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
            # Science/AAAS official figure widths: 5.7, 12.1, 18.4 cm.
            # Source: https://www.science.org/content/page/instructions-preparing-initial-manuscript
            "figure_width_mm": 57.0,
            # Height is a Graph Hub assumption, preserving the existing 0.80
            # width:height bridge-render ratio for Science's 57 mm single column.
            "figure_height_mm": 45.6,
            # Source: https://www.science.org/content/page/instructions-preparing-initial-manuscript
            "figure_column_widths_mm": {"single": 57.0, "double": 121.0, "full": 184.0, "triple": 184.0},
            # Science figure guidance keeps final lettering at or above 5 pt.
            # Source: https://www.science.org/content/page/instructions-preparing-initial-manuscript
            "min_font_size_pt": 5.0,
            # Science line-art floor used for Graph Hub output compliance.
            # Source: https://www.science.org/content/page/instructions-preparing-initial-manuscript
            "min_line_width_pt": 0.5,
            # Tool default: Science gives widths but no max figure height; use
            # a conservative 234 mm page-height cap for compliance diagnostics.
            # Source: https://www.science.org/content/page/instructions-preparing-initial-manuscript
            "max_figure_height_mm": 234.0,
            # Science uses compact final-size graphics; 3 pt markers keep
            # plotted points legible at 57 mm without dominating 6.5-7 pt text.
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
            # ACS official one-column graphic width is 240 pt = 3.33 in.
            # Source: https://pubs.acs.org/page/4authors/submission/graphics_prep.html
            "figure_width_mm": 84.67,
            # Height is a Graph Hub assumption, preserving the existing 0.80
            # width:height bridge-render ratio for ACS's 84.67 mm single column.
            "figure_height_mm": 67.736,
            # ACS official double-column graphic width remains 7 in.
            # Source: https://pubs.acs.org/page/4authors/submission/graphics_prep.html
            "figure_column_widths_mm": {"single": 84.67, "double": 177.8, "full": 177.8},
            # ACS graphics guidance allows lettering down to 4.5 pt.
            # Source: https://pubs.acs.org/page/4authors/submission/graphics_prep.html
            "min_font_size_pt": 4.5,
            # ACS graphics guidance uses 0.5 pt as the minimum line weight.
            # Source: https://pubs.acs.org/page/4authors/submission/graphics_prep.html
            "min_line_width_pt": 0.5,
            # ACS 660 pt maximum graphic height including caption is ~233 mm.
            # Source: https://pubs.acs.org/page/4authors/submission/graphics_prep.html
            "max_figure_height_mm": 233.0,
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
    "rsc": {
        "baseline": {
            # RSC figure-preparation anchors: single-column artwork is commonly
            # prepared around 8.3 cm final width.
            "figure_width_mm": 83.0,
            # Height is a Graph Hub assumption, preserving the existing 0.80
            # width:height bridge-render ratio for RSC's 83 mm single column.
            "figure_height_mm": 66.4,
            # RSC anchors: 8.3 cm single column and 17.1 cm double column.
            # RSC does not strongly define a 1.5-column slot here, so one_half
            # is treated as the double/full width rather than a separate spec.
            "figure_column_widths_mm": {
                "single": 83.0,
                "one_half": 171.0,
                "double": 171.0,
                "full": 171.0,
                "triple": 171.0,
            },
            # RSC author guidance sets 7 pt as the minimum final text size.
            # Source: https://www.rsc.org/journals-books-databases/author-and-reviewer-hub/authors-information/preparing-your-article/
            "min_font_size_pt": 7.0,
            # RSC line-art guidance uses a 0.5 pt practical minimum.
            # Source: https://www.rsc.org/journals-books-databases/author-and-reviewer-hub/authors-information/preparing-your-article/
            "min_line_width_pt": 0.5,
            # RSC maximum graphic height is treated as a full-page 233 mm cap.
            # Source: https://www.rsc.org/journals-books-databases/author-and-reviewer-hub/authors-information/preparing-your-article/
            "max_figure_height_mm": 233.0,
            # RSC single-column width is close to ACS/Cell, so 3.3 pt markers
            # remain readable without crowding chemical/materials plots.
            "main_marker_size": 3.3,
            # Facet markers stay below the main marker size to avoid crowding
            # in subdivided RSC panels.
            "facet_marker_size": 2.5,
            # Marker edges stay above hairline weight while preserving symbol
            # interiors at final publication size.
            "main_marker_edge_width": 0.55,
            # Main plotted lines use a conservative 1.0 pt journal-scale stroke.
            "main_line_width": 1.0,
            # Dense time-series traces use a slightly lighter stroke while
            # staying visible at 83 mm final width.
            "timeseries_line_width": 0.8,
            # Error bars stay lighter than primary data strokes but above a
            # practical print hairline.
            "error_line_width": 0.75,
            # Cap size follows the generic baseline for RSC's near-default
            # single-column width.
            "error_cap_size": 2.0,
            # Jitter points are reduced from generic baseline to avoid
            # overplotting in one-column categorical plots.
            "jitter_size": 12.0,
            # Jitter outlines follow the marker edge width.
            "jitter_line_width": 0.55,
            # Bar outlines match the practical 0.5 pt print minimum assumption.
            "bar_edge_width": 0.5,
            # KDE resolution is raised above generic baseline for smoother
            # distribution plots; this is a repo assumption, not an RSC spec.
            "violin_kde_points": 192,
            # Keep the generic violin width because RSC single columns are
            # close to Graph Hub's default journal scale.
            "violin_width": 0.5,
            # RSC-specific default is explicit; viridis is perceptually uniform
            # and already Graph Hub's fallback for unknown physics types.
            "default_colormap": "viridis",
        },
    },
    "elsevier": {
        "baseline": {
            # Elsevier figure-preparation anchors: single-column artwork is
            # commonly prepared around 90 mm final width.
            "figure_width_mm": 90.0,
            # Height is a Graph Hub assumption, preserving the existing 0.80
            # width:height bridge-render ratio for Elsevier's 90 mm column.
            "figure_height_mm": 72.0,
            # Elsevier anchors: 90 mm single column, 140 mm 1.5-column, and
            # 190 mm double/full width.
            "figure_column_widths_mm": {
                "single": 90.0,
                "one_half": 140.0,
                "double": 190.0,
                "full": 190.0,
                "triple": 190.0,
            },
            # Elsevier artwork sizing expects readable final text; use 7 pt
            # main lettering while noting 6 pt subscripts are separately allowed.
            # Source: https://www.elsevier.com/researcher/author/tools-and-resources/artwork-and-media-instructions/artwork-sizing
            "min_font_size_pt": 7.0,
            # Tool default: Elsevier sizing guidance does not define a track
            # line-weight floor, so Graph Hub enforces its conservative 0.5 pt.
            # Source: https://www.elsevier.com/researcher/author/tools-and-resources/artwork-and-media-instructions/artwork-sizing
            "min_line_width_pt": 0.5,
            # Tool default: Elsevier sizing guidance here does not define a
            # maximum height, so use the conservative 234 mm page-height cap.
            # Source: https://www.elsevier.com/researcher/author/tools-and-resources/artwork-and-media-instructions/artwork-sizing
            "max_figure_height_mm": 234.0,
            # Elsevier's single-column canvas is larger than the other journal
            # singles here, so 3.6 pt markers remain readable without crowding.
            "main_marker_size": 3.6,
            # Facet markers stay below the main marker size to avoid crowding
            # in subdivided Elsevier panels.
            "facet_marker_size": 2.8,
            # Marker edges stay above hairline weight and match the slightly
            # larger Elsevier marker scale.
            "main_marker_edge_width": 0.6,
            # Main plotted lines use a conservative 1.05 pt journal-scale
            # stroke for the wider Elsevier canvas.
            "main_line_width": 1.05,
            # Dense time-series traces use a lighter stroke than the main line
            # while remaining visible at 90 mm final width.
            "timeseries_line_width": 0.9,
            # Error bars stay lighter than primary data strokes but above a
            # practical print hairline.
            "error_line_width": 0.8,
            # Slightly wider caps match the larger Elsevier column scale.
            "error_cap_size": 2.2,
            # Jitter points are smaller than the generic baseline but scaled a
            # bit above ACS/RSC for Elsevier's wider single column.
            "jitter_size": 13.0,
            # Jitter outlines follow the marker edge width.
            "jitter_line_width": 0.6,
            # Bar outlines stay above a practical print hairline without
            # overpowering fills.
            "bar_edge_width": 0.55,
            # KDE resolution is raised above generic baseline for smoother
            # distribution plots; this is a repo assumption, not an Elsevier spec.
            "violin_kde_points": 192,
            # Keep the generic violin width because Elsevier single columns are
            # close to Graph Hub's default journal scale.
            "violin_width": 0.5,
            # Elsevier-specific default is explicit; viridis is perceptually
            # uniform and already Graph Hub's fallback for unknown physics types.
            "default_colormap": "viridis",
        },
    },
    "wiley": {
        "baseline": {
            # Wiley Advanced Materials graphics FAQ names ~8.5 cm one-column width.
            # Source: https://onlinelibrary.wiley.com/page/journal/15214095/homepage/graphics-faq/index.html
            "figure_width_mm": 85.0,
            # Height is a Graph Hub assumption, preserving the existing 0.80
            # width:height bridge-render ratio for Wiley's 85 mm single column.
            "figure_height_mm": 68.0,
            # Wiley Advanced Materials-family corrected anchors: 8.5 cm single
            # and 17.8 cm double/full column; no separate triple width modeled.
            # Source: https://onlinelibrary.wiley.com/page/journal/15214095/homepage/graphics-faq/index.html
            "figure_column_widths_mm": {"single": 85.0, "double": 178.0, "full": 178.0},
            # Tool default: Wiley/Advanced Materials guidance is qualitative
            # for minimum text in this track; Graph Hub enforces 5 pt.
            # Source: https://onlinelibrary.wiley.com/page/journal/15214095/homepage/graphics-faq/index.html
            "min_font_size_pt": 5.0,
            # Tool default: Wiley/Advanced Materials guidance is qualitative
            # for line weight here; Graph Hub enforces 0.5 pt.
            # Source: https://onlinelibrary.wiley.com/page/journal/15214095/homepage/graphics-faq/index.html
            "min_line_width_pt": 0.5,
            # Tool default: Wiley/Advanced Materials guidance does not define
            # a max height for this track; use conservative 234 mm.
            # Source: https://onlinelibrary.wiley.com/page/journal/15214095/homepage/graphics-faq/index.html
            "max_figure_height_mm": 234.0,
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
    "cell": {
        "baseline": {
            # Cell Press figure-preparation anchors: single-column artwork is
            # commonly prepared at ~85 mm final width.
            "figure_width_mm": 85.0,
            # Height is a Graph Hub assumption, preserving the existing 0.80
            # width:height bridge-render ratio for Cell's 85 mm single column.
            "figure_height_mm": 68.0,
            # Cell Press anchors: 85 mm single column, 114 mm 1.5-column, and
            # 174 mm double/full width. Graph Hub's standard slots are single,
            # double, full, and triple; one_half records the 1.5-column anchor.
            "figure_column_widths_mm": {
                "single": 85.0,
                "one_half": 114.0,
                "double": 174.0,
                "full": 174.0,
                "triple": 174.0,
            },
            # Cell Press figure guidelines specify 6 pt as the minimum type size.
            # Source: https://www.cell.com/figureguidelines
            "min_font_size_pt": 6.0,
            # Cell Press figure guidelines use 0.5 pt as the minimum line weight.
            # Source: https://www.cell.com/figureguidelines
            "min_line_width_pt": 0.5,
            # Cell Press maximum figure height is 200 mm.
            # Source: https://www.cell.com/figureguidelines
            "max_figure_height_mm": 200.0,
            # Cell's single-column width is close to ACS/Wiley, so use the same
            # readable 3.4 pt main marker without cloning Nature's smaller mark.
            "main_marker_size": 3.4,
            # Facet markers stay below the main marker size to prevent crowding
            # in subdivided Cell Press panels.
            "facet_marker_size": 2.6,
            # Marker edges stay above hairline weight while preserving symbol
            # interiors at final publication size.
            "main_marker_edge_width": 0.55,
            # Main plotted lines use a conservative 1.0 pt journal-scale stroke.
            "main_line_width": 1.0,
            # Dense time-series traces get a slightly lighter stroke than the
            # main line token while staying visible in 85 mm columns.
            "timeseries_line_width": 0.85,
            # Error bars follow the repo's readable journal stroke scale and
            # stay below the primary data stroke.
            "error_line_width": 0.8,
            # Cap size follows the generic baseline for Cell's near-default
            # single-column width.
            "error_cap_size": 2.0,
            # Jitter points are reduced from generic baseline to avoid
            # overplotting while remaining visible at Cell figure scale.
            "jitter_size": 12.0,
            # Jitter outlines follow the marker edge width.
            "jitter_line_width": 0.55,
            # Bar outlines are slightly heavier than Science's compact track
            # for Cell's larger column widths.
            "bar_edge_width": 0.55,
            # KDE resolution is raised above generic baseline for smoother
            # distribution plots; this is a repo assumption, not a Cell spec.
            "violin_kde_points": 192,
            # Keep the generic violin width because Cell single columns are
            # close to Graph Hub's default journal scale.
            "violin_width": 0.5,
            # Cell-specific default is explicit; viridis is perceptually
            # uniform and already Graph Hub's fallback for unknown physics types.
            "default_colormap": "viridis",
        },
    },
}

PROFILE_ALIASES = {
    "default": "baseline",
    "base": "baseline",
    "premium": INTERNAL_RESISTANCE_PROFILE,
    "resistance": INTERNAL_RESISTANCE_PROFILE,
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
    target_tokens = TARGET_FORMAT_PROFILE_TOKENS.get(target_key, {})
    tokens.update(target_tokens.get(DEFAULT_PROFILE, {}))
    tokens.update(target_tokens.get(profile_key, {}))
    return tokens, {"target_format": target_key, "profile": profile_key}


def get_profile_rc_overrides(profile_name=None):
    profile, key = get_style_profile(profile_name)
    return profile.get("rc_overrides", {}), key


def list_profiles():
    return sorted(STYLE_PROFILES.keys())
