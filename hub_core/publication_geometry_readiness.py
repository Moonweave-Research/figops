"""Geometry evidence and selected-policy projection evaluation.

The raw v2 path validates policy-free measurements.  Severity is consumed only
from a validated, explicitly selected policy projection.  Legacy v1 checks are
kept as a compatibility adapter.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final

FindingFactory = Callable[..., Any]

_RAW_POLICY_FIELDS: Final = frozenset(
    {
        "advisory",
        "blocked",
        "compliant",
        "font_offenders",
        "fail",
        "failed",
        "hard",
        "height_offender",
        "line_offenders",
        "limit",
        "limits",
        "max",
        "max_figure_height_mm",
        "maximum",
        "min",
        "min_font_size_pt",
        "min_line_width_pt",
        "minimum",
        "offender",
        "offenders",
        "outcome",
        "pass",
        "passed",
        "policy_id",
        "policy_version",
        "severity",
        "threshold",
        "verdict",
        "violation",
        "violations",
    }
)
_AVAILABILITY: Final = frozenset({"available", "unavailable", "not_applicable", "unknown"})
_OBJECTIVE_HARD_METRICS: Final = frozenset(
    {
        "artists_outside_figure",
        "clipping",
        "geometry.clipping",
        "style_geometry_observations",
    }
)
_POLICY_PAIR: Final = {
    "hard": "blocked",
    "advisory": "needs_revision",
    "informational": "informational",
}
_LEGACY_RUBRIC: Final[dict[str, tuple[str, str]]] = {
    "tick_label_overlaps": ("FQ-H3", "review"),
    "tick_label_crowding": ("FQ-A2", "review"),
    "artists_outside_axes": ("FQ-H4", "review"),
    "artists_outside_figure": ("FQ-H2", "blocked"),
    "legend_data_collision": ("informational", "non_blocking"),
    "axis_label_title_overlap": ("FQ-H3", "review"),
    "figure_title_panel_title_overlap": ("FQ-H3", "review"),
    "colorbar_overlap": ("FQ-H3", "review"),
    "blank_area_ratio": ("FQ-H4", "review"),
    "point_annotation_overlaps": ("FQ-H3", "review"),
    "artist_overlaps": ("FQ-H3", "review"),
    "legend_internal_overlaps": ("FQ-H3", "review"),
    "marker_marker_overlaps": ("FQ-H4", "review"),
    "text_axis_edge_proximity": ("FQ-A2", "review"),
    "legend_marker_consistency": ("FQ-A1", "review"),
    "label_offset_consistency": ("FQ-A4", "review"),
    "point_label_skips": ("FQ-A2", "review"),
    "annotation_overlay_contrast": ("FQ-A3", "review"),
    "font_size_token_drift": ("FQ-H2", "review"),
    "journal_compliance": ("FQ-H2", "review"),
}


def _base(identifier: str) -> str:
    return identifier.split("[", 1)[0]


def _policy_field_path(value: Any, path: str) -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in _RAW_POLICY_FIELDS:
                return child_path
            found = _policy_field_path(child, child_path)
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _policy_field_path(child, f"{path}[{index}]")
            if found:
                return found
    return None


def _panel(scope: Any) -> int | None:
    if isinstance(scope, str):
        match = re.fullmatch(r"axis=(\d+)", scope)
        return int(match.group(1)) if match else None
    if isinstance(scope, Mapping):
        for key in ("axis", "axis_index", "panel"):
            value = scope.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return None


def _emit(finding: FindingFactory, code: str, severity: str, message: str, ref: str, action: str, **extra: Any) -> Any:
    return finding(
        code=code,
        severity=severity,
        source="geometry_diagnostics",
        message=message,
        evidence_ref=ref,
        action=action,
        **extra,
    )


def _v2_findings(
    payload: Mapping[str, Any],
    required_ids: Sequence[str],
    finding: FindingFactory,
) -> tuple[list[Any], dict[str, Mapping[str, Any]]]:
    results: list[Any] = []
    by_id: dict[str, Mapping[str, Any]] = {}
    unknown = sorted(set(payload) - {"schema_version", "measurements", "warnings", "data"})
    if unknown:
        results.append(
            _emit(
                finding,
                "GEOMETRY_FIELD_UNKNOWN",
                "hard",
                "Raw geometry evidence contains an unknown field.",
                f"geometry_diagnostics.{unknown[0]}",
                "Regenerate the sidecar with the frozen raw geometry shape.",
            )
        )
    forbidden = _policy_field_path(payload, "geometry_diagnostics")
    if forbidden:
        results.append(
            _emit(
                finding,
                "GEOMETRY_RAW_POLICY_FIELD_FORBIDDEN",
                "hard",
                "Raw geometry evidence contains a policy-owned field.",
                forbidden,
                "Move thresholds, verdicts, and severity into a policy projection.",
            )
        )
    warnings = payload.get("warnings")
    if not isinstance(warnings, list) or not all(isinstance(item, str) for item in warnings):
        results.append(
            _emit(
                finding,
                "GEOMETRY_WARNINGS_INVALID",
                "hard",
                "Raw geometry warnings must be a list of strings.",
                "geometry_diagnostics.warnings",
                "Regenerate the canonical warnings container.",
            )
        )
    measurements = payload.get("measurements")
    if not isinstance(measurements, list):
        results.append(
            _emit(
                finding,
                "GEOMETRY_EVIDENCE_INVALID",
                "hard",
                "Raw geometry evidence does not contain a measurements list.",
                "geometry_diagnostics.measurements",
                "Re-render and regenerate raw geometry diagnostics.",
            )
        )
        return results, by_id

    seen_bases: set[str] = set()
    allowed = {"id", "metric_id", "availability", "value", "unit", "scope", "reason"}
    for index, measurement in enumerate(measurements):
        path = f"geometry_diagnostics.measurements[{index}]"
        if not isinstance(measurement, Mapping):
            results.append(
                _emit(
                    finding,
                    "GEOMETRY_MEASUREMENT_INVALID",
                    "hard",
                    "A raw geometry measurement is malformed.",
                    path,
                    "Regenerate the sidecar using the frozen measurement contract.",
                )
            )
            continue
        has_id, has_metric_id = "id" in measurement, "metric_id" in measurement
        raw_identifier = measurement.get("id") if has_id else measurement.get("metric_id")
        if has_id == has_metric_id or not isinstance(raw_identifier, str) or not raw_identifier.strip():
            results.append(
                _emit(
                    finding,
                    "GEOMETRY_MEASUREMENT_ID_INVALID",
                    "hard",
                    "A measurement must have exactly one non-empty id or metric_id.",
                    path,
                    "Regenerate the sidecar with one stable identifier per measurement.",
                )
            )
            continue
        identifier = raw_identifier.strip()
        extra_fields = sorted(set(measurement) - allowed)
        if extra_fields:
            results.append(
                _emit(
                    finding,
                    "GEOMETRY_MEASUREMENT_FIELD_UNKNOWN",
                    "hard",
                    f"Geometry measurement {identifier} contains an unknown field.",
                    f"{path}.{extra_fields[0]}",
                    "Regenerate the sidecar with the frozen measurement shape.",
                )
            )
        if identifier in by_id:
            results.append(
                _emit(
                    finding,
                    "GEOMETRY_MEASUREMENT_DUPLICATE",
                    "hard",
                    f"Geometry measurement ID is duplicated: {identifier}.",
                    path,
                    "Regenerate the sidecar with unique measurement IDs.",
                )
            )
            continue
        by_id[identifier] = measurement
        metric_base = _base(identifier)
        seen_bases.add(metric_base)
        availability = measurement.get("availability")
        if availability not in _AVAILABILITY:
            results.append(
                _emit(
                    finding,
                    "GEOMETRY_AVAILABILITY_INVALID",
                    "hard",
                    f"Geometry measurement {identifier} has invalid availability.",
                    f"{path}.availability",
                    "Use a frozen evidence-contract availability value.",
                )
            )
            continue
        if availability == "available":
            if "value" not in measurement:
                results.append(
                    _emit(
                        finding,
                        "GEOMETRY_VALUE_MISSING",
                        "hard",
                        f"Available geometry measurement {identifier} has no value.",
                        f"{path}.value",
                        "Regenerate the complete raw measurement.",
                    )
                )
            continue
        reason = measurement.get("reason")
        malformed = "value" in measurement or not isinstance(reason, str) or not reason.strip()
        required = identifier in required_ids or metric_base in required_ids
        results.append(
            _emit(
                finding,
                "GEOMETRY_MEASUREMENT_UNAVAILABLE_INVALID"
                if malformed
                else "GEOMETRY_REQUIRED_DIAGNOSTIC_UNAVAILABLE"
                if required
                else "GEOMETRY_DIAGNOSTIC_UNAVAILABLE",
                "hard" if malformed or required else "info",
                f"Unavailable geometry measurement {identifier} is malformed." if malformed else str(reason),
                path,
                "Regenerate the required raw diagnostic before applying the selected policy."
                if required
                else "Review whether this optional diagnostic is relevant.",
                panel=_panel(measurement.get("scope")),
            )
        )
    missing = sorted(item for item in set(required_ids) if item not in by_id and item not in seen_bases)
    if missing:
        results.append(
            _emit(
                finding,
                "GEOMETRY_REQUIRED_DIAGNOSTICS_MISSING",
                "hard",
                f"Required diagnostic IDs are missing: {', '.join(missing)}.",
                "geometry_diagnostics.measurements",
                "Regenerate the complete diagnostic set required by the selected policy.",
            )
        )
    if not measurements:
        results.append(
            _emit(
                finding,
                "GEOMETRY_DIAGNOSTICS_UNAVAILABLE",
                "hard" if required_ids else "info",
                "Geometry diagnostics contain no measurements.",
                "geometry_diagnostics.measurements",
                "Generate raw diagnostics when required by the selected policy.",
            )
        )
    return results, by_id


def _v1_findings(payload: Mapping[str, Any], required_ids: Sequence[str], finding: FindingFactory) -> list[Any]:
    results: list[Any] = []
    if payload.get("schema_version") != "geometry_diagnostics/1":
        results.append(
            _emit(
                finding,
                "GEOMETRY_SCHEMA_UNSUPPORTED",
                "hard",
                "Geometry evidence uses an unsupported or missing schema version.",
                "geometry_diagnostics.schema_version",
                "Regenerate geometry diagnostics with a supported schema.",
            )
        )
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return results + [
            _emit(
                finding,
                "GEOMETRY_EVIDENCE_INVALID",
                "hard",
                "Geometry evidence does not contain a checks list.",
                "geometry_diagnostics.checks",
                "Re-render and regenerate geometry diagnostics.",
            )
        ]
    seen: set[str] = set()
    unavailable = False
    failed = False
    for index, check in enumerate(checks):
        path = f"geometry_diagnostics.checks[{index}]"
        if not isinstance(check, Mapping) or not isinstance(check.get("name"), str):
            results.append(
                _emit(
                    finding,
                    "GEOMETRY_CHECK_INVALID",
                    "hard",
                    "A geometry check is malformed.",
                    path,
                    "Regenerate supported diagnostics.",
                )
            )
            continue
        name = check["name"]
        if name in seen:
            results.append(
                _emit(
                    finding,
                    "GEOMETRY_CHECK_DUPLICATE",
                    "hard",
                    f"Geometry check name is duplicated: {name}.",
                    path,
                    "Emit one result per geometry check.",
                )
            )
            continue
        seen.add(name)
        mapping = _LEGACY_RUBRIC.get(name)
        if mapping is None:
            results.append(
                _emit(
                    finding,
                    "GEOMETRY_CHECK_UNKNOWN",
                    "hard",
                    f"Unknown geometry check requires manual review: {name}.",
                    path,
                    "Map the diagnostic before relying on it.",
                )
            )
            continue
        rubric_id, policy = mapping
        passed = check.get("passed")
        if passed is None:
            unavailable = True
            required = name in required_ids
            results.append(
                _emit(
                    finding,
                    "GEOMETRY_REQUIRED_DIAGNOSTIC_UNAVAILABLE" if required else "GEOMETRY_DIAGNOSTIC_UNAVAILABLE",
                    "hard" if required else "info",
                    str(check.get("detail") or f"Geometry check {name} was not measured."),
                    path,
                    "Regenerate the required diagnostic."
                    if required
                    else "Review if this optional diagnostic is relevant.",
                    panel=check.get("axis_index"),
                    rubric_id=rubric_id,
                )
            )
            continue
        if not isinstance(passed, bool):
            results.append(
                _emit(
                    finding,
                    "GEOMETRY_CHECK_PASSED_INVALID",
                    "hard",
                    f"Geometry check {name} has a non-boolean passed value.",
                    f"{path}.passed",
                    "Regenerate diagnostics with a literal boolean.",
                    rubric_id=rubric_id,
                )
            )
            continue
        if passed:
            continue
        failed = True
        severity = "info" if policy == "non_blocking" else "hard" if policy == "blocked" else "major"
        results.append(
            _emit(
                finding,
                f"GEOMETRY_{name.upper()}",
                severity,
                str(check.get("detail") or f"Geometry check {name} failed."),
                path,
                "Review this informational diagnostic; it does not gate readiness."
                if severity == "info"
                else "Correct the figure geometry and re-render.",
                panel=check.get("axis_index"),
                rubric_id=rubric_id,
            )
        )
    missing = sorted(set(required_ids) - seen)
    if missing:
        results.append(
            _emit(
                finding,
                "GEOMETRY_REQUIRED_DIAGNOSTICS_MISSING",
                "hard",
                f"Required diagnostic IDs are missing: {', '.join(missing)}.",
                "geometry_diagnostics.checks",
                "Regenerate the complete required diagnostic set.",
            )
        )
    summary = payload.get("passed")
    if not checks and summary is None:
        unavailable = True
        results.append(
            _emit(
                finding,
                "GEOMETRY_DIAGNOSTICS_UNAVAILABLE",
                "info",
                "Geometry diagnostics were not produced for this render.",
                "geometry_diagnostics",
                "Generate diagnostics only when required.",
            )
        )
    conflict = (
        summary not in (True, False, None)
        or (summary is True and (failed or unavailable))
        or (summary is False and not (failed or unavailable))
        or (summary is None and not unavailable)
    )
    if conflict:
        results.append(
            _emit(
                finding,
                "GEOMETRY_SUMMARY_INCONSISTENT",
                "hard",
                "Geometry summary conflicts with check details.",
                "geometry_diagnostics.passed",
                "Regenerate internally consistent compatibility diagnostics.",
            )
        )
    return results


def geometry_findings(
    payload: Mapping[str, Any],
    *,
    required_diagnostic_ids: Sequence[str] = (),
    finding: FindingFactory,
) -> tuple[list[Any], dict[str, Mapping[str, Any]]]:
    """Validate raw v2 measurements or adapt legacy v1 checks."""

    if payload.get("schema_version") == "geometry_diagnostics/2":
        return _v2_findings(payload, required_diagnostic_ids, finding)
    return _v1_findings(payload, required_diagnostic_ids, finding), {}


def _projection_resolution_conflict(
    projection: Mapping[str, Any],
    resolved_policy: Mapping[str, Any],
) -> bool:
    local = projection.get("resolved")
    if local is None:
        return False
    if not isinstance(local, Mapping):
        return True
    parameters = resolved_policy.get("parameters", {})
    if not isinstance(parameters, Mapping) or set(local) != set(parameters):
        return True
    canonical_source = resolved_policy.get("source")
    for name, value in parameters.items():
        resolution = local.get(name)
        if not isinstance(resolution, Mapping) or resolution.get("value") != value:
            return True
        if resolution.get("source") not in {canonical_source, "resolved_policy"}:
            return True
    return False


def policy_projection_findings(
    envelope: Mapping[str, Any],
    measurements_by_id: Mapping[str, Mapping[str, Any]],
    *,
    policy_ids: Sequence[str],
    finding: FindingFactory,
) -> tuple[list[Any], list[str]]:
    """Apply only validated projections explicitly selected by the caller."""

    results: list[Any] = []
    applied: list[str] = []
    projections = envelope.get("policy_projections")
    if not isinstance(projections, list):
        return results, applied
    by_id: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
    for index, projection in enumerate(projections):
        if isinstance(projection, Mapping) and isinstance(projection.get("id"), str):
            by_id.setdefault(projection["id"], []).append((index, projection))
    resolved_policy = envelope.get("resolved_policy")
    for policy_id in sorted(set(policy_ids)):
        matches = by_id.get(policy_id, [])
        if len(matches) != 1:
            results.append(
                finding(
                    code="POLICY_PROJECTION_MISSING" if not matches else "POLICY_PROJECTION_DUPLICATE",
                    severity="hard",
                    source="policy_projection",
                    message=f"Selected policy must have exactly one validated projection: {policy_id}.",
                    evidence_ref="policy_projections",
                    action="Generate exactly one validated projection for every selected policy.",
                )
            )
            continue
        index, projection = matches[0]
        version = str(projection.get("version") or "")
        if not isinstance(resolved_policy, Mapping):
            results.append(
                finding(
                    code="POLICY_RESOLUTION_MISSING",
                    severity="hard",
                    source="policy_projection",
                    message=f"Selected policy {policy_id}@{version} lacks a resolved policy snapshot.",
                    evidence_ref="resolved_policy",
                    action="Record the canonical resolved_policy snapshot before applying the projection.",
                    rubric_id=f"{policy_id}@{version}",
                )
            )
            continue
        if resolved_policy.get("id") != policy_id or str(resolved_policy.get("version") or "") != version:
            results.append(
                finding(
                    code="POLICY_RESOLUTION_MISMATCH",
                    severity="hard",
                    source="policy_projection",
                    message=f"Selected projection {policy_id}@{version} does not match resolved_policy.",
                    evidence_ref="resolved_policy",
                    action="Select the projection matching the canonical resolved policy snapshot.",
                    rubric_id=f"{policy_id}@{version}",
                )
            )
            continue
        if _projection_resolution_conflict(projection, resolved_policy):
            results.append(
                finding(
                    code="POLICY_PROJECTION_RESOLUTION_CONFLICT",
                    severity="hard",
                    source="policy_projection",
                    message="Projection-local resolved values conflict with canonical resolved_policy.",
                    evidence_ref=f"policy_projections[{index}].resolved",
                    action="Remove the override or make it exactly reference the canonical snapshot.",
                    rubric_id=f"{policy_id}@{version}",
                )
            )
            continue
        raw_findings = projection.get("findings")
        if not isinstance(raw_findings, list):
            applied.append(policy_id)
            continue
        projection_valid = True
        projected_results: list[Any] = []
        for finding_index, raw in enumerate(raw_findings):
            if not isinstance(raw, Mapping):
                projection_valid = False
                results.append(
                    finding(
                        code="POLICY_FINDING_INVALID",
                        severity="hard",
                        source="policy_projection",
                        message="A selected policy projection contains a malformed finding.",
                        evidence_ref=f"policy_projections[{index}].findings[{finding_index}]",
                        action="Regenerate the complete projection from validated raw evidence.",
                        rubric_id=f"{policy_id}@{version}",
                    )
                )
                continue
            metric_id = str(raw.get("metric_id") or "")
            measurement = measurements_by_id.get(metric_id)
            path = f"policy_projections[{index}].findings[{finding_index}]"
            if measurement is None or measurement.get("availability") != "available":
                projection_valid = False
                results.append(
                    finding(
                        code="POLICY_FINDING_METRIC_UNKNOWN"
                        if measurement is None
                        else "POLICY_FINDING_METRIC_UNAVAILABLE",
                        severity="hard",
                        source="policy_projection",
                        message="A selected policy finding lacks available referenced raw evidence.",
                        evidence_ref=path,
                        action="Regenerate the projection from the exact available measurement set.",
                        rubric_id=f"{policy_id}@{version}",
                    )
                )
                continue
            projected_severity = str(raw.get("severity") or "")
            projected_outcome = str(raw.get("outcome") or "")
            if _POLICY_PAIR.get(projected_severity) != projected_outcome:
                projection_valid = False
                results.append(
                    finding(
                        code="POLICY_FINDING_OUTCOME_INCONSISTENT",
                        severity="hard",
                        source="policy_projection",
                        message="A selected policy finding has inconsistent severity and outcome.",
                        evidence_ref=path,
                        action="Regenerate the projection with the closed severity/outcome pairing.",
                        rubric_id=f"{policy_id}@{version}",
                    )
                )
                continue
            code = str(raw.get("code") or "POLICY_FINDING")
            message = str(raw.get("message") or "Selected policy finding.")
            if projected_severity == "hard" and _base(metric_id) in _OBJECTIVE_HARD_METRICS:
                severity = "hard"
            elif projected_severity == "hard":
                severity = "major"
                code = f"{code}_AESTHETIC_ADVISORY"
                message = f"{message} This aesthetic measurement is advisory, not a hard gate."
            else:
                severity = "major" if projected_severity == "advisory" else "info"
            projected_results.append(
                finding(
                    code=code,
                    severity=severity,
                    source="policy_projection",
                    message=message,
                    evidence_ref=metric_id,
                    action="Correct the objective selected-policy violation and re-render."
                    if severity == "hard"
                    else "Review the policy evidence together with the rendered figure.",
                    panel=_panel(measurement.get("scope")),
                    rubric_id=f"{policy_id}@{version}",
                )
            )
        if projection_valid:
            results.extend(projected_results)
            applied.append(policy_id)
    return results, applied
