from __future__ import annotations

import os
from collections.abc import Callable

NormalizeLang = Callable[[object], str]


def validate_visual_outputs(
    errors: list[str],
    items: object,
    *,
    section_name: str,
    norm_policy: dict,
    normalize_lang_func: NormalizeLang,
    allowed_target_formats: set[str],
    allowed_output_formats: set[str],
    preset_names: set | None = None,
    sample_ids: set[str] | None = None,
    condition_ids: set[str] | None = None,
    require_traceability: bool = False,
) -> None:
    if items is None:
        items = []
    if not isinstance(items, list):
        errors.append(f"Invalid '{section_name}' section (must be a list).")
        return

    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append(f"{section_name}[{i}] must be a mapping.")
            continue
        script = item.get("script")
        output = item.get("output")
        lang = normalize_lang_func(item.get("lang"))

        if lang != "athena":
            if not isinstance(script, str) or not script.strip():
                errors.append(f"{section_name}[{i}].script is required.")

        if not isinstance(output, str) or not output.strip():
            errors.append(f"{section_name}[{i}].output is required for output verification.")

        claim = item.get("claim")
        if claim is not None and (not isinstance(claim, str) or not claim.strip()):
            errors.append(f"{section_name}[{i}].claim must be a non-empty string when provided.")

        trace_samples = item.get("samples", [])
        if trace_samples is None:
            trace_samples = []
        if not isinstance(trace_samples, list):
            errors.append(f"{section_name}[{i}].samples must be a list when provided.")
            trace_samples = []
        else:
            valid_trace_samples = []
            for sample_index, sample in enumerate(trace_samples, 1):
                if not isinstance(sample, str) or not sample.strip():
                    errors.append(f"{section_name}[{i}].samples[{sample_index}] must be a non-empty string.")
                    continue
                valid_trace_samples.append(sample.strip())
            if sample_ids is not None:
                unknown_samples = sorted(sample for sample in valid_trace_samples if sample not in sample_ids)
                if unknown_samples:
                    errors.append(
                        f"{section_name}[{i}].samples references unknown sample_id(s): "
                        f"{', '.join(unknown_samples)}."
                    )

        trace_conditions = item.get("conditions", [])
        if trace_conditions is None:
            trace_conditions = []
        if not isinstance(trace_conditions, list):
            errors.append(f"{section_name}[{i}].conditions must be a list when provided.")
            trace_conditions = []
        else:
            valid_trace_conditions = []
            for condition_index, condition in enumerate(trace_conditions, 1):
                if not isinstance(condition, str) or not condition.strip():
                    errors.append(f"{section_name}[{i}].conditions[{condition_index}] must be a non-empty string.")
                    continue
                valid_trace_conditions.append(condition.strip())
            if condition_ids is not None:
                unknown_conditions = sorted(
                    condition for condition in valid_trace_conditions if condition not in condition_ids
                )
                if unknown_conditions:
                    errors.append(
                        f"{section_name}[{i}].conditions references unknown condition id(s): "
                        f"{', '.join(unknown_conditions)}."
                    )

        has_traceability_declaration = any(
            key in item and item.get(key) is not None for key in ("claim", "samples", "conditions")
        )
        if require_traceability and has_traceability_declaration:
            missing = []
            if not isinstance(claim, str) or not claim.strip():
                missing.append("claim")
            if not trace_samples:
                missing.append("samples")
            if not trace_conditions:
                missing.append("conditions")
            if missing:
                figure_id = item.get("id") if isinstance(item.get("id"), str) and item.get("id").strip() else f"#{i}"
                missing_text = ", ".join(f"missing {field}" for field in missing)
                errors.append(f"{section_name}[{i}] '{figure_id}' {missing_text} for traceability.")

        inputs = item.get("inputs", None)
        if inputs is not None and not isinstance(inputs, list):
            errors.append(f"{section_name}[{i}].inputs must be a list.")
        elif isinstance(inputs, list):
            for inp in inputs:
                if isinstance(inp, str):
                    if os.path.isabs(inp):
                        errors.append(f"{section_name}[{i}].inputs: absolute path '{inp}' is not allowed.")
                    elif ".." in inp.replace("\\", "/").split("/"):
                        errors.append(f"{section_name}[{i}].inputs: path traversal '..' in '{inp}' is not allowed.")
        if "cache" in item and not isinstance(item.get("cache"), bool):
            errors.append(f"{section_name}[{i}].cache must be a boolean.")
        if "theme" in item:
            theme = item.get("theme")
            if not isinstance(theme, str) or theme.strip().lower() not in allowed_target_formats:
                allowed = ", ".join(sorted(allowed_target_formats))
                errors.append(f"{section_name}[{i}].theme must be one of: {allowed}.")
        if "format" in item:
            output_format = item.get("format")
            if not isinstance(output_format, str) or output_format.strip().lower() not in allowed_output_formats:
                allowed = ", ".join(sorted(allowed_output_formats))
                errors.append(f"{section_name}[{i}].format must be one of: {allowed}.")
        if preset_names is not None and "preset" in item:
            item_preset = item.get("preset")
            if item_preset not in preset_names:
                errors.append(f"{section_name}[{i}].preset '{item_preset}' references an undefined preset.")
        expand = item.get("expand")
        if expand is not None and expand not in ("batch", "each"):
            errors.append(f"{section_name}[{i}].expand must be 'batch' or 'each'.")
        if expand == "each" and isinstance(output, str) and "{stem}" not in output:
            errors.append(f"{section_name}[{i}].output must contain '{{stem}}' placeholder when expand='each'.")
        if not norm_policy["allow_nonstandard"] and isinstance(script, str) and script.strip():
            item_lang = normalize_lang_func(item.get("lang"))
            if not item_lang:
                item_lang = "r" if script.lower().endswith(".r") else "python"
            if item_lang != norm_policy["plot_lang"]:
                errors.append(
                    f"{section_name}[{i}] language '{item_lang}' violates policy "
                    f"(plot must be '{norm_policy['plot_lang']}')."
                )
