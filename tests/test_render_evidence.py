from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image

from hub_core.artifact_audit import audit_artifact_evidence
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
