"""Read-only completed-job audit adapter for v2 evidence."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from hub_core.artifact_audit import audit_artifact_evidence
from hub_core.evidence_contract import normalize_evidence_envelope
from hub_core.mcp.manifest_io import read_verified_runtime_json_object
from hub_core.mcp.render_response import audit_response

_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


class McpAuditToolsMixin:
    """Audit persisted immutable evidence with caller-selected policy packs."""

    def audit_artifact(self, arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = str(arguments.get("job_id") or "")
        if _JOB_ID.fullmatch(job_id) is None:
            raise ValueError("job_id must contain 1-80 ASCII letters, digits, underscores, or hyphens")
        manifest = self._read_unique_audit_manifest(job_id)
        if manifest.get("job_id") != job_id:
            raise ValueError("Render manifest job_id does not match the requested completed job")
        raw_evidence = manifest.get("evidence")
        if isinstance(raw_evidence, Mapping):
            evidence = normalize_evidence_envelope(raw_evidence)
        else:
            evidence = normalize_evidence_envelope(manifest, allow_legacy=True)
        policies = arguments.get("policy_packs", [])
        report = audit_artifact_evidence(
            evidence,
            policy_packs=policies,
            project_id=manifest.get("project_id") if isinstance(manifest.get("project_id"), str) else None,
            figure_id=self._manifest_figure_id(manifest),
        )
        previews = manifest.get("preview_artifacts")
        preview_entries = [item for item in previews if isinstance(item, Mapping)] if isinstance(previews, list) else []
        return audit_response(
            job_id=job_id,
            evidence=evidence,
            report=report,
            preview_entries=preview_entries,
        )

    def _read_unique_audit_manifest(self, job_id: str) -> dict[str, Any]:
        selection = self._resolve_job_manifest(job_id)
        return read_verified_runtime_json_object(
            selection.root,
            selection.path,
            expected_job_id=job_id,
        )

    @staticmethod
    def _manifest_figure_id(manifest: Mapping[str, Any]) -> str | None:
        value = manifest.get("figure_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
        selected = manifest.get("selected_figure")
        value = selected.get("id") if isinstance(selected, Mapping) else None
        return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = ["McpAuditToolsMixin"]
