"""Project snapshot, script execution, and failure-artifact runtime helpers."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import traceback
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hub_core.adapters import select_adapters
from hub_core.external_raw_execution import is_external_raw_declaration
from hub_core.mcp.render_errors import ProjectRenderExportError, ProjectRenderScriptError
from hub_core.mcp.render_geometry import SCRIPT_OUTPUT_TAIL_LINES, _geometry_stub, _layout_report_from_geometry
from hub_core.process_supervisor import supervise_process
from hub_core.project_paths import (
    open_verified_project_input,
    resolve_project_input,
    snapshot_project_input,
)
from hub_core.provenance_inputs import expand_project_input_files
from hub_core.redaction import redact_text


class McpProjectRuntimeMixin:
    """Project snapshot and script-runtime methods inherited by the MCP server."""

    def _project_render_timeout_seconds(self) -> float:
        """Return the script budget supplied by the render-orchestration façade."""
        raise NotImplementedError

    def _copy_project_snapshot(
        self,
        *,
        source_project: Path,
        snapshot_project: Path,
        config_relpath: str,
        selected_figure: dict[str, Any],
        claim_inventory: Mapping[str, Any] | None = None,
    ) -> list[str]:
        if snapshot_project.exists():
            shutil.rmtree(snapshot_project)
        snapshot_project.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []

        def copy_relative_path(raw_relpath: str) -> None:
            try:
                relpath = self._project_relative_path(raw_relpath, "snapshot path")
            except ValueError as exc:
                raise ProjectRenderExportError(str(exc)) from exc
            source_path = source_project / relpath
            destination_path = snapshot_project / relpath
            if not source_path.exists():
                raise ProjectRenderExportError(f"Required project snapshot path not found: {raw_relpath}")
            if source_path.is_symlink():
                raise ProjectRenderExportError(f"Project snapshot refuses symlinked path: {raw_relpath}")
            try:
                source_path.resolve().relative_to(source_project.resolve())
            except ValueError as exc:
                raise ProjectRenderExportError(f"Project snapshot path escapes project root: {raw_relpath}") from exc
            if source_path.is_dir():
                self._copy_project_snapshot_directory(source_path, destination_path, copied)
                return
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)
            copied.append(str(destination_path))

        copy_relative_path(config_relpath)
        script_rel = str(selected_figure.get("script") or "").split("::")[0]
        if script_rel:
            copy_relative_path(script_rel)
        try:
            project_declarations = [
                declaration
                for declaration in self._selected_figure_declared_inputs(selected_figure)
                if not is_external_raw_declaration(declaration)
            ]
            input_paths = expand_project_input_files(
                source_project,
                project_declarations,
                require_matches=True,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise ProjectRenderExportError(str(exc)) from exc
        for input_path in input_paths:
            copy_relative_path(input_path.relative_to(source_project.resolve()).as_posix())
        for declaration in self._verified_claim_snapshot_declarations(
            source_project,
            selected_figure,
            claim_inventory,
        ):
            copy_relative_path(declaration)
        for standard_folder in ("hub_scripts", "results/data"):
            if (source_project / standard_folder).is_dir():
                copy_relative_path(standard_folder)
        return [str(path) for path in snapshot_project.rglob("*") if path.is_file()]

    @staticmethod
    def _verified_claim_snapshot_declarations(
        source_project: Path,
        selected_figure: Mapping[str, Any],
        claim_inventory: Mapping[str, Any] | None,
    ) -> list[str]:
        """Discover verified claim-lineage membership for immutable snapshot replay.

        This is intentionally gated by the already verified inventory decision.
        Invalid or review-only inventories remain non-promotable and do not widen
        the execution snapshot.  Promotion later recomputes the full inventory
        from these copied bytes and requires an exact canonical match.
        """

        if not isinstance(claim_inventory, Mapping) or claim_inventory.get("status") != "verified":
            return []
        inventory_ref = claim_inventory.get("artifact_ref")
        configured_ref = selected_figure.get("claim_inventory")
        if not isinstance(inventory_ref, str) or inventory_ref != configured_ref:
            raise ProjectRenderExportError(
                "Verified claim inventory binding disagrees with figures[].claim_inventory"
            )

        def read_json(declaration: str, *, purpose: str, limit: int) -> dict[str, Any]:
            resolved = resolve_project_input(source_project, declaration, purpose=purpose)
            select_adapters({}).prefetcher.ensure_local([str(resolved)])
            identity = snapshot_project_input(source_project, declaration, purpose=purpose)
            with open_verified_project_input(
                source_project,
                declaration,
                expected_snapshot=identity,
                purpose=purpose,
            ) as handle:
                payload = handle.read(limit + 1)
            if len(payload) > limit:
                raise ProjectRenderExportError(f"{purpose} exceeds its bounded snapshot limit")

            def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                result: dict[str, Any] = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError(f"duplicate JSON key: {key}")
                    result[key] = value
                return result

            try:
                loaded = json.loads(
                    payload.decode("utf-8"),
                    object_pairs_hook=reject_duplicate_keys,
                )
            except (UnicodeError, ValueError) as exc:
                raise ProjectRenderExportError(f"{purpose} changed after claim verification") from exc
            if not isinstance(loaded, dict):
                raise ProjectRenderExportError(f"{purpose} must remain a JSON object")
            return loaded

        inventory = read_json(inventory_ref, purpose="claim inventory snapshot", limit=256 * 1024)
        raw_evidence = inventory.get("calculation_evidence_paths")
        if not isinstance(raw_evidence, list) or len(raw_evidence) > 32 or any(
            not isinstance(item, str) for item in raw_evidence
        ):
            raise ProjectRenderExportError(
                "Verified claim inventory calculation evidence membership changed before snapshot"
            )

        declarations: list[str] = [inventory_ref]
        for evidence_ref in raw_evidence:
            lineage = read_json(
                evidence_ref,
                purpose="calculation evidence snapshot",
                limit=1024 * 1024,
            )
            declarations.append(evidence_ref)
            descriptors = [lineage.get("calculation_artifact")]
            producer = lineage.get("producer")
            if isinstance(producer, Mapping):
                descriptors.extend([producer.get("script"), producer.get("config")])
            for field in ("input_artifacts", "output_artifacts"):
                values = lineage.get(field)
                if isinstance(values, list):
                    descriptors.extend(values)
            for descriptor in descriptors:
                if not isinstance(descriptor, Mapping) or not isinstance(descriptor.get("path"), str):
                    raise ProjectRenderExportError(
                        "Verified calculation evidence lineage changed before snapshot"
                    )
                declarations.append(str(descriptor["path"]))
        return list(dict.fromkeys(declarations))

    @staticmethod
    def _copy_project_snapshot_directory(source_dir: Path, destination_dir: Path, copied: list[str]) -> None:
        ignored_dirs = {".git", ".venv", "__pycache__", ".pytest_cache", ".dvc"}
        source_root = source_dir.resolve()
        for current_root, dirs, files in os.walk(source_dir):
            current_path = Path(current_root)
            dirs[:] = [dirname for dirname in dirs if dirname not in ignored_dirs]
            for dirname in list(dirs):
                child_dir = current_path / dirname
                if child_dir.is_symlink():
                    raise ProjectRenderExportError(f"Project snapshot refuses symlinked directory: {child_dir}")
                try:
                    child_dir.resolve().relative_to(source_root)
                except ValueError as exc:
                    raise ProjectRenderExportError(
                        f"Project snapshot directory escapes source tree: {child_dir}"
                    ) from exc
            relative_root = current_path.relative_to(source_dir)
            destination_root = destination_dir / relative_root
            destination_root.mkdir(parents=True, exist_ok=True)
            for filename in files:
                source_file = current_path / filename
                if source_file.is_symlink():
                    raise ProjectRenderExportError(f"Project snapshot refuses symlinked file: {source_file}")
                try:
                    source_file.resolve().relative_to(source_root)
                except ValueError as exc:
                    raise ProjectRenderExportError(f"Project snapshot file escapes source tree: {source_file}") from exc
                destination_file = destination_root / filename
                shutil.copy2(source_file, destination_file)
                copied.append(str(destination_file))

    def _run_project_figure_script(
        self,
        *,
        snapshot_project_path: Path,
        selected_figure: dict[str, Any],
        style_summary: dict[str, str],
        input_paths: list[Path] | None = None,
    ) -> None:
        try:
            script_rel = self._project_relative_path(
                str(selected_figure.get("script") or "").split("::")[0],
                "figures[].script",
            )
        except ValueError as exc:
            raise ProjectRenderExportError(str(exc)) from exc
        try:
            script_path = resolve_project_input(
                snapshot_project_path,
                script_rel.as_posix(),
                purpose="figures[].script",
            )
        except (FileNotFoundError, ValueError) as exc:
            raise ProjectRenderExportError(str(exc)) from exc
        # job_root is the snapshot parent; the sidecar must land OUTSIDE the snapshot
        # tree so it never enters environment_sha256 (which rglob-hashes the snapshot).
        job_root = snapshot_project_path.parent
        script_output_path = job_root / "script_output.json"
        env = os.environ.copy()
        env.update(
            {
                "RESEARCH_HUB_PATH": str(self.hub_path),
                "PYTHONPATH": self._pythonpath_with_hub(env),
                "PROJECT_ROOT": str(snapshot_project_path),
                "THEME_FORMAT": style_summary["target_format"],
                "THEME_PROFILE": style_summary["profile"],
                "THEME_OUTPUT_FORMAT": style_summary["output_format"],
                "GEOMETRY_DIAGNOSTICS_OUT": str(job_root / "geometry_diagnostics.json"),
                "GEOMETRY_DIAGNOSTICS_DEADLINE": str(time.time() + self._project_render_timeout_seconds()),
                "MPLBACKEND": env.get("MPLBACKEND", "Agg"),
                "MPLCONFIGDIR": env.get("MPLCONFIGDIR", str(job_root / ".matplotlib")),
            }
        )
        if input_paths:
            env["GRAPH_HUB_INPUTS"] = os.pathsep.join(str(path) for path in input_paths)
        Path(env["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
        output_lines: list[str] = []

        def capture_output(line: str) -> None:
            output_lines.append(line)
            if len(output_lines) > SCRIPT_OUTPUT_TAIL_LINES:
                del output_lines[:-SCRIPT_OUTPUT_TAIL_LINES]

        suffix = script_path.suffix.lower()
        if suffix == ".py":
            command = [sys.executable, str(script_path)]
        elif suffix == ".r":
            rscript = shutil.which("Rscript")
            if rscript is None:
                raise ProjectRenderScriptError("Rscript is unavailable; the .R figure script was not executed.")
            command = [rscript, str(script_path)]
        else:
            raise ProjectRenderScriptError("Configured figure scripts must use .py or .R.")
        completed = supervise_process(
            command,
            cwd=str(snapshot_project_path),
            env=env,
            timeout_seconds=self._project_render_timeout_seconds(),
            on_output=capture_output,
        )
        script_output = "".join(output_lines)
        if completed.timed_out:
            self._write_project_script_output(
                script_output_path,
                returncode=None,
                stdout=script_output,
                stderr=completed.failure or "",
                timed_out=True,
            )
            raise TimeoutError(f"Figure script timed out after {self._project_render_timeout_seconds():.1f} seconds.")
        self._write_project_script_output(
            script_output_path,
            returncode=completed.returncode,
            stdout=script_output,
            stderr=completed.failure or "",
            timed_out=False,
        )
        if completed.failure or completed.returncode != 0:
            message = completed.failure or script_output.strip() or f"Figure script exited {completed.returncode}."
            raise ProjectRenderScriptError(
                message,
                returncode=completed.returncode,
                script_output=self._script_output_tail(script_output, completed.failure or ""),
            )

    @staticmethod
    def _normalize_script_stream(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    @classmethod
    def _script_output_tail(cls, stdout: Any, stderr: Any) -> list[str]:
        combined = "\n".join(
            part
            for part in (
                cls._normalize_script_stream(stdout),
                cls._normalize_script_stream(stderr),
            )
            if part
        )
        lines = [redact_text(line.rstrip()) for line in combined.splitlines() if line.strip()]
        return lines[-SCRIPT_OUTPUT_TAIL_LINES:]

    @classmethod
    def _write_project_script_output(
        cls,
        path: Path,
        *,
        returncode: int | None,
        stdout: Any,
        stderr: Any,
        timed_out: bool,
    ) -> None:
        payload = {
            "returncode": returncode,
            "timed_out": bool(timed_out),
            "tail": cls._script_output_tail(stdout, stderr),
        }
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _read_project_script_output(job_root: Path) -> list[str]:
        try:
            payload = json.loads((job_root / "script_output.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        tail = payload.get("tail")
        if not isinstance(tail, list):
            return []
        return [str(line) for line in tail if str(line).strip()]

    def _project_failure_script_output(self, exc: Exception, job_root: Path) -> list[str]:
        explicit = getattr(exc, "script_output", None)
        if isinstance(explicit, list) and explicit:
            return [redact_text(str(line)) for line in explicit if str(line).strip()]
        return self._read_project_script_output(job_root)

    @staticmethod
    def _exception_error_lines(exc: Exception) -> list[str]:
        lines = [line.rstrip() for line in traceback.format_exception(type(exc), exc, exc.__traceback__)]
        compact = [redact_text(line) for line in lines if line.strip()]
        message = redact_text(str(exc).strip())
        tail = compact[-SCRIPT_OUTPUT_TAIL_LINES:]
        if message:
            tail = [line for line in tail if line != message]
            return [message, *tail]
        return tail or [type(exc).__name__]

    def _pythonpath_with_hub(self, env: dict[str, str]) -> str:
        hub_path = str(self.hub_path)
        current = env.get("PYTHONPATH", "")
        parts = [part for part in current.split(os.pathsep) if part and part != hub_path]
        return os.pathsep.join([hub_path, *parts])

    @staticmethod
    def _project_context_render_warnings(project_path: Path) -> list[str]:
        context_path = project_path / "hub_scripts" / "project_context.py"
        if not context_path.exists():
            return []
        try:
            context_text = context_path.read_text(encoding="utf-8")
        except OSError as exc:
            return [f"Could not inspect hub_scripts/project_context.py for MCP render path safety: {exc}"]
        if "RESEARCH_HUB_PATH" in context_text:
            return []
        return [
            "hub_scripts/project_context.py does not reference RESEARCH_HUB_PATH; MCP snapshot renders "
            "inject the canonical hub on PYTHONPATH, but this project should be updated to the env-first "
            "project_context.py template for portable direct runs."
        ]

    def _write_project_render_failure_artifacts(
        self,
        *,
        job_id: str,
        job_root: Path,
        snapshot_project_path: Path,
        selected_figure: dict[str, Any],
        manifest_path: Path,
        status_path: Path,
        latest_dir: Path,
        created_paths: list[str],
        failure_stage: str,
        resolution_hint: str,
        baseline_comparison: dict[str, Any],
        provenance: dict[str, Any],
        style_summary: dict[str, Any],
        script_output: list[str] | None = None,
        layout_report: dict[str, Any] | None = None,
        raw_integrity_status: dict[str, Any] | None = None,
        canonical_docs_registry: dict[str, Any] | None = None,
        research_ops_policy: dict[str, Any] | None = None,
    ) -> list[str]:
        script_output = script_output or []
        layout_report = layout_report or _layout_report_from_geometry(
            _geometry_stub("render_execution_failed"),
            failure_stage=failure_stage,
            script_output=script_output,
        )
        created = list(created_paths)
        manifest = {
            "job_id": job_id,
            "renderer_surface": "figops.render_project_figure",
            "job_root": str(job_root),
            "snapshot_project_path": str(snapshot_project_path),
            "selected_figure": selected_figure,
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
            "style_summary": style_summary,
            "visual_preflight_status": {"passed": False, "checks": [], "warnings": ["render_execution_failed"]},
            "layout_report": layout_report,
            "failure_stage": failure_stage,
            "resolution_hint": resolution_hint,
            "script_output": script_output,
            "artifact_status": "failed",
            "baseline_comparison": baseline_comparison,
            "manual_review_needed": True,
            "provenance": provenance,
            "raw_integrity_status": raw_integrity_status or {},
            "canonical_docs_registry": canonical_docs_registry or {},
            "research_ops_policy": research_ops_policy or {},
        }
        status_payload = self._render_status_payload(
            job_id=job_id,
            status="error",
            summary="Project figure render execution failed.",
            manifest_path=manifest_path,
            output_path=snapshot_project_path / str(selected_figure.get("output") or ""),
            artifact_status="failed",
            manual_review_needed=True,
            failure_stage=failure_stage,
            resolution_hint=resolution_hint,
        )
        if script_output:
            status_payload["script_output"] = script_output
        status_payload["layout_report"] = layout_report
        status_payload["provenance"] = provenance
        status_payload["style_summary"] = style_summary
        return self._write_failure_artifacts_to_disk(
            manifest, manifest_path, status_payload, status_path, latest_dir, created
        )
