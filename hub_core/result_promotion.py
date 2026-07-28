"""Production integration for eligible runtime-rendered project results.

The detailed render manifest stays below the external runtime root.  Only the
verified figure bytes and a closed :class:`DurableReceipt` cross into declared
durable result roles.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, TypeAlias

from .artifact_policy_measurement import (
    ArtifactPolicyMeasurementError,
    verify_artifact_policy_projection,
)
from .claim_inventory import evaluate_project_claim_inventory
from .durable_promotion import PromotedArtifact, promote_result_with_receipt
from .durable_receipt import (
    DurableReceipt,
    opaque_artifact_id,
    opaque_claim_id,
    opaque_receipt_id,
)
from .human_review_receipt import calculate_subject_digest, opaque_figure_artifact_id, opaque_project_id
from .project_paths import project_path_has_symlink_component, resolve_project_output
from .project_structure_contract import resolve_project_structure
from .promotion_gate_receipt import validate_promotion_gate_receipt
from .promotion_gate_recording import (
    PromotionGateRecordingError,
    discard_promotion_gate_receipt,
    record_promotion_gate_receipt,
)


class ResultPromotionError(RuntimeError):
    """An eligible render could not be reduced to a safe durable result."""


PromotionGateReceiptInput: TypeAlias = Mapping[str, Any]
_DEFAULT_PROMOTION_GATE_DECISION_SCOPE = "figure_scientific_and_communication"


def _verify_promotion_gate_admission(
    promotion_gate_receipt: PromotionGateReceiptInput,
    *,
    primary_sha256: str,
    durable_receipt: DurableReceipt,
    expected_project_id: str,
    expected_artifact_id: str,
    decision_scope: str,
) -> dict[str, Any]:
    """Require a canonical eligible gate bound to this result's lineage.

    The evaluator's report is accepted as a convenience envelope when it
    contains ``receipt_candidate``; the receipt validator remains the sole
    authority for the closed gate schema and derived status.
    """

    if not isinstance(promotion_gate_receipt, Mapping):
        raise ResultPromotionError("promotion gate receipt/report must be a mapping")
    candidate: Mapping[str, Any] = promotion_gate_receipt
    report_status: object | None = None
    if "receipt_candidate" in promotion_gate_receipt:
        report_status = promotion_gate_receipt.get("gate_status")
        candidate_value = promotion_gate_receipt.get("receipt_candidate")
        if not isinstance(candidate_value, Mapping):
            raise ResultPromotionError("promotion gate report receipt_candidate is malformed")
        candidate = candidate_value
    try:
        validated = validate_promotion_gate_receipt(candidate)
    except (TypeError, ValueError) as exc:
        raise ResultPromotionError(f"promotion gate receipt is invalid: {exc}") from exc
    if report_status is not None and report_status != validated.get("gate_status"):
        raise ResultPromotionError("promotion gate report status does not match its receipt candidate")
    if "receipt_candidate" in promotion_gate_receipt and report_status != "eligible":
        raise ResultPromotionError("promotion gate report is not eligible")
    if validated.get("gate_status") != "eligible":
        raise ResultPromotionError("promotion gate receipt is not eligible")
    subject = validated.get("subject")
    if not isinstance(subject, Mapping):
        raise ResultPromotionError("eligible promotion gate receipt is missing its subject")
    if subject.get("project_id") != expected_project_id:
        raise ResultPromotionError("promotion gate subject does not bind the trusted project identity")
    if subject.get("artifact_id") != expected_artifact_id:
        raise ResultPromotionError("promotion gate subject does not bind the selected figure identity")
    if subject.get("artifact_sha256") != primary_sha256:
        raise ResultPromotionError("promotion gate subject does not bind the verified primary artifact")
    subject_payload = {key: value for key, value in subject.items() if key != "subject_digest"}
    try:
        expected_subject_digest = calculate_subject_digest(
            subject_payload,
            decision_scope,
        )
    except (TypeError, ValueError) as exc:
        raise ResultPromotionError("promotion gate subject digest is malformed") from exc
    if subject.get("subject_digest") != expected_subject_digest:
        raise ResultPromotionError("promotion gate subject digest does not match its subject")
    expected_lineage_sha = durable_receipt.canonical_sha256()
    if subject.get("lineage_receipt_sha256") != expected_lineage_sha:
        raise ResultPromotionError("promotion gate subject does not bind the durable lineage receipt")
    return validated


def _sha256_text(value: object) -> str:
    text = str(value or "unavailable")
    if len(text) == 64:
        try:
            int(text, 16)
        except ValueError:
            pass
        else:
            return text.lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _primary_artifact(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    evidence = manifest.get("evidence")
    artifacts = evidence.get("artifacts") if isinstance(evidence, Mapping) else None
    entries = artifacts.get("entries") if isinstance(artifacts, Mapping) else None
    primary = [item for item in entries or [] if isinstance(item, Mapping) and item.get("logical_role") == "primary"]
    if len(primary) != 1:
        raise ResultPromotionError("eligible render requires exactly one verified primary artifact")
    digest = primary[0].get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ResultPromotionError("eligible render primary artifact is missing its SHA-256")
    return primary[0]


def _claim_bindings(manifest: Mapping[str, Any], figure_key: str) -> tuple[list[dict[str, str]], list[str]]:
    inventory = manifest.get("claim_inventory")
    claims = inventory.get("claims") if isinstance(inventory, Mapping) else None
    dependencies: dict[str, dict[str, str]] = {}
    claim_ids: list[str] = []
    for claim in claims or []:
        if not isinstance(claim, Mapping):
            continue
        claim_id = claim.get("claim_id")
        if isinstance(claim_id, str) and claim_id.strip():
            claim_ids.append(claim_id.strip())
        for dependency in claim.get("dependencies") or []:
            if not isinstance(dependency, Mapping):
                continue
            artifact_id = dependency.get("artifact_id")
            role = dependency.get("role")
            digest = dependency.get("sha256")
            if all(isinstance(value, str) and value for value in (artifact_id, role, digest)):
                dependencies[str(artifact_id)] = {
                    "artifact_id": str(artifact_id),
                    "role": str(role),
                    "sha256": str(digest),
                }
    if not claim_ids:
        claim_ids = [f"figure:{figure_key}:explicit-no-claims"]
    return list(dependencies.values()), claim_ids


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verified_manifest_bytes(
    manifest: Mapping[str, Any], manifest_path: str | Path, *, max_bytes: int = 16 * 1024 * 1024
) -> bytes:
    try:
        raw = Path(manifest_path).read_bytes()
    except OSError as exc:
        raise ResultPromotionError("runtime manifest is missing or unreadable at promotion") from exc
    if not raw or len(raw) > max_bytes:
        raise ResultPromotionError("runtime manifest exceeds its bounded promotion contract")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        loaded_object: dict[str, Any] = {}
        for key, value in pairs:
            if key in loaded_object:
                raise ValueError(f"duplicate manifest key: {key}")
            loaded_object[key] = value
        return loaded_object

    try:
        loaded = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ResultPromotionError("runtime manifest is not valid UTF-8 JSON") from exc
    if not isinstance(loaded, Mapping) or _canonical(loaded) != _canonical(manifest):
        raise ResultPromotionError("inspected manifest does not match the persisted runtime manifest")
    return raw


def _verify_policy_gate(
    runtime_artifact: str | Path,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, str]:
    evidence = manifest.get("evidence")
    resolved_policy = evidence.get("resolved_policy") if isinstance(evidence, Mapping) else None
    projections = evidence.get("policy_projections") if isinstance(evidence, Mapping) else None
    if not isinstance(resolved_policy, Mapping) or not isinstance(projections, list) or len(projections) != 1:
        raise ResultPromotionError("eligible render requires one recomputable publication policy projection")
    projection = projections[0]
    if not isinstance(projection, Mapping):
        raise ResultPromotionError("eligible render publication policy projection is malformed")
    measurements = evidence.get("measurements")
    producer = evidence.get("producer")
    provenance = evidence.get("provenance")
    if not isinstance(measurements, list) or not isinstance(producer, Mapping) or not isinstance(provenance, Mapping):
        raise ResultPromotionError("eligible render policy evidence is missing producer-bound geometry")
    try:
        recomputed = verify_artifact_policy_projection(
            runtime_artifact,
            resolved_policy=resolved_policy,
            policy_projection=projection,
            geometry_measurements=measurements,
            producer_binding={"producer": producer, "provenance": provenance},
        )
    except ArtifactPolicyMeasurementError as exc:
        raise ResultPromotionError(f"publication policy projection failed recomputation: {exc}") from exc
    if recomputed["policy_projection"].get("status") != "informational":
        raise ResultPromotionError("publication policy has unmet required or review-only outcomes")
    visual_style = config.get("visual_style")
    configured_target = (
        str(visual_style.get("validation_target") or "").strip().lower()
        if isinstance(visual_style, Mapping)
        else ""
    )
    parameters = resolved_policy.get("parameters")
    measured_target = (
        str(parameters.get("validation_target") or "").strip().lower()
        if isinstance(parameters, Mapping)
        else ""
    )
    expected_profile = f"journal-{configured_target}" if configured_target else ""
    if not configured_target or measured_target != configured_target or resolved_policy.get("id") != expected_profile:
        raise ResultPromotionError(
            "publication policy projection must match the trusted project validation target"
        )
    style_summary = manifest.get("style_summary")
    if not isinstance(style_summary, Mapping) or style_summary.get("validation_target") != configured_target:
        raise ResultPromotionError("runtime manifest policy target disagrees with the trusted project config")
    resolved = projection.get("resolved")
    results_sha = resolved.get("results_sha256") if isinstance(resolved, Mapping) else None
    outcomes_sha256 = results_sha.get("value") if isinstance(results_sha, Mapping) else None
    if not isinstance(outcomes_sha256, str):
        raise ResultPromotionError("publication policy outcomes digest is missing")
    return {
        "profile_id": expected_profile,
        "rule_version": str(resolved_policy.get("version") or ""),
        "measurement_version": str(parameters.get("measurement_version") or ""),
        "outcomes_sha256": outcomes_sha256,
    }


def _verify_claim_gate(
    *,
    runtime_artifact: str | Path,
    output_relpath: str,
    selected_figure: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    nested = manifest.get("claim_inventory")
    if not isinstance(nested, Mapping):
        raise ResultPromotionError("eligible render is missing its structured claim inventory")
    if (
        nested.get("status") != "verified"
        or nested.get("promotion_eligible") is not True
        or nested.get("manual_review_needed") is not False
        or nested.get("errors") not in ([], ())
    ):
        raise ResultPromotionError("nested claim inventory is not verified for promotion")
    runtime_path = Path(runtime_artifact).resolve(strict=True)
    output_parts = PurePosixPath(output_relpath.replace("\\", "/")).parts
    snapshot_root = runtime_path
    for _part in output_parts:
        snapshot_root = snapshot_root.parent
    verified = evaluate_project_claim_inventory(snapshot_root, dict(selected_figure))
    if _canonical(verified) != _canonical(nested):
        raise ResultPromotionError("claim inventory does not recompute from the runtime snapshot")
    claims = verified.get("claims")
    if not isinstance(claims, list):
        raise ResultPromotionError("verified claim inventory claims are malformed")
    if not claims and verified.get("explicit_no_claims") is not True:
        raise ResultPromotionError("empty claim inventory lacks an explicit no-claims declaration")
    return verified


def _is_promotion_eligible(manifest: Mapping[str, Any]) -> bool:
    return bool(
        manifest.get("promotion_eligible") is True
        and manifest.get("publication_status") == "verified"
        and manifest.get("manual_review_needed") is False
    )


def promote_eligible_project_result(
    *,
    project_root: str | Path,
    config: Mapping[str, Any],
    runtime_root: str | Path,
    runtime_artifact: str | Path,
    output_relpath: str,
    manifest: Mapping[str, Any],
    manifest_path: str | Path,
    figure_id: str,
    selected_figure: Mapping[str, Any],
    promotion_gate_receipt: PromotionGateReceiptInput | None = None,
    promotion_gate_decision_scope: str = _DEFAULT_PROMOTION_GATE_DECISION_SCOPE,
) -> tuple[PromotedArtifact, PromotedArtifact] | None:
    """Promote one fully verified project render, or return ``None`` when gated.

    ``promotion_gate_receipt`` is an optional canonical receipt (or evaluator
    report containing ``receipt_candidate``); when supplied, admission is
    bound to the primary artifact and the durable receipt constructed here.
    ``promotion_gate_decision_scope`` is required when the evaluator used a
    non-default decision scope because the frozen gate receipt omits that field.
    """

    if not _is_promotion_eligible(manifest):
        return None
    contract = resolve_project_structure(config, project_root=project_root)
    output = PurePosixPath(output_relpath.replace("\\", "/"))
    figure_root = PurePosixPath(contract.roots["figures"])
    if output == figure_root or not output.is_relative_to(figure_root):
        raise ResultPromotionError("eligible render output must be declared below result.figure")
    if project_path_has_symlink_component(project_root, output.as_posix(), purpose="durable figure output"):
        raise ResultPromotionError("durable figure output must not traverse a symlink or reparse point")
    destination = resolve_project_output(
        project_root,
        output.as_posix(),
        purpose="durable figure output",
    )

    manifest_bytes = _verified_manifest_bytes(manifest, manifest_path)
    primary = _primary_artifact(manifest)
    publication_policy = _verify_policy_gate(runtime_artifact, manifest, config)
    verified_claims = _verify_claim_gate(
        runtime_artifact=runtime_artifact,
        output_relpath=output_relpath,
        selected_figure=selected_figure,
        manifest=manifest,
    )
    producer = manifest.get("provenance")
    if not isinstance(producer, Mapping):
        raise ResultPromotionError("eligible render is missing producer provenance")
    figure_key = hashlib.sha256(str(figure_id).encode("utf-8")).hexdigest()[:20]
    artifact_id = opaque_artifact_id("result.figure", f"figure:{figure_key}")
    output_binding = {
        "artifact_id": artifact_id,
        "role": "result.figure",
        "sha256": str(primary["sha256"]).lower(),
    }
    claim_bound_manifest = {**manifest, "claim_inventory": verified_claims}
    input_bindings, claim_ids = _claim_bindings(claim_bound_manifest, figure_key)
    if not input_bindings:
        input_bindings = [
            {
                "artifact_id": f"raw:{figure_key}:input-set",
                "role": "raw",
                "sha256": str(producer.get("input_sha256") or "").lower(),
            }
        ]

    receipt = DurableReceipt(
        figops_version=str(producer.get("mcp_surface_version") or "unknown"),
        run_id=opaque_receipt_id(
            "run", manifest.get("job_id") or producer.get("job_id") or "unknown"
        ),
        timestamp=str(producer.get("timestamp_utc") or "unknown"),
        git_sha256=_sha256_text(producer.get("hub_git_commit")),
        config_sha256=str(producer.get("config_sha256") or "").lower(),
        script_sha256=str(producer.get("script_sha256") or "").lower(),
        environment_lock_sha256=str(producer.get("environment_sha256") or "").lower(),
        durable_artifact=output_binding,
        input_artifacts=[
            {
                **binding,
                "artifact_id": opaque_artifact_id(binding["role"], binding["artifact_id"]),
            }
            for binding in input_bindings
        ],
        output_artifacts=[output_binding],
        claim_ids=[opaque_claim_id(claim_id) for claim_id in claim_ids],
        manifest_id=opaque_receipt_id(
            "manifest", manifest.get("job_id") or producer.get("job_id") or "unknown"
        ),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        publication_policy=publication_policy,
    )
    validated_gate_receipt: dict[str, Any] | None = None
    if promotion_gate_receipt is not None:
        project_config = config.get("project") if isinstance(config, Mapping) else None
        project_name = project_config.get("name") if isinstance(project_config, Mapping) else None
        if not isinstance(project_name, str) or not project_name.strip():
            raise ResultPromotionError("promotion gate requires a trusted project.name identity")
        try:
            expected_project_id = opaque_project_id(project_name)
            expected_artifact_id = opaque_figure_artifact_id(str(figure_id))
        except (TypeError, ValueError) as exc:
            raise ResultPromotionError("promotion gate subject identities are malformed") from exc
        validated_gate_receipt = _verify_promotion_gate_admission(
            promotion_gate_receipt,
            primary_sha256=str(primary["sha256"]).lower(),
            durable_receipt=receipt,
            expected_project_id=expected_project_id,
            expected_artifact_id=expected_artifact_id,
            decision_scope=promotion_gate_decision_scope,
        )

    evidence_root = PurePosixPath(contract.roots["evidence"])
    receipt_relpath = evidence_root / f"figure-{figure_key}.receipt.json"
    if project_path_has_symlink_component(
        project_root,
        receipt_relpath.as_posix(),
        purpose="durable result receipt",
    ):
        raise ResultPromotionError("durable result receipt must not traverse a symlink or reparse point")
    receipt_destination = resolve_project_output(
        project_root,
        receipt_relpath.as_posix(),
        purpose="durable result receipt",
    )
    gate_relpath = evidence_root / f"figure-{figure_key}.promotion-gate.json"
    if validated_gate_receipt is not None:
        try:
            frozen_gate = record_promotion_gate_receipt(
                validated_gate_receipt,
                evidence_root=Path(project_root) / evidence_root,
                relative_path=gate_relpath.relative_to(evidence_root).as_posix(),
            )
        except Exception as exc:
            raise ResultPromotionError(
                f"promotion gate receipt could not be frozen: {exc}"
            ) from exc
    else:
        frozen_gate = None
    try:
        promoted = promote_result_with_receipt(
            runtime_artifact,
            destination,
            receipt,
            receipt_destination,
            runtime_root=runtime_root,
        )
    except Exception as exc:
        if frozen_gate is not None:
            try:
                discard_promotion_gate_receipt(
                    frozen_gate,
                    evidence_root=Path(project_root) / evidence_root,
                )
            except PromotionGateRecordingError as cleanup_exc:
                raise ResultPromotionError(
                    "promotion failed and promotion-gate receipt rollback was withheld: "
                    f"{cleanup_exc}"
                ) from exc
        raise
    return promoted


__all__ = [
    "PromotionGateReceiptInput",
    "ResultPromotionError",
    "promote_eligible_project_result",
]
