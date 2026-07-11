"""Persistent baseline state helpers for visual regression checks.

This module owns manifest loading, snapshot updates, and aggregate reporting.
The public compatibility façade remains in :mod:`hub_core.visual_regression`.
"""

import hashlib
import json
import os
import shutil
import warnings


def load_baseline_state(*, resolve_hub_logs_dir, baseline_dirname, manifest_filename):
    """Load the baseline manifest and return its mutable run state."""
    baseline_dir = os.path.join(resolve_hub_logs_dir(), baseline_dirname)
    files_dir = os.path.join(baseline_dir, "files")
    manifest_path = os.path.join(baseline_dir, manifest_filename)
    manifest = {
        "schema_version": 1,
        "updated_at": None,
        "figures": {},
    }

    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                loaded_ver = loaded.get("schema_version", 1)
                if loaded_ver != 1:
                    warnings.warn(
                        f"Baseline manifest schema_version={loaded_ver} "
                        f"(expected 1) in {manifest_path}; results may be unreliable",
                        stacklevel=3,
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


def write_baseline_manifest(baseline_state, *, updated_at):
    """Persist a dirty baseline manifest using the existing durable write contract."""
    manifest = baseline_state["manifest"]
    manifest["updated_at"] = updated_at
    manifest_path = baseline_state["manifest_path"]
    try:
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise RuntimeError(f"failed to write regression baseline manifest: {manifest_path}") from exc
    baseline_state["dirty"] = False
    baseline_state["was_updated"] = True


def resolve_figure_baseline(
    baseline_state,
    *,
    project_dir,
    project_name,
    figure_id,
    output_path,
    regression_baseline,
    tolerances,
    path_exists,
    hash_file,
    file_size,
    build_baseline_key,
    upsert_baseline_entry,
    build_visual_diff_metrics,
    evaluate_pixel_verdict,
):
    """Resolve one output against a persisted baseline under the selected mode."""
    current_exists = path_exists(output_path)
    current_hash = hash_file(output_path)
    current_size = file_size(output_path)
    key = build_baseline_key(project_dir, figure_id)
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
            entry = upsert_baseline_entry(
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
    if not baseline_path or not path_exists(baseline_path):
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

    diff = build_visual_diff_metrics(baseline_path, output_path)
    regression_ok, status, reason = evaluate_pixel_verdict(diff, tolerances)
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


def upsert_baseline_entry(
    baseline_state,
    *,
    key,
    project_dir,
    project_name,
    figure_id,
    output_path,
    current_hash,
    current_size,
    artifact_dimensions,
    updated_at,
):
    """Copy one output into baseline storage and update its manifest entry."""
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
        "dimensions": artifact_dimensions(output_path),
        "updated_at": updated_at,
    }
    baseline_state["manifest"]["figures"][key] = entry
    baseline_state["dirty"] = True
    return entry


def build_baseline_key(project_dir, figure_id):
    """Return the stable manifest key for one project output."""
    normalized = f"{os.path.abspath(project_dir)}::{figure_id}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_baseline_summary(results, baseline_state, regression_baseline):
    """Aggregate per-figure baseline statuses for the check-all report."""
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
