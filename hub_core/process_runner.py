import glob as glob_module
import logging
import os
import subprocess

from .adapters import select_adapters
from .cache_manager import (
    collect_signatures,
    file_signature,
    is_step_stale,
    record_step_state,
    save_build_state,
)
from .config_parser import get_language_policy, normalize_lang, resolve_presets, resolve_step_style
from .data_contract import get_data_contract_paths
from .domain_analysis import DomainAnalysisError, run_domain_helper
from .execution_security import (
    DEFAULT_EXECUTION_TIMEOUT_SECONDS,
    ExecutionSecurityError,
    execution_timeout_seconds,
    resolve_contained_project_path,
)
from .external_raw import ExternalRawError
from .external_raw_execution import external_raw_signatures
from .logging import get_logger
from .process_runner_commands import build_r_cmd as _build_r_cmd
from .process_runner_commands import fallback_sanitize_path as _fallback_sanitize_path
from .process_runner_commands import join_config_path as _join_config_path
from .process_runner_commands import prefix_uv_if_needed as _prefix_uv_if_needed
from .process_runner_commands import resolve_runner as _resolve_runner
from .process_runner_commands import sanitize_script_path as _sanitize_script_path
from .process_runner_inputs import contained_input_groups as _contained_input_groups
from .process_runner_inputs import partition_input_declarations as _partition_input_declarations
from .process_runner_inputs import (  # noqa: F401 - compatibility alias
    prefetch_and_revalidate_inputs as _prefetch_and_revalidate_inputs,
)
from .process_runner_inputs import project_relative_inputs as _project_relative_inputs
from .process_runner_inputs import resolve_execution_inputs as _resolve_execution_inputs
from .process_runner_runtime import run_command_env_overlay as _run_command_env_overlay
from .process_runner_runtime import run_command_runtime as _run_command_runtime
from .process_runner_variants import VariantDependencies
from .process_runner_variants import run_comparison as _run_comparison_variant
from .process_runner_variants import run_sweep as _run_sweep_variant
from .process_runner_visual_batch import run_visual_artifact_batch as _run_visual_artifact_batch
from .process_runner_visual_expansion import run_expanded_visual_artifacts as _run_expanded_visual_artifacts
from .process_supervisor import supervise_process
from .project_paths import (
    ProjectPathError,
    resolve_project_input,
    resolve_project_output,
)
from .runtime_boundary import RuntimeBoundaryError
from .utils import (
    flatten_glob_results,
    is_executable_available,
    normalize_string_list,
    scan_csv_export_anomalies,
    verify_output_file,
)
from .uv_runtime import build_uv_environment, ensure_uv_runtime_dirs

logger = get_logger(__name__)

__all__ = [
    "_build_r_cmd",
    "_fallback_sanitize_path",
    "_join_config_path",
    "_prefix_uv_if_needed",
    "_resolve_runner",
    "_sanitize_script_path",
    "run_analysis",
    "run_assemblies",
    "run_command",
    "run_comparison",
    "run_diagrams",
    "run_plots",
    "run_sweep",
]


def _log(message: str = "") -> None:
    if "❌" in message or "FAIL" in message:
        level = logging.ERROR
    elif "⚠️" in message or "[WARN]" in message:
        level = logging.WARNING
    else:
        level = logging.INFO
    logger.log(level, message)


try:
    from themes.style_profiles import resolve_profile_name
except Exception:

    def resolve_profile_name(profile_name=None):
        if profile_name is None:
            return "baseline"
        key = str(profile_name).strip().lower()
        return key if key else "baseline"


def _set_failure_context(failure_context: dict | None, stage: str, message: str) -> None:
    if not isinstance(failure_context, dict):
        return
    failure_context.setdefault("stage", stage)
    failure_context.setdefault("message", message)


def _resolve_prefetcher(config: dict, prefetcher=None):
    return prefetcher if prefetcher is not None else select_adapters(config).prefetcher


def _resolve_athena(config: dict, athena=None):
    return athena if athena is not None else select_adapters(config).athena


def _resolve_output_path(project_dir, declaration):
    return str(resolve_project_output(project_dir, declaration, purpose="declared execution output"))


def _variant_dependencies() -> VariantDependencies:
    """Bind variant orchestration to this module's compatibility surface."""

    from .config_parser import parse_comparison_config, parse_sweep_config
    from .data_contract import validate_data_contract, validate_data_contract_preflight

    return VariantDependencies(
        log=_log,
        set_failure_context=_set_failure_context,
        parse_sweep_config=parse_sweep_config,
        parse_comparison_config=parse_comparison_config,
        validate_data_contract=validate_data_contract,
        validate_data_contract_preflight=validate_data_contract_preflight,
        resolve_contained_project_path=resolve_contained_project_path,
        execution_security_error=ExecutionSecurityError,
        join_config_path=_join_config_path,
        env_overlay=_run_command_env_overlay,
        run_analysis=run_analysis,
        run_plots=run_plots,
        run_diagrams=run_diagrams,
    )


def run_command(cmd_list, cwd, additional_env=None, *, timeout_seconds=DEFAULT_EXECUTION_TIMEOUT_SECONDS):
    return _run_command_runtime(
        cmd_list,
        cwd,
        additional_env,
        timeout_seconds,
        log=_log,
        popen_factory=subprocess.Popen,
        build_uv_environment=build_uv_environment,
        ensure_uv_runtime_dirs=ensure_uv_runtime_dirs,
        supervise_process=supervise_process,
    )


def run_analysis(
    project_dir,
    config,
    build_state,
    build_state_path,
    config_hash,
    force=False,
    prefetcher=None,
    athena=None,
    external_raw_allowed_roots=None,
):
    _log(f"\n🚀 [Analysis Step] {config['project']['name']}")
    prefetcher = _resolve_prefetcher(config, prefetcher)
    athena = _resolve_athena(config, athena)
    policy = get_language_policy(config)
    timeout_seconds = execution_timeout_seconds(config)
    pipeline = config.get("pipeline", {})
    steps = pipeline.get("analysis", [])
    contract_paths = get_data_contract_paths(config)

    if not steps:
        _log("   (No analysis steps defined)")
        return True

    for i, step in enumerate(steps, 1):
        domain_helper = step.get("domain_helper")
        if domain_helper:
            step_key = f"{i}:domain_helper:{domain_helper}"
            raw_inputs = normalize_string_list(step.get("inputs"))
            expand_mode = step.get("expand", "batch")
            try:
                project_input_patterns, external_input_declarations = _partition_input_declarations(raw_inputs)
                glob_results = _contained_input_groups(project_dir, project_input_patterns)
                declared_inputs = _project_relative_inputs(project_dir, flatten_glob_results(glob_results))
                external_input_signature = external_raw_signatures(config, external_input_declarations)
            except (ExternalRawError, FileNotFoundError, ProjectPathError, ValueError) as exc:
                _log(f"      ❌ {exc}")
                return False
            declared_outputs = normalize_string_list(step.get("outputs"))
            try:
                for output in declared_outputs:
                    resolve_project_output(project_dir, output, purpose=f"pipeline.analysis[{i}].outputs")
            except (FileNotFoundError, ProjectPathError) as exc:
                _log(f"      ❌ {exc}")
                return False

            if project_input_patterns and not declared_inputs:
                _log(f"      ❌ Glob patterns matched zero files: {raw_inputs}")
                return False

            signature = {
                "domain_helper": domain_helper,
                "inputs": collect_signatures(project_dir, declared_inputs),
                "external_inputs": external_input_signature,
                "input_patterns": raw_inputs,
                "outputs": declared_outputs,
                "params": step.get("params", {}) or {},
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
                _log(f"   [SKIP] analysis {i}: {domain_helper} (unchanged)")
                continue

            try:
                input_abs_paths = _resolve_execution_inputs(
                    project_dir,
                    config,
                    declared_inputs,
                    external_input_declarations,
                    prefetcher,
                    external_raw_allowed_roots,
                )
            except (ExternalRawError, FileNotFoundError, ProjectPathError, RuntimeBoundaryError) as exc:
                _log(f"      ❌ {exc}")
                return False
            scan_csv_export_anomalies(project_dir, declared_inputs)
            _log(f"   [RUN] analysis {i}: {domain_helper} ({stale_reason})")
            try:
                run_domain_helper(
                    str(domain_helper),
                    input_paths=input_abs_paths,
                    output_paths=[_resolve_output_path(project_dir, p) for p in declared_outputs],
                    params=step.get("params", {}) or {},
                )
            except DomainAnalysisError as exc:
                _log(f"      ❌ Domain helper failed: {exc}")
                return False

            output_signatures = collect_signatures(project_dir, declared_outputs)
            missing_outputs = [item["path"] for item in output_signatures if not item.get("exists")]
            if declared_outputs and missing_outputs:
                _log(f"      ❌ Analysis outputs not generated: {', '.join(missing_outputs)}")
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
            continue

        script = step["script"]
        lang = normalize_lang(step.get("lang", "R")) or "r"
        step_key = f"{i}:{script}"

        if (not policy["allow_nonstandard"]) and lang != policy["analysis_lang"]:
            _log(f"      ❌ Policy violation: analysis language must be '{policy['analysis_lang']}', got '{lang}'.")
            return False

        try:
            script_full_path = str(
                resolve_project_input(
                    project_dir,
                    script,
                    purpose=f"pipeline.analysis[{i}].script",
                )
            )
        except (FileNotFoundError, ProjectPathError) as exc:
            _log(f"      ❌ {exc}")
            return False

        runner = _resolve_runner(lang, step, config)
        if not runner:
            _log(f"      ❌ Unsupported language: {lang}")
            return False
        if not is_executable_available(runner):
            _log(f"      ❌ Runner not found or not executable: {runner}")
            return False

        raw_inputs = normalize_string_list(step.get("inputs"))
        expand_mode = step.get("expand", "batch")
        try:
            project_input_patterns, external_input_declarations = _partition_input_declarations(raw_inputs)
            glob_results = _contained_input_groups(project_dir, project_input_patterns)
            declared_inputs = _project_relative_inputs(project_dir, flatten_glob_results(glob_results))
            external_input_signature = external_raw_signatures(config, external_input_declarations)
        except (ExternalRawError, FileNotFoundError, ProjectPathError, ValueError) as exc:
            _log(f"      ❌ {exc}")
            return False
        declared_outputs = normalize_string_list(step.get("outputs"))
        if not declared_outputs:
            declared_outputs = contract_paths
        try:
            for output in declared_outputs:
                resolve_project_output(project_dir, output, purpose=f"pipeline.analysis[{i}].outputs")
        except (FileNotFoundError, ProjectPathError) as exc:
            _log(f"      ❌ {exc}")
            return False

        if project_input_patterns and not declared_inputs:
            _log(f"      ❌ Glob patterns matched zero files: {raw_inputs}")
            return False

        additional_env = {}

        solve_env = athena.load_solve_context_env()
        additional_env.update(solve_env)

        signature = {
            "script": file_signature(script_full_path, project_dir),
            "inputs": collect_signatures(project_dir, declared_inputs),
            "external_inputs": external_input_signature,
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
            _log(f"   [SKIP] analysis {i}: {script} (unchanged)")
            continue

        try:
            input_abs_paths = _resolve_execution_inputs(
                project_dir,
                config,
                declared_inputs,
                external_input_declarations,
                prefetcher,
                external_raw_allowed_roots,
            )
            script_full_path = str(
                resolve_project_input(
                    project_dir,
                    script,
                    purpose=f"pipeline.analysis[{i}].script",
                )
            )
        except (ExternalRawError, FileNotFoundError, ProjectPathError, RuntimeBoundaryError) as exc:
            _log(f"      ❌ {exc}")
            return False
        if input_abs_paths:
            additional_env["GRAPH_HUB_INPUTS"] = os.pathsep.join(str(path) for path in input_abs_paths)
        scan_csv_export_anomalies(project_dir, declared_inputs)
        _log(f"   [RUN] analysis {i}: {script} ({stale_reason})")
        if lang == "r":
            base_cmd = _build_r_cmd(runner, script_full_path, config)
        else:
            base_cmd = [runner, script]
        cmd = _prefix_uv_if_needed(base_cmd, config)
        if not run_command(cmd, project_dir, additional_env=additional_env, timeout_seconds=timeout_seconds):
            _log(f"      ❌ Step {i} failed. Stopping pipeline.")
            return False

        output_signatures = collect_signatures(project_dir, declared_outputs)
        missing_outputs = [item["path"] for item in output_signatures if not item.get("exists")]
        if declared_outputs and missing_outputs:
            _log(f"      ❌ Analysis outputs not generated: {', '.join(missing_outputs)}")
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

    _log("   ✅ Analysis step completed.")
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
    prefetcher=None,
    athena=None,
    external_raw_allowed_roots=None,
):
    _log(f"\n{step_header} {config['project']['name']}")
    prefetcher = _resolve_prefetcher(config, prefetcher)
    athena = _resolve_athena(config, athena)
    policy = get_language_policy(config)
    timeout_seconds = execution_timeout_seconds(config)
    artifacts = config.get(section_name, [])

    if not artifacts:
        _log(f"   (No {section_name} defined)")
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
            _log(f"      ❌ Policy violation: plotting language must be '{policy['plot_lang']}', got '{lang}'.")
            return False

        try:
            script_full_path = str(
                resolve_project_input(
                    project_dir,
                    script,
                    purpose=f"{section_name}[{i}].script",
                )
            )
            resolve_project_output(project_dir, output, purpose=f"{section_name}[{i}].output")
        except (FileNotFoundError, ProjectPathError) as exc:
            _log(f"      ❌ {exc}")
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

        solve_env = athena.load_solve_context_env()
        env_vars.update(solve_env)

        runner = _resolve_runner(lang, artifact, config)
        if lang != "athena":
            if not runner:
                _log(f"      ❌ Unsupported language: {lang}")
                return False
            if not is_executable_available(runner):
                _log(f"      ❌ Runner not found or not executable: {runner}")
                return False

        raw_inputs = normalize_string_list(artifact.get("inputs"))
        expand_mode = artifact.get("expand", "batch")
        try:
            effective_inputs = raw_inputs if raw_inputs else list(default_inputs)
            project_input_patterns, external_input_declarations = _partition_input_declarations(effective_inputs)
            if external_input_declarations and expand_mode == "each":
                raise ExternalRawError("external raw inputs do not support expand='each'")
            glob_results = _contained_input_groups(project_dir, project_input_patterns)
            declared_inputs = _project_relative_inputs(project_dir, flatten_glob_results(glob_results))
            external_input_signature = external_raw_signatures(config, external_input_declarations)
        except (ExternalRawError, FileNotFoundError, ProjectPathError, ValueError) as exc:
            _log(f"      ❌ {exc}")
            return False
        if not declared_inputs and not external_input_declarations:
            declared_inputs = list(default_inputs)
        declared_outputs = [output]

        try:
            input_abs_paths = _resolve_execution_inputs(
                project_dir,
                config,
                declared_inputs,
                external_input_declarations,
                prefetcher,
                external_raw_allowed_roots,
            )
            script_full_path = str(
                resolve_project_input(
                    project_dir,
                    script,
                    purpose=f"{section_name}[{i}].script",
                )
            )
        except (ExternalRawError, FileNotFoundError, ProjectPathError, RuntimeBoundaryError) as exc:
            _log(f"      ❌ {exc}")
            return False

        if input_abs_paths:
            env_vars["GRAPH_HUB_INPUTS"] = os.pathsep.join(str(path) for path in input_abs_paths)

        has_glob_patterns = any(glob_module.has_magic(p) for p in raw_inputs) if raw_inputs else False

        if expand_mode == "each" and not has_glob_patterns and raw_inputs:
            _log("      [WARN] expand='each' has no effect without glob patterns in inputs")

        if expand_mode == "each" and has_glob_patterns:
            if not _run_expanded_visual_artifacts(
                project_dir,
                config,
                build_state,
                build_state_path,
                config_hash,
                artifact=artifact,
                artifact_id=artifact_id,
                script=script,
                script_full_path=script_full_path,
                output=output,
                lang=lang,
                runner=runner,
                raw_inputs=raw_inputs,
                glob_results=glob_results,
                env_vars=env_vars,
                timeout_seconds=timeout_seconds,
                step_kind=step_kind,
                run_label=run_label,
                skip_label=skip_label,
                force=force,
                target_format=target_format,
                font_scale=font_scale,
                profile_name=profile_name,
                log=_log,
                flatten_glob_results=flatten_glob_results,
                file_signature=file_signature,
                collect_signatures=collect_signatures,
                is_step_stale=is_step_stale,
                resolve_path=_resolve_output_path,
                prefix_uv_if_needed=_prefix_uv_if_needed,
                run_command=run_command,
                verify_output_file=verify_output_file,
                record_step_state=record_step_state,
                save_build_state=save_build_state,
                athena=athena,
            ):
                return False

            continue

        if not _run_visual_artifact_batch(
            project_dir,
            config,
            build_state,
            build_state_path,
            config_hash,
            artifact=artifact,
            artifact_id=artifact_id,
            script=script,
            script_full_path=script_full_path,
            output=output,
            lang=lang,
            runner=runner,
            raw_inputs=raw_inputs,
            expand_mode=expand_mode,
            declared_inputs=declared_inputs,
            external_input_signatures=external_input_signature,
            declared_outputs=declared_outputs,
            env_vars=env_vars,
            timeout_seconds=timeout_seconds,
            step_kind=step_kind,
            step_key=step_key,
            run_label=run_label,
            skip_label=skip_label,
            force=force,
            target_format=target_format,
            font_scale=font_scale,
            profile_name=profile_name,
            log=_log,
            file_signature=file_signature,
            collect_signatures=collect_signatures,
            is_step_stale=is_step_stale,
            resolve_path=_resolve_output_path,
            prefix_uv_if_needed=_prefix_uv_if_needed,
            run_command=run_command,
            verify_output_file=verify_output_file,
            record_step_state=record_step_state,
            save_build_state=save_build_state,
            athena=athena,
        ):
            return False

    return True


def run_plots(
    project_dir,
    config,
    build_state,
    build_state_path,
    config_hash,
    force=False,
    prefetcher=None,
    athena=None,
    external_raw_allowed_roots=None,
):
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
        prefetcher=prefetcher,
        athena=athena,
        external_raw_allowed_roots=external_raw_allowed_roots,
    )
    if success:
        _log("   ✅ Plotting step completed.")
    return success


def run_diagrams(
    project_dir,
    config,
    build_state,
    build_state_path,
    config_hash,
    force=False,
    prefetcher=None,
    athena=None,
    external_raw_allowed_roots=None,
):
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
        prefetcher=prefetcher,
        athena=athena,
        external_raw_allowed_roots=external_raw_allowed_roots,
    )
    if success:
        _log("   ✅ Diagram step completed.")
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
    prefetcher=None,
    athena=None,
) -> bool:
    return _run_sweep_variant(
        project_dir,
        config,
        build_state,
        build_state_path,
        config_hash,
        sweep_cfg,
        dependencies=_variant_dependencies(),
        step=step,
        force=force,
        failure_context=failure_context,
        prefetcher=prefetcher,
        athena=athena,
    )


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
    prefetcher=None,
    athena=None,
) -> bool:
    return _run_comparison_variant(
        project_dir,
        config,
        build_state,
        build_state_path,
        config_hash,
        comparison_cfg,
        dependencies=_variant_dependencies(),
        step=step,
        force=force,
        failure_context=failure_context,
        prefetcher=prefetcher,
        athena=athena,
    )


def run_assemblies(project_dir: str, config: dict, force: bool = False) -> bool:
    assemblies = config.get("assemblies", {})
    if not assemblies:
        return True

    _log(f"\n   [Assembly Step] {config['project']['name']}")

    from plotting.figure_assembler import assemble_figure

    all_success = True
    for fig_id, fig_cfg in assemblies.items():
        _log(f"   [RUN] assembling {fig_id}...")
        try:
            out_path = assemble_figure(fig_id, fig_cfg, project_dir)
            rel_path = os.path.relpath(out_path, project_dir)
            _log(f"      -> {rel_path}")
        except Exception as exc:
            _log(f"      FAIL {fig_id}: {exc}")
            all_success = False

    return all_success
    return all_success
