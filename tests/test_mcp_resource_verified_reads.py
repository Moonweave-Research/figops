from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import hub_core.mcp.manifest_io as manifest_io
import hub_core.mcp.resources as resources_module
import hub_core.project_config_reader as project_config_reader
from hub_core.mcp import GraphHubMCPServer
from hub_core.mcp.transport import _handle_json_rpc
from tests._symlink import symlink_or_skip

CONFIG_TEXT = """\
project:
  name: Secure Resource
  role: module
  status: active
visual_style:
  target_format: nature
  profile: baseline
"""


def _project_id(server: GraphHubMCPServer) -> str:
    response = server.read_resource("figops://projects")
    projects = json.loads(response["contents"][0]["text"])["projects"]
    assert len(projects) == 1
    return projects[0]["project_id"]


def _resource_rpc(server: GraphHubMCPServer, uri: str) -> dict:
    return _handle_json_rpc(
        server,
        {"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": uri}},
    )


def _make_project(research_root: Path) -> Path:
    project = research_root / "01_Secure"
    project.mkdir(parents=True)
    (project / "project_config.yaml").write_text(CONFIG_TEXT, encoding="utf-8")
    return project


def _make_manifest(runtime_root: Path, job_id: str, text: str | None = None) -> Path:
    manifest = runtime_root / "mcp_jobs" / job_id / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(text or json.dumps({"job_id": job_id, "source_data_path": "input.csv"}), encoding="utf-8")
    return manifest


def test_project_config_resource_reads_one_prefetched_verified_descriptor(monkeypatch, tmp_path: Path) -> None:
    research_root = tmp_path / "research"
    runtime_root = tmp_path / "runtime"
    project = _make_project(research_root)
    runtime_root.mkdir()
    prefetch = Mock()
    monkeypatch.setattr(
        resources_module,
        "select_adapters",
        lambda _config: SimpleNamespace(prefetcher=prefetch),
    )
    server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)

    project_id = _project_id(server)
    result = server.read_resource(f"figops://projects/{project_id}/config")

    assert result["contents"] == [
        {
            "uri": f"figops://projects/{project_id}/config",
            "mimeType": "application/x-yaml",
            "text": CONFIG_TEXT,
        }
    ]
    prefetch.ensure_local.assert_called_once_with([str((project / "project_config.yaml").resolve())])


def test_project_config_validate_then_hardlink_swap_reads_zero_external_bytes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    research_root = tmp_path / "research"
    runtime_root = tmp_path / "runtime"
    project = _make_project(research_root)
    runtime_root.mkdir()
    external = tmp_path / "outside-secret.yaml"
    external.write_text("EXTERNAL_RESOURCE_SECRET: must-never-be-read\n", encoding="utf-8")
    server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)
    project_id = _project_id(server)
    original_snapshot = project_config_reader.snapshot_project_input
    original_open = project_config_reader.open_verified_project_input
    descriptor_yields: list[int] = []

    def snapshot_then_swap(*args, **kwargs):
        snapshot = original_snapshot(*args, **kwargs)
        config = project / "project_config.yaml"
        config.unlink()
        os.link(external, config)
        return snapshot

    @contextmanager
    def tracking_open(*args, **kwargs):
        with original_open(*args, **kwargs) as handle:
            descriptor_yields.append(handle.fileno())
            yield handle

    monkeypatch.setattr(project_config_reader, "snapshot_project_input", snapshot_then_swap)
    monkeypatch.setattr(project_config_reader, "open_verified_project_input", tracking_open)

    response = _resource_rpc(server, f"figops://projects/{project_id}/config")
    serialized = json.dumps(response, ensure_ascii=False)

    assert response["error"]["code"] == -32602
    assert descriptor_yields == []
    assert "EXTERNAL_RESOURCE_SECRET" not in serialized
    assert str(external) not in serialized
    assert str(research_root) not in serialized


def test_project_config_resource_rejects_preexisting_hardlink_before_prefetch(monkeypatch, tmp_path: Path) -> None:
    research_root = tmp_path / "research"
    runtime_root = tmp_path / "runtime"
    project = _make_project(research_root)
    runtime_root.mkdir()
    external = tmp_path / "outside-hardlink.yaml"
    external.write_text("PREEXISTING_HARDLINK_SECRET: must-never-be-read\n", encoding="utf-8")
    config = project / "project_config.yaml"
    config.unlink()
    os.link(external, config)
    server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)
    project_id = _project_id(server)
    prefetch = Mock()
    monkeypatch.setattr(
        resources_module,
        "select_adapters",
        lambda _config: SimpleNamespace(prefetcher=prefetch),
    )

    response = _resource_rpc(server, f"figops://projects/{project_id}/config")
    serialized = json.dumps(response, ensure_ascii=False)

    assert response["error"]["code"] == -32602
    prefetch.ensure_local.assert_not_called()
    assert "PREEXISTING_HARDLINK_SECRET" not in serialized
    assert str(external) not in serialized
    assert str(research_root) not in serialized


def test_project_config_resource_detects_post_read_path_replacement(monkeypatch, tmp_path: Path) -> None:
    research_root = tmp_path / "research"
    runtime_root = tmp_path / "runtime"
    project = _make_project(research_root)
    runtime_root.mkdir()
    replacement = tmp_path / "replacement.yaml"
    replacement.write_text("POST_READ_REPLACEMENT_SECRET: must-never-be-returned\n", encoding="utf-8")
    server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)
    project_id = _project_id(server)
    original_open = project_config_reader.open_verified_project_input

    @contextmanager
    def replace_after_read(*args, **kwargs):
        with original_open(*args, **kwargs) as handle:
            yield handle
        os.replace(replacement, project / "project_config.yaml")

    monkeypatch.setattr(project_config_reader, "open_verified_project_input", replace_after_read)

    response = _resource_rpc(server, f"figops://projects/{project_id}/config")
    serialized = json.dumps(response, ensure_ascii=False)

    assert response["error"]["code"] == -32602
    assert "POST_READ_REPLACEMENT_SECRET" not in serialized
    assert str(research_root) not in serialized


def test_project_config_resource_refuses_symlink_and_redacts_paths(tmp_path: Path) -> None:
    research_root = tmp_path / "research"
    runtime_root = tmp_path / "runtime"
    project = _make_project(research_root)
    runtime_root.mkdir()
    external = tmp_path / "outside-secret.yaml"
    external.write_text("SYMLINK_RESOURCE_SECRET: must-never-be-returned\n", encoding="utf-8")
    config = project / "project_config.yaml"
    config.unlink()
    symlink_or_skip(config, external)
    server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)
    project_id = _project_id(server)

    response = _resource_rpc(server, f"figops://projects/{project_id}/config")
    serialized = json.dumps(response, ensure_ascii=False)

    assert response["error"]["code"] == -32602
    assert "SYMLINK_RESOURCE_SECRET" not in serialized
    assert str(external) not in serialized
    assert str(research_root) not in serialized


@pytest.mark.skipif(os.name != "nt", reason="NTFS junction witness is Windows-specific")
def test_project_config_resource_refuses_junction_project(tmp_path: Path) -> None:
    research_root = tmp_path / "research"
    runtime_root = tmp_path / "runtime"
    external_project = tmp_path / "outside" / "01_Junction"
    external_project.mkdir(parents=True)
    (external_project / "project_config.yaml").write_text(CONFIG_TEXT, encoding="utf-8")
    research_root.mkdir()
    runtime_root.mkdir()
    junction = research_root / "01_Junction"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(external_project)],
        capture_output=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip("junction creation is unavailable")
    try:
        server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)
        projects = server.read_resource("figops://projects")
        payload = json.loads(projects["contents"][0]["text"])
        response = _resource_rpc(server, "figops://projects/01_Junction__not-discoverable/config")
        serialized = json.dumps({"projects": payload, "response": response}, ensure_ascii=False)

        assert payload["projects"] == []
        assert response["error"]["code"] == -32002
        assert str(external_project) not in serialized
        assert str(research_root) not in serialized
    finally:
        os.rmdir(junction)


def test_job_manifest_resource_uses_verified_reader_and_preserves_shape(tmp_path: Path) -> None:
    research_root = tmp_path / "research"
    runtime_root = tmp_path / "runtime"
    research_root.mkdir()
    manifest = _make_manifest(runtime_root, "safe-job")
    server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)

    result = server.read_resource("figops://jobs/safe-job/manifest")
    content = result["contents"][0]
    payload = json.loads(content["text"])

    assert content["uri"] == "figops://jobs/safe-job/manifest"
    assert content["mimeType"] == "application/json"
    assert payload["job_id"] == "safe-job"
    assert payload["source_data_path"] == "input.csv"
    assert str(manifest) not in content["text"]
    assert str(runtime_root) not in content["text"]


def test_job_manifest_validate_then_hardlink_swap_reads_zero_external_bytes(monkeypatch, tmp_path: Path) -> None:
    research_root = tmp_path / "research"
    runtime_root = tmp_path / "runtime"
    research_root.mkdir()
    manifest = _make_manifest(runtime_root, "swap-job")
    external = tmp_path / "outside-secret.json"
    external.write_text(
        json.dumps({"job_id": "swap-job", "secret": "EXTERNAL_MANIFEST_SECRET"}),
        encoding="utf-8",
    )
    server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)
    original_snapshot = manifest_io.snapshot_project_input
    original_open = manifest_io.open_verified_project_input
    descriptor_yields: list[int] = []

    def snapshot_then_swap(*args, **kwargs):
        snapshot = original_snapshot(*args, **kwargs)
        manifest.unlink()
        os.link(external, manifest)
        return snapshot

    @contextmanager
    def tracking_open(*args, **kwargs):
        with original_open(*args, **kwargs) as handle:
            descriptor_yields.append(handle.fileno())
            yield handle

    monkeypatch.setattr(manifest_io, "snapshot_project_input", snapshot_then_swap)
    monkeypatch.setattr(manifest_io, "open_verified_project_input", tracking_open)

    response = _resource_rpc(server, "figops://jobs/swap-job/manifest")
    serialized = json.dumps(response, ensure_ascii=False)

    assert response["error"]["code"] == -32603
    assert descriptor_yields == []
    assert "EXTERNAL_MANIFEST_SECRET" not in serialized
    assert str(external) not in serialized
    assert str(runtime_root) not in serialized


def test_job_manifest_resource_detects_post_read_path_replacement(monkeypatch, tmp_path: Path) -> None:
    research_root = tmp_path / "research"
    runtime_root = tmp_path / "runtime"
    research_root.mkdir()
    manifest = _make_manifest(runtime_root, "post-swap-job")
    replacement = tmp_path / "replacement-manifest.json"
    replacement.write_text(
        json.dumps({"job_id": "post-swap-job", "secret": "POST_READ_MANIFEST_SECRET"}),
        encoding="utf-8",
    )
    server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)
    original_open = manifest_io.open_verified_project_input

    @contextmanager
    def replace_after_read(*args, **kwargs):
        with original_open(*args, **kwargs) as handle:
            yield handle
        os.replace(replacement, manifest)

    monkeypatch.setattr(manifest_io, "open_verified_project_input", replace_after_read)

    response = _resource_rpc(server, "figops://jobs/post-swap-job/manifest")
    serialized = json.dumps(response, ensure_ascii=False)

    assert response["error"]["code"] == -32603
    assert "POST_READ_MANIFEST_SECRET" not in serialized
    assert str(runtime_root) not in serialized


def test_job_manifest_resource_rejects_preexisting_hardlink_without_returning_bytes(tmp_path: Path) -> None:
    research_root = tmp_path / "research"
    runtime_root = tmp_path / "runtime"
    research_root.mkdir()
    external = tmp_path / "outside-manifest.json"
    external.write_text(
        json.dumps({"job_id": "linked-job", "secret": "PREEXISTING_MANIFEST_SECRET"}),
        encoding="utf-8",
    )
    manifest = runtime_root / "mcp_jobs" / "linked-job" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    os.link(external, manifest)
    server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)

    response = _resource_rpc(server, "figops://jobs/linked-job/manifest")
    serialized = json.dumps(response, ensure_ascii=False)

    assert response["error"]["code"] == -32603
    assert "PREEXISTING_MANIFEST_SECRET" not in serialized
    assert str(external) not in serialized
    assert str(runtime_root) not in serialized


@pytest.mark.parametrize(
    "text",
    [
        '{"job_id":"strict-job","job_id":"strict-job"}',
        '{"job_id":"different-job"}',
    ],
)
def test_job_manifest_resource_rejects_duplicate_keys_and_wrong_job_id(tmp_path: Path, text: str) -> None:
    research_root = tmp_path / "research"
    runtime_root = tmp_path / "runtime"
    research_root.mkdir()
    _make_manifest(runtime_root, "strict-job", text)
    server = GraphHubMCPServer(research_root=research_root, runtime_root=runtime_root)

    response = _resource_rpc(server, "figops://jobs/strict-job/manifest")

    assert response["error"]["code"] == -32603
    assert str(runtime_root) not in json.dumps(response, ensure_ascii=False)
