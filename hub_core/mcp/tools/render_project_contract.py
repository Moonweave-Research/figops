"""Result-contract construction for project render responses.

The render-project façade owns orchestration and authorization.  This module
owns only the path-safe projection of runtime and durable-result state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def project_render_result_contract(mixin: Any, **kwargs: Any) -> dict[str, Any]:
    return build_project_render_result_contract(
        **kwargs,
        public_runtime_path=mixin._public_runtime_path,
        file_sha256=mixin._file_sha256,
    )


def build_project_render_result_contract(
    *,
    job_root: Path,
    snapshot_project_path: Path,
    output_path: Path,
    output_relpath: str,
    promotion_eligible: bool,
    public_runtime_path: Callable[[Path], str],
    file_sha256: Callable[[Path], str],
    promoted: Any = None,
    workflow_intent: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Describe runtime output and durable-result state without host paths.

    ``output_path`` is represented by a runtime URI.  The project-relative
    path remains a non-authoritative label so consumers cannot mistake a
    disposable snapshot for the durable project result.
    """

    del snapshot_project_path  # retained in the façade call contract for compatibility
    try:
        project_relative_path = Path(output_relpath).as_posix()
        runtime_relative_path = output_path.absolute().relative_to(job_root.absolute()).as_posix()
    except (OSError, ValueError):
        project_relative_path = str(output_relpath).replace("\\", "/")
        runtime_relative_path = ""

    runtime_uri = public_runtime_path(output_path)
    artifact_exists = output_path.is_file()
    artifact_sha256: str | None = None
    if artifact_exists:
        try:
            artifact_sha256 = file_sha256(output_path)
        except OSError:
            artifact_exists = False
    runtime_artifact = {
        "status": "created" if artifact_exists else "unavailable",
        "uri": runtime_uri or None,
        "relative_path": runtime_relative_path or f"project/{project_relative_path}",
        "project_relative_path": project_relative_path,
        "sha256": artifact_sha256,
        "source": "runtime_snapshot",
    }

    durable_status = "promoted" if promoted is not None else "not_promoted"
    if durable_status == "promoted":
        durable_reason_code = None
        durable_reason = None
    elif dry_run:
        durable_reason_code = "DRY_RUN"
        durable_reason = "Dry-run validation creates no runtime bytes or durable project result."
    elif isinstance(workflow_intent, dict) and workflow_intent.get("intent") == "exploration":
        durable_reason_code = "EXPLORATION_NON_PROMOTABLE"
        durable_reason = "Exploration renders remain runtime-only and are never promotable."
    elif promotion_eligible:
        durable_reason_code = "PROMOTION_NOT_PERFORMED"
        durable_reason = "The result passed eligibility but no durable promotion was performed."
    else:
        durable_reason_code = "PROMOTION_NOT_ELIGIBLE"
        durable_reason = "Promotion eligibility was not satisfied; the durable project result was unchanged."

    durable_result = {
        "status": durable_status,
        "relative_path": project_relative_path if durable_status == "promoted" else None,
        "reason_code": durable_reason_code,
        "reason": durable_reason,
        "source": "durable_project_result",
    }
    return {
        "runtime_artifact": runtime_artifact,
        "durable_result": durable_result,
        "promotion_status": durable_status,
        "promotion_reason": durable_reason,
        "source_unchanged": True,
        "overwrite_scope": "job_workspace_only",
    }
