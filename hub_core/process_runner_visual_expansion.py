"""Per-input visual artifact execution for ``expand: each`` configurations."""

from __future__ import annotations

import os


def run_expanded_visual_artifacts(
    project_dir,
    config,
    build_state,
    build_state_path,
    config_hash,
    *,
    artifact,
    artifact_id,
    script,
    script_full_path,
    output,
    lang,
    runner,
    raw_inputs,
    glob_results,
    env_vars,
    timeout_seconds,
    step_kind,
    run_label,
    skip_label,
    force,
    target_format,
    font_scale,
    profile_name,
    log,
    flatten_glob_results,
    file_signature,
    collect_signatures,
    is_step_stale,
    resolve_path,
    prefix_uv_if_needed,
    run_command,
    verify_output_file,
    record_step_state,
    save_build_state,
    athena,
) -> bool:
    """Run and cache one visual artifact for each globbed input file."""
    all_matched = flatten_glob_results(glob_results)
    for matched_file in all_matched:
        stem = os.path.splitext(os.path.basename(matched_file))[0]
        expanded_output = output.replace("{stem}", stem)
        expanded_step_key = f"{artifact_id}:{script}->{expanded_output}"
        expanded_declared_inputs = [os.path.relpath(matched_file, project_dir)]
        expanded_declared_outputs = [expanded_output]
        iter_env_vars = dict(env_vars)
        iter_env_vars["GRAPH_HUB_INPUTS"] = matched_file

        iter_signature = {
            "script": file_signature(script_full_path, project_dir),
            "inputs": collect_signatures(project_dir, expanded_declared_inputs),
            "runner": runner,
            "lang": lang,
            "theme": {
                "format": target_format,
                "scale": font_scale,
                "profile": profile_name,
            },
            "input_patterns": raw_inputs,
            "expand_mode": "each",
        }
        declared_format = artifact.get("format")
        if declared_format:
            iter_signature["declared_format"] = str(declared_format).strip().lower()

        iter_output_signatures = collect_signatures(project_dir, expanded_declared_outputs)
        cache_enabled = bool(artifact.get("cache", True))

        if not cache_enabled:
            iter_stale = True
            iter_stale_reason = "cache disabled by config"
        else:
            iter_stale, iter_stale_reason = is_step_stale(
                step_kind=step_kind,
                step_key=expanded_step_key,
                signature=iter_signature,
                output_signatures=iter_output_signatures,
                build_state=build_state,
                config_hash=config_hash,
                force=force,
            )

        if not iter_stale:
            iter_output_path = resolve_path(project_dir, expanded_output)
            valid, verification_msg = verify_output_file(iter_output_path)
            if not valid:
                log(f"      ❌ Cached output verification failed: {verification_msg}")
                return False
            log(f"   [SKIP] {skip_label} {artifact_id} ({stem}): {expanded_output} (unchanged)")
            continue

        log(f"   [RUN] {run_label} {artifact_id} ({stem}): {expanded_output} ({iter_stale_reason})")

        if lang == "athena":
            from hub_core import athena_bridge

            athena_spec = artifact.get("spec", {})
            output_abs_path = resolve_path(project_dir, expanded_output)
            data_context = athena.load_solve_data_context()
            success = athena_bridge.render_from_athena_spec(athena_spec, output_abs_path, data_context)
            if not success:
                log(f"      ❌ Athena rendering failed for {artifact_id} ({stem}).")
                return False
        else:
            cmd = prefix_uv_if_needed([runner, script], config)
            try:
                if not run_command(
                    cmd,
                    project_dir,
                    additional_env=iter_env_vars,
                    timeout_seconds=timeout_seconds,
                ):
                    log(f"      ❌ Failed to generate {artifact_id} ({stem}). Stopping pipeline.")
                    return False
            except KeyError as exc:
                if "RESEARCH_COLOR_PALETTES" in str(exc) or "Nature Journal" in str(exc):
                    log("      ❌ Style Error: Invalid palette name in script. Check palettes.yaml.")
                else:
                    log(f"      ❌ Logic Error: Missing key {exc} in {run_label} script.")
                return False
            except Exception as exc:
                log(f"      ❌ Unexpected execution failure: {exc}")
                return False

        iter_output_path = resolve_path(project_dir, expanded_output)
        valid, verification_msg = verify_output_file(iter_output_path)
        if not valid:
            log(f"      ❌ Output verification failed: {verification_msg}")
            return False
        log(f"      ✅ Output verified: {verification_msg}")

        iter_output_signatures = collect_signatures(project_dir, expanded_declared_outputs)
        record_step_state(
            build_state=build_state,
            step_kind=step_kind,
            step_key=expanded_step_key,
            signature=iter_signature,
            outputs=iter_output_signatures,
            config_hash=config_hash,
        )
        save_build_state(build_state_path, build_state)

    return True
