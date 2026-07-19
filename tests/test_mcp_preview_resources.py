from __future__ import annotations

import base64
import hashlib
import json
import sys
from types import ModuleType
from typing import Any

import pytest

from hub_core.mcp import GraphHubMCPServer
from hub_core.mcp.transport import _handle_json_rpc


def _write_runtime_preview(runtime_root, *, job_id: str = "actual-job", include_contract: bool = True) -> bytes:
    from PIL import Image

    job_root = runtime_root / "mcp_jobs" / job_id
    job_root.mkdir(parents=True)
    image_path = job_root / "figure.png"
    Image.new("RGB", (3, 2), color=(17, 34, 51)).save(image_path, format="PNG")
    raw = image_path.read_bytes()
    manifest: dict[str, Any] = {
        "job_id": job_id,
        "figures": [str(image_path)],
    }
    if include_contract:
        manifest["preview_artifacts"] = [
            {
                "logical_role": "primary",
                "relative_path": "figure.png",
                "media_type": "image/png",
                "byte_size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        ]
    (job_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return raw


class _FakeMetadata:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def as_dict(self) -> dict[str, Any]:
        return dict(self.payload)


class _FakeBlob:
    def __init__(
        self,
        metadata: _FakeMetadata,
        *,
        data_base64: str | None,
        preview_media_type: str | None,
        raw_byte_size: int | None = None,
        encoded_byte_size: int | None = None,
    ) -> None:
        self.metadata = metadata
        self.data_base64 = data_base64
        self.preview_media_type = preview_media_type
        if data_base64 is not None:
            encoded_byte_size = len(data_base64.encode("ascii")) if encoded_byte_size is None else encoded_byte_size
            raw_byte_size = len(base64.b64decode(data_base64)) if raw_byte_size is None else raw_byte_size
        self.raw_byte_size = raw_byte_size
        self.encoded_byte_size = encoded_byte_size

    def as_dict(self, *, include_data: bool) -> dict[str, Any]:
        payload = {
            "metadata": self.metadata.as_dict(),
            "preview_media_type": self.preview_media_type,
            "raw_byte_size": self.raw_byte_size,
            "encoded_byte_size": self.encoded_byte_size,
            "width": None,
            "height": None,
        }
        if include_data:
            payload["data_base64"] = self.data_base64
        return payload


def _metadata(*, availability: str = "available", source_media_type: str = "image/png") -> _FakeMetadata:
    return _FakeMetadata(
        {
            "availability": availability,
            "code": "PREVIEW_AVAILABLE" if availability == "available" else "PREVIEW_NOT_FOUND",
            "reason": "" if availability == "available" else "Preview artifact is unavailable.",
            "resolution_hint": "" if availability == "available" else "Render the requested artifact.",
            "job_id": "job-1",
            "logical_role": "primary",
            "artifact_index": 0,
            "source_media_type": source_media_type,
            "source_byte_size": 68,
            "source_sha256": "a" * 64,
            "memory_limit_bytes": 256 * 1024 * 1024,
            "memory_limit_enforced": None,
            "preview_uri": "figops://jobs/job-1/previews/primary/0",
        }
    )


@pytest.fixture
def preview_core(monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleType, dict[str, list[tuple[Any, ...]]]]:
    calls: dict[str, list[tuple[Any, ...]]] = {"describe": [], "read": []}
    module = ModuleType("hub_core.mcp.preview_artifacts")

    def describe(runtime_root: Any, job_id: str, *, logical_role: str, artifact_index: int) -> _FakeMetadata:
        calls["describe"].append((runtime_root, job_id, logical_role, artifact_index))
        return _metadata()

    def read(runtime_root: Any, job_id: str, *, logical_role: str, artifact_index: int) -> _FakeBlob:
        calls["read"].append((runtime_root, job_id, logical_role, artifact_index))
        return _FakeBlob(
            _metadata(),
            data_base64="iVBORw0KGgo=",
            preview_media_type="image/png",
            raw_byte_size=8,
            encoded_byte_size=12,
        )

    module.MAX_PREVIEW_BASE64_BYTES = 2_796_204
    module.MAX_PREVIEW_RAW_BYTES = 2 * 1024 * 1024
    module.describe_job_preview = describe
    module.read_job_preview_blob = read
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module, calls


def _read_rpc(server: GraphHubMCPServer, uri: str) -> dict[str, Any]:
    return _handle_json_rpc(
        server,
        {"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": uri}},
    )


def test_artifact_resource_is_metadata_only_and_does_not_generate_blob(tmp_path, preview_core) -> None:
    _, calls = preview_core
    server = GraphHubMCPServer(runtime_root=tmp_path, write_tools_enabled=False)

    response = _read_rpc(server, "figops://jobs/job-1/artifacts/primary/0")

    content = response["result"]["contents"][0]
    payload = json.loads(content["text"])
    assert content["mimeType"] == "application/json"
    assert "blob" not in content
    assert payload["preview_uri"] == "figops://jobs/job-1/previews/primary/0"
    assert calls["describe"] == [(tmp_path.resolve(), "job-1", "primary", 0)]
    assert calls["read"] == []


def test_preview_resource_generates_blob_only_when_read(tmp_path, preview_core) -> None:
    _, calls = preview_core
    server = GraphHubMCPServer(runtime_root=tmp_path, write_tools_enabled=False)

    response = _read_rpc(server, "figops://jobs/job-1/previews/primary/0")

    content = response["result"]["contents"][0]
    assert content == {
        "uri": "figops://jobs/job-1/previews/primary/0",
        "mimeType": "image/png",
        "blob": "iVBORw0KGgo=",
    }
    assert calls["describe"] == []
    assert calls["read"] == [(tmp_path.resolve(), "job-1", "primary", 0)]


def test_unavailable_preview_returns_typed_metadata_without_blob(tmp_path, preview_core) -> None:
    module, calls = preview_core

    def unavailable(*args: Any, **kwargs: Any) -> _FakeBlob:
        calls["read"].append((*args, kwargs))
        return _FakeBlob(_metadata(availability="unavailable"), data_base64=None, preview_media_type=None)

    module.read_job_preview_blob = unavailable
    server = GraphHubMCPServer(runtime_root=tmp_path, write_tools_enabled=False)

    response = _read_rpc(server, "figops://jobs/job-1/previews/primary/0")

    content = response["result"]["contents"][0]
    payload = json.loads(content["text"])
    assert content["mimeType"] == "application/json"
    assert "blob" not in content
    assert "data_base64" not in payload
    assert payload["metadata"]["availability"] == "unavailable"


def test_svg_source_is_never_returned_as_active_content(tmp_path, preview_core) -> None:
    module, _ = preview_core
    module.describe_job_preview = lambda *args, **kwargs: _metadata(source_media_type="image/svg+xml")
    module.read_job_preview_blob = lambda *args, **kwargs: _FakeBlob(
        _metadata(source_media_type="image/svg+xml"),
        data_base64="iVBORw0KGgo=",
        preview_media_type="image/png",
    )
    server = GraphHubMCPServer(runtime_root=tmp_path, write_tools_enabled=False)

    metadata_response = _read_rpc(server, "figops://jobs/job-1/artifacts/primary/0")
    preview_response = _read_rpc(server, "figops://jobs/job-1/previews/primary/0")

    metadata_content = metadata_response["result"]["contents"][0]
    preview_content = preview_response["result"]["contents"][0]
    assert metadata_content["mimeType"] == "application/json"
    assert "blob" not in metadata_content
    assert "<svg" not in metadata_content["text"].lower()
    assert preview_content["mimeType"] == "image/png"


@pytest.mark.parametrize(
    "uri",
    [
        "figops://jobs/../previews/primary/0",
        "figops://jobs/%2E%2E/previews/primary/0",
        "figops://jobs/job-1/previews/%2E%2E/0",
        "figops://jobs/job-1/previews/primary/-1",
        "figops://jobs/job-1/previews/primary/00",
        "figops://jobs/job-1/previews/primary/1.0",
        "figops://jobs/job-1/previews/primary/256",
        "figops://jobs/job-1/previews/primary/1000000",
        "figops://jobs/job-1/previews/primary/0/extra",
        "figops://jobs/job-1/artifacts/foo%2Fbar/0",
        "figops://jobs/job-1/source/primary/0",
        "figops://jobs/job-1/previews/primary/0?raw=1",
    ],
)
def test_preview_resource_rejects_path_like_or_noncanonical_addresses(tmp_path, preview_core, uri: str) -> None:
    _, calls = preview_core
    server = GraphHubMCPServer(runtime_root=tmp_path, write_tools_enabled=False)

    response = _read_rpc(server, uri)

    assert response["error"]["code"] == -32602
    assert calls == {"describe": [], "read": []}


def test_preview_worker_exception_is_redacted(tmp_path, preview_core) -> None:
    module, _ = preview_core
    secret_path = tmp_path / "private" / "secret.svg"

    def fail(*args: Any, **kwargs: Any) -> _FakeBlob:
        raise RuntimeError(f"could not open {secret_path}: SUPER_SECRET")

    module.read_job_preview_blob = fail
    server = GraphHubMCPServer(runtime_root=tmp_path, write_tools_enabled=False)

    response = _read_rpc(server, "figops://jobs/job-1/previews/primary/0")
    serialized = json.dumps(response)

    assert response["error"]["code"] == -32603
    assert str(secret_path) not in serialized
    assert "SUPER_SECRET" not in serialized
    assert "Preview blob could not be read safely" in response["error"]["message"]


def test_preview_resource_refuses_non_raster_blob_media(tmp_path, preview_core) -> None:
    module, _ = preview_core
    module.read_job_preview_blob = lambda *args, **kwargs: _FakeBlob(
        _metadata(source_media_type="image/svg+xml"),
        data_base64="PHN2Zz48L3N2Zz4=",
        preview_media_type="image/svg+xml",
    )
    server = GraphHubMCPServer(runtime_root=tmp_path, write_tools_enabled=False)

    response = _read_rpc(server, "figops://jobs/job-1/previews/primary/0")

    assert response["error"]["code"] == -32603
    assert "disallowed media type" in response["error"]["message"]


def test_preview_resource_rechecks_encoded_limit_at_transport_boundary(tmp_path, preview_core) -> None:
    module, _ = preview_core
    module.MAX_PREVIEW_BASE64_BYTES = 4
    server = GraphHubMCPServer(runtime_root=tmp_path, write_tools_enabled=False)

    response = _read_rpc(server, "figops://jobs/job-1/previews/primary/0")

    assert response["error"]["code"] == -32603
    assert "invalid blob payload" in response["error"]["message"]


@pytest.mark.parametrize(
    "blob",
    [
        _FakeBlob(
            _metadata(),
            data_base64="iVBORw0KGgo=",
            preview_media_type="image/png",
            encoded_byte_size=11,
        ),
        _FakeBlob(
            _metadata(),
            data_base64="bm90LXBuZw==",
            preview_media_type="image/png",
        ),
    ],
)
def test_preview_resource_rechecks_size_metadata_and_magic(tmp_path, preview_core, blob: _FakeBlob) -> None:
    module, _ = preview_core
    module.read_job_preview_blob = lambda *args, **kwargs: blob
    server = GraphHubMCPServer(runtime_root=tmp_path, write_tools_enabled=False)

    response = _read_rpc(server, "figops://jobs/job-1/previews/primary/0")

    assert response["error"]["code"] == -32603
    assert "inconsistent bounded blob metadata" in response["error"]["message"]


def test_actual_manifest_metadata_and_blob_resources_work_with_writes_disabled(tmp_path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    _write_runtime_preview(runtime_root)
    before = {path.relative_to(runtime_root): path.read_bytes() for path in runtime_root.rglob("*") if path.is_file()}
    server = GraphHubMCPServer(runtime_root=runtime_root, write_tools_enabled=False)

    metadata_response = _read_rpc(server, "figops://jobs/actual-job/artifacts/primary/0")
    metadata_content = metadata_response["result"]["contents"][0]
    metadata = json.loads(metadata_content["text"])
    preview_response = _read_rpc(server, "figops://jobs/actual-job/previews/primary/0")
    preview_content = preview_response["result"]["contents"][0]

    assert metadata["availability"] == "available"
    assert metadata["source_media_type"] == "image/png"
    assert metadata["preview_uri"] == "figops://jobs/actual-job/previews/primary/0"
    assert metadata_content["mimeType"] == "application/json"
    assert "blob" not in metadata_content
    assert preview_content["mimeType"] == "image/png"
    assert base64.b64decode(preview_content["blob"], validate=True).startswith(b"\x89PNG\r\n\x1a\n")
    assert server.write_tools_enabled is False
    after = {path.relative_to(runtime_root): path.read_bytes() for path in runtime_root.rglob("*") if path.is_file()}
    assert after == before


def test_figures_field_is_not_a_preview_membership_fallback(tmp_path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    _write_runtime_preview(runtime_root, job_id="legacy-only", include_contract=False)
    server = GraphHubMCPServer(runtime_root=runtime_root, write_tools_enabled=False)

    metadata_response = _read_rpc(server, "figops://jobs/legacy-only/artifacts/primary/0")
    preview_response = _read_rpc(server, "figops://jobs/legacy-only/previews/primary/0")
    metadata = json.loads(metadata_response["result"]["contents"][0]["text"])
    preview = json.loads(preview_response["result"]["contents"][0]["text"])

    assert metadata["availability"] == "unavailable"
    assert metadata["code"] == "ARTIFACT_NOT_DECLARED"
    assert preview["metadata"]["availability"] == "unavailable"
    assert preview["metadata"]["code"] == "ARTIFACT_NOT_DECLARED"
    assert "blob" not in preview_response["result"]["contents"][0]
