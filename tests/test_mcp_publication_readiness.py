from __future__ import annotations

import base64
import hashlib
import json

from hub_core.mcp import GraphHubMCPServer


def test_readiness_tool_is_read_only_path_free_and_available_when_writes_disabled(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    manifest_dir = runtime_root / "mcp_jobs" / "job-1"
    manifest_dir.mkdir(parents=True)
    artifact = manifest_dir / "figure.png"
    artifact_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    artifact.write_bytes(artifact_bytes)
    output_hash = hashlib.sha256(artifact_bytes).hexdigest()
    (manifest_dir / "manifest.json").write_text(
        json.dumps(
            {
                "job_id": "job-1",
                "project_id": "project-safe",
                "figure_id": "figure-safe",
                "artifact_status": "created",
                "figures": [{"path": str(artifact), "format": "png"}],
                "provenance": {
                    "input_sha256": "1" * 64,
                    "config_sha256": "2" * 64,
                    "script_sha256": "3" * 64,
                    "environment_sha256": "4" * 64,
                    "output_sha256": output_hash,
                },
                "geometry_diagnostics": {
                    "schema_version": "geometry_diagnostics/1",
                    "passed": True,
                    "checks": [],
                },
                "visual_preflight_status": {"passed": True},
                "layout_report": {"schema_version": "layout_report/1", "passed": True},
            }
        ),
        encoding="utf-8",
    )
    server = GraphHubMCPServer(runtime_root=runtime_root, write_tools_enabled=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("readiness evaluation must not invoke subprocesses or writers")

    monkeypatch.setattr("subprocess.run", forbidden)
    before = sorted(path.relative_to(runtime_root) for path in runtime_root.rglob("*"))
    result = server.call_tool("figops.evaluate_publication_readiness", {"job_id": "job-1"})
    after = sorted(path.relative_to(runtime_root) for path in runtime_root.rglob("*"))

    assert result["isError"] is False
    structured = result["structuredContent"]
    assert structured["status"] == "ok"
    assert structured["readiness_report"]["readiness_status"] == "needs_review"
    assert structured["readiness_report"]["applied_policies"] == []
    assert not any(
        item["source"] == "policy_projection"
        for item in structured["readiness_report"]["findings"]
    )
    assert structured["created_paths"] == []
    assert structured["modified_paths"] == []
    assert before == after
    serialized = json.dumps(structured, ensure_ascii=False)
    assert str(tmp_path) not in serialized
    assert "secret" not in serialized.casefold()


def test_readiness_tool_has_no_legacy_graphhub_alias(tmp_path):
    runtime_root = tmp_path / "absent"
    server = GraphHubMCPServer(runtime_root=runtime_root, write_tools_enabled=False)
    names = {tool["name"] for tool in server.list_tool_definitions()}

    assert "figops.evaluate_publication_readiness" in names
    assert "graphhub.evaluate_publication_readiness" not in server._handlers
    result = server.call_tool("figops.evaluate_publication_readiness", {"job_id": "missing-job"})
    assert result["isError"] is True
    assert runtime_root.exists() is False


def test_readiness_tool_blocks_when_required_evidence_is_missing(tmp_path):
    runtime_root = tmp_path / "runtime"
    manifest_dir = runtime_root / "mcp_jobs" / "job-empty"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "manifest.json").write_text('{"job_id": "job-empty"}', encoding="utf-8")
    server = GraphHubMCPServer(runtime_root=runtime_root, write_tools_enabled=False)

    result = server.call_tool("figops.evaluate_publication_readiness", {"job_id": "job-empty"})

    assert result["isError"] is True
    report = result["structuredContent"]["readiness_report"]
    assert report["readiness_status"] == "blocked"
    assert {finding["source"] for finding in report["findings"]} == {
        "artifact_integrity",
        "provenance_coverage",
        "geometry_diagnostics",
        "visual_preflight_status",
        "layout_report",
    }
