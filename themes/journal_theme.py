"""
[Graph_making_hub]/themes/journal_theme.py
==========================================
📐 저널 투고용 matplotlib 전역 테마 설정 (Theme Library Vending Machine)

[역할]
- 모든 Python 연구 스크립트가 import하는 시각화 표준
- target_format 파라미터에 따라 딕셔너리를 로드하고, font_scale에 따라 크기를 보정하는 순수 함수.
- 환경 변수 직접 참조를 배제하여 순수 함수(Pure function) 원칙 준수.
"""

import copy
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
from cycler import cycler

try:
    from .compliance import _clamp_figure_artists_to_journal_compliance, _clamp_rc_to_journal_compliance
    from .declutter import _declutter_text_artists
except ImportError:
    from compliance import _clamp_figure_artists_to_journal_compliance, _clamp_rc_to_journal_compliance
    from declutter import _declutter_text_artists

try:
    # Package import path: from themes.journal_theme import ...
    from .palettes import get_palette

    try:
        from .style_profiles import get_profile_rc_overrides, get_render_style_tokens, resolve_profile_name
    except ImportError:
        from style_profiles import get_profile_rc_overrides, get_render_style_tokens, resolve_profile_name
except ImportError:
    # Backward compatibility for direct path import: sys.path += ['themes']
    from palettes import get_palette

    try:
        from style_profiles import get_profile_rc_overrides, resolve_profile_name
    except ImportError:

        def resolve_profile_name(profile_name=None):
            return "baseline"

        def get_profile_rc_overrides(profile_name=None):
            return {}, "baseline"

        def get_render_style_tokens(target_format="nature", profile_name=None):
            return {}, {"target_format": str(target_format or "nature").lower(), "profile": "baseline"}

try:
    from .layout import (
        _LAYOUT_LOCK_ATTR,
        MULTI_PANEL_GRID_SPECS_MM,
        PUBLICATION_LAYOUT_SPECS_MM,
        _apply_legacy_publication_layout,
        _figure_size_mm,
        _lock_publication_layout,
        apply_panel_grid_layout,
        apply_publication_layout,
        get_legend_args,
    )
except ImportError:
    from layout import (
        _LAYOUT_LOCK_ATTR,
        MULTI_PANEL_GRID_SPECS_MM,
        PUBLICATION_LAYOUT_SPECS_MM,
        _apply_legacy_publication_layout,
        _figure_size_mm,
        _lock_publication_layout,
        apply_panel_grid_layout,
        apply_publication_layout,
        get_legend_args,
    )

__all__ = [
    "DOUBLE_COLUMN",
    "INTERNAL_STYLE_TARGET_FORMAT",
    "MULTI_PANEL_GRID_SPECS_MM",
    "PUBLICATION_LAYOUT_SPECS_MM",
    "SINGLE_COLUMN",
    "STYLE_PRESETS",
    "TIFF_AUTO_PRESETS",
    "_LAYOUT_LOCK_ATTR",
    "_active_font_token_sizes",
    "_apply_legacy_publication_layout",
    "_figure_size_mm",
    "_lock_publication_layout",
    "_safe_geometry_diagnostics_inline",
    "apply_journal_style",
    "apply_journal_theme",
    "apply_panel_grid_layout",
    "apply_publication_layout",
    "font_tokens",
    "get_figsize",
    "get_legend_args",
    "mm_to_inch",
    "panel_label",
    "save_journal_fig",
    "set_figure_size",
]


# ── Nature/Science Standard Widths (mm) ─────────────────────────
SINGLE_COLUMN = 89  # mm
DOUBLE_COLUMN = 183  # mm
DIAG_BUDGET_FLOOR_SECONDS = 5.0
INTERNAL_STYLE_TARGET_FORMAT = "_".join(("nature", "surfur"))

TIFF_AUTO_PRESETS: set[str] = {
    "nature",
    INTERNAL_STYLE_TARGET_FORMAT,
    "science",
    "acs",
    "rsc",
    "elsevier",
    "wiley",
    "cell",
}


@dataclass(frozen=True)
class FontTokens:
    tag: float
    label: float
    annot: float
    legend: float
    axis: float
    tick: float

    @property
    def annotation(self) -> float:
        return self.annot

    def __getitem__(self, key: str) -> float:
        return self.as_dict()[key]

    def as_dict(self) -> dict[str, float]:
        return {
            "tag": self.tag,
            "label": self.label,
            "annot": self.annot,
            "annotation": self.annot,
            "legend": self.legend,
            "axis": self.axis,
            "tick": self.tick,
        }


_FONT_TOKEN_PRESETS: dict[str, FontTokens] = {
    "nature": FontTokens(tag=8.0, label=6.0, annot=6.0, legend=7.0, axis=7.0, tick=6.0),
    # Science/AAAS figure guidance uses Helvetica/Arial-family lettering and
    # compact final-size labels; 7 pt body/axis text with 6.5 pt ticks is a
    # Graph Hub assumption that keeps above the repo's existing small-text floor.
    "science": FontTokens(tag=8.0, label=7.0, annot=7.0, legend=7.0, axis=7.0, tick=6.5),
    # ACS artwork guidance permits small final lettering, but this track uses
    # readable 7 pt body/axis text and 6.5 pt ticks within Graph Hub's floor.
    "acs": FontTokens(tag=8.0, label=7.0, annot=7.0, legend=7.0, axis=7.0, tick=6.5),
    # RSC artwork guidance uses Arial/Helvetica-style sans-serif lettering;
    # use 7 pt body/axis/tick text to stay at the RSC minimum font floor.
    "rsc": FontTokens(tag=8.0, label=7.0, annot=7.0, legend=7.0, axis=7.0, tick=7.0),
    # Elsevier figure guidance supports Arial/Helvetica-style sans-serif text;
    # use 7 pt body/axis/tick text for main lettering; subscripts may be 6 pt.
    "elsevier": FontTokens(tag=8.0, label=7.0, annot=7.0, legend=7.0, axis=7.0, tick=7.0),
    # Wiley/Advanced Materials-family artwork uses readable sans-serif labels;
    # keep 7 pt body/axis text and 6.5 pt ticks within Graph Hub's floor.
    "wiley": FontTokens(tag=8.0, label=7.0, annot=7.0, legend=7.0, axis=7.0, tick=6.5),
    # Cell Press figure guidance specifies Arial fonts; use readable 7 pt
    # body/axis lettering with 6.5 pt ticks as a Graph Hub assumption that
    # stays within the repo's established small-text floor.
    "cell": FontTokens(tag=8.0, label=7.0, annot=7.0, legend=7.0, axis=7.0, tick=6.5),
    INTERNAL_STYLE_TARGET_FORMAT: FontTokens(tag=6.0, label=5.0, annot=6.0, legend=6.0, axis=7.0, tick=6.0),
    "ppt": FontTokens(tag=16.0, label=12.0, annot=12.0, legend=12.0, axis=14.0, tick=12.0),
    "default": FontTokens(tag=8.0, label=6.0, annot=6.0, legend=7.0, axis=7.0, tick=6.0),
}
_ACTIVE_FONT_TOKENS = _FONT_TOKEN_PRESETS["nature"]
_ACTIVE_TARGET_FORMAT = "nature"
_ACTIVE_COMPLIANCE_TOKENS: dict[str, float | str] | None = None


def font_tokens(target: str = "nature", font_scale: float = 1.0, profile_name=None) -> FontTokens:
    target_key = str(target or "nature").lower()
    tokens = _FONT_TOKEN_PRESETS.get(target_key, _FONT_TOKEN_PRESETS["nature"])
    if not isinstance(font_scale, (int, float)) or font_scale <= 0:
        raise ValueError(f"font_scale must be a positive number, got {font_scale!r}")
    if font_scale == 1.0:
        scaled = tokens
    else:
        scaled = FontTokens(
            tag=tokens.tag * font_scale,
            label=tokens.label * font_scale,
            annot=tokens.annot * font_scale,
            legend=tokens.legend * font_scale,
            axis=tokens.axis * font_scale,
            tick=tokens.tick * font_scale,
        )
    if profile_name is None:
        return scaled
    profile_rc, _ = get_profile_rc_overrides(resolve_profile_name(profile_name))
    resolved_axis = float(profile_rc.get("axes.labelsize", scaled.axis))
    resolved_tick = float(profile_rc.get("xtick.labelsize", profile_rc.get("ytick.labelsize", scaled.tick)))
    resolved_legend = float(profile_rc.get("legend.fontsize", scaled.legend))
    resolved_tag = float(profile_rc.get("axes.titlesize", scaled.tag))
    return FontTokens(
        tag=resolved_tag,
        label=resolved_axis,
        annot=resolved_axis,
        legend=resolved_legend,
        axis=resolved_axis,
        tick=resolved_tick,
    )


def mm_to_inch(mm):
    return mm / 25.4


# ── Style Presets Dictionary ─────────────────────────────────────
# 하드코딩된 설정을 딕셔너리 기반으로 추상화하여 의존성 없는 테마 엔진 구축
STYLE_PRESETS = {
    "nature": {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
        "mathtext.fontset": "custom",
        "mathtext.rm": "Arial",
        "mathtext.it": "Arial:italic",
        "mathtext.bf": "Arial:bold",
        # Font Sizes (Nature standard: 5~7pt strictly, 8pt only for 'a', 'b', 'c' panel tags)
        "axes.titlesize": 7.5,
        "axes.titleweight": "normal",
        "axes.labelsize": 7.0,
        "axes.labelweight": "normal",
        "legend.fontsize": 7.0,
        "xtick.labelsize": 6.0,
        "ytick.labelsize": 6.0,
        # Line Weights
        "axes.linewidth": 0.5,
        "grid.linewidth": 0.3,
        "lines.linewidth": 1.0,
        "patch.linewidth": 0.5,
        "xtick.major.width": 0.4,
        "ytick.major.width": 0.4,
        # Grid & Ticks
        "axes.grid": False,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.top": True,
        "ytick.right": True,
        "xtick.minor.visible": True,
        "ytick.minor.visible": True,
        "xtick.minor.width": 0.3,
        "ytick.minor.width": 0.3,
        "xtick.minor.size": 2.0,
        "ytick.minor.size": 2.0,
        "xtick.major.size": 3.5,
        "ytick.major.size": 3.5,
        "xtick.major.pad": 3.0,
        "ytick.major.pad": 3.0,
        # Legend
        "legend.frameon": False,
        "legend.loc": "best",
        # Output
        "savefig.dpi": 600,
        "savefig.format": "pdf",
        "savefig.bbox": "tight",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    },
    "ppt": {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
        # Font Sizes (PPT에 맞춰 확대된 기본값)
        "axes.labelsize": 14.0,
        "axes.titlesize": 16.0,
        "legend.fontsize": 12.0,
        "xtick.labelsize": 12.0,
        "ytick.labelsize": 12.0,
        # Line Weights (PPT에 맞춰 굵은 선)
        "axes.linewidth": 1.5,
        "grid.linewidth": 1.0,
        "lines.linewidth": 2.0,
        "patch.linewidth": 1.5,
        "xtick.major.width": 1.2,
        "ytick.major.width": 1.2,
        # Grid & Ticks
        "axes.grid": False,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.top": False,
        "ytick.right": False,
        # Legend
        "legend.frameon": False,
        "legend.loc": "best",
        # Output
        "savefig.dpi": 300,
        "savefig.format": "png",
        "savefig.bbox": "tight",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    },
}
# Per-journal style differentiation based on actual submission guidelines
STYLE_PRESETS["science"] = copy.deepcopy(STYLE_PRESETS["nature"])
STYLE_PRESETS["science"].update(
    {
        # Science/AAAS asks for Helvetica/Arial-style sans-serif lettering;
        # prefer Helvetica first, then keep Arial and portable fallbacks.
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans", "Liberation Sans"],
        "mathtext.rm": "Helvetica",
        "mathtext.it": "Helvetica:italic",
        "mathtext.bf": "Helvetica:bold",
        # Science final artwork should use compact, consistent lettering.
        # 7 pt is guideline-aligned; 6.5 pt ticks are an explicit repo
        # assumption to keep dense axes legible without exceeding small panels.
        "font.size": 7.0,
        "axes.titlesize": 7.5,
        "axes.labelsize": 7.0,
        "legend.fontsize": 7.0,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        # Science line-art stroke assumptions: light enough for 55 mm figures,
        # still above hairline-like rendering in exported vector/raster files.
        "axes.linewidth": 0.5,
        "grid.linewidth": 0.3,
        "lines.linewidth": 0.9,
        "lines.markersize": 3.0,
        "lines.markeredgewidth": 0.5,
        "patch.linewidth": 0.45,
        "xtick.top": False,  # Science: no box, only left+bottom axes
        "ytick.right": False,
    }
)

STYLE_PRESETS["acs"] = copy.deepcopy(STYLE_PRESETS["nature"])
STYLE_PRESETS["acs"].update(
    {
        # ACS artwork guidance recommends Arial/Helvetica-style lettering;
        # prefer Helvetica first, then Arial and portable fallbacks.
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans", "Liberation Sans"],
        "mathtext.rm": "Helvetica",
        "mathtext.it": "Helvetica:italic",
        "mathtext.bf": "Helvetica:bold",
        # Use readable 7 pt final-size text; ACS allows smaller lettering in
        # some journals, but Graph Hub keeps this track above the local floor.
        "font.size": 7.0,
        "axes.titlesize": 7.5,
        "axes.labelsize": 7.0,
        "legend.fontsize": 7.0,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        # ACS line-art guidance uses 0.5 pt as a practical minimum; these values
        # stay above that while matching ACS column-scale plots.
        "axes.linewidth": 0.6,
        "grid.linewidth": 0.3,
        "lines.linewidth": 1.0,
        "lines.markersize": 3.4,
        "lines.markeredgewidth": 0.55,
        "patch.linewidth": 0.5,
        "xtick.direction": "out",  # ACS: outward ticks
        "ytick.direction": "out",
    }
)

STYLE_PRESETS["rsc"] = copy.deepcopy(STYLE_PRESETS["nature"])
STYLE_PRESETS["rsc"].update(
    {
        # RSC journal artwork commonly uses Arial/Helvetica-style sans-serif
        # lettering; prefer Arial first to match that author-facing wording.
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
        "mathtext.rm": "Arial",
        "mathtext.it": "Arial:italic",
        "mathtext.bf": "Arial:bold",
        # Use readable 7 pt final-size body/tick text to respect RSC's
        # minimum final text size.
        "font.size": 7.0,
        "axes.titlesize": 7.5,
        "axes.labelsize": 7.0,
        "legend.fontsize": 7.0,
        "xtick.labelsize": 7.0,
        "ytick.labelsize": 7.0,
        # RSC single-column width is close to ACS/Cell; use 1.0 pt primary
        # strokes and 0.6 pt axes so line art stays above hairline weight.
        "axes.linewidth": 0.6,
        "lines.linewidth": 1.0,
        "lines.markersize": 3.3,
        "lines.markeredgewidth": 0.55,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.direction": "out",
        "ytick.direction": "out",
    }
)

STYLE_PRESETS["elsevier"] = copy.deepcopy(STYLE_PRESETS["nature"])
STYLE_PRESETS["elsevier"].update(
    {
        # Elsevier artwork commonly accepts Arial/Helvetica-style sans-serif
        # lettering; prefer Arial first to match author-facing guidance.
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
        "mathtext.fontset": "custom",
        "mathtext.rm": "Arial",
        "mathtext.it": "Arial:italic",
        "mathtext.bf": "Arial:bold",
        # Use readable 7 pt final-size body/tick text for Elsevier main
        # lettering; subscripts are the separate 6 pt exception.
        "font.size": 7.0,
        "axes.titlesize": 7.5,
        "axes.labelsize": 7.0,
        "legend.fontsize": 7.0,
        "xtick.labelsize": 7.0,
        "ytick.labelsize": 7.0,
        # Elsevier column widths are the broadest journal anchors in this set;
        # use slightly stronger primary strokes while staying publication-scale.
        "axes.linewidth": 0.65,
        "lines.linewidth": 1.05,
        "lines.markersize": 3.6,
        "lines.markeredgewidth": 0.6,
        "xtick.major.width": 0.65,
        "ytick.major.width": 0.65,
        "xtick.direction": "out",
        "ytick.direction": "out",
    }
)

STYLE_PRESETS["wiley"] = copy.deepcopy(STYLE_PRESETS["nature"])
STYLE_PRESETS["wiley"].update(
    {
        # Wiley Advanced Materials-family artwork uses Helvetica/Arial-style
        # sans-serif lettering; prefer Helvetica first, then portable fallbacks.
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans", "Liberation Sans"],
        "mathtext.rm": "Helvetica",
        "mathtext.it": "Helvetica:italic",
        "mathtext.bf": "Helvetica:bold",
        # Use readable 7 pt final-size text for dense materials figures; this
        # is a Graph Hub assumption aligned with the local min-size floor.
        "font.size": 7.0,
        "axes.titlesize": 7.5,
        "axes.labelsize": 7.0,
        "legend.fontsize": 7.0,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        # Wiley column widths sit between ACS/Nature and full-width figures;
        # these strokes are readable without the previous heavy 1.0 pt axes.
        "lines.linewidth": 1.0,
        "lines.markersize": 3.5,
        "lines.markeredgewidth": 0.55,
        "axes.linewidth": 0.7,
        "xtick.major.width": 0.7,
        "ytick.major.width": 0.7,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.top": True,
        "ytick.right": True,
        "savefig.dpi": 600,
    }
)

STYLE_PRESETS["cell"] = copy.deepcopy(STYLE_PRESETS["nature"])
STYLE_PRESETS["cell"].update(
    {
        # Cell Press figure guidelines specify Arial fonts.
        # Source: https://www.cell.com/figureguidelines
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "DejaVu Sans", "Liberation Sans", "Helvetica"],
        "mathtext.rm": "Arial",
        "mathtext.it": "Arial:italic",
        "mathtext.bf": "Arial:bold",
        # Use readable final-size text across Cell-family figures. 7 pt
        # body/axis labels are a repo assumption aligned with the local floor.
        "font.size": 7.0,
        "axes.titlesize": 7.5,
        "axes.labelsize": 7.0,
        "legend.fontsize": 7.0,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        # Cell Press column widths are near ACS/Wiley; keep primary line art at
        # 1.0 pt and axes at 0.65 pt so exported lines stay above hairline
        # weight without making the frame heavier than the data.
        "lines.linewidth": 1.0,
        "lines.markersize": 3.4,
        "lines.markeredgewidth": 0.55,
        "axes.linewidth": 0.65,
        "xtick.major.width": 0.65,
        "ytick.major.width": 0.65,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.top": False,
        "ytick.right": False,
        "savefig.dpi": 600,
    }
)

# Internal project style preset (2026-04-10)
# - NatComm 5-7pt strict compliance (title 7.0, legend 6.0)
# - 50x50 mm plot box 기준 → spine/tick 약간 굵게 (0.75pt)
# - minor tick global 강제 off (필요한 플랏에서만 개별 on)
# - 기본 `nature`와 별개로 유지해 다른 프로젝트에 영향 없음
STYLE_PRESETS[INTERNAL_STYLE_TARGET_FORMAT] = copy.deepcopy(STYLE_PRESETS["nature"])
STYLE_PRESETS[INTERNAL_STYLE_TARGET_FORMAT].update(
    {
        "font.size": 7.0,  # ax.text() 등의 기본 텍스트 크기 (rcParams 기본 10pt 오버라이드)
        "axes.titlesize": 7.0,
        "legend.fontsize": 6.0,
        "legend.title_fontsize": 6.0,
        "axes.linewidth": 0.75,
        "xtick.major.width": 0.75,
        "ytick.major.width": 0.75,
        "xtick.minor.visible": False,
        "ytick.minor.visible": False,
    }
)

STYLE_PRESETS["default"] = copy.deepcopy(STYLE_PRESETS["nature"])

_FALLBACK_SANS_FONTS = ["Arial", "Helvetica", "Liberation Sans", "DejaVu Sans"]


def _resolve_sans_fonts(preferred_fonts):
    preferred = preferred_fonts if isinstance(preferred_fonts, list) else _FALLBACK_SANS_FONTS
    resolved = list(dict.fromkeys(preferred))
    if "DejaVu Sans" not in resolved:
        # Keep a universal fallback at the end for non-Docker environments.
        resolved.append("DejaVu Sans")
    return resolved


def _apply_runtime_font_resolution(theme_rc):
    sans_fonts = _resolve_sans_fonts(theme_rc.get("font.sans-serif"))
    theme_rc["font.sans-serif"] = sans_fonts
    primary_font = sans_fonts[0]

    if theme_rc.get("mathtext.fontset") == "custom":
        if primary_font == "DejaVu Sans":
            theme_rc["mathtext.fontset"] = "dejavusans"
            theme_rc.pop("mathtext.rm", None)
            theme_rc.pop("mathtext.it", None)
            theme_rc.pop("mathtext.bf", None)
        else:
            theme_rc["mathtext.rm"] = primary_font
            theme_rc["mathtext.it"] = f"{primary_font}:italic"
            theme_rc["mathtext.bf"] = f"{primary_font}:bold"


def _journal_compliance_tokens(target_format: str, profile_name: str) -> dict[str, float | str] | None:
    render_tokens, meta = get_render_style_tokens(target_format, profile_name)
    required_keys = ("min_font_size_pt", "min_line_width_pt", "max_figure_height_mm")
    if not all(key in render_tokens for key in required_keys):
        return None
    return {
        "target_format": meta["target_format"],
        "profile": meta["profile"],
        "min_font_size_pt": float(render_tokens["min_font_size_pt"]),
        "min_line_width_pt": float(render_tokens["min_line_width_pt"]),
        "max_figure_height_mm": float(render_tokens["max_figure_height_mm"]),
    }


def _font_tokens_from_rc(target_format: str, theme_rc: dict, font_scale: float, profile_name: str) -> FontTokens:
    fallback = font_tokens(target_format, font_scale, profile_name)
    axis = float(theme_rc.get("axes.labelsize", fallback.axis))
    tick = float(theme_rc.get("xtick.labelsize", theme_rc.get("ytick.labelsize", fallback.tick)))
    legend = float(theme_rc.get("legend.fontsize", fallback.legend))
    tag = float(theme_rc.get("axes.titlesize", fallback.tag))
    return FontTokens(tag=tag, label=axis, annot=axis, legend=legend, axis=axis, tick=tick)


def apply_journal_theme(target_format="nature", font_scale=1.0, profile_name=None):
    """
    지정된 포맷과 폰트 스케일을 기반으로 전역 rcParams에 저널 스타일을 적용합니다.
    (순수 함수 지향: 환경 변수를 내부에서 읽지 않고 인자로만 작동)

    Args:
        target_format (str): 적용할 테마 프리셋 이름
            ('nature', 'science', 'ppt', 'default', 'acs', 'rsc', 'elsevier', or internal aliases)
        font_scale (float): 기준 테마 폰트 사이즈 대비 보정 배율
        profile_name (str): 세부 스타일 프로파일 이름 (예: baseline, internal profiles)
    """
    global _ACTIVE_COMPLIANCE_TOKENS, _ACTIVE_FONT_TOKENS, _ACTIVE_TARGET_FORMAT

    # 1. 포맷 가져오기 (fallback: nature)
    target_format = target_format.lower()
    if target_format not in STYLE_PRESETS:
        target_format = "nature"

    theme_rc = copy.deepcopy(STYLE_PRESETS[target_format])

    # 2. font_scale 적용 (크기와 관련된 값들에 배율 곱하기)
    if not isinstance(font_scale, (int, float)) or font_scale <= 0:
        raise ValueError(f"font_scale must be a positive number, got {font_scale!r}")
    if font_scale != 1.0:
        keys_to_scale_font = [
            "font.size",
            "axes.labelsize",
            "axes.titlesize",
            "legend.fontsize",
            "xtick.labelsize",
            "ytick.labelsize",
        ]
        # 선 굵기는 너무 굵어지지 않도록 배율의 0.7 배 정도만 적용하거나 동일하게 적용
        keys_to_scale_line = [
            "axes.linewidth",
            "grid.linewidth",
            "lines.linewidth",
            "patch.linewidth",
            "xtick.major.width",
            "ytick.major.width",
        ]

        for k in keys_to_scale_font:
            if k in theme_rc:
                theme_rc[k] = theme_rc[k] * font_scale

        line_scale = 1.0 + (font_scale - 1.0) * 0.7
        for k in keys_to_scale_line:
            if k in theme_rc:
                theme_rc[k] = theme_rc[k] * line_scale

    # 2.5. 런타임 폰트 해상도 (프로필보다 먼저 적용하여 프로필이 우선)
    _apply_runtime_font_resolution(theme_rc)

    # 2.6. profile별 rc override 적용 (최종 우선)
    resolved_profile = resolve_profile_name(profile_name)
    profile_rc, _ = get_profile_rc_overrides(resolved_profile)
    if profile_rc:
        theme_rc.update(profile_rc)

    compliance_tokens = _journal_compliance_tokens(target_format, resolved_profile)
    _clamp_rc_to_journal_compliance(theme_rc, compliance_tokens)

    # 2.7. SVG Baseline Alignment Correction (Zenith Audit Fix)
    # Matplotlib's default SVG path rendering can sometimes shift baselines.
    # We force mathtext depth to be accounted for more strictly in SVG export.
    theme_rc["svg.fonttype"] = "none"
    if os.environ.get("PUB_QUALITY", "false").lower() == "true":
        theme_rc["savefig.dpi"] = 1200  # Extreme resolution for submission
        theme_rc["mathtext.fallback"] = None

    # 2.8. CVD-safe Palette (Okabe-Ito) Injection
    # Zenith Masterpiece: All journal plots must be CVD-safe by default.
    theme_rc["axes.prop_cycle"] = cycler(color=get_palette("Okabe-Ito"))

    # 3. 전역 적용
    plt.rcParams.update(theme_rc)
    _ACTIVE_FONT_TOKENS = _font_tokens_from_rc(target_format, theme_rc, font_scale, resolved_profile)
    _ACTIVE_TARGET_FORMAT = target_format
    _ACTIVE_COMPLIANCE_TOKENS = compliance_tokens


# 별칭 (Sulfur 프로젝트 호환성)
apply_journal_style = apply_journal_theme


def set_figure_size(width_mm, height_mm=None, ratio=0.8):
    """mm 단위로 figure 크기를 설정합니다."""
    if height_mm is None:
        height_mm = width_mm * ratio
    return (mm_to_inch(width_mm), mm_to_inch(height_mm))


# 별칭 (Sulfur 프로젝트 호환성)
get_figsize = set_figure_size


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


def _safe_geometry_diagnostics_inline(fig) -> dict:
    """Run geometry diagnostics in the same frame that holds the live figure.

    Never raises: a diagnostics-engine error degrades to a passed:null stub so the
    worker's broad except can never hard-fail an already-saved figure. The wall-clock
    budget skip reads ONLY GEOMETRY_DIAGNOSTICS_DEADLINE against a fixed floor;
    MCP_RENDER_TIMEOUT_SECONDS is a module constant in mcp_surface and is never in
    os.environ, so it must not be read here.
    """
    try:
        from hub_core.geometry_diagnostics import SCHEMA_VERSION, diagnose_figure_geometry

        deadline = float(os.environ.get("GEOMETRY_DIAGNOSTICS_DEADLINE", "inf"))
        if deadline - time.time() < DIAG_BUDGET_FLOOR_SECONDS:
            return {
                "schema_version": SCHEMA_VERSION,
                "passed": None,
                "checks": [],
                "warnings": ["skipped: render budget"],
            }
        data_axes = [
            axis for axis in fig.axes if axis.get_visible() and getattr(axis, "_graph_hub_role", None) != "colorbar"
        ]
        layout_locked = getattr(fig, _LAYOUT_LOCK_ATTR, None) is not None
        return diagnose_figure_geometry(
            fig,
            data_axes,
            layout_locked=layout_locked,
            font_token_sizes=_active_font_token_sizes(),
            journal_compliance=_ACTIVE_COMPLIANCE_TOKENS,
        )
    except Exception as exc:
        from hub_core.geometry_diagnostics import SCHEMA_VERSION

        return {"schema_version": SCHEMA_VERSION, "passed": None, "checks": [], "warnings": [str(exc)]}


def _active_font_token_sizes() -> list[float]:
    return list(_ACTIVE_FONT_TOKENS.as_dict().values())


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def save_journal_fig(
    fig,
    filename,
    *,
    companion_formats: tuple[str, ...] = ("png",),
    preset: str | None = None,
    tiff_companion: bool = True,
    auto_declutter: bool | None = None,
    **kwargs,
):
    """
    Format-aware deterministic save wrapper.
    PDF uses CreationDate/ModDate, while SVG suppresses Date metadata for stable output.
    If filename is .pdf, companion files are generated per companion_formats (png, tiff).

    Layout-locked figures use rc_context to suppress savefig.bbox='tight' from rcParams,
    because passing bbox_inches=None in kwargs still falls back to rcParams in matplotlib.

    If preset is in TIFF_AUTO_PRESETS and tiff_companion is True, a 300 DPI LZW-compressed
    TIFF companion is saved alongside any primary format (unless primary is already TIFF).
    """
    import contextlib

    layout_lock = getattr(fig, _LAYOUT_LOCK_ATTR, None)
    if layout_lock:
        kwargs.pop("bbox_inches", None)
        save_ctx = plt.rc_context({"savefig.bbox": None, "savefig.pad_inches": 0})
    else:
        kwargs.setdefault("bbox_inches", "tight")
        save_ctx = contextlib.nullcontext()

    metadata = kwargs.pop("metadata", {}) or {}
    file_path = Path(filename)
    suffix = file_path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        kwargs.setdefault("dpi", 600)

    # 도구 버전 정보 차단 — 환경별 바이너리 해시 불일치 방지
    metadata.setdefault("Creator", None)
    metadata.pop("Producer", None)
    metadata.pop("Software", None)

    if suffix == ".svg":
        metadata.pop("CreationDate", None)
        metadata.pop("ModDate", None)
        metadata.setdefault("Date", None)
    else:
        metadata.setdefault("CreationDate", None)
        metadata.setdefault("ModDate", None)

    if auto_declutter is None:
        auto_declutter = _env_truthy("GRAPH_HUB_AUTO_DECLUTTER")

    with save_ctx:
        if auto_declutter:
            _declutter_text_artists(fig)
        _clamp_figure_artists_to_journal_compliance(fig, _ACTIVE_COMPLIANCE_TOKENS)
        fig.savefig(filename, metadata=metadata, **kwargs)

        # Geometry diagnostics: run once, AFTER the primary artifact is durably written,
        # so a slow/timed-out diagnostics pass can never cost the figure. Sidecar is
        # addressed by GEOMETRY_DIAGNOSTICS_OUT; absent => no-op (athena_bridge/standalone).
        diagnostics_out = os.environ.get("GEOMETRY_DIAGNOSTICS_OUT")
        if diagnostics_out:
            diag = _safe_geometry_diagnostics_inline(fig)
            try:
                Path(diagnostics_out).write_text(json.dumps(diag), encoding="utf-8")
            except Exception:
                pass  # writing the sidecar must never fail the save

        # Companion file generation for PDF outputs
        if suffix == ".pdf":
            if "png" in companion_formats:
                png_kwargs = copy.deepcopy(kwargs)
                png_kwargs["dpi"] = 600
                fig.savefig(file_path.with_suffix(".png"), **png_kwargs)

            if "tiff" in companion_formats:
                tiff_kwargs = copy.deepcopy(kwargs)
                tiff_kwargs["dpi"] = 600
                tiff_kwargs["pil_kwargs"] = {"compression": "tiff_lzw"}
                fig.savefig(file_path.with_suffix(".tiff"), **tiff_kwargs)

        # Auto TIFF companion for journal presets
        _preset = (preset or "").lower()
        if tiff_companion and _preset in TIFF_AUTO_PRESETS and suffix != ".tiff" and "tiff" not in companion_formats:
            tiff_path = file_path.with_suffix(".tiff")
            fig.savefig(
                str(tiff_path),
                dpi=300,
                format="tiff",
                bbox_inches="tight",
                pil_kwargs={"compression": "tiff_lzw"},
            )
