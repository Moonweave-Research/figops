from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from hub_core.mcp import GraphHubMCPServer
from hub_core.mcp.discovery_schemas import list_resource_templates
from hub_core.mcp.render_orchestration import _build_preview_artifacts, _preview_resource_references
from hub_core.mcp.schemas import list_tool_definitions
from tests.test_mcp_rendering import _write_csv, _write_project_render_fixture


def _call(server: GraphHubMCPServer, tool_name: str, arguments: dict) -> dict:
    response = server.call_tool(tool_name, arguments)
    assert json.loads(response["content"][0]["text"]) == response["structuredContent"]
    return response["structuredContent"]


def _assert_render_preview_contract(server: GraphHubMCPServer, result: dict, *, kind: str) -> dict:
    assert result["status"] in {"ok", "warning"}
    assert result["artifact_resources"]
    assert result["preview_resources"]
    assert all(uri.startswith("figops://jobs/") and "/artifacts/" in uri for uri in result["artifact_resources"])
    assert all(uri.startswith("figops://jobs/") and "/previews/" in uri for uri in result["preview_resources"])
    assert "blob" not in json.dumps(result)

    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    entries = manifest["preview_artifacts"]
    assert len(entries) == len(result["artifact_resources"]) == len(result["preview_resources"])
    job_root = server.runtime_root / kind / result["job_id"]
    for index, entry in enumerate(entries):
        artifact = job_root / entry["relative_path"]
        raw = artifact.read_bytes()
        assert artifact.is_file()
        assert entry["byte_size"] == len(raw)
        assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
        assert result["artifact_resources"][index].endswith(f"/{index}")
        assert result["preview_resources"][index].endswith(f"/{index}")

    metadata = server.read_resource(result["artifact_resources"][0])["contents"][0]
    assert metadata["mimeType"] == "application/json"
    assert "blob" not in metadata
    preview = server.read_resource(result["preview_resources"][0])["contents"][0]
    if entries[0]["media_type"] == "image/svg+xml":
        unavailable = json.loads(preview["text"])
        assert unavailable["metadata"]["availability"] == "unavailable"
        assert "blob" not in preview
    else:
        assert preview["mimeType"] in {"image/png", "image/jpeg", "image/webp"}
        assert base64.b64decode(preview["blob"], validate=True)
    return manifest


def test_successful_single_render_publishes_exact_lazy_preview_contract(tmp_path: Path) -> None:
    data_path = _write_csv(tmp_path / "input" / "data.csv")
    server = GraphHubMCPServer(
        research_root=tmp_path,
        runtime_root=tmp_path / "runtime",
        write_tools_enabled=True,
    )

    result = _call(
        server,
        "figops.render_csv_graph",
        {"data_path": str(data_path), "x_column": "x", "y_column": "y", "job_id": "preview-single"},
    )

    manifest = _assert_render_preview_contract(server, result, kind="mcp_jobs")
    assert manifest["preview_artifacts"][0]["logical_role"] == "primary"
    assert manifest["preview_artifacts"][0]["media_type"] == "image/png"


def test_successful_multipanel_render_publishes_lazy_preview_contract(tmp_path: Path) -> None:
    data_path = _write_csv(tmp_path / "input" / "data.csv")
    server = GraphHubMCPServer(
        research_root=tmp_path,
        runtime_root=tmp_path / "runtime",
        write_tools_enabled=True,
    )

    result = _call(
        server,
        "figops.render_csv_multipanel",
        {
            "panels": [
                {"data_path": str(data_path), "x_column": "x", "y_column": "y", "title": "A"},
                {"data_path": str(data_path), "x_column": "x", "y_column": "y", "title": "B"},
            ],
            "rows": 1,
            "cols": 2,
            "job_id": "preview-multipanel",
        },
    )

    manifest = _assert_render_preview_contract(server, result, kind="mcp_jobs")
    assert manifest["preview_artifacts"][0]["logical_role"] == "primary"


def test_successful_project_render_publishes_lazy_preview_contract(tmp_path: Path) -> None:
    research_root = tmp_path / "ResearchOS"
    project = _write_project_render_fixture(research_root)
    server = GraphHubMCPServer(
        research_root=research_root,
        runtime_root=tmp_path / "runtime",
        write_tools_enabled=True,
    )

    result = _call(
        server,
        "figops.render_project_figure",
        {"project_path": str(project), "figure_id": "Fig1", "job_id": "preview-project"},
    )

    manifest = _assert_render_preview_contract(server, result, kind="mcp_project_jobs")
    assert manifest["preview_artifacts"][0]["relative_path"].startswith("project/")


def test_dry_run_and_failed_render_do_not_invent_preview_membership(tmp_path: Path) -> None:
    data_path = _write_csv(tmp_path / "input" / "data.csv")
    server = GraphHubMCPServer(
        research_root=tmp_path,
        runtime_root=tmp_path / "runtime",
        write_tools_enabled=True,
    )

    dry_run = _call(
        server,
        "figops.render_csv_graph",
        {
            "data_path": str(data_path),
            "x_column": "x",
            "y_column": "y",
            "job_id": "preview-dry",
            "dry_run": True,
        },
    )
    failed = _call(
        server,
        "figops.render_csv_graph",
        {"data_path": str(data_path), "x_column": "missing", "y_column": "y", "job_id": "preview-fail"},
    )

    for result in (dry_run, failed):
        assert result["artifact_resources"] == []
        assert not result.get("preview_resources")
    assert not (server.runtime_root / "mcp_jobs" / "preview-dry").exists()
    assert not (server.runtime_root / "mcp_jobs" / "preview-fail").exists()


@pytest.mark.parametrize(
    ("suffix", "image_format", "media_type"),
    [(".png", "PNG", "image/png"), (".jpg", "JPEG", "image/jpeg"), (".webp", "WEBP", "image/webp")],
)
def test_producer_seals_supported_raster_headers(
    tmp_path: Path,
    suffix: str,
    image_format: str,
    media_type: str,
) -> None:
    job_root = tmp_path / "job"
    artifact = job_root / "results" / f"figure{suffix}"
    artifact.parent.mkdir(parents=True)
    Image.new("RGB", (8, 6), "navy").save(artifact, format=image_format)

    entries = _build_preview_artifacts(
        job_root=job_root,
        output_path=artifact,
        figures=[{"path": str(artifact), "format": suffix.lstrip(".")}],
    )

    assert entries == [
        {
            "logical_role": "primary",
            "relative_path": f"results/figure{suffix}",
            "media_type": media_type,
            "byte_size": artifact.stat().st_size,
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }
    ]


def test_pdf_primary_and_raster_companion_keep_exact_roles_and_uris(tmp_path: Path) -> None:
    job_root = tmp_path / "job"
    primary = job_root / "results" / "figure.pdf"
    companion = job_root / "results" / "figure.png"
    primary.parent.mkdir(parents=True)
    primary.write_bytes(b"%PDF-1.4\n%%EOF\n")
    Image.new("RGB", (8, 6), "navy").save(companion, format="PNG")

    entries = _build_preview_artifacts(
        job_root=job_root,
        output_path=primary,
        figures=[{"path": str(companion)}, {"path": str(primary)}],
    )
    references = _preview_resource_references("pdf-job", entries)

    assert [entry["logical_role"] for entry in entries] == ["primary", "companion:png"]
    assert entries[0]["media_type"] == "application/pdf"
    assert references["artifact_resources"] == [
        "figops://jobs/pdf-job/artifacts/primary/0",
        "figops://jobs/pdf-job/artifacts/companion%3Apng/1",
    ]
    assert references["preview_resources"][1].endswith("/companion%3Apng/1")


def test_discovery_lists_metadata_and_lazy_preview_templates() -> None:
    templates = {item["uriTemplate"]: item for item in list_resource_templates()}

    assert "figops://jobs/{job_id}/artifacts/{logical_role}/{artifact_index}" in templates
    assert "figops://jobs/{job_id}/previews/{logical_role}/{artifact_index}" in templates


def test_render_output_schemas_declare_only_bounded_resource_uri_arrays() -> None:
    definitions = {definition["name"]: definition for definition in list_tool_definitions()}

    for name in ("figops.render_csv_graph", "figops.render_csv_multipanel", "figops.render_project_figure"):
        properties = definitions[name]["outputSchema"]["properties"]
        for key, path_kind in (("artifact_resources", "artifacts"), ("preview_resources", "previews")):
            schema = properties[key]
            assert schema["type"] == "array"
            assert schema["maxItems"] == 256
            assert schema["items"]["maxLength"] == 256
            assert f"/{path_kind}/" in schema["items"]["pattern"]
            assert "blob" not in json.dumps(schema).lower()
