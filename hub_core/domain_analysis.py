from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


class DomainAnalysisError(ValueError):
    """Raised when a built-in domain analysis helper cannot run safely."""


def _reject_unknown_params(params: Mapping[str, Any], allowed: set[str], helper_name: str) -> None:
    unknown = sorted(set(params) - allowed)
    if unknown:
        raise DomainAnalysisError(f"{helper_name} received unknown params: {', '.join(unknown)}")


def _single_path(paths: Sequence[str], label: str, helper_name: str) -> Path:
    if len(paths) != 1:
        raise DomainAnalysisError(f"{helper_name} requires exactly one {label}, got {len(paths)}.")
    return Path(paths[0])


def _string_param(params: Mapping[str, Any], key: str, helper_name: str, default: str | None = None) -> str:
    value = params.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise DomainAnalysisError(f"{helper_name}.{key} must be a non-empty string.")
    return value.strip()


def _positive_int_param(params: Mapping[str, Any], key: str, helper_name: str, default: int) -> int:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DomainAnalysisError(f"{helper_name}.{key} must be a positive integer.")
    return value


def _number_param(params: Mapping[str, Any], key: str, helper_name: str, default: float) -> float:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainAnalysisError(f"{helper_name}.{key} must be a number.")
    return float(value)


def _read_csv(input_path: Path, helper_name: str):
    if not input_path.is_file():
        raise DomainAnalysisError(f"{helper_name} input CSV not found: {input_path}")
    try:
        import pandas as pd
    except ImportError as exc:
        raise DomainAnalysisError(f"{helper_name} requires pandas.") from exc
    try:
        return pd.read_csv(input_path)
    except Exception as exc:
        raise DomainAnalysisError(f"{helper_name} failed to read {input_path}: {type(exc).__name__}: {exc}") from exc


def _require_columns(df, columns: Sequence[str], helper_name: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise DomainAnalysisError(f"{helper_name} missing required columns: {', '.join(missing)}")


def _numeric_series(df, column: str, helper_name: str):
    import pandas as pd

    try:
        series = pd.to_numeric(df[column], errors="raise")
    except Exception as exc:
        raise DomainAnalysisError(f"{helper_name}.{column} must contain numeric values.") from exc
    if series.isna().any():
        raise DomainAnalysisError(f"{helper_name}.{column} contains null values.")
    return series


def _write_csv(df, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


def signal_smooth_baseline(input_paths: Sequence[str], output_paths: Sequence[str], params: Mapping[str, Any]) -> None:
    helper_name = "materials_polymer.signal_smooth_baseline"
    _reject_unknown_params(
        params,
        {
            "x_column",
            "y_column",
            "window",
            "baseline_method",
            "smoothed_column",
            "baseline_column",
            "corrected_column",
        },
        helper_name,
    )
    input_path = _single_path(input_paths, "input", helper_name)
    output_path = _single_path(output_paths, "output", helper_name)
    x_column = _string_param(params, "x_column", helper_name, "time_s")
    y_column = _string_param(params, "y_column", helper_name, "signal_au")
    smoothed_column = _string_param(params, "smoothed_column", helper_name, "smoothed_signal_au")
    baseline_column = _string_param(params, "baseline_column", helper_name, "baseline_au")
    corrected_column = _string_param(params, "corrected_column", helper_name, "corrected_signal_au")
    window = _positive_int_param(params, "window", helper_name, 5)
    baseline_method = _string_param(params, "baseline_method", helper_name, "rolling_min")
    if baseline_method not in {"first", "rolling_min"}:
        raise DomainAnalysisError(f"{helper_name}.baseline_method must be one of: first, rolling_min.")

    df = _read_csv(input_path, helper_name)
    _require_columns(df, [x_column, y_column], helper_name)
    _numeric_series(df, x_column, helper_name)
    y_values = _numeric_series(df, y_column, helper_name)

    result = df.copy()
    smoothed = y_values.rolling(window=window, center=True, min_periods=1).mean()
    if baseline_method == "first":
        baseline = smoothed.iloc[0]
    else:
        baseline = smoothed.rolling(window=window, center=True, min_periods=1).min()
    result[smoothed_column] = smoothed
    result[baseline_column] = baseline
    result[corrected_column] = smoothed - baseline
    _write_csv(result, output_path)


def resistivity_transform(input_paths: Sequence[str], output_paths: Sequence[str], params: Mapping[str, Any]) -> None:
    helper_name = "materials_polymer.resistivity_transform"
    _reject_unknown_params(
        params,
        {
            "resistance_column",
            "area_column",
            "thickness_column",
            "thickness_correction_um",
            "resistivity_column",
            "conductivity_column",
        },
        helper_name,
    )
    input_path = _single_path(input_paths, "input", helper_name)
    output_path = _single_path(output_paths, "output", helper_name)
    resistance_column = _string_param(params, "resistance_column", helper_name, "resistance_ohm")
    area_column = _string_param(params, "area_column", helper_name, "area_cm2")
    thickness_column = _string_param(params, "thickness_column", helper_name, "thickness_um")
    resistivity_column = _string_param(params, "resistivity_column", helper_name, "resistivity_ohm_cm")
    conductivity_column = _string_param(params, "conductivity_column", helper_name, "conductivity_s_cm")
    thickness_correction_um = _number_param(params, "thickness_correction_um", helper_name, 20.0)

    df = _read_csv(input_path, helper_name)
    _require_columns(df, [resistance_column, area_column, thickness_column], helper_name)
    resistance = _numeric_series(df, resistance_column, helper_name)
    area = _numeric_series(df, area_column, helper_name)
    thickness_um = _numeric_series(df, thickness_column, helper_name)
    corrected_thickness_cm = (thickness_um - thickness_correction_um) * 1.0e-4
    if (resistance <= 0).any():
        raise DomainAnalysisError(f"{helper_name}.{resistance_column} must be positive.")
    if (area <= 0).any():
        raise DomainAnalysisError(f"{helper_name}.{area_column} must be positive.")
    if (corrected_thickness_cm <= 0).any():
        raise DomainAnalysisError(f"{helper_name} corrected thickness must be positive.")

    result = df.copy()
    resistivity = resistance * (area / corrected_thickness_cm)
    result[resistivity_column] = resistivity
    result[conductivity_column] = 1.0 / resistivity
    _write_csv(result, output_path)


DOMAIN_HELPERS: dict[str, Callable[[Sequence[str], Sequence[str], Mapping[str, Any]], None]] = {
    "materials_polymer.signal_smooth_baseline": signal_smooth_baseline,
    "materials_polymer.resistivity_transform": resistivity_transform,
}

DOMAIN_HELPER_NAMES = frozenset(DOMAIN_HELPERS)
DOMAIN_HELPER_DESCRIPTIONS: dict[str, dict[str, Any]] = {
    "materials_polymer.signal_smooth_baseline": {
        "purpose": "Smooth a time-series signal and add baseline-corrected columns for polymer response data.",
        "inputs": {"count": 1, "format": "csv"},
        "outputs": {"count": 1, "format": "csv"},
        "params_schema": {
            "required": [],
            "properties": {
                "x_column": {"type": "string", "default": "time_s"},
                "y_column": {"type": "string", "default": "signal_au"},
                "window": {"type": "integer", "minimum": 1, "default": 5},
                "baseline_method": {"type": "string", "enum": ["first", "rolling_min"], "default": "rolling_min"},
                "smoothed_column": {"type": "string", "default": "smoothed_signal_au"},
                "baseline_column": {"type": "string", "default": "baseline_au"},
                "corrected_column": {"type": "string", "default": "corrected_signal_au"},
            },
            "additionalProperties": False,
        },
        "worked_example": {
            "domain_helper": "materials_polymer.signal_smooth_baseline",
            "inputs": ["raw/polymer_response.csv"],
            "outputs": ["results/data/polymer_signal_cleaned.csv"],
            "params": {"x_column": "time_s", "y_column": "signal_au", "window": 5},
        },
    },
    "materials_polymer.resistivity_transform": {
        "purpose": "Convert measured resistance, electrode area, and thickness into resistivity and conductivity.",
        "inputs": {"count": 1, "format": "csv"},
        "outputs": {"count": 1, "format": "csv"},
        "params_schema": {
            "required": [],
            "properties": {
                "resistance_column": {"type": "string", "default": "resistance_ohm"},
                "area_column": {"type": "string", "default": "area_cm2"},
                "thickness_column": {"type": "string", "default": "thickness_um"},
                "thickness_correction_um": {"type": "number", "default": 20.0},
                "resistivity_column": {"type": "string", "default": "resistivity_ohm_cm"},
                "conductivity_column": {"type": "string", "default": "conductivity_s_cm"},
            },
            "additionalProperties": False,
        },
        "worked_example": {
            "domain_helper": "materials_polymer.resistivity_transform",
            "inputs": ["results/data/polymer_signal_cleaned.csv"],
            "outputs": ["results/data/polymer_material_properties.csv"],
            "params": {
                "resistance_column": "resistance_ohm",
                "area_column": "area_cm2",
                "thickness_column": "thickness_um",
                "thickness_correction_um": 20,
            },
        },
    },
}


def list_domain_helper_descriptions() -> list[dict[str, Any]]:
    return [
        {"name": name, **description}
        for name, description in sorted(DOMAIN_HELPER_DESCRIPTIONS.items())
    ]


def run_domain_helper(
    helper_name: str,
    *,
    input_paths: Sequence[str],
    output_paths: Sequence[str],
    params: Mapping[str, Any] | None = None,
) -> None:
    if helper_name not in DOMAIN_HELPERS:
        allowed = ", ".join(sorted(DOMAIN_HELPERS))
        raise DomainAnalysisError(f"Unknown domain_helper '{helper_name}'. Allowed: {allowed}.")
    if params is None:
        params = {}
    if not isinstance(params, Mapping):
        raise DomainAnalysisError(f"{helper_name}.params must be a mapping.")
    DOMAIN_HELPERS[helper_name](input_paths, output_paths, params)
