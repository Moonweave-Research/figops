"""Explicitly write-gated human-review receipt recording."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from hub_core.human_review_receipt import (
    canonical_human_review_receipt_bytes,
    opaque_figure_artifact_id,
    opaque_project_id,
    validate_human_review_receipt,
)
from hub_core.project_structure_contract import resolve_project_structure
from hub_core.review_recording import record_human_review_receipt

from .project_tools import _self_described_authority_keys


class McpReviewToolsMixin:
    """MCP review recording handlers.

    Validation is deliberately performed before any destination is created.
    The receipt itself is evidence, not a host authority; reviewer authority
    is verified later by the pure promotion gate using a configured policy.
    """

    def record_human_review(self, arguments: dict[str, Any]) -> dict[str, Any]:
        guarded = self._authorize_write_tool("figops.record_human_review", arguments)
        if guarded is not None:
            return guarded
        if getattr(self, "require_host_approval", False):
            # The existing host authority root is scoped to reviewed project
            # structure plans.  Do not reinterpret a self-described human
            # review receipt as that authority or silently widen its scope.
            raise ValueError(
                "Host approval is required for this MCP server; review recording has no host-authority binding."
            )
        # The receipt is a closed evidence DTO and therefore legitimately
        # contains reviewer/authority_assertion fields.  Those fields are not
        # a host trust channel; scan every other argument for forged authority
        # payloads before resolving a project or creating its evidence root.
        authority_scan = {key: value for key, value in arguments.items() if key != "review_receipt"}
        forbidden = _self_described_authority_keys(authority_scan)
        if forbidden:
            raise ValueError(
                "Tool arguments may not self-describe host approval or authority: "
                + ", ".join(forbidden)
                + "."
            )
        project_path = self._resolve_execution_project_path(arguments.get("project_path"))
        figure_id = arguments.get("figure_id")
        if not isinstance(figure_id, str) or not figure_id.strip():
            raise ValueError("figure_id is required.")
        review_receipt = arguments.get("review_receipt")
        if not isinstance(review_receipt, Mapping):
            raise ValueError("review_receipt must be a canonical human-review receipt object.")
        receipt = validate_human_review_receipt(review_receipt)
        loaded = self._load_project_config(project_path)
        config = loaded.get("config")
        if not isinstance(config, Mapping):
            raise ValueError("project configuration is required before recording a human review.")
        if loaded.get("errors"):
            raise ValueError("project configuration is invalid: " + "; ".join(map(str, loaded["errors"])))
        # Resolve the caller's selector against the trusted project config
        # before deriving any artifact identity or touching the evidence
        # root.  A receipt cannot make an unconfigured (or ambiguous)
        # figure ID valid merely by self-describing its subject.
        figures = self._project_figure_entries(dict(config))
        selected_figure, selection_errors = self._select_project_figure(
            figures,
            figure_id=figure_id,
            figure_output=None,
        )
        if selected_figure is None or selection_errors:
            detail = "; ".join(selection_errors) if selection_errors else "figure_id was not resolved."
            raise ValueError("figure_id must resolve to exactly one trusted configured figure: " + detail)
        contract = resolve_project_structure(config, project_root=project_path)
        subject = receipt.get("subject")
        if not isinstance(subject, Mapping):
            raise ValueError("review_receipt.subject is required.")
        project_name = config.get("project", {}).get("name") if isinstance(config.get("project"), Mapping) else None
        if not isinstance(project_name, str) or not project_name.strip():
            raise ValueError("trusted project.name is required for review recording.")
        expected_project_id = opaque_project_id(project_name)
        expected_artifact_id = opaque_figure_artifact_id(figure_id)
        if subject.get("project_id") != expected_project_id:
            raise ValueError("review subject does not bind the trusted project identity.")
        if subject.get("artifact_id") != expected_artifact_id:
            raise ValueError("review subject does not bind the selected figure identity.")
        expected_subject = arguments.get("expected_subject")
        if expected_subject is not None:
            if not isinstance(expected_subject, Mapping):
                raise ValueError("expected_subject must be a mapping.")
            if dict(expected_subject) != dict(subject):
                raise ValueError("review subject does not match the trusted expected subject.")

        relative = arguments.get("relative_path")
        if not isinstance(relative, str) or not relative:
            raise ValueError("relative_path is required.")
        evidence_root = Path(project_path) / str(contract.roots["evidence"])
        relative_path = PurePosixPath(relative)
        evidence_role = PurePosixPath(str(contract.roots["evidence"]))
        if relative_path.is_absolute() or ".." in relative_path.parts or "\\" in relative:
            raise ValueError("relative_path must stay below the declared evidence role.")
        # ``record_human_review_receipt`` receives a path relative to its
        # evidence root, so an MCP caller cannot redirect into figures or
        # publication by spelling a project-relative path.
        if relative_path.as_posix() != relative:
            raise ValueError("relative_path must use canonical POSIX separators.")
        canonical_bytes = canonical_human_review_receipt_bytes(receipt)
        result = record_human_review_receipt(
            receipt,
            evidence_root=evidence_root,
            relative_path=relative_path.as_posix(),
            write_authorized=True,
        )
        return self._envelope(
            "figops.record_human_review",
            arguments,
            summary="Recorded one append-only human-review receipt.",
            created_paths=[str(evidence_role / relative_path)],
            is_dry_run=False,
            project_path=str(project_path),
            relative_path=result.relative_path,
            receipt_id=result.receipt_id,
            canonical_sha256=result.canonical_sha256,
            size_bytes=len(canonical_bytes),
            review_receipt=receipt,
        )


__all__ = ["McpReviewToolsMixin"]
