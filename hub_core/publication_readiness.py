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

from .evidence_contract import EvidenceContractError, normalize_evidence_envelope
from .provenance_inputs import REQUIRED_PROVENANCE_HASHES, provenance_hash_coverage
from .publication_geometry_readiness import (
    geometry_findings as _geometry_findings,
)
from .publication_geometry_readiness import (
    policy_projection_findings as _policy_projection_findings,
)

SCHEMA_VERSION: Final = "publication_readiness/1"
RENDER_JOB_REQUIRED_EVIDENCE: Final = (
    "artifact_integrity",
    "provenance_coverage",
    "geometry_diagnostics",
    "visual_preflight_status",
    "layout_report",
)
ReadinessStatus = Literal["blocked", "needs_revision", "needs_review"]
FindingSeverity = Literal["hard", "major", "info"]
_RELATIVE_BACKSLASH_PATH_RE: Final = re.compile(r"^(?!.*(?:^|\\)\.\.(?:\\|$))[A-Za-z0-9_.-]+(?:\\[A-Za-z0-9_.-]+)+$")


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
        if status not in {"passed", "warning", "failed", "skipped"}:
            findings.append(
                _finding(
                    code="CALCULATION_STATUS_INVALID",
                    severity="hard",
                    source="calculation_checks",
                    message="Calculation check has an unknown or missing status.",
                    evidence_ref=f"calculation_checks.checks[{index}].status",
                    action="Regenerate calculation evidence using passed, warning, failed, or skipped status.",
                )
            )
            continue
        if status == "passed" and check.get("manual_review_needed") is not True:
            continue
        severity: FindingSeverity = "hard" if status == "failed" else "major"
        name = str(check.get("name") or index)
        findings.append(
            _finding(
                code=(
                    "CALCULATION_REVIEW"
                    if status == "passed"
                    else "CALCULATION_WARNING"
                    if status == "warning"
                    else f"CALCULATION_{status.upper()}"
                ),
                severity=severity,
                source="calculation_checks",
                message=str(check.get("message") or f"Calculation check {name} requires attention."),
                evidence_ref=f"calculation_checks.checks[{index}]",
                action="Resolve the calculation check and regenerate its diagnostic sidecar.",
            )
        )
    return findings


def _summary_findings(source: str, payload: Mapping[str, Any]) -> list[ReadinessFinding]:
    if source == "layout_report":
        if payload.get("schema_version") != "layout_report/1":
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
        aggregate = payload.get("passed")
        render_errors = payload.get("render_errors", [])
        if aggregate not in (True, False, None) or not isinstance(render_errors, list):
            return [
                _finding(
                    code="LAYOUT_REPORT_INVALID",
                    severity="hard",
                    source=source,
                    message="Layout compatibility evidence is malformed.",
                    evidence_ref="layout_report",
                    action="Regenerate the layout compatibility projection.",
                )
            ]
        if render_errors:
            return [
                _finding(
                    code="LAYOUT_RENDER_ERROR",
                    severity="hard",
                    source=source,
                    message="Layout evidence records a render execution error.",
                    evidence_ref="layout_report.render_errors",
                    action="Resolve the render error and regenerate the artifact.",
                )
            ]
        return []
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


def _integrity_findings(evidence: Mapping[str, Any]) -> list[ReadinessFinding]:
    findings: list[ReadinessFinding] = []
    artifact_status = evidence.get("artifact_status")
    failure_stage = evidence.get("failure_stage")
    normalized_status = str(artifact_status or "").strip().lower()
    if normalized_status in {"failed", "error", "missing", "corrupt"}:
        findings.append(
            _finding(
                code="ARTIFACT_STATUS_FAILED",
                severity="hard",
                source="artifact_integrity",
                message=f"Artifact producer reported a failed state: {normalized_status}.",
                evidence_ref="artifact_status",
                action="Resolve the render/export failure and produce a verified artifact.",
            )
        )
    if isinstance(failure_stage, str) and failure_stage.strip():
        findings.append(
            _finding(
                code="FAILURE_STAGE_REPORTED",
                severity="hard",
                source="artifact_integrity",
                message=f"The producer reported failure stage {failure_stage.strip()}.",
                evidence_ref="failure_stage",
                action="Resolve the producer failure before readiness evaluation.",
            )
        )

    artifact_integrity = evidence.get("artifact_integrity")
    if isinstance(artifact_integrity, Mapping):
        errors = artifact_integrity.get("errors")
        entries = artifact_integrity.get("entries")
        integrity_valid = (
            artifact_integrity.get("status") == "passed"
            and isinstance(entries, list)
            and bool(entries)
            and isinstance(errors, list)
            and not errors
        )
        if not integrity_valid:
            findings.append(
                _finding(
                    code="ARTIFACT_INTEGRITY_FAILED",
                    severity="hard",
                    source="artifact_integrity",
                    message="Artifact existence, media header, dimensions, or hash verification failed.",
                    evidence_ref="artifact_integrity",
                    action="Regenerate the declared artifact and its integrity evidence.",
                )
            )

    completed_artifact = bool(
        normalized_status
        and normalized_status not in {"failed", "error", "missing", "corrupt", "skipped", "unavailable"}
    ) or (isinstance(artifact_integrity, Mapping) and artifact_integrity.get("status") == "passed")
    supplied_coverage = evidence.get("provenance_coverage")
    coverage = provenance_hash_coverage(evidence.get("provenance")) if completed_artifact else None
    if completed_artifact and isinstance(supplied_coverage, Mapping):
        expected_coverage = {
            "status": coverage["status"],
            "hashes": coverage["hashes"],
            "missing": coverage["missing"],
        }
        actual_coverage = {
            "status": supplied_coverage.get("status"),
            "hashes": supplied_coverage.get("hashes"),
            "missing": supplied_coverage.get("missing"),
        }
        if actual_coverage != expected_coverage:
            findings.append(
                _finding(
                    code="PROVENANCE_COVERAGE_INCONSISTENT",
                    severity="hard",
                    source="provenance",
                    message="Provenance coverage summary conflicts with the supplied provenance hashes.",
                    evidence_ref="provenance_coverage",
                    action="Regenerate coverage from the allowlisted provenance hash fields.",
                )
            )
    if isinstance(coverage, Mapping) and completed_artifact:
        missing = coverage.get("missing")
        if not isinstance(missing, list):
            missing = list(REQUIRED_PROVENANCE_HASHES)
        if missing:
            findings.append(
                _finding(
                    code="PROVENANCE_HASHES_MISSING",
                    severity="hard",
                    source="provenance",
                    message=f"Required provenance hashes are missing: {', '.join(map(str, missing))}.",
                    evidence_ref="provenance_coverage.missing",
                    action="Record input, config, script, environment, and output SHA-256 hashes.",
                )
            )

    raw = evidence.get("raw_integrity_status")
    if isinstance(raw, Mapping) and raw.get("configured") is True and raw.get("ok") is not True:
        strict = str(raw.get("mode") or "").lower() == "strict"
        findings.append(
            _finding(
                code="RAW_INTEGRITY_STRICT_FAILED" if strict else "RAW_INTEGRITY_WARNING",
                severity="hard" if strict else "major",
                source="raw_integrity",
                message="Raw data integrity is unsealed or does not match its seal.",
                evidence_ref="raw_integrity_status",
                action="Seal or reconcile the declared raw inputs before continuing.",
            )
        )

    canonical = evidence.get("canonical_docs_registry")
    if isinstance(canonical, Mapping) and canonical.get("declared") is True and canonical.get("required") is True:
        docs = canonical.get("docs")
        valid = isinstance(docs, list) and bool(docs)
        if valid:
            valid = all(
                isinstance(doc, Mapping)
                and doc.get("exists") is True
                and doc.get("contained") is True
                and doc.get("regular_file") is True
                and doc.get("symlinked") is False
                and doc.get("status") == "ready"
                for doc in docs
            )
        if not valid:
            findings.append(
                _finding(
                    code="CANONICAL_DOC_EVIDENCE_INVALID",
                    severity="hard",
                    source="canonical_docs",
                    message="Required canonical documentation lacks valid contained regular-file evidence.",
                    evidence_ref="canonical_docs_registry.docs",
                    action="Restore and revalidate every required canonical document.",
                )
            )
    return findings


def _v2_consistency_findings(evidence: Mapping[str, Any]) -> list[ReadinessFinding]:
    if evidence.get("version") != "2.0":
        return []
    try:
        normalized = normalize_evidence_envelope(evidence)
    except EvidenceContractError as exc:
        return [
            _finding(
                code=f"EVIDENCE_CONTRACT_{exc.code}",
                severity="hard",
                source="evidence_contract",
                message=exc.message,
                evidence_ref=exc.path,
                action="Regenerate a valid figops_evidence/2 envelope.",
            )
        ]

    findings: list[ReadinessFinding] = []
    for index, projection in enumerate(normalized.get("policy_projections", [])):
        if "status" in projection and projection["status"] not in {
            "blocked",
            "needs_revision",
            "needs_review",
            "informational",
        }:
            findings.append(
                _finding(
                    code="POLICY_PROJECTION_STATUS_INVALID",
                    severity="hard",
                    source="evidence_contract",
                    message="Policy projection status is outside the closed outcome enum.",
                    evidence_ref=f"policy_projections[{index}].status",
                    action="Regenerate the policy projection with a supported status.",
                )
            )

    exact = normalized.get("exact_reproducibility")
    if isinstance(exact, Mapping) and exact.get("status") in {"same", "different"}:
        same = exact.get("reference_sha256") == exact.get("candidate_sha256")
        status_consistent = (exact.get("status") == "same") == same
        if str(exact.get("algorithm") or "").lower() != "sha256" or not status_consistent:
            findings.append(
                _finding(
                    code="EXACT_REPRODUCIBILITY_INCONSISTENT",
                    severity="hard",
                    source="evidence_contract",
                    message="Exact reproducibility status conflicts with SHA-256 evidence.",
                    evidence_ref="exact_reproducibility",
                    action="Recompute exact-byte evidence using SHA-256.",
                )
            )

    roles = {
        entry.get("logical_role")
        for entry in normalized.get("artifacts", {}).get("entries", [])
        if isinstance(entry, Mapping)
    }
    visual = normalized.get("visual_comparison")
    if isinstance(visual, Mapping) and visual.get("status") == "available":
        refs = {visual.get("reference_artifact"), visual.get("candidate_artifact")}
        if not refs <= roles:
            findings.append(
                _finding(
                    code="VISUAL_ARTIFACT_REFERENCE_UNKNOWN",
                    severity="hard",
                    source="evidence_contract",
                    message="Visual comparison references artifacts absent from the verified artifact set.",
                    evidence_ref="visual_comparison",
                    action="Reference verified logical artifact roles only.",
                )
            )
    entries = normalized.get("artifacts", {}).get("entries", [])
    output_hash = normalized.get("provenance", {}).get("output_sha256")
    if entries and isinstance(output_hash, str) and output_hash != entries[0].get("sha256"):
        findings.append(
            _finding(
                code="PROVENANCE_OUTPUT_HASH_MISMATCH",
                severity="hard",
                source="provenance",
                message="Output provenance hash does not match the primary artifact entry.",
                evidence_ref="provenance.output_sha256",
                action="Regenerate provenance from the verified artifact bytes.",
            )
        )
    return findings


def _reproducibility_findings(evidence: Mapping[str, Any]) -> list[ReadinessFinding]:
    findings: list[ReadinessFinding] = []
    exact = evidence.get("exact_reproducibility", evidence.get("baseline_comparison"))
    if isinstance(exact, Mapping):
        checked = exact.get("checked") is True or exact.get("status") in {"same", "different"}
        matched = exact.get("matched")
        status = exact.get("status")
        different = matched is False or status == "different"
        if checked and different:
            findings.append(
                _finding(
                    code="EXACT_BYTES_DIFFERENT",
                    severity="info",
                    source="exact_reproducibility",
                    message="Candidate bytes differ from the exact SHA-256 reference.",
                    evidence_ref=(
                        "exact_reproducibility" if "exact_reproducibility" in evidence else "baseline_comparison"
                    ),
                    action="Treat this as exact non-identity, not as a visual-quality conclusion.",
                )
            )
    visual = evidence.get("visual_comparison")
    if isinstance(visual, Mapping) and visual.get("status") in {"unavailable", "skipped"}:
        findings.append(
            _finding(
                code="VISUAL_COMPARISON_UNAVAILABLE",
                severity="info",
                source="visual_comparison",
                message=str(visual.get("reason") or "Visual comparison was unavailable."),
                evidence_ref="visual_comparison",
                action=(
                    "Supply a named reference/candidate and versioned algorithm only if visual comparison is needed."
                ),
            )
        )
    return findings


def evaluate_publication_readiness(
    evidence: Mapping[str, Any],
    *,
    project_id: str | None = None,
    figure_id: str | None = None,
    required_evidence: Sequence[str] = (),
    required_diagnostic_ids: Sequence[str] = (),
    policy_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Evaluate evidence into one of three automatic readiness states.

    ``required_evidence`` is supplied by an integration adapter because the
    evidence required for a CSV render and a project render can differ.
    """

    normalized = _canonical_value(evidence)
    if not isinstance(normalized, dict):
        raise TypeError("readiness evidence must be an object")
    findings: list[ReadinessFinding] = []
    validated_v2: dict[str, Any] | None = None
    if normalized.get("version") == "2.0":
        try:
            validated_v2 = normalize_evidence_envelope(normalized)
        except EvidenceContractError:
            validated_v2 = None
    findings.extend(_v2_consistency_findings(normalized))
    findings.extend(_integrity_findings(normalized))
    findings.extend(_reproducibility_findings(normalized))
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
    if not isinstance(geometry, dict) and validated_v2 is not None:
        geometry = {
            "schema_version": "geometry_diagnostics/2",
            "measurements": validated_v2.get("measurements", []),
            "warnings": [],
        }
    geometry_measurements: dict[str, Mapping[str, Any]] = {}
    if isinstance(geometry, dict):
        geometry_findings, geometry_measurements = _geometry_findings(
            geometry,
            required_diagnostic_ids=required_diagnostic_ids,
            finding=_finding,
        )
        findings.extend(geometry_findings)
    requested_policies = tuple(
        policy_id for policy_id in (policy_ids or ()) if isinstance(policy_id, str) and policy_id.strip()
    )
    applied_policies: list[str]
    if validated_v2 is not None:
        projection_findings, applied_policies = _policy_projection_findings(
            validated_v2,
            geometry_measurements,
            policy_ids=requested_policies,
            finding=_finding,
        )
        findings.extend(projection_findings)
    else:
        applied_policies = []
        if requested_policies:
            findings.append(
                _finding(
                    code="POLICY_SELECTION_UNVALIDATED",
                    severity="hard",
                    source="policy_projection",
                    message="Requested policies lack a validated v2 projection and resolved_policy snapshot.",
                    evidence_ref="policy_ids",
                    action="Supply a valid v2 envelope with matching policy projection and resolved_policy.",
                )
            )
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
        | ({"geometry_diagnostics"} if isinstance(geometry, dict) else set())
        | ({"policy_projection"} if applied_policies else set())
        | {
            source
            for source in (
                "geometry_diagnostics",
                "calculation_checks",
                "visual_preflight_status",
                "layout_report",
                "data_contract",
                "artifact_integrity",
                "provenance",
                "raw_integrity",
                "canonical_docs",
                "evidence_contract",
                "exact_reproducibility",
                "policy_projection",
                "visual_comparison",
            )
            if source in normalized or any(item.source == source for item in findings)
        }
    )
    gates = []
    for source in sources:
        related = [item for item in findings if item.source == source]
        outcome = (
            "blocked"
            if any(item.severity == "hard" for item in related)
            else "needs_revision"
            if any(item.severity == "major" for item in related)
            else "passed"
        )
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
        "applied_policies": applied_policies,
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
