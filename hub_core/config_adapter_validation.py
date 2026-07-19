"""Validation helpers for configured runtime adapter selections."""

from __future__ import annotations


def validate_named_adapter(
    errors: list[str],
    adapters: dict,
    key: str,
    allowed_values: set[str],
) -> None:
    """Append a validation error when a named adapter selection is invalid."""
    if key not in adapters:
        return
    raw_value = adapters.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        errors.append(f"environment.adapters.{key} must be a non-empty string.")
        return
    value = raw_value.strip().lower()
    if value not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        errors.append(f"environment.adapters.{key} '{raw_value}' is invalid. Allowed: {allowed}.")
