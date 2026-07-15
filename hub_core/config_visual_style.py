"""Validation for project visual-style and named-preset configuration."""


def validate_visual_style(
    errors: list[str],
    config: dict,
    *,
    allowed_target_formats: set[str],
    known_style_profile_keys: set[str],
    known_style_profiles: set[str],
) -> None:
    """Validate project-level visual defaults."""
    visual_style = config.get("visual_style", {})
    if visual_style is None:
        visual_style = {}
    if not isinstance(visual_style, dict):
        errors.append("Invalid 'visual_style' section (must be a mapping).")
    else:
        target_format = visual_style.get("target_format", "nature")
        if not isinstance(target_format, str) or target_format.lower() not in allowed_target_formats:
            allowed = ", ".join(sorted(allowed_target_formats))
            errors.append(f"Invalid visual_style.target_format: '{target_format}'. Allowed values: {allowed}.")

        font_scale = visual_style.get("font_scale", 1.0)
        if isinstance(font_scale, bool) or not isinstance(font_scale, (int, float)) or font_scale <= 0:
            errors.append("visual_style.font_scale must be a positive number.")

        profile_name = visual_style.get("profile", "baseline")
        if not isinstance(profile_name, str) or not profile_name.strip():
            errors.append("visual_style.profile must be a non-empty string.")
        else:
            profile_key = profile_name.strip().lower()
            if known_style_profile_keys and profile_key not in known_style_profile_keys:
                allowed_profiles = ", ".join(sorted(known_style_profiles))
                errors.append(f"Invalid visual_style.profile: '{profile_name}'. Allowed values: {allowed_profiles}.")


def validate_presets(
    errors: list[str],
    config: dict,
    *,
    allowed_target_formats: set[str],
    allowed_output_formats: set[str],
    allowed_preset_keys: set[str],
) -> set:
    """Validate named visual presets, returning their defined names."""
    presets_raw = config.get("presets", {})
    if presets_raw is None:
        presets_raw = {}
    if not isinstance(presets_raw, dict):
        errors.append("Invalid 'presets' section (must be a mapping).")
    else:
        defined_preset_names = {key for key in presets_raw if key != "_default"}
        default_preset = presets_raw.get("_default")
        if default_preset is not None and default_preset not in defined_preset_names:
            errors.append(f"presets._default '{default_preset}' references an undefined preset.")
        for preset_name, preset_vals in presets_raw.items():
            if preset_name == "_default":
                continue
            if not isinstance(preset_vals, dict):
                errors.append(f"presets.{preset_name} must be a mapping.")
                continue
            bad_keys = set(preset_vals.keys()) - allowed_preset_keys
            if bad_keys:
                allowed = ", ".join(sorted(allowed_preset_keys))
                errors.append(
                    f"presets.{preset_name} contains unknown keys: {', '.join(sorted(bad_keys))}. Allowed: {allowed}."
                )
            if "target_format" in preset_vals:
                target_format = preset_vals["target_format"]
                if not isinstance(target_format, str) or target_format.lower() not in allowed_target_formats:
                    allowed = ", ".join(sorted(allowed_target_formats))
                    errors.append(
                        f"presets.{preset_name}.target_format '{target_format}' is invalid. Allowed: {allowed}."
                    )
            if "font_scale" in preset_vals:
                font_scale = preset_vals["font_scale"]
                if (
                    isinstance(font_scale, bool)
                    or not isinstance(font_scale, (int, float))
                    or not (0.5 <= font_scale <= 3.0)
                ):
                    errors.append(f"presets.{preset_name}.font_scale must be a number in [0.5, 3.0].")
            if "profile" in preset_vals:
                profile = preset_vals["profile"]
                if not isinstance(profile, str) or not profile.strip():
                    errors.append(f"presets.{preset_name}.profile must be a non-empty string.")
            if "output_format" in preset_vals:
                output_format = preset_vals["output_format"]
                if not isinstance(output_format, str) or output_format.strip().lower() not in allowed_output_formats:
                    allowed = ", ".join(sorted(allowed_output_formats))
                    errors.append(
                        f"presets.{preset_name}.output_format '{output_format}' is invalid. Allowed: {allowed}."
                    )

    return {key for key in presets_raw if key != "_default"} if isinstance(presets_raw, dict) else set()
