"""
Visual Regression Module: Handles figure/PDF similarity checking and baseline management.
Used for publication-quality output verification.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import warnings
from datetime import datetime

from .config_parser import discover_projects_with_status, load_config
from .runtime_paths import resolve_hub_logs_dir, resolve_runtime_root
from .utils import resolve_path

try:
    from PIL import Image, ImageChops, ImageStat
except Exception:
    Image = None
    ImageChops = None
    ImageStat = None

DEFAULT_REPORT_DIRNAME = "hub_logs"
DEFAULT_REPORT_FILENAME = "check_all_report.json"
DEFAULT_BASELINE_DIRNAME = "figure_regression_baselines"
DEFAULT_BASELINE_MANIFEST = "baseline_manifest.json"
STDOUT_TAIL_LINES = 20
VALID_REGRESSION_BASELINE_MODES = {"ignore", "check", "update"}
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif"}
SUPPORTED_PDF_EXTENSIONS = {".pdf"}
PDF_PREVIEW_SIZE = 1024
# Visual regression tolerances. Defaults are strict (0.0) so byte-identical
# images pass and any visible pixel difference fails. Override per project via
# the config `regression` section: {"pixel_diff_ratio_tol": float, "pixel_rms_tol": float}.
DEFAULT_PIXEL_DIFF_RATIO_TOL = 0.0
DEFAULT_PIXEL_RMS_TOL = 0.0


def run_check_all(
    hub_path,
    root_dir,
    *,
    step="all",
    force=False,
    strict_lock=False,
    scan_depth=4,
    regression_baseline="ignore",
):
    hub_path = os.path.abspath(hub_path)
    root_dir = os.path.abspath(root_dir)
    regression_baseline = _normalize_regression_baseline_mode(regression_baseline)
    discovered_projects = discover_projects_with_status(root_dir, max_depth=scan_depth)
    if not discovered_projects:
        raise RuntimeError(f"No configured projects found under: {root_dir}")
    projects = [project for project in discovered_projects if project.get("valid")]
    invalid_projects = [
        {
            "project_name": project.get("name"),
            "project_path": project.get("path"),
            "config": project.get("config"),
            "errors": list(project.get("errors") or []),
        }
        for project in discovered_projects
        if not project.get("valid")
    ]

    baseline_state = _load_baseline_state(hub_path)
    started_at = datetime.now()
    results = []
    overall_success = len(invalid_projects) == 0

    for project in projects:
        project_rel = project["path"]
        project_dir = os.path.abspath(os.path.join(root_dir, project_rel))
        result = _run_single_project(
            hub_path,
            project_dir,
            step=step,
            force=force,
            strict_lock=strict_lock,
            baseline_state=baseline_state,
            regression_baseline=regression_baseline,
        )
        results.append(result)
        if not result.get("success"):
            overall_success = False

    if baseline_state.get("dirty"):
        _write_baseline_manifest(baseline_state)

    baseline_summary = _build_baseline_summary(results, baseline_state, regression_baseline)
    finished_at = datetime.now()
    report = {
        "schema_version": 3,
        "root_dir": root_dir,
        "hub_path": hub_path,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at.isoformat(timespec="seconds"),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "command_defaults": {
            "step": step,
            "force": bool(force),
            "strict_lock": bool(strict_lock),
            "scan_depth": scan_depth,
            "regression_baseline": regression_baseline,
        },
        "discovered_count": len(discovered_projects),
        "project_count": len(results),
        "invalid_count": len(invalid_projects),
        "passed_count": sum(1 for item in results if item.get("success")),
        "failed_count": sum(1 for item in results if not item.get("success")),
        "success": overall_success,
        "baseline_summary": baseline_summary,
        "invalid_projects": invalid_projects,
        "results": results,
    }
    report_path = write_check_all_report(hub_path, report)
    return report_path, report


def write_check_all_report(
    hub_path,
    report,
    *,
    log_dirname=DEFAULT_REPORT_DIRNAME,
    filename=DEFAULT_REPORT_FILENAME,
):
    if not isinstance(report, dict):
        raise RuntimeError("Check-all report must be a dict.")

    runtime_root = resolve_runtime_root()
    if log_dirname is None:
        log_dir = resolve_hub_logs_dir()
    elif os.path.isabs(log_dirname):
        log_dir = log_dirname
    else:
        log_dir = os.path.join(runtime_root, log_dirname)
    report_path = os.path.join(log_dir, filename)

    try:
        os.makedirs(log_dir, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError as exc:
        print(f"❌ Check-all report write failed: {report_path}\n   └─ {exc}")
        raise RuntimeError(f"failed to write check-all report: {report_path}") from exc

    print(f"🧪 Check-all report written: {report_path}")
    return report_path


def _run_single_project(
    hub_path,
    project_dir,
    *,
    step,
    force,
    strict_lock,
    baseline_state,
    regression_baseline,
):
    command = [
        sys.executable,
        os.path.join(hub_path, "orchestrator.py"),
        "--project",
        project_dir,
        "--step",
        step,
    ]
    if force:
        command.append("--force")
    if strict_lock:
        command.append("--strict-lock")

    started_at = datetime.now()
    try:
        proc = subprocess.run(
            command,
            cwd=hub_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        output = proc.stdout or ""
        exit_code = proc.returncode
    except Exception as exc:
        finished_at = datetime.now()
        return {
            "project_dir": project_dir,
            "project_name": os.path.basename(project_dir),
            "command": command,
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": finished_at.isoformat(timespec="seconds"),
            "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
            "exit_code": None,
            "success": False,
            "status": "runner_error",
            "stdout_tail": [f"{type(exc).__name__}: {exc}"],
            "figure_outputs": [],
        }

    finished_at = datetime.now()
    config, config_path, config_hash = load_config(project_dir)
    tolerances = _resolve_regression_tolerances(config)
    figure_outputs = _collect_figure_outputs(
        project_dir,
        config,
        baseline_state=baseline_state,
        project_name=_resolve_project_name(project_dir, config),
        regression_baseline=regression_baseline,
        tolerances=tolerances,
    )
    project_name = _resolve_project_name(project_dir, config)
    baseline_failed = any(not output.get("regression_ok", False) for output in figure_outputs)
    pipeline_success = exit_code == 0
    project_success = pipeline_success and not baseline_failed
    status = "success"
    if exit_code != 0:
        status = "failed"
    elif baseline_failed:
        status = "regression_failed"

    return {
        "project_dir": project_dir,
        "project_name": project_name,
        "config_path": config_path,
        "config_hash": config_hash,
        "command": command,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": finished_at.isoformat(timespec="seconds"),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "exit_code": exit_code,
        "success": project_success,
        "status": status,
        "pipeline_success": pipeline_success,
        "stdout_tail": _summarize_stdout(output),
        "figure_outputs": figure_outputs,
    }


def _resolve_project_name(project_dir, config):
    if isinstance(config, dict):
        project = config.get("project", {})
        if isinstance(project, dict):
            name = project.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return os.path.basename(project_dir)


def _collect_figure_outputs(project_dir, config, *, baseline_state, project_name, regression_baseline, tolerances=None):
    if not isinstance(config, dict):
        return []
    if tolerances is None:
        tolerances = _resolve_regression_tolerances(config)
    outputs = []
    outputs.extend(
        _collect_declared_outputs(
            project_dir,
            config.get("figures", []),
            baseline_state=baseline_state,
            project_name=project_name,
            regression_baseline=regression_baseline,
            tolerances=tolerances,
            id_prefix="Fig",
        )
    )
    outputs.extend(
        _collect_declared_outputs(
            project_dir,
            config.get("diagrams", []),
            baseline_state=baseline_state,
            project_name=project_name,
            regression_baseline=regression_baseline,
            tolerances=tolerances,
            id_prefix="Diagram",
        )
    )
    return outputs


def _collect_declared_outputs(
    project_dir,
    items,
    *,
    baseline_state,
    project_name,
    regression_baseline,
    tolerances,
    id_prefix,
):
    if not isinstance(items, list):
        return []

    outputs = []
    for idx, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        rel_output = item.get("output")
        if not isinstance(rel_output, str) or not rel_output.strip():
            continue
        output_path = resolve_path(project_dir, rel_output.strip())
        figure_id = item.get("id") or f"{id_prefix}{idx}"
        outputs.append(
            _build_output_record(
                baseline_state,
                project_dir=project_dir,
                project_name=project_name,
                figure_id=figure_id,
                output_path=output_path,
                regression_baseline=regression_baseline,
                tolerances=tolerances,
                artifact_kind="declared",
            )
        )
        sidecar_pdf = _resolve_sidecar_pdf(output_path)
        if sidecar_pdf:
            outputs.append(
                _build_output_record(
                    baseline_state,
                    project_dir=project_dir,
                    project_name=project_name,
                    figure_id=f"{figure_id}.pdf",
                    output_path=sidecar_pdf,
                    regression_baseline=regression_baseline,
                    tolerances=tolerances,
                    artifact_kind="sidecar_pdf",
                )
            )
    return outputs


def _build_output_record(
    baseline_state,
    *,
    project_dir,
    project_name,
    figure_id,
    output_path,
    regression_baseline,
    tolerances,
    artifact_kind,
):
    baseline_result = _resolve_figure_baseline(
        baseline_state,
        project_dir=project_dir,
        project_name=project_name,
        figure_id=figure_id,
        output_path=output_path,
        regression_baseline=regression_baseline,
        tolerances=tolerances,
    )
    return {
        "figure_id": figure_id,
        "artifact_kind": artifact_kind,
        "path": output_path,
        "exists": os.path.exists(output_path),
        "sha256": _hash_file(output_path),
        "size": _file_size(output_path),
        "dimensions": _artifact_dimensions(output_path),
        "baseline": baseline_result,
        "regression_ok": baseline_result.get("regression_ok", False),
    }


def _resolve_sidecar_pdf(output_path):
    root, ext = os.path.splitext(output_path)
    if ext.lower() == ".pdf":
        return None
    sidecar = root + ".pdf"
    return sidecar if os.path.exists(sidecar) else None


def _normalize_regression_baseline_mode(mode):
    key = str(mode or "ignore").strip().lower()
    if key not in VALID_REGRESSION_BASELINE_MODES:
        allowed = ", ".join(sorted(VALID_REGRESSION_BASELINE_MODES))
        raise RuntimeError(f"invalid regression baseline mode: {mode!r}. allowed: {allowed}")
    return key


def _load_baseline_state(hub_path):
    baseline_dir = os.path.join(resolve_hub_logs_dir(), DEFAULT_BASELINE_DIRNAME)
    files_dir = os.path.join(baseline_dir, "files")
    manifest_path = os.path.join(baseline_dir, DEFAULT_BASELINE_MANIFEST)
    manifest = {
        "schema_version": 1,
        "updated_at": None,
        "figures": {},
    }

    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                loaded_ver = loaded.get("schema_version", 1)
                if loaded_ver != 1:
                    warnings.warn(
                        f"Baseline manifest schema_version={loaded_ver} "
                        f"(expected 1) in {manifest_path}; results may be unreliable",
                        stacklevel=2,
                    )
                figures = loaded.get("figures", {})
                if isinstance(figures, dict):
                    manifest = {
                        "schema_version": loaded_ver,
                        "updated_at": loaded.get("updated_at"),
                        "figures": figures,
                    }
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"failed to load regression baseline manifest: {manifest_path}") from exc

    return {
        "baseline_dir": baseline_dir,
        "files_dir": files_dir,
        "manifest_path": manifest_path,
        "manifest": manifest,
        "dirty": False,
        "was_updated": False,
    }


def _write_baseline_manifest(baseline_state):
    manifest = baseline_state["manifest"]
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    manifest_path = baseline_state["manifest_path"]
    try:
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError as exc:
        raise RuntimeError(f"failed to write regression baseline manifest: {manifest_path}") from exc
    baseline_state["dirty"] = False
    baseline_state["was_updated"] = True


def _resolve_figure_baseline(
    baseline_state,
    *,
    project_dir,
    project_name,
    figure_id,
    output_path,
    regression_baseline,
    tolerances=None,
):
    if tolerances is None:
        tolerances = _resolve_regression_tolerances(None)
    current_exists = os.path.exists(output_path)
    current_hash = _hash_file(output_path)
    current_size = _file_size(output_path)
    key = _build_baseline_key(project_dir, figure_id)
    entry = baseline_state["manifest"]["figures"].get(key)

    if regression_baseline == "ignore":
        return {
            "mode": "ignore",
            "status": "skipped",
            "regression_ok": True,
            "baseline_path": entry.get("baseline_path") if isinstance(entry, dict) else None,
            "baseline_sha256": entry.get("sha256") if isinstance(entry, dict) else None,
            "current_sha256": current_hash,
            "diff": None,
        }

    if regression_baseline == "update":
        if current_exists:
            entry = _upsert_baseline_entry(
                baseline_state,
                key=key,
                project_dir=project_dir,
                project_name=project_name,
                figure_id=figure_id,
                output_path=output_path,
                current_hash=current_hash,
                current_size=current_size,
            )
            return {
                "mode": "update",
                "status": "updated",
                "regression_ok": True,
                "baseline_path": entry.get("baseline_path"),
                "baseline_sha256": entry.get("sha256"),
                "current_sha256": current_hash,
                "diff": None,
            }
        return {
            "mode": "update",
            "status": "missing_output",
            "regression_ok": False,
            "baseline_path": entry.get("baseline_path") if isinstance(entry, dict) else None,
            "baseline_sha256": entry.get("sha256") if isinstance(entry, dict) else None,
            "current_sha256": current_hash,
            "diff": None,
        }

    if not isinstance(entry, dict):
        return {
            "mode": "check",
            "status": "missing_baseline",
            "regression_ok": False,
            "baseline_path": None,
            "baseline_sha256": None,
            "current_sha256": current_hash,
            "diff": None,
        }

    if not current_exists:
        return {
            "mode": "check",
            "status": "missing_output",
            "regression_ok": False,
            "baseline_path": entry.get("baseline_path"),
            "baseline_sha256": entry.get("sha256"),
            "current_sha256": current_hash,
            "diff": None,
        }

    baseline_path = entry.get("baseline_path")
    baseline_hash = entry.get("sha256")
    if not baseline_path or not os.path.exists(baseline_path):
        return {
            "mode": "check",
            "status": "missing_baseline",
            "regression_ok": False,
            "baseline_path": baseline_path,
            "baseline_sha256": baseline_hash,
            "current_sha256": current_hash,
            "diff": None,
        }

    if bool(baseline_hash) and baseline_hash == current_hash:
        return {
            "mode": "check",
            "status": "matched",
            "regression_ok": True,
            "baseline_path": baseline_path,
            "baseline_sha256": baseline_hash,
            "current_sha256": current_hash,
            "diff": None,
        }

    # Hashes differ: do not decide on the hash alone. Compute pixel metrics and
    # gate on tolerances. A size mismatch fails outright (no silent cropping).
    diff = _build_visual_diff_metrics(baseline_path, output_path)
    regression_ok, status, reason = _evaluate_pixel_verdict(diff, tolerances)
    result = {
        "mode": "check",
        "status": status,
        "regression_ok": regression_ok,
        "baseline_path": baseline_path,
        "baseline_sha256": baseline_hash,
        "current_sha256": current_hash,
        "diff": diff,
    }
    if reason:
        result["reason"] = reason
    return result


def _resolve_regression_tolerances(config):
    pixel_diff_ratio_tol = DEFAULT_PIXEL_DIFF_RATIO_TOL
    pixel_rms_tol = DEFAULT_PIXEL_RMS_TOL
    if isinstance(config, dict):
        section = config.get("regression")
        if isinstance(section, dict):
            raw_ratio = section.get("pixel_diff_ratio_tol")
            if _is_finite_number(raw_ratio) and float(raw_ratio) >= 0:
                pixel_diff_ratio_tol = float(raw_ratio)
            raw_rms = section.get("pixel_rms_tol")
            if _is_finite_number(raw_rms) and float(raw_rms) >= 0:
                pixel_rms_tol = float(raw_rms)
    return {
        "pixel_diff_ratio_tol": pixel_diff_ratio_tol,
        "pixel_rms_tol": pixel_rms_tol,
    }


def _is_finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return value == value and value not in (float("inf"), float("-inf"))


def _evaluate_pixel_verdict(diff, tolerances):
    """Map diff metrics + tolerances to (regression_ok, status, reason).

    - No usable metrics (renderer/PIL unavailable, unsupported artifact): the
      content genuinely differs (hashes mismatched) and cannot be quantified,
      so fail closed.
    - Size mismatch: fail outright.
    - Otherwise: pass only when pixel_diff_ratio <= tol AND pixel_rms <= rms_tol.
    """
    if not isinstance(diff, dict):
        return False, "mismatch", "visual diff metrics unavailable; cannot verify within tolerance"

    if diff.get("size_mismatch"):
        baseline_dims = diff.get("baseline_dimensions")
        current_dims = diff.get("current_dimensions")
        return (
            False,
            "size_mismatch",
            f"dimensions differ: baseline={baseline_dims} current={current_dims}",
        )

    pixel_diff_ratio = diff.get("pixel_diff_ratio")
    pixel_rms = diff.get("pixel_rms")
    if not _is_finite_number(pixel_diff_ratio) or not _is_finite_number(pixel_rms):
        return False, "mismatch", "pixel metrics missing; cannot verify within tolerance"

    # Gate the verdict on the unrounded metrics so a genuinely-different image
    # whose rounded metrics collapse to 0.0 does not pass-open against a strict
    # tolerance; the rounded values stay only for reporting.
    ratio_for_verdict = diff.get("pixel_diff_ratio_raw", pixel_diff_ratio)
    rms_for_verdict = diff.get("pixel_rms_raw", pixel_rms)

    ratio_tol = tolerances["pixel_diff_ratio_tol"]
    rms_tol = tolerances["pixel_rms_tol"]
    within_tol = float(ratio_for_verdict) <= ratio_tol and float(rms_for_verdict) <= rms_tol
    if within_tol:
        return True, "within_tolerance", None
    reason = (
        f"pixel diff exceeds tolerance: pixel_diff_ratio={pixel_diff_ratio} (tol={ratio_tol}), "
        f"pixel_rms={pixel_rms} (tol={rms_tol})"
    )
    return False, "mismatch", reason


def _upsert_baseline_entry(
    baseline_state,
    *,
    key,
    project_dir,
    project_name,
    figure_id,
    output_path,
    current_hash,
    current_size,
):
    ext = os.path.splitext(output_path)[1].lower() or ".bin"
    project_hash = hashlib.sha256(os.path.abspath(project_dir).encode("utf-8")).hexdigest()[:12]
    dest_rel = os.path.join("files", project_hash, f"{figure_id}{ext}")
    dest_path = os.path.join(baseline_state["baseline_dir"], dest_rel)
    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(output_path, dest_path)
    except OSError as exc:
        raise RuntimeError(f"failed to update regression baseline snapshot: {dest_path}") from exc

    entry = {
        "project_dir": os.path.abspath(project_dir),
        "project_name": project_name,
        "figure_id": figure_id,
        "source_output": os.path.abspath(output_path),
        "baseline_path": dest_path,
        "baseline_relpath": dest_rel.replace(os.sep, "/"),
        "sha256": current_hash,
        "size": current_size,
        "dimensions": _artifact_dimensions(output_path),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    baseline_state["manifest"]["figures"][key] = entry
    baseline_state["dirty"] = True
    return entry


def _build_baseline_key(project_dir, figure_id):
    normalized = f"{os.path.abspath(project_dir)}::{figure_id}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _build_baseline_summary(results, baseline_state, regression_baseline):
    summary = {
        "mode": regression_baseline,
        "manifest_path": baseline_state["manifest_path"],
        "updated": bool(baseline_state.get("was_updated")),
        "figure_count": 0,
        "matched_count": 0,
        "within_tolerance_count": 0,
        "mismatch_count": 0,
        "size_mismatch_count": 0,
        "missing_baseline_count": 0,
        "missing_output_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
    }
    for result in results:
        for output in result.get("figure_outputs", []):
            summary["figure_count"] += 1
            baseline = output.get("baseline", {})
            status = baseline.get("status", "skipped")
            if status == "matched":
                summary["matched_count"] += 1
            elif status == "within_tolerance":
                summary["within_tolerance_count"] += 1
            elif status == "mismatch":
                summary["mismatch_count"] += 1
            elif status == "size_mismatch":
                summary["size_mismatch_count"] += 1
            elif status == "missing_baseline":
                summary["missing_baseline_count"] += 1
            elif status == "missing_output":
                summary["missing_output_count"] += 1
            elif status == "updated":
                summary["updated_count"] += 1
            else:
                summary["skipped_count"] += 1
    return summary


def _build_visual_diff_metrics(baseline_path, current_path):
    ext = os.path.splitext(current_path or baseline_path)[1].lower()
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        metrics = _build_image_diff_metrics(baseline_path, current_path)
        if metrics is not None:
            metrics["artifact_type"] = "image"
        return metrics
    if ext in SUPPORTED_PDF_EXTENSIONS:
        metrics = _build_pdf_diff_metrics(baseline_path, current_path)
        if metrics is not None:
            metrics.setdefault("artifact_type", "pdf")
        return metrics
    return None


def _build_image_diff_metrics(baseline_path, current_path):
    if not (_is_supported_image(baseline_path) and _is_supported_image(current_path)):
        return None

    try:
        with Image.open(baseline_path) as baseline_img, Image.open(current_path) as current_img:
            baseline_rgba = baseline_img.convert("RGBA")
            current_rgba = current_img.convert("RGBA")
            metrics = {
                "baseline_dimensions": [baseline_rgba.width, baseline_rgba.height],
                "current_dimensions": [current_rgba.width, current_rgba.height],
            }
            if baseline_rgba.size != current_rgba.size:
                # 크기 불일치는 크롭으로 숨기지 않는다: 정량 지표 없이 플래그만 반환하고
                # 판정은 _evaluate_pixel_verdict 에서 outright fail 로 처리한다.
                metrics["size_mismatch"] = True
                return metrics
            metrics["size_mismatch"] = False

            diff = ImageChops.difference(baseline_rgba, current_rgba)
            diff_gray = diff.convert("L")
            histogram = diff_gray.histogram()
            total_pixels = sum(histogram) or 1
            zero_pixels = histogram[0] if histogram else 0
            stat = ImageStat.Stat(diff)
            raw_pixel_diff_ratio = 1 - (zero_pixels / total_pixels)
            raw_pixel_rms = sum(stat.rms) / len(stat.rms)
            metrics["pixel_diff_ratio_raw"] = raw_pixel_diff_ratio
            metrics["pixel_rms_raw"] = raw_pixel_rms
            metrics["pixel_diff_ratio"] = round(raw_pixel_diff_ratio, 6)
            metrics["pixel_rms"] = round(raw_pixel_rms, 4)
            return metrics
    except Exception:
        return None


def _build_pdf_diff_metrics(baseline_path, current_path):
    metrics = {
        "artifact_type": "pdf",
        "renderer": "qlmanage",
        "render_mode": "thumbnail_first_page",
    }
    renderer = _resolve_pdf_renderer()
    if renderer is None:
        metrics["status"] = "pdf_visual_diff_unavailable"
        return metrics

    try:
        with tempfile.TemporaryDirectory(prefix="ghub-pdfdiff-") as tmpdir:
            baseline_preview = _render_pdf_preview(renderer, baseline_path, tmpdir)
            current_preview = _render_pdf_preview(renderer, current_path, tmpdir)
            metrics["baseline_preview_available"] = baseline_preview is not None
            metrics["current_preview_available"] = current_preview is not None
            if not baseline_preview or not current_preview:
                metrics["status"] = "pdf_render_failed"
                return metrics

            image_metrics = _build_image_diff_metrics(baseline_preview, current_preview)
            if image_metrics is None:
                metrics["status"] = "pdf_render_failed"
                return metrics

            metrics.update(image_metrics)
            metrics["status"] = "ok"
            return metrics
    except Exception:
        metrics["status"] = "pdf_render_failed"
        return metrics


def _artifact_dimensions(path):
    if _is_supported_image(path):
        return _image_dimensions(path)
    if os.path.splitext(path)[1].lower() in SUPPORTED_PDF_EXTENSIONS:
        renderer = _resolve_pdf_renderer()
        if renderer is None:
            return None
        try:
            with tempfile.TemporaryDirectory(prefix="ghub-pdfsize-") as tmpdir:
                preview_path = _render_pdf_preview(renderer, path, tmpdir)
                return _image_dimensions(preview_path) if preview_path else None
        except Exception:
            return None
    return None


def _image_dimensions(path):
    if not _is_supported_image(path):
        return None
    try:
        with Image.open(path) as img:
            return [img.width, img.height]
    except Exception:
        return None


def _resolve_pdf_renderer():
    qlmanage = shutil.which("qlmanage")
    if qlmanage:
        return {"name": "qlmanage", "cmd": qlmanage}
    return None


def _render_pdf_preview(renderer, pdf_path, tmpdir):
    if not renderer or renderer.get("name") != "qlmanage":
        return None
    proc = subprocess.run(
        [
            renderer["cmd"],
            "-t",
            "-s",
            str(PDF_PREVIEW_SIZE),
            "-o",
            tmpdir,
            pdf_path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    stem = os.path.basename(pdf_path) + ".png"
    candidate = os.path.join(tmpdir, stem)
    if os.path.exists(candidate):
        return candidate
    pngs = [os.path.join(tmpdir, name) for name in os.listdir(tmpdir) if name.lower().endswith(".png")]
    return pngs[0] if pngs else None


def _is_supported_image(path):
    if Image is None or not isinstance(path, str):
        return False
    return os.path.splitext(path)[1].lower() in SUPPORTED_IMAGE_EXTENSIONS


def _hash_file(path):
    if not os.path.exists(path) or not os.path.isfile(path):
        return None
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError:
        return None
    return hasher.hexdigest()


def _file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _summarize_stdout(output):
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if len(lines) <= STDOUT_TAIL_LINES:
        return lines
    return lines[-STDOUT_TAIL_LINES:]
