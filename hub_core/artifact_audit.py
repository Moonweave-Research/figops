"""Policy-explicit synthesis over a validated FigOps evidence envelope.

The audit kernel is intentionally narrower than publication readiness.  It
always evaluates immutable integrity facts, while geometry, presentation, and
other readiness judgments are evaluated only when the caller selects a closed
policy pack.  Automatic audit results always require human review.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal

from .evidence_contract import EvidenceContractError, normalize_evidence_envelope
from .publication_evidence import _sanitize_path_text
from .publication_readiness import evaluate_publication_readiness, evidence_digest
from .redaction import redact_secrets, redact_text

SCHEMA_VERSION: Final = "artifact_audit/1"
PUBLICATION_READINESS_POLICY: Final = "publication-readiness-v1"
SUPPORTED_POLICY_PACKS: Final = frozenset({PUBLICATION_READINESS_POLICY})
POLICY_PROJECTION_IDS: Final = {PUBLICATION_READINESS_POLICY: ("publication-readiness-v2",)}
MAX_AUDIT_OUTPUT_BYTES: Final = 64 * 1024

AuditStatus = Literal["blocked", "needs_revision", "needs_review"]
_SEVERITY_ORDER: Final = {"hard": 0, "major": 1, "info": 2}
_MAX_FINDINGS_RETURNED: Final = 48
_MAX_GATE_DETAILS: Final = 24
_MAX_TEXT_LENGTH: Final = 512


def audit_artifact_evidence(
    evidence: Mapping[str, Any],
    *,
    policy_packs: Sequence[str] = (),
    project_id: str | None = None,
    figure_id: str | None = None,
) -> dict[str, Any]:
    """Audit one already-loaded evidence envelope.

    Unknown, malformed, or duplicate policy identifiers are rejected rather
    than ignored.  Evidence-contract failures are returned as typed hard
    findings so callers can explain why the completed job cannot be trusted.
    No path loading or artifact-byte access occurs in this layer.
    """

    selected = _selected_policy_packs(policy_packs)
    findings: list[dict[str, Any]] = []
    normalized: dict[str, Any] | None = None
    try:
        normalized = normalize_evidence_envelope(evidence)
    except EvidenceContractError as exc:
        findings.append(
            _finding(
                code=f"EVIDENCE_CONTRACT_{exc.code}",
                severity="hard",
                source="evidence_contract",
                message=exc.message,
                evidence_ref=exc.path,
                action="Regenerate a valid figops_evidence/2 envelope.",
            )
        )

    if normalized is not None:
        findings.extend(_kernel_findings(normalized))
        if PUBLICATION_READINESS_POLICY in selected:
            findings.extend(
                _publication_policy_findings(
                    normalized,
                    project_id=project_id,
                    figure_id=figure_id,
                )
            )

    all_findings = _deduplicated_findings(findings)
    status = _status(all_findings)
    gates = _gate_evidence(all_findings, selected, contract_valid=normalized is not None)
    returned_findings = all_findings[:_MAX_FINDINGS_RETURNED]
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "manual_review_required": True,
        "selected_policy_ids": list(selected),
        "evidence_digest": evidence_digest(normalized) if normalized is not None else None,
        "summary": _summary(all_findings, returned_findings, gates),
        "gates": gates,
        "findings": returned_findings,
    }
    return _bounded_report(report)


def _selected_policy_packs(policy_packs: Sequence[str]) -> tuple[str, ...]:
    if isinstance(policy_packs, (str, bytes)) or not isinstance(policy_packs, Sequence):
        raise ValueError("policy_packs must be an array of explicit policy identifiers")
    selected: list[str] = []
    for index, value in enumerate(policy_packs):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"policy_packs[{index}] must be a non-empty policy identifier")
        policy_id = value.strip()
        if policy_id not in SUPPORTED_POLICY_PACKS:
            raise ValueError(f"unsupported artifact audit policy pack: {policy_id}")
        if policy_id in selected:
            raise ValueError(f"duplicate artifact audit policy pack: {policy_id}")
        selected.append(policy_id)
    return tuple(selected)


def _kernel_findings(evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    producer = evidence["producer"]
    producer_status = producer["status"]
    if producer_status in {"failed", "skipped"}:
        stage = producer.get("failure_stage")
        findings.append(
            _finding(
                code="PRODUCER_FAILED" if producer_status == "failed" else "PRODUCER_SKIPPED",
                severity="hard",
                source="producer",
                message=(
                    f"The evidence producer failed at stage {stage}."
                    if stage
                    else "The evidence producer did not complete the artifact job."
                ),
                evidence_ref="producer",
                action="Resolve the producer failure and regenerate the artifact evidence.",
            )
        )
    elif producer_status == "warning":
        findings.append(
            _finding(
                code="PRODUCER_WARNING",
                severity="major",
                source="producer",
                message=str(producer.get("reason") or "The evidence producer reported a warning."),
                evidence_ref="producer.status",
                action="Review the producer warning before relying on the artifact.",
            )
        )

    artifacts = evidence["artifacts"]
    artifact_status = artifacts["status"]
    if artifact_status in {"failed", "skipped", "unavailable"}:
        findings.append(
            _finding(
                code="ARTIFACT_INTEGRITY_UNAVAILABLE" if artifact_status != "failed" else "ARTIFACT_INTEGRITY_FAILED",
                severity="hard",
                source="artifact_integrity",
                message=str(artifacts.get("reason") or "Verified artifact evidence is unavailable."),
                evidence_ref="artifacts",
                action="Regenerate and verify the declared primary artifact.",
            )
        )
    elif artifact_status == "warning":
        findings.append(
            _finding(
                code="ARTIFACT_INTEGRITY_WARNING",
                severity="major",
                source="artifact_integrity",
                message=str(artifacts.get("reason") or "Artifact verification completed with a warning."),
                evidence_ref="artifacts.status",
                action="Resolve the artifact warning and verify the replacement bytes.",
            )
        )
    for index, entry in enumerate(artifacts.get("entries", [])):
        if isinstance(entry, Mapping) and entry.get("dimension_availability", "available") != "available":
            findings.append(
                _finding(
                    code="ARTIFACT_PIXEL_DIMENSIONS_UNAVAILABLE",
                    severity="info",
                    source="artifact_integrity",
                    message=str(entry.get("dimension_reason") or "Pixel dimensions are unavailable."),
                    evidence_ref=f"artifacts.entries[{index}].dimension_availability",
                    action="Use the bounded preview resource for visual review; do not infer source pixel dimensions.",
                )
            )

    provenance = evidence["provenance"]
    provenance_status = provenance["status"]
    if provenance_status in {"failed", "skipped", "unavailable"}:
        findings.append(
            _finding(
                code="PROVENANCE_INCOMPLETE",
                severity="hard",
                source="provenance",
                message=str(provenance.get("reason") or "Required provenance evidence is unavailable."),
                evidence_ref="provenance",
                action="Record the required input, config, script, environment, and output hashes.",
            )
        )
    elif provenance_status == "warning":
        findings.append(
            _finding(
                code="PROVENANCE_WARNING",
                severity="major",
                source="provenance",
                message=str(provenance.get("reason") or "Provenance collection reported a warning."),
                evidence_ref="provenance.status",
                action="Review and reconcile the provenance warning.",
            )
        )

    findings.extend(
        _immutable_summary_findings(
            evidence["data_contract_summary"],
            source="raw_integrity",
            hard_code="RAW_OR_DATA_INTEGRITY_FAILED",
            warning_code="RAW_OR_DATA_INTEGRITY_WARNING",
        )
    )
    findings.extend(
        _immutable_summary_findings(
            evidence["calculation_summary"],
            source="claim_linkage",
            hard_code="UNSUPPORTED_CLAIM_OR_CALCULATION_FAILED",
            warning_code="CLAIM_OR_CALCULATION_WARNING",
        )
    )
    return findings


def _immutable_summary_findings(
    summary: Mapping[str, Any],
    *,
    source: str,
    hard_code: str,
    warning_code: str,
) -> list[dict[str, Any]]:
    """Fail closed from every detail record in a closed producer summary."""

    findings: list[dict[str, Any]] = []
    summary_field = "data_contract_summary" if source == "raw_integrity" else "calculation_summary"
    for index, check in enumerate(summary["checks"]):
        status = check["status"]
        if status not in {"failed", "warning"}:
            continue
        findings.append(
            _finding(
                code=hard_code if status == "failed" else warning_code,
                severity="hard" if status == "failed" else "major",
                source=source,
                message=str(check["message"]),
                evidence_ref=f"{summary_field}.checks[{index}]",
                action=(
                    "Seal or reconcile the declared raw inputs."
                    if source == "raw_integrity"
                    else "Remove the unsupported claim or attach verified calculation evidence."
                ),
            )
        )
    return findings


def _publication_policy_findings(
    evidence: Mapping[str, Any],
    *,
    project_id: str | None,
    figure_id: str | None,
) -> list[dict[str, Any]]:
    """Delegate the selected readiness pack to the existing evaluator."""

    report = evaluate_publication_readiness(
        evidence,
        project_id=project_id,
        figure_id=figure_id,
        policy_ids=POLICY_PROJECTION_IDS[PUBLICATION_READINESS_POLICY],
    )
    findings = [dict(item) for item in report.get("findings", []) if isinstance(item, Mapping)]

    # Native v2 summaries are deliberately policy-neutral in the envelope.
    # When readiness is explicitly selected, project their detailed statuses
    # without trusting their aggregate fields.
    for field in ("data_contract_summary", "calculation_summary"):
        for index, check in enumerate(evidence[field]["checks"]):
            if check["status"] not in {"failed", "warning"}:
                continue
            findings.append(
                _finding(
                    code=f"{field.upper()}_{check['status'].upper()}",
                    severity="hard" if check["status"] == "failed" else "major",
                    source=field,
                    message=str(check["message"]),
                    evidence_ref=f"{field}.checks[{index}]",
                    action="Resolve the selected readiness check and regenerate its evidence.",
                    policy_id=PUBLICATION_READINESS_POLICY,
                )
            )
    for finding in findings:
        finding.setdefault("policy_id", PUBLICATION_READINESS_POLICY)
    return findings


def _finding(
    *,
    code: str,
    severity: str,
    source: str,
    message: str,
    evidence_ref: str,
    action: str,
    policy_id: str | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "source": source,
        "message": message,
        "evidence_ref": evidence_ref,
        "recommended_action": action,
        "policy_id": policy_id,
    }


def _deduplicated_findings(findings: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in findings:
        finding = _normalized_finding(item)
        key = (
            str(finding.get("code")),
            str(finding.get("source")),
            str(finding.get("evidence_ref")),
            str(finding.get("policy_id")),
        )
        unique.setdefault(key, finding)
    return sorted(
        unique.values(),
        key=lambda item: (
            _SEVERITY_ORDER.get(str(item.get("severity")), 3),
            str(item.get("source")),
            str(item.get("code")),
            str(item.get("evidence_ref")),
        ),
    )


def _normalized_finding(item: Mapping[str, Any]) -> dict[str, Any]:
    """Allowlist and sanitize one finding before it crosses the audit boundary."""

    finding = {
        "code": _public_text(item.get("code")),
        "severity": str(item.get("severity")) if item.get("severity") in _SEVERITY_ORDER else "hard",
        "source": _public_text(item.get("source")),
        "message": _public_text(item.get("message")),
        "evidence_ref": _public_text(item.get("evidence_ref")),
        "recommended_action": _public_text(item.get("recommended_action")),
        "policy_id": _public_text(item.get("policy_id")) if item.get("policy_id") is not None else None,
    }
    if isinstance(item.get("affected_panel"), int) and not isinstance(item.get("affected_panel"), bool):
        finding["affected_panel"] = item["affected_panel"]
    if item.get("rubric_id") is not None:
        finding["rubric_id"] = _public_text(item.get("rubric_id"))
    if isinstance(item.get("waivable"), bool):
        finding["waivable"] = item["waivable"]
    return finding


def _public_text(value: Any) -> str:
    redacted = redact_text(str(value or ""))
    sanitized = _sanitize_path_text(redacted).replace("\x00", "")
    if len(sanitized) <= _MAX_TEXT_LENGTH:
        return sanitized
    return sanitized[: _MAX_TEXT_LENGTH - 12] + " [truncated]"


def _status(findings: Sequence[Mapping[str, Any]]) -> AuditStatus:
    severities = {item.get("severity") for item in findings}
    if "hard" in severities:
        return "blocked"
    if "major" in severities:
        return "needs_revision"
    return "needs_review"


def _gate_evidence(
    findings: Sequence[Mapping[str, Any]],
    selected: Sequence[str],
    *,
    contract_valid: bool,
) -> list[dict[str, Any]]:
    sources_by_gate = {
        "evidence_contract": ({"evidence_contract"}, "version"),
        "producer": ({"producer"}, "producer"),
        "artifact_integrity": ({"artifact_integrity"}, "artifacts"),
        "provenance": ({"provenance"}, "provenance"),
        "raw_integrity": ({"raw_integrity"}, "data_contract_summary.checks"),
        "claim_linkage": ({"claim_linkage"}, "calculation_summary.checks"),
    }
    gates: list[dict[str, Any]] = []
    for gate_id, (sources, default_ref) in sources_by_gate.items():
        related = [item for item in findings if item.get("source") in sources and item.get("policy_id") is None]
        codes = [str(item.get("code")) for item in related]
        refs = sorted({str(item.get("evidence_ref")) for item in related}) or [default_ref]
        gates.append(
            {
                "id": gate_id,
                "status": _status(related),
                "available": contract_valid if gate_id != "evidence_contract" else True,
                "finding_codes": codes[:_MAX_GATE_DETAILS],
                "evidence_refs": refs[:_MAX_GATE_DETAILS],
                "detail_count": len(related),
                "details_truncated": len(codes) > _MAX_GATE_DETAILS or len(refs) > _MAX_GATE_DETAILS,
            }
        )
    for policy_id in selected:
        related = [item for item in findings if item.get("policy_id") == policy_id]
        codes = [str(item.get("code")) for item in related]
        refs = sorted({str(item.get("evidence_ref")) for item in related})
        gates.append(
            {
                "id": policy_id,
                "status": _status(related),
                "available": contract_valid,
                "finding_codes": codes[:_MAX_GATE_DETAILS],
                "evidence_refs": refs[:_MAX_GATE_DETAILS],
                "detail_count": len(related),
                "details_truncated": len(codes) > _MAX_GATE_DETAILS or len(refs) > _MAX_GATE_DETAILS,
            }
        )
    return gates


def _summary(
    findings: Sequence[Mapping[str, Any]],
    returned_findings: Sequence[Mapping[str, Any]],
    gates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    omitted = len(findings) - len(returned_findings)
    return {
        "status": _status(findings),
        "finding_counts": {
            severity: sum(item.get("severity") == severity for item in findings)
            for severity in ("hard", "major", "info")
        },
        "gate_counts": {
            status: sum(item.get("status") == status for item in gates)
            for status in ("blocked", "needs_revision", "needs_review")
        },
        "finding_count": len(findings),
        "findings_returned": len(returned_findings),
        "findings_omitted": omitted,
        "findings_truncated": omitted > 0,
    }


def _bounded_report(report: dict[str, Any]) -> dict[str, Any]:
    """Redact recursively and guarantee the serialized audit stays within 64 KiB."""

    redacted = redact_secrets(report)
    if not isinstance(redacted, dict):
        raise RuntimeError("artifact audit output must remain an object")
    redacted["summary"]["serialized_bytes"] = 0
    for _ in range(10_000):
        size = _serialized_size(redacted)
        if size <= MAX_AUDIT_OUTPUT_BYTES and redacted["summary"]["serialized_bytes"] == size:
            return redacted
        redacted["summary"]["serialized_bytes"] = size
        if _serialized_size(redacted) <= MAX_AUDIT_OUTPUT_BYTES:
            continue
        if not _trim_one_output_detail(redacted):
            raise RuntimeError("bounded artifact audit output exceeds the 64 KiB contract")
    raise RuntimeError("bounded artifact audit output did not converge")


def _trim_one_output_detail(report: dict[str, Any]) -> bool:
    if report["findings"]:
        report["findings"].pop()
        returned = len(report["findings"])
        total = int(report["summary"]["finding_count"])
        report["summary"]["findings_returned"] = returned
        report["summary"]["findings_omitted"] = total - returned
        report["summary"]["findings_truncated"] = True
        return True
    for gate in reversed(report["gates"]):
        refs = gate.get("evidence_refs")
        codes = gate.get("finding_codes")
        target = refs if isinstance(refs, list) and refs else codes
        if isinstance(target, list) and target:
            target.pop()
            gate["details_truncated"] = True
            return True
    return False


def _serialized_size(value: Mapping[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
