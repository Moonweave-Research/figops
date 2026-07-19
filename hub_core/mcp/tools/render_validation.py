from __future__ import annotations

import math
import re
from typing import Any

from hub_core.calculation_evidence import MAX_EVIDENCE_FILES, verify_calculation_evidence_bundle
from hub_core.claim_inventory import evaluate_project_claim_inventory
from hub_core.project_paths import normalize_project_relative_path
from hub_core.rendering import PLOT_TYPES

_STATISTICAL_OVERLAY_PLOT_TYPES = {"line", "scatter", "xy"}
_BAR_AGGREGATE_METHODS = {"mean", "median"}
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ANNOTATION_P_CLAIM_RE = re.compile(
    r"^p(?:<=|<|=)[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$",
    re.IGNORECASE,
)
_MARKER_FIELDS = {
    "x1",
    "x2",
    "y",
    "h",
    "label",
    "color",
    "calculation_evidence_id",
    "analysis_artifact_sha256",
    "test_metadata",
}


def _bounded_marker_string(value: Any, name: str, *, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    if len(value) > limit:
        raise ValueError(f"{name} exceeds {limit} characters.")
    return value


def _marker_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a JSON number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite.")
    return number


def _optional_positive_int_arg(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


class McpRenderValidationMixin:
    """Shared argument-validation helpers for MCP render tools."""

    @staticmethod
    def _project_claim_inventory(root: Any, selected_figure: dict[str, Any]) -> dict[str, Any]:
        """Evaluate the mandatory project-script publication claim inventory."""

        return evaluate_project_claim_inventory(root, selected_figure)

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
        elif ci_band:
            errors.append(
                "ci_band is unavailable in quick/compat rendering until independently produced bounds are linked."
            )
        if significance_markers is None:
            significance_markers = ()
        if not isinstance(significance_markers, (list, tuple)):
            errors.append("significance_markers must be an array of objects.")
        else:
            for idx, marker in enumerate(significance_markers):
                if not isinstance(marker, dict):
                    errors.append(f"significance_markers[{idx}] must be an object.")
                    continue
                missing = [key for key in ("x1", "x2", "y", "label") if key not in marker]
                if missing:
                    errors.append(
                        f"significance_markers[{idx}] missing required field(s): {', '.join(missing)}."
                    )
                    continue
                for key in ("x1", "x2", "y", "h"):
                    if key not in marker or marker.get(key) is None:
                        continue
                    if isinstance(marker[key], bool) or not isinstance(marker[key], (int, float)):
                        errors.append(f"significance_markers[{idx}].{key} must be a JSON number.")
                    elif not math.isfinite(float(marker[key])):
                        errors.append(f"significance_markers[{idx}].{key} must be finite.")
                evidence_id = marker.get("calculation_evidence_id")
                if not isinstance(evidence_id, str) or not evidence_id.strip():
                    errors.append(
                        f"significance_markers[{idx}].calculation_evidence_id must cite calculation evidence."
                    )
                artifact_hash = marker.get("analysis_artifact_sha256")
                if not isinstance(artifact_hash, str) or not _SHA256_RE.fullmatch(artifact_hash):
                    errors.append(
                        f"significance_markers[{idx}].analysis_artifact_sha256 must be a 64-character SHA-256."
                    )
                test_metadata = marker.get("test_metadata")
                if not isinstance(test_metadata, dict):
                    errors.append(f"significance_markers[{idx}].test_metadata must be an object.")
                else:
                    test_name = test_metadata.get("test_name")
                    if not isinstance(test_name, str) or not test_name.strip():
                        errors.append(f"significance_markers[{idx}].test_metadata.test_name is required.")
                    model = test_metadata.get("model")
                    if not isinstance(model, str) or not model.strip():
                        errors.append(f"significance_markers[{idx}].test_metadata.model is required.")
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
    def _calculation_evidence_path_args(raw_path: Any, raw_paths: Any = None) -> tuple[str, ...]:
        if raw_path not in (None, "") and raw_paths not in (None, (), []):
            raise ValueError("Use calculation_evidence_path or calculation_evidence_paths, not both.")
        values = raw_paths if raw_paths not in (None, (), []) else ([raw_path] if raw_path not in (None, "") else [])
        if not isinstance(values, (list, tuple)):
            raise ValueError("calculation_evidence_paths must be an array of project-relative JSON paths.")
        if len(values) > MAX_EVIDENCE_FILES:
            raise ValueError(f"calculation_evidence_paths exceeds {MAX_EVIDENCE_FILES} files.")
        normalized: list[str] = []
        for index, value in enumerate(values):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"calculation_evidence_paths[{index}] must be a project-relative JSON path.")
            canonical = normalize_project_relative_path(value, purpose="calculation evidence artifact")
            if canonical not in normalized:
                normalized.append(canonical)
        return tuple(normalized)

    def _verified_calculation_evidence(self, raw_path: Any, raw_paths: Any = None) -> list[dict[str, Any]]:
        """Load one bounded bundle using server-owned adapter selection."""
        paths = self._calculation_evidence_path_args(raw_path, raw_paths)
        return verify_calculation_evidence_bundle(self.research_root, paths) if paths else []

    @staticmethod
    def _normalized_significance_markers_arg(value: Any) -> tuple[dict[str, Any], ...]:
        if value in (None, (), []):
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("significance_markers must be an array of objects.")
        normalized: list[dict[str, Any]] = []
        for index, marker in enumerate(value):
            if not isinstance(marker, dict):
                raise ValueError(f"significance_markers[{index}] must be an object.")
            if set(marker) - _MARKER_FIELDS:
                raise ValueError(f"significance_markers[{index}] contains unsupported fields.")
            missing = [
                key
                for key in (
                    "x1",
                    "x2",
                    "y",
                    "label",
                    "calculation_evidence_id",
                    "analysis_artifact_sha256",
                    "test_metadata",
                )
                if key not in marker
            ]
            if missing:
                raise ValueError(
                    f"significance_markers[{index}] missing required field(s): {', '.join(missing)}."
                )
            metadata = marker.get("test_metadata")
            if not isinstance(metadata, dict) or set(metadata) - {"test_name", "model"}:
                raise ValueError(f"significance_markers[{index}].test_metadata must be a closed object.")
            evidence_id = _bounded_marker_string(
                marker.get("calculation_evidence_id"),
                f"significance_markers[{index}].calculation_evidence_id",
            )
            artifact_hash = marker.get("analysis_artifact_sha256")
            if not isinstance(artifact_hash, str) or not _SHA256_RE.fullmatch(artifact_hash):
                raise ValueError(
                    f"significance_markers[{index}].analysis_artifact_sha256 must be a 64-character SHA-256."
                )
            item = {
                "x1": _marker_number(marker["x1"], f"significance_markers[{index}].x1"),
                "x2": _marker_number(marker["x2"], f"significance_markers[{index}].x2"),
                "y": _marker_number(marker["y"], f"significance_markers[{index}].y"),
                "h": _marker_number(marker.get("h", 0.02), f"significance_markers[{index}].h"),
                "label": _bounded_marker_string(marker.get("label"), f"significance_markers[{index}].label", limit=128),
                "calculation_evidence_id": evidence_id,
                "analysis_artifact_sha256": artifact_hash.lower(),
                "test_metadata": {
                    "test_name": _bounded_marker_string(
                        metadata.get("test_name"), f"significance_markers[{index}].test_metadata.test_name"
                    ),
                    "model": _bounded_marker_string(
                        metadata.get("model"), f"significance_markers[{index}].test_metadata.model"
                    ),
                },
            }
            if "color" in marker:
                item["color"] = _bounded_marker_string(
                    marker.get("color"), f"significance_markers[{index}].color", limit=64
                )
            normalized.append(item)
        return tuple(normalized)

    @staticmethod
    def _statistical_claim_linkage_errors(
        significance_markers: Any,
        calculation_evidence: list[dict[str, Any]],
    ) -> list[str]:
        if not significance_markers:
            return []
        by_id = {
            str(record.get("evidence_id")): record
            for record in calculation_evidence
            if isinstance(record, dict) and record.get("evidence_id")
        }
        errors: list[str] = []
        if len(by_id) != len(calculation_evidence):
            errors.append("calculation evidence IDs must be globally unique.")
        claimed_ids: set[str] = set()
        for index, marker in enumerate(significance_markers):
            if not isinstance(marker, dict):
                continue
            evidence_id = str(marker.get("calculation_evidence_id") or "")
            if evidence_id in claimed_ids:
                errors.append(
                    f"significance_markers[{index}].calculation_evidence_id is an unscoped duplicate claim."
                )
            claimed_ids.add(evidence_id)
            record = by_id.get(evidence_id)
            if record is None:
                errors.append(
                    f"significance_markers[{index}].calculation_evidence_id does not reference "
                    "verified calculation evidence."
                )
                continue
            if marker.get("analysis_artifact_sha256") != record.get("analysis_artifact_sha256"):
                errors.append(
                    f"significance_markers[{index}].analysis_artifact_sha256 does not match "
                    "the referenced calculation evidence."
                )
            metadata = marker.get("test_metadata") if isinstance(marker.get("test_metadata"), dict) else {}
            if metadata != record.get("test_metadata"):
                errors.append(
                    f"significance_markers[{index}].test_metadata does not match the producer-owned evidence metadata."
                )
            marker_label = str(marker.get("label") or marker.get("text") or "*")
            assertion = record.get("assertion") if isinstance(record.get("assertion"), dict) else {}
            if marker_label != assertion.get("display_label"):
                errors.append(
                    f"significance_markers[{index}].label does not match the producer-owned evidence annotation."
                )
            binding = record.get("marker_binding") if isinstance(record.get("marker_binding"), dict) else {}
            if any(float(marker.get(field)) != float(binding.get(field, float("nan"))) for field in ("x1", "x2")):
                errors.append(
                    f"significance_markers[{index}] comparison coordinates do not match producer-owned evidence."
                )
        return errors

    @staticmethod
    def _annotation_claim_evidence(
        annotations: Any,
        calculation_evidence: list[dict[str, Any]],
        *,
        claimed_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        by_id = {record["evidence_id"]: record for record in calculation_evidence}
        used = claimed_ids if claimed_ids is not None else set()
        claims: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        errors: list[str] = []
        for index, annotation in enumerate(annotations or ()):
            if not isinstance(annotation, dict):
                continue
            text = annotation.get("text")
            if not isinstance(text, str) or not text:
                continue
            compact = "".join(text.split()).replace("≤", "<=").replace("＜", "<").replace("＝", "=")
            recognized = bool(_ANNOTATION_P_CLAIM_RE.fullmatch(compact) or (compact and set(compact) == {"*"}))
            kind = str(annotation.get("annotation_kind") or "auto")
            if kind == "literal":
                ledger_text = text[:512]
                candidates.append(
                    {
                        "source": "annotation",
                        "annotation_index": index,
                        "text": ledger_text,
                        "text_truncated": len(text) > len(ledger_text),
                        "status": "unverified_literal",
                        "manual_review_required": True,
                    }
                )
                continue
            if not recognized and kind != "statistical_claim":
                continue
            evidence_id = str(annotation.get("calculation_evidence_id") or "")
            record = by_id.get(evidence_id)
            if record is None:
                errors.append(
                    f"annotations[{index}] is a statistical claim candidate and must reference "
                    "verified calculation evidence."
                )
                continue
            if evidence_id in used:
                errors.append(f"annotations[{index}] reuses an unscoped calculation evidence ID.")
                continue
            used.add(evidence_id)
            assertion = record.get("assertion") if isinstance(record.get("assertion"), dict) else {}
            metadata = annotation.get("test_metadata")
            if text != assertion.get("display_label"):
                errors.append(f"annotations[{index}].text does not match producer-owned display_label.")
            if annotation.get("analysis_artifact_sha256") != record.get("analysis_artifact_sha256"):
                errors.append(f"annotations[{index}].analysis_artifact_sha256 does not match evidence.")
            if metadata != record.get("test_metadata"):
                errors.append(f"annotations[{index}].test_metadata does not match evidence.")
            claims.append(
                {
                    "source": "annotation",
                    "annotation_index": index,
                    "text": text,
                    "calculation_evidence_id": evidence_id,
                    "analysis_artifact_sha256": record.get("analysis_artifact_sha256"),
                    "test_metadata": record.get("test_metadata"),
                }
            )
        return {
            "claims": claims,
            "claim_candidates": candidates,
            "errors": errors,
            "manual_review_needed": bool(candidates),
        }

    @staticmethod
    def _fill_band_claim_evidence(fill_between: Any) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        errors: list[str] = []
        for index, band in enumerate(fill_between or ()):
            if not isinstance(band, dict) or "band_kind" not in band:
                continue
            kind = band.get("band_kind")
            if kind == "confidence_interval":
                errors.append(
                    f"fill_between[{index}].band_kind='confidence_interval' is unavailable until "
                    "interval evidence is linked."
                )
            elif kind == "literal":
                text = str(band.get("label") or "")
                ledger_text = text[:512]
                candidates.append(
                    {
                        "source": "fill_between",
                        "band_index": index,
                        "text": ledger_text,
                        "text_truncated": len(text) > len(ledger_text),
                        "status": "unverified_literal",
                        "manual_review_required": True,
                    }
                )
        return {"claim_candidates": candidates, "errors": errors, "manual_review_needed": bool(candidates)}

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
