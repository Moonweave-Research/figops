"""Compact one-render and completed-job audit response contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Final
from urllib.parse import quote

from hub_core.evidence_contract import normalize_evidence_envelope
from hub_core.mcp.preview_artifacts import preview_resource_uri

MAX_RENDER_RESPONSE_BYTES: Final = 96 * 1024
MAX_RESPONSE_WARNINGS: Final = 24
MAX_RESPONSE_TEXT: Final = 512
_RASTER_MEDIA: Final = {"image/png", "image/jpeg", "image/webp"}


def one_render_response(tool_name: str, result: Mapping[str, Any]) -> dict[str, Any]:
    """Project a verbose compatibility render result into the v2 reasoning payload."""

    job_id = _job_id(result.get("job_id"))
    evidence_raw = result.get("evidence")
    if result.get("status") == "error" or not isinstance(evidence_raw, Mapping):
        response = {
            "schema_version": "figops.render-response/1",
            "status": "error",
            "tool": tool_name,
            "job_id": job_id,
            "summary": _text(result.get("summary") or "Render failed."),
            "artifact": None,
            "manifest_uri": _manifest_uri(job_id) if job_id else None,
            "preview_uri": None,
            "evidence": None,
            "warnings": _texts(result.get("warnings")),
            "errors": _texts(result.get("errors")),
            "manual_review_needed": True,
            "failure_stage": _text(result.get("failure_stage")) or None,
            "resolution_hint": _text(result.get("resolution_hint")) or None,
        }
        runtime_availability = result.get("runtime_availability")
        if isinstance(runtime_availability, Mapping):
            response["runtime_availability"] = {
                "status": _text(runtime_availability.get("status")),
                "reason": _text(runtime_availability.get("reason")),
            }
        _add_project_render_context(response, result)
        return _bounded(response)

    evidence = normalize_evidence_envelope(evidence_raw)
    preview_uri = _preferred_preview_uri(result.get("preview_resources"), evidence)
    response = {
        "schema_version": "figops.render-response/1",
        "status": "warning" if result.get("status") == "warning" else "ok",
        "tool": tool_name,
        "job_id": job_id,
        "summary": _text(result.get("summary") or "Render completed."),
        "artifact": _primary_artifact(evidence),
        "manifest_uri": _manifest_uri(job_id),
        "preview_uri": preview_uri,
        "evidence": evidence,
        "warnings": _texts(result.get("warnings")),
        "errors": [],
        "manual_review_needed": bool(result.get("manual_review_needed")),
        "failure_stage": None,
        "resolution_hint": None,
    }
    _add_project_render_context(response, result)
    return _bounded(response)


def audit_response(
    *,
    job_id: str,
    evidence: Mapping[str, Any],
    report: Mapping[str, Any],
    preview_entries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a bounded audit synthesis without embedding manifest or image bytes."""

    normalized = normalize_evidence_envelope(evidence)
    preview_uris = [
        preview_resource_uri(job_id, str(entry["logical_role"]), index)
        for index, entry in enumerate(preview_entries)
        if isinstance(entry.get("logical_role"), str)
    ]
    preview_uri = _preferred_preview_uri(preview_uris, normalized)
    response = {
        "schema_version": "figops.audit-response/1",
        "status": report.get("status"),
        "job_id": job_id,
        "artifact": _primary_artifact(normalized),
        "manifest_uri": _manifest_uri(job_id),
        "preview_uri": preview_uri,
        "audit": dict(report),
    }
    return _bounded(response)


def _primary_artifact(evidence: Mapping[str, Any]) -> dict[str, Any] | None:
    artifacts = evidence.get("artifacts")
    entries = artifacts.get("entries") if isinstance(artifacts, Mapping) else None
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, Mapping) and entry.get("logical_role") == "primary":
            return {
                key: entry[key]
                for key in (
                    "logical_role",
                    "relative_path",
                    "media_type",
                    "byte_size",
                    "sha256",
                    "width",
                    "height",
                    "dimension_availability",
                    "dimension_reason",
                )
                if key in entry
            }
    return None


def _preferred_preview_uri(value: Any, evidence: Mapping[str, Any]) -> str | None:
    if not isinstance(value, list):
        return None
    artifacts = evidence.get("artifacts")
    entries = artifacts.get("entries") if isinstance(artifacts, Mapping) else None
    if isinstance(entries, list):
        for index, entry in enumerate(entries):
            if (
                isinstance(entry, Mapping)
                and entry.get("media_type") in _RASTER_MEDIA
                and index < len(value)
                and isinstance(value[index], str)
                and value[index].startswith("figops://jobs/")
            ):
                return value[index]
    for item in value:
        if isinstance(item, str) and item.startswith("figops://jobs/"):
            return item
    return None


def _job_id(value: Any) -> str:
    text = str(value or "")
    return text if text and len(text) <= 80 else ""


def _manifest_uri(job_id: str) -> str:
    return f"figops://jobs/{quote(job_id, safe='')}/manifest"


def _text(value: Any) -> str:
    text = str(value or "").replace("\x00", "")
    return text if len(text) <= MAX_RESPONSE_TEXT else text[: MAX_RESPONSE_TEXT - 12] + " [truncated]"


def _texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value[:MAX_RESPONSE_WARNINGS]]


def _add_project_render_context(response: dict[str, Any], result: Mapping[str, Any]) -> None:
    for key in ("policy_context", "workflow_intent"):
        value = result.get(key)
        if isinstance(value, Mapping):
            response[key] = dict(value)


def _bounded(response: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RENDER_RESPONSE_BYTES:
        raise RuntimeError("v2 render/audit response exceeds its bounded response contract")
    return response


__all__ = ["MAX_RENDER_RESPONSE_BYTES", "audit_response", "one_render_response"]
