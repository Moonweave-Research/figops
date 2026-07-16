"""Thin read-only MCP adapter for bounded data inspection."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from hub_core.allowed_data import resolve_inspect_max_bytes
from hub_core.config_parser import load_yaml_with_unique_keys, validate_config
from hub_core.data_inspection import inspect_allowed_data
from hub_core.external_raw import ExternalRawError, validate_external_raw_descriptors
from hub_core.external_raw_execution import bind_launcher_allowed_roots
from hub_core.path_identity import canonical_is_relative_to, canonical_path
from hub_core.project_config_reader import find_verified_project_config, read_verified_project_config
from hub_core.project_discovery import ProjectDiscoveryService

_VALUE_ACCESS_CLASSES = frozenset({"public", "internal"})
_RESTRICTED_ACCESS_CLASSES = frozenset({"restricted", "sensitive", "confidential", "secret"})


def _normalize_access_class(value: object) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "unspecified"
    if not isinstance(value, str):
        return "unknown"
    normalized = value.strip().lower().replace("-", "_")
    if normalized in _VALUE_ACCESS_CLASSES:
        return normalized
    if normalized in _RESTRICTED_ACCESS_CLASSES:
        return "restricted"
    return "unknown"


def _declared_access(item: dict[str, Any]) -> str:
    values = [item[key] for key in ("access_class", "sensitivity") if key in item]
    if not values:
        return "unspecified"
    normalized = {_normalize_access_class(value) for value in values}
    return normalized.pop() if len(normalized) == 1 else "unknown"


class McpDataToolsMixin:
    """Expose one-shot facts without adding response-envelope context overhead."""

    def inspect_data(self, arguments: dict[str, Any]) -> dict[str, Any]:
        requested_include = arguments.get("include_samples", False)
        requested_rows = arguments.get("sample_rows", 0)
        samples_requested = requested_include is True
        policy = self._data_access_policy(
            arguments.get("data_path"),
            samples_requested=samples_requested,
            external_raw_id=arguments.get("external_raw_id"),
        )
        bounded_values = policy["mode"] == "bounded_values"
        external_identity = policy.get("external_raw_identity")
        prefetch_mode = str(os.environ.get("GRAPH_HUB_PREFETCH_ADAPTER") or "none").strip().lower()
        if prefetch_mode == "noop":
            prefetch_mode = "noop"
        elif prefetch_mode == "gdrive":
            prefetch_mode = "gdrive"
        else:
            prefetch_mode = "none"
        inspect_kwargs = {
            "allowed_roots": tuple(root for root in self.allowed_data_roots if root.is_dir()),
            "relative_base": self.research_root,
            "prefetch_mode": prefetch_mode,
            "max_bytes": resolve_inspect_max_bytes(warnings=self.security_warnings),
            "columns": arguments.get("columns"),
        }
        # External raw values require a verified post-prefetch digest.  The
        # first pass is metadata-only; only exact descriptor identity and SHA
        # agreement authorize a bounded second pass.
        first_pass_values = bounded_values and external_identity is None
        result = inspect_allowed_data(
            arguments.get("data_path"),
            **inspect_kwargs,
            include_samples=(first_pass_values if isinstance(requested_include, bool) else requested_include),
            sample_rows=(requested_rows if first_pass_values else 0),
        )
        if external_identity is not None and bounded_values:
            observed_sha256 = str((result.get("source") or {}).get("sha256") or "")
            expected_sha256 = str(external_identity["sha256"])
            if result.get("status") == "available" and observed_sha256 == expected_sha256:
                result = inspect_allowed_data(
                    arguments.get("data_path"),
                    **inspect_kwargs,
                    include_samples=True,
                    sample_rows=requested_rows,
                )
                if str((result.get("source") or {}).get("sha256") or "") == expected_sha256:
                    policy["materialized_sha256_verified"] = True
                else:
                    bounded_values = False
            else:
                bounded_values = False
            if not bounded_values:
                policy.update(
                    {
                        "mode": "metadata_only",
                        "samples_allowed": False,
                        "reason_code": "INSPECTION_METADATA_ONLY_EXTERNAL_HASH_MISMATCH",
                        "materialized_sha256_verified": False,
                    }
                )
        if result.get("status") == "unavailable":
            reason = str((result.get("availability") or {}).get("reason") or "INSPECTION_UNAVAILABLE")
            result["status_code"] = reason
        elif bounded_values:
            result["status_code"] = "INSPECTION_VALUES_AVAILABLE"
        else:
            self._metadata_only(result)
            result["status_code"] = policy["reason_code"]
            warnings = result.setdefault("warnings", [])
            warnings.append(
                {
                    "code": policy["reason_code"],
                    "message": "Data values and sample rows were omitted by the declared sensitivity policy.",
                }
            )
        result["access_policy"] = policy
        return result

    def _data_access_policy(
        self,
        raw_path: object,
        *,
        samples_requested: bool,
        external_raw_id: object = None,
    ) -> dict[str, Any]:
        requested_external_id = external_raw_id.strip() if isinstance(external_raw_id, str) else None
        declarations = self._matching_data_declarations(
            raw_path,
            external_raw_id=requested_external_id,
        )
        if not declarations:
            classification = "unknown"
            declaration_source = "undeclared"
        elif len(declarations) > 1:
            classification = "unknown"
            declaration_source = "multiple_declarations"
        else:
            classes = {item["classification"] for item in declarations}
            sources = {item["source"] for item in declarations}
            classification = classes.pop() if len(classes) == 1 else "unknown"
            declaration_source = sources.pop() if len(sources) == 1 else "multiple_declarations"

        external_identity = None
        if len(declarations) == 1 and declarations[0]["source"] == "external_raw":
            external_identity = declarations[0].get("external_raw_identity")

        external_id_missing = declaration_source == "external_raw" and not requested_external_id
        samples_allowed = (
            classification in _VALUE_ACCESS_CLASSES
            and samples_requested
            and not external_id_missing
            and (declaration_source != "external_raw" or external_identity is not None)
        )
        if samples_allowed:
            reason_code = "INSPECTION_VALUES_AVAILABLE"
        elif external_id_missing:
            reason_code = "INSPECTION_METADATA_ONLY_EXTERNAL_ID_REQUIRED"
        elif classification == "restricted":
            reason_code = "INSPECTION_METADATA_ONLY_RESTRICTED"
        elif classification == "unspecified":
            reason_code = "INSPECTION_METADATA_ONLY_UNSPECIFIED"
        elif classification == "unknown":
            reason_code = (
                "INSPECTION_METADATA_ONLY_UNDECLARED"
                if declaration_source == "undeclared"
                else "INSPECTION_METADATA_ONLY_AMBIGUOUS"
            )
        else:
            reason_code = "INSPECTION_METADATA_ONLY_DEFAULT"
        policy = {
            "classification": classification,
            "declaration_source": declaration_source,
            "mode": "bounded_values" if samples_allowed else "metadata_only",
            "samples_requested": samples_requested,
            "samples_allowed": samples_allowed,
            "reason_code": reason_code,
        }
        if external_identity is not None:
            policy["external_raw_identity"] = external_identity
            policy["materialized_sha256_verified"] = False
        return policy

    def _matching_data_declarations(
        self,
        raw_path: object,
        *,
        external_raw_id: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            requested = self._resolve_allowed_data_path(raw_path, field_name="data_path")
        except (OSError, RuntimeError, TypeError, ValueError):
            return []
        matches: list[dict[str, Any]] = []
        try:
            external_authority = bind_launcher_allowed_roots(
                tuple(root for root in self.allowed_data_roots if root.is_dir())
            )
        except (ExternalRawError, OSError):
            external_authority = {}
        for project_root, config in self._policy_configs(requested):
            data_contract = config.get("data_contract")
            checks = data_contract.get("csv_checks", []) if isinstance(data_contract, dict) else []
            if isinstance(checks, list):
                for check in checks:
                    if not isinstance(check, dict) or not isinstance(check.get("path"), str):
                        continue
                    try:
                        candidate = (project_root / check["path"]).resolve()
                    except (OSError, RuntimeError):
                        continue
                    if candidate == requested:
                        matches.append(
                            {"classification": _declared_access(check), "source": "data_contract"}
                        )

            try:
                external_descriptors = validate_external_raw_descriptors(config.get("external_raw"))
            except ExternalRawError:
                continue
            for descriptor in external_descriptors:
                if descriptor.locator_kind != "path":
                    continue
                if external_raw_id is not None and descriptor.id != external_raw_id:
                    continue
                allowed_root = external_authority.get(descriptor.allowed_root)
                if allowed_root is None:
                    continue
                try:
                    candidate = canonical_path(
                        allowed_root.joinpath(*descriptor.locator.split("/")),
                        strict=True,
                    )
                    if not canonical_is_relative_to(candidate, allowed_root, strict=True):
                        continue
                except (FileNotFoundError, OSError, RuntimeError, ValueError):
                    continue
                if candidate != requested:
                    continue
                identity = {
                    "artifact_id": descriptor.id,
                    "allowed_root": descriptor.allowed_root,
                    "version": descriptor.version,
                    "sha256": descriptor.sha256,
                    "content_included": False,
                }
                matches.append(
                    {
                        "classification": _normalize_access_class(descriptor.access_class),
                        "source": "external_raw",
                        "external_raw_identity": identity,
                    }
                )
        return matches

    def _policy_configs(self, requested: Path) -> list[tuple[Path, dict[str, Any]]]:
        roots: list[Path] = []
        if canonical_is_relative_to(requested, self.research_root):
            for parent in (requested.parent, *requested.parents):
                try:
                    if find_verified_project_config(parent) is not None:
                        roots.append(parent)
                        break
                except (OSError, RuntimeError, ValueError):
                    continue
                if parent == self.research_root:
                    break
        try:
            roots.extend(
                (self.research_root / project.path).resolve()
                for project in ProjectDiscoveryService(self.research_root).discover(max_depth=4)
                if project.classification not in {"folder_role", "unclassified"}
            )
        except (OSError, RuntimeError, ValueError):
            pass

        configs: list[tuple[Path, dict[str, Any]]] = []
        seen: set[str] = set()
        for root in roots:
            key = os.path.normcase(str(root))
            if key in seen:
                continue
            seen.add(key)
            try:
                declaration = find_verified_project_config(root)
                if declaration is None:
                    continue
                parsed = load_yaml_with_unique_keys(read_verified_project_config(root, declaration))
            except Exception:
                continue
            if isinstance(parsed, dict):
                if not validate_config(parsed, project_root=root):
                    configs.append((root, parsed))
        return configs

    @staticmethod
    def _metadata_only(result: dict[str, Any]) -> None:
        result["columns"] = []
        result["sample_columns"] = []
        result["samples"] = []
        result["sample_columns"] = []
        result["samples"] = []
        scan = result.get("scan")
        if isinstance(scan, dict):
            scan["columns_returned"] = 0


__all__ = ["McpDataToolsMixin"]
