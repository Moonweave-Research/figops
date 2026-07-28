"""Recomputable publication-policy measurements over an existing artifact.

This module is deliberately read-only: selecting a validation target never
invokes a renderer, applies a theme, or changes the supplied artifact bytes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from PIL import Image

from .config_style import ALLOWED_TARGET_FORMATS
from .journal_geometry_policy import geometry_minimum_results
from .journal_specs import get_preflight_spec
from .output_verification import verify_output_file
from .policy_resolution import PolicyResolutionError, resolve_policy_set

MEASUREMENT_IMPLEMENTATION: Final = "figops-artifact-policy-measurement"
MEASUREMENT_VERSION: Final = "3"
RULE_VERSION: Final = "3"
RENDER_POLICY_CONTEXT_SCHEMA: Final = "figops-render-policy-context/1"

_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_RASTER_SUFFIXES: Final = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
_FORMAT_ALIASES: Final = {"jpeg": "jpg", "tif": "tiff"}
_RENDER_POLICIES: Final = frozenset(ALLOWED_TARGET_FORMATS)
# Integer pixels-per-metre metadata cannot encode every integral DPI exactly.
# This bound covers that representation error without admitting a 599 DPI file
# against a 600 DPI minimum.
_DPI_METADATA_TOLERANCE: Final = 0.02


class ArtifactPolicyMeasurementError(ValueError):
    """An artifact policy projection cannot be measured or verified."""


def resolve_render_policy_selection(
    style_policy: str | None,
    *,
    compatibility: bool = False,
) -> dict[str, Any]:
    """Resolve the observable render policy for MCP/project integration.

    New surfaces default to a true no-op neutral theme.  Callers selecting the
    frozen compatibility surface must opt into ``compatibility=True`` to retain
    the historical Nature effective default.
    """

    return resolve_render_policy_context(
        {"style_policy": style_policy} if style_policy is not None else {},
        compatibility=compatibility,
    )["render_policy"]


def resolve_render_policy_context(
    arguments: Mapping[str, Any] | None = None,
    *,
    target_format: str | None = None,
    compatibility: bool | None = None,
    policy_layers: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve render/validation policy through the canonical policy core.

    The returned context is additive for new callers: legacy callers may still
    consume the singular ``render_policy`` and ``validation_target`` values,
    while provenance-aware callers can bind to ``policy_set_sha256``.
    """

    if arguments is None:
        arguments = {}
    if not isinstance(arguments, Mapping):
        raise ArtifactPolicyMeasurementError("render policy arguments must be a mapping")
    v2_contract = arguments.get("v2_policy_contract") is True
    compatibility_mode = (not v2_contract) if compatibility is None else bool(compatibility)
    selected, source, raw_render_policy = _selected_render_policy(
        arguments,
        target_format=target_format,
        compatibility=compatibility_mode,
    )
    validation_target, validation_source = _selected_validation_target(
        arguments,
        target_format=target_format,
        compatibility=compatibility_mode,
    )
    layer_parameters: dict[str, Any] = {}
    if source != "v2-default":
        layer_parameters["render_policy"] = selected
    if validation_target:
        layer_parameters["validation_target"] = validation_target
    layers = [dict(layer) for layer in policy_layers or ()]
    if layer_parameters:
        layers.append(
            {
                "source": "render",
                "policy_id": f"render-context-{selected}",
                "version": "1",
                "parameters": layer_parameters,
            }
        )
    try:
        policy_set = resolve_policy_set(layers)
    except PolicyResolutionError as exc:
        raise ArtifactPolicyMeasurementError(str(exc)) from exc
    resolved_render = str(policy_set.value("render_policy").value)
    if resolved_render not in _RENDER_POLICIES:
        raise ArtifactPolicyMeasurementError(f"unsupported render policy: {resolved_render}")
    resolved_validation = policy_set.value("validation_target").value
    render_policy = (
        dict(raw_render_policy)
        if raw_render_policy is not None
        else _legacy_render_policy(resolved_render, source)
    )
    return {
        "schema_version": RENDER_POLICY_CONTEXT_SCHEMA,
        "source": source,
        "validation_source": validation_source,
        "policy_set_sha256": policy_set.canonical_sha256(),
        "policy_set": policy_set.to_json(),
        "render_policy": render_policy,
        "validation_target": resolved_validation,
    }


def resolve_render_validation_policies(
    arguments: Mapping[str, Any],
    *,
    target_format: str,
) -> tuple[str, dict[str, Any]]:
    """Resolve separate validation/render policies for a render call site."""

    context = resolve_render_policy_context(arguments, target_format=target_format)
    return str(context["validation_target"] or ""), dict(context["render_policy"])


def _selected_render_policy(
    arguments: Mapping[str, Any],
    *,
    target_format: str | None,
    compatibility: bool,
) -> tuple[str, str, Mapping[str, Any] | None]:
    raw_render_policy = arguments.get("resolved_render_policy")
    if isinstance(raw_render_policy, Mapping):
        return _style_from_resolved_policy(raw_render_policy), "explicit-render-policy", raw_render_policy
    raw = arguments.get("style_policy")
    if not isinstance(raw, str) or not raw.strip():
        raw = target_format
    explicit = isinstance(raw, str) and bool(raw.strip())
    selected = str(raw).strip().lower() if explicit else "nature" if compatibility else "neutral"
    if selected not in _RENDER_POLICIES:
        raise ArtifactPolicyMeasurementError(f"unsupported render policy: {selected}")
    source = "explicit-render-policy" if explicit else "compatibility-default" if compatibility else "v2-default"
    return selected, source, None


def _selected_validation_target(
    arguments: Mapping[str, Any],
    *,
    target_format: str | None,
    compatibility: bool,
) -> tuple[str | None, str]:
    validation_target = str(arguments.get("validation_target") or "").strip().lower()
    source = "explicit-validation-target" if validation_target else "none"
    if not validation_target and compatibility:
        candidate = str(target_format or arguments.get("target_format") or "").strip().lower()
        try:
            get_preflight_spec(candidate)
        except ValueError:
            pass
        else:
            validation_target = candidate
            source = "compatibility-target-inference"
    if validation_target:
        get_preflight_spec(validation_target)
    return validation_target or None, source


def _style_from_resolved_policy(policy: Mapping[str, Any]) -> str:
    parameters = policy.get("parameters")
    raw = parameters.get("style_policy") if isinstance(parameters, Mapping) else None
    if not isinstance(raw, str) or not raw.strip():
        raw = parameters.get("render_policy") if isinstance(parameters, Mapping) else None
    if not isinstance(raw, str) or not raw.strip():
        raw = policy.get("id")
    selected = str(raw or "").strip().lower()
    if selected.startswith("render-"):
        selected = selected.removeprefix("render-")
    if selected not in _RENDER_POLICIES:
        raise ArtifactPolicyMeasurementError(f"unsupported render policy: {selected}")
    return selected


def _legacy_render_policy(selected: str, source: str) -> dict[str, Any]:
    return {
        "id": f"render-{selected}",
        "version": "1",
        "source": source,
        "parameters": {
            "style_policy": selected,
            "mutates_journal_aesthetics": selected != "neutral",
        },
    }


def measure_artifact_policy(
    artifact_path: str | Path,
    *,
    validation_target: str,
    artifact_sha256: str | None = None,
    render_policy: str = "neutral",
    geometry_measurements: Sequence[Mapping[str, Any]] | None = None,
    producer_binding: Mapping[str, Any] | None = None,
    validation_profile: str = "baseline",
) -> dict[str, Any]:
    """Measure existing bytes and return evidence measurements plus projection.

    The returned projection is deterministic for the artifact bytes, target,
    rule version, and measurement implementation/version.  It may therefore be
    regenerated by a verifier without trusting renderer-provided conclusions.
    """

    path = Path(artifact_path)
    if not path.is_file():
        raise ArtifactPolicyMeasurementError("artifact policy input must be an existing regular file")
    structurally_valid, structural_detail = verify_output_file(path)
    if not structurally_valid:
        raise ArtifactPolicyMeasurementError(f"artifact structure is invalid: {structural_detail}")
    digest = _file_sha256(path)
    if artifact_sha256 is not None:
        expected = str(artifact_sha256).strip().lower()
        if _SHA256.fullmatch(expected) is None or expected != digest:
            raise ArtifactPolicyMeasurementError("artifact SHA-256 does not match the measured bytes")

    target = str(validation_target or "").strip().lower()
    try:
        spec = get_preflight_spec(target)
    except ValueError as exc:
        raise ArtifactPolicyMeasurementError(str(exc)) from exc

    facts = _artifact_facts(path)
    measurements = _measurements(facts)
    canonical_geometry = _canonical_geometry_measurements(geometry_measurements)
    trusted_geometry = (
        canonical_geometry
        if _producer_binding_is_valid(producer_binding, artifact_sha256=digest)
        else None
    )
    results = [
        *_policy_results(facts, spec),
        *geometry_minimum_results(
            trusted_geometry,
            validation_target=target,
            profile=validation_profile,
        ),
    ]
    inputs = {
        "artifact_sha256": digest,
        "validation_target": target,
        "rule_version": RULE_VERSION,
        "measurement_implementation": MEASUREMENT_IMPLEMENTATION,
        "measurement_version": MEASUREMENT_VERSION,
        "validation_profile": str(validation_profile or "baseline").strip().lower(),
        "geometry_measurements_sha256": (
            _canonical_sha256(canonical_geometry) if geometry_measurements is not None else None
        ),
        "producer_binding_sha256": (
            _canonical_sha256(dict(producer_binding)) if producer_binding is not None else None
        ),
    }
    inputs_sha256 = _canonical_sha256(inputs)
    results_sha256 = _canonical_sha256(results)
    parameters = {
        **inputs,
        "inputs_sha256": inputs_sha256,
        "results_sha256": results_sha256,
        "render_policy": str(render_policy or "neutral").strip().lower(),
        "results": results,
    }
    policy_id = f"journal-{target}"
    source = "artifact-policy-verifier"
    projection = {
        "id": policy_id,
        "version": RULE_VERSION,
        "measurement_refs": [
            *[item["metric_id"] for item in measurements],
            *(
                ["style_geometry_observations"]
                if any(item.get("id") == "style_geometry_observations" for item in canonical_geometry)
                else []
            ),
        ],
        "resolved": {
            key: {"value": value, "source": source}
            for key, value in parameters.items()
        },
        "findings": _findings(results),
        "status": _projection_status(results),
    }
    return {
        "measurements": measurements,
        "resolved_policy": {
            "id": policy_id,
            "version": RULE_VERSION,
            "source": source,
            "parameters": parameters,
        },
        "policy_projection": projection,
    }


def verify_artifact_policy_projection(
    artifact_path: str | Path,
    *,
    resolved_policy: Mapping[str, Any],
    policy_projection: Mapping[str, Any],
    geometry_measurements: Sequence[Mapping[str, Any]] | None = None,
    producer_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute and return the canonical projection, rejecting any tampering."""

    parameters = resolved_policy.get("parameters")
    if not isinstance(parameters, Mapping):
        raise ArtifactPolicyMeasurementError("resolved policy parameters are missing")
    recomputed = measure_artifact_policy(
        artifact_path,
        validation_target=str(parameters.get("validation_target") or ""),
        artifact_sha256=str(parameters.get("artifact_sha256") or ""),
        render_policy=str(parameters.get("render_policy") or "neutral"),
        geometry_measurements=geometry_measurements,
        producer_binding=producer_binding,
        validation_profile=str(parameters.get("validation_profile") or "baseline"),
    )
    if _canonical_json(recomputed["resolved_policy"]) != _canonical_json(dict(resolved_policy)):
        raise ArtifactPolicyMeasurementError("resolved artifact policy binding does not recompute")
    if _canonical_json(recomputed["policy_projection"]) != _canonical_json(dict(policy_projection)):
        raise ArtifactPolicyMeasurementError("artifact policy projection does not recompute")
    return recomputed


def _artifact_facts(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    fmt = _FORMAT_ALIASES.get(suffix.lstrip("."), suffix.lstrip("."))
    facts: dict[str, Any] = {
        "format": fmt,
        "artifact_kind": "raster" if suffix in _RASTER_SUFFIXES else "vector",
        "pixel_width": None,
        "pixel_height": None,
        "dpi_x": None,
        "dpi_y": None,
        "physical_width_mm": None,
        "color_mode": None,
        "pdf_type3_fonts": None,
    }
    if suffix not in _RASTER_SUFFIXES:
        if suffix == ".pdf":
            try:
                pdf_bytes = path.read_bytes()
            except OSError as exc:
                raise ArtifactPolicyMeasurementError("PDF artifact could not be measured") from exc
            facts["physical_width_mm"] = _pdf_width_mm(pdf_bytes)
            facts["pdf_type3_fonts"] = b"/Subtype /Type3" in pdf_bytes or b"/Subtype/Type3" in pdf_bytes
        elif suffix == ".svg":
            facts["physical_width_mm"] = _svg_width_mm(path)
        elif suffix == ".eps":
            facts["physical_width_mm"] = _eps_width_mm(path)
        return facts
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            facts["pixel_width"] = int(image.width)
            facts["pixel_height"] = int(image.height)
            facts["color_mode"] = str(image.mode)
            raw_dpi = image.info.get("dpi")
            if isinstance(raw_dpi, (tuple, list)) and len(raw_dpi) == 2:
                dpi_x, dpi_y = float(raw_dpi[0]), float(raw_dpi[1])
                if dpi_x > 0 and dpi_y > 0:
                    facts["dpi_x"] = round(dpi_x, 6)
                    facts["dpi_y"] = round(dpi_y, 6)
                    facts["physical_width_mm"] = round(image.width / dpi_x * 25.4, 6)
    except Exception as exc:
        raise ArtifactPolicyMeasurementError("raster artifact could not be measured") from exc
    return facts


def _measurements(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    measurements = [
        _available("artifact.format", str(facts["format"]), "format"),
    ]
    if facts["pixel_width"] is None:
        reason = "not applicable to a vector artifact"
        measurements.extend(
            [
                _unavailable("artifact.pixel_width", "px", reason),
                _unavailable("artifact.pixel_height", "px", reason),
                _unavailable("artifact.raster_dpi", "dpi", reason),
                (
                    _available("artifact.physical_width", facts["physical_width_mm"], "mm")
                    if facts["physical_width_mm"] is not None
                    else _unavailable("artifact.physical_width", "mm", "vector physical width is unavailable")
                ),
                _unavailable("artifact.color_mode", "color-mode", reason),
            ]
        )
        if facts["pdf_type3_fonts"] is None:
            measurements.append(
                _unavailable(
                    "artifact.font_geometry",
                    "font-safety",
                    "PDF font-subtype inspection is not applicable to this artifact format",
                )
            )
        else:
            measurements.append(
                _available(
                    "artifact.font_geometry",
                    "type3-present" if facts["pdf_type3_fonts"] else "no-type3",
                    "font-safety",
                )
            )
        measurements.append(
            _unavailable(
                "artifact.text_geometry",
                "geometry",
                "text geometry is not reliably recoverable from the supported vector-byte inspection",
            )
        )
        return measurements
    measurements.extend(
        [
            _available("artifact.pixel_width", facts["pixel_width"], "px"),
            _available("artifact.pixel_height", facts["pixel_height"], "px"),
            _available("artifact.color_mode", facts["color_mode"], "color-mode"),
        ]
    )
    if facts["dpi_x"] is None:
        measurements.extend(
            [
                _unavailable("artifact.raster_dpi", "dpi", "DPI metadata is absent"),
                _unavailable("artifact.physical_width", "mm", "DPI metadata is absent"),
            ]
        )
    else:
        measurements.extend(
            [
                _available("artifact.raster_dpi", min(facts["dpi_x"], facts["dpi_y"]), "dpi"),
                _available("artifact.physical_width", facts["physical_width_mm"], "mm"),
            ]
        )
    measurements.extend(
        [
            _unavailable(
                "artifact.font_geometry",
                "font-safety",
                "font geometry is not recoverable from verified raster bytes",
            ),
            _unavailable(
                "artifact.text_geometry",
                "geometry",
                "text geometry is not recoverable from verified raster bytes",
            ),
        ]
    )
    return measurements


def _policy_results(facts: Mapping[str, Any], spec: Any) -> list[dict[str, Any]]:
    accepted = sorted(str(item) for item in spec.formats.value)
    fmt = str(facts["format"])
    results = [
        _result("format", "artifact.format", "pass" if fmt in accepted else "fail", fmt, accepted, required=True),
    ]
    dpi = min(facts["dpi_x"], facts["dpi_y"]) if facts["dpi_x"] is not None else None
    is_raster = facts["artifact_kind"] == "raster"
    results.append(
        _result(
            "dpi",
            "artifact.raster_dpi",
            (
                "not_applicable"
                if dpi is None
                else "pass"
                if dpi >= float(spec.min_dpi.value) - _DPI_METADATA_TOLERANCE
                else "fail"
            ),
            dpi,
            float(spec.min_dpi.value),
            (
                "DPI metadata is unavailable"
                if dpi is None and is_raster
                else "resolution-independent vector artifact"
                if dpi is None
                else None
            ),
            required=is_raster,
            comparison_tolerance=_DPI_METADATA_TOLERANCE if is_raster else None,
        )
    )
    width = facts["physical_width_mm"]
    results.append(
        _result(
            "physical_width",
            "artifact.physical_width",
            "not_applicable" if width is None else "pass" if width <= float(spec.max_width_mm.value) else "fail",
            width,
            float(spec.max_width_mm.value),
            "physical width cannot be derived from the artifact metadata" if width is None else None,
            required=True,
        )
    )
    mode = facts["color_mode"]
    results.append(
        _result(
            "color_mode",
            "artifact.color_mode",
            "not_applicable" if mode is None else "fail" if str(mode).upper() == "CMYK" else "pass",
            mode,
            "not CMYK",
            "color mode is not represented by this vector-byte measurement" if mode is None else None,
            required=is_raster,
        )
    )
    results.append(
        _result(
            "text_geometry",
            "artifact.text_geometry",
            "not_applicable",
            None,
            None,
            "text geometry has no artifact-only hard threshold in the encoded journal minima",
            required=False,
        )
    )
    type3 = facts["pdf_type3_fonts"]
    results.append(
        _result(
            "font_geometry",
            "artifact.font_geometry",
            "not_applicable" if type3 is None else "fail" if type3 else "pass",
            None if type3 is None else "type3-present" if type3 else "no-type3",
            "no Type3 PDF fonts" if type3 is not None else None,
            "PDF font-subtype inspection is not applicable to this artifact format" if type3 is None else None,
            required=type3 is not None,
        )
    )
    return results


def _result(
    check_id: str,
    metric_id: str,
    status: str,
    observed: Any,
    expected: Any,
    reason: str | None = None,
    *,
    required: bool,
    comparison_tolerance: float | None = None,
) -> dict[str, Any]:
    item = {
        "check_id": check_id,
        "metric_id": metric_id,
        "status": status,
        "observed": observed,
        "expected": expected,
        "enforcement": "required" if required else "informational",
    }
    if reason:
        item["reason"] = reason
    if comparison_tolerance is not None:
        item["comparison_tolerance"] = comparison_tolerance
    return item


def _findings(results: list[dict[str, Any]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for result in results:
        if result["status"] == "not_applicable":
            continue
        status = result["status"]
        severity = "hard" if status == "fail" else "informational"
        outcome = "blocked" if status == "fail" else "informational"
        message = f"{result['check_id']} measured {status} from the existing artifact."
        if result.get("reason"):
            message = f"{message} {result['reason']}"
        findings.append(
            {
                "code": f"ARTIFACT_{str(result['check_id']).upper()}_{status.upper()}",
                "metric_id": str(result["metric_id"]),
                "severity": severity,
                "outcome": outcome,
                "message": message,
            }
        )
    return findings


def _projection_status(results: list[dict[str, Any]]) -> str:
    statuses = {item["status"] for item in results if item["enforcement"] == "required"}
    if "fail" in statuses:
        return "blocked"
    if "not_applicable" in statuses:
        return "needs_review"
    return "informational"


def _producer_binding_is_valid(
    value: Mapping[str, Any] | None,
    *,
    artifact_sha256: str,
) -> bool:
    if not isinstance(value, Mapping) or set(value) != {"producer", "provenance"}:
        return False
    producer = value.get("producer")
    provenance = value.get("provenance")
    if not isinstance(producer, Mapping) or not isinstance(provenance, Mapping):
        return False
    if producer.get("status") != "passed" or provenance.get("status") != "passed":
        return False
    if str(provenance.get("output_sha256") or "").lower() != artifact_sha256:
        return False
    required_hashes = (
        "input_sha256",
        "config_sha256",
        "script_sha256",
        "environment_sha256",
        "output_sha256",
    )
    return all(_SHA256.fullmatch(str(provenance.get(key) or "").lower()) for key in required_hashes)


def _canonical_geometry_measurements(
    measurements: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    for item in measurements or ():
        identifier = str(item.get("id", item.get("metric_id")) or "")
        if identifier.startswith("artifact."):
            continue
        normalized = {
            "id": identifier,
            "availability": item.get("availability"),
            "unit": item.get("unit"),
            "scope": item.get("scope"),
        }
        if "value" in item:
            normalized["value"] = item["value"]
        if "reason" in item:
            normalized["reason"] = item["reason"]
        canonical.append(normalized)
    return canonical


_PDF_MEDIA_BOX_RE: Final = re.compile(
    rb"/MediaBox\s*\[\s*([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\s+"
    rb"([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\s*\]"
)
_EPS_BOUNDING_BOX_RE: Final = re.compile(
    rb"^%%BoundingBox:\s*([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\s+"
    rb"([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\s*$",
    re.MULTILINE,
)
_SVG_LENGTH_RE: Final = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(mm|cm|in|pt|px)?\s*$", re.IGNORECASE)


def _pdf_width_mm(data: bytes) -> float | None:
    match = _PDF_MEDIA_BOX_RE.search(data)
    if match is None:
        return None
    x0, _, x1, _ = (float(value) for value in match.groups())
    width_points = abs(x1 - x0)
    return round(width_points * 25.4 / 72.0, 6) if width_points > 0 else None


def _eps_width_mm(path: Path) -> float | None:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ArtifactPolicyMeasurementError("EPS artifact could not be measured") from exc
    match = _EPS_BOUNDING_BOX_RE.search(data)
    if match is None:
        return None
    x0, _, x1, _ = (float(value) for value in match.groups())
    width_points = abs(x1 - x0)
    return round(width_points * 25.4 / 72.0, 6) if width_points > 0 else None


def _svg_width_mm(path: Path) -> float | None:
    try:
        from xml.etree import ElementTree

        width = ElementTree.parse(path).getroot().attrib.get("width")
    except (ElementTree.ParseError, OSError) as exc:
        raise ArtifactPolicyMeasurementError("SVG artifact could not be measured") from exc
    match = _SVG_LENGTH_RE.fullmatch(str(width or ""))
    if match is None:
        return None
    magnitude = float(match.group(1))
    unit = (match.group(2) or "px").lower()
    factors = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72.0, "px": 25.4 / 96.0}
    return round(magnitude * factors[unit], 6) if magnitude > 0 else None


def _available(metric_id: str, value: Any, unit: str) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "availability": "available",
        "value": value,
        "unit": unit,
        "scope": "primary-artifact",
    }


def _unavailable(metric_id: str, unit: str, reason: str) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "availability": "not_applicable",
        "unit": unit,
        "scope": "primary-artifact",
        "reason": reason,
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


__all__ = [
    "ArtifactPolicyMeasurementError",
    "MEASUREMENT_IMPLEMENTATION",
    "MEASUREMENT_VERSION",
    "RULE_VERSION",
    "measure_artifact_policy",
    "resolve_render_policy_context",
    "resolve_render_policy_selection",
    "resolve_render_validation_policies",
    "verify_artifact_policy_projection",
]
