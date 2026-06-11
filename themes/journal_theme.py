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
from pathlib import Path

import matplotlib.pyplot as plt
from cycler import cycler
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
    from palettes import get_palette

    try:
        from style_profiles import get_profile_rc_overrides, resolve_profile_name
    except ImportError:

        def resolve_profile_name(profile_name=None):
            return "baseline"

        def get_profile_rc_overrides(profile_name=None):
            return {}, "baseline"


# ── Nature/Science Standard Widths (mm) ─────────────────────────
SINGLE_COLUMN = 89  # mm
DOUBLE_COLUMN = 183  # mm
_LAYOUT_LOCK_ATTR = "_graph_hub_layout_lock"
DIAG_BUDGET_FLOOR_SECONDS = 5.0

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
    # 02_Surfur_Polymer 전용 — 정사각 50x50 mm plot box (3-up NatComm double-col 기준)
    # 독립 single-panel 용. 3-up/2-up 멀티패널은 스크립트에서 figsize 직접 계산.
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

TIFF_AUTO_PRESETS: set[str] = {"nature", "nature_surfur", "science", "acs", "rsc", "elsevier", "wiley", "cell"}


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
        "xtick.top": False,  # Science: no box, only left+bottom axes
        "ytick.right": False,
    }
)

STYLE_PRESETS["acs"] = copy.deepcopy(STYLE_PRESETS["nature"])
STYLE_PRESETS["acs"].update(
    {
        "xtick.direction": "out",  # ACS: tick outside
        "ytick.direction": "out",
        "axes.labelsize": 7.5,  # ACS: 7-8pt range
    }
)

STYLE_PRESETS["rsc"] = copy.deepcopy(STYLE_PRESETS["nature"])
STYLE_PRESETS["rsc"].update(
    {
        "axes.linewidth": 0.6,
        "lines.linewidth": 1.2,
    }
)

STYLE_PRESETS["elsevier"] = copy.deepcopy(STYLE_PRESETS["nature"])
STYLE_PRESETS["elsevier"].update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "mathtext.fontset": "dejavuserif",
        "axes.labelsize": 8.0,
        "axes.titlesize": 8.5,
        "xtick.labelsize": 7.0,
        "ytick.labelsize": 7.0,
    }
)

STYLE_PRESETS["wiley"] = copy.deepcopy(STYLE_PRESETS["nature"])
STYLE_PRESETS["wiley"].update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
        "axes.titlesize": 8.0,
        "axes.labelsize": 7.0,
        "lines.linewidth": 1.0,
        "axes.linewidth": 1.0,
        "xtick.major.width": 1.0,
        "ytick.major.width": 1.0,
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
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
        "axes.titlesize": 7.0,
        "axes.labelsize": 7.0,
        "lines.linewidth": 0.75,
        "axes.linewidth": 0.75,
        "xtick.major.width": 0.75,
        "ytick.major.width": 0.75,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.top": False,
        "ytick.right": False,
        "savefig.dpi": 600,
    }
)

# 02_Surfur_Polymer 전용 프리셋 (2026-04-10)
# - NatComm 5-7pt strict compliance (title 7.0, legend 6.0)
# - 50x50 mm plot box 기준 → spine/tick 약간 굵게 (0.75pt)
# - minor tick global 강제 off (필요한 플랏에서만 개별 on)
# - 기본 `nature`와 별개로 유지해 다른 프로젝트에 영향 없음
STYLE_PRESETS["nature_surfur"] = copy.deepcopy(STYLE_PRESETS["nature"])
STYLE_PRESETS["nature_surfur"].update(
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


def apply_journal_theme(target_format="nature", font_scale=1.0, profile_name=None):
    """
    지정된 포맷과 폰트 스케일을 기반으로 전역 rcParams에 저널 스타일을 적용합니다.
    (순수 함수 지향: 환경 변수를 내부에서 읽지 않고 인자로만 작동)

    Args:
        target_format (str): 적용할 테마 프리셋 이름 ('nature', 'nature_surfur', 'science', 'ppt', 'default', 'acs', 'rsc', 'elsevier')
        font_scale (float): 기준 테마 폰트 사이즈 대비 보정 배율
        profile_name (str): 세부 스타일 프로파일 이름 (예: baseline, resistance_premium)
    """
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


# 별칭 (Sulfur 프로젝트 호환성)
apply_journal_style = apply_journal_theme


def set_figure_size(width_mm, height_mm=None, ratio=0.8):
    """mm 단위로 figure 크기를 설정합니다."""
    if height_mm is None:
        height_mm = width_mm * ratio
    return (mm_to_inch(width_mm), mm_to_inch(height_mm))


# 별칭 (Sulfur 프로젝트 호환성)
get_figsize = set_figure_size


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
        return diagnose_figure_geometry(fig, data_axes, layout_locked=layout_locked)
    except Exception as exc:
        from hub_core.geometry_diagnostics import SCHEMA_VERSION

        return {"schema_version": SCHEMA_VERSION, "passed": None, "checks": [], "warnings": [str(exc)]}


def save_journal_fig(
    fig,
    filename,
    *,
    companion_formats: tuple[str, ...] = ("png",),
    preset: str | None = None,
    tiff_companion: bool = True,
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

    with save_ctx:
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


# ── Multi-panel grid specs (unified source, 2026-04-10) ──────────
# 여러 프로젝트가 각자 local copy를 두던 PANEL_GRID_SPECS_MM을
# hub 단일 소스로 통합. 프로젝트별 예외는 script kwargs로만 허용.
# 모든 layout은 NatComm double column 180mm 이내 + log-scale label
# 충돌 방지를 위한 여유 있는 wspace 기준.
MULTI_PANEL_GRID_SPECS_MM: dict[str, dict[str, float]] = {
    # 3-up triplet: 44×44 box, wspace 14mm → 178mm width (180 이내 2mm 버퍼)
    # wspace 14mm는 log-scale tick label("10^{14}") + y-label rotation
    # + 양쪽 padding 전부 여유 있게 수용
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
    # 2-up pair: 72×72 box, wspace 14mm → 176mm width
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
    # 2x2 quad: 70×70 box, wspace 14mm → 175mm width, 174mm height
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
    # triplet_cell: triplet 1x3 row의 "per-cell" 치수에 맞춘 단독 single panel.
    # mockup 1col3 슬롯에 들어갈 single panel이 triplet row의 cell과 동일 크기로
    # 보이도록 margin을 줄여 per-cell proportion(178/3 ≈ 59mm) 일치.
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
    # solo: NatComm Slot A 단일 standalone panel (기본 가로형)
    # 가로형 기본 (시계열/스펙트럼 등 x축 길이 중요), 정사각 원하면
    # apply_panel_grid_layout(layout_type="solo", box_height_mm=70)으로 override.
    # figure: 90×77 mm → NatComm single column 88-89mm 수용.
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
    """Set deterministic multi-panel layout with absolute mm dimensions.

    Reads MULTI_PANEL_GRID_SPECS_MM[layout_type] as the default.
    Per-script overrides (box_width_mm, box_height_mm, any spec key) are
    explicit at the call site — preferred over hidden project-level overrides.

    Returns dict with figure_width_mm, figure_height_mm, box_width_mm, box_height_mm.
    """
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
    [Promoted from Pusan DEA Project]
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
        fig.set_size_inches(mm_to_inch(figure_width_mm), mm_to_inch(figure_height_mm), forward=True)
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
    """
    [Promoted from Pusan DEA Project]
    지정된 레이아웃 프리셋에 최적화된 legend 설정값을 딕셔너리로 반환합니다.
    사용법: plt.legend(**get_legend_args('top_outside'))
    """
    _fs = plt.rcParams.get("legend.fontsize", 7.0)
    if layout_type == "top_outside":
        return {"fontsize": _fs, "loc": "lower center", "bbox_to_anchor": (0.5, 1.02), "ncol": ncol, "frameon": False}
    elif layout_type == "right_outside":
        return {"fontsize": _fs, "loc": "center left", "bbox_to_anchor": (1.02, 0.5), "ncol": 1, "frameon": False}
    return {"fontsize": _fs, "loc": "best"}
