from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import pickle
import sys
import tempfile
import time
import traceback
import uuid
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hub_core.mcp.render_errors import ProjectRenderExportError, ProjectRenderScriptError  # noqa: F401
from hub_core.mcp.render_geometry import (
    SCRIPT_OUTPUT_TAIL_LINES,
    _geometry_stub,
    _geometry_warnings,  # noqa: F401
    _layout_report_from_geometry,
    _read_geometry_sidecar,  # noqa: F401
)
from hub_core.mcp.render_project_runtime import McpProjectRuntimeMixin
from hub_core.project_discovery import ProjectDiscoveryService

MCP_RENDER_CSV_MAX_BYTES = 64 * 1024 * 1024
MCP_RENDER_TIMEOUT_SECONDS = 120.0
MCP_BATCH_TIMEOUT_SECONDS = 30.0
MCP_WORKER_RESULT_MAX_BYTES = 16 * 1024 * 1024


def _ensure_matplotlib_runtime_env(config_root: str | Path | None = None) -> None:
    os.environ.setdefault("MPLBACKEND", "Agg")
    if os.environ.get("MPLCONFIGDIR"):
        return
    root = Path(config_root) if config_root is not None else Path(tempfile.gettempdir())
    config_dir = root / ".matplotlib"
    config_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(config_dir)


def _write_worker_result(result_path: str | Path, result: dict[str, Any]) -> None:
    try:
        payload = pickle.dumps(result)
    except (pickle.PickleError, TypeError, ValueError) as exc:
        payload = pickle.dumps(
            {
                "status": "error",
                "error": f"Worker result could not be serialized: {type(exc).__name__}: {exc}",
                "failure_stage": "TRANSFER",
            }
        )
    size = len(payload)
    if size > MCP_WORKER_RESULT_MAX_BYTES:
        payload = pickle.dumps(
            {
                "status": "error",
                "error": (
                    f"Worker result too large: {size} bytes exceeds "
                    f"{MCP_WORKER_RESULT_MAX_BYTES} bytes."
                ),
                "failure_stage": "TRANSFER",
            }
        )
    Path(result_path).write_bytes(payload)


def _read_worker_result(result_path: str | Path, worker_label: str) -> dict[str, Any]:
    path = Path(result_path)
    if not path.is_file():
        raise RuntimeError(f"{worker_label} worker exited without returning a result.")
    try:
        result = pickle.loads(path.read_bytes())
    except (OSError, pickle.PickleError, EOFError, TypeError, ValueError) as exc:
        raise RuntimeError(f"{worker_label} worker returned an unreadable result: {exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"{worker_label} worker returned an invalid result payload.")
    return result


def _render_bridge_figure_worker(spec_payload: dict[str, Any], result_path: str) -> None:
    _ensure_matplotlib_runtime_env(Path(spec_payload["output_path"]).parent)
    try:
        with redirect_stdout(sys.stderr):
            from plotting.bridge_renderer import BridgeFigureSpec, render_bridge_figure

            output_path = render_bridge_figure(BridgeFigureSpec(**spec_payload))
        _write_worker_result(result_path, {"status": "ok", "output_path": output_path})
    except Exception as exc:
        _write_worker_result(
            result_path,
            {"status": "error", "error": str(exc), "traceback": traceback.format_exc().splitlines()},
        )


def _render_multipanel_figure_worker(spec_payload: dict[str, Any], result_path: str) -> None:
    _ensure_matplotlib_runtime_env(Path(spec_payload["output_path"]).parent)
    try:
        with redirect_stdout(sys.stderr):
            from plotting.bridge_renderer import BridgeFigureSpec, MultiPanelSpec, render_multipanel_figure

            panel_specs = tuple(BridgeFigureSpec(**panel) for panel in spec_payload.pop("panels"))
            output_path = render_multipanel_figure(MultiPanelSpec(panels=panel_specs, **spec_payload))
        _write_worker_result(result_path, {"status": "ok", "output_path": output_path})
    except Exception as exc:
        _write_worker_result(
            result_path,
            {"status": "error", "error": str(exc), "traceback": traceback.format_exc().splitlines()},
        )


def _batch_discovery_worker(root: str, max_depth: int, result_path: str) -> None:
    _ensure_matplotlib_runtime_env()
    try:
        with redirect_stdout(sys.stderr):
            projects = ProjectDiscoveryService(
                root,
                include_worktrees=True,
                include_ephemeral=True,
            ).discover(max_depth=max_depth)
        _write_worker_result(result_path, {"status": "ok", "projects": projects})
    except Exception as exc:
        _write_worker_result(
            result_path,
            {"status": "error", "error": str(exc), "traceback": traceback.format_exc().splitlines()},
        )


def _write_manifest_and_status(
    manifest: dict[str, Any],
    manifest_path: Path,
    status_payload: dict[str, Any],
    status_path: Path,
    latest_dir: Path,
) -> None:
    """Write manifest and status payload to disk, then copy both to latest_dir.

    Shared boilerplate for render success and failure artifact methods.
    """
    _ensure_no_symlinked_runtime_path(manifest_path)
    _ensure_no_symlinked_runtime_path(status_path)
    _ensure_no_symlinked_runtime_path(latest_dir)
    latest_dir.mkdir(parents=True, exist_ok=True)
    latest_manifest_path = latest_dir / "manifest.json"
    latest_status_path = latest_dir / "status.json"
    _ensure_no_symlinked_runtime_path(latest_manifest_path)
    _ensure_no_symlinked_runtime_path(latest_status_path)
    _atomic_json_write(manifest_path, manifest)
    _atomic_json_write(status_path, status_payload)
    _atomic_json_write(latest_manifest_path, manifest)
    _atomic_json_write(latest_status_path, status_payload)


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    """Write one runtime JSON leaf atomically after validating its full path."""
    _ensure_no_symlinked_runtime_path(path)
    if path.exists() and path.is_symlink():
        raise RuntimeError(f"Runtime write target must not be a symlink: {path}")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(temporary_path, flags | nofollow, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        _ensure_no_symlinked_runtime_path(path)
        os.replace(temporary_path, path)
    except OSError:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _first_symlink_component(path: Path) -> Path | None:
    raw_path = Path(path)
    current = Path(raw_path.anchor) if raw_path.is_absolute() else Path()
    parts = raw_path.parts[1:] if raw_path.is_absolute() else raw_path.parts
    for part in parts:
        current = current / part
        if current.is_symlink():
            return current
    return None


def _ensure_no_symlinked_runtime_path(path: Path) -> None:
    symlink = _first_symlink_component(path)
    if symlink is not None:
        raise RuntimeError(f"Runtime write target must not include symlinked path components: {symlink}")


def _build_manifest(
    *,
    job_id: str,
    job_root: Path,
    config_path: Path,
    status_path: Path,
    latest_dir: Path,
    figures: list[dict[str, Any]],
    created_paths: list[str],
    style_summary: dict[str, Any],
    visual_preflight_status: dict[str, Any],
    geometry_diagnostics: dict[str, Any],
    layout_report: dict[str, Any],
    artifact_status: str,
    baseline_comparison: dict[str, Any],
    manual_review_needed: bool,
    provenance: dict[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    """Build a standard render manifest dict.

    Renders the common skeleton shared by CSV graph and project figure
    manifests.  Callers pass extra keyword arguments for render-type-specific
    fields (e.g. *source_data_path*, *project_id*, *selected_figure*).
    """
    manifest: dict[str, Any] = {
        "job_id": job_id,
        "job_root": str(job_root),
        "config_path": str(config_path),
        "status_path": str(status_path),
        "latest_dir": str(latest_dir),
        "latest_alias": str(latest_dir),
        "figures": figures,
        "diagrams": [],
        "assemblies": [],
        "logs": [],
        "created_paths": created_paths,
        "modified_paths": [],
        "skipped_paths": [],
        "style_summary": style_summary,
        "visual_preflight_status": visual_preflight_status,
        "geometry_diagnostics": geometry_diagnostics,
        "layout_report": layout_report,
        "failure_stage": "",
        "resolution_hint": "",
        "artifact_status": artifact_status,
        "baseline_comparison": baseline_comparison,
        "manual_review_needed": manual_review_needed,
        "provenance": provenance,
    }
    manifest.update(extra)
    return manifest


class McpRenderOrchestrationMixin(McpProjectRuntimeMixin):
    """Render, snapshot, provenance, and geometry helper methods for the MCP server."""

    @staticmethod
    def _project_render_timeout_seconds() -> float:
        return MCP_RENDER_TIMEOUT_SECONDS

    @staticmethod
    def _render_status_payload(
        *,
        job_id: str,
        status: str,
        summary: str,
        manifest_path: Path,
        output_path: Path,
        artifact_status: str,
        manual_review_needed: bool,
        failure_stage: str,
        resolution_hint: str,
    ) -> dict[str, Any]:
        return {
            "engine_target": "figops_mcp_render",
            "job_id": job_id,
            "status": status,
            "summary": summary,
            "manifest_path": str(manifest_path),
            "output_path": str(output_path),
            "artifact_status": artifact_status,
            "manual_review_needed": manual_review_needed,
            "failure_stage": failure_stage,
            "resolution_hint": resolution_hint,
        }

    @staticmethod
    def _write_failure_artifacts_to_disk(
        manifest: dict[str, Any],
        manifest_path: Path,
        status_payload: dict[str, Any],
        status_path: Path,
        latest_dir: Path,
        created: list[str],
    ) -> list[str]:
        """Write manifest and status to disk, update created_paths, and copy to latest.

        Shared boilerplate for bridge and project render failure artifact methods.
        """
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        for path in (manifest_path, status_path):
            path_text = str(path)
            if path_text not in created:
                created.append(path_text)
        manifest["created_paths"] = created
        _write_manifest_and_status(manifest, manifest_path, status_payload, status_path, latest_dir)
        return created

    def _write_render_failure_artifacts(
        self,
        *,
        job_id: str,
        job_root: Path,
        source_data_path: Path,
        copied_data_path: Path,
        config_path: Path,
        output_path: Path,
        manifest_path: Path,
        status_path: Path,
        latest_dir: Path,
        created_paths: list[str],
        failure_stage: str,
        resolution_hint: str,
        baseline_comparison: dict[str, Any],
    ) -> list[str]:
        layout_report = _layout_report_from_geometry(
            _geometry_stub("render_execution_failed"),
            failure_stage=failure_stage,
        )
        created = list(created_paths)
        manifest = {
            "job_id": job_id,
            "job_root": str(job_root),
            "source_data_path": str(source_data_path),
            "copied_data_path": str(copied_data_path) if copied_data_path.exists() else "",
            "config_path": str(config_path) if config_path.exists() else "",
            "status_path": str(status_path),
            "latest_dir": str(latest_dir),
            "latest_alias": str(latest_dir),
            "figures": [],
            "diagrams": [],
            "assemblies": [],
            "logs": [],
            "created_paths": created,
            "modified_paths": [],
            "skipped_paths": [],
            "style_summary": {},
            "visual_preflight_status": {"passed": False, "checks": [], "warnings": ["render_execution_failed"]},
            "layout_report": layout_report,
            "failure_stage": failure_stage,
            "resolution_hint": resolution_hint,
            "artifact_status": "failed",
            "baseline_comparison": baseline_comparison,
            "manual_review_needed": True,
        }
        status_payload = self._render_status_payload(
            job_id=job_id,
            status="error",
            summary="Render execution failed.",
            manifest_path=manifest_path,
            output_path=output_path,
            artifact_status="failed",
            manual_review_needed=True,
            failure_stage=failure_stage,
            resolution_hint=resolution_hint,
        )
        status_payload["layout_report"] = layout_report
        return self._write_failure_artifacts_to_disk(
            manifest, manifest_path, status_payload, status_path, latest_dir, created
        )

    @staticmethod
    @contextmanager
    def _geometry_diagnostics_env(job_root: Path):
        """Set GEOMETRY_DIAGNOSTICS_OUT/_DEADLINE for the spawn-child render, then restore.

        Both vars mutate the parent os.environ so the spawn child inherits them; the finally
        restores/pops them so a stale path/deadline never redirects the next in-process render.
        The deadline is an absolute epoch (time.time()), cross-process comparable; the child
        reads it against a fixed floor (see themes.journal_theme.DIAG_BUDGET_FLOOR_SECONDS).
        """
        prior_out = os.environ.get("GEOMETRY_DIAGNOSTICS_OUT")
        prior_deadline = os.environ.get("GEOMETRY_DIAGNOSTICS_DEADLINE")
        os.environ["GEOMETRY_DIAGNOSTICS_OUT"] = str(job_root / "geometry_diagnostics.json")
        os.environ["GEOMETRY_DIAGNOSTICS_DEADLINE"] = str(time.time() + MCP_RENDER_TIMEOUT_SECONDS)
        try:
            yield
        finally:
            for key, prior in (
                ("GEOMETRY_DIAGNOSTICS_OUT", prior_out),
                ("GEOMETRY_DIAGNOSTICS_DEADLINE", prior_deadline),
            ):
                if prior is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = prior

    @staticmethod
    def _run_render_bridge_figure(spec_payload: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory(prefix="figops_mcp_render_worker_") as tmpdir:
            result_path = Path(tmpdir) / "result.json"
            process = multiprocessing.Process(
                target=_render_bridge_figure_worker,
                args=(spec_payload, str(result_path)),
                name="figops-mcp-render",
            )
            process.start()
            process.join(MCP_RENDER_TIMEOUT_SECONDS)
            if process.is_alive():
                process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
                raise TimeoutError(f"Render timed out after {MCP_RENDER_TIMEOUT_SECONDS:.1f} seconds.")
            if process.exitcode not in (0, None):
                raise RuntimeError(f"Render worker exited with code {process.exitcode}.")
            result = _read_worker_result(result_path, "Render")
            if result.get("status") != "ok":
                trace = result.get("traceback") if isinstance(result.get("traceback"), list) else []
                message = "\n".join(str(line) for line in trace[-SCRIPT_OUTPUT_TAIL_LINES:]) or str(
                    result.get("error") or "Render worker failed."
                )
                raise RuntimeError(message)

    @staticmethod
    def _run_render_multipanel_figure(spec_payload: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory(prefix="figops_mcp_multipanel_worker_") as tmpdir:
            result_path = Path(tmpdir) / "result.json"
            process = multiprocessing.Process(
                target=_render_multipanel_figure_worker,
                args=(spec_payload, str(result_path)),
                name="figops-mcp-multipanel-render",
            )
            process.start()
            process.join(MCP_RENDER_TIMEOUT_SECONDS)
            if process.is_alive():
                process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
                raise TimeoutError(f"Render timed out after {MCP_RENDER_TIMEOUT_SECONDS:.1f} seconds.")
            if process.exitcode not in (0, None):
                raise RuntimeError(f"Render worker exited with code {process.exitcode}.")
            result = _read_worker_result(result_path, "Multipanel render")
            if result.get("status") != "ok":
                trace = result.get("traceback") if isinstance(result.get("traceback"), list) else []
                message = "\n".join(str(line) for line in trace[-SCRIPT_OUTPUT_TAIL_LINES:]) or str(
                    result.get("error") or "Multipanel render worker failed."
                )
                raise RuntimeError(message)

    def _project_render_error(
        self,
        arguments: dict[str, Any],
        *,
        dry_run: bool,
        job_id: str,
        job_root: Path,
        summary: str,
        errors: list[str],
        failure_stage: str,
        resolution_hint: str,
        **extra: Any,
    ) -> dict[str, Any]:
        geometry_diagnostics = extra.pop("geometry_diagnostics", _geometry_stub("no figure"))
        persist_failure = bool(extra.pop("persist_failure", False)) and not dry_run
        provenance = extra.pop(
            "provenance",
            {"attempt": arguments.get("_mcp_attempt_provenance", {})},
        )
        style_summary = extra.get("style_summary", {})
        if not isinstance(style_summary, dict):
            style_summary = {}
        created_paths: list[str] = []
        manifest_path = job_root / "manifest.json"
        status_path = job_root / "status.json"
        latest_dir = self.runtime_root / "_latest" / "mcp_project_render"
        snapshot_project_path = job_root / "project"
        if persist_failure:
            unsafe_path = _first_symlink_component(job_root) or _first_symlink_component(latest_dir)
            if unsafe_path is None:
                layout_report = extra.get(
                    "layout_report",
                    _layout_report_from_geometry(geometry_diagnostics, failure_stage=failure_stage),
                )
                created_paths = self._write_project_render_failure_artifacts(
                    job_id=job_id,
                    job_root=job_root,
                    snapshot_project_path=snapshot_project_path,
                    selected_figure=extra.get("selected_figure", {}),
                    manifest_path=manifest_path,
                    status_path=status_path,
                    latest_dir=latest_dir,
                    created_paths=[],
                    failure_stage=failure_stage,
                    resolution_hint=resolution_hint,
                    baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
                    provenance=provenance,
                    style_summary=style_summary,
                    layout_report=layout_report,
                )
                extra["manifest_path"] = self._public_runtime_path(manifest_path)
                extra["status_path"] = self._public_runtime_path(status_path)
                extra["latest_dir"] = self._public_runtime_path(latest_dir)
                extra["latest_alias"] = self._public_runtime_path(latest_dir)
            else:
                errors = [*errors, "Failure artifacts were not persisted because the runtime path is unsafe."]
        extra["created_paths"] = self._public_runtime_paths(created_paths)
        extra = self._public_failure_extra(extra)
        return self._envelope(
            "figops.render_project_figure",
            arguments,
            status="error",
            summary=summary,
            errors=errors,
            manual_review_needed=True,
            is_dry_run=dry_run,
            job_id=job_id,
            job_root=self._public_runtime_path(job_root),
            artifact_status="failed",
            baseline_comparison=self._baseline_comparison(None, arguments.get("baseline_path")),
            provenance=provenance,
            geometry_diagnostics=geometry_diagnostics,
            layout_report=extra.pop(
                "layout_report",
                _layout_report_from_geometry(geometry_diagnostics, failure_stage=failure_stage),
            ),
            failure_stage=failure_stage,
            resolution_hint=resolution_hint,
            **extra,
        )

    def _public_runtime_path(self, path: Path) -> str:
        """Expose runtime artifacts only as runtime URIs, never host-local paths."""
        resolved = path.resolve()
        if not resolved.is_relative_to(self.runtime_root.resolve()):
            return ""
        return self._runtime_uri(resolved)

    def _public_runtime_paths(self, paths: list[str]) -> list[str]:
        return [public for raw_path in paths if (public := self._public_runtime_path(Path(raw_path)))]

    def _public_failure_extra(self, extra: dict[str, Any]) -> dict[str, Any]:
        path_keys = {
            "job_root",
            "snapshot_project_path",
            "output_path",
            "config_path",
            "manifest_path",
            "status_path",
            "latest_dir",
            "latest_alias",
        }
        for key in path_keys:
            raw_value = extra.get(key)
            if isinstance(raw_value, str) and raw_value:
                if raw_value.startswith("runtime://"):
                    continue
                extra[key] = self._public_runtime_path(Path(raw_value))
        return extra

    def _baseline_comparison(self, artifact_path: Path | None, raw_baseline_path: Any) -> dict[str, Any]:
        if not isinstance(raw_baseline_path, str) or not raw_baseline_path.strip():
            return {"checked": False, "matched": None, "status": "not_checked", "warnings": []}

        try:
            baseline_path = self._resolve_allowed_data_path(raw_baseline_path, field_name="baseline_path")
        except ValueError as exc:
            return {
                "checked": True,
                "matched": False,
                "status": "manual_review_needed",
                "baseline_path": "",
                "artifact_path": str(artifact_path) if artifact_path else "",
                "algorithm": "sha256",
                "warnings": [str(exc)],
            }
        warnings: list[str] = []
        if artifact_path is None:
            warnings.append("Baseline comparison requested but no artifact path was available.")
            return {
                "checked": True,
                "matched": False,
                "status": "manual_review_needed",
                "baseline_path": str(baseline_path),
                "artifact_path": "",
                "algorithm": "sha256",
                "warnings": warnings,
            }
        artifact_path = Path(artifact_path).expanduser().resolve()
        if not baseline_path.is_file():
            warnings.append("Baseline comparison requested but baseline_path is not a file.")
            return {
                "checked": True,
                "matched": False,
                "status": "manual_review_needed",
                "baseline_path": str(baseline_path),
                "artifact_path": str(artifact_path),
                "algorithm": "sha256",
                "warnings": warnings,
            }
        if not artifact_path.is_file():
            warnings.append("Baseline comparison requested but artifact file is missing.")
            return {
                "checked": True,
                "matched": False,
                "status": "manual_review_needed",
                "baseline_path": str(baseline_path),
                "artifact_path": str(artifact_path),
                "algorithm": "sha256",
                "warnings": warnings,
            }

        artifact_sha = self._file_sha256(artifact_path)
        baseline_sha = self._file_sha256(baseline_path)
        matched = artifact_sha == baseline_sha
        return {
            "checked": True,
            "matched": matched,
            "status": "baseline_matched" if matched else "manual_review_needed",
            "baseline_path": str(baseline_path),
            "artifact_path": str(artifact_path),
            "algorithm": "sha256",
            "artifact_sha256": artifact_sha,
            "warnings": [] if matched else ["Artifact does not match baseline."],
        }

    def _mcp_lock_status(self) -> dict[str, Any]:
        """Collect uv.lock / renv.lock status for provenance records."""
        python_lock = self.hub_path / "uv.lock"
        r_lock = self.hub_path / "renv.lock"
        return {
            "python_lock": {
                "path": str(python_lock),
                "exists": python_lock.is_file(),
                "sha256": self._file_sha256(python_lock) if python_lock.is_file() else "",
            },
            "r_lock": {
                "path": str(r_lock),
                "exists": r_lock.is_file(),
                "sha256": self._file_sha256(r_lock) if r_lock.is_file() else "",
            },
        }

    def _mcp_render_provenance(
        self,
        *,
        job_id: str,
        source_data_path: Path,
        copied_data_path: Path,
        config_path: Path,
        output_path: Path,
        target_format: str,
        profile: str,
        output_format: str,
    ) -> dict[str, Any]:
        source_hash = self._file_sha256(source_data_path) if source_data_path.is_file() else ""
        copied_hash = self._file_sha256(copied_data_path) if copied_data_path.is_file() else ""
        config_hash = self._file_sha256(config_path) if config_path.is_file() else ""
        output_hash = self._file_sha256(output_path) if output_path.is_file() else ""
        lock_status = self._mcp_lock_status()
        env_payload = {
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "target_format": target_format,
            "profile": profile,
            "output_format": output_format,
            "lock_status": lock_status,
            "renderer": "plotting.bridge_renderer.render_bridge_figure",
            "mcp_surface_version": self._read_version(),
        }
        environment_hash = hashlib.sha256(
            json.dumps(env_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return {
            "job_id": job_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "renderer": "plotting.bridge_renderer.render_bridge_figure",
            "renderer_surface": "figops.render_csv_graph",
            "mcp_surface_version": self._read_version(),
            "hub_git_commit": self._git_commit(),
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "source_data_sha256": source_hash,
            "copied_data_sha256": copied_hash,
            "config_sha256": config_hash,
            "output_sha256": output_hash,
            "environment_sha256": environment_hash,
            "lock_status": lock_status,
        }

    def _mcp_project_render_provenance(
        self,
        *,
        job_id: str,
        project_path: Path,
        snapshot_project_path: Path,
        config_path: Path,
        output_path: Path,
        selected_figure: dict[str, Any],
        style_summary: dict[str, str],
    ) -> dict[str, Any]:
        config_hash = self._file_sha256(config_path) if config_path.is_file() else ""
        output_hash = self._file_sha256(output_path) if output_path.is_file() else ""
        project_files = sorted(path for path in snapshot_project_path.rglob("*") if path.is_file())
        snapshot_payload = [
            {
                "path": path.relative_to(snapshot_project_path).as_posix(),
                "sha256": self._file_sha256(path),
            }
            for path in project_files
        ]
        lock_status = self._mcp_lock_status()
        env_payload = {
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "selected_figure": self._public_selected_figure(selected_figure),
            "style_summary": style_summary,
            "lock_status": lock_status,
            "renderer": "project_config.figure_script",
            "mcp_surface_version": self._read_version(),
            "snapshot_files": snapshot_payload,
        }
        environment_hash = hashlib.sha256(
            json.dumps(env_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return {
            "job_id": job_id,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "renderer": "project_config.figure_script",
            "renderer_surface": "figops.render_project_figure",
            "mcp_surface_version": self._read_version(),
            "hub_git_commit": self._git_commit(),
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "source_project_path": self._public_project_path(project_path),
            "snapshot_project_path": str(snapshot_project_path),
            "selected_figure": self._public_selected_figure(selected_figure),
            "snapshot_file_count": len(snapshot_payload),
            "snapshot_files_sha256": hashlib.sha256(
                json.dumps(snapshot_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "config_sha256": config_hash,
            "output_sha256": output_hash,
            "environment_sha256": environment_hash,
            "lock_status": lock_status,
        }
