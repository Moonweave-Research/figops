from __future__ import annotations

import itertools
import os

from .execution_security import is_reserved_execution_env_key, output_pattern_error


def validate_sweep(sweep: dict) -> list[str]:
    errors: list[str] = []

    if not isinstance(sweep, dict):
        errors.append("sweep must be a mapping.")
        return errors

    enabled = sweep.get("enabled", False)
    if not isinstance(enabled, bool):
        errors.append("sweep.enabled must be a boolean.")

    has_values = "values" in sweep
    has_grid = "grid" in sweep

    if has_values and has_grid:
        errors.append("sweep: specify either 'values' or 'grid', not both.")

    if has_values:
        parameter = sweep.get("parameter")
        if not isinstance(parameter, str) or not parameter.strip():
            errors.append("sweep.parameter is required and must be a non-empty string when 'values' is used.")
        elif is_reserved_execution_env_key(parameter):
            errors.append(f"sweep.parameter is a reserved execution environment key: {parameter!r}.")
        values = sweep.get("values")
        if not isinstance(values, list) or len(values) == 0:
            errors.append("sweep.values must be a non-empty list.")
        elif any(not isinstance(v, (int, float, str)) for v in values):
            errors.append("sweep.values entries must be numbers or strings.")

    if has_grid:
        grid = sweep.get("grid")
        if not isinstance(grid, dict) or len(grid) == 0:
            errors.append("sweep.grid must be a non-empty mapping.")
        else:
            for param_name, param_values in grid.items():
                if not isinstance(param_name, str) or not param_name.strip():
                    errors.append("sweep.grid keys must be non-empty strings.")
                elif is_reserved_execution_env_key(param_name):
                    errors.append(f"sweep.grid.{param_name} is a reserved execution environment key.")
                if not isinstance(param_values, list) or len(param_values) == 0:
                    errors.append(f"sweep.grid.{param_name} must be a non-empty list.")
                elif any(not isinstance(v, (int, float, str)) for v in param_values):
                    errors.append(f"sweep.grid.{param_name} entries must be numbers or strings.")

    output_dir_pattern = sweep.get("output_dir_pattern")
    if output_dir_pattern is not None:
        if not isinstance(output_dir_pattern, str) or not output_dir_pattern.strip():
            errors.append("sweep.output_dir_pattern must be a non-empty string.")
        else:
            pattern_error = output_pattern_error(output_dir_pattern)
            if pattern_error is not None:
                errors.append(f"sweep.output_dir_pattern {pattern_error}.")

    return errors


def validate_comparison(comparison: dict) -> list[str]:
    errors: list[str] = []

    if not isinstance(comparison, dict):
        errors.append("comparison must be a mapping.")
        return errors

    enabled = comparison.get("enabled", False)
    if not isinstance(enabled, bool):
        errors.append("comparison.enabled must be a boolean.")

    conditions = comparison.get("conditions", [])
    if conditions is None:
        conditions = []
    if not isinstance(conditions, list):
        errors.append("comparison.conditions must be a list.")
    else:
        for i, cond in enumerate(conditions, 1):
            if not isinstance(cond, dict):
                errors.append(f"comparison.conditions[{i}] must be a mapping.")
                continue
            label = cond.get("label")
            if not isinstance(label, str) or not label.strip():
                errors.append(f"comparison.conditions[{i}].label is required and must be a non-empty string.")
            data_override = cond.get("data_override")
            if data_override is not None:
                if not isinstance(data_override, str) or not data_override.strip():
                    errors.append(f"comparison.conditions[{i}].data_override must be a non-empty string.")
                elif os.path.isabs(data_override):
                    errors.append(
                        f"comparison.conditions[{i}].data_override must be a relative path, "
                        f"got absolute: '{data_override}'."
                    )
                elif ".." in data_override.replace("\\", "/").split("/"):
                    errors.append(
                        f"comparison.conditions[{i}].data_override contains path traversal '..': '{data_override}'."
                    )
            env = cond.get("env", {})
            if env is not None and not isinstance(env, dict):
                errors.append(f"comparison.conditions[{i}].env must be a mapping.")
            elif isinstance(env, dict):
                for key, val in env.items():
                    if not isinstance(key, str):
                        errors.append(f"comparison.conditions[{i}].env keys must be strings.")
                    elif is_reserved_execution_env_key(key):
                        errors.append(
                            f"comparison.conditions[{i}].env.{key} is a reserved execution environment key."
                        )
                    if not isinstance(val, (str, int, float, bool)):
                        errors.append(
                            f"comparison.conditions[{i}].env.{key} value must be a scalar (str/int/float/bool)."
                        )

    overlay_output = comparison.get("overlay_output")
    if overlay_output is not None:
        if not isinstance(overlay_output, str) or not overlay_output.strip():
            errors.append("comparison.overlay_output must be a non-empty string.")
        elif os.path.isabs(overlay_output):
            errors.append("comparison.overlay_output must be a relative path.")
        elif ".." in overlay_output.replace("\\", "/").split("/"):
            errors.append("comparison.overlay_output contains path traversal '..'.")

    return errors


def parse_comparison_config(comparison: dict) -> dict:
    """Return a normalized comparison config with a flat list of condition dicts."""
    enabled = bool(comparison.get("enabled", False))
    conditions: list[dict] = []
    for cond in comparison.get("conditions", []) or []:
        conditions.append(
            {
                "label": str(cond.get("label", "")).strip(),
                "data_override": cond.get("data_override"),
                "env": {str(k): str(v) for k, v in (cond.get("env") or {}).items()},
            }
        )
    overlay_output: str | None = comparison.get("overlay_output")
    return {
        "enabled": enabled,
        "conditions": conditions,
        "overlay_output": overlay_output,
    }


def parse_sweep_config(sweep: dict) -> dict:
    """Return a normalized sweep config with a flat list of (env_var, value) runs."""
    enabled = bool(sweep.get("enabled", False))
    output_dir_pattern = sweep.get("output_dir_pattern", "results/figures/sweep_{parameter}_{value}")

    runs: list[dict[str, str]] = []

    if "values" in sweep:
        parameter = sweep["parameter"].strip()
        for value in sweep["values"]:
            runs.append({parameter: str(value)})
    elif "grid" in sweep:
        grid = sweep["grid"]
        param_names = list(grid.keys())
        param_value_lists = [grid[k] for k in param_names]
        for combo in itertools.product(*param_value_lists):
            runs.append({name: str(val) for name, val in zip(param_names, combo)})

    return {
        "enabled": enabled,
        "output_dir_pattern": output_dir_pattern,
        "runs": runs,
    }
