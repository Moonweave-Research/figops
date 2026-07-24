"""Build validated policy-neutral evidence for successful render manifests."""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from .artifact_policy_measurement import measure_artifact_policy
from .evidence_contract import normalize_evidence_envelope
from .geometry_raw_contract import normalize_geometry_payload
from .project_paths import open_verified_project_input, snapshot_project_input
from .provenance_inputs import provenance_hash_coverage

_SHA256: Final = re.compile(r"^[0-9a-fA-F]{64}$")
_RASTER_MEDIA: Final = {"image/png", "image/jpeg", "image/webp"}
_MEDIA_BY_SUFFIX: Final = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".svg": "image/svg+xml",
}
_MAX_ARTIFACTS: Final = 256
_MAX_ARTIFACT_BYTES: Final = 256 * 1024 * 1024
_MAX_RASTER_PIXELS: Final = 100_000_000
_RENDER_POLICY_CONTEXT_SCHEMA: Final = "figops-render-policy-context/1"


class RenderEvidenceError(ValueError):
    """A render result cannot be represented as trustworthy v2 evidence."""


def build_render_evidence(
    manifest: Mapping[str, Any],
    *,
    job_root: str | Path,
    producer_kind: str,
    producer_version: str,
    resolved_policy: Mapping[str, Any] | None = None,
    render_policy: Mapping[str, Any] | None = None,
    policy_context: Mapping[str, Any] | None = None,
    validation_target: str | None = None,
    baseline_reference_sha256: str | None = None,
) -> dict[str, Any]:
    """Re-verify final bytes and return one frozen ``figops_evidence/2`` envelope."""

    provenance = _provenance(manifest.get("provenance"))
    producer = {
        "status": "passed",
        "kind": _required_text(producer_kind, "producer_kind"),
        "version": _required_text(producer_version, "producer_version"),
    }
    entries = _artifact_entries(manifest, Path(job_root))
    artifacts: dict[str, Any] = {"status": "passed", "entries": entries}

    geometry = normalize_geometry_payload(_geometry_payload(manifest))
    measurements = list(geometry["measurements"])
    evidence: dict[str, Any] = {
        "version": "2.0",
        "producer": producer,
        "measurements": measurements,
        "policy_projections": [],
        "artifacts": artifacts,
        "provenance": provenance,
        "data_contract_summary": _data_contract_summary(manifest),
        "calculation_summary": _calculation_summary(manifest),
        "exact_reproducibility": _exact_reproducibility(
            manifest.get("baseline_comparison"),
            reference_sha256=baseline_reference_sha256,
        ),
        "visual_comparison": None,
    }
    policy = _resolved_policy(resolved_policy)
    context = _policy_context(policy_context)
    selected_render_policy = _resolved_policy(render_policy)
    target = str(validation_target or "").strip().lower()
    if context is not None:
        evidence["policy_context"] = context
        context_render_policy = _resolved_policy(context["render_policy"])
        if selected_render_policy is not None and selected_render_policy != context_render_policy:
            raise RenderEvidenceError("render_policy conflicts with policy_context")
        selected_render_policy = selected_render_policy or context_render_policy
        context_target = str(context.get("validation_target") or "").strip().lower()
        if target and context_target and target != context_target:
            raise RenderEvidenceError("validation_target conflicts with policy_context")
        target = target or context_target
    if target:
        if policy is not None:
            raise RenderEvidenceError(
                "validation_target cannot be combined with the legacy resolved_policy argument"
            )
        primary = next(entry for entry in entries if entry["logical_role"] == "primary")
        measured = measure_artifact_policy(
            Path(job_root) / primary["relative_path"],
            validation_target=target,
            artifact_sha256=primary["sha256"],
            render_policy=(
                str(selected_render_policy["id"])
                if selected_render_policy is not None
                else "neutral"
            ),
            geometry_measurements=measurements,
            producer_binding={"producer": producer, "provenance": provenance},
        )
        measurements.extend(measured["measurements"])
        evidence["policy_projections"] = [measured["policy_projection"]]
        policy = measured["resolved_policy"]
    elif selected_render_policy is not None:
        if policy is not None:
            raise RenderEvidenceError("render_policy conflicts with the legacy resolved_policy argument")
        policy = selected_render_policy
    if policy is not None:
        evidence["resolved_policy"] = policy
    ledger = manifest.get("mutation_ledger")
    if isinstance(ledger, list) and ledger:
        evidence["mutation_ledger"] = ledger
    return normalize_evidence_envelope(evidence)


def _artifact_entries(manifest: Mapping[str, Any], job_root: Path) -> list[dict[str, Any]]:
    raw_entries = manifest.get("preview_artifacts")
    if not isinstance(raw_entries, list) or not raw_entries or len(raw_entries) > _MAX_ARTIFACTS:
        raise RenderEvidenceError("render manifest has no bounded preview artifact membership")
    root = job_root.resolve(strict=True)
    entries = [_verified_artifact_entry(root, raw, index) for index, raw in enumerate(raw_entries)]
    roles = [entry["logical_role"] for entry in entries]
    if roles.count("primary") != 1:
        raise RenderEvidenceError("render evidence requires exactly one primary artifact")
    return entries


def _verified_artifact_entry(root: Path, raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise RenderEvidenceError(f"preview_artifacts[{index}] must be an object")
    role = _required_text(raw.get("logical_role"), f"preview_artifacts[{index}].logical_role")
    declaration = _required_text(raw.get("relative_path"), f"preview_artifacts[{index}].relative_path")
    media_type = _required_text(raw.get("media_type"), f"preview_artifacts[{index}].media_type").lower()
    declared_size = raw.get("byte_size")
    declared_hash = raw.get("sha256")
    if isinstance(declared_size, bool) or not isinstance(declared_size, int) or declared_size <= 0:
        raise RenderEvidenceError("preview artifact has an invalid byte size")
    if not isinstance(declared_hash, str) or _SHA256.fullmatch(declared_hash) is None:
        raise RenderEvidenceError("preview artifact has an invalid SHA-256")
    snapshot = snapshot_project_input(root, declaration, purpose="render evidence artifact")
    if _MEDIA_BY_SUFFIX.get(snapshot.path.suffix.lower()) != media_type:
        raise RenderEvidenceError("preview artifact media type does not match its extension")
    with open_verified_project_input(
        root,
        declaration,
        expected_snapshot=snapshot,
        purpose="render evidence artifact",
    ) as stream:
        opened = os.fstat(stream.fileno())
        if opened.st_size != declared_size or opened.st_size > _MAX_ARTIFACT_BYTES:
            raise RenderEvidenceError("preview artifact byte size changed after sealing")
        head = stream.read(4096)
        if _detected_media_type(head) != media_type:
            raise RenderEvidenceError("preview artifact header does not match its media type")
        dimensions = _raster_dimensions(stream) if media_type in _RASTER_MEDIA else None
        stream.seek(0)
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        closed = os.fstat(stream.fileno())
    if _identity(opened) != _identity(closed):
        raise RenderEvidenceError("preview artifact changed during evidence verification")
    if digest.hexdigest().lower() != declared_hash.lower():
        raise RenderEvidenceError("preview artifact hash changed after sealing")
    entry = {
        "logical_role": role,
        "relative_path": declaration.replace("\\", "/"),
        "media_type": media_type,
        "byte_size": declared_size,
        "sha256": declared_hash.lower(),
        "header_valid": True,
        "availability": "available",
    }
    if dimensions is None:
        entry.update(
            {
                "dimension_availability": "unavailable",
                "dimension_reason": "vector artifacts do not define policy-neutral pixel dimensions",
            }
        )
    else:
        entry.update(
            {
                "width": dimensions[0],
                "height": dimensions[1],
                "dimensions_valid": True,
                "dimension_availability": "available",
            }
        )
    return entry


def _raster_dimensions(stream: Any) -> tuple[int, int]:
    try:
        from PIL import Image

        stream.seek(0)
        with Image.open(stream) as image:
            width, height = int(image.width), int(image.height)
            if width <= 0 or height <= 0 or width * height > _MAX_RASTER_PIXELS:
                raise RenderEvidenceError("raster artifact dimensions exceed the evidence limit")
            image.verify()
        return width, height
    except RenderEvidenceError:
        raise
    except Exception as exc:
        raise RenderEvidenceError("raster artifact structure could not be verified") from exc


def _provenance(raw: Any) -> dict[str, Any]:
    coverage = provenance_hash_coverage(raw)
    if coverage["status"] != "passed":
        missing = ", ".join(coverage["missing"])
        raise RenderEvidenceError(f"render provenance is missing required hashes: {missing}")
    return {"status": "passed", **coverage["hashes"], "unavailable_fields": []}


def _geometry_payload(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = manifest.get("geometry_diagnostics")
    if not isinstance(payload, Mapping):
        raise RenderEvidenceError("render geometry evidence is missing or malformed")
    return payload


def _data_contract_summary(manifest: Mapping[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    contract = manifest.get("data_contract")
    if isinstance(contract, Mapping):
        passed = contract.get("passed")
        if isinstance(passed, bool):
            checks.append(
                {
                    "id": "data_contract",
                    "status": "passed" if passed else "failed",
                    "message": (
                        "Declared data contract validation completed."
                        if passed
                        else "Declared data contract failed."
                    ),
                }
            )
    raw = manifest.get("raw_integrity_status")
    if isinstance(raw, Mapping) and raw.get("configured") is True:
        ok = raw.get("ok") is True
        mode = str(raw.get("mode") or "warn").lower()
        checks.append(
            {
                "id": "raw_integrity",
                "status": "passed" if ok else "failed" if mode == "strict" else "warning",
                "message": (
                    "Declared raw inputs match their integrity seal."
                    if ok
                    else "Declared raw inputs require reconciliation."
                ),
            }
        )
    return _summary(checks, "no data contract evidence was produced")


def _calculation_summary(manifest: Mapping[str, Any]) -> dict[str, Any]:
    raw = manifest.get("calculation_checks")
    raw_checks = raw.get("checks") if isinstance(raw, Mapping) else None
    checks: list[dict[str, str]] = []
    if isinstance(raw_checks, list):
        for index, item in enumerate(raw_checks[:256]):
            if not isinstance(item, Mapping):
                continue
            status = str(item.get("status") or "skipped").lower()
            if status not in {"passed", "warning", "failed", "skipped"}:
                status = "failed"
            check_id = str(item.get("id") or item.get("name") or f"calculation.{index}").strip()
            message = str(item.get("message") or f"Calculation check {check_id} reported {status}.").strip()
            checks.append({"id": check_id or f"calculation.{index}", "status": status, "message": message})
    return _summary(checks, "no calculation checks were selected")


def _summary(checks: list[dict[str, str]], skipped_reason: str) -> dict[str, Any]:
    statuses = {item["status"] for item in checks}
    if "failed" in statuses:
        status = "failed"
    elif "warning" in statuses:
        status = "warning"
    elif checks:
        status = "passed"
    else:
        status = "skipped"
    result: dict[str, Any] = {"status": status, "checks": checks}
    if status == "skipped":
        result["reason"] = skipped_reason
    return result


def _exact_reproducibility(raw: Any, *, reference_sha256: str | None) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping) or raw.get("checked") is not True:
        return None
    reference = reference_sha256 or raw.get("reference_sha256")
    candidate = raw.get("artifact_sha256") or raw.get("candidate_sha256")
    if (
        isinstance(reference, str)
        and _SHA256.fullmatch(reference)
        and isinstance(candidate, str)
        and _SHA256.fullmatch(candidate)
    ):
        return {
            "status": "same" if reference.lower() == candidate.lower() else "different",
            "algorithm": "sha256",
            "reference_sha256": reference.lower(),
            "candidate_sha256": candidate.lower(),
        }
    return {"status": "unavailable", "reason": "baseline comparison hashes were incomplete"}


def _resolved_policy(raw: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    policy = {
        "id": raw.get("id"),
        "version": raw.get("version"),
        "source": raw.get("source"),
        "parameters": raw.get("parameters", {}),
    }
    if not all(isinstance(policy[field], str) and str(policy[field]).strip() for field in ("id", "version", "source")):
        raise RenderEvidenceError("resolved render policy is malformed")
    if not isinstance(policy["parameters"], Mapping):
        raise RenderEvidenceError("resolved render policy parameters must be an object")
    return policy


def _policy_context(raw: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    context = {
        "schema_version": raw.get("schema_version"),
        "source": raw.get("source"),
        "policy_set_sha256": raw.get("policy_set_sha256"),
        "render_policy": raw.get("render_policy"),
        "validation_target": raw.get("validation_target"),
    }
    if context["schema_version"] != _RENDER_POLICY_CONTEXT_SCHEMA:
        raise RenderEvidenceError("policy_context schema is malformed")
    if not isinstance(context["source"], str) or not context["source"].strip():
        raise RenderEvidenceError("policy_context source is malformed")
    if not isinstance(context["policy_set_sha256"], str) or _SHA256.fullmatch(context["policy_set_sha256"]) is None:
        raise RenderEvidenceError("policy_context digest is malformed")
    if not isinstance(context["render_policy"], Mapping):
        raise RenderEvidenceError("policy_context render_policy is malformed")
    if "validation_target" not in raw:
        raise RenderEvidenceError("policy_context validation_target is malformed")
    target = context["validation_target"]
    if target is not None and (not isinstance(target, str) or not target.strip()):
        raise RenderEvidenceError("policy_context validation_target is malformed")
    return context


def _detected_media_type(head: bytes) -> str:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(head) >= 12 and head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if b"<svg" in head.lstrip(b"\xef\xbb\xbf\x00\t\r\n ")[:1024].lower():
        return "image/svg+xml"
    return ""


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RenderEvidenceError(f"{field} must be a non-empty string")
    return value.strip()


def _identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns


__all__ = ["RenderEvidenceError", "build_render_evidence"]
