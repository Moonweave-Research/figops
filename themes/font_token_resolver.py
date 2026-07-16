"""Font-token presets and scale/profile resolution for journal themes."""

from __future__ import annotations

from typing import Any, Callable


def build_font_token_presets(token_type: Callable[..., Any], internal_target: str) -> dict[str, Any]:
    """Build immutable role-token objects while leaving their public type facade-owned."""
    return {
        # Neutral follows the active Matplotlib defaults and exists only so
        # authored-output helpers have semantic fallbacks without selecting a
        # journal aesthetic.
        "neutral": token_type(tag=12.0, label=10.0, annot=10.0, legend=10.0, axis=10.0, tick=10.0),
        "nature": token_type(tag=8.0, label=6.0, annot=6.0, legend=7.0, axis=7.0, tick=6.0),
        # Science/AAAS figure guidance uses Helvetica/Arial-family lettering.
        "science": token_type(tag=8.0, label=7.0, annot=7.0, legend=7.0, axis=7.0, tick=6.5),
        # ACS uses readable 7 pt body/axis text and 6.5 pt ticks.
        "acs": token_type(tag=8.0, label=7.0, annot=7.0, legend=7.0, axis=7.0, tick=6.5),
        # RSC stays at its 7 pt minimum font floor.
        "rsc": token_type(tag=8.0, label=7.0, annot=7.0, legend=7.0, axis=7.0, tick=7.0),
        # Elsevier main lettering uses 7 pt body/axis/tick text.
        "elsevier": token_type(tag=8.0, label=7.0, annot=7.0, legend=7.0, axis=7.0, tick=7.0),
        # Wiley keeps 7 pt body/axis text and 6.5 pt ticks.
        "wiley": token_type(tag=8.0, label=7.0, annot=7.0, legend=7.0, axis=7.0, tick=6.5),
        # Cell Press uses readable 7 pt body/axis lettering with 6.5 pt ticks.
        "cell": token_type(tag=8.0, label=7.0, annot=7.0, legend=7.0, axis=7.0, tick=6.5),
        internal_target: token_type(tag=6.0, label=5.0, annot=6.0, legend=6.0, axis=7.0, tick=6.0),
        "ppt": token_type(tag=16.0, label=12.0, annot=12.0, legend=12.0, axis=14.0, tick=12.0),
        "default": token_type(tag=8.0, label=6.0, annot=6.0, legend=7.0, axis=7.0, tick=6.0),
    }


def resolve_font_tokens(
    target: str,
    font_scale: float,
    profile_name: Any,
    *,
    presets: dict[str, Any],
    token_type: Callable[..., Any],
    get_profile_rc_overrides: Callable[..., tuple[dict[str, Any], str]],
    resolve_profile_name: Callable[[Any], str],
) -> Any:
    """Resolve a facade-owned token object from target, scale, and profile."""
    target_key = str(target or "nature").lower()
    tokens = presets.get(target_key, presets["nature"])
    if not isinstance(font_scale, (int, float)) or font_scale <= 0:
        raise ValueError(f"font_scale must be a positive number, got {font_scale!r}")
    if font_scale == 1.0:
        scaled = tokens
    else:
        scaled = token_type(
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
    return token_type(
        tag=resolved_tag,
        label=resolved_axis,
        annot=resolved_axis,
        legend=resolved_legend,
        axis=resolved_axis,
        tick=resolved_tick,
    )
