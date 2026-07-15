from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from hub_core.evidence_contract import validate_evidence_envelope
from hub_core.mcp import GraphHubMCPServer
from hub_core.mcp.schemas import TOOL_NAMES, list_tool_definitions
from hub_core.mcp.transport import JSONRPC_INVALID_PARAMS, _handle_json_rpc
from tests.test_mcp_rendering import _write_csv, _write_project_render_fixture


def _server(root: Path, *, writes: bool) -> GraphHubMCPServer:
    return GraphHubMCPServer(
        research_root=root,
        runtime_root=root / "runtime",
        write_tools_enabled=writes,
    )


def test_inspect_data_is_real_bounded_read_only_one_shot(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input" / "facts.csv")
    server = _server(tmp_path, writes=False)

    response = server.call_tool("figops.inspect_data", {"data_path": str(source)})
    result = response["structuredContent"]

    assert response["isError"] is False
    assert result["status"] == "available"
    assert result["source"]["format"] == "csv"
    assert result["scan"]["row_count"] == 3
    assert result["samples"] == []
    assert len(result["source"]["sha256"]) == 64
    assert len(json.dumps(result, separators=(",", ":")).encode()) <= 32 * 1024
    assert not (tmp_path / "runtime").exists()


def test_basic_render_is_one_call_with_validated_evidence_and_lazy_uris(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input" / "facts.csv")
    server = _server(tmp_path, writes=True)

    response = server.call_tool(
        "figops.render_basic_csv",
        {
            "data_path": str(source),
            "x": "x",
            "y": "y",
            "plot_type": "line",
            "labels": {"title": "Raw authored title"},
            "job_id": "v2-basic",
        },
    )
    result = response["structuredContent"]

    assert response["isError"] is False
    assert result["status"] in {"ok", "warning"}
    assert result["job_id"] == "v2-basic"
    assert result["manifest_uri"] == "figops://jobs/v2-basic/manifest"
    assert result["preview_uri"].startswith("figops://jobs/v2-basic/previews/primary/0")
    assert result["artifact"]["logical_role"] == "primary"
    validate_evidence_envelope(result["evidence"])
    assert result["evidence"]["provenance"]["output_sha256"] == result["artifact"]["sha256"]
    assert not ({"created_paths", "job_root", "output_path", "config_path"} & set(result))
    assert "blob" not in json.dumps(result).lower()
    manifest = json.loads(
        (tmp_path / "runtime" / "mcp_jobs" / "v2-basic" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["evidence"] == result["evidence"]


def test_project_script_render_executes_only_declared_python_and_returns_same_contract(tmp_path: Path) -> None:
    project = _write_project_render_fixture(tmp_path)
    server = _server(tmp_path, writes=True)

    response = server.call_tool(
        "figops.render_project_script",
        {"project_path": str(project), "figure_id": "Fig1", "job_id": "v2-project"},
    )
    result = response["structuredContent"]

    assert response["isError"] is False
    assert result["status"] in {"ok", "warning"}
    assert result["artifact"]["media_type"] == "image/png"
    assert result["preview_uri"] == "figops://jobs/v2-project/previews/primary/0"
    validate_evidence_envelope(result["evidence"])
    assert result["evidence"]["producer"]["kind"] == "mcp-project-script-render"


def test_project_rscript_missing_is_typed_and_creates_no_job(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _write_project_render_fixture(tmp_path)
    python_script = project / "hub_scripts" / "plot.py"
    r_script = python_script.with_suffix(".R")
    r_script.write_text("stop('must not execute')\n", encoding="utf-8")
    config_path = project / "project_config.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "visual_style:\n",
            "language_policy:\n  analysis_lang: r\n  plot_lang: r\n  allow_nonstandard: true\nvisual_style:\n",
        ).replace("hub_scripts/plot.py", "hub_scripts/plot.R"),
        encoding="utf-8",
    )
    monkeypatch.setattr("hub_core.mcp.tools.render_project.shutil.which", lambda _name: None)
    server = _server(tmp_path, writes=True)

    result = server.call_tool(
        "figops.render_project_script",
        {"project_path": str(project), "figure_id": "Fig1", "job_id": "missing-r"},
    )["structuredContent"]

    assert result["status"] == "error"
    assert result.get("runtime_availability") == {
        "status": "unavailable",
        "reason": "RSCRIPT_UNAVAILABLE",
    }, result
    assert "not executed" in result["errors"][0]
    assert not (tmp_path / "runtime" / "mcp_project_jobs" / "missing-r").exists()


@pytest.mark.parametrize("forbidden", ["code", "source", "command", "args", "interpreter"])
def test_project_script_schema_rejects_code_and_command_surfaces(tmp_path: Path, forbidden: str) -> None:
    server = _server(tmp_path, writes=True)
    response = _handle_json_rpc(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "figops.render_project_script",
                "arguments": {"project_path": "project", "figure_id": "Fig1", forbidden: "print(1)"},
            },
        },
    )
    assert response["error"]["code"] == JSONRPC_INVALID_PARAMS
    assert forbidden in response["error"]["message"]


def test_nested_basic_labels_are_closed_before_dispatch(tmp_path: Path) -> None:
    server = _server(tmp_path, writes=True)
    response = _handle_json_rpc(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "figops.render_basic_csv",
                "arguments": {
                    "data_path": "input.csv",
                    "x": "x",
                    "y": "y",
                    "labels": {"title": "ok", "statistics": "mean+-sem"},
                },
            },
        },
    )
    assert response["error"]["code"] == JSONRPC_INVALID_PARAMS
    assert "labels.statistics" in response["error"]["message"]


def test_writes_disabled_blocks_v2_and_alias_before_runtime_mutation(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input" / "facts.csv")
    server = _server(tmp_path, writes=False)

    for name, arguments in (
        ("figops.render_basic_csv", {"data_path": str(source), "x": "x", "y": "y", "job_id": "blocked-v2"}),
        (
            "graphhub.render_csv_graph",
            {"data_path": str(source), "x_column": "x", "y_column": "y", "job_id": "blocked-alias"},
        ),
    ):
        response = server.call_tool(name, arguments)
        assert response["isError"] is True
        assert response["structuredContent"]["error_category"] == "disabled"
    assert not (tmp_path / "runtime").exists()


def test_all_direct_write_handlers_and_legacy_aliases_guard_before_validation_or_mutation(tmp_path: Path) -> None:
    server = _server(tmp_path, writes=False)

    direct_handlers = (
        server.render_csv_graph,
        server.render_csv_multipanel,
        server.render_project_figure,
        server.render_basic_csv,
        server.render_project_script,
        server.scaffold_project,
        server.normalize_project_structure,
        server.batch_check,
    )
    for handler in direct_handlers:
        assert handler({})["status"] == "error"
    for alias in (
        "graphhub.render_csv_graph",
        "graphhub.render_csv_multipanel",
        "graphhub.render_project_figure",
        "graphhub.scaffold_project",
        "graphhub.normalize_project_structure",
        "graphhub.batch_check",
    ):
        assert server._handlers[alias]({})["status"] == "error"
    assert not (tmp_path / "runtime").exists()


def test_audit_is_read_only_explicit_and_returns_preview_uri(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "input" / "facts.csv")
    writer = _server(tmp_path, writes=True)
    rendered = writer.call_tool(
        "figops.render_basic_csv",
        {"data_path": str(source), "x": "x", "y": "y", "job_id": "audit-me"},
    )["structuredContent"]
    manifest_path = tmp_path / "runtime" / "mcp_jobs" / "audit-me" / "manifest.json"
    before = manifest_path.read_bytes()
    reader = _server(tmp_path, writes=False)

    response = reader.call_tool("figops.audit_artifact", {"job_id": "audit-me", "policy_packs": []})
    result = response["structuredContent"]

    assert response["isError"] is False
    assert result["status"] in {"blocked", "needs_revision", "needs_review"}
    assert result["manifest_uri"] == rendered["manifest_uri"]
    assert result["preview_uri"] == rendered["preview_uri"]
    assert result["audit"]["selected_policy_ids"] == []
    assert result["audit"]["manual_review_required"] is True
    assert manifest_path.read_bytes() == before
    assert "approved" not in json.dumps(result).lower()
    assert "publishable" not in json.dumps(result).lower()


def _render_audit_fixture(root: Path, job_id: str) -> tuple[GraphHubMCPServer, Path]:
    source = _write_csv(root / "input" / f"{job_id}.csv")
    writer = _server(root, writes=True)
    result = writer.call_tool(
        "figops.render_basic_csv",
        {"data_path": str(source), "x": "x", "y": "y", "job_id": job_id},
    )["structuredContent"]
    assert result["status"] in {"ok", "warning"}
    return _server(root, writes=False), root / "runtime" / "mcp_jobs" / job_id / "manifest.json"


def test_audit_rejects_duplicate_job_id_across_runtime_job_kinds(tmp_path: Path) -> None:
    reader, manifest = _render_audit_fixture(tmp_path, "ambiguous-audit")
    duplicate = tmp_path / "runtime" / "mcp_project_jobs" / "ambiguous-audit" / "manifest.json"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_bytes(manifest.read_bytes())

    response = reader.call_tool("figops.audit_artifact", {"job_id": "ambiguous-audit"})

    assert response["isError"] is True
    assert "ambiguous" in " ".join(response["structuredContent"]["errors"]).lower()


def test_audit_rejects_manifest_job_id_mismatch(tmp_path: Path) -> None:
    reader, manifest = _render_audit_fixture(tmp_path, "bound-audit")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["job_id"] = "different-job"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    response = reader.call_tool("figops.audit_artifact", {"job_id": "bound-audit"})

    assert response["isError"] is True
    assert "does not match" in " ".join(response["structuredContent"]["errors"]).lower()


def test_audit_rejects_manifest_swap_between_snapshot_and_descriptor_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, manifest = _render_audit_fixture(tmp_path, "swap-audit")
    replacement = manifest.with_name("replacement.json")
    replacement.write_bytes(manifest.read_bytes())
    from hub_core.mcp import manifest_io

    original_snapshot = manifest_io.snapshot_project_input
    swapped = False

    def snapshot_then_swap(*args, **kwargs):
        nonlocal swapped
        snapshot = original_snapshot(*args, **kwargs)
        if not swapped:
            replacement.replace(manifest)
            swapped = True
        return snapshot

    monkeypatch.setattr(manifest_io, "snapshot_project_input", snapshot_then_swap)
    response = reader.call_tool("figops.audit_artifact", {"job_id": "swap-audit"})

    assert swapped is True
    assert response["isError"] is True
    assert response["structuredContent"]["status"] == "error"


def test_audit_rejects_symlinked_manifest_leaf(tmp_path: Path) -> None:
    reader, manifest = _render_audit_fixture(tmp_path, "linked-audit")
    outside = tmp_path / "outside-manifest.json"
    outside.write_bytes(manifest.read_bytes())
    manifest.unlink()
    try:
        manifest.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")

    response = reader.call_tool("figops.audit_artifact", {"job_id": "linked-audit"})

    assert response["isError"] is True
    assert response["structuredContent"]["status"] == "error"


def test_audit_rejects_manifest_directory_reparse_component(tmp_path: Path) -> None:
    _, external_manifest = _render_audit_fixture(tmp_path / "external", "junction-audit")
    external_job = external_manifest.parent
    jobs_root = tmp_path / "runtime" / "mcp_jobs"
    jobs_root.mkdir(parents=True)
    linked_job = jobs_root / "junction-audit"
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(linked_job), str(external_job)],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            pytest.skip("directory junction creation is unavailable on this host")
    else:
        try:
            linked_job.symlink_to(external_job, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlink creation is unavailable on this host")
    reader = _server(tmp_path, writes=False)

    response = reader.call_tool("figops.audit_artifact", {"job_id": "junction-audit"})

    assert response["isError"] is True
    assert response["structuredContent"]["status"] == "error"


def test_all_tool_annotations_are_truthful_and_v2_schemas_fit_budgets() -> None:
    definitions = {item["name"]: item for item in list_tool_definitions()}
    assert set(definitions) == set(TOOL_NAMES)
    for name, definition in definitions.items():
        annotations = definition["annotations"]
        should_write = name in {
            "figops.render_csv_graph",
            "figops.render_csv_multipanel",
            "figops.render_project_figure",
            "figops.scaffold_project",
            "figops.normalize_project_structure",
            "figops.batch_check",
            "figops.render_basic_csv",
            "figops.render_project_script",
        }
        assert annotations["readOnlyHint"] is (not should_write)
        assert annotations["destructiveHint"] is should_write
        assert annotations["openWorldHint"] is False
    for name in (
        "figops.inspect_data",
        "figops.render_basic_csv",
        "figops.render_project_script",
        "figops.audit_artifact",
    ):
        size = len(json.dumps(definitions[name]["inputSchema"], separators=(",", ":")).encode())
        assert size <= 6 * 1024
    assert len(definitions["figops.render_basic_csv"]["inputSchema"]["properties"]) <= 14


def test_wp5_touched_modules_stay_below_modularity_gate() -> None:
    root = Path(__file__).parents[1]
    for relative in (
        "hub_core/mcp/schemas.py",
        "hub_core/mcp/tool_schema_common.py",
        "hub_core/mcp/v2_tool_schemas.py",
        "hub_core/mcp/render_orchestration.py",
        "hub_core/mcp/render_manifest.py",
        "hub_core/mcp/tools/render_csv.py",
        "hub_core/mcp/tools/render_support.py",
    ):
        assert len((root / relative).read_text(encoding="utf-8").splitlines()) < 800, relative
