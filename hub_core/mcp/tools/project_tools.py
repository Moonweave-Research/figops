from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hub_core.approval_authority import verify_approval_authority
from hub_core.project_normalization import (
    NORMALIZATION_CONFIRMATION_REQUIRED,
    NORMALIZATION_HOST_APPROVAL_REJECTED,
    NORMALIZATION_HOST_APPROVAL_REQUIRED,
    NORMALIZATION_OVERWRITE_DISABLED,
    NORMALIZATION_PLAN_REJECTED,
    NORMALIZATION_POLICY_DEPRECATED,
    NORMALIZATION_REVIEW_REQUIRED,
    apply_normalize_project,
    apply_scaffold_project,
    plan_normalize_project,
    plan_scaffold_project,
)
from hub_core.structure_plan import confirmation_token as structure_confirmation_token


class _HostApprovalRejected(PermissionError):
    """Raised when mutation-boundary host approval revalidation fails."""


_HOST_AUTHORITY_ARGUMENT_KEYS = frozenset(
    {
        "approval",
        "approval_json",
        "approval_payload",
        "approval_record",
        "approval_receipt",
        "approval_receipt_id",
        "approval_status",
        "algorithm",
        "attestation",
        "approved",
        "authority",
        "authority_index",
        "authority_root",
        "authorization",
        "capability",
        "capability_handle",
        "currentness",
        "host_approval",
        "host_approval_receipt",
        "host_authority",
        "host_authorization",
        "key_id",
        "receipt",
        "receipt_id",
        "reviewer",
        "review_record",
        "reviewer_identity",
        "reviewer_role",
        "revocation",
        "revocation_epoch",
        "trust",
        "trusted",
        "signature",
        "trust_root",
        "trust_root_id",
    }
)


def _self_described_authority_keys(arguments: dict[str, Any]) -> list[str]:
    """Find authority-looking fields at every depth of a tool request.

    Host approval is deliberately an out-of-band trust channel.  The one
    exception is the opaque, top-level ``approval_receipt_id`` consumed by the
    host authority root.  Every other authority-looking field is rejected,
    including fields hidden in a mapping/list payload such as
    ``approved_mappings[0].reviewer`` or ``manifest.trust_root``.
    """

    def canonical_key(key: object) -> str:
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key).strip()).replace("-", "_").casefold()

    # Catch compound names such as ``approval_token`` and ``trusted_by`` in
    # addition to the explicit compatibility list above, while keeping normal
    # request fields such as ``approved_mappings`` valid.
    authority_components = frozenset(
        {
            "approval",
            "approved",
            "authority",
            "authorization",
            "authorize",
            "receipt",
            "review",
            "reviewer",
            "signature",
            "signed",
            "trust",
            "trusted",
        }
    )

    def is_authority_key(key: object) -> bool:
        canonical = canonical_key(key)
        if canonical in _HOST_AUTHORITY_ARGUMENT_KEYS:
            return True
        return bool(authority_components.intersection(canonical.split("_")))

    def format_path(path: tuple[object, ...]) -> str:
        rendered = ""
        for part in path:
            if isinstance(part, int):
                rendered += f"[{part}]"
            else:
                rendered = f"{rendered}.{part}" if rendered else str(part)
        return rendered

    findings: set[str] = set()

    def visit(value: object, path: tuple[object, ...] = ()) -> None:
        if isinstance(value, Mapping):
            for raw_key, nested in value.items():
                key = str(raw_key)
                key_path = path + (key,)
                canonical = canonical_key(raw_key)
                # Only this exact semantic field at the request root is
                # allowed.  Its value must remain opaque; if a caller embeds a
                # mapping/list below it, recurse so forged nested fields still
                # fail closed.
                if not path and canonical == "approval_receipt_id":
                    if not isinstance(nested, str):
                        findings.add(format_path(key_path))
                    visit(nested, key_path)
                    continue
                # ``approved_mappings`` is the one ordinary request field
                # whose name contains an authority word; only its top-level
                # collection is part of the public normalization contract.
                if not (not path and canonical == "approved_mappings") and is_authority_key(raw_key):
                    findings.add(format_path(key_path))
                visit(nested, key_path)
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                visit(nested, path + (index,))

    visit(arguments)
    return sorted(findings, key=str.casefold)


class McpProjectToolsMixin:
    """Project scaffold and normalization MCP tool handlers."""

    def scaffold_project(self, arguments: dict[str, Any]) -> dict[str, Any]:
        guarded = self._authorize_write_tool("figops.scaffold_project", arguments)
        if guarded is not None:
            return guarded
        project_name = self._required_string(arguments, "project_name")
        project_root = self._resolve_under_root(arguments.get("project_root"), field_name="project_root")
        target_format = str(arguments.get("target_format") or "nature").strip().lower()
        template = str(arguments.get("template") or "standard").strip().lower()
        dry_run = bool(arguments.get("dry_run", True))
        overwrite = bool(arguments.get("overwrite", False))
        manifest = plan_scaffold_project(
            project_root=project_root,
            hub_path=self.hub_path,
            project_name=project_name,
            target_format=target_format,
            template=template,
        )
        public_manifest = self._public_manifest(manifest)
        planned_paths = self._manifest_destinations(public_manifest)
        config_path = Path(str(manifest["project_root"])) / "project_config.yaml"
        style_summary = self._manifest_style_summary(manifest)
        validation = self._validation_summary(config_path)
        scaffold_manifest_path = str(Path(str(manifest["project_root"])) / ".figops_scaffold_manifest.json")
        if dry_run:
            return self._envelope(
                "figops.scaffold_project",
                arguments,
                summary=f"Planned scaffold for project {project_name}.",
                is_dry_run=True,
                project_root=str(manifest["project_root"]),
                project_name=project_name,
                planned_paths=planned_paths,
                manifest=public_manifest,
                manifest_path=scaffold_manifest_path,
                config_path=str(config_path),
                style_summary=style_summary,
                validation=validation,
            )
        try:
            applied = apply_scaffold_project(manifest, overwrite=overwrite)
        except FileExistsError as exc:
            return self._envelope(
                "figops.scaffold_project",
                arguments,
                status="error",
                summary="Scaffold destination already exists.",
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=False,
                project_root=str(manifest["project_root"]),
                project_name=project_name,
                planned_paths=planned_paths,
                manifest=public_manifest,
                manifest_path=scaffold_manifest_path,
                config_path=str(config_path),
                style_summary=style_summary,
                validation=validation,
            )
        validation = self._validation_summary(config_path)
        return self._envelope(
            "figops.scaffold_project",
            arguments,
            summary=f"Created scaffold for project {project_name}.",
            created_paths=applied["created_paths"],
            modified_paths=applied["modified_paths"],
            skipped_paths=applied["skipped_paths"],
            is_dry_run=False,
            project_root=str(manifest["project_root"]),
            project_name=project_name,
            planned_paths=planned_paths,
            manifest=applied["manifest"],
            manifest_path=scaffold_manifest_path,
            config_path=str(config_path),
            style_summary=style_summary,
            validation=validation,
        )

    def normalize_project_structure(self, arguments: dict[str, Any]) -> dict[str, Any]:
        guarded = self._authorize_write_tool("figops.normalize_project_structure", arguments)
        if guarded is not None:
            return guarded
        if self.require_host_approval:
            forbidden_authority_keys = _self_described_authority_keys(arguments)
            if forbidden_authority_keys:
                approval_receipt_id = arguments.get("approval_receipt_id")
                return self._envelope(
                    "figops.normalize_project_structure",
                    arguments,
                    status="error",
                    summary="Self-described approval fields are not a host authority.",
                    errors=[
                        "Tool arguments may contain only top-level opaque approval_receipt_id; "
                        "rejected authority fields: "
                        + ", ".join(forbidden_authority_keys)
                        + "."
                    ],
                    manual_review_needed=True,
                    is_dry_run=bool(arguments.get("dry_run", True)),
                    error_category="validation",
                    error_code=NORMALIZATION_HOST_APPROVAL_REJECTED,
                    approval_receipt_id=(
                        approval_receipt_id if isinstance(approval_receipt_id, str) else None
                    ),
                    host_approval_required=True,
                    approval_status="rejected",
                )
        project_path = self._resolve_under_root(arguments.get("project_path"), field_name="project_path")
        dry_run = bool(arguments.get("dry_run", True))
        move_policy = str(arguments.get("move_policy") or "adopt").strip().lower()
        include_raw = bool(arguments.get("include_raw", False))
        overwrite = bool(arguments.get("overwrite", False))
        approved_mappings = arguments.get("approved_mappings")
        config_diff = arguments.get("config_diff")
        unresolved_references = arguments.get("hardcoded_unresolved_references")

        if move_policy in {"move", "symlink"}:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Legacy normalization policy is disabled.",
                errors=[f"move_policy={move_policy!r} is deprecated and disabled; use reviewed copy-only migration."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                error_category="disabled",
                error_code=NORMALIZATION_POLICY_DEPRECATED,
                project_root=str(project_path),
            )
        if overwrite:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Normalization overwrite is disabled.",
                errors=["overwrite=true is disabled; reviewed migrations never replace existing paths."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                error_category="disabled",
                error_code=NORMALIZATION_OVERWRITE_DISABLED,
                project_root=str(project_path),
            )
        if move_policy not in {"adopt", "copy"}:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Normalization policy is invalid.",
                errors=["move_policy must be one of: adopt, copy."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                error_category="validation",
                error_code=NORMALIZATION_PLAN_REJECTED,
                project_root=str(project_path),
            )

        if approved_mappings is not None and not isinstance(approved_mappings, list):
            raise ValueError("approved_mappings must be an array of reviewed mappings.")
        if config_diff is not None and not isinstance(config_diff, list):
            raise ValueError("config_diff must be an array of typed compare-and-swap edits.")
        if unresolved_references is not None and not isinstance(unresolved_references, list):
            raise ValueError("hardcoded_unresolved_references must be an array.")

        planning_policy = move_policy
        if move_policy == "copy" and approved_mappings is None:
            planning_policy = "adopt"
        manifest = plan_normalize_project(
            project_path=project_path,
            move_policy=planning_policy,
            include_raw=include_raw,
            approved_mappings=approved_mappings,
            config_diff=config_diff,
            hardcoded_unresolved_references=unresolved_references,
        )
        public_manifest = self._public_manifest(manifest)
        proposed_mappings = list(public_manifest.get("proposed_mappings") or [])
        planned_paths = self._manifest_destinations(public_manifest)
        if not planned_paths:
            planned_paths = [str(item["destination"]) for item in proposed_mappings]
        project_root = Path(str(manifest["project_root"]))
        config_path = project_root / "project_config.yaml"
        validation = self._validation_summary(config_path)
        token = structure_confirmation_token(manifest)
        common = {
            "project_root": str(project_root),
            "planned_paths": planned_paths,
            "manifest": public_manifest,
            "manifest_path": "",
            "config_path": str(config_path),
            "style_summary": manifest["style_summary"],
            "validation": validation,
            "proposed_mappings": proposed_mappings,
            "unresolved_proposals": list(public_manifest.get("unresolved_proposals") or []),
            "plan_digest": manifest["digest"],
            "confirmation_token": token,
        }
        if self.require_host_approval:
            common.update(
                {
                    "host_approval_required": True,
                    "approval_receipt_id": (
                        arguments.get("approval_receipt_id")
                        if isinstance(arguments.get("approval_receipt_id"), str)
                        else None
                    ),
                    "approval_status": "required",
                }
            )
        if dry_run and move_policy == "adopt":
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                summary=f"Proposed normalization mappings for {project_root.name}; no mappings are approved.",
                is_dry_run=True,
                manual_review_needed=bool(proposed_mappings or common["unresolved_proposals"]),
                **common,
            )
        if move_policy == "adopt" or approved_mappings is None or (not dry_run and not approved_mappings):
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Normalization requires reviewed mappings.",
                errors=["Autodiscovery cannot be applied; submit explicit approved_mappings in copy mode."],
                manual_review_needed=True,
                is_dry_run=dry_run,
                error_category="validation",
                error_code=NORMALIZATION_REVIEW_REQUIRED,
                **common,
            )
        if dry_run:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                summary=f"Built reviewed copy-only plan for {project_root.name}.",
                is_dry_run=True,
                **common,
            )
        supplied_token = arguments.get("confirmation_token")
        if not isinstance(supplied_token, str) or not supplied_token:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Normalization confirmation is required.",
                errors=["Apply requires the confirmation_token returned for the reviewed copy-only plan."],
                manual_review_needed=True,
                is_dry_run=False,
                error_category="validation",
                error_code=NORMALIZATION_CONFIRMATION_REQUIRED,
                **common,
            )
        if self.require_host_approval:
            approval_receipt_id = arguments.get("approval_receipt_id")
            verification = verify_approval_authority(
                manifest,
                approval_receipt_id,
                self.host_authority_root,
            )
            if not verification.valid:
                reason = verification.reason.replace("_", " ")
                common["approval_status"] = "rejected"
                return self._envelope(
                    "figops.normalize_project_structure",
                    arguments,
                    status="error",
                    summary="Host approval is required before normalization apply.",
                    errors=[f"Host approval receipt was rejected: {reason}."],
                    manual_review_needed=True,
                    is_dry_run=False,
                    error_category="validation",
                    error_code=(
                        NORMALIZATION_HOST_APPROVAL_REQUIRED
                        if verification.reason
                        in {
                            "missing_or_untrusted_root",
                            "missing_trusted_root",
                            "untrusted_root",
                            "missing_or_invalid_receipt_id",
                        }
                        else NORMALIZATION_HOST_APPROVAL_REJECTED
                    ),
                    **common,
                )
            common["approval_status"] = "verified"
        pre_apply_verifier = None
        if self.require_host_approval:
            def _revalidate_host_approval(_root: Path, current_plan: dict[str, Any]) -> None:
                boundary_verification = verify_approval_authority(
                    current_plan,
                    approval_receipt_id,
                    self.host_authority_root,
                )
                if not boundary_verification.valid:
                    raise _HostApprovalRejected(
                        "Host approval changed before mutation boundary: "
                        f"{boundary_verification.reason.replace('_', ' ')}."
                    )

            pre_apply_verifier = _revalidate_host_approval
        try:
            self._resolve_execution_project_path(arguments.get("project_path"))
        except ValueError as exc:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Reviewed normalization plan was rejected.",
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=False,
                error_category="validation",
                error_code=NORMALIZATION_PLAN_REJECTED,
                **common,
            )
        try:
            applied = apply_normalize_project(
                manifest,
                hub_path=self.hub_path,
                confirmation_token=supplied_token,
                pre_apply_verifier=pre_apply_verifier,
            )
        except _HostApprovalRejected as exc:
            common["approval_status"] = "rejected"
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Host approval was rejected at the mutation boundary.",
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=False,
                error_category="validation",
                error_code=NORMALIZATION_HOST_APPROVAL_REJECTED,
                **common,
            )
        except (FileExistsError, OSError, PermissionError, RuntimeError, ValueError) as exc:
            return self._envelope(
                "figops.normalize_project_structure",
                arguments,
                status="error",
                summary="Reviewed normalization plan was rejected.",
                errors=[str(exc)],
                manual_review_needed=True,
                is_dry_run=False,
                error_category="validation",
                error_code=NORMALIZATION_PLAN_REJECTED,
                **common,
            )
        validation = self._validation_summary(config_path)
        validation_failed = validation.get("checked") is True and validation.get("valid") is False
        approval_response_fields = (
            {
                "approval_receipt_id": common["approval_receipt_id"],
                "host_approval_required": common["host_approval_required"],
                "approval_status": common["approval_status"],
            }
            if self.require_host_approval
            else {}
        )
        return self._envelope(
            "figops.normalize_project_structure",
            arguments,
            status="warning" if validation_failed else "ok",
            summary=(
                f"Applied normalization for {project_root.name}, but project validation still needs changes."
                if validation_failed
                else f"Applied normalization for {project_root.name}."
            ),
            created_paths=applied["created_paths"],
            modified_paths=[],
            skipped_paths=[],
            warnings=["Normalized project config did not pass validation."] if validation_failed else [],
            manual_review_needed=validation_failed,
            is_dry_run=False,
            project_root=str(project_root),
            planned_paths=planned_paths,
            manifest=public_manifest,
            manifest_path="",
            config_path=str(config_path),
            style_summary=manifest["style_summary"],
            validation=validation,
            proposed_mappings=proposed_mappings,
            unresolved_proposals=common["unresolved_proposals"],
            plan_digest=applied["plan_digest"],
            confirmation_token=token,
            **approval_response_fields,
            originals_preserved=applied["originals_preserved"],
            rollback_journal=applied["rollback_journal"],
            provenance_receipt=applied["provenance_receipt"],
        )
