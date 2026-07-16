"""Structured, fail-closed claim inventory for project-script publication renders."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .adapters import select_adapters
from .calculation_evidence import verify_calculation_evidence_bundle
from .claim_script_inspection import analyze_claim_script
from .project_paths import (
    normalize_project_relative_path,
    open_verified_project_input,
    project_path_has_symlink_component,
    resolve_project_input,
    snapshot_project_input,
)

SCHEMA_VERSION = "figops_claim_inventory/1"
MAX_INVENTORY_BYTES = 256 * 1024
MAX_SCRIPT_INSPECTION_BYTES = 1024 * 1024
MAX_CLAIMS = 128
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_P_CLAIM_RE = re.compile(
    r"\bp\s*(?:<=|<|=|≤)\s*[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?\b",
    re.IGNORECASE,
)
_STAR_CLAIM_RE = re.compile(r"(?<!\*)\*{1,4}(?!\*)")
_DEPENDENCY_ROLES = {"result.source_data", "result.table"}


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("claim inventory JSON contains duplicate object keys")
        result[key] = value
    return result


def _text(value: Any, name: str, *, limit: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"claim inventory requires non-empty {name}")
    if len(value) > limit:
        raise ValueError(f"claim inventory {name} exceeds {limit} characters")
    return value.strip()


def _read_project_bytes(root: str | Path, declared: str, *, purpose: str, limit: int) -> bytes:
    normalized = normalize_project_relative_path(declared, purpose=purpose)
    if project_path_has_symlink_component(root, normalized, purpose=purpose):
        raise ValueError(f"{purpose} must not traverse a symlink, junction, or reparse point")
    resolved = resolve_project_input(root, normalized, purpose=purpose)
    select_adapters({}).prefetcher.ensure_local([str(resolved)])
    snapshot = snapshot_project_input(root, normalized, purpose=purpose)
    with open_verified_project_input(root, normalized, expected_snapshot=snapshot, purpose=purpose) as handle:
        payload = handle.read(limit + 1)
    if len(payload) > limit:
        raise ValueError(f"{purpose} exceeds its bounded inspection limit")
    return payload


def inspect_script_claim_candidates(root: str | Path, script_path: str, configured_claim: Any = None) -> dict[str, Any]:
    """Conservatively discover displayed claim-like text; this never verifies a claim."""

    normalized = normalize_project_relative_path(script_path, purpose="project figure script")
    try:
        raw = _read_project_bytes(
            root,
            normalized,
            purpose="project figure script claim inspection",
            limit=MAX_SCRIPT_INSPECTION_BYTES,
        )
        script_text = raw.decode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        return {
            "inspectable": False,
            "candidates": [],
            "dynamic_candidates": [],
            "reason": str(exc),
        }
    literals, inspectable, dynamic_candidates = analyze_claim_script(
        script_text, Path(normalized).suffix.lower()
    )
    if not inspectable:
        return {
            "inspectable": False,
            "candidates": [],
            "dynamic_candidates": [],
            "reason": "script syntax or runtime is uninspectable",
        }
    candidates: list[dict[str, str]] = []
    if isinstance(configured_claim, str) and configured_claim.strip():
        candidates.append({"source": "figures[].claim", "text": configured_claim.strip()})
    for literal in literals:
        for match in _P_CLAIM_RE.finditer(literal):
            candidates.append({"source": "script_literal", "text": match.group(0)})
        compact = literal.strip()
        if _STAR_CLAIM_RE.fullmatch(compact):
            candidates.append({"source": "script_literal", "text": compact})
    unique = list({(item["source"], item["text"]): item for item in candidates}.values())
    return {
        "inspectable": True,
        "candidates": unique,
        "dynamic_candidates": dynamic_candidates,
        "reason": "",
    }


def _dependency(value: Any, name: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"artifact_id", "role", "sha256"}:
        raise ValueError(f"claim inventory {name} must contain artifact_id, role, and sha256 only")
    role = _text(value.get("role"), f"{name}.role")
    if role not in _DEPENDENCY_ROLES:
        raise ValueError(f"claim inventory {name}.role must be result.source_data or result.table")
    sha256 = _text(value.get("sha256"), f"{name}.sha256", limit=64)
    if not _SHA256_RE.fullmatch(sha256):
        raise ValueError(f"claim inventory {name}.sha256 must be a lowercase SHA-256")
    return {"artifact_id": _text(value.get("artifact_id"), f"{name}.artifact_id"), "role": role, "sha256": sha256}


def verify_claim_inventory(
    root: str | Path,
    inventory_path: str,
    *,
    figure_id: str,
    discovered_candidates: list[dict[str, str]],
) -> dict[str, Any]:
    """Verify a structured inventory and every calculation/dependency edge."""

    normalized_path = normalize_project_relative_path(inventory_path, purpose="claim inventory")
    raw = _read_project_bytes(root, normalized_path, purpose="claim inventory", limit=MAX_INVENTORY_BYTES)
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"claim inventory must contain valid closed UTF-8 JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"claim inventory must use schema_version {SCHEMA_VERSION!r}")
    if set(payload) != {"schema_version", "figure_id", "calculation_evidence_paths", "claims"}:
        raise ValueError("claim inventory must be a closed structured document")
    if _text(payload.get("figure_id"), "figure_id") != figure_id:
        raise ValueError("claim inventory figure_id does not match the selected figure")
    evidence_paths = payload.get("calculation_evidence_paths")
    if not isinstance(evidence_paths, list) or any(not isinstance(path, str) for path in evidence_paths):
        raise ValueError("claim inventory calculation_evidence_paths must be an array of project-relative paths")
    evidence = verify_calculation_evidence_bundle(root, evidence_paths) if evidence_paths else []
    by_claim_id: dict[str, dict[str, Any]] = {}
    for record in evidence:
        if record.get("verification_status") != "verified":
            raise ValueError("claim inventory references unverified calculation evidence")
        for claim_id in record.get("claim_ids", []):
            if claim_id in by_claim_id:
                raise ValueError("claim inventory calculation evidence has duplicate claim bindings")
            by_claim_id[claim_id] = record

    claims = payload.get("claims")
    if not isinstance(claims, list) or len(claims) > MAX_CLAIMS:
        raise ValueError(f"claim inventory claims must be an array of at most {MAX_CLAIMS} entries")
    normalized_claims: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or set(claim) != {
            "claim_id",
            "kind",
            "displayed_text",
            "displayed_region",
            "calculation_artifact_id",
            "dependencies",
        }:
            raise ValueError(f"claim inventory claims[{index}] must use the closed claim shape")
        claim_id = _text(claim.get("claim_id"), f"claims[{index}].claim_id")
        if claim_id in seen_ids:
            raise ValueError("claim inventory contains duplicate claim IDs")
        seen_ids.add(claim_id)
        record = by_claim_id.get(claim_id)
        if record is None:
            raise ValueError(f"claim inventory claim {claim_id!r} lacks verified calculation evidence")
        dependencies_value = claim.get("dependencies")
        if not isinstance(dependencies_value, list) or not dependencies_value:
            raise ValueError(f"claim inventory claim {claim_id!r} requires source-data/table dependencies")
        dependencies = [
            _dependency(value, f"claims[{index}].dependencies[{dep_index}]")
            for dep_index, value in enumerate(dependencies_value)
        ]
        lineage = [
            {key: item.get(key) for key in ("artifact_id", "role", "sha256")}
            for item in [*record.get("input_artifacts", []), *record.get("output_artifacts", [])]
        ]
        if any(dependency not in lineage for dependency in dependencies):
            raise ValueError(f"claim inventory claim {claim_id!r} has an unverifiable dependency edge")
        artifact_id = _text(claim.get("calculation_artifact_id"), f"claims[{index}].calculation_artifact_id")
        if artifact_id != record.get("calculation_artifact_id"):
            raise ValueError(f"claim inventory claim {claim_id!r} cites the wrong calculation artifact")
        normalized_claims.append(
            {
                "claim_id": claim_id,
                "kind": _text(claim.get("kind"), f"claims[{index}].kind"),
                "displayed_text": _text(claim.get("displayed_text"), f"claims[{index}].displayed_text"),
                "displayed_region": _text(claim.get("displayed_region"), f"claims[{index}].displayed_region"),
                "calculation_artifact_id": artifact_id,
                "dependencies": dependencies,
                "calculation_artifact_sha256": record["analysis_artifact_sha256"],
                "durable_receipt_sha256": record["durable_receipt_sha256"],
            }
        )
    declared_text = {claim["displayed_text"] for claim in normalized_claims}
    undeclared = [candidate for candidate in discovered_candidates if candidate["text"] not in declared_text]
    if undeclared:
        raise ValueError("claim inventory does not declare every conservatively detected claim candidate")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "verified",
        "figure_id": figure_id,
        "artifact_ref": normalized_path,
        "explicit_no_claims": not normalized_claims,
        "claims": normalized_claims,
        "discovered_candidates": discovered_candidates,
        "manual_review_needed": False,
        "promotion_eligible": True,
        "errors": [],
    }


def evaluate_project_claim_inventory(root: str | Path, selected_figure: dict[str, Any]) -> dict[str, Any]:
    """Return a publication decision without allowing missing/uninspectable evidence to pass."""

    figure_id = str(selected_figure.get("id") or "").strip()
    script_path = str(selected_figure.get("script") or "").split("::", 1)[0]
    inspection = inspect_script_claim_candidates(root, script_path, selected_figure.get("claim"))
    inventory_path = selected_figure.get("claim_inventory")
    errors: list[str] = []
    if not inspection["inspectable"]:
        errors.append(f"project figure script is uninspectable: {inspection['reason']}")
    if inspection.get("dynamic_candidates"):
        errors.append(
            "project figure script contains dynamic statistical-claim annotation text; "
            "publication promotion requires manual review"
        )
    if not isinstance(inventory_path, str) or not inventory_path.strip():
        errors.append(
            "publication project-script render requires a structured claim inventory, "
            "including explicit no-claims"
        )
    if not errors:
        try:
            verified = verify_claim_inventory(
                root,
                inventory_path,
                figure_id=figure_id,
                discovered_candidates=inspection["candidates"],
            )
            verified["dynamic_candidates"] = []
            return verified
        except (FileNotFoundError, OSError, ValueError) as exc:
            errors.append(str(exc))
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "unverified",
        "figure_id": figure_id,
        "artifact_ref": "",
        "explicit_no_claims": False,
        "claims": [],
        "discovered_candidates": inspection["candidates"],
        "dynamic_candidates": inspection.get("dynamic_candidates", []),
        "manual_review_needed": True,
        "promotion_eligible": False,
        "errors": errors,
    }


__all__ = [
    "SCHEMA_VERSION",
    "evaluate_project_claim_inventory",
    "inspect_script_claim_candidates",
    "verify_claim_inventory",
]
