from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hub_core.mcp import GraphHubMCPServer
from themes.style_packs import INTERNAL_STYLE_TARGET_FORMAT

VALID_CONFIG = """
project:
  name: Verified Read
visual_style:
  target_format: {target_format}
  font_scale: 1.0
  profile: baseline
data_contract:
  csv_checks:
    - path: results/data/summary.csv
      required_columns: [x, y]
sample_registry:
  - sample_id: sample-a
experimental_conditions:
  conditions:
    - id: condition-a
      parameters: {{}}
figures:
  - id: Fig1
    script: hub_scripts/plot.py
    output: results/figures/Fig1.png
    claim: The declared relationship is preserved.
    samples: [sample-a]
    conditions: [condition-a]
"""


def _write_project(root: Path) -> Path:
    project = root / "01_Verified"
    project.mkdir(parents=True)
    (project / "project_config.yaml").write_text(
        VALID_CONFIG.format(target_format=INTERNAL_STYLE_TARGET_FORMAT),
        encoding="utf-8",
    )
    return project


def _server(root: Path) -> GraphHubMCPServer:
    return GraphHubMCPServer(
        research_root=root / "research",
        runtime_root=root / "runtime",
        write_tools_enabled=False,
        surface_profile="compatibility",
    )


def _structured(server: GraphHubMCPServer, name: str, arguments: dict) -> dict:
    return server.call_tool(name, arguments)["structuredContent"]


def test_list_inspect_validate_and_compatibility_aliases_never_path_reopen_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    research = tmp_path / "research"
    project = _write_project(research)
    server = _server(tmp_path)
    original_read_text = Path.read_text

    def reject_config_reopen(path: Path, *args, **kwargs):
        if path.name == "project_config.yaml":
            raise AssertionError("project config was reopened by pathname")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reject_config_reopen)
    calls = (
        ("figops.list_projects", {"root": str(research)}),
        ("graphhub.list_projects", {"root": str(research)}),
        ("figops.inspect_project", {"project_path": str(project)}),
        ("graphhub.inspect_project", {"project_path": str(project)}),
        ("figops.validate_project", {"project_path": str(project)}),
        ("graphhub.validate_project", {"project_path": str(project)}),
    )
    for name, arguments in calls:
        result = server.call_tool(name, arguments)
        assert result["isError"] is False, (name, result["structuredContent"])
        assert "reopened by pathname" not in json.dumps(result["structuredContent"])


def test_project_config_hardlink_is_rejected_before_prefetch_and_external_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    research = tmp_path / "research"
    project = research / "01_Hardlink"
    project.mkdir(parents=True)
    external = tmp_path / "external-secret.yaml"
    external.write_text("external_secret_marker: never-read\n", encoding="utf-8")
    os.link(external, project / "project_config.yaml")
    prefetch_calls: list[list[str]] = []

    monkeypatch.setattr(
        "hub_core.project_config_reader.NoopPrefetcher.ensure_local",
        lambda _self, paths: prefetch_calls.append(paths),
    )
    result = _server(tmp_path).call_tool("figops.inspect_project", {"project_path": str(project)})

    assert result["isError"] is True
    assert prefetch_calls == []
    serialized = json.dumps(result["structuredContent"], ensure_ascii=False)
    assert "external_secret_marker" not in serialized
    assert str(external) not in serialized


def test_project_config_swap_after_prefetch_never_reaches_yaml_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hub_core import project_config_reader

    research = tmp_path / "research"
    project = _write_project(research)
    config = project / "project_config.yaml"
    external = tmp_path / "external-swap.yaml"
    external.write_text("external_secret_marker: never-parse\n", encoding="utf-8")
    original_snapshot = project_config_reader.snapshot_project_input
    parse_calls = 0

    def snapshot_then_swap(*args, **kwargs):
        snapshot = original_snapshot(*args, **kwargs)
        config.unlink()
        os.link(external, config)
        return snapshot

    def count_parse(*_args, **_kwargs):
        nonlocal parse_calls
        parse_calls += 1
        raise AssertionError("swapped config bytes reached YAML parser")

    monkeypatch.setattr(project_config_reader, "snapshot_project_input", snapshot_then_swap)
    monkeypatch.setattr("hub_core.mcp.tools.read_tools.load_yaml_with_unique_keys", count_parse)
    result = _server(tmp_path).call_tool("figops.inspect_project", {"project_path": str(project)})

    assert result["isError"] is True
    assert parse_calls == 0
    serialized = json.dumps(result["structuredContent"], ensure_ascii=False)
    assert "external_secret_marker" not in serialized
    assert str(external) not in serialized


def _write_job_manifest(runtime_root: Path, job_id: str, payload: dict | None = None) -> Path:
    job_root = runtime_root / "mcp_jobs" / job_id
    job_root.mkdir(parents=True)
    manifest = {
        "job_id": job_id,
        "artifact_status": "created",
        "figures": [],
        "geometry_diagnostics": {"schema_version": "geometry_diagnostics/1", "passed": True, "checks": []},
        "visual_preflight_status": {"passed": True},
        "layout_report": {"schema_version": "layout_report/1", "passed": True},
    }
    manifest.update(payload or {})
    path = job_root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "tool_name",
    [
        "figops.collect_artifacts",
        "graphhub.collect_artifacts",
        "figops.evaluate_publication_readiness",
    ],
)
def test_job_manifest_hardlink_is_rejected_before_json_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
) -> None:
    from hub_core.mcp import manifest_io

    runtime = tmp_path / "runtime"
    job_id = "hardlink-job"
    job_root = runtime / "mcp_jobs" / job_id
    job_root.mkdir(parents=True)
    external = tmp_path / "external-secret.json"
    external.write_text(json.dumps({"job_id": job_id, "external_secret_marker": True}), encoding="utf-8")
    os.link(external, job_root / "manifest.json")
    parse_calls = 0
    original_parse = manifest_io._parse_json_object

    def count_parse(payload: bytes):
        nonlocal parse_calls
        parse_calls += 1
        return original_parse(payload)

    monkeypatch.setattr(manifest_io, "_parse_json_object", count_parse)
    result = _server(tmp_path).call_tool(tool_name, {"job_id": job_id})

    assert result["isError"] is True
    assert parse_calls == 0
    serialized = json.dumps(result["structuredContent"], ensure_ascii=False)
    assert "external_secret_marker" not in serialized
    assert str(external) not in serialized


@pytest.mark.parametrize(
    "tool_name",
    [
        "figops.collect_artifacts",
        "graphhub.collect_artifacts",
        "figops.evaluate_publication_readiness",
    ],
)
def test_job_manifest_path_swap_never_reaches_json_parser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
) -> None:
    from hub_core.mcp import manifest_io

    runtime = tmp_path / "runtime"
    job_id = "swap-job"
    manifest = _write_job_manifest(runtime, job_id)
    external = tmp_path / "external-swap.json"
    external.write_text(json.dumps({"job_id": job_id, "external_secret_marker": True}), encoding="utf-8")
    original_snapshot = manifest_io.snapshot_project_input
    parse_calls = 0

    def snapshot_then_swap(*args, **kwargs):
        snapshot = original_snapshot(*args, **kwargs)
        manifest.unlink()
        os.link(external, manifest)
        return snapshot

    def count_parse(_payload: bytes):
        nonlocal parse_calls
        parse_calls += 1
        raise AssertionError("swapped manifest bytes reached JSON parser")

    monkeypatch.setattr(manifest_io, "snapshot_project_input", snapshot_then_swap)
    monkeypatch.setattr(manifest_io, "_parse_json_object", count_parse)
    result = _server(tmp_path).call_tool(tool_name, {"job_id": job_id})

    assert result["isError"] is True
    assert parse_calls == 0
    serialized = json.dumps(result["structuredContent"], ensure_ascii=False)
    assert "external_secret_marker" not in serialized
    assert str(external) not in serialized


def test_collect_and_readiness_preserve_normal_verified_manifest_behavior(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    job_id = "normal-job"
    _write_job_manifest(runtime, job_id)
    server = _server(tmp_path)

    collected = server.call_tool("figops.collect_artifacts", {"job_id": job_id})
    readiness = server.call_tool("figops.evaluate_publication_readiness", {"job_id": job_id})

    assert collected["isError"] is False
    assert collected["structuredContent"]["job_id"] == job_id
    assert readiness["isError"] is True
    assert readiness["structuredContent"]["readiness_report"]["readiness_status"] == "blocked"


def _assert_job_ambiguity_for_all_consumers(server: GraphHubMCPServer, job_id: str) -> None:
    for tool_name in (
        "figops.collect_artifacts",
        "graphhub.collect_artifacts",
        "figops.evaluate_publication_readiness",
    ):
        result = server.call_tool(tool_name, {"job_id": job_id})
        assert result["isError"] is True
        assert result["structuredContent"]["error_code"] == "JOB_AMBIGUOUS"
        assert "JOB_AMBIGUOUS" in " ".join(result["structuredContent"]["errors"])

    for scheme in ("figops", "graphhub"):
        with pytest.raises(ValueError, match="JOB_AMBIGUOUS"):
            server.read_resource(f"{scheme}://jobs/{job_id}/manifest")


def test_duplicate_job_id_across_runtime_job_kinds_is_ambiguous(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    job_id = "duplicate-kind"
    _write_job_manifest(runtime, job_id)
    project_job = runtime / "mcp_project_jobs" / job_id
    project_job.mkdir(parents=True)
    (project_job / "manifest.json").write_text(json.dumps({"job_id": job_id}), encoding="utf-8")

    _assert_job_ambiguity_for_all_consumers(_server(tmp_path), job_id)


def test_duplicate_job_id_across_runtime_roots_is_ambiguous(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = tmp_path / "runtime"
    fallback = tmp_path / "fallback-runtime"
    job_id = "duplicate-root"
    _write_job_manifest(runtime, job_id)
    _write_job_manifest(fallback, job_id)
    server = _server(tmp_path)
    server._runtime_root_explicit = False
    monkeypatch.setattr(
        "hub_core.mcp.tools.batch_tools.runtime_root_lookup_candidates",
        lambda: (fallback,),
    )

    _assert_job_ambiguity_for_all_consumers(server, job_id)
