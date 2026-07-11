"""Journal compliance clamp helpers for rcParams and figure artists."""

from __future__ import annotations

import warnings


def _positive_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number

def _clamp_rc_to_journal_compliance(theme_rc: dict, compliance_tokens: dict[str, float | str] | None) -> None:
    if not compliance_tokens:
        return

    target_format = str(compliance_tokens["target_format"])
    min_font = float(compliance_tokens["min_font_size_pt"])
    min_line = float(compliance_tokens["min_line_width_pt"])
    font_keys = [
        "font.size",
        "axes.labelsize",
        "axes.titlesize",
        "legend.fontsize",
        "legend.title_fontsize",
        "xtick.labelsize",
        "ytick.labelsize",
    ]
    line_keys = [
        "axes.linewidth",
        "lines.linewidth",
        "lines.markeredgewidth",
    ]

    font_changes: list[str] = []
    for key in font_keys:
        value = _positive_float(theme_rc.get(key))
        if value is not None and value < min_font:
            theme_rc[key] = min_font
            font_changes.append(f"{key} {value:g}->{min_font:g}")
    if font_changes:
        warnings.warn(
            f"journal compliance: clamped {target_format} font rcParams to the {min_font:g} pt floor "
            f"({', '.join(font_changes)})",
            RuntimeWarning,
            stacklevel=3,
        )

    line_changes: list[str] = []
    for key in line_keys:
        value = _positive_float(theme_rc.get(key))
        if value is not None and value < min_line:
            theme_rc[key] = min_line
            line_changes.append(f"{key} {value:g}->{min_line:g}")
    if line_changes:
        warnings.warn(
            f"journal compliance: clamped {target_format} line rcParams to the {min_line:g} pt floor "
            f"({', '.join(line_changes)})",
            RuntimeWarning,
            stacklevel=3,
        )


def _is_visible_artist(artist) -> bool:
    if artist is None or not artist.get_visible():
        return False
    alpha = artist.get_alpha()
    return alpha is None or alpha > 0.01


def _clamp_artist_font(text, min_font: float) -> bool:
    if text is None or not text.get_text() or not _is_visible_artist(text):
        return False
    size = _positive_float(text.get_fontsize())
    if size is not None and size + 0.01 < min_font:
        text.set_fontsize(min_font)
        return True
    return False


def _clamp_artist_linewidth(artist, min_line: float) -> int:
    if artist is None or not _is_visible_artist(artist):
        return 0
    if not hasattr(artist, "get_linewidth") or not hasattr(artist, "set_linewidth"):
        return 0
    value = _positive_float(artist.get_linewidth())
    if value is not None and value + 0.001 < min_line:
        artist.set_linewidth(min_line)
        return 1
    return 0


def _clamp_collection_linewidths(collection, min_line: float) -> int:
    if collection is None or not _is_visible_artist(collection):
        return 0
    if not hasattr(collection, "get_linewidths") or not hasattr(collection, "set_linewidth"):
        return 0
    linewidths = list(collection.get_linewidths())
    if not linewidths:
        return 0
    changed = 0
    clamped = []
    for linewidth in linewidths:
        value = _positive_float(linewidth)
        if value is not None and value + 0.001 < min_line:
            clamped.append(min_line)
            changed += 1
        else:
            clamped.append(linewidth)
    if changed:
        collection.set_linewidth(clamped)
    return changed


def _clamp_figure_artists_to_journal_compliance(fig, compliance_tokens: dict[str, float | str] | None) -> None:
    if not compliance_tokens:
        return

    target_format = str(compliance_tokens["target_format"])
    min_font = float(compliance_tokens["min_font_size_pt"])
    min_line = float(compliance_tokens["min_line_width_pt"])
    font_changes = 0
    line_changes = 0

    for ax in fig.axes:
        text_artists = [
            ax.title,
            ax.xaxis.label,
            ax.yaxis.label,
            *ax.get_xticklabels(),
            *ax.get_yticklabels(),
            *ax.texts,
        ]
        legend = ax.get_legend()
        if legend is not None and _is_visible_artist(legend):
            text_artists.extend(legend.get_texts())
            text_artists.append(legend.get_title())
        for text in text_artists:
            if _clamp_artist_font(text, min_font):
                font_changes += 1

        for line in ax.get_lines():
            line_changes += _clamp_artist_linewidth(line, min_line)
        for collection in ax.collections:
            line_changes += _clamp_collection_linewidths(collection, min_line)
        for patch in ax.patches:
            line_changes += _clamp_artist_linewidth(patch, min_line)
        for spine in ax.spines.values():
            line_changes += _clamp_artist_linewidth(spine, min_line)

    if font_changes or line_changes:
        warnings.warn(
            f"journal compliance: clamped {target_format} artist sizes to journal floors "
            f"({font_changes} font artist(s) to >= {min_font:g} pt; "
            f"{line_changes} line artist(s) to >= {min_line:g} pt)",
            RuntimeWarning,
            stacklevel=3,
        )
