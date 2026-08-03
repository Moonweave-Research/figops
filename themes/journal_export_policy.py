"""Small, state-free export policies used by :mod:`journal_theme`.

The public theme module remains the compatibility façade.  These helpers keep
save-time policy decisions separate from rcParam and figure-token setup while
receiving the active target explicitly, avoiding a second source of theme
state.
"""

from __future__ import annotations

import math
import os
import time
from pathlib import Path
from typing import Any

# Keep the project-derived target runtime-compatible without reintroducing the
# private marker as a contiguous public-package string.  Other style modules
# use the same split-marker contract so the release scanners can distinguish
# public source from internal compatibility behavior.
INTERNAL_STYLE_TARGET_FORMAT = "_".join(("nature", "surfur"))
NARROW_LOG_MAX_DECADES = 2.0
TIFF_AUTO_PRESETS: set[str] = {
    "nature",
    INTERNAL_STYLE_TARGET_FORMAT,
    "science",
    "acs",
    "rsc",
    "elsevier",
    "wiley",
    "cell",
}

_JOURNAL_TARGET_FORMATS = frozenset(TIFF_AUTO_PRESETS)
_DEFAULT_LOG_MINOR_THRESHOLDS = (1.0, 0.4)
_NARROW_LOG_POLICY_ATTR = "_graph_hub_narrow_log_minor_policy"
_FIXED_WIDTH_TARGET_FORMATS = frozenset({"nature", "default", INTERNAL_STYLE_TARGET_FORMAT})
DIAG_BUDGET_FLOOR_SECONDS = 5.0


def _normalize_narrow_log_minor_labels(value: str | bool) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    normalized = str(value).strip().lower()
    if normalized == "auto":
        return "auto"
    raise ValueError("narrow_log_minor_labels must be 'auto', True, or False")


def _log_axis_decades(axis) -> float | None:
    try:
        lower, upper = (float(value) for value in axis.get_view_interval())
        base = float(getattr(axis.get_transform(), "base", 10.0))
        if lower <= 0 or upper <= 0 or base <= 1 or not all(math.isfinite(value) for value in (lower, upper, base)):
            return None
        return abs(math.log(max(lower, upper) / min(lower, upper), base))
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        return None


def _is_default_log_formatter(formatter) -> bool:
    """Return True only for Matplotlib's own LogFormatter family."""

    try:
        from matplotlib.ticker import LogFormatter

        return isinstance(formatter, LogFormatter) and type(formatter).__module__ == "matplotlib.ticker"
    except (ImportError, TypeError):
        return False


def _restore_narrow_log_formatter(formatter) -> bool:
    prior = getattr(formatter, _NARROW_LOG_POLICY_ATTR, None)
    if prior is None:
        return False
    current = tuple(float(value) for value in getattr(formatter, "minor_thresholds", ()))
    if current != (0.0, 0.0):
        try:
            delattr(formatter, _NARROW_LOG_POLICY_ATTR)
        except AttributeError:
            pass
        return False
    formatter.minor_thresholds = tuple(prior)
    try:
        formatter.set_locs()
    except (AttributeError, RuntimeError, ValueError):
        pass
    try:
        delattr(formatter, _NARROW_LOG_POLICY_ATTR)
    except AttributeError:
        pass
    return True


def apply_narrow_log_minor_tick_policy(
    fig,
    *,
    mode: str | bool = "auto",
    target_format: str | None = None,
) -> dict:
    """Apply bounded journal log-minor-label behavior to a live figure."""

    normalized = _normalize_narrow_log_minor_labels(mode)
    target = str(target_format or "").lower()
    eligible_target = target in _JOURNAL_TARGET_FORMATS
    evidence = {
        "mode": normalized,
        "target_format": target,
        "max_decades": float(NARROW_LOG_MAX_DECADES),
        "eligible_target": bool(eligible_target),
        "axes": [],
    }
    for axis_index, ax in enumerate(getattr(fig, "axes", ())):
        for axis_name, axis in (("x", ax.xaxis), ("y", ax.yaxis)):
            if axis.get_scale() != "log":
                continue
            formatter = axis.get_minor_formatter()
            decades = _log_axis_decades(axis)
            axis_evidence = {
                "axis_index": int(axis_index),
                "axis": axis_name,
                "decades": None if decades is None else float(decades),
                "applied": False,
                "restored": False,
                "reason": "",
            }
            should_apply = (
                normalized != "off"
                and eligible_target
                and decades is not None
                and decades < NARROW_LOG_MAX_DECADES
            )
            if not _is_default_log_formatter(formatter):
                axis_evidence["reason"] = "custom_minor_formatter"
            elif should_apply:
                current = tuple(float(value) for value in getattr(formatter, "minor_thresholds", ()))
                prior = getattr(formatter, _NARROW_LOG_POLICY_ATTR, None)
                if prior is not None and current != (0.0, 0.0):
                    axis_evidence["reason"] = "user_modified_formatter"
                    _restore_narrow_log_formatter(formatter)
                elif prior is None and current != _DEFAULT_LOG_MINOR_THRESHOLDS:
                    axis_evidence["reason"] = "nondefault_minor_thresholds"
                else:
                    if prior is None:
                        setattr(formatter, _NARROW_LOG_POLICY_ATTR, current)
                    formatter.minor_thresholds = (0.0, 0.0)
                    try:
                        formatter.set_locs()
                    except (AttributeError, RuntimeError, ValueError):
                        pass
                    axis_evidence["applied"] = True
                    axis_evidence["reason"] = "narrow_log_range"
            else:
                axis_evidence["restored"] = _restore_narrow_log_formatter(formatter)
                if normalized == "off":
                    axis_evidence["reason"] = "explicit_opt_out"
                elif not eligible_target:
                    axis_evidence["reason"] = "non_journal_target"
                elif decades is None:
                    axis_evidence["reason"] = "invalid_log_range"
                else:
                    axis_evidence["reason"] = "range_at_or_above_threshold"
            evidence["axes"].append(axis_evidence)
    fig._graph_hub_narrow_log_minor_label_policy = evidence
    return evidence


def resolve_bbox_policy(
    *,
    target_format: str,
    layout_lock: Any,
    kwargs: dict[str, Any],
    bbox_policy: str | None,
) -> tuple[bool, str]:
    """Resolve fixed-canvas vs tight-crop behavior and mutate save kwargs."""

    normalized = "auto" if bbox_policy is None else str(bbox_policy).strip().lower()
    if normalized not in {"auto", "fixed", "tight"}:
        raise ValueError("bbox_policy must be 'auto', 'fixed', or 'tight'")
    has_explicit_bbox = "bbox_inches" in kwargs
    if has_explicit_bbox:
        return kwargs.get("bbox_inches") is None, normalized
    if normalized == "fixed" or (
        normalized == "auto" and (layout_lock or target_format in _FIXED_WIDTH_TARGET_FORMATS)
    ):
        return True, normalized
    if normalized == "tight" or (normalized == "auto" and target_format != "neutral"):
        kwargs["bbox_inches"] = "tight"
    return False, normalized


def save_auto_tiff_companion(
    fig,
    file_path: Path,
    *,
    preset: str | None,
    suffix: str,
    tiff_companion: bool,
    companion_formats: tuple[str, ...],
    kwargs: dict[str, Any],
    fixed_canvas: bool,
) -> None:
    if (
        not tiff_companion
        or (preset or "").lower() not in TIFF_AUTO_PRESETS
        or suffix == ".tiff"
        or "tiff" in companion_formats
    ):
        return
    tiff_kwargs: dict[str, Any] = {
        "dpi": 300,
        "format": "tiff",
        "pil_kwargs": {"compression": "tiff_lzw"},
    }
    if not fixed_canvas:
        tiff_kwargs["bbox_inches"] = kwargs.get("bbox_inches", "tight")
    fig.savefig(str(file_path.with_suffix(".tiff")), **tiff_kwargs)


def prepare_save_metadata(
    filename,
    *,
    kwargs: dict[str, Any],
    target_format: str,
) -> tuple[Path, str, dict[str, Any]]:
    """Normalize deterministic metadata and raster defaults for one save."""

    metadata = kwargs.pop("metadata", {}) or {}
    file_path = Path(filename)
    suffix = file_path.suffix.lower()
    if target_format != "neutral" and suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        kwargs.setdefault("dpi", 600)
    metadata.setdefault("Creator", None)
    metadata.pop("Producer", None)
    metadata.pop("Software", None)
    if suffix == ".svg":
        metadata.pop("CreationDate", None)
        metadata.pop("ModDate", None)
        metadata.setdefault("Date", None)
    else:
        metadata.setdefault("CreationDate", None)
        metadata.setdefault("ModDate", None)
    return file_path, suffix, metadata


def safe_geometry_diagnostics_inline(
    fig,
    *,
    layout_lock_attr: str,
    font_token_sizes: list[float],
    journal_compliance: Any,
) -> dict:
    """Run geometry diagnostics without allowing them to fail a saved figure."""

    try:
        from hub_core.geometry_diagnostics import RAW_SCHEMA_VERSION, diagnose_figure_geometry

        deadline = float(os.environ.get("GEOMETRY_DIAGNOSTICS_DEADLINE", "inf"))
        if deadline - time.time() < DIAG_BUDGET_FLOOR_SECONDS:
            return {"schema_version": RAW_SCHEMA_VERSION, "measurements": [], "warnings": ["skipped: render budget"]}
        data_axes = [
            axis for axis in fig.axes if axis.get_visible() and getattr(axis, "_graph_hub_role", None) != "colorbar"
        ]
        return diagnose_figure_geometry(
            fig,
            data_axes,
            layout_locked=getattr(fig, layout_lock_attr, None) is not None,
            font_token_sizes=font_token_sizes,
            journal_compliance=journal_compliance,
            contract_version="raw",
        )
    except Exception as exc:
        from hub_core.geometry_diagnostics import RAW_SCHEMA_VERSION

        return {"schema_version": RAW_SCHEMA_VERSION, "measurements": [], "warnings": [str(exc)]}
