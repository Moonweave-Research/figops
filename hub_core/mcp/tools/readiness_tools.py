from __future__ import annotations

import re
from typing import Any

from hub_core.publication_evidence import load_readiness_manifest
from hub_core.publication_readiness import evaluate_publication_readiness


class McpReadinessToolsMixin:
    """Read-only publication-readiness evaluation for existing render jobs."""

    def evaluate_publication_readiness(self, arguments: dict[str, Any]) -> dict[str, Any]:
        job_id = str(arguments["job_id"])
        if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_id) is None:
            raise ValueError("job_id must contain 1-80 ASCII letters, digits, underscores, or hyphens.")
        manifest_path = self._find_job_manifest_path(job_id)
        if not manifest_path.is_file():
            raise FileNotFoundError(f"No render manifest exists for job_id {job_id!r}.")

        evidence = load_readiness_manifest(manifest_path)
        report = evaluate_publication_readiness(
            evidence,
            project_id=evidence.get("project_id"),
            figure_id=evidence.get("figure_id"),
            required_evidence=("geometry_diagnostics", "visual_preflight_status", "layout_report"),
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
