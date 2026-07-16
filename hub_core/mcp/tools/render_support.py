from __future__ import annotations

import fnmatch
import os
import re
import uuid
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import numpy as np

from hub_core.config_parser import ALLOWED_OUTPUT_FORMATS, ALLOWED_TARGET_FORMATS
from hub_core.data_contract import _read_data_safe, _validate_semantic_constraints
from hub_core.figure_preflight import validate_figure_preflight
from hub_core.mcp import render_orchestration as render_helpers
from hub_core.project_discovery import ProjectDiscoveryService
from hub_core.project_paths import normalize_project_relative_path
from themes.style_profiles import DEFAULT_PROFILE, PROFILE_ALIASES, list_profiles


class McpRenderToolSupportMixin:
    """Private helpers shared by FigOps MCP tool handlers."""

    def _csv_render_error(
        self,
        arguments: dict[str, Any],
        *,
        summary: str,
        errors: list[str],
        failure_stage: str,
        resolution_hint: str,
        is_dry_run: bool | None = None,
        tool_name: str = "figops.render_csv_graph",
        **extra: Any,
    ) -> dict[str, Any]:
        geometry_diagnostics = extra.pop(
            "geometry_diagnostics",
            render_helpers._geometry_stub("no figure"),
        )
        layout_report = extra.pop(
            "layout_report",
            render_helpers._layout_report_from_geometry(geometry_diagnostics),
        )
        return self._envelope(
            tool_name,
            arguments,
            status="error",
            summary=summary,
            errors=errors,
            manual_review_needed=True,
            is_dry_run=False if is_dry_run is None else is_dry_run,
            artifact_status="failed",
            baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            geometry_diagnostics=geometry_diagnostics,
            layout_report=layout_report,
            failure_stage=failure_stage,
            resolution_hint=resolution_hint,
            **extra,
        )

    @staticmethod
    def _manifest_path_list(manifest: dict[str, Any], key: str) -> list[str]:
        value = manifest.get(key)
        return [str(item) for item in value] if isinstance(value, list) else []

    @staticmethod
    def _preflight_warnings(preflight: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        raw_warnings = preflight.get("warnings")
        if isinstance(raw_warnings, list):
            warnings.extend(str(warning) for warning in raw_warnings)
        raw_checks = preflight.get("checks")
        if isinstance(raw_checks, list):
            for check in raw_checks:
                if isinstance(check, dict) and check.get("passed") is False:
                    detail = check.get("detail")
                    if detail:
                        warnings.append(str(detail))
        return warnings

    @staticmethod
    def _artifact_status(preflight: dict[str, Any], baseline_comparison: dict[str, Any]) -> str:
        if baseline_comparison.get("checked") and baseline_comparison.get("matched") is True:
            return "baseline_matched"
        if baseline_comparison.get("checked") and baseline_comparison.get("matched") is False:
            return "manual_review_needed"
        if preflight.get("passed") is True and not McpRenderToolSupportMixin._preflight_warnings(preflight):
            return "preflight_passed"
        if preflight.get("passed") is None:
            return "validated"
        if preflight.get("passed") is False or McpRenderToolSupportMixin._preflight_warnings(preflight):
            return "manual_review_needed"
        return "created"

    @staticmethod
    def _baseline_warnings(baseline_comparison: dict[str, Any]) -> list[str]:
        raw_warnings = baseline_comparison.get("warnings")
        return [str(warning) for warning in raw_warnings] if isinstance(raw_warnings, list) else []

    @staticmethod
    def _calculation_warnings(calculation_checks: dict[str, Any]) -> list[str]:
        warnings = []
        for check in calculation_checks.get("checks", []):
            if check.get("status") in {"warning", "skipped"} or check.get("manual_review_needed"):
                name = check.get("name", "calculation_check")
                message = check.get("message", "requires manual review")
                warnings.append(f"{name}: {message}")
        return warnings

    @staticmethod
    def _render_job_id(raw_job_id: Any = None) -> str:
        if raw_job_id is None or not str(raw_job_id).strip():
            return f"job-{uuid.uuid4().hex[:12]}"
        text = str(raw_job_id).strip()
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text)
        safe = safe.strip("-_")
        if not safe:
            raise ValueError("job_id must contain at least one alphanumeric character.")
        return safe[:80]

    @staticmethod
    def _required_string(arguments: dict[str, Any], key: str) -> str:
        value = arguments.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} is required.")
        return value.strip()

    def _input_file_path(self, raw_path: Any) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("data_path is required.")
        path = self._resolve_allowed_data_path(raw_path, field_name="data_path")
        if not path.is_file():
            raise ValueError("data_path is not a file.")
        if path.suffix.lower() != ".csv":
            raise ValueError("data_path must point to a CSV file.")
        file_size = path.stat().st_size
        max_bytes = McpRenderToolSupportMixin._render_csv_max_bytes()
        if file_size > max_bytes:
            limit_mb = max_bytes / (1024 * 1024)
            actual_mb = file_size / (1024 * 1024)
            raise ValueError(f"data_path exceeds MCP CSV size limit: {actual_mb:.1f} MB > {limit_mb:.1f} MB.")
        return path

    @staticmethod
    def _render_csv_max_bytes() -> int:
        raw_value = os.environ.get("GRAPH_HUB_MCP_RENDER_CSV_MAX_BYTES")
        if raw_value is None:
            return render_helpers.MCP_RENDER_CSV_MAX_BYTES
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return render_helpers.MCP_RENDER_CSV_MAX_BYTES
        return value if value > 0 else render_helpers.MCP_RENDER_CSV_MAX_BYTES

    @staticmethod
    def _render_style_errors(target_format: str, output_format: str, profile: str) -> list[str]:
        errors = []
        if target_format not in ALLOWED_TARGET_FORMATS:
            errors.append(f"Invalid target_format: {target_format}. Allowed: {sorted(ALLOWED_TARGET_FORMATS)}")
        if output_format not in ALLOWED_OUTPUT_FORMATS:
            errors.append(f"Invalid output_format: {output_format}. Allowed: {sorted(ALLOWED_OUTPUT_FORMATS)}")
        profile_keys = set(list_profiles()) | set(PROFILE_ALIASES)
        if profile.strip().lower() not in profile_keys:
            errors.append(f"Invalid profile: {profile}. Allowed: {sorted(list_profiles())}")
        return errors

    @staticmethod
    def _rendered_figure_artifacts(output_path: Path) -> list[dict[str, str]]:
        artifacts: list[dict[str, str]] = []
        for candidate in sorted(output_path.parent.glob(f"{output_path.stem}.*")):
            if candidate.suffix.lower().lstrip(".") in ALLOWED_OUTPUT_FORMATS:
                artifacts.append({"path": str(candidate), "format": candidate.suffix.lower().lstrip(".")})
        if not artifacts:
            artifacts.append({"path": str(output_path), "format": output_path.suffix.lower().lstrip(".")})
        return artifacts

    @classmethod
    def _project_figure_metadata(
        cls,
        output_path: Path,
        selected_figure: dict[str, Any],
        *,
        project_path: Path | None = None,
        figures: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        width_px, height_px = cls._image_dimensions(output_path)
        aspect = round(width_px / height_px, 6) if width_px and height_px else None
        metadata = {
            "schema_version": "figure_metadata/1",
            "width_px": width_px,
            "height_px": height_px,
            "aspect": aspect,
            "layout_type": str(selected_figure.get("layout_type") or selected_figure.get("layout") or "").strip(),
        }
        metadata["canonical_check"] = cls._figure_canonical_check(metadata, selected_figure)
        metadata["family_check"] = cls._figure_family_check(metadata, selected_figure, project_path, figures or [])
        return metadata

    @staticmethod
    def _figure_metadata_warnings(figure_metadata: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        for key in ("canonical_check", "family_check"):
            check = figure_metadata.get(key)
            if not isinstance(check, dict):
                continue
            raw_warnings = check.get("warnings")
            if isinstance(raw_warnings, list):
                warnings.extend(str(item) for item in raw_warnings if str(item).strip())
        return warnings

    @staticmethod
    def _image_dimensions(output_path: Path) -> tuple[int | None, int | None]:
        candidates = [output_path, *sorted(output_path.parent.glob(f"{output_path.stem}.*"))]
        seen: set[Path] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                from PIL import Image

                with Image.open(candidate) as image:
                    width, height = image.size
                    return int(width), int(height)
            except Exception:
                if candidate.suffix.lower() == ".svg":
                    svg_width, svg_height = McpRenderToolSupportMixin._svg_dimensions(candidate)
                    if svg_width is not None and svg_height is not None:
                        return svg_width, svg_height
        return None, None

    @staticmethod
    def _svg_dimensions(path: Path) -> tuple[int | None, int | None]:
        try:
            root = ElementTree.parse(path).getroot()
        except Exception:
            return None, None

        def parse_length(value: Any) -> float | None:
            match = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)", str(value or ""))
            return float(match.group(1)) if match else None

        width = parse_length(root.attrib.get("width"))
        height = parse_length(root.attrib.get("height"))
        if width is None or height is None:
            view_box = root.attrib.get("viewBox") or root.attrib.get("viewbox")
            parts = [float(part) for part in re.findall(r"[-+]?(?:\d*\.\d+|\d+)", str(view_box or ""))]
            if len(parts) == 4:
                width = width if width is not None else parts[2]
                height = height if height is not None else parts[3]
        if width is None or height is None:
            return None, None
        return int(round(width)), int(round(height))

    @classmethod
    def _figure_canonical_check(
        cls,
        metadata: dict[str, Any],
        selected_figure: dict[str, Any],
    ) -> dict[str, Any]:
        canonical = selected_figure.get("canonical")
        if canonical is None:
            canonical = {}
        if not isinstance(canonical, dict):
            canonical = {}
        expected = cls._canonical_expectations(selected_figure, canonical)
        warnings: list[str] = list(expected.get("warnings", []))
        tolerance = expected["dimension_tolerance_px"]
        width_px = metadata.get("width_px")
        height_px = metadata.get("height_px")
        expected_width = expected.get("width_px")
        expected_height = expected.get("height_px")
        expected_layout = str(expected.get("layout_type") or "").strip()
        actual_layout = str(metadata.get("layout_type") or "").strip()

        if expected_layout and actual_layout and actual_layout != expected_layout:
            warnings.append(f"figure canonical mismatch: layout_type {actual_layout!r} != expected {expected_layout!r}")
        if isinstance(width_px, int) and isinstance(expected_width, int) and abs(width_px - expected_width) > tolerance:
            warnings.append(
                f"figure canonical mismatch: width_px {width_px} != expected {expected_width} (tolerance {tolerance}px)"
            )
        if (
            isinstance(height_px, int)
            and isinstance(expected_height, int)
            and abs(height_px - expected_height) > tolerance
        ):
            warnings.append(
                f"figure canonical mismatch: height_px {height_px} != expected {expected_height} "
                f"(tolerance {tolerance}px)"
            )
        declared_dimensions = expected.get("declared_width") or expected.get("declared_height")
        if declared_dimensions and (width_px is None or height_px is None):
            warnings.append("figure canonical check could not inspect rendered dimensions")
        return {
            "passed": len(warnings) == 0,
            "expected": expected,
            "warnings": warnings,
        }

    @staticmethod
    def _canonical_expectations(
        selected_figure: dict[str, Any],
        canonical: dict[str, Any],
    ) -> dict[str, Any]:
        expected_dims = canonical.get("expected_dims") or canonical.get("dims") or canonical.get("dimensions")
        expected_width = canonical.get("width_px", selected_figure.get("expected_width_px"))
        expected_height = canonical.get("height_px", selected_figure.get("expected_height_px"))
        warnings: list[str] = []
        allowed_keys = {
            "expected_dims",
            "dims",
            "dimensions",
            "width_px",
            "height_px",
            "layout_type",
            "dimension_tolerance_px",
            "family_dimension_tolerance_px",
            "match_family",
        }
        for key in sorted(str(item) for item in canonical.keys() if str(item) not in allowed_keys):
            warnings.append(f"figure canonical config warning: unknown key {key!r}")
        if isinstance(expected_dims, (list, tuple)) and len(expected_dims) >= 2:
            expected_width = expected_dims[0]
            expected_height = expected_dims[1]
        elif expected_dims is not None:
            warnings.append("figure canonical config warning: expected_dims must contain width and height")
        tolerance = canonical.get("dimension_tolerance_px", selected_figure.get("dimension_tolerance_px", 8))
        try:
            tolerance_px = max(0, int(tolerance))
        except (TypeError, ValueError):
            tolerance_px = 8
            warnings.append("figure canonical config warning: dimension_tolerance_px must be an integer")
        family_tolerance = canonical.get(
            "family_dimension_tolerance_px",
            selected_figure.get("family_dimension_tolerance_px", 8),
        )
        try:
            family_tolerance_px = max(0, int(family_tolerance))
        except (TypeError, ValueError):
            family_tolerance_px = 8
            warnings.append("figure canonical config warning: family_dimension_tolerance_px must be an integer")

        def optional_int(value: Any, field_name: str) -> int | None:
            if isinstance(value, bool) or value is None:
                if isinstance(value, bool):
                    warnings.append(f"figure canonical config warning: {field_name} must be an integer")
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                warnings.append(f"figure canonical config warning: {field_name} must be an integer")
                return None

        return {
            "layout_type": str(
                canonical.get("layout_type") or selected_figure.get("expected_layout_type") or ""
            ).strip(),
            "width_px": optional_int(expected_width, "width_px"),
            "height_px": optional_int(expected_height, "height_px"),
            "declared_width": expected_width is not None,
            "declared_height": expected_height is not None,
            "dimension_tolerance_px": tolerance_px,
            "family_dimension_tolerance_px": family_tolerance_px,
            "match_family": str(canonical.get("match_family") or selected_figure.get("match_family") or "").strip(),
            "warnings": warnings,
        }

    @classmethod
    def _figure_family_check(
        cls,
        metadata: dict[str, Any],
        selected_figure: dict[str, Any],
        project_path: Path | None,
        figures: list[dict[str, Any]],
    ) -> dict[str, Any]:
        expected = metadata.get("canonical_check", {}).get("expected", {})
        family_pattern = str(expected.get("match_family") or "").strip() if isinstance(expected, dict) else ""
        selected_output = str(selected_figure.get("output") or "")
        try:
            selected_output_parent = cls._project_relative_path(selected_output, "figures[].output").parent
        except ValueError:
            return {"passed": True, "family": family_pattern, "siblings": [], "warnings": []}
        family = family_pattern or cls._figure_family_key(
            str(selected_figure.get("id") or ""),
            output_parent=selected_output_parent.as_posix(),
        )
        if not family or project_path is None:
            return {"passed": True, "family": family, "siblings": [], "warnings": []}

        siblings: list[dict[str, Any]] = []
        tolerance = int(metadata.get("canonical_check", {}).get("expected", {}).get("family_dimension_tolerance_px", 8))
        width_px = metadata.get("width_px")
        height_px = metadata.get("height_px")
        for figure in figures:
            if figure is selected_figure:
                continue
            sibling_id = str(figure.get("id") or "")
            try:
                sibling_rel = cls._project_relative_path(figure.get("output"), "figures[].output")
            except ValueError:
                continue
            sibling_matches = (
                fnmatch.fnmatch(sibling_id, family_pattern)
                if family_pattern
                else cls._figure_family_key(sibling_id, output_parent=sibling_rel.parent.as_posix()) == family
            )
            if not sibling_matches:
                continue
            if sibling_rel.parent != selected_output_parent:
                continue
            sibling_width, sibling_height = cls._image_dimensions(project_path / sibling_rel)
            if sibling_width is None or sibling_height is None:
                continue
            siblings.append(
                {
                    "id": sibling_id,
                    "output": sibling_rel.as_posix(),
                    "width_px": sibling_width,
                    "height_px": sibling_height,
                    "layout_type": str(figure.get("layout_type") or figure.get("layout") or "").strip(),
                }
            )

        warnings: list[str] = []
        for sibling in siblings:
            if isinstance(width_px, int) and abs(width_px - int(sibling["width_px"])) > tolerance:
                warnings.append(
                    f"figure family sibling mismatch: {selected_figure.get('id')} width_px {width_px} "
                    f"differs from sibling {sibling['id']} width_px {sibling['width_px']}"
                )
            if isinstance(height_px, int) and abs(height_px - int(sibling["height_px"])) > tolerance:
                warnings.append(
                    f"figure family sibling mismatch: {selected_figure.get('id')} height_px {height_px} "
                    f"differs from sibling {sibling['id']} height_px {sibling['height_px']}"
                )
            actual_layout = str(metadata.get("layout_type") or "")
            sibling_layout = str(sibling.get("layout_type") or "")
            if actual_layout and sibling_layout and actual_layout != sibling_layout:
                warnings.append(
                    f"figure family sibling mismatch: {selected_figure.get('id')} layout_type {actual_layout!r} "
                    f"differs from sibling {sibling['id']} layout_type {sibling_layout!r}"
                )
        return {
            "passed": len(warnings) == 0,
            "family": family,
            "siblings": siblings,
            "warnings": warnings,
        }

    @staticmethod
    def _figure_family_key(figure_id: str, *, output_parent: str = "") -> str:
        text = figure_id.strip()
        if "_" not in text:
            return f"dir:{output_parent}" if output_parent else ""
        parts = [part for part in text.split("_") if part]
        if len(parts) < 3:
            return ""
        return "_".join(parts[1:])

    @staticmethod
    def _validate_render_data_contract(
        data_path: Path,
        *,
        required_columns: list[str],
        semantic_checks: dict[str, Any],
        axis_scales: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        calculation_checks: list[dict[str, Any]] = []
        empty_summary = {
            "schema_version": "1.0",
            "checks": [],
            "quality_passed": True,
            "manual_review_needed": False,
        }
        try:
            import pandas as pd

            df = _read_data_safe(str(data_path), pd)
        except Exception as exc:
            return {
                "errors": [f"Failed to read render data contract input: {exc}"],
                "calculation_checks": empty_summary,
            }

        stripped_to_actual = {}
        for actual_col in df.columns:
            stripped_col = str(actual_col).strip()
            if stripped_col in stripped_to_actual and stripped_to_actual[stripped_col] != actual_col:
                return {
                    "errors": [
                        "Ambiguous columns after strip normalization: "
                        f"'{stripped_to_actual[stripped_col]}' and '{actual_col}'"
                    ],
                    "calculation_checks": empty_summary,
                }
            stripped_to_actual[stripped_col] = actual_col

        missing = [col for col in required_columns if str(col).strip() not in stripped_to_actual]
        if missing:
            return {"errors": [f"Missing required columns: {missing}"], "calculation_checks": empty_summary}

        scale_errors: list[str] = []
        for requested_col, scale in (axis_scales or {}).items():
            if str(scale or "linear").strip().lower() != "log":
                continue
            actual_col = stripped_to_actual.get(str(requested_col).strip())
            if actual_col is None:
                continue
            numeric = pd.to_numeric(df[actual_col], errors="coerce")
            invalid_count = int((numeric.isna() | ~np.isfinite(numeric) | (numeric <= 0)).sum())
            if invalid_count:
                scale_errors.append(
                    f"Column '{requested_col}' has {invalid_count} non-positive/non-numeric value(s); "
                    "log scale requires finite values > 0."
                )

        semantic_errors, _row_violations = _validate_semantic_constraints(
            df,
            semantic_checks,
            stripped_to_actual,
            calculation_checks=calculation_checks,
            csv_rel_path=str(data_path),
            source_config_path="project_config.yaml",
        )
        return {
            "errors": [*scale_errors, *list(semantic_errors)],
            "calculation_checks": {
                "schema_version": "1.0",
                "checks": calculation_checks,
                "quality_passed": not any(
                    check.get("status") in {"warning", "failed"} for check in calculation_checks
                ),
                "manual_review_needed": any(bool(check.get("manual_review_needed")) for check in calculation_checks),
            },
        }

    @staticmethod
    def _render_project_config(
        *,
        target_format: str,
        profile: str,
        output_format: str,
        x_column: str,
        y_column: str,
        z_column: str,
        facet_column: str,
        series_column: str,
        semantic_checks: dict[str, Any],
        extra_required_columns: list[str] | None = None,
    ) -> dict[str, Any]:
        extra_required_columns = extra_required_columns or []
        return {
            "project": {"name": "FigOps MCP Render Job"},
            "visual_style": {
                "target_format": target_format,
                "font_scale": 1.0,
                "profile": profile,
            },
            "language_policy": {"analysis_lang": "r", "plot_lang": "python", "allow_nonstandard": False},
            "data_contract": {
                # Quick CSV jobs do not declare a project sample/condition
                # registry, so the scoped research-ops relaxation is explicit.
                "require_figure_traceability": False,
                "csv_checks": [
                    {
                        "path": "data/input.csv",
                        "required_columns": [
                            x_column,
                            y_column,
                            *([z_column] if z_column else []),
                            *([facet_column] if facet_column else []),
                            *([series_column] if series_column else []),
                            *extra_required_columns,
                        ],
                        "semantic_checks": semantic_checks,
                    }
                ]
            },
            "figures": [
                {
                    "id": "Graph",
                    "script": "bridge_renderer",
                    "inputs": ["data/input.csv"],
                    "output": f"results/figures/graph.{output_format}",
                }
            ],
        }

    @staticmethod
    def _safe_preflight(output_path: Path, target_format: str) -> dict[str, Any]:
        try:
            return validate_figure_preflight(output_path, str(target_format or "nature").strip().lower() or "nature")
        except Exception as exc:
            return {
                "passed": False,
                "checks": [],
                "warnings": [str(exc)],
            }

    @classmethod
    def _visual_preflight_with_geometry_overlaps(
        cls,
        output_path: Path,
        target_format: str,
        geometry_diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        preflight = cls._safe_preflight(output_path, target_format)
        overlaps = cls._artist_overlaps_from_geometry(geometry_diagnostics)
        if overlaps:
            preflight = dict(preflight)
            preflight["overlaps"] = overlaps
            warnings = list(preflight.get("warnings") or [])
            warnings.append(f"artist_overlaps_detected:{len(overlaps)}")
            preflight["warnings"] = warnings
        return preflight

    @staticmethod
    def _artist_overlaps_from_geometry(geometry_diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
        measurements = geometry_diagnostics.get("measurements") if isinstance(geometry_diagnostics, dict) else None
        if not isinstance(measurements, list):
            return []
        overlaps: list[dict[str, Any]] = []
        for measurement in measurements:
            if (
                not isinstance(measurement, dict)
                or str(measurement.get("metric_id") or "").split("[", 1)[0] != "artist_overlaps"
                or measurement.get("availability") != "available"
            ):
                continue
            data = measurement.get("value") if isinstance(measurement.get("value"), dict) else {}
            raw_overlaps = data.get("overlaps") if isinstance(data, dict) else []
            if not isinstance(raw_overlaps, list):
                continue
            for item in raw_overlaps:
                if isinstance(item, dict):
                    overlaps.append(
                        {
                            "axes": int(item.get("axes", data.get("axis_index", 0))),
                            "a": str(item.get("a", "")),
                            "b": str(item.get("b", "")),
                            "iou": float(item.get("iou", 0.0)),
                        }
                    )
        return overlaps

    def _resolve_project_render_path(self, arguments: dict[str, Any]) -> Path:
        # tools/call validation enforces exactly one of project_id/project_path,
        # so only the single-selector path-or-id resolution is reachable here.
        if arguments.get("project_path"):
            return self._resolve_execution_project_path(arguments["project_path"])
        return self._resolve_project_path(arguments)

    def _project_figure_entries(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        return self._list_section(config, "figures")

    @staticmethod
    def _select_project_figure(
        figures: list[dict[str, Any]],
        *,
        figure_id: Any,
        figure_output: Any,
    ) -> tuple[dict[str, Any] | None, list[str]]:
        if not figures:
            return None, ["Project config has no figures[] entries."]
        id_text = str(figure_id).strip() if isinstance(figure_id, str) and figure_id.strip() else ""
        output_text = str(figure_output).strip() if isinstance(figure_output, str) and figure_output.strip() else ""
        if id_text and output_text:
            matches = [
                figure
                for figure in figures
                if str(figure.get("id") or "") == id_text and str(figure.get("output") or "") == output_text
            ]
            return (
                (matches[0], [])
                if len(matches) == 1
                else (None, ["figure_id and figure_output did not match one figure."])
            )
        if id_text:
            matches = [figure for figure in figures if str(figure.get("id") or "") == id_text]
            return (matches[0], []) if len(matches) == 1 else (None, [f"figure_id not found or ambiguous: {id_text}"])
        if output_text:
            matches = [figure for figure in figures if str(figure.get("output") or "") == output_text]
            return (
                (matches[0], [])
                if len(matches) == 1
                else (None, [f"figure_output not found or ambiguous: {output_text}"])
            )
        if len(figures) == 1:
            return figures[0], []
        return None, ["Project has multiple figures; provide figure_id or figure_output."]

    @staticmethod
    def _figure_selector_summary(figures: list[dict[str, Any]]) -> str:
        selectors = []
        for figure in figures:
            figure_id = str(figure.get("id") or "").strip()
            output = str(figure.get("output") or "").strip()
            selector = ", ".join(part for part in (f"figure_id={figure_id}" if figure_id else "", output) if part)
            if selector:
                selectors.append(selector)
        return "; ".join(selectors) if selectors else "<no configured figures>"

    @staticmethod
    def _public_selected_figure(figure: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(figure.get("id") or ""),
            "script": str(figure.get("script") or ""),
            "output": str(figure.get("output") or ""),
        }

    def _stable_project_id_for_path(self, project_path: Path) -> str:
        # Single source of truth: same id ProjectDiscoveryService assigns, so a
        # rendered project reports back the id list_projects emits for it.
        return ProjectDiscoveryService._stable_project_id(project_path)

    def _public_project_path(self, project_path: Path) -> str:
        try:
            return project_path.resolve().relative_to(self.research_root).as_posix()
        except ValueError:
            return "input://project_path"

    @staticmethod
    def _project_relative_path(raw_path: Any, field_name: str) -> Path:
        return Path(normalize_project_relative_path(raw_path, purpose=field_name))

    @staticmethod
    def _selected_figure_style_summary(
        config: dict[str, Any],
        selected_figure: dict[str, Any],
        arguments: dict[str, Any],
    ) -> dict[str, str]:
        visual_style = config.get("visual_style") if isinstance(config.get("visual_style"), dict) else {}
        output_relpath = str(selected_figure.get("output") or "")
        inferred_format = Path(output_relpath).suffix.lower().lstrip(".") or "png"
        return {
            "target_format": str(arguments.get("target_format") or visual_style.get("target_format") or "nature")
            .strip()
            .lower(),
            "profile": str(arguments.get("profile") or visual_style.get("profile") or DEFAULT_PROFILE).strip()
            or DEFAULT_PROFILE,
            "output_format": str(arguments.get("output_format") or selected_figure.get("format") or inferred_format)
            .strip()
            .lower()
            .lstrip("."),
        }

    @staticmethod
    def _selected_figure_declared_inputs(selected_figure: dict[str, Any]) -> list[str]:
        raw_inputs = selected_figure.get("inputs") or selected_figure.get("input") or []
        if isinstance(raw_inputs, str):
            raw_inputs = [raw_inputs]
        if not isinstance(raw_inputs, list):
            return []
        return [str(item) for item in raw_inputs if isinstance(item, str) and item.strip()]
