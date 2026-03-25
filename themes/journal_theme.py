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
import os
from pathlib import Path

import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
from matplotlib import font_manager

try:
    # Package import path: from themes.journal_theme import ...
    from .palettes import WT_COLORS, get_palette
    try:
        from .style_profiles import get_profile_rc_overrides, resolve_profile_name
    except ImportError:
        from style_profiles import get_profile_rc_overrides, resolve_profile_name
except ImportError:
    # Backward compatibility for direct path import: sys.path += ['themes']
    from palettes import WT_COLORS, get_palette
    try:
        from style_profiles import get_profile_rc_overrides, resolve_profile_name
    except ImportError:
        def resolve_profile_name(profile_name=None):
            return "baseline"

        def get_profile_rc_overrides(profile_name=None):
            return {}, "baseline"

# ── Nature/Science Standard Widths (mm) ─────────────────────────
SINGLE_COLUMN = 89    # mm
DOUBLE_COLUMN = 183   # mm

def mm_to_inch(mm):
    return mm / 25.4

# ── Style Presets Dictionary ─────────────────────────────────────
# 하드코딩된 설정을 딕셔너리 기반으로 추상화하여 의존성 없는 테마 엔진 구축
STYLE_PRESETS = {
    'nature': {
        "font.family":         "sans-serif",
        "font.sans-serif":     ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
        "mathtext.fontset":    "custom",
        "mathtext.rm":         "Arial",
        "mathtext.it":         "Arial:italic",
        "mathtext.bf":         "Arial:bold",

        # Font Sizes (Nature standard: 5~7pt strictly, 8pt only for 'a', 'b', 'c' panel tags)
        "axes.titlesize":      7.5,
        "axes.titleweight":    "normal",
        "axes.labelsize":      7.0,
        "axes.labelweight":    "normal",
        "legend.fontsize":     7.0,
        "xtick.labelsize":     6.0,
        "ytick.labelsize":     6.0,

        # Line Weights
        "axes.linewidth":      0.5,
        "grid.linewidth":      0.3,
        "lines.linewidth":     1.0,
        "patch.linewidth":     0.5,
        "xtick.major.width":   0.4,
        "ytick.major.width":   0.4,

        # Grid & Ticks
        "axes.grid":           False,
        "xtick.direction":     "in",
        "ytick.direction":     "in",
        "xtick.top":           True,
        "ytick.right":         True,
        "xtick.minor.visible": True,
        "ytick.minor.visible": True,
        "xtick.minor.width":   0.3,
        "ytick.minor.width":   0.3,
        "xtick.minor.size":    2.0,
        "ytick.minor.size":    2.0,
        "xtick.major.size":    3.5,
        "ytick.major.size":    3.5,
        "xtick.major.pad":     3.0,
        "ytick.major.pad":     3.0,

        # Legend
        "legend.frameon":      False,
        "legend.loc":          "best",

        # Output
        "savefig.dpi":         600,
        "savefig.format":      "pdf",
        "savefig.bbox":        "tight",
        "svg.fonttype":        "path",
        "pdf.fonttype":        42,
        "ps.fonttype":         42
    },
    'ppt': {
        "font.family":         "sans-serif",
        "font.sans-serif":     ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],

        # Font Sizes (PPT에 맞춰 확대된 기본값)
        "axes.labelsize":      14.0,
        "axes.titlesize":      16.0,
        "legend.fontsize":     12.0,
        "xtick.labelsize":     12.0,
        "ytick.labelsize":     12.0,

        # Line Weights (PPT에 맞춰 굵은 선)
        "axes.linewidth":      1.5,
        "grid.linewidth":      1.0,
        "lines.linewidth":     2.0,
        "patch.linewidth":     1.5,
        "xtick.major.width":   1.2,
        "ytick.major.width":   1.2,

        # Grid & Ticks
        "axes.grid":           False,
        "xtick.direction":     "out",
        "ytick.direction":     "out",
        "xtick.top":           False,
        "ytick.right":         False,

        # Legend
        "legend.frameon":      False,
        "legend.loc":          "best",

        # Output
        "savefig.dpi":         300,
        "savefig.format":      "png",
        "savefig.bbox":        "tight",
        "svg.fonttype":        "path",
        "pdf.fonttype":        42,
        "ps.fonttype":         42
    }
}
# science 테마는 nature와 호환, default도 nature로 처리
STYLE_PRESETS['science'] = copy.deepcopy(STYLE_PRESETS['nature'])
STYLE_PRESETS['default'] = copy.deepcopy(STYLE_PRESETS['nature'])

_FALLBACK_SANS_FONTS = ["Arial", "Helvetica", "Liberation Sans", "DejaVu Sans"]


def _available_font_names():
    return {entry.name for entry in font_manager.fontManager.ttflist}


def _resolve_sans_fonts(preferred_fonts):
    preferred = preferred_fonts if isinstance(preferred_fonts, list) else _FALLBACK_SANS_FONTS
    available = _available_font_names()
    resolved = [font for font in preferred if font in available]
    if not resolved:
        resolved = ["DejaVu Sans"]
    elif "DejaVu Sans" not in resolved:
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


def apply_journal_theme(target_format='nature', font_scale=1.0, profile_name=None):
    """
    지정된 포맷과 폰트 스케일을 기반으로 전역 rcParams에 저널 스타일을 적용합니다.
    (순수 함수 지향: 환경 변수를 내부에서 읽지 않고 인자로만 작동)

    Args:
        target_format (str): 적용할 테마 프리셋 이름 ('nature', 'science', 'ppt', 'default')
        font_scale (float): 기준 테마 폰트 사이즈 대비 보정 배율
        profile_name (str): 세부 스타일 프로파일 이름 (예: baseline, resistance_premium)
    """
    # 1. 포맷 가져오기 (fallback: nature)
    target_format = target_format.lower()
    if target_format not in STYLE_PRESETS:
        target_format = 'nature'

    theme_rc = copy.deepcopy(STYLE_PRESETS[target_format])

    # 2. font_scale 적용 (크기와 관련된 값들에 배율 곱하기)
    if font_scale != 1.0:
        keys_to_scale_font = [
            'axes.labelsize', 'axes.titlesize', 'legend.fontsize',
            'xtick.labelsize', 'ytick.labelsize'
        ]
        # 선 굵기는 너무 굵어지지 않도록 배율의 0.7 배 정도만 적용하거나 동일하게 적용
        keys_to_scale_line = [
            'axes.linewidth', 'grid.linewidth', 'lines.linewidth',
            'patch.linewidth', 'xtick.major.width', 'ytick.major.width'
        ]

        for k in keys_to_scale_font:
            if k in theme_rc:
                theme_rc[k] = theme_rc[k] * font_scale

        line_scale = 1.0 + (font_scale - 1.0) * 0.7
        for k in keys_to_scale_line:
            if k in theme_rc:
                theme_rc[k] = theme_rc[k] * line_scale

    # 2.5. profile별 rc override 적용
    resolved_profile = resolve_profile_name(profile_name)
    profile_rc, _ = get_profile_rc_overrides(resolved_profile)
    if profile_rc:
        theme_rc.update(profile_rc)

    _apply_runtime_font_resolution(theme_rc)

    # 2.7. SVG Baseline Alignment Correction (Zenith Audit Fix)
    # Matplotlib's default SVG path rendering can sometimes shift baselines.
    # We force mathtext depth to be accounted for more strictly in SVG export.
    theme_rc["svg.fonttype"] = "path"
    if os.environ.get("PUB_QUALITY", "false").lower() == "true":
        theme_rc["savefig.dpi"] = 1200  # Extreme resolution for submission
        # When in high quality mode, we can use 'none' for svg to keep text editable,
        # but the request asks to maintain 'path' while fixing the jump.
        # We ensure mathtext.fallback is set to None to avoid mixing font types.
        theme_rc["mathtext.fallback"] = None

    # 3. 전역 적용
    plt.rcParams.update(theme_rc)

# 별칭 (Sulfur 프로젝트 호환성)
apply_journal_style = apply_journal_theme

def set_figure_size(width_mm, height_mm=None, ratio=0.8):
    """mm 단위로 figure 크기를 설정합니다."""
    if height_mm is None:
        height_mm = width_mm * ratio
    return (mm_to_inch(width_mm), mm_to_inch(height_mm))

# 별칭 (Sulfur 프로젝트 호환성)
get_figsize = set_figure_size


def save_journal_fig(fig, filename, **kwargs):
    """
    Format-aware deterministic save wrapper.
    PDF uses CreationDate/ModDate, while SVG suppresses Date metadata for stable output.
    If filename is .pdf, it also saves a .png version for Word compatibility.
    """
    kwargs.setdefault('bbox_inches', 'tight')
    metadata = kwargs.pop('metadata', {}) or {}
    file_path = Path(filename)
    suffix = file_path.suffix.lower()

    if suffix == ".svg":
        metadata.pop('CreationDate', None)
        metadata.pop('ModDate', None)
        metadata.setdefault('Date', None)
    else:
        metadata.setdefault('CreationDate', None)
        metadata.setdefault('ModDate', None)

    # Save original
    fig.savefig(filename, metadata=metadata, **kwargs)

    # Word compatibility: Save high-res PNG if original is PDF
    if suffix == ".pdf":
        png_filename = file_path.with_suffix(".png")
        # Ensure high resolution for Word (600 DPI for line art/plots)
        png_kwargs = copy.deepcopy(kwargs)
        png_kwargs['dpi'] = 600
        fig.savefig(png_filename, **png_kwargs)


def apply_publication_layout(layout_type='top_outside'):
    """
    [Promoted from Pusan DEA Project]
    모든 그래프의 Axes(데이터 박스) 크기를 강제로 일치시키는 전역 레이아웃 설정 프리셋.
    개별 스크립트에서 plt.subplots_adjust()를 직접 호출하는 대신 사용합니다.
    """
    if layout_type == 'top_outside':
        # 상단 범례(TOP LEGEND)를 낼 때 가장 예쁜 데이터 박스 크기 고정값
        plt.subplots_adjust(left=0.18, right=0.95, bottom=0.22, top=0.76)
    elif layout_type == 'right_outside':
        # 우측 범례용 고정값
        plt.subplots_adjust(left=0.15, right=0.75, bottom=0.18, top=0.92)
    elif layout_type == 'standard':
        # 일반적인 정방형/직사각형 배치
        plt.subplots_adjust(left=0.15, right=0.95, bottom=0.15, top=0.90)


def get_legend_args(layout_type='top_outside', ncol=2):
    """
    [Promoted from Pusan DEA Project]
    지정된 레이아웃 프리셋에 최적화된 legend 설정값을 딕셔너리로 반환합니다.
    사용법: plt.legend(**get_legend_args('top_outside'))
    """
    _fs = plt.rcParams.get('legend.fontsize', 7.0)
    if layout_type == 'top_outside':
        return {
            'fontsize': _fs,
            'loc': 'lower center',
            'bbox_to_anchor': (0.5, 1.02),
            'ncol': ncol,
            'frameon': False
        }
    elif layout_type == 'right_outside':
        return {
            'fontsize': _fs,
            'loc': 'center left',
            'bbox_to_anchor': (1.02, 0.5),
            'ncol': 1,
            'frameon': False
        }
    return {'fontsize': _fs, 'loc': 'best'}
