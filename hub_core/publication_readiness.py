"""Pure publication-readiness evaluation and deterministic reporting.

This module deliberately has no CLI or MCP dependencies.  It consumes JSON-like
evidence that existing render paths already produce and returns a JSON-like
report.  Automatic evaluation never represents human approval.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

SCHEMA_VERSION: Final = "publication_readiness/1"
ReadinessStatus = Literal["blocked", "needs_revision", "needs_review"]
FindingSeverity = Literal["hard", "major", "info"]
_RELATIVE_BACKSLASH_PATH_RE: Final = re.compile(
    r"^(?!.*(?:^|\\)\.\.(?:\\|$))[A-Za-z0-9_.-]+(?:\\[A-Za-z0-9_.-]+)+$"
)

# Mirrors docs/specs/geometry-diagnostic-rubric-map.json.  Keeping the IDs in
# findings makes the committed rubric the reviewable source of policy.
_GEOMETRY_RUBRIC: Final[dict[str, tuple[str, str]]] = {
    "tick_label_overlaps": ("FQ-H3", "blocked"),
    "tick_label_crowding": ("FQ-A2", "review"),
    "artists_outside_axes": ("FQ-H4", "blocked"),
    "artists_outside_figure": ("FQ-H2", "blocked"),
    "legend_data_collision": ("informational", "non_blocking"),
    "axis_label_title_overlap": ("FQ-H3", "blocked"),
    "figure_title_panel_title_overlap": ("FQ-H3", "blocked"),
    "colorbar_overlap": ("FQ-H3", "blocked"),
    "blank_area_ratio": ("FQ-H4", "blocked"),
    "point_annotation_overlaps": ("FQ-H3", "blocked"),
    "artist_overlaps": ("FQ-H3", "blocked"),
    "legend_internal_overlaps": ("FQ-H3", "blocked"),
    "marker_marker_overlaps": ("FQ-H4", "blocked"),
    "text_axis_edge_proximity": ("FQ-A2", "review"),
    "legend_marker_consistency": ("FQ-A1", "review"),
    "label_offset_consistency": ("FQ-A4", "review"),
    "point_label_skips": ("FQ-A2", "review"),
    "annotation_overlay_contrast": ("FQ-A3", "review"),
    "font_size_token_drift": ("FQ-H2", "blocked"),
    "journal_compliance": ("FQ-H2", "blocked"),
}


@dataclass(frozen=True, slots=True)
class ReadinessFinding:
    """Stable, actionable finding emitted by the readiness evaluator."""

    code: str
    severity: FindingSeverity
    source: str
    message: str
    evidence_ref: str
    recommended_action: str
    affected_panel: int | None = None
    rubric_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "source": self.source,
            "message": self.message,
            "evidence_ref": self.evidence_ref,
            "recommended_action": self.recommended_action,
            "affected_panel": self.affected_panel,
            "rubric_id": self.rubric_id,
            "waivable": False,
        }


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("readiness evidence cannot contain NaN or infinity")
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, str):
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        if _RELATIVE_BACKSLASH_PATH_RE.fullmatch(normalized):
            return normalized.replace("\\", "/")
        return normalized
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("readiness evidence object keys must be strings")
            normalized[key] = _canonical_value(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_canonical_value(item) for item in value]
    raise TypeError(f"unsupported readiness evidence value: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Return the platform-independent canonical JSON representation."""

    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def evidence_digest(evidence: Mapping[str, Any]) -> str:
    """Identify the exact normalized evidence evaluated by this module."""

    return hashlib.sha256(canonical_json_bytes(evidence)).hexdigest()


def _finding(
    *,
    code: str,
    severity: FindingSeverity,
    source: str,
    message: str,
    evidence_ref: str,
    action: str,
    panel: Any = None,
    rubric_id: str | None = None,
) -> ReadinessFinding:
    return ReadinessFinding(
        code=code,
        severity=severity,
        source=source,
        message=message,
        evidence_ref=evidence_ref,
        recommended_action=action,
        affected_panel=panel if isinstance(panel, int) and not isinstance(panel, bool) else None,
        rubric_id=rubric_id,
    )


def _geometry_findings(payload: Mapping[str, Any]) -> list[ReadinessFinding]:
    findings: list[ReadinessFinding] = []
    if payload.get("schema_version") != "geometry_diagnostics/1":
        findings.append(
            _finding(
                code="GEOMETRY_SCHEMA_UNSUPPORTED",
                severity="hard",
                source="geometry_diagnostics",
                message="Geometry evidence uses an unsupported or missing schema version.",
                evidence_ref="geometry_diagnostics.schema_version",
                action="Regenerate geometry diagnostics with schema geometry_diagnostics/1.",
            )
        )
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return [
            _finding(
                code="GEOMETRY_EVIDENCE_INVALID",
                severity="hard",
                source="geometry_diagnostics",
                message="Geometry evidence does not contain a checks list.",
                evidence_ref="geometry_diagnostics.checks",
                action="Re-render the figure and regenerate geometry diagnostics.",
            )
        ]
    seen_names: set[str] = set()
    state_failure_seen = False
    for index, check in enumerate(checks):
        if not isinstance(check, Mapping) or not isinstance(check.get("name"), str):
            findings.append(
                _finding(
                    code="GEOMETRY_CHECK_INVALID",
                    severity="hard",
                    source="geometry_diagnostics",
                    message="A geometry check is malformed.",
                    evidence_ref=f"geometry_diagnostics.checks[{index}]",
                    action="Regenerate geometry diagnostics with a supported FigOps version.",
                )
            )
            continue
        name = check["name"]
        if name in seen_names:
            findings.append(
                _finding(
                    code="GEOMETRY_CHECK_DUPLICATE",
                    severity="hard",
                    source="geometry_diagnostics",
                    message=f"Geometry check name is duplicated: {name}.",
                    evidence_ref=f"geometry_diagnostics.checks[{index}]",
                    action="Regenerate diagnostics with exactly one result per geometry check.",
                )
            )
            continue
        seen_names.add(name)
        mapping = _GEOMETRY_RUBRIC.get(name)
        if mapping is None:
            findings.append(
                _finding(
                    code="GEOMETRY_CHECK_UNKNOWN",
                    severity="hard",
                    source="geometry_diagnostics",
                    message=f"Unknown geometry check requires manual review: {name}.",
                    evidence_ref=f"geometry_diagnostics.checks[{index}]",
                    action="Map the diagnostic to the figure-quality rubric before relying on it.",
                )
            )
            continue
        rubric_id, policy = mapping
        passed = check.get("passed")
        if not isinstance(passed, bool):
            findings.append(
                _finding(
                    code="GEOMETRY_CHECK_PASSED_INVALID",
                    severity="hard",
                    source="geometry_diagnostics",
                    message=f"Geometry check {name} has a non-boolean passed value.",
                    evidence_ref=f"geometry_diagnostics.checks[{index}].passed",
                    action="Regenerate diagnostics with a literal boolean passed result for every check.",
                    rubric_id=rubric_id,
                )
            )
            state_failure_seen = True
            continue
        if passed is True:
            continue
        if policy == "non_blocking":
            if passed is False:
                findings.append(
                    _finding(
                        code=f"GEOMETRY_{name.upper()}",
                        severity="info",
                        source="geometry_diagnostics",
                        message=str(check.get("detail") or f"Informational geometry check {name} failed."),
                        evidence_ref=f"geometry_diagnostics.checks[{index}]",
                        action="Review this informational diagnostic; it does not gate readiness.",
                        panel=check.get("axis_index"),
                        rubric_id=rubric_id,
                    )
                )
            continue
        state_failure_seen = True
        severity: FindingSeverity = "hard" if policy == "blocked" else "major"
        outcome = "was not measured" if passed is None else "failed"
        detail = check.get("detail")
        message = str(detail) if isinstance(detail, str) and detail.strip() else f"Geometry check {name} {outcome}."
        findings.append(
            _finding(
                code=f"GEOMETRY_{name.upper()}",
                severity=severity,
                source="geometry_diagnostics",
                message=message,
                evidence_ref=f"geometry_diagnostics.checks[{index}]",
                action="Correct the figure geometry and re-render the figure.",
                panel=check.get("axis_index"),
                rubric_id=rubric_id,
            )
        )
    summary_passed = payload.get("passed")
    if (summary_passed is True and state_failure_seen) or (summary_passed is not True and not state_failure_seen):
        findings.append(
            _finding(
                code="GEOMETRY_SUMMARY_INCONSISTENT",
                severity="hard",
                source="geometry_diagnostics",
                message="Geometry summary is not passed but no gating check explains the result.",
                evidence_ref="geometry_diagnostics.passed",
                action="Regenerate internally consistent geometry diagnostics.",
            )
        )
    return findings


def _calculation_findings(payload: Mapping[str, Any]) -> list[ReadinessFinding]:
    findings: list[ReadinessFinding] = []
    if payload.get("schema_version") != "1.0":
        findings.append(
            _finding(
                code="CALCULATION_SCHEMA_UNSUPPORTED",
                severity="hard",
                source="calculation_checks",
                message="Calculation evidence uses an unsupported or missing schema version.",
                evidence_ref="calculation_checks.schema_version",
                action="Regenerate calculation evidence with schema 1.0.",
            )
        )
    checks = payload.get("checks")
    if not isinstance(checks, list):
        findings.append(
            _finding(
                code="CALCULATION_EVIDENCE_INVALID",
                severity="hard",
                source="calculation_checks",
                message="Calculation evidence does not contain a checks list.",
                evidence_ref="calculation_checks.checks",
                action="Regenerate the calculation-check sidecar.",
            )
        )
        return findings
    for index, check in enumerate(checks):
        if not isinstance(check, Mapping):
            findings.append(
                _finding(
                    code="CALCULATION_CHECK_INVALID",
                    severity="hard",
                    source="calculation_checks",
                    message="A calculation check is malformed.",
                    evidence_ref=f"calculation_checks.checks[{index}]",
                    action="Regenerate the calculation-check sidecar.",
                )
            )
            continue
        status = check.get("status")
        if status not in {"passed", "failed", "skipped"}:
            findings.append(
                _finding(
                    code="CALCULATION_STATUS_INVALID",
                    severity="hard",
                    source="calculation_checks",
                    message="Calculation check has an unknown or missing status.",
                    evidence_ref=f"calculation_checks.checks[{index}].status",
                    action="Regenerate calculation evidence using passed, failed, or skipped status.",
                )
            )
            continue
        if status == "passed" and check.get("manual_review_needed") is not True:
            continue
        severity: FindingSeverity = "hard" if status == "failed" else "major"
        name = str(check.get("name") or index)
        findings.append(
            _finding(
                code="CALCULATION_REVIEW" if status == "passed" else f"CALCULATION_{status.upper()}",
                severity=severity,
                source="calculation_checks",
                message=str(check.get("message") or f"Calculation check {name} requires attention."),
                evidence_ref=f"calculation_checks.checks[{index}]",
                action="Resolve the calculation check and regenerate its diagnostic sidecar.",
            )
        )
    return findings


def _summary_findings(source: str, payload: Mapping[str, Any]) -> list[ReadinessFinding]:
    if source == "layout_report" and payload.get("schema_version") != "layout_report/1":
        return [
            _finding(
                code="LAYOUT_REPORT_SCHEMA_UNSUPPORTED",
                severity="hard",
                source=source,
                message="Layout report uses an unsupported or missing schema version.",
                evidence_ref="layout_report.schema_version",
                action="Regenerate layout evidence with schema layout_report/1.",
            )
        ]
    if payload.get("passed") is True:
        return []
    code = source.upper().replace("-", "_") + "_FAILED"
    return [
        _finding(
            code=code,
            severity="hard",
            source=source,
            message=f"{source.replace('_', ' ').title()} did not pass.",
            evidence_ref=f"{source}.passed",
            action=f"Resolve the {source.replace('_', ' ')} failures and regenerate the evidence.",
        )
    ]


def evaluate_publication_readiness(
    evidence: Mapping[str, Any],
    *,
    project_id: str | None = None,
    figure_id: str | None = None,
    required_evidence: Sequence[str] = (),
) -> dict[str, Any]:
    """Evaluate evidence into one of three automatic readiness states.

    ``required_evidence`` is supplied by an integration adapter because the
    evidence required for a CSV render and a project render can differ.
    """

    normalized = _canonical_value(evidence)
    if not isinstance(normalized, dict):
        raise TypeError("readiness evidence must be an object")
    findings: list[ReadinessFinding] = []
    for source in required_evidence:
        if source not in normalized or not isinstance(normalized[source], dict):
            findings.append(
                _finding(
                    code="REQUIRED_EVIDENCE_MISSING",
                    severity="hard",
                    source=source,
                    message=f"Required evidence is missing or invalid: {source}.",
                    evidence_ref=source,
                    action=f"Generate valid {source.replace('_', ' ')} evidence before evaluation.",
                )
            )

    geometry = normalized.get("geometry_diagnostics")
    if isinstance(geometry, dict):
        findings.extend(_geometry_findings(geometry))
    calculation = normalized.get("calculation_checks")
    if isinstance(calculation, dict):
        findings.extend(_calculation_findings(calculation))
    for source in ("visual_preflight_status", "layout_report", "data_contract"):
        payload = normalized.get(source)
        if isinstance(payload, dict):
            findings.extend(_summary_findings(source, payload))

    severity_order = {"hard": 0, "major": 1, "info": 2}
    findings.sort(key=lambda item: (severity_order[item.severity], item.source, item.code, item.evidence_ref))
    status: ReadinessStatus
    if any(item.severity == "hard" for item in findings):
        status = "blocked"
    elif any(item.severity == "major" for item in findings):
        status = "needs_revision"
    else:
        status = "needs_review"
    sources = sorted(
        set(required_evidence)
        | {
            source
            for source in (
                "geometry_diagnostics",
                "calculation_checks",
                "visual_preflight_status",
                "layout_report",
                "data_contract",
            )
            if source in normalized
        }
    )
    gates = []
    for source in sources:
        related = [item for item in findings if item.source == source]
        outcome = "blocked" if any(item.severity == "hard" for item in related) else "needs_revision" if any(
            item.severity == "major" for item in related
        ) else "passed"
        gates.append(
            {
                "source": source,
                "outcome": outcome,
                "evidence_ref": source,
            }
        )
    style_summary = normalized.get("style_summary")
    target_format = style_summary.get("target_format") if isinstance(style_summary, dict) else None
    if not isinstance(target_format, str):
        target_format = None
    return {
        "schema_version": SCHEMA_VERSION,
        "readiness_status": status,
        "project_id": project_id,
        "figure_id": figure_id,
        "target_format": target_format,
        "evidence_digest": evidence_digest(normalized),
        "manual_review_required": True,
        "gates": gates,
        "findings": [item.as_dict() for item in findings],
    }


def render_readiness_json(report: Mapping[str, Any]) -> str:
    """Render a byte-stable, human-readable JSON report."""

    normalized = _canonical_value(report)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def render_readiness_markdown(report: Mapping[str, Any]) -> str:
    """Render a deterministic Markdown summary without claiming approval."""

    status = str(report.get("readiness_status", "blocked"))
    digest = str(report.get("evidence_digest", ""))
    target_format = report.get("target_format")
    target_label = target_format if isinstance(target_format, str) else "unspecified"
    lines = [
        "# Publication Readiness Report",
        "",
        f"- Status: `{status}`",
        f"- Target format: `{target_label}`",
        f"- Evidence digest: `{digest}`",
        "- Manual review required: `true`",
        "",
        "Automatic evaluation does not constitute publication approval.",
        "",
        "## Gates",
        "",
    ]
    gates = report.get("gates")
    if isinstance(gates, list) and gates:
        for gate in gates:
            if isinstance(gate, Mapping):
                lines.append(
                    f"- `{gate.get('source', 'unknown')}`: `{gate.get('outcome', 'blocked')}` "
                    f"(evidence: `{gate.get('evidence_ref', 'unknown')}`)"
                )
    else:
        lines.append("No automatic gates were supplied.")
    lines.extend(["", "## Findings", ""])
    findings = report.get("findings")
    if not isinstance(findings, list) or not findings:
        lines.append("No automatic findings. Human review is still required.")
    else:
        for finding in findings:
            if not isinstance(finding, Mapping):
                continue
            lines.extend(
                [
                    f"### {finding.get('code', 'UNKNOWN')}",
                    "",
                    f"- Severity: `{finding.get('severity', 'hard')}`",
                    f"- Source: `{finding.get('source', 'unknown')}`",
                    f"- Evidence: `{finding.get('evidence_ref', 'unknown')}`",
                    f"- Message: {finding.get('message', '')}",
                    f"- Recommended action: {finding.get('recommended_action', '')}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"
