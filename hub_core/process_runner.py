import os
import subprocess
import sys
import tempfile

from .cache_manager import (
    collect_signatures,
    file_signature,
    is_step_stale,
    record_step_state,
    save_build_state,
)
from .config_parser import get_language_policy, normalize_lang
from .data_contract import get_data_contract_paths
from .utils import (
    ensure_local_files,
    is_executable_available,
    normalize_string_list,
    resolve_path,
    verify_output_file,
)

try:
    from themes.style_profiles import resolve_profile_name
except Exception:
    def resolve_profile_name(profile_name=None):
        if profile_name is None:
            return "baseline"
        key = str(profile_name).strip().lower()
        return key if key else "baseline"

def _resolve_runner(lang, step_cfg, config):
    execution = config.get('execution', {}) if isinstance(config.get('execution', {}), dict) else {}
    if lang == 'r':
        return step_cfg.get('r_exec') or execution.get('rscript') or 'Rscript'
    if lang in {'python', 'py'}:
        return step_cfg.get('python_exec') or execution.get('python') or sys.executable
    return None

def _prefix_uv_if_needed(cmd, config):
    environment = config.get('environment', {})
    if environment.get('uv_run') is True:
        return ['uv', 'run'] + cmd
    return cmd

def run_command(cmd_list, cwd, additional_env=None):
    # This assumes orchestrator.py is one level up from hub_core
    hub_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    env = os.environ.copy()
    env['RESEARCH_HUB_PATH'] = hub_path
    env['PROJECT_ROOT'] = os.path.abspath(cwd)
    if "MPLCONFIGDIR" not in env:
        mpl_cache = os.path.join(tempfile.gettempdir(), "graph_hub_mplcache")
        os.makedirs(mpl_cache, exist_ok=True)
        env["MPLCONFIGDIR"] = mpl_cache
    if "MPLBACKEND" not in env and not env.get("DISPLAY"):
        env["MPLBACKEND"] = "Agg"
    if additional_env:
        env.update(additional_env)

    try:
        process = subprocess.Popen(
            cmd_list, cwd=os.path.abspath(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env
        )
        for line in process.stdout:
            print(f"      {line.strip()}")
        process.wait(timeout=600)  # 10분 타임아웃
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
    pipeline = config.get('pipeline', {})
    steps = pipeline.get('analysis', [])
    contract_paths = get_data_contract_paths(config)

    if not steps:
        print("   (No analysis steps defined)")
        return True

    for i, step in enumerate(steps, 1):
        script = step['script']
        lang = normalize_lang(step.get('lang', 'R')) or "r"
        step_key = f"{i}:{script}"

        if (not policy['allow_nonstandard']) and lang != policy['analysis_lang']:
            print(f"      ❌ Policy violation: analysis language must be '{policy['analysis_lang']}', got '{lang}'.")
            return False

        script_full_path = resolve_path(project_dir, script)
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

        declared_inputs = normalize_string_list(step.get("inputs"))
        declared_outputs = normalize_string_list(step.get("outputs"))
        if not declared_outputs:
            declared_outputs = contract_paths

        # --- Prefetch Logic (Google Drive Force Download) ---
        input_abs_paths = [resolve_path(project_dir, p) for p in declared_inputs]
        ensure_local_files(input_abs_paths)
        # ----------------------------------------------------

        signature = {
            "script": file_signature(script_full_path, project_dir),
            "inputs": collect_signatures(project_dir, declared_inputs),
            "runner": runner,
            "lang": lang,
        }
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

        print(f"   [RUN] analysis {i}: {script} ({stale_reason})")
        cmd = _prefix_uv_if_needed([runner, script], config)
        if not run_command(cmd, project_dir):
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

    for i, artifact in enumerate(artifacts, 1):
        artifact_id = artifact.get('id', f'{item_prefix}{i}')
        script = artifact.get('script', '').split("::")[0]
        output = artifact.get('output', 'output.pdf')
        lang = artifact.get('lang', None)
        step_key = f"{artifact_id}:{script}->{output}"

        if not lang:
            lang = 'r' if script.lower().endswith('.r') else 'python'

        lang = normalize_lang(lang)
        if (not policy['allow_nonstandard']) and lang != policy['plot_lang'] and lang != "athena":
            print(f"      ❌ Policy violation: plotting language must be '{policy['plot_lang']}', got '{lang}'.")
            return False

        script_full_path = resolve_path(project_dir, script)
        if not os.path.exists(script_full_path):
            print(f"      ❌ {run_label.capitalize()} script not found: {script_full_path}")
            return False

        visual_style = config.get('visual_style', {})
        target_format = str(artifact.get('theme') or visual_style.get('target_format', 'nature')).lower()
        font_scale = str(visual_style.get('font_scale', 1.0))
        profile_name = resolve_profile_name(visual_style.get('profile', 'baseline'))
        env_vars = {
            'THEME_FORMAT': target_format,
            'THEME_SCALE': font_scale,
            'THEME_PROFILE': profile_name,
        }

        runner = _resolve_runner(lang, artifact, config)
        if lang != "athena":
            if not runner:
                print(f"      ❌ Unsupported language: {lang}")
                return False
            if not is_executable_available(runner):
                print(f"      ❌ Runner not found or not executable: {runner}")
                return False

        declared_inputs = normalize_string_list(artifact.get("inputs"))
        if not declared_inputs:
            declared_inputs = list(default_inputs)
        declared_outputs = [output]

        input_abs_paths = [resolve_path(project_dir, p) for p in declared_inputs]
        ensure_local_files(input_abs_paths)

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

            # TODO: Load data_context from CSV inputs if needed
            data_context = {}

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
                if 'RESEARCH_COLOR_PALETTES' in str(e) or 'Nature Journal' in str(e):
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
