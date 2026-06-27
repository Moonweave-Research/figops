from __future__ import annotations

from typing import Any

from hub_core.rendering import PLOT_TYPES

_STATISTICAL_OVERLAY_PLOT_TYPES = {"line", "scatter", "xy"}
_BAR_AGGREGATE_METHODS = {"mean", "median"}


def _optional_positive_int_arg(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


class McpRenderValidationMixin:
    """Shared argument-validation helpers for MCP render tools."""

    @staticmethod
    def _statistical_overlay_arg_errors(
        *,
        plot_type: str,
        fit_line: Any,
        ci_band: Any,
        significance_markers: Any,
        fit_options: Any = None,
    ) -> list[str]:
        errors: list[str] = []
        if not isinstance(fit_line, bool):
            errors.append("fit_line must be a boolean.")
        if not isinstance(ci_band, bool):
            errors.append("ci_band must be a boolean.")
        if significance_markers is None:
            significance_markers = ()
        if not isinstance(significance_markers, (list, tuple)):
            errors.append("significance_markers must be an array of objects.")
        else:
            for idx, marker in enumerate(significance_markers):
                if not isinstance(marker, dict):
                    errors.append(f"significance_markers[{idx}] must be an object.")
                    continue
                missing = [key for key in ("x1", "x2", "y") if key not in marker]
                if missing:
                    errors.append(
                        f"significance_markers[{idx}] missing required field(s): {', '.join(missing)}."
                    )
                    continue
                for key in ("x1", "x2", "y", "h"):
                    if key not in marker or marker.get(key) is None:
                        continue
                    try:
                        float(marker[key])
                    except (TypeError, ValueError):
                        errors.append(f"significance_markers[{idx}].{key} must be numeric.")
        if fit_options in (None, {}, []):
            fit_options = {}
        elif not isinstance(fit_options, dict):
            errors.append("fit_options must be an object.")
            fit_options = {}
        if fit_options and not (fit_line or ci_band):
            errors.append("fit_options requires fit_line or ci_band.")
        has_overlays = bool(fit_line or ci_band or fit_options or significance_markers)
        if has_overlays and plot_type not in _STATISTICAL_OVERLAY_PLOT_TYPES:
            errors.append("statistical overlays are only supported for plot_type 'line', 'scatter', or 'xy'.")
        return errors

    @staticmethod
    def _category_order_arg_errors(*, plot_type: str, category_order: tuple[float | str, ...]) -> list[str]:
        if not category_order:
            return []
        capabilities = PLOT_TYPES[plot_type].capabilities
        if not capabilities.get("supports_category_order", False):
            return [f"category_order is not supported for plot_type '{plot_type}'."]
        return []

    @staticmethod
    def _bar_aggregate_arg_errors(*, plot_type: str, aggregate: str) -> list[str]:
        if not aggregate:
            return []
        if aggregate not in _BAR_AGGREGATE_METHODS:
            allowed = ", ".join(sorted(_BAR_AGGREGATE_METHODS))
            return [f"aggregate must be one of: {allowed}."]
        if plot_type != "bar":
            return ["aggregate is only supported for plot_type 'bar'."]
        return []

    @staticmethod
    def _semantic_checks_with_bar_error_column(
        semantic_checks: dict[str, Any],
        *,
        y_column: str,
        bar_error_column: str,
    ) -> dict[str, Any]:
        merged = {
            str(column): dict(checks) if isinstance(checks, dict) else checks
            for column, checks in semantic_checks.items()
        }
        y_checks = merged.get(y_column, {})
        if not isinstance(y_checks, dict):
            raise ValueError(f"semantic_checks for '{y_column}' must be an object when bar_error_column is set.")
        declared = {"column": bar_error_column, "source": bar_error_column}
        existing = y_checks.get("error_bar_source")
        if existing is not None and existing != declared:
            raise ValueError(
                f"bar_error_column '{bar_error_column}' conflicts with semantic_checks['{y_column}'].error_bar_source."
            )
        y_checks["error_bar_source"] = declared
        merged[y_column] = y_checks
        return merged

    @staticmethod
    def _order_arg(raw_value: Any, field_name: str, *, allow_numbers: bool) -> tuple[str | float, ...]:
        if raw_value is None:
            return ()
        if not isinstance(raw_value, (list, tuple)):
            raise ValueError(f"{field_name} must be an array.")
        values: list[str | float] = []
        for index, item in enumerate(raw_value):
            if isinstance(item, bool) or item is None:
                raise ValueError(
                    f"{field_name}[{index}] must be a string" + (" or number." if allow_numbers else ".")
                )
            if isinstance(item, str):
                values.append(item.strip())
            elif allow_numbers and isinstance(item, (int, float)):
                values.append(float(item))
            else:
                raise ValueError(
                    f"{field_name}[{index}] must be a string" + (" or number." if allow_numbers else ".")
                )
        return tuple(values)
