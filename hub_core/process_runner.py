import glob as glob_module
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .cache_manager import (
    collect_signatures,
    file_signature,
    is_step_stale,
    record_step_state,
    save_build_state,
)
from .config_parser import get_language_policy, normalize_lang, resolve_presets, resolve_step_style
from .data_contract import get_data_contract_paths
from .utils import (
    ensure_local_files,
    expand_glob_inputs,
    flatten_glob_results,
    get_hub_path,
    is_executable_available,
    normalize_string_list,
    resolve_path,
    scan_csv_export_anomalies,
    verify_output_file,
)


def _fallback_sanitize_path(raw_path: str, allowed_roots: list[Path]) -> Path:
    """Standalone fallback when Athena's path_sanitizer is unavailable."""
    if ".." in Path(raw_path).parts:
        raise ValueError(f"Path traversal rejected: '..' found in '{raw_path}'")

    candidate = Path(raw_path).expanduser().resolve()
    for root in allowed_roots:
        resolved_root = root.expanduser().resolve()
        try:
            candidate.relative_to(resolved_root)
            return candidate
        except ValueError:
            continue

    allowed_strs = ", ".join(str(root) for root in allowed_roots)
    raise ValueError(f"Path '{candidate}' is outside all allowed roots: {allowed_strs}")


def _sanitize_script_path(raw_path: str, project_dir: str) -> str:
    """Verify script path is within [Graph_making_hub] before execution.

    Raises ValueError with a descriptive message if the resolved path
    escapes the hub root.  Returns the resolved absolute path string on success.
    """
    hub_root = Path(get_hub_path()).resolve()
    project_root = Path(project_dir).resolve()
    allowed = [hub_root, project_root]
    try:
        _ensure_athena_on_path()
        from utils.path_sanitizer import sanitize_path as _sp
    except Exception:
        _sp = _fallback_sanitize_path
    try:
        return str(_sp(raw_path, allowed))
    except ValueError as exc:
        raise ValueError(f"Script path rejected (path traversal guard): {exc}") from exc


try:
    from themes.style_profiles import resolve_profile_name
except Exception:

    def resolve_profile_name(profile_name=None):
        if profile_name is None:
            return "baseline"
        key = str(profile_name).strip().lower()
        return key if key else "baseline"


_athena_path_registered = False


def _set_failure_context(failure_context: dict | None, stage: str, message: str) -> None:
    if not isinstance(failure_context, dict):
        return
    failure_context.setdefault("stage", stage)
    failure_context.setdefault("message", message)


def _ensure_athena_on_path() -> None:
    global _athena_path_registered
    if _athena_path_registered:
        return
    athena_root = os.path.abspath(os.path.join(get_hub_path(), "..", "[Athena]"))
    if athena_root not in sys.path:
        sys.path.insert(0, athena_root)
    _athena_path_registered = True


def _load_solve_context_env() -> dict[str, str]:
    try:
        _ensure_athena_on_path()
        from integrations.solve_live_context import load_as_env_vars

        return load_as_env_vars()
    except Exception as exc:
        print(f"      ⚠️  Failed to load solve context env: {type(exc).__name__}: {exc}")
        return {}


def _load_solve_data_context() -> dict:
    try:
        _ensure_athena_on_path()
        from integrations.solve_live_context import load_as_data_context

        return load_as_data_context()
    except Exception as exc:
        print(f"      ⚠️  Failed to load solve data context: {type(exc).__name__}: {exc}")
        return {}


def _resolve_runner(lang, step_cfg, config):
    execution = config.get("execution", {}) if isinstance(config.get("execution", {}), dict) else {}
    if lang == "r":
        return step_cfg.get("r_exec") or execution.get("rscript") or "Rscript"
    if lang in {"python", "py"}:
        return step_cfg.get("python_exec") or execution.get("python") or sys.executable
    return None


def _prefix_uv_if_needed(cmd, config):
    environment = config.get("environment", {})
    if environment.get("uv_run") is True:
        return ["uv", "run"] + cmd
    return cmd


def _build_r_cmd(runner: str, script_path: str, config: dict) -> list[str]:
    """Build the Rscript command, wrapping with renv::activate() when r_strict is enabled."""
    environment = config.get("environment", {}) or {}
    r_strict = bool(environment.get("r_strict", False))
    if r_strict:
        safe_path = str(script_path).replace("\\", "\\\\").replace("'", "\\'")
        renv_expr = (
            "tryCatch("
            "renv::activate(), "
            "error=function(e) stop(paste('[renv] activate() failed:', conditionMessage(e)))"
            f"); source('{safe_path}')"
        )
        return [runner, "-e", renv_expr]
    return [runner, script_path]


_OUTPUT_TAIL_LINES = 20


def run_command(cmd_list, cwd, additional_env=None):
    # This assumes orchestrator.py is one level up from hub_core
    hub_path = get_hub_path()

    env = os.environ.copy()
    env["PYTHONPATH"] = (
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.pathsep + env.get("PYTHONPATH", "")
    )
    env["RESEARCH_HUB_PATH"] = hub_path
    env["PROJECT_ROOT"] = os.path.abspath(cwd)
    if "MPLCONFIGDIR" not in env:
        mpl_cache = os.path.join(tempfile.gettempdir(), "graph_hub_mplcache")
        os.makedirs(mpl_cache, exist_ok=True)
        env["MPLCONFIGDIR"] = mpl_cache
    if "UV_CACHE_DIR" not in env:
        uv_cache_dir = os.path.join(tempfile.gettempdir(), "graph_hub_uv_cache")
        os.makedirs(uv_cache_dir, exist_ok=True)
        env["UV_CACHE_DIR"] = uv_cache_dir
    if "MPLBACKEND" not in env and not env.get("DISPLAY"):
        env["MPLBACKEND"] = "Agg"
    if additional_env:
        env.update(additional_env)

    try:
        process = subprocess.Popen(
            cmd_list,
            cwd=os.path.abspath(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        output_lines: list[str] = []
        for line in process.stdout:
            stripped = line.strip()
            print(f"      {stripped}")
            if stripped:
                output_lines.append(stripped)
        process.wait(timeout=600)  # 10분 타임아웃
        if process.returncode != 0:
            print(f"      ❌ Execution failed with return code {process.returncode}")
            tail = output_lines[-_OUTPUT_TAIL_LINES:] if len(output_lines) > _OUTPUT_TAIL_LINES else output_lines
            if tail:
                print(f"      ── last {len(tail)} lines ──")
                for tail_line in tail:
                    print(f"      {tail_line}")
        return process.returncode == 0
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        print("      ❌ Execution timed out (600s limit)")
        return False
    except Exception as e:
        print(f"      ❌ Execution failed: {e}")
        return False


def run_analysis(project_dir, config, build_state, build_state_path, config_hash, force=False):
    print(f"\n🚀 [Analysis Step] {config['project']['name']}")
    policy = get_language_policy(config)
    pipeline = config.get("pipeline", {})
    steps = pipeline.get("analysis", [])
    contract_paths = get_data_contract_paths(config)

    if not steps:
        print("   (No analysis steps defined)")
        return True

    for i, step in enumerate(steps, 1):
        script = step["script"]
        lang = normalize_lang(step.get("lang", "R")) or "r"
        step_key = f"{i}:{script}"

        if (not policy["allow_nonstandard"]) and lang != policy["analysis_lang"]:
            print(f"      ❌ Policy violation: analysis language must be '{policy['analysis_lang']}', got '{lang}'.")
            return False

        script_full_path = resolve_path(project_dir, script)
        try:
            script_full_path = _sanitize_script_path(script_full_path, project_dir)
        except ValueError as exc:
            print(f"      ❌ {exc}")
            return False
        if not os.path.exists(script_full_path):
            print(f"      ❌ Script not found: {script_full_path}")
            return False

        runner = _resolve_runner(lang, step, config)
        if not runner:
            print(f"      ❌ Unsupported language: {lang}")
            return False
        if not is_executable_available(runner):
            print(f"      ❌ Runner not found or not executable: {runner}")
            return False

        raw_inputs = normalize_string_list(step.get("inputs"))
        expand_mode = step.get("expand", "batch")
        glob_results = expand_glob_inputs(project_dir, raw_inputs)
        declared_inputs = [os.path.relpath(p, project_dir) for p in flatten_glob_results(glob_results)]
        declared_outputs = normalize_string_list(step.get("outputs"))
        if not declared_outputs:
            declared_outputs = contract_paths

        if raw_inputs and not declared_inputs:
            print(f"      ❌ Glob patterns matched zero files: {raw_inputs}")
            return False

        input_abs_paths = flatten_glob_results(glob_results)

        additional_env = {}
        if declared_inputs:
            additional_env["GRAPH_HUB_INPUTS"] = os.pathsep.join(resolve_path(project_dir, p) for p in declared_inputs)

        solve_env = _load_solve_context_env()
        additional_env.update(solve_env)

        signature = {
            "script": file_signature(script_full_path, project_dir),
            "inputs": collect_signatures(project_dir, declared_inputs),
            "runner": runner,
            "lang": lang,
            "input_patterns": raw_inputs,
            "expand_mode": expand_mode,
        }
        env_overrides = step.get("_cache_env_overrides")
        if isinstance(env_overrides, dict) and env_overrides:
            signature["env_overrides"] = {key: str(env_overrides[key]) for key in sorted(env_overrides)}
        output_signatures = collect_signatures(project_dir, declared_outputs)
        cache_enabled = bool(step.get("cache", True))

        if not declared_outputs:
            stale = True
            stale_reason = "cache unavailable (no outputs declared)"
        elif not cache_enabled:
            stale = True
            stale_reason = "cache disabled by config"
        else:
            stale, stale_reason = is_step_stale(
                step_kind="analysis",
                step_key=step_key,
                signature=signature,
                output_signatures=output_signatures,
                build_state=build_state,
                config_hash=config_hash,
                force=force,
            )

        if not stale:
            print(f"   [SKIP] analysis {i}: {script} (unchanged)")
            continue

        # --- Prefetch Logic (Google Drive Force Download) ---
        ensure_local_files(input_abs_paths)
        scan_csv_export_anomalies(project_dir, declared_inputs)
        # ----------------------------------------------------
        print(f"   [RUN] analysis {i}: {script} ({stale_reason})")
        if lang == "r":
            base_cmd = _build_r_cmd(runner, script_full_path, config)
        else:
            base_cmd = [runner, script]
        cmd = _prefix_uv_if_needed(base_cmd, config)
        if not run_command(cmd, project_dir, additional_env=additional_env):
            print(f"      ❌ Step {i} failed. Stopping pipeline.")
            return False

        output_signatures = collect_signatures(project_dir, declared_outputs)
        missing_outputs = [item["path"] for item in output_signatures if not item.get("exists")]
        if declared_outputs and missing_outputs:
            print(f"      ❌ Analysis outputs not generated: {', '.join(missing_outputs)}")
            return False

        record_step_state(
            build_state=build_state,
            step_kind="analysis",
            step_key=step_key,
            signature=signature,
            outputs=output_signatures,
            config_hash=config_hash,
        )
        save_build_state(build_state_path, build_state)

    print("   ✅ Analysis step completed.")
    return True


def _run_visual_artifacts(
    project_dir,
    config,
    build_state,
    build_state_path,
    config_hash,
    *,
    section_name,
    step_kind,
    step_header,
    run_label,
    skip_label,
    item_prefix,
    default_inputs,
    force=False,
):
    print(f"\n{step_header} {config['project']['name']}")
    policy = get_language_policy(config)
    artifacts = config.get(section_name, [])

    if not artifacts:
        print(f"   (No {section_name} defined)")
        return True

    resolved_presets = resolve_presets(config)

    for i, artifact in enumerate(artifacts, 1):
        artifact_id = artifact.get("id", f"{item_prefix}{i}")
        script = artifact.get("script", "").split("::")[0]
        output = artifact.get("output", "output.pdf")
        lang = artifact.get("lang", None)
        step_key = f"{artifact_id}:{script}->{output}"

        if not lang:
            lang = "r" if script.lower().endswith(".r") else "python"

        lang = normalize_lang(lang)
        if (not policy["allow_nonstandard"]) and lang != policy["plot_lang"] and lang != "athena":
            print(f"      ❌ Policy violation: plotting language must be '{policy['plot_lang']}', got '{lang}'.")
            return False

        script_full_path = resolve_path(project_dir, script)
        try:
            script_full_path = _sanitize_script_path(script_full_path, project_dir)
        except ValueError as exc:
            print(f"      ❌ {exc} — skipping {artifact_id}")
            continue
        if not os.path.exists(script_full_path):
            print(f"      ❌ {run_label.capitalize()} script not found: {script_full_path}")
            return False

        style = resolve_step_style(artifact, config, resolved_presets)
        target_format = str(style["target_format"] or "nature").lower()
        font_scale = str(style["font_scale"] if style["font_scale"] is not None else 1.0)
        profile_name = resolve_profile_name(style["profile"])
        env_vars = {
            "THEME_FORMAT": target_format,
            "THEME_SCALE": font_scale,
            "THEME_PROFILE": profile_name,
        }
        if style.get("colormap"):
            env_vars["THEME_COLORMAP"] = style["colormap"]
        if style.get("output_format"):
            env_vars["THEME_OUTPUT_FORMAT"] = style["output_format"].strip().lower()

        solve_env = _load_solve_context_env()
        env_vars.update(solve_env)

        runner = _resolve_runner(lang, artifact, config)
        if lang != "athena":
            if not runner:
                print(f"      ❌ Unsupported language: {lang}")
                return False
            if not is_executable_available(runner):
                print(f"      ❌ Runner not found or not executable: {runner}")
                return False

        raw_inputs = normalize_string_list(artifact.get("inputs"))
        expand_mode = artifact.get("expand", "batch")
        glob_results = expand_glob_inputs(project_dir, raw_inputs if raw_inputs else list(default_inputs))
        declared_inputs = [os.path.relpath(p, project_dir) for p in flatten_glob_results(glob_results)]
        if not declared_inputs:
            declared_inputs = list(default_inputs)
        declared_outputs = [output]

        input_abs_paths = flatten_glob_results(glob_results)
        ensure_local_files(input_abs_paths)

        if declared_inputs:
            env_vars["GRAPH_HUB_INPUTS"] = os.pathsep.join(resolve_path(project_dir, p) for p in declared_inputs)

        has_glob_patterns = any(glob_module.has_magic(p) for p in raw_inputs) if raw_inputs else False

        if expand_mode == "each" and not has_glob_patterns and raw_inputs:
            print("      [WARN] expand='each' has no effect without glob patterns in inputs")

        if expand_mode == "each" and has_glob_patterns:
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
                    "expand_mode": expand_mode,
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
                    print(f"   [SKIP] {skip_label} {artifact_id} ({stem}): {expanded_output} (unchanged)")
                    continue

                print(f"   [RUN] {run_label} {artifact_id} ({stem}): {expanded_output} ({iter_stale_reason})")

                if lang == "athena":
                    from hub_core import athena_bridge

                    athena_spec = artifact.get("spec", {})
                    output_abs_path = resolve_path(project_dir, expanded_output)
                    data_context = {}
                    success = athena_bridge.render_from_athena_spec(athena_spec, output_abs_path, data_context)
                    if not success:
                        print(f"      ❌ Athena rendering failed for {artifact_id} ({stem}).")
                        return False
                else:
                    cmd = _prefix_uv_if_needed([runner, script], config)
                    try:
                        if not run_command(cmd, project_dir, additional_env=iter_env_vars):
                            print(f"      ❌ Failed to generate {artifact_id} ({stem}). Stopping pipeline.")
                            return False
                    except KeyError as e:
                        if "RESEARCH_COLOR_PALETTES" in str(e) or "Nature Journal" in str(e):
                            print("      ❌ Style Error: Invalid palette name in script. Check palettes.yaml.")
                        else:
                            print(f"      ❌ Logic Error: Missing key {e} in {run_label} script.")
                        return False
                    except Exception as e:
                        print(f"      ❌ Unexpected execution failure: {e}")
                        return False

                iter_output_path = resolve_path(project_dir, expanded_output)
                valid, verification_msg = verify_output_file(iter_output_path)
                if not valid:
                    print(f"      ❌ Output verification failed: {verification_msg}")
                    return False
                print(f"      ✅ Output verified: {verification_msg}")

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

            continue

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
            print(f"   [SKIP] {skip_label} {artifact_id}: {output} (unchanged)")
            continue

        print(f"   [RUN] {run_label} {artifact_id}: {output} ({stale_reason})")

        # ── 1. Check for Athena Engine ──────────────────────────────────────
        if lang == "athena":
            from hub_core import athena_bridge

            athena_spec = artifact.get("spec", {})
            output_abs_path = resolve_path(project_dir, output)

            data_context = _load_solve_data_context()

            success = athena_bridge.render_from_athena_spec(athena_spec, output_abs_path, data_context)
            if not success:
                print(f"      ❌ Athena rendering failed for {artifact_id}.")
                return False

        # ── 2. Standard Script Execution ────────────────────────────────────
        else:
            cmd = _prefix_uv_if_needed([runner, script], config)
            try:
                if not run_command(cmd, project_dir, additional_env=env_vars):
                    print(f"      ❌ Failed to generate {artifact_id}. Stopping pipeline.")
                    return False
            except KeyError as e:
                if "RESEARCH_COLOR_PALETTES" in str(e) or "Nature Journal" in str(e):
                    print("      ❌ Style Error: Invalid palette name in script. Check palettes.yaml.")
                else:
                    print(f"      ❌ Logic Error: Missing key {e} in {run_label} script.")
                return False
            except Exception as e:
                print(f"      ❌ Unexpected execution failure: {e}")
                return False

        output_path = resolve_path(project_dir, output)
        valid, verification_msg = verify_output_file(output_path)
        if not valid:
            print(f"      ❌ Output verification failed: {verification_msg}")
            return False
        print(f"      ✅ Output verified: {verification_msg}")

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


def run_plots(project_dir, config, build_state, build_state_path, config_hash, force=False):
    contract_paths = get_data_contract_paths(config)
    success = _run_visual_artifacts(
        project_dir,
        config,
        build_state,
        build_state_path,
        config_hash,
        section_name="figures",
        step_kind="figures",
        step_header="🎨 [Plotting Step]",
        run_label="plot",
        skip_label="plot",
        item_prefix="Fig",
        default_inputs=contract_paths,
        force=force,
    )
    if success:
        print("   ✅ Plotting step completed.")
    return success


def run_diagrams(project_dir, config, build_state, build_state_path, config_hash, force=False):
    success = _run_visual_artifacts(
        project_dir,
        config,
        build_state,
        build_state_path,
        config_hash,
        section_name="diagrams",
        step_kind="diagrams",
        step_header="🧩 [Diagram Step]",
        run_label="diagram",
        skip_label="diagram",
        item_prefix="Diagram",
        default_inputs=[],
        force=force,
    )
    if success:
        print("   ✅ Diagram step completed.")
    return success


def run_sweep(
    project_dir: str,
    config: dict,
    build_state: dict,
    build_state_path: str,
    config_hash: str,
    sweep_cfg: dict,
    step: str = "all",
    force: bool = False,
    failure_context: dict | None = None,
) -> bool:
    from .config_parser import parse_sweep_config
    from .data_contract import validate_data_contract, validate_data_contract_preflight

    parsed = parse_sweep_config(sweep_cfg)
    runs = parsed["runs"]
    output_dir_pattern = parsed["output_dir_pattern"]

    if not runs:
        print("   ⚠️  Sweep enabled but no parameter runs resolved. Check sweep.values or sweep.grid.")
        _set_failure_context(
            failure_context,
            "CONFIG",
            "Sweep enabled but no parameter runs were resolved.",
        )
        return False

    total = len(runs)
    print(f"\n🔁 [Sweep Mode] {total} run(s) scheduled")

    all_success = True
    for idx, env_overrides in enumerate(runs, 1):
        label_parts = ", ".join(f"{k}={v}" for k, v in env_overrides.items())
        print(f"\n{'─' * 60}")
        print(f"   Sweep run {idx}/{total}: {label_parts}")

        # Resolve output directory for this run
        output_dir = output_dir_pattern
        for param_name, param_value in env_overrides.items():
            output_dir = output_dir.replace(f"{{{param_name}}}", param_value)
        if "{parameter}" in output_dir or "{value}" in output_dir:
            if len(env_overrides) == 1:
                param_name, param_value = next(iter(env_overrides.items()))
                output_dir = output_dir.replace("{parameter}", param_name).replace("{value}", param_value)
            else:
                joined_names = "_".join(env_overrides.keys())
                joined_pairs = "_".join(f"{name}_{value}" for name, value in env_overrides.items())
                output_dir = output_dir.replace("{parameter}", joined_names).replace("{value}", joined_pairs)
        sweep_output_dir = os.path.join(project_dir, output_dir)
        os.makedirs(sweep_output_dir, exist_ok=True)

        # Build a patched config with figures/diagrams outputs redirected to sweep_output_dir
        import copy

        run_config = copy.deepcopy(config)
        for analysis_step in run_config.get("pipeline", {}).get("analysis", []):
            analysis_step["_cache_env_overrides"] = dict(env_overrides)
        for section in ("figures", "diagrams"):
            for artifact in run_config.get(section, []):
                orig_output = artifact.get("output", "")
                artifact["output"] = os.path.join(output_dir, os.path.basename(orig_output))

        run_success = True
        if step in ("plot", "all"):
            run_success = validate_data_contract_preflight(
                project_dir,
                run_config,
                require_existing=step == "plot",
            )
            if not run_success:
                _set_failure_context(
                    failure_context,
                    "VALIDATE",
                    f"Sweep preflight failed for run {idx}/{total} ({label_parts}).",
                )

        # Inject sweep env vars prefixed with SWEEP_
        sweep_env = {f"SWEEP_{k}": v for k, v in env_overrides.items()}
        # Also inject bare names so scripts can reference them directly
        sweep_env.update(env_overrides)

        # Temporarily patch run_command to always include sweep_env
        import hub_core.process_runner as _self

        _orig = _self.run_command

        def _sweep_run_command(cmd_list, cwd, additional_env=None):
            merged = dict(sweep_env)
            if additional_env:
                merged.update(additional_env)
            return _orig(cmd_list, cwd, additional_env=merged)

        _self.run_command = _sweep_run_command

        try:
            if run_success and step in ("analysis", "all"):
                run_success = run_analysis(
                    project_dir,
                    run_config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=force,
                )
                if not run_success:
                    _set_failure_context(
                        failure_context,
                        "EXECUTE",
                        f"Sweep analysis failed for run {idx}/{total} ({label_parts}).",
                    )
            if run_success and step in ("plot", "all"):
                run_success = validate_data_contract(project_dir, run_config)
                if not run_success:
                    _set_failure_context(
                        failure_context,
                        "VALIDATE",
                        f"Sweep data contract validation failed for run {idx}/{total} ({label_parts}).",
                    )
            if run_success and step in ("plot", "all"):
                run_success = run_plots(
                    project_dir,
                    run_config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=force,
                )
                if not run_success:
                    _set_failure_context(
                        failure_context,
                        "EXECUTE",
                        f"Sweep plotting failed for run {idx}/{total} ({label_parts}).",
                    )
            if run_success and step in ("diagrams", "all"):
                run_success = run_diagrams(
                    project_dir,
                    run_config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=force,
                )
                if not run_success:
                    _set_failure_context(
                        failure_context,
                        "EXECUTE",
                        f"Sweep diagram generation failed for run {idx}/{total} ({label_parts}).",
                    )
        finally:
            _self.run_command = _orig

        status = "✅" if run_success else "❌"
        print(f"   {status} Sweep run {idx}/{total} ({label_parts}): {'OK' if run_success else 'FAILED'}")
        print(f"      output_dir: {sweep_output_dir}")

        if not run_success:
            all_success = False

    print(f"\n{'=' * 60}")
    if all_success:
        print(f"✅ Sweep completed: {total}/{total} runs passed.")
    else:
        print("❌ Sweep finished with failures. Check output above.")
    return all_success


def run_comparison(
    project_dir: str,
    config: dict,
    build_state: dict,
    build_state_path: str,
    config_hash: str,
    comparison_cfg: dict,
    step: str = "all",
    force: bool = False,
    failure_context: dict | None = None,
) -> bool:
    from .config_parser import parse_comparison_config
    from .data_contract import validate_data_contract, validate_data_contract_preflight

    parsed = parse_comparison_config(comparison_cfg)
    conditions = parsed["conditions"]
    overlay_output = parsed["overlay_output"]

    if not conditions:
        print("   ⚠️  Comparison enabled but no conditions defined. Check comparison.conditions.")
        _set_failure_context(
            failure_context,
            "CONFIG",
            "Comparison enabled but no conditions were resolved.",
        )
        return False

    total = len(conditions)
    print(f"\n🔀 [Comparison Mode] {total} condition(s) scheduled")
    if overlay_output:
        print(f"   overlay_output: {overlay_output}")

    all_success = True
    for idx, cond in enumerate(conditions, 1):
        label = cond["label"]
        env_overrides = cond["env"]
        data_override = cond.get("data_override")

        print(f"\n{'─' * 60}")
        print(f"   Condition {idx}/{total}: {label}")

        import copy

        run_config = copy.deepcopy(config)

        # Redirect outputs to a per-condition subdirectory so runs don't overwrite each other
        safe_label = label.replace(" ", "_").replace("/", "_").replace("%", "pct")
        condition_output_dir = os.path.join("results", "figures", f"comparison_{safe_label}")
        abs_condition_dir = os.path.join(project_dir, condition_output_dir)
        os.makedirs(abs_condition_dir, exist_ok=True)

        for section in ("figures", "diagrams"):
            for artifact in run_config.get(section, []):
                orig_output = artifact.get("output", "")
                artifact["output"] = os.path.join(condition_output_dir, os.path.basename(orig_output))

        # Apply data_override: redirect pipeline analysis inputs if specified
        if data_override:
            for analysis_step in run_config.get("pipeline", {}).get("analysis", []):
                analysis_step["inputs"] = [data_override]

        run_success = True
        if step in ("plot", "all"):
            run_success = validate_data_contract_preflight(
                project_dir,
                run_config,
                require_existing=step == "plot",
            )
            if not run_success:
                _set_failure_context(
                    failure_context,
                    "VALIDATE",
                    f"Comparison preflight failed for condition {idx}/{total} ({label}).",
                )

        # Inject env vars — COMPARISON_ prefixed + bare names, plus the condition label
        cond_env = {f"COMPARISON_{k}": v for k, v in env_overrides.items()}
        cond_env.update(env_overrides)
        cond_env["COMPARISON_LABEL"] = label

        import hub_core.process_runner as _self

        _orig = _self.run_command

        def _comparison_run_command(cmd_list, cwd, additional_env=None, _env=cond_env):
            merged = dict(_env)
            if additional_env:
                merged.update(additional_env)
            return _orig(cmd_list, cwd, additional_env=merged)

        _self.run_command = _comparison_run_command

        try:
            if run_success and step in ("analysis", "all"):
                run_success = run_analysis(
                    project_dir,
                    run_config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=force,
                )
                if not run_success:
                    _set_failure_context(
                        failure_context,
                        "EXECUTE",
                        f"Comparison analysis failed for condition {idx}/{total} ({label}).",
                    )
            if run_success and step in ("plot", "all"):
                run_success = validate_data_contract(project_dir, run_config)
                if not run_success:
                    _set_failure_context(
                        failure_context,
                        "VALIDATE",
                        f"Comparison data contract validation failed for condition {idx}/{total} ({label}).",
                    )
            if run_success and step in ("plot", "all"):
                run_success = run_plots(
                    project_dir,
                    run_config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=force,
                )
                if not run_success:
                    _set_failure_context(
                        failure_context,
                        "EXECUTE",
                        f"Comparison plotting failed for condition {idx}/{total} ({label}).",
                    )
            if run_success and step in ("diagrams", "all"):
                run_success = run_diagrams(
                    project_dir,
                    run_config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=force,
                )
                if not run_success:
                    _set_failure_context(
                        failure_context,
                        "EXECUTE",
                        f"Comparison diagram generation failed for condition {idx}/{total} ({label}).",
                    )
        finally:
            _self.run_command = _orig

        status = "✅" if run_success else "❌"
        print(f"   {status} Condition {idx}/{total} ({label}): {'OK' if run_success else 'FAILED'}")
        print(f"      output_dir: {abs_condition_dir}")

        if not run_success:
            all_success = False

    print(f"\n{'=' * 60}")
    if all_success:
        print(f"✅ Comparison completed: {total}/{total} conditions passed.")
        if overlay_output:
            print(f"   overlay_output target: {os.path.join(project_dir, overlay_output)}")
            print("   (overlay assembly is delegated to the project's plot script via COMPARISON_LABEL env vars)")
    else:
        print("❌ Comparison finished with failures. Check output above.")


def run_assemblies(project_dir: str, config: dict, force: bool = False) -> bool:
    assemblies = config.get("assemblies", {})
    if not assemblies:
        return True

    print(f"\n   [Assembly Step] {config['project']['name']}")

    from plotting.figure_assembler import assemble_figure

    all_success = True
    for fig_id, fig_cfg in assemblies.items():
        print(f"   [RUN] assembling {fig_id}...")
        try:
            out_path = assemble_figure(fig_id, fig_cfg, project_dir)
            rel_path = os.path.relpath(out_path, project_dir)
            print(f"      -> {rel_path}")
        except Exception as exc:
            print(f"      FAIL {fig_id}: {exc}")
            all_success = False

    return all_success
    return all_success
