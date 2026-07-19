from __future__ import annotations

import base64
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml

from hub_core.adapters import select_adapters
from hub_core.config_parser import ALLOWED_OUTPUT_FORMATS, PUBLIC_TARGET_FORMATS, load_yaml_with_unique_keys
from hub_core.mcp.manifest_io import read_verified_runtime_json_object
from hub_core.path_identity import (
    canonical_is_relative_to,
    canonical_path,
    lexical_or_canonical_relative_to,
)
from hub_core.project_config_reader import read_verified_project_config
from hub_core.project_discovery import ProjectDiscoveryService
from hub_core.project_paths import (
    ProjectPathError,
    normalize_project_relative_path,
    project_path_has_symlink_component,
)
from hub_core.runtime_paths import runtime_root_lookup_candidates
from themes.style_packs import list_style_packs
from themes.style_profiles import DEFAULT_PROFILE, PUBLIC_PROFILE_ALIASES, list_public_profiles

_STRICT_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_STRICT_LOGICAL_ROLE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_STRICT_ARTIFACT_INDEX_RE = re.compile(r"^(?:0|[1-9][0-9]{0,2})$")
_PREVIEW_BLOB_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


class McpResourcesMixin:
    """FigOps MCP resource handlers."""

    def read_resource(self, uri: str) -> dict[str, Any]:
        parsed = self._parse_resource_uri(uri)
        authority = parsed["authority"]
        segments = parsed["segments"]

        if authority == "styles" and not segments:
            return self._resource_text(uri, "application/json", self._json_resource_text(self._styles_payload()))
        if authority == "profiles" and not segments:
            payload = {
                "profiles": list_public_profiles(),
                "profile_aliases": dict(sorted(PUBLIC_PROFILE_ALIASES.items())),
                "default_profile": DEFAULT_PROFILE,
            }
            return self._resource_text(uri, "application/json", self._json_resource_text(payload))
        if authority == "projects" and not segments:
            root = self.research_root
            projects = ProjectDiscoveryService(root).discover(max_depth=4)
            payload = {
                "root": str(root),
                "count": len(projects),
                "projects": [self._serialize_project(project) for project in projects],
            }
            return self._resource_text(uri, "application/json", self._json_resource_text(payload))
        if authority == "projects" and len(segments) == 2 and segments[1] == "config":
            project = self._discover_project_by_id(segments[0])
            try:
                text = self._read_verified_project_config(project)
            except FileNotFoundError as exc:
                raise FileNotFoundError(f"Project config not found: {project.project_id}") from exc
            except Exception as exc:
                raise ValueError("Project config resource could not be read safely.") from exc
            return self._resource_text(uri, "application/x-yaml", text)
        if authority == "jobs" and len(segments) == 2 and segments[1] == "manifest":
            job_id = segments[0]
            if _STRICT_JOB_ID_RE.fullmatch(job_id) is None:
                raise ValueError("job_id contains invalid characters.")
            selection = self._resolve_job_manifest(job_id)
            try:
                manifest = read_verified_runtime_json_object(
                    selection.root,
                    selection.path,
                    expected_job_id=job_id,
                )
            except ValueError as exc:
                raise RuntimeError("Render job manifest could not be read safely.") from exc
            sanitized = self._sanitize_resource_payload(manifest, {"data_path": manifest.get("source_data_path")})
            return self._resource_text(uri, "application/json", self._json_resource_text(sanitized))
        if authority == "jobs" and len(segments) == 4 and segments[1] in {"artifacts", "previews"}:
            job_id, resource_kind, logical_role, raw_index = segments
            artifact_index = self._validate_preview_resource_address(job_id, logical_role, raw_index)
            if resource_kind == "artifacts":
                return self._read_preview_artifact_metadata(
                    uri,
                    job_id=job_id,
                    logical_role=logical_role,
                    artifact_index=artifact_index,
                )
            return self._read_preview_blob(
                uri,
                job_id=job_id,
                logical_role=logical_role,
                artifact_index=artifact_index,
            )

        raise ValueError(f"Unsupported FigOps resource URI: {uri}")

    def _styles_payload(self) -> dict[str, Any]:
        return {
            "target_formats": sorted(PUBLIC_TARGET_FORMATS),
            "output_formats": sorted(ALLOWED_OUTPUT_FORMATS),
            "profiles": list_public_profiles(),
            "profile_aliases": dict(sorted(PUBLIC_PROFILE_ALIASES.items())),
            "style_packs": list_style_packs(),
            "default_target_format": "nature",
            "default_profile": DEFAULT_PROFILE,
        }

    @staticmethod
    def _resource_text(uri: str, mime_type: str, text: str) -> dict[str, Any]:
        return {"contents": [{"uri": uri, "mimeType": mime_type, "text": text}]}

    @staticmethod
    def _resource_blob(uri: str, mime_type: str, blob: str) -> dict[str, Any]:
        return {"contents": [{"uri": uri, "mimeType": mime_type, "blob": blob}]}

    @staticmethod
    def _json_resource_text(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    @staticmethod
    def _parse_resource_uri(uri: str) -> dict[str, Any]:
        if not isinstance(uri, str) or not uri.strip():
            raise ValueError("Resource uri is required.")
        parsed = urlsplit(uri)
        if parsed.scheme not in {"figops", "graphhub"}:
            raise ValueError("Resource uri scheme must be figops.")
        if parsed.query or parsed.fragment:
            raise ValueError("Resource uri query and fragment are not supported.")
        authority = parsed.netloc
        if authority not in {"styles", "profiles", "projects", "jobs"}:
            raise ValueError(f"Unsupported FigOps resource authority: {authority}")
        if authority in {"styles", "profiles"} and parsed.path:
            raise ValueError(f"Resource figops://{authority} does not accept path segments.")
        if authority == "projects" and not parsed.path:
            return {"authority": authority, "segments": []}
        if authority == "jobs" and not parsed.path:
            raise ValueError("Job resource must be figops://jobs/{job_id}/manifest.")
        if authority in {"projects", "jobs"} and not parsed.path.startswith("/"):
            raise ValueError("Dynamic FigOps resource path must start with '/'.")
        raw_segments = parsed.path[1:].split("/") if parsed.path else []
        if any(segment == "" for segment in raw_segments):
            raise ValueError("Resource uri contains an empty path segment.")
        segments = [unquote(segment) for segment in raw_segments]
        if any(segment in {"", ".", ".."} or "/" in segment or "\\" in segment for segment in segments):
            raise ValueError("Resource uri contains an invalid path segment.")
        if authority == "projects" and not (len(segments) == 2 and segments[1] == "config"):
            raise ValueError("Project resource must be figops://projects or figops://projects/{project_id}/config.")
        if authority == "jobs":
            is_manifest = len(segments) == 2 and segments[1] == "manifest"
            is_addressed_artifact = len(segments) == 4 and segments[1] in {"artifacts", "previews"}
            if not (is_manifest or is_addressed_artifact):
                raise ValueError("Job resource must address a manifest or a logical preview artifact.")
        return {"authority": authority, "segments": segments}

    @staticmethod
    def _validate_preview_resource_address(job_id: str, logical_role: str, raw_index: str) -> int:
        if _STRICT_JOB_ID_RE.fullmatch(job_id) is None:
            raise ValueError("job_id contains invalid characters.")
        if _STRICT_LOGICAL_ROLE_RE.fullmatch(logical_role) is None:
            raise ValueError("logical_role contains invalid characters.")
        if _STRICT_ARTIFACT_INDEX_RE.fullmatch(raw_index) is None:
            raise ValueError("artifact_index must be a canonical non-negative integer.")
        artifact_index = int(raw_index)
        if artifact_index >= 256:
            raise ValueError("artifact_index must be smaller than 256.")
        return artifact_index

    def _read_preview_artifact_metadata(
        self,
        uri: str,
        *,
        job_id: str,
        logical_role: str,
        artifact_index: int,
    ) -> dict[str, Any]:
        try:
            from hub_core.mcp.preview_artifacts import describe_job_preview

            metadata = describe_job_preview(
                self.runtime_root,
                job_id,
                logical_role=logical_role,
                artifact_index=artifact_index,
            )
            payload = metadata.as_dict()
        except Exception as exc:
            raise RuntimeError("Preview artifact metadata could not be read safely.") from exc
        sanitized = self._sanitize_resource_payload(payload, {})
        return self._resource_text(uri, "application/json", self._json_resource_text(sanitized))

    def _read_preview_blob(
        self,
        uri: str,
        *,
        job_id: str,
        logical_role: str,
        artifact_index: int,
    ) -> dict[str, Any]:
        try:
            from hub_core.mcp.preview_artifacts import (
                MAX_PREVIEW_BASE64_BYTES,
                MAX_PREVIEW_RAW_BYTES,
                read_job_preview_blob,
            )

            preview = read_job_preview_blob(
                self.runtime_root,
                job_id,
                logical_role=logical_role,
                artifact_index=artifact_index,
            )
        except Exception as exc:
            raise RuntimeError("Preview blob could not be read safely.") from exc
        try:
            metadata = preview.metadata.as_dict()
            if metadata.get("availability") != "available" or preview.data_base64 is None:
                payload = preview.as_dict(include_data=False)
                sanitized = self._sanitize_resource_payload(payload, {})
                return self._resource_text(uri, "application/json", self._json_resource_text(sanitized))
        except Exception as exc:
            raise RuntimeError("Preview blob metadata could not be read safely.") from exc
        media_type = preview.preview_media_type
        if media_type not in _PREVIEW_BLOB_MEDIA_TYPES:
            raise RuntimeError("Preview worker returned a disallowed media type.")
        if not isinstance(preview.data_base64, str) or not preview.data_base64:
            raise RuntimeError("Preview worker returned an invalid blob payload.")
        try:
            encoded = preview.data_base64.encode("ascii")
            if len(encoded) > MAX_PREVIEW_BASE64_BYTES:
                raise ValueError("encoded preview exceeds its limit")
            raw = base64.b64decode(encoded, validate=True)
        except (UnicodeEncodeError, ValueError) as exc:
            raise RuntimeError("Preview worker returned an invalid blob payload.") from exc
        if (
            len(raw) > MAX_PREVIEW_RAW_BYTES
            or preview.encoded_byte_size != len(encoded)
            or preview.raw_byte_size != len(raw)
            or not self._preview_magic_matches_media_type(raw, media_type)
        ):
            raise RuntimeError("Preview worker returned inconsistent bounded blob metadata.")
        return self._resource_blob(uri, media_type, preview.data_base64)

    @staticmethod
    def _preview_magic_matches_media_type(raw: bytes, media_type: str) -> bool:
        if media_type == "image/png":
            return raw.startswith(b"\x89PNG\r\n\x1a\n")
        if media_type == "image/jpeg":
            return raw.startswith(b"\xff\xd8\xff")
        if media_type == "image/webp":
            return len(raw) >= 12 and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"
        return False

    def _read_verified_project_config(self, project: Any) -> str:
        """Read one discovered config from the same verified descriptor."""

        if not project.config:
            raise FileNotFoundError("Discovered project has no config declaration.")
        try:
            research_root = canonical_path(self.research_root, strict=True)
            project_declaration = normalize_project_relative_path(project.path, purpose="discovered project")
            if project_path_has_symlink_component(
                research_root,
                project_declaration,
                purpose="discovered project",
            ):
                raise ProjectPathError("Discovered project includes a symlink or reparse-point component.")
            project_root = canonical_path(
                research_root.joinpath(*PurePosixPath(project_declaration).parts),
                strict=True,
            )
            if not canonical_is_relative_to(project_root, research_root, strict=True):
                raise ProjectPathError("Discovered project must stay inside the research root.")
            if not project_root.is_dir():
                raise ProjectPathError("Discovered project root must be a directory.")
        except ValueError as exc:
            raise ProjectPathError("Discovered project must stay inside the research root.") from exc
        except (OSError, RuntimeError) as exc:
            raise ProjectPathError("Discovered project root is unavailable.") from exc

        text = read_verified_project_config(
            project_root,
            project.config,
            prefetcher=select_adapters({}).prefetcher,
        )
        # ``Path.read_text`` previously exposed universal-newline text. Preserve
        # that public representation without reopening the verified pathname.
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _runtime_root_for_manifest(self, manifest_path: Path) -> Path:
        roots = [Path(self.runtime_root)]
        if not self._runtime_root_explicit:
            roots.extend(Path(path) for path in runtime_root_lookup_candidates())
        raw_manifest = manifest_path.expanduser().absolute()
        for candidate in roots:
            try:
                root = canonical_path(candidate, strict=True)
                lexical_or_canonical_relative_to(raw_manifest, root)
            except (FileNotFoundError, OSError, RuntimeError, ValueError):
                continue
            return root
        raise ValueError("Render job manifest is outside the configured runtime roots.")

    def _discover_project_by_id(self, project_id: str) -> Any:
        for project in ProjectDiscoveryService(self.research_root).discover(max_depth=4):
            if project.project_id == project_id:
                return project
        raise FileNotFoundError(f"Project id not found: {project_id}")

    def _sanitize_resource_payload(self, value: Any, arguments: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {key: self._sanitize_resource_payload(item, arguments) for key, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize_resource_payload(item, arguments) for item in value]
        if isinstance(value, str):
            return self._sanitize_diagnostic_text(value, arguments)
        return value

    @staticmethod
    def _public_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
        public = dict(manifest)
        public["entries"] = [McpResourcesMixin._public_manifest_entry(entry) for entry in manifest.get("entries", [])]
        return public

    @staticmethod
    def _public_manifest_entry(entry: dict[str, Any]) -> dict[str, Any]:
        public = dict(entry)
        public.pop("content", None)
        return public

    @staticmethod
    def _manifest_destinations(manifest: dict[str, Any]) -> list[str]:
        paths = []
        for entry in manifest.get("entries", []):
            destination = entry.get("destination")
            if isinstance(destination, str) and destination:
                paths.append(destination)
        return paths

    @staticmethod
    def _manifest_style_summary(manifest: dict[str, Any]) -> dict[str, Any]:
        for entry in manifest.get("entries", []):
            if entry.get("destination") != "project_config.yaml":
                continue
            raw_config = entry.get("content")
            if not isinstance(raw_config, str):
                continue
            try:
                config = load_yaml_with_unique_keys(raw_config) or {}
            except yaml.YAMLError:
                break
            visual_style = config.get("visual_style") if isinstance(config.get("visual_style"), dict) else {}
            presets = config.get("presets") if isinstance(config.get("presets"), dict) else {}
            return {
                "target_format": str(visual_style.get("target_format") or "nature"),
                "profile": str(visual_style.get("profile") or DEFAULT_PROFILE),
                "presets": sorted(str(key) for key in presets),
                "style_update_applied": True,
            }
        return {"target_format": "nature", "profile": DEFAULT_PROFILE, "presets": [], "style_update_applied": False}
