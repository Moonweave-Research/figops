from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pytest
from PIL import Image

from hub_core.artifact_audit import audit_artifact_evidence
from hub_core.artifact_policy_measurement import (
    MEASUREMENT_IMPLEMENTATION,
    MEASUREMENT_VERSION,
    RULE_VERSION,
    ArtifactPolicyMeasurementError,
    measure_artifact_policy,
    resolve_render_policy_context,
    resolve_render_policy_selection,
    resolve_render_validation_policies,
    verify_artifact_policy_projection,
)
from hub_core.evidence_contract import EvidenceContractError, validate_evidence_envelope
from hub_core.mcp.render_geometry import _geometry_stub
from hub_core.mcp.render_orchestration import _build_preview_artifacts, _preview_resource_references
from hub_core.mcp.render_response import audit_response, one_render_response
from hub_core.render_evidence import build_render_evidence


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(job_id: str, previews: list[dict], output_sha256: str) -> dict:
    return {
        "job_id": job_id,
        "preview_artifacts": previews,
        "geometry_diagnostics": _geometry_stub("geometry sidecar unavailable in fixture"),
        "provenance": {
            "input_sha256": "1" * 64,
            "config_sha256": "2" * 64,
            "script_sha256": "3" * 64,
            "environment_sha256": "4" * 64,
            "output_sha256": output_sha256,
        },
        "data_contract": {"passed": True},
        "calculation_checks": {"checks": []},
        "baseline_comparison": {"checked": False},
    }


def _pdf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n")
    return path


def test_pdf_primary_keeps_integrity_and_png_companion_dimensions_in_evidence(tmp_path: Path) -> None:
    job_root = tmp_path / "job"
    primary = _pdf(job_root / "results" / "figure.pdf")
    companion = job_root / "results" / "figure.png"
    Image.new("RGB", (23, 17), "navy").save(companion, format="PNG")
    previews = _build_preview_artifacts(
        job_root=job_root,
        output_path=primary,
        figures=[{"path": str(companion)}, {"path": str(primary)}],
    )
    manifest = _manifest("pdf-companion", previews, _sha256(primary))

    evidence = build_render_evidence(
        manifest,
        job_root=job_root,
        producer_kind="test-vector-render",
        producer_version="1",
    )

    validate_evidence_envelope(evidence)
    assert evidence["artifacts"]["status"] == "passed"
    assert [entry["logical_role"] for entry in evidence["artifacts"]["entries"]] == [
        "primary",
        "companion:png",
    ]
    pdf_entry, png_entry = evidence["artifacts"]["entries"]
    assert pdf_entry["availability"] == "available"
    assert pdf_entry["header_valid"] is True
    assert pdf_entry["sha256"] == _sha256(primary) == evidence["provenance"]["output_sha256"]
    assert pdf_entry["dimension_availability"] == "unavailable"
    assert not ({"width", "height", "dimensions_valid"} & set(pdf_entry))
    assert png_entry["dimension_availability"] == "available"
    assert (png_entry["width"], png_entry["height"]) == (23, 17)
    assert png_entry["sha256"] == _sha256(companion)

    references = _preview_resource_references("pdf-companion", previews)
    response = one_render_response(
        "figops.render_project_script",
        {
            "status": "ok",
            "job_id": "pdf-companion",
            "summary": "rendered",
            "evidence": evidence,
            "preview_resources": references["preview_resources"],
        },
    )
    assert response["artifact"]["media_type"] == "application/pdf"
    assert response["artifact"]["sha256"] == _sha256(primary)
    assert response["artifact"]["dimension_availability"] == "unavailable"
    assert response["preview_uri"].endswith("/companion%3Apng/1")
    audit_report = audit_artifact_evidence(evidence)
    assert "ARTIFACT_PIXEL_DIMENSIONS_UNAVAILABLE" in {
        finding["code"] for finding in audit_report["findings"]
    }
    assert audit_report["summary"]["finding_counts"]["hard"] == 0
    audited = audit_response(
        job_id="pdf-companion",
        evidence=evidence,
        report=audit_report,
        preview_entries=previews,
    )
    assert audited["artifact"]["sha256"] == _sha256(primary)
    assert audited["preview_uri"] == response["preview_uri"]


@pytest.mark.parametrize(
    ("suffix", "payload", "media_type"),
    [
        ("pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf"),
        ("svg", b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"></svg>', "image/svg+xml"),
    ],
)
def test_vector_only_render_keeps_verified_artifact_with_typed_dimensions(
    tmp_path: Path,
    suffix: str,
    payload: bytes,
    media_type: str,
) -> None:
    job_root = tmp_path / "job"
    primary = job_root / "results" / f"figure.{suffix}"
    primary.parent.mkdir(parents=True, exist_ok=True)
    primary.write_bytes(payload)
    previews = _build_preview_artifacts(
        job_root=job_root,
        output_path=primary,
        figures=[{"path": str(primary)}],
    )
    job_id = f"{suffix}-only"
    manifest = _manifest(job_id, previews, _sha256(primary))
    evidence = build_render_evidence(
        manifest,
        job_root=job_root,
        producer_kind="test-vector-render",
        producer_version="1",
    )
    references = _preview_resource_references(job_id, previews)

    response = one_render_response(
        "figops.render_project_script",
        {
            "status": "ok",
            "job_id": job_id,
            "evidence": evidence,
            "preview_resources": references["preview_resources"],
        },
    )

    assert response["artifact"] is not None
    assert response["artifact"]["media_type"] == media_type
    assert response["artifact"]["sha256"] == evidence["provenance"]["output_sha256"]
    assert response["artifact"]["dimension_availability"] == "unavailable"
    assert response["preview_uri"].endswith("/primary/0")


def test_primary_output_hash_mismatch_still_fails_closed_for_vector_render(tmp_path: Path) -> None:
    job_root = tmp_path / "job"
    primary = _pdf(job_root / "results" / "figure.pdf")
    previews = _build_preview_artifacts(
        job_root=job_root,
        output_path=primary,
        figures=[{"path": str(primary)}],
    )
    manifest = _manifest("pdf-mismatch", previews, "f" * 64)

    with pytest.raises(EvidenceContractError) as raised:
        build_render_evidence(
            manifest,
            job_root=job_root,
            producer_kind="test-vector-render",
            producer_version="1",
        )

    assert raised.value.code == "PRIMARY_OUTPUT_HASH_CONFLICT"


def test_policy_context_preserves_neutral_v2_and_nature_compatibility_split() -> None:
    v2 = resolve_render_policy_context({}, compatibility=False)
    compatibility = resolve_render_policy_context({}, compatibility=True)

    assert v2["render_policy"]["id"] == "render-neutral"
    assert v2["render_policy"]["source"] == "v2-default"
    assert v2["validation_target"] is None
    assert compatibility["render_policy"]["id"] == "render-nature"
    assert compatibility["render_policy"]["source"] == "compatibility-default"
    assert compatibility["validation_target"] is None

    inferred_target, inferred_policy = resolve_render_validation_policies({}, target_format="nature")
    v2_target, v2_policy = resolve_render_validation_policies(
        {"v2_policy_contract": True},
        target_format="nature",
    )
    assert (inferred_target, inferred_policy["id"]) == ("nature", "render-nature")
    assert (v2_target, v2_policy["id"]) == ("", "render-nature")


def test_explicit_render_policy_wins_over_compatibility_target_projection() -> None:
    explicit = {
        "id": "render-science",
        "version": "1",
        "source": "explicit-render-policy",
        "parameters": {"style_policy": "science", "mutates_journal_aesthetics": True},
    }
    context = resolve_render_policy_context(
        {"resolved_render_policy": explicit},
        target_format="nature",
        compatibility=True,
    )

    assert context["render_policy"] == explicit
    assert context["validation_target"] == "nature"
    assert context["policy_set"]["parameters"]["render_policy"]["value"] == "science"
    assert context["policy_set"]["parameters"]["validation_target"]["value"] == "nature"


def test_policy_context_records_source_opt_out_provenance_and_canonical_digest() -> None:
    layer = {
        "source": "project",
        "policy_id": "project-research-ops",
        "version": "1",
        "parameters": {"require_figure_traceability": {"opt_out": True}},
    }

    left = resolve_render_policy_context({}, compatibility=False, policy_layers=[layer])
    reordered_layer = {
        "parameters": layer["parameters"],
        "version": layer["version"],
        "policy_id": layer["policy_id"],
        "source": layer["source"],
    }
    right = resolve_render_policy_context({}, compatibility=False, policy_layers=[reordered_layer])
    traceability = left["policy_set"]["parameters"]["require_figure_traceability"]
    canonical_digest = hashlib.sha256(
        json.dumps(
            left["policy_set"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()

    assert left["source"] == "v2-default"
    assert traceability["source"] == "explicit_project_opt_out"
    assert traceability["opt_out_requested"] is True
    assert traceability["opt_out_accepted"] is True
    assert left["policy_set_sha256"] == canonical_digest
    assert left["policy_set_sha256"] == right["policy_set_sha256"]


def test_validator_measures_artifact_without_render_mutation(tmp_path: Path) -> None:
    job_root = tmp_path / "job"
    primary = job_root / "results" / "figure.png"
    primary.parent.mkdir(parents=True)
    Image.new("RGB", (120, 80), "navy").save(primary, format="PNG", dpi=(300, 300))
    previews = _build_preview_artifacts(
        job_root=job_root,
        output_path=primary,
        figures=[{"path": str(primary)}],
    )
    before = primary.read_bytes()
    manifest = _manifest("neutral-nature-audit", previews, _sha256(primary))

    evidence = build_render_evidence(
        manifest,
        job_root=job_root,
        producer_kind="test-neutral-render",
        producer_version="1",
        render_policy=resolve_render_policy_selection(None),
        validation_target="nature",
    )

    assert primary.read_bytes() == before
    assert evidence["resolved_policy"]["parameters"]["render_policy"] == "render-neutral"
    assert evidence["resolved_policy"]["parameters"]["validation_target"] == "nature"
    assert evidence["policy_projections"][0]["id"] == "journal-nature"
    assert evidence["policy_projections"][0]["status"] == "blocked"


def test_build_render_evidence_consumes_policy_context_with_old_policy_fields(tmp_path: Path) -> None:
    job_root = tmp_path / "job"
    primary = job_root / "results" / "figure.png"
    primary.parent.mkdir(parents=True)
    Image.new("RGB", (120, 80), "navy").save(primary, format="PNG", dpi=(300, 300))
    previews = _build_preview_artifacts(
        job_root=job_root,
        output_path=primary,
        figures=[{"path": str(primary)}],
    )
    manifest = _manifest("context-neutral-nature-audit", previews, _sha256(primary))
    context = resolve_render_policy_context({"validation_target": "nature"}, compatibility=False)

    evidence = build_render_evidence(
        manifest,
        job_root=job_root,
        producer_kind="test-neutral-render",
        producer_version="1",
        policy_context=context,
    )

    assert evidence["resolved_policy"]["id"] == "journal-nature"
    assert evidence["resolved_policy"]["parameters"]["render_policy"] == "render-neutral"
    assert evidence["resolved_policy"]["parameters"]["validation_target"] == "nature"
    assert evidence["policy_projections"][0]["id"] == "journal-nature"
    assert evidence["policy_context"] == {
        "schema_version": context["schema_version"],
        "source": context["source"],
        "policy_set_sha256": context["policy_set_sha256"],
        "render_policy": context["render_policy"],
        "validation_target": context["validation_target"],
    }
    assert evidence["policy_context"]["policy_set_sha256"] == context["policy_set_sha256"]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("policy_set_sha256", None, "policy_context digest is malformed"),
        ("policy_set_sha256", "forged", "policy_context digest is malformed"),
        ("schema_version", "figops-render-policy-context/0", "policy_context schema is malformed"),
        ("render_policy", None, "policy_context render_policy is malformed"),
    ],
)
def test_build_render_evidence_rejects_malformed_policy_context(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    job_root = tmp_path / "job"
    primary = job_root / "results" / "figure.png"
    primary.parent.mkdir(parents=True)
    Image.new("RGB", (120, 80), "navy").save(primary, format="PNG", dpi=(300, 300))
    previews = _build_preview_artifacts(
        job_root=job_root,
        output_path=primary,
        figures=[{"path": str(primary)}],
    )
    manifest = _manifest("malformed-policy-context", previews, _sha256(primary))
    context = resolve_render_policy_context({"validation_target": "nature"}, compatibility=False)
    if value is None:
        context.pop(field)
    else:
        context[field] = value

    with pytest.raises(ValueError, match=message):
        build_render_evidence(
            manifest,
            job_root=job_root,
            producer_kind="test-neutral-render",
            producer_version="1",
            policy_context=context,
        )


def test_legacy_render_policy_argument_conflicts_keep_public_errors(tmp_path: Path) -> None:
    job_root = tmp_path / "job"
    primary = _pdf(job_root / "results" / "figure.pdf")
    previews = _build_preview_artifacts(
        job_root=job_root,
        output_path=primary,
        figures=[{"path": str(primary)}],
    )
    manifest = _manifest("legacy-conflicts", previews, _sha256(primary))
    legacy = {
        "id": "legacy-policy",
        "version": "1",
        "source": "legacy-test",
        "parameters": {},
    }

    with pytest.raises(
        ValueError,
        match="validation_target cannot be combined with the legacy resolved_policy argument",
    ):
        build_render_evidence(
            manifest,
            job_root=job_root,
            producer_kind="test-render",
            producer_version="1",
            resolved_policy=legacy,
            validation_target="nature",
        )
    with pytest.raises(ValueError, match="render_policy conflicts with the legacy resolved_policy argument"):
        build_render_evidence(
            manifest,
            job_root=job_root,
            producer_kind="test-render",
            producer_version="1",
            resolved_policy=legacy,
            render_policy=resolve_render_policy_selection("neutral"),
        )


def test_policy_projection_binds_artifact_rule_and_measurement_versions(tmp_path: Path) -> None:
    job_root = tmp_path / "job"
    primary = job_root / "results" / "figure.png"
    primary.parent.mkdir(parents=True)
    Image.new("RGB", (60, 40), "white").save(primary, format="PNG", dpi=(600, 600))
    previews = _build_preview_artifacts(
        job_root=job_root,
        output_path=primary,
        figures=[{"path": str(primary)}],
    )
    manifest = _manifest("projection-binding", previews, _sha256(primary))
    evidence = build_render_evidence(
        manifest,
        job_root=job_root,
        producer_kind="test-policy-render",
        producer_version="1",
        render_policy=resolve_render_policy_selection("neutral"),
        validation_target="nature",
    )
    parameters = evidence["resolved_policy"]["parameters"]

    assert parameters["artifact_sha256"] == _sha256(primary)
    assert parameters["rule_version"] == RULE_VERSION
    assert parameters["measurement_implementation"] == MEASUREMENT_IMPLEMENTATION
    assert parameters["measurement_version"] == MEASUREMENT_VERSION
    assert len(parameters["inputs_sha256"]) == len(parameters["results_sha256"]) == 64
    producer_binding = {
        "producer": evidence["producer"],
        "provenance": evidence["provenance"],
    }
    recomputed = verify_artifact_policy_projection(
        primary,
        resolved_policy=evidence["resolved_policy"],
        policy_projection=evidence["policy_projections"][0],
        geometry_measurements=evidence["measurements"],
        producer_binding=producer_binding,
    )
    assert recomputed["policy_projection"] == evidence["policy_projections"][0]

    tampered = dict(evidence["resolved_policy"])
    tampered["parameters"] = dict(parameters)
    tampered["parameters"]["results_sha256"] = "0" * 64
    with pytest.raises(ArtifactPolicyMeasurementError, match="does not recompute"):
        verify_artifact_policy_projection(
            primary,
            resolved_policy=tampered,
            policy_projection=evidence["policy_projections"][0],
            geometry_measurements=evidence["measurements"],
            producer_binding=producer_binding,
        )

    tampered_geometry = copy.deepcopy(evidence["measurements"])
    tampered_geometry[0]["reason"] = "forged geometry availability"
    with pytest.raises(ArtifactPolicyMeasurementError, match="does not recompute"):
        verify_artifact_policy_projection(
            primary,
            resolved_policy=evidence["resolved_policy"],
            policy_projection=evidence["policy_projections"][0],
            geometry_measurements=tampered_geometry,
            producer_binding=producer_binding,
        )


def test_required_resolution_and_geometry_unavailable_fail_closed(
    tmp_path: Path,
) -> None:
    without_dpi = tmp_path / "missing-dpi.png"
    Image.new("RGB", (120, 80), "navy").save(without_dpi, format="PNG")
    unavailable = measure_artifact_policy(without_dpi, validation_target="nature")

    assert unavailable["policy_projection"]["status"] == "needs_review"
    unavailable_results = unavailable["resolved_policy"]["parameters"]["results"]
    dpi = next(item for item in unavailable_results if item["check_id"] == "dpi")
    text = next(item for item in unavailable_results if item["check_id"] == "text_geometry")
    assert (dpi["status"], dpi["enforcement"]) == ("not_applicable", "required")
    assert (text["status"], text["enforcement"]) == ("not_applicable", "informational")

    measured = tmp_path / "measured.png"
    Image.new("RGB", (120, 80), "navy").save(measured, format="PNG", dpi=(600, 600))
    ready = measure_artifact_policy(measured, validation_target="nature")
    assert ready["policy_projection"]["status"] == "needs_review"
    ready_dpi = next(
        item
        for item in ready["resolved_policy"]["parameters"]["results"]
        if item["check_id"] == "dpi"
    )
    assert ready_dpi["comparison_tolerance"] == 0.02

    below_minimum = tmp_path / "below-minimum.png"
    Image.new("RGB", (120, 80), "navy").save(below_minimum, format="PNG", dpi=(599, 599))
    below = measure_artifact_policy(below_minimum, validation_target="nature")
    assert below["policy_projection"]["status"] == "blocked"


def test_pdf_width_and_font_subtype_are_measured_from_existing_bytes(tmp_path: Path) -> None:
    safe = tmp_path / "safe.pdf"
    # Keep the fixture's page geometry explicit. Other integration tests may
    # enable ``savefig.bbox = "tight"`` globally, which intentionally crops
    # the PDF MediaBox and makes a five-inch canvas narrower than 127 mm.
    with plt.rc_context({"pdf.fonttype": 42, "savefig.bbox": None}):
        figure, axis = plt.subplots(figsize=(5, 2))
        axis.plot([0, 1], [0, 1])
        figure.savefig(safe, format="pdf")
        plt.close(figure)
    safe_policy = measure_artifact_policy(safe, validation_target="nature")

    assert safe_policy["policy_projection"]["status"] == "needs_review"
    safe_results = safe_policy["resolved_policy"]["parameters"]["results"]
    assert next(item for item in safe_results if item["check_id"] == "physical_width")["observed"] == 127.0
    assert next(item for item in safe_results if item["check_id"] == "font_geometry")["status"] == "pass"

    type3 = tmp_path / "type3.pdf"
    with plt.rc_context({"pdf.fonttype": 3, "savefig.bbox": None}):
        figure, axis = plt.subplots(figsize=(5, 2))
        axis.set_title("Type3")
        figure.savefig(type3, format="pdf")
        plt.close(figure)
    blocked = measure_artifact_policy(type3, validation_target="nature")
    assert blocked["policy_projection"]["status"] == "blocked"
    assert any(item["code"] == "ARTIFACT_FONT_GEOMETRY_FAIL" for item in blocked["policy_projection"]["findings"])


def test_malformed_pdf_with_policy_tokens_is_rejected_before_measurement(tmp_path: Path) -> None:
    malformed = tmp_path / "forged.pdf"
    malformed.write_bytes(
        b"%PDF-1.4\n1 0 obj<</Type/Page/MediaBox [0 0 360 200]>>endobj\n%%EOF\n"
    )

    with pytest.raises(ArtifactPolicyMeasurementError, match="artifact structure is invalid"):
        measure_artifact_policy(malformed, validation_target="nature")


def test_bound_style_geometry_can_satisfy_journal_minima_and_rejects_tampering(tmp_path: Path) -> None:
    artifact = tmp_path / "bound.png"
    Image.new("RGB", (120, 80), "navy").save(artifact, format="PNG", dpi=(600, 600))
    geometry = [
        {
            "metric_id": "style_geometry_observations",
            "availability": "available",
            "unit": "structured",
            "scope": "figure",
            "value": {
                "figure_height_mm": 50.0,
                "font_sizes": [{"axes": 0, "role": "axis", "fontsize_pt": 6.0}],
                "line_widths": [{"axes": 0, "role": "line", "artist_index": 0, "linewidth_pt": 0.8}],
            },
        }
    ]
    producer_binding = {
        "producer": {"status": "passed", "kind": "test", "version": "1"},
        "provenance": {
            "status": "passed",
            "input_sha256": "1" * 64,
            "config_sha256": "2" * 64,
            "script_sha256": "3" * 64,
            "environment_sha256": "4" * 64,
            "output_sha256": _sha256(artifact),
        },
    }
    measured = measure_artifact_policy(
        artifact,
        validation_target="nature",
        geometry_measurements=geometry,
        producer_binding=producer_binding,
    )

    assert measured["policy_projection"]["status"] == "informational"
    results = measured["resolved_policy"]["parameters"]["results"]
    assert all(
        item["status"] == "pass"
        for item in results
        if item["check_id"] in {"minimum_font_size", "minimum_line_width", "maximum_figure_height"}
    )
    verify_artifact_policy_projection(
        artifact,
        resolved_policy=measured["resolved_policy"],
        policy_projection=measured["policy_projection"],
        geometry_measurements=geometry,
        producer_binding=producer_binding,
    )

    forged = copy.deepcopy(geometry)
    forged[0]["value"]["font_sizes"][0]["fontsize_pt"] = 1.0
    with pytest.raises(ArtifactPolicyMeasurementError, match="does not recompute"):
        verify_artifact_policy_projection(
            artifact,
            resolved_policy=measured["resolved_policy"],
            policy_projection=measured["policy_projection"],
            geometry_measurements=forged,
            producer_binding=producer_binding,
        )
