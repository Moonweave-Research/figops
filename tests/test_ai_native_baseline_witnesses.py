from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub_core.mcp import FigOpsMCPServer, GraphHubMCPServer
from hub_core.mcp.preview_artifacts import (
    MAX_PREVIEW_BASE64_BYTES,
    MAX_PREVIEW_EDGE,
    MAX_PREVIEW_PIXELS,
    MAX_PREVIEW_RAW_BYTES,
    PREVIEW_WORKER_MEMORY_BYTES,
    PREVIEW_WORKER_TIMEOUT_SECONDS,
)
from hub_core.mcp.transport import _handle_json_rpc
from hub_core.publication_readiness import evaluate_publication_readiness
from hub_core.raw_integrity import verify_raw_integrity
from plotting.bridge_renderer import BridgeFigureSpec
from plotting.renderers.labels import display_label

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "ai_native_agent_eval"
EXPIRY = "2026-08-15"


def _xfail(*, owner: str, defect: str):
    return pytest.mark.xfail(
        strict=True,
        reason=f"owner={owner}; expiry={EXPIRY}; defect={defect}",
    )


def _geometry(*checks: dict) -> dict:
    return {
        "schema_version": "geometry_diagnostics/1",
        "checks": list(checks),
        "passed": all(check.get("passed") is True for check in checks),
    }


def _clean_readiness_evidence() -> dict:
    return {
        "artifact_status": "ready",
        "failure_stage": "",
        "geometry_diagnostics": _geometry({"name": "tick_label_overlaps", "passed": True}),
        "visual_preflight_status": {"passed": True},
        "layout_report": {"schema_version": "layout_report/1", "passed": True},
        "provenance": {
            "input_sha256": "1" * 64,
            "config_sha256": "2" * 64,
            "script_sha256": "3" * 64,
            "output_sha256": "4" * 64,
        },
    }


def _write_project_fixture(project: Path, *, csv_check_path: str) -> None:
    (project / "hub_scripts").mkdir(parents=True)
    (project / "results" / "data").mkdir(parents=True)
    (project / "hub_scripts" / "plot.py").write_text(
        "from pathlib import Path\n"
        "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
        "Path('results/figures/Fig1.png').write_bytes(b'png')\n",
        encoding="utf-8",
    )
    quoted_check_path = json.dumps(csv_check_path)
    (project / "project_config.yaml").write_text(
        "\n".join(
            [
                "project:",
                "  name: AI Native Boundary Witness",
                "visual_style:",
                "  target_format: nature",
                "  profile: baseline",
                "data_contract:",
                "  csv_checks:",
                f"    - path: {quoted_check_path}",
                '      required_columns: ["x", "y"]',
                "      dtypes: {x: number, y: number}",
                "figures:",
                "  - id: Fig1",
                "    script: hub_scripts/plot.py",
                "    output: results/figures/Fig1.png",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("escape_kind", ["absolute", "traversal"])
def test_mcp_project_render_rejects_escaping_csv_check_path(tmp_path: Path, escape_kind: str) -> None:
    research_root = tmp_path / "research"
    project = research_root / "project"
    outside = research_root / "outside.csv"
    outside.parent.mkdir(parents=True)
    outside.write_text("x,y\n1,2\n", encoding="utf-8")
    csv_check_path = outside.as_posix() if escape_kind == "absolute" else "../outside.csv"
    _write_project_fixture(project, csv_check_path=csv_check_path)
    runtime_root = tmp_path / "runtime"
    server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)

    result = server.call_tool(
        "figops.render_project_figure",
        {
            "project_path": "project",
            "figure_id": "Fig1",
            "job_id": f"path-escape-{escape_kind}",
            "dry_run": True,
        },
    )["structuredContent"]

    assert result["status"] == "error"
    assert result["failure_stage"] in {"CONFIG", "VALIDATE", "CONTRACT"}
    assert not (runtime_root / "mcp_project_jobs" / f"path-escape-{escape_kind}").exists()


def test_default_bridge_label_preserves_scientific_identifier() -> None:
    spec = BridgeFigureSpec(
        csv_path="data.csv",
        output_path="figure.png",
        plot_type="bar",
        x_column="sample",
        y_column="value",
        title="Label fidelity witness",
    )

    assert display_label("ABC_DEF", compress_labels=spec.compress_labels) == "ABC_DEF"


def test_failed_artifact_and_failure_stage_override_clean_geometry() -> None:
    evidence = _clean_readiness_evidence()
    evidence.update({"artifact_status": "failed", "failure_stage": "PLOT"})

    report = evaluate_publication_readiness(evidence)
    codes = {finding["code"] for finding in report["findings"]}

    assert report["readiness_status"] == "blocked"
    assert any("ARTIFACT" in code or "FAILURE_STAGE" in code for code in codes)


def test_missing_required_provenance_hashes_block_readiness() -> None:
    evidence = _clean_readiness_evidence()
    evidence["provenance"] = {}

    report = evaluate_publication_readiness(evidence)

    assert report["readiness_status"] == "blocked"
    assert any("PROVENANCE" in finding["code"] for finding in report["findings"])


def test_producer_warning_calculation_status_is_supported() -> None:
    report = evaluate_publication_readiness(
        {
            "calculation_checks": {
                "schema_version": "1.0",
                "checks": [
                    {
                        "name": "grouped_cv",
                        "status": "warning",
                        "manual_review_needed": True,
                        "message": "Declared warn-only threshold exceeded.",
                    }
                ],
            }
        }
    )

    assert report["readiness_status"] in {"needs_revision", "needs_review"}
    assert all(finding["code"] != "CALCULATION_STATUS_INVALID" for finding in report["findings"])


def test_optional_unavailable_geometry_is_not_malformed_evidence() -> None:
    report = evaluate_publication_readiness(
        {
            "geometry_diagnostics": {
                "schema_version": "geometry_diagnostics/1",
                "checks": [
                    {
                        "name": "tick_label_crowding",
                        "passed": None,
                        "detail": "renderer did not expose tick extents",
                    }
                ],
                "passed": None,
            }
        }
    )

    assert report["readiness_status"] == "needs_review"
    assert all(finding["code"] != "GEOMETRY_CHECK_PASSED_INVALID" for finding in report["findings"])


def test_explicit_strict_raw_integrity_without_manifest_fails_closed(tmp_path: Path) -> None:
    config = {
        "project": {"name": "Strict Raw Witness"},
        "data_contract": {
            "raw_integrity": {
                "manifest": "raw/.raw_manifest.json",
                "mode": "strict",
                "paths": ["raw/"],
            }
        },
    }
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "data.csv").write_text("x,y\n1,2\n", encoding="utf-8")

    result = verify_raw_integrity(tmp_path, config)

    assert result["sealed"] is False
    assert result["ok"] is False
    assert result["errors"]


def test_significance_marker_without_calculation_evidence_is_rejected(tmp_path: Path) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    runtime_root = tmp_path / "runtime"
    server = GraphHubMCPServer(research_root=tmp_path, runtime_root=runtime_root)

    result = server.call_tool(
        "figops.render_csv_graph",
        {
            "data_path": str(data_path),
            "x_column": "x",
            "y_column": "y",
            "plot_type": "scatter",
            "significance_markers": [{"x1": 0, "x2": 1, "y": 2, "label": "p<0.05"}],
            "job_id": "unsupported-statistical-claim",
            "dry_run": True,
        },
    )["structuredContent"]

    assert result["status"] == "error"
    assert any(
        token in json.dumps(result, ensure_ascii=False).lower()
        for token in ("evidence_id", "analysis artifact", "provenance")
    )
    assert not (runtime_root / "mcp_jobs" / "unsupported-statistical-claim").exists()


def test_agent_eval_cases_are_outcome_and_permission_centered() -> None:
    payload = json.loads((FIXTURE_ROOT / "cases.json").read_text(encoding="utf-8"))
    cases = payload["cases"]

    assert payload["schema_version"] == "figops_agent_eval_cases/1"
    assert {case["id"] for case in cases} == {
        "simple-csv-unknown-columns",
        "complex-declared-project-script",
        "project-input-path-escape",
        "unsupported-statistical-annotation",
        "failed-artifact",
        "missing-provenance",
        "preview-driven-targeted-revision",
    }
    assert all(case.get("expected_outcomes") for case in cases)
    assert all("required_tool_sequence" not in case for case in cases)
    project_case = next(case for case in cases if case["id"] == "complex-declared-project-script")
    assert {"code", "command", "interpreter_flags"} <= set(project_case["forbidden_payload_fields"])


def test_v1_baseline_records_live_surface_and_expiring_witness_ownership() -> None:
    baseline = json.loads((FIXTURE_ROOT / "baseline-v1.json").read_text(encoding="utf-8"))
    surface = baseline["tool_surface"]

    assert baseline["schema_version"] == "figops_agent_eval_baseline/1"
    assert surface["canonical_tool_count"] == 14
    assert surface["legacy_alias_count"] == 13
    assert surface["tools_array_bytes"] == 51455
    assert surface["render_csv_graph_top_level_properties"] == 46
    assert baseline["guided_call_baseline"]["project"]["render_calls"] == 2
    assert baseline["target_budgets"]["known_schema_render_calls"] == 1
    assert all(witness["owner"] and witness["expiry"] == EXPIRY for witness in baseline["open_witnesses"])


def test_final_v2_measurement_matches_live_default_surface_and_generated_references() -> None:
    measurement = json.loads((FIXTURE_ROOT / "final-v2.json").read_text(encoding="utf-8"))

    def live_surface(*, writes_enabled: bool) -> tuple[list[dict], dict]:
        response = _handle_json_rpc(
            FigOpsMCPServer(surface_profile="v2", write_tools_enabled=writes_enabled),
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        return response["result"]["tools"], response

    tools, response = live_surface(writes_enabled=True)
    compact = lambda payload: json.dumps(  # noqa: E731
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    schemas = [
        (len(compact(tool["inputSchema"])), tool["name"])
        for tool in tools
    ]
    surface = measurement["tool_surface"]
    assert [tool["name"] for tool in tools] == surface["names"]
    assert len(tools) == surface["emitted_tool_definition_count"]
    assert len(compact(tools)) == surface["tools_array_bytes"]
    assert len(compact(response)) == surface["tools_list_response_bytes"]
    assert max(schemas) == (
        surface["maximum_input_schema_bytes"],
        surface["maximum_input_schema_tool"],
    )
    basic = next(tool for tool in tools if tool["name"] == "figops.render_basic_csv")
    assert len(basic["inputSchema"]["properties"]) == surface["render_basic_csv_top_level_properties"]

    read_tools, read_response = live_surface(writes_enabled=False)
    read_surface = measurement["writes_disabled_surface"]
    assert [tool["name"] for tool in read_tools] == read_surface["names"]
    assert len(compact(read_tools)) == read_surface["tools_array_bytes"]
    assert len(compact(read_response)) == read_surface["tools_list_response_bytes"]

    for reference in measurement["generated_references"].values():
        path = Path(__file__).parents[1] / reference["path"]
        assert len(path.read_bytes()) == reference["bytes"]
        assert len(path.read_text(encoding="utf-8").splitlines()) == reference["lines"]

    limits = measurement["preview_limits"]
    assert PREVIEW_WORKER_TIMEOUT_SECONDS == limits["worker_timeout_seconds"]
    assert MAX_PREVIEW_PIXELS == limits["maximum_pixels"]
    assert PREVIEW_WORKER_MEMORY_BYTES == limits["worker_memory_bytes"]
    assert MAX_PREVIEW_EDGE == limits["maximum_edge_pixels"]
    assert MAX_PREVIEW_RAW_BYTES == limits["maximum_raw_bytes"]
    assert MAX_PREVIEW_BASE64_BYTES == limits["maximum_base64_bytes"]

    assert measurement["open_witnesses"] == []
    assert measurement["evaluation_summary"]["hard_error_cases"]["catch_rate"] == 1.0
    assert measurement["evaluation_summary"]["preview_driven_revision"]["live_model_run"] is True
    assert measurement["evaluation_summary"]["preview_driven_revision"]["status"] == "passed"


def test_live_preview_revision_witness_is_bounded_targeted_and_non_approving() -> None:
    witness_path = FIXTURE_ROOT / "live-preview-revision-v1.json"
    witness = json.loads(witness_path.read_text(encoding="utf-8"))
    measurement = json.loads((FIXTURE_ROOT / "final-v2.json").read_text(encoding="utf-8"))

    def is_sha256(value: object) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and set(value) <= set("0123456789abcdef")
        )

    assert witness["schema_version"] == "figops_live_preview_revision_witness/1"
    assert witness["server"] == {
        "surface_profile": "v2",
        "write_tools_enabled": True,
        "strict_roots": True,
        "strict_data_roots": True,
        "runtime_location": "temporary child of the resolved FigOps runtime root",
    }
    assert witness["call_counts"] == {"render": 2, "preview_read": 2, "collect": 0}
    assert is_sha256(witness["fixture"]["input_sha256"])

    for key in ("initial_render", "revised_render"):
        render = witness[key]
        artifact = render["artifact"]
        preview = render["preview"]
        assert render["tool"] == "figops.render_basic_csv"
        assert render["status"] == "ok"
        assert is_sha256(artifact["sha256"])
        assert is_sha256(preview["blob_sha256"])
        assert artifact["resource_uri"].startswith(f"figops://jobs/{render['job_id']}/artifacts/")
        assert render["manifest_uri"] == f"figops://jobs/{render['job_id']}/manifest"
        assert preview["uri"].startswith(f"figops://jobs/{render['job_id']}/previews/")
        assert preview["media_type"] == "image/png"
        assert preview["read_lazily"] is True
        assert preview["visually_inspected"] is True
        assert 0 < preview["blob_byte_size"] <= MAX_PREVIEW_RAW_BYTES
        assert 0 < preview["width"] <= MAX_PREVIEW_EDGE
        assert 0 < preview["height"] <= MAX_PREVIEW_EDGE

    initial_observations = " ".join(witness["initial_render"]["visual_observations"]).casefold()
    assert all(term in initial_observations for term in ("zigzag", "no legend or title", "raw labels"))
    decision = witness["revision_decision"]
    assert set(decision["changes"]) == {"series", "labels"}
    assert decision["changes"]["series"] == "Scenario"
    assert decision["changes"]["labels"] == {
        "title": "Synthetic run duration by release step",
        "x_axis": "Release step",
        "y_axis": "Duration (seconds)",
    }
    assert decision["unchanged"] == ["data", "x", "y", "plot_type", "style_policy", "output_format"]
    assert decision["invented_statistics"] is False
    assert witness["revised_render"]["targeted_change_confirmed"] is True
    revised_observations = " ".join(witness["revised_render"]["visual_observations"]).casefold()
    assert all(term in revised_observations for term in ("separate monotonic", "legend", "no statistical"))

    consistency = witness["consistency_checks"]
    assert all(
        consistency[key] is True
        for key in (
            "initial_response_artifact_evidence_manifest_and_resource_hash_match",
            "revised_response_artifact_evidence_manifest_and_resource_hash_match",
            "job_scoped_manifest_artifact_and_preview_uris_match",
            "input_hash_unchanged",
            "script_hash_unchanged",
            "environment_hash_unchanged",
            "config_hash_changed_for_authored_revision",
            "initial_primary_immutable",
            "preview_max_edge_respected",
        )
    )
    initial_sha = witness["initial_render"]["artifact"]["sha256"]
    assert consistency["initial_primary_sha256_before_revision"] == initial_sha
    assert consistency["initial_primary_sha256_after_revision"] == initial_sha
    assert witness["cleanup"] == {
        "temporary_fixture_removed": True,
        "temporary_runtime_jobs_removed": True,
    }
    assert witness["result"] == {
        "live_model_preview_revision": "passed",
        "human_approval_requested": False,
        "human_approval_claimed": False,
        "publication_approval_claimed": False,
    }

    summary = measurement["evaluation_summary"]["preview_driven_revision"]
    assert summary["witness_path"] == witness_path.relative_to(Path(__file__).parents[1]).as_posix()
    assert summary["call_counts"] == witness["call_counts"]
    assert summary["invented_statistics"] is False
    assert summary["sha_consistency"] is True
    assert summary["initial_primary_immutable"] is True
    assert summary["temporary_workspace_cleaned"] is True
    assert summary["human_or_publication_approval_claimed"] is False
