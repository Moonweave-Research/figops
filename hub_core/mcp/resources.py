from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml

from hub_core.config_parser import ALLOWED_OUTPUT_FORMATS, ALLOWED_TARGET_FORMATS, load_yaml_with_unique_keys
from hub_core.project_discovery import ProjectDiscoveryService
from themes.style_packs import list_style_packs
from themes.style_profiles import DEFAULT_PROFILE, PROFILE_ALIASES, list_profiles

_STRICT_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


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
                "profiles": list_profiles(),
                "profile_aliases": dict(sorted(PROFILE_ALIASES.items())),
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
            config_path = Path(project.config_path)
            self._validate_resource_config_path(config_path, (self.research_root / project.path).resolve())
            try:
                text = config_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise FileNotFoundError(f"Project config not found: {project.project_id}") from exc
            return self._resource_text(uri, "application/x-yaml", text)
        if authority == "jobs" and len(segments) == 2 and segments[1] == "manifest":
            job_id = segments[0]
            if _STRICT_JOB_ID_RE.fullmatch(job_id) is None:
                raise ValueError("job_id contains invalid characters.")
            manifest_path = self._find_job_manifest_path(job_id)
            if not manifest_path.exists():
                raise FileNotFoundError(f"Render job manifest not found: {job_id}")
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"Render job manifest could not be read: {exc}") from exc
            sanitized = self._sanitize_resource_payload(manifest, {"data_path": manifest.get("source_data_path")})
            return self._resource_text(uri, "application/json", self._json_resource_text(sanitized))

        raise ValueError(f"Unsupported FigOps resource URI: {uri}")

    def _styles_payload(self) -> dict[str, Any]:
        return {
            "target_formats": sorted(ALLOWED_TARGET_FORMATS),
            "output_formats": sorted(ALLOWED_OUTPUT_FORMATS),
            "profiles": list_profiles(),
            "profile_aliases": dict(sorted(PROFILE_ALIASES.items())),
            "style_packs": list_style_packs(),
            "default_target_format": "nature",
            "default_profile": DEFAULT_PROFILE,
        }

    @staticmethod
    def _resource_text(uri: str, mime_type: str, text: str) -> dict[str, Any]:
        return {"contents": [{"uri": uri, "mimeType": mime_type, "text": text}]}

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
        if authority == "jobs" and not (len(segments) == 2 and segments[1] == "manifest"):
            raise ValueError("Job resource must be figops://jobs/{job_id}/manifest.")
        return {"authority": authority, "segments": segments}

    @staticmethod
    def _validate_resource_config_path(config_path: Path, project_path: Path) -> None:
        if config_path.is_symlink():
            raise ValueError("Project config resource refuses symlinked config files.")
        resolved_config = config_path.resolve()
        resolved_project = project_path.resolve()
        try:
            resolved_config.relative_to(resolved_project)
        except ValueError as exc:
            raise ValueError("Project config resource must stay inside the discovered project.") from exc
        if not config_path.is_file():
            raise FileNotFoundError(f"Project config not found: {config_path}")
        if config_path.stat().st_size > 1024 * 1024:
            raise ValueError("Project config resource refuses configs larger than 1 MiB.")

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
