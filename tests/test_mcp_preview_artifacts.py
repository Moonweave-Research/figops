from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from PIL import Image

from hub_core.mcp import preview_artifacts as previews


def _image_bytes(tmp_path: Path, *, size: tuple[int, int] = (32, 24), format: str = "PNG") -> bytes:
    path = tmp_path / f"fixture.{format.lower()}"
    Image.new("RGB", size, "#2952a3").save(path, format=format)
    return path.read_bytes()


def _job(
    tmp_path: Path,
    payload: bytes,
    *,
    suffix: str = ".png",
    media_type: str = "image/png",
    job_id: str = "preview-job",
    kind: str = "mcp_jobs",
    role: str = "primary",
    entry_updates: dict[str, object] | None = None,
) -> tuple[Path, Path, Path]:
    runtime = tmp_path / "runtime"
    job_root = runtime / kind / job_id
    artifact = job_root / "results" / f"figure{suffix}"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(payload)
    entry: dict[str, object] = {
        "logical_role": role,
        "relative_path": f"results/figure{suffix}",
        "media_type": media_type,
        "byte_size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    entry.update(entry_updates or {})
    manifest = {"job_id": job_id, "preview_artifacts": [entry]}
    (job_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return runtime, job_root, artifact


def test_describe_is_metadata_only_and_does_not_start_worker(monkeypatch, tmp_path: Path) -> None:
    runtime, _, _ = _job(tmp_path, _image_bytes(tmp_path))
    monkeypatch.setattr(previews, "_run_worker", lambda *args: pytest.fail("describe must stay lazy"))

    result = previews.describe_job_preview(runtime, "preview-job", logical_role="primary", artifact_index=0)

    assert result.availability == "available"
    assert result.preview_uri == "figops://jobs/preview-job/previews/primary/0"
    assert "data" not in result.as_dict()
    assert result.memory_limit_enforced is None


def test_raster_blob_is_bounded_and_memory_limited(tmp_path: Path) -> None:
    runtime, _, _ = _job(tmp_path, _image_bytes(tmp_path, size=(640, 480)))

    blob = previews.read_job_preview_blob(runtime, "preview-job", logical_role="primary", artifact_index=0)

    assert blob.available
    assert blob.metadata.memory_limit_enforced is True
    assert blob.raw_byte_size is not None and blob.raw_byte_size <= previews.MAX_PREVIEW_RAW_BYTES
    assert blob.encoded_byte_size is not None and blob.encoded_byte_size <= previews.MAX_PREVIEW_BASE64_BYTES
    assert blob.width is not None and blob.width <= previews.MAX_PREVIEW_EDGE
    assert blob.height is not None and blob.height <= previews.MAX_PREVIEW_EDGE


def test_preview_worker_temp_is_scoped_below_runtime(monkeypatch, tmp_path: Path) -> None:
    runtime, _, _ = _job(tmp_path, _image_bytes(tmp_path))
    observed: list[Path] = []
    real_temporary_directory = tempfile.TemporaryDirectory

    def scoped_temp(*args, **kwargs):
        observed.append(Path(kwargs["dir"]).resolve())
        return real_temporary_directory(*args, **kwargs)

    monkeypatch.setattr(previews.tempfile, "TemporaryDirectory", scoped_temp)
    blob = previews.read_job_preview_blob(runtime, "preview-job", logical_role="primary", artifact_index=0)

    assert blob.available
    assert observed == [(runtime / "previews" / "temp").resolve()]


def test_preview_read_does_not_modify_primary_artifact(tmp_path: Path) -> None:
    runtime, _, artifact = _job(tmp_path, _image_bytes(tmp_path, size=(640, 480)))
    before = (artifact.read_bytes(), artifact.stat().st_mtime_ns, artifact.stat().st_size)
    blob = previews.read_job_preview_blob(runtime, "preview-job", logical_role="primary", artifact_index=0)
    after = (artifact.read_bytes(), artifact.stat().st_mtime_ns, artifact.stat().st_size)
    assert blob.available
    assert after == before


@pytest.mark.parametrize("job_id", ["", "../escape", "a/b", "a\\b", "x" * 81])
def test_invalid_job_id_is_typed_unavailable(tmp_path: Path, job_id: str) -> None:
    tmp_path.mkdir(exist_ok=True)
    result = previews.describe_job_preview(tmp_path, job_id, logical_role="primary", artifact_index=0)
    assert result.availability == "unavailable"
    assert result.code == "SELECTOR_INVALID"
    assert result.job_id == ""


def test_unknown_and_ambiguous_jobs_fail_closed(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    missing = previews.describe_job_preview(runtime, "missing", logical_role="primary", artifact_index=0)
    assert missing.code == "JOB_NOT_FOUND"

    payload = _image_bytes(tmp_path)
    _job(tmp_path, payload, job_id="same", kind="mcp_jobs")
    _job(tmp_path, payload, job_id="same", kind="mcp_project_jobs")
    ambiguous = previews.describe_job_preview(runtime, "same", logical_role="primary", artifact_index=0)
    assert ambiguous.code == "JOB_AMBIGUOUS"


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"byte_size": 1}, "ARTIFACT_SIZE_MISMATCH"),
        ({"sha256": "0" * 64}, "ARTIFACT_HASH_MISMATCH"),
        ({"media_type": "image/jpeg"}, "MEDIA_TYPE_MISMATCH"),
        ({"relative_path": "../outside.png"}, "ARTIFACT_UNSAFE"),
        ({"relative_path": "C:/outside.png"}, "ARTIFACT_UNSAFE"),
    ],
)
def test_manifest_integrity_mismatch_is_typed_unavailable(
    tmp_path: Path, updates: dict[str, object], expected: str
) -> None:
    runtime, _, _ = _job(tmp_path, _image_bytes(tmp_path), entry_updates=updates)
    result = previews.describe_job_preview(runtime, "preview-job", logical_role="primary", artifact_index=0)
    assert result.code == expected


def test_figures_without_strict_preview_membership_are_not_accepted(tmp_path: Path) -> None:
    runtime, job_root, artifact = _job(tmp_path, _image_bytes(tmp_path))
    (job_root / "manifest.json").write_text(
        json.dumps({"job_id": "preview-job", "figures": [{"path": str(artifact)}]}), encoding="utf-8"
    )
    result = previews.describe_job_preview(runtime, "preview-job", logical_role="primary", artifact_index=0)
    assert result.code == "ARTIFACT_NOT_DECLARED"


def test_role_and_global_index_are_bound_together(tmp_path: Path) -> None:
    runtime, _, _ = _job(tmp_path, _image_bytes(tmp_path), role="primary")
    wrong_role = previews.describe_job_preview(runtime, "preview-job", logical_role="alternate", artifact_index=0)
    wrong_index = previews.describe_job_preview(runtime, "preview-job", logical_role="primary", artifact_index=1)
    assert wrong_role.code == "ARTIFACT_NOT_DECLARED"
    assert wrong_index.code == "ARTIFACT_NOT_DECLARED"


def test_artifact_symlink_is_rejected(tmp_path: Path) -> None:
    runtime, _, artifact = _job(tmp_path, _image_bytes(tmp_path))
    outside = tmp_path / "outside.png"
    outside.write_bytes(artifact.read_bytes())
    artifact.unlink()
    try:
        artifact.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    result = previews.describe_job_preview(runtime, "preview-job", logical_role="primary", artifact_index=0)
    assert result.code == "ARTIFACT_UNSAFE"


def test_source_change_between_describe_and_read_fails_closed(monkeypatch, tmp_path: Path) -> None:
    runtime, _, artifact = _job(tmp_path, _image_bytes(tmp_path))
    original = previews._copy_verified_source

    def swap(selection: object, destination: Path) -> None:
        artifact.write_bytes(b"changed")
        original(selection, destination)  # type: ignore[arg-type]

    monkeypatch.setattr(previews, "_copy_verified_source", swap)
    blob = previews.read_job_preview_blob(runtime, "preview-job", logical_role="primary", artifact_index=0)
    assert blob.metadata.code in {"ARTIFACT_SIZE_MISMATCH", "ARTIFACT_HASH_MISMATCH"}


def test_excessive_decoded_pixels_fail_in_bounded_worker(tmp_path: Path) -> None:
    runtime, _, _ = _job(tmp_path, _image_bytes(tmp_path, size=(3000, 3000)))
    blob = previews.read_job_preview_blob(runtime, "preview-job", logical_role="primary", artifact_index=0)
    assert blob.metadata.code == "PREVIEW_PIXEL_LIMIT"


def test_corrupt_raster_with_valid_magic_is_typed_decode_failure(tmp_path: Path) -> None:
    corrupt = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
    runtime, _, _ = _job(tmp_path, corrupt)
    described = previews.describe_job_preview(runtime, "preview-job", logical_role="primary", artifact_index=0)
    blob = previews.read_job_preview_blob(runtime, "preview-job", logical_role="primary", artifact_index=0)
    assert described.availability == "available"
    assert blob.metadata.code == "RASTER_DECODE_FAILED"


def test_source_and_manifest_byte_limits_are_typed(tmp_path: Path) -> None:
    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * previews.MAX_PREVIEW_SOURCE_BYTES
    runtime, _, _ = _job(tmp_path / "source", oversized)
    source_result = previews.describe_job_preview(runtime, "preview-job", logical_role="primary", artifact_index=0)
    assert source_result.code == "SOURCE_BYTE_LIMIT"

    payload = _image_bytes(tmp_path)
    runtime2, job_root, _ = _job(tmp_path / "manifest", payload)
    manifest_path = job_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["padding"] = "x" * previews.MAX_PREVIEW_MANIFEST_BYTES
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    manifest_result = previews.describe_job_preview(runtime2, "preview-job", logical_role="primary", artifact_index=0)
    assert manifest_result.code == "MANIFEST_INVALID"


def test_public_read_enforces_raw_and_base64_caps(monkeypatch, tmp_path: Path) -> None:
    payload = _image_bytes(tmp_path)
    runtime, _, _ = _job(tmp_path, payload)

    def oversized_worker(source: Path, output: Path, result: Path, media: str) -> tuple[dict[str, object], bool]:
        output.write_bytes(b"0" * (previews.MAX_PREVIEW_RAW_BYTES + 1))
        return {"status": "available"}, True

    monkeypatch.setattr(previews, "_run_worker", oversized_worker)
    raw_result = previews.read_job_preview_blob(runtime, "preview-job", logical_role="primary", artifact_index=0)
    assert raw_result.metadata.code == "PREVIEW_BYTE_LIMIT"

    def valid_worker(source: Path, output: Path, result: Path, media: str) -> tuple[dict[str, object], bool]:
        output.write_bytes(payload)
        return {"status": "available"}, True

    monkeypatch.setattr(previews, "_run_worker", valid_worker)
    monkeypatch.setattr(previews.base64, "b64encode", lambda raw: b"x" * (previews.MAX_PREVIEW_BASE64_BYTES + 1))
    encoded_result = previews.read_job_preview_blob(runtime, "preview-job", logical_role="primary", artifact_index=0)
    assert encoded_result.metadata.code == "PREVIEW_BASE64_LIMIT"


def test_safe_and_active_svg_are_explicitly_unavailable(tmp_path: Path) -> None:
    safe = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><path d="M0 0"/></svg>'
    runtime, _, _ = _job(tmp_path, safe, suffix=".svg", media_type="image/svg+xml")
    described = previews.describe_job_preview(runtime, "preview-job", logical_role="primary", artifact_index=0)
    read = previews.read_job_preview_blob(runtime, "preview-job", logical_role="primary", artifact_index=0)
    assert described.code == "SVG_RENDERER_UNAVAILABLE"
    assert read.metadata.code == "SVG_RENDERER_UNAVAILABLE"

    active = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    runtime2, _, _ = _job(tmp_path / "active", active, suffix=".svg", media_type="image/svg+xml")
    read2 = previews.read_job_preview_blob(runtime2, "preview-job", logical_role="primary", artifact_index=0)
    assert read2.metadata.code == "SVG_ACTIVE_CONTENT"


def test_single_page_pdf_converts_and_multi_page_pdf_is_rejected(tmp_path: Path) -> None:
    single_path = tmp_path / "single.pdf"
    Image.new("RGB", (120, 80), "white").save(single_path, format="PDF")
    runtime, _, _ = _job(tmp_path / "single-job", single_path.read_bytes(), suffix=".pdf", media_type="application/pdf")
    single = previews.read_job_preview_blob(runtime, "preview-job", logical_role="primary", artifact_index=0)
    if single.metadata.code == "PDF_RENDERER_UNAVAILABLE":
        pytest.skip("system Poppler is unavailable")
    assert single.available

    multi_path = tmp_path / "multi.pdf"
    images = [Image.new("RGB", (120, 80), color) for color in ("white", "black")]
    images[0].save(multi_path, format="PDF", save_all=True, append_images=images[1:])
    runtime2, _, _ = _job(tmp_path / "multi-job", multi_path.read_bytes(), suffix=".pdf", media_type="application/pdf")
    multi = previews.read_job_preview_blob(runtime2, "preview-job", logical_role="primary", artifact_index=0)
    assert multi.metadata.code == "PDF_PAGE_LIMIT"


@pytest.mark.skipif(os.name != "nt", reason="Windows CREATE_SUSPENDED witness")
def test_windows_worker_is_assigned_before_suspended_process_resumes(monkeypatch, tmp_path: Path) -> None:
    marker = tmp_path / "started.txt"
    real = previews._WindowsJobLimiter.create()

    class Observed:
        def assign(self, process: subprocess.Popen[bytes]) -> None:
            assert not marker.exists()
            real.assign(process)

        def resume(self, process: subprocess.Popen[bytes]) -> None:
            real.resume(process)

        def terminate(self, process: subprocess.Popen[bytes]) -> None:
            real.terminate(process)

        def close(self) -> None:
            real.close()

    monkeypatch.setattr(previews._WindowsJobLimiter, "create", classmethod(lambda cls: Observed()))
    process, limiter = previews._start_limited_process(
        [sys.executable, "-c", "from pathlib import Path; Path(__import__('sys').argv[1]).write_text('x')", str(marker)]
    )
    process.wait(timeout=5)
    limiter.close()
    assert marker.exists()


def test_timeout_terminates_worker_descendants(tmp_path: Path) -> None:
    marker = tmp_path / "orphan.txt"
    child_code = "import pathlib,time,sys; time.sleep(2); pathlib.Path(sys.argv[1]).write_text('orphan')"
    parent_code = (
        "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]); time.sleep(30)"
    )
    process, limiter = previews._start_limited_process([sys.executable, "-c", parent_code, child_code, str(marker)])
    time.sleep(0.3)
    limiter.terminate(process)
    limiter.close()
    time.sleep(2.2)
    assert not marker.exists()


def test_worker_memory_limit_kills_real_overallocation() -> None:
    process, limiter = previews._start_limited_process(
        [sys.executable, "-c", "x = bytearray(300 * 1024 * 1024); print(len(x))"]
    )
    process.wait(timeout=10)
    limiter.close()
    assert process.returncode != 0


def test_posix_limited_spawn_failure_is_typed(monkeypatch) -> None:
    monkeypatch.setattr(previews.subprocess, "Popen", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(previews._PreviewUnavailable) as caught:
        previews._spawn_posix_limited_process([sys.executable, "-c", "pass"], {}, previews._Limiter())
    assert caught.value.code == "WORKER_MEMORY_LIMIT_UNAVAILABLE"


def test_manifest_directory_reparse_component_is_rejected(tmp_path: Path) -> None:
    payload = _image_bytes(tmp_path)
    _, external_job, _ = _job(tmp_path / "external", payload, job_id="junction-job")
    runtime = tmp_path / "runtime"
    jobs = runtime / "mcp_jobs"
    jobs.mkdir(parents=True)
    link = jobs / "junction-job"
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(external_job)],
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            pytest.skip("directory junction creation is unavailable on this host")
    else:
        try:
            link.symlink_to(external_job, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlink creation is unavailable on this host")
    result = previews.describe_job_preview(runtime, "junction-job", logical_role="primary", artifact_index=0)
    assert result.code == "MANIFEST_UNSAFE"
