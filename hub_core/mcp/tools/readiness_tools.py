from __future__ import annotations

import re
from typing import Any

from hub_core.publication_evidence import readiness_evidence_from_verified_manifest
from hub_core.publication_readiness import RENDER_JOB_REQUIRED_EVIDENCE, evaluate_publication_readiness


class McpReadinessToolsMixin:
    """Read-only publication-readiness evaluation for existing render jobs."""

    def evaluate_publication_readiness(self, arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = str(arguments["job_id"])
        if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id) is None:
            raise ValueError("job_id must contain 1-80 ASCII letters, digits, underscores, or hyphens.")
        selection = self._resolve_job_manifest(job_id)
        manifest = self._read_verified_job_manifest(job_id, selection)
        evidence = readiness_evidence_from_verified_manifest(manifest, selection.path)
        report = evaluate_publication_readiness(
            evidence,
            project_id=evidence.get("project_id"),
            figure_id=evidence.get("figure_id"),
            required_evidence=RENDER_JOB_REQUIRED_EVIDENCE,
        )
        readiness_status = report["readiness_status"]
        status = (
            "error"
            if readiness_status == "blocked"
            else "warning"
            if readiness_status == "needs_revision"
            else "ok"
        )
        return self._envelope(
            "figops.evaluate_publication_readiness",
            arguments,
            status=status,
            summary=f"Publication readiness evaluation completed with status {readiness_status}.",
            manual_review_needed=True,
            readiness_report=report,
        )
