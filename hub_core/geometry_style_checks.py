"""Font-token and journal style checks for geometry diagnostics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure


ALPHA_EPS = 0.01
MAX_REPORTED_STYLE_FINDINGS = 50


def _is_paintable_artist(artist: Any) -> bool:
    if not artist.get_visible():
        return False
    alpha = artist.get_alpha()
    return alpha is None or alpha > ALPHA_EPS


def _visible_tick_labels(labels: list[Any]) -> list[Any]:
    return [text for text in labels if text.get_text() and _is_paintable_artist(text)]


def _default_font_token_sizes(data_axes: list[Axes]) -> list[float]:
    sizes: set[float] = set()
    for ax in data_axes:
        for artist in (ax.xaxis.label, ax.yaxis.label):
            if artist is not None and _is_paintable_artist(artist):
                sizes.add(round(float(artist.get_fontsize()), 2))
        for text in [
            *_visible_tick_labels(list(ax.get_xticklabels())),
            *_visible_tick_labels(list(ax.get_yticklabels())),
        ]:
            sizes.add(round(float(text.get_fontsize()), 2))
        legend = ax.get_legend()
        if legend is not None and _is_paintable_artist(legend):
            for text in legend.get_texts():
                if text.get_text() and _is_paintable_artist(text):
                    sizes.add(round(float(text.get_fontsize()), 2))
    return sorted(sizes)


def _font_size_matches_token(size: float, token_sizes: list[float], *, tolerance: float = 0.05) -> bool:
    return any(abs(size - token) <= tolerance for token in token_sizes)


def _font_size_token_drift(data_axes: list[Axes], font_token_sizes: list[float] | None) -> dict[str, Any]:
    name = "font_size_token_drift"
    token_sizes = sorted({round(float(size), 2) for size in (font_token_sizes or []) if float(size) > 0})
    if not token_sizes:
        token_sizes = _default_font_token_sizes(data_axes)
    if not token_sizes:
        return {
            "name": name,
            "passed": True,
            "detail": "skipped: no font token sizes",
            "data": {"token_sizes": []},
        }

    offenders: list[dict[str, Any]] = []
    role_sizes: dict[str, set[float]] = {"text": set(), "axis": set(), "legend": set(), "tick": set()}
    for axis_index, ax in enumerate(data_axes):
        for text in ax.texts:
            if not text.get_text() or not _is_paintable_artist(text):
                continue
            size = round(float(text.get_fontsize()), 2)
            role_sizes["text"].add(size)
            if not _font_size_matches_token(size, token_sizes):
                offenders.append({"axes": int(axis_index), "role": "text", "text": text.get_text(), "fontsize": size})
        for role, artist in (("axis", ax.xaxis.label), ("axis", ax.yaxis.label)):
            if artist is None or not artist.get_text() or not _is_paintable_artist(artist):
                continue
            size = round(float(artist.get_fontsize()), 2)
            role_sizes[role].add(size)
            if not _font_size_matches_token(size, token_sizes):
                offenders.append({"axes": int(axis_index), "role": role, "text": artist.get_text(), "fontsize": size})
        for text in [
            *_visible_tick_labels(list(ax.get_xticklabels())),
            *_visible_tick_labels(list(ax.get_yticklabels())),
        ]:
            size = round(float(text.get_fontsize()), 2)
            role_sizes["tick"].add(size)
            if not _font_size_matches_token(size, token_sizes):
                offenders.append({"axes": int(axis_index), "role": "tick", "text": text.get_text(), "fontsize": size})
        legend = ax.get_legend()
        if legend is not None and _is_paintable_artist(legend):
            for text in legend.get_texts():
                if not text.get_text() or not _is_paintable_artist(text):
                    continue
                size = round(float(text.get_fontsize()), 2)
                role_sizes["legend"].add(size)
                if not _font_size_matches_token(size, token_sizes):
                    offenders.append(
                        {"axes": int(axis_index), "role": "legend", "text": text.get_text(), "fontsize": size}
                    )

    role_size_counts = {role: len(sizes) for role, sizes in role_sizes.items() if sizes}
    divergent_roles = sorted(role for role, count in role_size_counts.items() if count > 1)
    if len(offenders) > MAX_REPORTED_STYLE_FINDINGS:
        offenders = offenders[:MAX_REPORTED_STYLE_FINDINGS]
        truncated = True
    else:
        truncated = False
    return {
        "name": name,
        "passed": len(offenders) == 0 and not divergent_roles,
        "detail": (
            f"{len(offenders)} text artists use non-token font sizes; divergent roles: "
            f"{', '.join(divergent_roles) or 'none'}"
        ),
        "data": {
            "token_sizes": token_sizes,
            "offenders": offenders,
            "offenders_truncated": bool(truncated),
            "role_size_counts": role_size_counts,
            "divergent_roles": divergent_roles,
        },
    }


def _journal_compliance(fig: Figure, data_axes: list[Axes], compliance: dict[str, Any]) -> dict[str, Any]:
    name = "journal_compliance"
    target_format = str(compliance.get("target_format", "unknown"))
    min_font = float(compliance["min_font_size_pt"])
    min_line = float(compliance["min_line_width_pt"])
    max_height = float(compliance["max_figure_height_mm"])
    figure_height_mm = float(fig.get_size_inches()[1] * 25.4)

    font_offenders = _journal_font_offenders(data_axes, min_font)
    line_offenders = _journal_line_offenders(data_axes, min_line)
    height_offender = figure_height_mm > max_height + 0.01
    passed = not font_offenders and not line_offenders and not height_offender
    return {
        "name": name,
        "passed": bool(passed),
        "detail": (
            f"{target_format}: {len(font_offenders)} font offenders below {min_font:g} pt; "
            f"{len(line_offenders)} line offenders below {min_line:g} pt; "
            f"height {figure_height_mm:.2f}/{max_height:g} mm"
        ),
        "data": {
            "target_format": target_format,
            "min_font_size_pt": min_font,
            "min_line_width_pt": min_line,
            "max_figure_height_mm": max_height,
            "figure_height_mm": figure_height_mm,
            "font_offenders": font_offenders,
            "line_offenders": line_offenders,
            "height_offender": bool(height_offender),
        },
    }


def _journal_font_offenders(data_axes: list[Axes], min_font: float) -> list[dict[str, Any]]:
    offenders: list[dict[str, Any]] = []
    for axis_index, ax in enumerate(data_axes):
        text_artists = [
            ("title", ax.title),
            ("axis", ax.xaxis.label),
            ("axis", ax.yaxis.label),
            *(("tick", text) for text in _visible_tick_labels(list(ax.get_xticklabels()))),
            *(("tick", text) for text in _visible_tick_labels(list(ax.get_yticklabels()))),
            *(("text", text) for text in ax.texts if text.get_text() and _is_paintable_artist(text)),
        ]
        legend = ax.get_legend()
        if legend is not None and _is_paintable_artist(legend):
            text_artists.extend(
                ("legend", text) for text in legend.get_texts() if text.get_text() and _is_paintable_artist(text)
            )
            title = legend.get_title()
            if title is not None and title.get_text() and _is_paintable_artist(title):
                text_artists.append(("legend", title))
        for role, text in text_artists:
            if text is None or not text.get_text() or not _is_paintable_artist(text):
                continue
            size = round(float(text.get_fontsize()), 2)
            if size + 0.01 < min_font:
                offenders.append({"axes": int(axis_index), "role": role, "text": text.get_text(), "fontsize": size})
                if len(offenders) >= MAX_REPORTED_STYLE_FINDINGS:
                    return offenders
    return offenders


def _journal_line_offenders(data_axes: list[Axes], min_line: float) -> list[dict[str, Any]]:
    offenders: list[dict[str, Any]] = []
    for axis_index, ax in enumerate(data_axes):
        for index, line in enumerate(ax.get_lines()):
            if _is_paintable_artist(line):
                _append_linewidth_offender(offenders, axis_index, "line", index, line.get_linewidth(), min_line)
        for index, coll in enumerate(ax.collections):
            if _is_paintable_artist(coll):
                for linewidth in _line_width_values(coll.get_linewidths()):
                    _append_linewidth_offender(offenders, axis_index, "collection", index, linewidth, min_line)
        for index, patch in enumerate(ax.patches):
            if _is_paintable_artist(patch):
                _append_linewidth_offender(offenders, axis_index, "patch", index, patch.get_linewidth(), min_line)
        for spine_name, spine in ax.spines.items():
            if _is_paintable_artist(spine):
                _append_linewidth_offender(
                    offenders,
                    axis_index,
                    f"spine:{spine_name}",
                    0,
                    spine.get_linewidth(),
                    min_line,
                )
        if len(offenders) >= MAX_REPORTED_STYLE_FINDINGS:
            return offenders[:MAX_REPORTED_STYLE_FINDINGS]
    return offenders


def _line_width_values(value: Any) -> list[float]:
    values = np.asarray(value, dtype=float).ravel()
    return [float(item) for item in values if np.isfinite(item)]


def _append_linewidth_offender(
    offenders: list[dict[str, Any]],
    axis_index: int,
    role: str,
    index: int,
    linewidth: Any,
    min_line: float,
) -> None:
    value = float(linewidth)
    if value <= 0:
        return
    rounded = round(value, 3)
    if rounded + 0.001 < min_line:
        offenders.append({"axes": int(axis_index), "role": role, "index": int(index), "linewidth": rounded})
