"""Single-output visual artifact cache, execution, and verification flow."""

from __future__ import annotations


def run_visual_artifact_batch(
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
    expand_mode,
    declared_inputs,
    declared_outputs,
    env_vars,
    timeout_seconds,
    step_kind,
    step_key,
    run_label,
    skip_label,
    force,
    target_format,
    font_scale,
    profile_name,
    log,
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
    """Run one non-expanded artifact while preserving cache and output contracts."""
    signature = {
        "script": file_signature(script_full_path, project_dir),
        "inputs": collect_signatures(project_dir, declared_inputs),
        "runner": runner,
        "lang": lang,
        "theme": {
            "format": target_format,
            "scale": font_scale,
            "profile": profile_name,
        },
        "input_patterns": raw_inputs,
        "expand_mode": expand_mode,
    }
    declared_format = artifact.get("format")
    if declared_format:
        signature["declared_format"] = str(declared_format).strip().lower()

    output_signatures = collect_signatures(project_dir, declared_outputs)
    cache_enabled = bool(artifact.get("cache", True))

    if not cache_enabled:
        stale = True
        stale_reason = "cache disabled by config"
    else:
        stale, stale_reason = is_step_stale(
            step_kind=step_kind,
            step_key=step_key,
            signature=signature,
            output_signatures=output_signatures,
            build_state=build_state,
            config_hash=config_hash,
            force=force,
        )

    if not stale:
        output_path = resolve_path(project_dir, output)
        valid, verification_msg = verify_output_file(output_path)
        if not valid:
            log(f"      ❌ Cached output verification failed: {verification_msg}")
            return False
        log(f"   [SKIP] {skip_label} {artifact_id}: {output} (unchanged)")
        return True

    log(f"   [RUN] {run_label} {artifact_id}: {output} ({stale_reason})")

    if lang == "athena":
        from hub_core import athena_bridge

        athena_spec = artifact.get("spec", {})
        output_abs_path = resolve_path(project_dir, output)
        data_context = athena.load_solve_data_context()
        success = athena_bridge.render_from_athena_spec(athena_spec, output_abs_path, data_context)
        if not success:
            log(f"      ❌ Athena rendering failed for {artifact_id}.")
            return False
    else:
        cmd = prefix_uv_if_needed([runner, script], config)
        try:
            if not run_command(cmd, project_dir, additional_env=env_vars, timeout_seconds=timeout_seconds):
                log(f"      ❌ Failed to generate {artifact_id}. Stopping pipeline.")
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

    output_path = resolve_path(project_dir, output)
    valid, verification_msg = verify_output_file(output_path)
    if not valid:
        log(f"      ❌ Output verification failed: {verification_msg}")
        return False
    log(f"      ✅ Output verified: {verification_msg}")

    output_signatures = collect_signatures(project_dir, declared_outputs)
    record_step_state(
        build_state=build_state,
        step_kind=step_kind,
        step_key=step_key,
        signature=signature,
        outputs=output_signatures,
        config_hash=config_hash,
    )
    save_build_state(build_state_path, build_state)
    return True
