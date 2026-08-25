"""Runtime font fallback helpers for multilingual Matplotlib labels."""

from __future__ import annotations

import sys
from collections.abc import Iterable

_CJK_FONT_CANDIDATES = {
    "darwin": ("Apple SD Gothic Neo", "AppleGothic", "Noto Sans CJK KR", "Noto Sans KR"),
    "win32": ("Malgun Gothic", "맑은 고딕", "Noto Sans CJK KR", "Noto Sans KR", "NanumGothic"),
    "default": ("Noto Sans CJK KR", "Noto Sans KR", "NanumGothic", "Nanum Gothic", "Source Han Sans KR"),
}


def _installed_font_family_names() -> dict[str, str]:
    """Return installed Matplotlib font family names keyed case-insensitively."""

    try:
        from matplotlib import font_manager

        return {
            str(entry.name).casefold(): str(entry.name)
            for entry in font_manager.fontManager.ttflist
            if str(entry.name).strip()
        }
    except Exception:
        # Font discovery is an enhancement only.  Keep the existing portable
        # Latin stack if a stripped-down Matplotlib runtime cannot enumerate it.
        return {}


def installed_cjk_font_fallbacks() -> list[str]:
    """Return installed Korean/CJK family names in platform-preferred order."""

    installed = _installed_font_family_names()
    platform_key = "win32" if sys.platform.startswith("win") else sys.platform
    candidates = (*_CJK_FONT_CANDIDATES.get(platform_key, ()), *_CJK_FONT_CANDIDATES["default"])
    resolved: list[str] = []
    for candidate in candidates:
        actual = installed.get(candidate.casefold())
        if actual and actual not in resolved:
            resolved.append(actual)
    return resolved


def per_glyph_font_family(primary_fonts: Iterable[object]) -> list[str]:
    """Build a concrete family list, enabling Matplotlib per-glyph fallback."""

    families: list[str] = []
    for raw_name in (*primary_fonts, *installed_cjk_font_fallbacks()):
        name = str(raw_name).strip()
        if name and name not in families:
            families.append(name)
    return families


__all__ = ["installed_cjk_font_fallbacks", "per_glyph_font_family"]
