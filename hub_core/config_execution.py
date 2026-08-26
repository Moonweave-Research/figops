"""Validation for the execution section of project configuration."""

from __future__ import annotations

from .cache_manager import CACHE_STRATEGIES
from .execution_security import is_positive_finite_timeout


def validate_execution_config(errors: list[str], execution: dict) -> None:
    for key in ("python", "rscript"):
        if key in execution and execution[key] is not None and not isinstance(execution[key], str):
            errors.append(f"execution.{key} must be a string or null.")
    if "timeout_seconds" in execution and not is_positive_finite_timeout(execution["timeout_seconds"]):
        errors.append("execution.timeout_seconds must be a positive finite number.")
    if "cache_strategy" in execution:
        cache_strategy = execution.get("cache_strategy")
        if not isinstance(cache_strategy, str) or cache_strategy.strip().lower() not in CACHE_STRATEGIES:
            allowed = ", ".join(sorted(CACHE_STRATEGIES))
            errors.append(f"execution.cache_strategy must be one of: {allowed}.")
