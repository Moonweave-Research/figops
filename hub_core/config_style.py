"""Style and preset resolution helpers for project configuration."""

from __future__ import annotations

INTERNAL_STYLE_TARGET_FORMAT = "_".join(("nature", "surfur"))

ALLOWED_TARGET_FORMATS = {
    "nature",
    INTERNAL_STYLE_TARGET_FORMAT,
    "science",
    "ppt",
    "default",
    "acs",
    "rsc",
    "elsevier",
    "wiley",
    "cell",
}
ALLOWED_FONT_STRATEGIES = {"compensate", "as_is"}
ALLOWED_PRESET_KEYS = {
    "target_format",
    "font_scale",
    "profile",
    "output_format",
    "colormap",
}

try:
    from themes.style_profiles import PROFILE_ALIASES, list_profiles, resolve_profile_name

    KNOWN_STYLE_PROFILES = set(list_profiles())
    KNOWN_STYLE_PROFILE_KEYS = set(list_profiles()) | set(PROFILE_ALIASES.keys())
except Exception:

    def resolve_profile_name(profile_name=None):
        if profile_name is None:
            return "baseline"
        key = str(profile_name).strip().lower()
        return key if key else "baseline"

    def list_profiles():
        return ["baseline"]

    PROFILE_ALIASES = {"default": "baseline", "base": "baseline"}
    KNOWN_STYLE_PROFILES = {"baseline"}
    KNOWN_STYLE_PROFILE_KEYS = {"baseline", "default", "base"}


def resolve_presets(config: dict) -> dict:
    raw = config.get("presets", {})
    if raw is None:
        raw = {}

    default_name: str | None = raw.get("_default", None)

    visual_style = config.get("visual_style", {}) or {}
    base = {
        "target_format": visual_style.get("target_format"),
        "font_scale": visual_style.get("font_scale"),
        "profile": visual_style.get("profile"),
    }

    result: dict = {"__default_name__": default_name}
    for preset_name, preset_vals in raw.items():
        if preset_name == "_default":
            continue
        merged = {key: value for key, value in base.items() if value is not None}
        if isinstance(preset_vals, dict):
            merged.update(preset_vals)
        result[preset_name] = merged

    return result


def resolve_step_style(
    step_cfg: dict,
    config: dict,
    resolved_presets: dict | None = None,
) -> dict:
    visual_style = config.get("visual_style", {}) or {}
    result = {
        "target_format": visual_style.get("target_format"),
        "font_scale": visual_style.get("font_scale"),
        "profile": visual_style.get("profile"),
        "output_format": None,
        "colormap": None,
    }

    if resolved_presets is not None:
        preset_key = step_cfg.get("preset")
        if preset_key is not None:
            preset_vals = resolved_presets.get(preset_key, {})
            result.update({key: value for key, value in preset_vals.items() if not key.startswith("__")})
        elif resolved_presets.get("__default_name__"):
            default_key = resolved_presets["__default_name__"]
            preset_vals = resolved_presets.get(default_key, {})
            result.update({key: value for key, value in preset_vals.items() if not key.startswith("__")})

    if "theme" in step_cfg:
        result["target_format"] = step_cfg["theme"]
    if "target_format" in step_cfg:
        result["target_format"] = step_cfg["target_format"]
    if "font_scale" in step_cfg:
        result["font_scale"] = step_cfg["font_scale"]
    if "profile" in step_cfg:
        result["profile"] = step_cfg["profile"]
    if "format" in step_cfg:
        result["output_format"] = step_cfg["format"]
    if "output_format" in step_cfg:
        result["output_format"] = step_cfg["output_format"]
    if "colormap" in step_cfg:
        result["colormap"] = step_cfg["colormap"]

    return result
