"""Detection for Matplotlib's unsupported mixed CJK + mathtext path."""

from __future__ import annotations

import re
import warnings
from typing import Any

_CJK_CHARACTER = re.compile(r"[\u1100-\u11ff\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff]")


def warn_for_mixed_cjk_mathtext(fig: Any) -> int:
    """Warn when a label combines CJK text with ``$...$`` mathtext.

    Matplotlib parses the complete string through mathtext in this case, which
    bypasses normal per-glyph CJK fallback.  Rendering still proceeds so the
    caller can choose how to split or replace the label.
    """

    texts: list[Any] = list(getattr(fig, "texts", ()) or ())
    for axis in getattr(fig, "axes", ()) or ():
        texts.extend(
            [
                getattr(axis, "title", None),
                axis.xaxis.label,
                axis.yaxis.label,
                *axis.get_xticklabels(),
                *axis.get_yticklabels(),
                *axis.texts,
            ]
        )
        legend = axis.get_legend()
        if legend is not None:
            texts.extend([*legend.get_texts(), legend.get_title()])

    seen: set[int] = set()
    count = 0
    for text_artist in texts:
        if text_artist is None or id(text_artist) in seen:
            continue
        seen.add(id(text_artist))
        try:
            text = str(text_artist.get_text())
        except Exception:
            continue
        if "$" in text and _CJK_CHARACTER.search(text):
            count += 1
    if count:
        warnings.warn(
            f"FigOps detected {count} CJK label(s) mixed with mathtext; Matplotlib cannot apply glyph fallback "
            "to that combined string. Split the label or replace simple mathtext with Unicode before submission.",
            RuntimeWarning,
            stacklevel=2,
        )
    return count


__all__ = ["warn_for_mixed_cjk_mathtext"]
