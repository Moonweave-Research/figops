"""Journal compliance clamp helpers for rcParams and figure artists."""

from __future__ import annotations

import hashlib
import json
import os
import warnings
from pathlib import Path

_FALLBACK_SANS_FONTS = ["Arial", "Helvetica", "Liberation Sans", "DejaVu Sans"]


def apply_runtime_font_resolution(theme_rc: dict) -> None:
    """Normalize the requested sans/math font stack without reading environment state."""
    preferred = theme_rc.get("font.sans-serif")
    sans_fonts = preferred if isinstance(preferred, list) else _FALLBACK_SANS_FONTS
    sans_fonts = list(dict.fromkeys(sans_fonts))
    if "DejaVu Sans" not in sans_fonts:
        sans_fonts.append("DejaVu Sans")
    theme_rc["font.sans-serif"] = sans_fonts
    primary_font = sans_fonts[0]
    if theme_rc.get("mathtext.fontset") != "custom":
        return
    if primary_font == "DejaVu Sans":
        theme_rc["mathtext.fontset"] = "dejavusans"
        for key in ("mathtext.rm", "mathtext.it", "mathtext.bf"):
            theme_rc.pop(key, None)
        return
    theme_rc["mathtext.rm"] = primary_font
    theme_rc["mathtext.it"] = f"{primary_font}:italic"
    theme_rc["mathtext.bf"] = f"{primary_font}:bold"


def resolved_font_token_values(theme_rc: dict, fallback) -> dict[str, float]:
    """Read the active theme's semantic font sizes into a constructor-ready mapping."""
    axis = float(theme_rc.get("axes.labelsize", fallback.axis))
    tick = float(theme_rc.get("xtick.labelsize", theme_rc.get("ytick.labelsize", fallback.tick)))
    return {
        "tag": float(theme_rc.get("axes.titlesize", fallback.tag)),
        "label": axis,
        "annot": axis,
        "legend": float(theme_rc.get("legend.fontsize", fallback.legend)),
        "axis": axis,
        "tick": tick,
    }


def resolve_journal_compliance_tokens(
    target_format: str,
    profile_name: str,
) -> dict[str, float | str] | None:
    """Resolve the selected journal policy without coupling it to theme state."""
    try:
        from .style_profiles import get_render_style_tokens
    except ImportError:  # direct ``themes`` path compatibility
        from style_profiles import get_render_style_tokens

    render_tokens, meta = get_render_style_tokens(target_format, profile_name)
    required_keys = ("min_font_size_pt", "min_line_width_pt", "max_figure_height_mm")
    if not all(key in render_tokens for key in required_keys):
        return None
    return {
        "target_format": meta["target_format"],
        "profile": meta["profile"],
        "policy_id": f"journal-{meta['target_format']}/{meta['profile']}",
        "min_font_size_pt": float(render_tokens["min_font_size_pt"]),
        "min_line_width_pt": float(render_tokens["min_line_width_pt"]),
        "max_figure_height_mm": float(render_tokens["max_figure_height_mm"]),
    }


def _positive_float(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number

def _mutation(
    *,
    transform: str,
    target: str,
    before,
    after,
    policy_id: str,
    reason: str,
) -> dict:
    digest = hashlib.sha256(f"{transform}\0{target}\0{before!r}\0{after!r}".encode()).hexdigest()[:16]
    return {
        "mutation_id": f"style-{digest}",
        "transform": transform,
        "mode": "explicit",
        "before": before,
        "after": after,
        "policy_id": policy_id,
        "reason": f"{reason}; target={target}",
    }


def _clamp_rc_to_journal_compliance(
    theme_rc: dict,
    compliance_tokens: dict[str, float | str] | None,
) -> list[dict]:
    if not compliance_tokens:
        return []

    target_format = str(compliance_tokens["target_format"])
    policy_id = str(compliance_tokens["policy_id"])
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
    ledger: list[dict] = []
    for key in font_keys:
        value = _positive_float(theme_rc.get(key))
        if value is not None and value < min_font:
            theme_rc[key] = min_font
            font_changes.append(f"{key} {value:g}->{min_font:g}")
            ledger.append(
                _mutation(
                    transform="compliance_clamp",
                    target=f"rcParams.{key}",
                    before=value,
                    after=min_font,
                    policy_id=policy_id,
                    reason="explicit font-floor clamp",
                )
            )
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
            ledger.append(
                _mutation(
                    transform="compliance_clamp",
                    target=f"rcParams.{key}",
                    before=value,
                    after=min_line,
                    policy_id=policy_id,
                    reason="explicit line-floor clamp",
                )
            )
    if line_changes:
        warnings.warn(
            f"journal compliance: clamped {target_format} line rcParams to the {min_line:g} pt floor "
            f"({', '.join(line_changes)})",
            RuntimeWarning,
            stacklevel=3,
        )
    return ledger


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


def _clamp_figure_artists_to_journal_compliance(
    fig,
    compliance_tokens: dict[str, float | str] | None,
) -> list[dict]:
    if not compliance_tokens:
        return []

    target_format = str(compliance_tokens["target_format"])
    policy_id = str(compliance_tokens["policy_id"])
    min_font = float(compliance_tokens["min_font_size_pt"])
    min_line = float(compliance_tokens["min_line_width_pt"])
    font_changes = 0
    line_changes = 0
    ledger: list[dict] = []

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
        for text_index, text in enumerate(text_artists):
            before = _positive_float(text.get_fontsize()) if text is not None else None
            if _clamp_artist_font(text, min_font):
                font_changes += 1
                ledger.append(
                    _mutation(
                        transform="compliance_clamp",
                        target=f"axes[{fig.axes.index(ax)}].text[{text_index}].fontsize",
                        before=before,
                        after=min_font,
                        policy_id=policy_id,
                        reason="explicit font-floor clamp",
                    )
                )

        artist_groups = (
            ("line", list(ax.get_lines())),
            ("patch", list(ax.patches)),
            ("spine", list(ax.spines.values())),
        )
        for role, artists in artist_groups:
            for index, artist in enumerate(artists):
                before = _positive_float(artist.get_linewidth())
                changed = _clamp_artist_linewidth(artist, min_line)
                line_changes += changed
                if changed:
                    ledger.append(
                        _mutation(
                            transform="compliance_clamp",
                            target=f"axes[{fig.axes.index(ax)}].{role}[{index}].linewidth",
                            before=before,
                            after=min_line,
                            policy_id=policy_id,
                            reason="explicit line-floor clamp",
                        )
                    )
        for index, collection in enumerate(ax.collections):
            before = [float(item) for item in collection.get_linewidths()]
            changed = _clamp_collection_linewidths(collection, min_line)
            line_changes += changed
            if changed:
                ledger.append(
                    _mutation(
                        transform="compliance_clamp",
                        target=f"axes[{fig.axes.index(ax)}].collection[{index}].linewidths",
                        before=before,
                        after=[float(item) for item in collection.get_linewidths()],
                        policy_id=policy_id,
                        reason="explicit line-floor clamp",
                    )
                )

    if font_changes or line_changes:
        warnings.warn(
            f"journal compliance: clamped {target_format} artist sizes to journal floors "
            f"({font_changes} font artist(s) to >= {min_font:g} pt; "
            f"{line_changes} line artist(s) to >= {min_line:g} pt)",
            RuntimeWarning,
            stacklevel=3,
        )
    return ledger


def apply_explicit_save_mutations(
    fig,
    *,
    compliance_mode: str,
    compliance_tokens: dict[str, float | str] | None,
    declutter_mode: str,
) -> tuple[list[dict], dict | None]:
    """Apply only caller-selected save-time mutations and return their evidence."""
    ledger: list[dict] = []
    declutter_evidence = None
    if declutter_mode == "declutter":
        try:
            from .declutter import _declutter_text_artists
        except ImportError:  # direct ``themes`` path compatibility
            from declutter import _declutter_text_artists

        declutter_evidence = _declutter_text_artists(fig)
        ledger.extend(declutter_evidence.get("mutation_ledger", []))
    if compliance_mode == "clamp":
        ledger.extend(_clamp_figure_artists_to_journal_compliance(fig, compliance_tokens))
    fig._graph_hub_mutation_ledger = list(ledger)
    fig._graph_hub_declutter_evidence = declutter_evidence
    return ledger, declutter_evidence


def append_authored_output_evidence(
    *,
    mutation_ledger: list[dict] | None = None,
    compliance: dict | None = None,
    declutter: dict | None = None,
) -> None:
    """Append explicit authored-output changes to the render sidecar."""
    sidecar = str(os.environ.get("AUTHORED_OUTPUT_EVIDENCE_OUT") or "").strip()
    if not sidecar:
        return
    path = Path(sidecar)
    payload = {"mode": "raw", "mappings": [], "collisions": [], "mutation_ledger": []}
    if path.is_file():
        payload.update(json.loads(path.read_text(encoding="utf-8")))
    combined = [*payload.get("mutation_ledger", []), *(mutation_ledger or [])]
    payload["mutation_ledger"] = list({item["mutation_id"]: item for item in combined}.values())
    if compliance is not None:
        payload["compliance"] = compliance
    if declutter is not None:
        payload["declutter"] = declutter
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
