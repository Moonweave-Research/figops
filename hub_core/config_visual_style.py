"""Validation for project visual-style and named-preset configuration."""

from __future__ import annotations

from collections.abc import Mapping

_CURRENT_STRUCTURE_CONTRACT = "figops-project-v1.1"
_JOURNAL_TARGETS = {
    "acs": "acs",
    "cell": "cell",
    "elsevier": "elsevier",
    "nature": "nature",
    "nature communications": "nature",
    "rsc": "rsc",
    "science": "science",
    "wiley": "wiley",
}


def _journal_validation_target(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return _JOURNAL_TARGETS.get(value.strip().lower())


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
        structure = config.get("structure", {})
        current_contract = (
            isinstance(structure, Mapping) and structure.get("contract") == _CURRENT_STRUCTURE_CONTRACT
        )
        implicit_render_policy = "neutral" if current_contract else "nature"
        target_format = visual_style.get("target_format", implicit_render_policy)
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

        render_policy = visual_style.get("render_policy")
        if render_policy is not None:
            if not isinstance(render_policy, str) or render_policy.strip().lower() not in allowed_target_formats:
                allowed = ", ".join(sorted(allowed_target_formats))
                errors.append(f"Invalid visual_style.render_policy: '{render_policy}'. Allowed values: {allowed}.")
            elif "target_format" in visual_style and isinstance(target_format, str):
                if render_policy.strip().lower() != target_format.strip().lower():
                    errors.append(
                        "visual_style.render_policy and legacy visual_style.target_format must select "
                        "the same rendering policy when both are provided."
                    )

        validation_target = visual_style.get("validation_target")
        if validation_target is not None and (
            not isinstance(validation_target, str)
            or validation_target.strip().lower() not in allowed_target_formats - {"neutral", "default", "ppt"}
        ):
            allowed = ", ".join(sorted(allowed_target_formats - {"neutral", "default", "ppt"}))
            errors.append(
                f"Invalid visual_style.validation_target: '{validation_target}'. Allowed values: {allowed}."
            )

        project = config.get("project", {})
        target_journal = project.get("target_journal") if isinstance(project, Mapping) else None
        if target_journal is not None and (not isinstance(target_journal, str) or not target_journal.strip()):
            errors.append("project.target_journal must be a non-empty string when provided.")
        expected_target = _journal_validation_target(target_journal)
        if expected_target is not None and isinstance(validation_target, str):
            if validation_target.strip().lower() != expected_target:
                errors.append(
                    "project.target_journal and visual_style.validation_target are inconsistent: "
                    f"{target_journal!r} requires {expected_target!r}."
                )


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
