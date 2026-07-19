"""Contained, manifest-bound, lazy preview access for MCP job artifacts."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Final, Literal, Mapping
from urllib.parse import quote

from hub_core.mcp.preview_process_limits import (
    PREVIEW_WORKER_MEMORY_BYTES,
)
from hub_core.mcp.preview_process_limits import (
    WindowsJobLimiter as _WindowsJobLimiter,
)
from hub_core.posix_worker_limits import (
    build_posix_limit_callback,
    posix_memory_limit_supported,
)
from hub_core.project_paths import (
    ProjectPathError,
    normalize_project_relative_path,
    open_verified_project_input,
    project_path_has_symlink_component,
    snapshot_project_input,
)
from hub_core.runtime_boundary import activate_runtime_root

MAX_PREVIEW_RAW_BYTES: Final = 2 * 1024 * 1024
MAX_PREVIEW_BASE64_BYTES: Final = 2_796_204
MAX_PREVIEW_EDGE: Final = 2_048
MAX_PREVIEW_PIXELS: Final = 8_000_000
PREVIEW_WORKER_TIMEOUT_SECONDS: Final = 5.0
MAX_PREVIEW_SOURCE_BYTES: Final = 16 * 1024 * 1024
MAX_PREVIEW_MANIFEST_BYTES: Final = 2 * 1024 * 1024

_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_ROLE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_MEDIA_SUFFIXES: Final = {
    "image/png": {".png"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/webp": {".webp"},
    "application/pdf": {".pdf"},
    "image/svg+xml": {".svg"},
}


@dataclass(frozen=True, slots=True)
class PreviewMetadata:
    availability: Literal["available", "unavailable"]
    code: str
    reason: str
    resolution_hint: str
    job_id: str
    logical_role: str
    artifact_index: int
    source_media_type: str | None = None
    source_byte_size: int | None = None
    source_sha256: str | None = None
    preview_uri: str | None = None
    memory_limit_bytes: int = PREVIEW_WORKER_MEMORY_BYTES
    memory_limit_enforced: bool | None = None
    memory_limit_limitation: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PreviewBlob:
    metadata: PreviewMetadata
    data_base64: str | None = None
    preview_media_type: str | None = None
    raw_byte_size: int | None = None
    encoded_byte_size: int | None = None
    width: int | None = None
    height: int | None = None

    @property
    def available(self) -> bool:
        return self.metadata.availability == "available" and self.data_base64 is not None

    def as_dict(self, *, include_data: bool = True) -> dict[str, Any]:
        payload = {
            "metadata": self.metadata.as_dict(),
            "preview_media_type": self.preview_media_type,
            "raw_byte_size": self.raw_byte_size,
            "encoded_byte_size": self.encoded_byte_size,
            "width": self.width,
            "height": self.height,
        }
        if include_data:
            payload["data_base64"] = self.data_base64
        return payload


@dataclass(frozen=True, slots=True)
class _Selection:
    runtime_root: Path
    job_root: Path
    declaration: str
    metadata: PreviewMetadata


def preview_worker_capabilities() -> dict[str, Any]:
    """Describe effective preview containment without claiming absent controls."""

    memory_enforced = os.name == "nt" or (
        os.name == "posix" and posix_memory_limit_supported()
    )
    return {
        "memory_limit_bytes": PREVIEW_WORKER_MEMORY_BYTES,
        "memory_limit_enforced": memory_enforced,
        "memory_limit_limitation": _memory_limit_limitation(memory_enforced),
        "timeout_seconds": PREVIEW_WORKER_TIMEOUT_SECONDS,
        "source_byte_limit": MAX_PREVIEW_SOURCE_BYTES,
        "raw_output_byte_limit": MAX_PREVIEW_RAW_BYTES,
        "base64_output_byte_limit": MAX_PREVIEW_BASE64_BYTES,
        "pixel_limit": MAX_PREVIEW_PIXELS,
        "edge_limit": MAX_PREVIEW_EDGE,
        "cpu_limit_enforced": os.name == "posix",
        "file_size_limit_enforced": os.name == "posix",
        "process_tree_containment": os.name in {"nt", "posix"},
    }


def preview_resource_uri(job_id: str, logical_role: str, artifact_index: int) -> str:
    """Build a canonical preview URI after strict selector validation."""

    _validate_selector(job_id, logical_role, artifact_index)
    return f"figops://jobs/{quote(job_id, safe='')}/previews/{quote(logical_role, safe='')}/{artifact_index}"


def describe_job_preview(
    runtime_root: str | Path,
    job_id: str,
    *,
    logical_role: str,
    artifact_index: int,
) -> PreviewMetadata:
    """Validate one declared preview artifact without producing preview bytes."""

    try:
        metadata = _resolve_selection(runtime_root, job_id, logical_role, artifact_index).metadata
        if metadata.source_media_type == "image/svg+xml":
            return _unavailable(job_id, logical_role, artifact_index, "SVG_RENDERER_UNAVAILABLE")
        return metadata
    except _PreviewUnavailable as exc:
        return _unavailable(job_id, logical_role, artifact_index, exc.code)


def read_job_preview_blob(
    runtime_root: str | Path,
    job_id: str,
    *,
    logical_role: str,
    artifact_index: int,
) -> PreviewBlob:
    """Generate and base64-encode a bounded preview only when the resource is read."""

    try:
        selection = _resolve_selection(runtime_root, job_id, logical_role, artifact_index)
        preview_temp = activate_runtime_root(runtime_root) / "previews" / "temp"
        preview_temp.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="figops_preview_", dir=preview_temp) as tmp:
            private_root = Path(tmp)
            source = private_root / f"source{Path(selection.declaration).suffix.lower()}"
            _copy_verified_source(selection, source)
            output = private_root / "preview.png"
            result_path = private_root / "result.json"
            worker_result, memory_enforced = _run_worker(
                source,
                output,
                result_path,
                selection.metadata.source_media_type or "",
            )
            if worker_result.get("status") != "available":
                code = str(worker_result.get("code") or "PREVIEW_CONVERSION_FAILED")
                unavailable = replace(
                    _unavailable(job_id, logical_role, artifact_index, code),
                    memory_limit_enforced=memory_enforced,
                    memory_limit_limitation=_memory_limit_limitation(memory_enforced),
                )
                return PreviewBlob(metadata=unavailable)
            raw, media_type, width, height = _read_validated_preview(output)
            encoded = base64.b64encode(raw)
            if len(encoded) > MAX_PREVIEW_BASE64_BYTES:
                raise _PreviewUnavailable("PREVIEW_BASE64_LIMIT")
            metadata = replace(
                selection.metadata,
                memory_limit_enforced=memory_enforced,
                memory_limit_limitation=_memory_limit_limitation(memory_enforced),
            )
            return PreviewBlob(
                metadata=metadata,
                data_base64=encoded.decode("ascii"),
                preview_media_type=media_type,
                raw_byte_size=len(raw),
                encoded_byte_size=len(encoded),
                width=width,
                height=height,
            )
    except _PreviewUnavailable as exc:
        return PreviewBlob(metadata=_unavailable(job_id, logical_role, artifact_index, exc.code))


class _PreviewUnavailable(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_REASONS: Final[dict[str, tuple[str, str]]] = {
    "SELECTOR_INVALID": (
        "Preview selector is invalid.",
        "Use the job ID, logical role, and index from the render response.",
    ),
    "RUNTIME_ROOT_UNAVAILABLE": (
        "Preview runtime storage is unavailable.",
        "Verify the configured FigOps runtime root.",
    ),
    "JOB_NOT_FOUND": (
        "No completed render job matches the requested ID.",
        "Use a job ID returned by a completed render.",
    ),
    "JOB_AMBIGUOUS": (
        "The requested job ID is ambiguous across runtime job kinds.",
        "Use a unique job ID and render again.",
    ),
    "MANIFEST_UNSAFE": (
        "The render manifest could not be read through the trusted job boundary.",
        "Re-render the job in a non-symlinked runtime directory.",
    ),
    "MANIFEST_INVALID": (
        "The render manifest does not contain a valid preview contract.",
        "Re-render with a current FigOps producer.",
    ),
    "ARTIFACT_NOT_DECLARED": (
        "The requested artifact is not a manifest-declared preview member.",
        "Use a preview URI returned by the render response.",
    ),
    "ARTIFACT_UNSAFE": (
        "The preview artifact is not a contained regular file.",
        "Re-render the job and inspect runtime integrity diagnostics.",
    ),
    "ARTIFACT_SIZE_MISMATCH": (
        "The artifact size differs from its manifest declaration.",
        "Re-render because the artifact changed after publication.",
    ),
    "ARTIFACT_HASH_MISMATCH": (
        "The artifact hash differs from its manifest declaration.",
        "Re-render because the artifact changed after publication.",
    ),
    "MEDIA_TYPE_MISMATCH": (
        "The artifact header, suffix, and declared media type do not agree.",
        "Re-render the artifact with a supported format.",
    ),
    "SOURCE_BYTE_LIMIT": (
        "The source artifact exceeds the bounded preview input limit.",
        "Render a smaller source artifact.",
    ),
    "WORKER_MEMORY_LIMIT_UNAVAILABLE": (
        "A hard preview worker memory limit could not be applied.",
        "Use a supported host/runtime before previewing this artifact.",
    ),
    "PREVIEW_WORKER_TIMEOUT": (
        "Preview conversion exceeded the five-second deadline.",
        "Render a simpler or smaller artifact.",
    ),
    "PREVIEW_CONVERSION_FAILED": (
        "Preview conversion failed safely.",
        "Inspect artifact integrity diagnostics and render again.",
    ),
    "PREVIEW_BYTE_LIMIT": (
        "The generated preview exceeds the two-MiB raw limit.",
        "Render a smaller or less complex artifact.",
    ),
    "PREVIEW_BASE64_LIMIT": (
        "The encoded preview exceeds the bounded payload limit.",
        "Render a smaller or less complex artifact.",
    ),
    "PREVIEW_PIXEL_LIMIT": ("The decoded preview exceeds the eight-megapixel limit.", "Render at smaller dimensions."),
    "RASTER_DECODE_FAILED": (
        "The raster artifact could not be decoded safely.",
        "Re-render a valid PNG, JPEG, or WebP artifact.",
    ),
    "PDF_RENDERER_UNAVAILABLE": (
        "The bounded PDF preview renderer is unavailable.",
        "Install a working system pdftoppm or render a raster companion.",
    ),
    "PDF_RENDER_TIMEOUT": ("PDF first-page conversion timed out.", "Render a simpler PDF or a raster companion."),
    "PDF_PAGE_LIMIT": ("Only single-page PDFs can be previewed.", "Render one figure per PDF or a raster companion."),
    "PDF_RENDER_FAILED": ("PDF first-page conversion failed safely.", "Validate the PDF or render a raster companion."),
    "SVG_ACTIVE_CONTENT": (
        "The SVG contains active or externally referenced content.",
        "Render a sanitized raster companion.",
    ),
    "SVG_PARSE_FAILED": ("The SVG could not be parsed safely.", "Render a valid sanitized SVG or raster companion."),
    "SVG_RENDERER_UNAVAILABLE": (
        "No SVG renderer has passed the required Windows safety smoke test.",
        "Render a PNG/JPEG/WebP companion for inspection.",
    ),
    "MEDIA_TYPE_UNSUPPORTED": (
        "The artifact media type is not previewable.",
        "Render PNG, JPEG, WebP, PDF, or a raster companion.",
    ),
}


def _unavailable(job_id: Any, role: Any, index: Any, code: str) -> PreviewMetadata:
    reason, hint = _REASONS.get(code, _REASONS["PREVIEW_CONVERSION_FAILED"])
    return PreviewMetadata(
        availability="unavailable",
        code=code,
        reason=reason,
        resolution_hint=hint,
        job_id=job_id if isinstance(job_id, str) and _JOB_ID.fullmatch(job_id) else "",
        logical_role=role if isinstance(role, str) and _ROLE.fullmatch(role) else "",
        artifact_index=index if isinstance(index, int) and not isinstance(index, bool) and index >= 0 else 0,
        memory_limit_enforced=False if code == "WORKER_MEMORY_LIMIT_UNAVAILABLE" else None,
        memory_limit_limitation=(
            "Hard worker memory enforcement is unavailable on this host."
            if code == "WORKER_MEMORY_LIMIT_UNAVAILABLE"
            else None
        ),
    )


def _memory_limit_limitation(memory_enforced: bool) -> str | None:
    if memory_enforced:
        return None
    if sys.platform != "darwin":
        return (
            "Hard worker memory enforcement is unavailable on this host; timeout, "
            "input/output byte caps, CPU/file limits where supported, and process "
            "isolation remain active."
        )
    return (
        "Hard worker memory enforcement is unavailable on macOS; timeout, "
        "input/output byte caps, CPU/file limits, and process isolation remain active."
    )


def _validate_selector(job_id: Any, role: Any, index: Any) -> None:
    if not isinstance(job_id, str) or _JOB_ID.fullmatch(job_id) is None:
        raise _PreviewUnavailable("SELECTOR_INVALID")
    if not isinstance(role, str) or _ROLE.fullmatch(role) is None:
        raise _PreviewUnavailable("SELECTOR_INVALID")
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < 256:
        raise _PreviewUnavailable("SELECTOR_INVALID")


def _resolve_selection(runtime_root: str | Path, job_id: Any, role: Any, index: Any) -> _Selection:
    _validate_selector(job_id, role, index)
    try:
        root = Path(runtime_root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, TypeError):
        raise _PreviewUnavailable("RUNTIME_ROOT_UNAVAILABLE") from None
    if not root.is_dir():
        raise _PreviewUnavailable("RUNTIME_ROOT_UNAVAILABLE")
    candidates = [
        root / "mcp_jobs" / job_id / "manifest.json",
        root / "mcp_project_jobs" / job_id / "manifest.json",
    ]
    present = [candidate for candidate in candidates if os.path.lexists(candidate)]
    if not present:
        raise _PreviewUnavailable("JOB_NOT_FOUND")
    if len(present) != 1:
        raise _PreviewUnavailable("JOB_AMBIGUOUS")
    manifest_path = present[0]
    job_root = manifest_path.parent
    manifest = _read_manifest(root, manifest_path)
    if manifest.get("job_id") != job_id:
        raise _PreviewUnavailable("MANIFEST_INVALID")
    entries = manifest.get("preview_artifacts")
    if not isinstance(entries, list) or len(entries) > 256 or index >= len(entries):
        raise _PreviewUnavailable("ARTIFACT_NOT_DECLARED")
    entry = entries[index]
    if not isinstance(entry, Mapping) or entry.get("logical_role") != role:
        raise _PreviewUnavailable("ARTIFACT_NOT_DECLARED")
    declaration = entry.get("relative_path")
    media_type = entry.get("media_type")
    declared_size = entry.get("byte_size")
    declared_hash = entry.get("sha256")
    if (
        not isinstance(declaration, str)
        or media_type not in _MEDIA_SUFFIXES
        or not isinstance(declared_size, int)
        or isinstance(declared_size, bool)
        or declared_size <= 0
        or not isinstance(declared_hash, str)
        or _SHA256.fullmatch(declared_hash) is None
    ):
        raise _PreviewUnavailable("MANIFEST_INVALID")
    try:
        declaration = normalize_project_relative_path(declaration, purpose="preview artifact")
    except ProjectPathError:
        raise _PreviewUnavailable("ARTIFACT_UNSAFE") from None
    if Path(declaration).suffix.lower() not in _MEDIA_SUFFIXES[media_type]:
        raise _PreviewUnavailable("MEDIA_TYPE_MISMATCH")
    if declared_size > MAX_PREVIEW_SOURCE_BYTES:
        raise _PreviewUnavailable("SOURCE_BYTE_LIMIT")
    try:
        if project_path_has_symlink_component(job_root, declaration, purpose="preview artifact"):
            raise _PreviewUnavailable("ARTIFACT_UNSAFE")
        snapshot = snapshot_project_input(job_root, declaration, purpose="preview artifact")
        with open_verified_project_input(
            job_root,
            declaration,
            expected_snapshot=snapshot,
            purpose="preview artifact",
        ) as stream:
            opened = os.fstat(stream.fileno())
            if opened.st_size != declared_size:
                raise _PreviewUnavailable("ARTIFACT_SIZE_MISMATCH")
            head = stream.read(4096)
            if _detect_media_type(head) != media_type:
                raise _PreviewUnavailable("MEDIA_TYPE_MISMATCH")
            digest = hashlib.sha256()
            digest.update(head)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            closed = os.fstat(stream.fileno())
            if _stat_identity(opened) != _stat_identity(closed):
                raise _PreviewUnavailable("ARTIFACT_UNSAFE")
            if digest.hexdigest().lower() != declared_hash.lower():
                raise _PreviewUnavailable("ARTIFACT_HASH_MISMATCH")
    except _PreviewUnavailable:
        raise
    except (OSError, ProjectPathError):
        raise _PreviewUnavailable("ARTIFACT_UNSAFE") from None
    metadata = PreviewMetadata(
        availability="available",
        code="PREVIEW_DECLARED",
        reason="Manifest-bound preview artifact is available for on-demand conversion.",
        resolution_hint="Read the preview resource to generate bounded image bytes.",
        job_id=job_id,
        logical_role=role,
        artifact_index=index,
        source_media_type=media_type,
        source_byte_size=declared_size,
        source_sha256=declared_hash.lower(),
        preview_uri=preview_resource_uri(job_id, role, index),
    )
    return _Selection(root, job_root, declaration, metadata)


def _read_manifest(runtime_root: Path, path: Path) -> dict[str, Any]:
    try:
        declaration = path.absolute().relative_to(runtime_root.absolute()).as_posix()
        if project_path_has_symlink_component(runtime_root, declaration, purpose="preview manifest"):
            raise _PreviewUnavailable("MANIFEST_UNSAFE")
        snapshot = snapshot_project_input(runtime_root, declaration, purpose="preview manifest")
        with open_verified_project_input(
            runtime_root,
            declaration,
            expected_snapshot=snapshot,
            purpose="preview manifest",
        ) as stream:
            opened = os.fstat(stream.fileno())
            if opened.st_size <= 0 or opened.st_size > MAX_PREVIEW_MANIFEST_BYTES:
                raise _PreviewUnavailable("MANIFEST_INVALID")
            payload = stream.read(MAX_PREVIEW_MANIFEST_BYTES + 1)
            closed = os.fstat(stream.fileno())
            if _stat_identity(opened) != _stat_identity(closed):
                raise _PreviewUnavailable("MANIFEST_UNSAFE")
        parsed = json.loads(payload.decode("utf-8"))
    except _PreviewUnavailable:
        raise
    except (OSError, ProjectPathError):
        raise _PreviewUnavailable("MANIFEST_UNSAFE") from None
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise _PreviewUnavailable("MANIFEST_INVALID") from None
    if not isinstance(parsed, dict):
        raise _PreviewUnavailable("MANIFEST_INVALID")
    return parsed


def _copy_verified_source(selection: _Selection, destination: Path) -> None:
    try:
        snapshot = snapshot_project_input(selection.job_root, selection.declaration, purpose="preview artifact")
        with (
            open_verified_project_input(
                selection.job_root,
                selection.declaration,
                expected_snapshot=snapshot,
                purpose="preview artifact",
            ) as source,
            destination.open("xb") as target,
        ):
            opened = os.fstat(source.fileno())
            digest = hashlib.sha256()
            copied = 0
            while chunk := source.read(1024 * 1024):
                copied += len(chunk)
                if copied > MAX_PREVIEW_SOURCE_BYTES:
                    raise _PreviewUnavailable("SOURCE_BYTE_LIMIT")
                digest.update(chunk)
                target.write(chunk)
            closed = os.fstat(source.fileno())
        if _stat_identity(opened) != _stat_identity(closed):
            raise _PreviewUnavailable("ARTIFACT_UNSAFE")
        if copied != selection.metadata.source_byte_size:
            raise _PreviewUnavailable("ARTIFACT_SIZE_MISMATCH")
        if digest.hexdigest() != selection.metadata.source_sha256:
            raise _PreviewUnavailable("ARTIFACT_HASH_MISMATCH")
    except _PreviewUnavailable:
        raise
    except (OSError, ProjectPathError):
        raise _PreviewUnavailable("ARTIFACT_UNSAFE") from None


def _detect_media_type(head: bytes) -> str:
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"RIFF") and len(head) >= 12 and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if b"<svg" in head.lstrip(b"\xef\xbb\xbf\x00\t\r\n ")[:1024].lower():
        return "image/svg+xml"
    return ""


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns


def _run_worker(source: Path, output: Path, result_path: Path, media_type: str) -> tuple[dict[str, Any], bool]:
    command = [
        sys.executable,
        "-m",
        "hub_core.mcp.preview_worker",
        "--source",
        str(source),
        "--output",
        str(output),
        "--result",
        str(result_path),
        "--media-type",
        media_type,
    ]
    process, limiter = _start_limited_process(command)
    memory_enforced = bool(getattr(limiter, "memory_enforced", True))
    try:
        process.wait(timeout=PREVIEW_WORKER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        limiter.terminate(process)
        raise _PreviewUnavailable("PREVIEW_WORKER_TIMEOUT") from None
    finally:
        limiter.close()
    if process.returncode != 0 or not result_path.is_file():
        raise _PreviewUnavailable("PREVIEW_CONVERSION_FAILED")
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise _PreviewUnavailable("PREVIEW_CONVERSION_FAILED") from None
    if not isinstance(payload, dict):
        raise _PreviewUnavailable("PREVIEW_CONVERSION_FAILED")
    return payload, memory_enforced


class _Limiter:
    def __init__(self, *, memory_enforced: bool = True) -> None:
        self.memory_enforced = memory_enforced

    def terminate(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass

    def close(self) -> None:
        return None


class _PosixLimiter(_Limiter):
    def terminate(self, process: subprocess.Popen[bytes]) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=0.5)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            super().terminate(process)


def _start_limited_process(command: list[str]) -> tuple[subprocess.Popen[bytes], _Limiter | None]:
    options: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": str(Path(__file__).resolve().parents[2]),
    }
    limiter: _Limiter | None = None
    if os.name == "nt":
        try:
            windows = _WindowsJobLimiter.create()
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000004
            process = subprocess.Popen(command, **options)
            windows.assign(process)
            windows.resume(process)
            limiter = windows
            return process, limiter
        except (OSError, ValueError):
            if "process" in locals() and process.poll() is None:
                process.kill()
                process.wait()
            if "windows" in locals():
                windows.close()
            raise _PreviewUnavailable("WORKER_MEMORY_LIMIT_UNAVAILABLE") from None
    try:
        limit_worker, memory_enforced = build_posix_limit_callback(
            memory_bytes=PREVIEW_WORKER_MEMORY_BYTES,
            cpu_seconds=PREVIEW_WORKER_TIMEOUT_SECONDS,
            file_bytes=MAX_PREVIEW_RAW_BYTES,
        )
        options["start_new_session"] = True
        options["preexec_fn"] = limit_worker
        limiter = _PosixLimiter(memory_enforced=memory_enforced)
    except (ImportError, AttributeError):
        limiter = None
    if limiter is None:
        raise _PreviewUnavailable("WORKER_MEMORY_LIMIT_UNAVAILABLE")
    return _spawn_posix_limited_process(command, options, limiter)


def _spawn_posix_limited_process(
    command: list[str], options: dict[str, Any], limiter: _Limiter
) -> tuple[subprocess.Popen[bytes], _Limiter]:
    """Translate RLIMIT/preexec/Popen setup failures into the public typed contract."""

    try:
        return subprocess.Popen(command, **options), limiter
    except (OSError, ValueError, subprocess.SubprocessError):
        limiter.close()
        raise _PreviewUnavailable("WORKER_MEMORY_LIMIT_UNAVAILABLE") from None


def _read_validated_preview(path: Path) -> tuple[bytes, str, int, int]:
    try:
        size = path.stat().st_size
        if size <= 0 or size > MAX_PREVIEW_RAW_BYTES:
            raise _PreviewUnavailable("PREVIEW_BYTE_LIMIT")
        raw = path.read_bytes()
        media_type = _detect_media_type(raw[:4096])
        if media_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise _PreviewUnavailable("PREVIEW_CONVERSION_FAILED")
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = MAX_PREVIEW_PIXELS
        from io import BytesIO

        with Image.open(BytesIO(raw)) as image:
            width, height = int(image.width), int(image.height)
            if (
                width <= 0
                or height <= 0
                or width > MAX_PREVIEW_EDGE
                or height > MAX_PREVIEW_EDGE
                or width * height > MAX_PREVIEW_PIXELS
            ):
                raise _PreviewUnavailable("PREVIEW_PIXEL_LIMIT")
            image.verify()
    except _PreviewUnavailable:
        raise
    except Exception:
        raise _PreviewUnavailable("PREVIEW_CONVERSION_FAILED") from None
    return raw, media_type, width, height
