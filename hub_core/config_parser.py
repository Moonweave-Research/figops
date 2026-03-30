import hashlib
import os
import unicodedata

import yaml

ALLOWED_TARGET_FORMATS = {"nature", "science", "ppt", "default"}
CURRENT_CONFIG_SCHEMA_VERSION = "1.0"
ALLOWED_PRESET_KEYS = {
    "target_format", "font_scale", "profile", "output_format", "colormap",
}
ALLOWED_ANALYSIS_POLICY_LANGS = {"r"}
ALLOWED_PLOT_POLICY_LANGS = {"python"}
ALLOWED_OUTPUT_FORMATS = {"png", "pdf", "svg"}
CONFIG_FILE_CANDIDATES = (
    "project_config.yaml",
    os.path.join("scripts", "project_config.yaml"),
)

try:
    from themes.style_profiles import PROFILE_ALIASES, list_profiles, resolve_profile_name
    _KNOWN_STYLE_PROFILES = set(list_profiles())
    _KNOWN_STYLE_PROFILE_KEYS = set(list_profiles()) | set(PROFILE_ALIASES.keys())
except Exception:
    def resolve_profile_name(profile_name=None):
        if profile_name is None:
            return "baseline"
        key = str(profile_name).strip().lower()
        return key if key else "baseline"

    def list_profiles():
        return ["baseline"]

    PROFILE_ALIASES = {"default": "baseline", "base": "baseline"}
    _KNOWN_STYLE_PROFILES = {"baseline"}
    _KNOWN_STYLE_PROFILE_KEYS = {"baseline", "default", "base"}

def normalize_lang(lang):
    if lang is None:
        return ""
    key = str(lang).strip().lower()
    if key == "py":
        return "python"
    return key

def get_language_policy(config):
    raw = config.get("language_policy", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}

    analysis_lang = normalize_lang(raw.get("analysis_lang", "r")) or "r"
    plot_lang = normalize_lang(raw.get("plot_lang", "python")) or "python"
    allow_nonstandard = bool(raw.get("allow_nonstandard", False))
    return {
        "analysis_lang": analysis_lang,
        "plot_lang": plot_lang,
        "allow_nonstandard": allow_nonstandard,
    }

def resolve_presets(config: dict) -> dict:
    raw = config.get("presets", {})
    if raw is None:
        raw = {}

    default_name: str | None = raw.get("_default", None)

    visual_style = config.get("visual_style", {}) or {}
    base = {
        "target_format": visual_style.get("target_format"),
        "font_scale": visual_style.get("font_scale"),
        "profile": visual_style.get("profile"),
    }

    result: dict = {"__default_name__": default_name}
    for preset_name, preset_vals in raw.items():
        if preset_name == "_default":
            continue
        merged = {k: v for k, v in base.items() if v is not None}
        if isinstance(preset_vals, dict):
            merged.update(preset_vals)
        result[preset_name] = merged

    return result

def resolve_step_style(
    step_cfg: dict,
    config: dict,
    resolved_presets: dict | None = None,
) -> dict:
    visual_style = config.get("visual_style", {}) or {}
    result = {
        "target_format": visual_style.get("target_format"),
        "font_scale": visual_style.get("font_scale"),
        "profile": visual_style.get("profile"),
        "output_format": None,
        "colormap": None,
    }

    if resolved_presets is not None:
        preset_key = step_cfg.get("preset")
        if preset_key is not None:
            preset_vals = resolved_presets.get(preset_key, {})
            result.update({k: v for k, v in preset_vals.items() if not k.startswith("__")})
        elif resolved_presets.get("__default_name__"):
            default_key = resolved_presets["__default_name__"]
            preset_vals = resolved_presets.get(default_key, {})
            result.update({k: v for k, v in preset_vals.items() if not k.startswith("__")})

    if "theme" in step_cfg:
        result["target_format"] = step_cfg["theme"]
    if "target_format" in step_cfg:
        result["target_format"] = step_cfg["target_format"]
    if "font_scale" in step_cfg:
        result["font_scale"] = step_cfg["font_scale"]
    if "profile" in step_cfg:
        result["profile"] = step_cfg["profile"]
    if "format" in step_cfg:
        result["output_format"] = step_cfg["format"]
    if "output_format" in step_cfg:
        result["output_format"] = step_cfg["output_format"]
    if "colormap" in step_cfg:
        result["colormap"] = step_cfg["colormap"]

    return result

def find_config_path(project_dir):
    for rel_path in CONFIG_FILE_CANDIDATES:
        candidate = os.path.join(project_dir, rel_path)
        if os.path.exists(candidate):
            return candidate
    return None

def _load_project_metadata(config_path, fallback_name):
    metadata = {
        "name": fallback_name,
        "valid": False,
        "errors": [],
    }

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            conf_data = yaml.safe_load(f)
    except Exception as exc:
        metadata["errors"] = [f"Failed to read config: {exc}"]
        return metadata

    if not isinstance(conf_data, dict):
        metadata["errors"] = validate_config(conf_data)
        return metadata

    metadata["name"] = conf_data.get('project', {}).get('name', fallback_name)
    metadata["errors"] = validate_config(conf_data)
    metadata["valid"] = len(metadata["errors"]) == 0
    return metadata

def _read_project_metadata(config_path, fallback_name):
    metadata = _load_project_metadata(config_path, fallback_name)
    return metadata["name"], metadata["valid"], list(metadata["errors"])

def validate_config(config):
    errors = []

    if not isinstance(config, dict):
        return ["Config root must be a YAML mapping/object."]

    schema_version = config.get("schema_version")
    if schema_version is not None:
        if str(schema_version) != CURRENT_CONFIG_SCHEMA_VERSION:
            errors.append(
                f"schema_version '{schema_version}' does not match expected "
                f"'{CURRENT_CONFIG_SCHEMA_VERSION}'. Update project_config.yaml or "
                f"remove schema_version to suppress this check."
            )

    project = config.get('project')
    if not isinstance(project, dict):
        errors.append("Missing or invalid 'project' section (must be a mapping).")
    else:
        name = project.get('name')
        if not isinstance(name, str) or not name.strip():
            errors.append("Missing required field: project.name (non-empty string).")

    visual_style = config.get('visual_style', {})
    if visual_style is None:
        visual_style = {}
    if not isinstance(visual_style, dict):
        errors.append("Invalid 'visual_style' section (must be a mapping).")
    else:
        target_format = visual_style.get('target_format', 'nature')
        if not isinstance(target_format, str) or target_format.lower() not in ALLOWED_TARGET_FORMATS:
            allowed = ", ".join(sorted(ALLOWED_TARGET_FORMATS))
            errors.append(
                f"Invalid visual_style.target_format: '{target_format}'. "
                f"Allowed values: {allowed}."
            )

        font_scale = visual_style.get('font_scale', 1.0)
        if isinstance(font_scale, bool) or not isinstance(font_scale, (int, float)) or font_scale <= 0:
            errors.append("visual_style.font_scale must be a positive number.")

        profile_name = visual_style.get('profile', 'baseline')
        if not isinstance(profile_name, str) or not profile_name.strip():
            errors.append("visual_style.profile must be a non-empty string.")
        else:
            profile_key = profile_name.strip().lower()
            if _KNOWN_STYLE_PROFILE_KEYS and profile_key not in _KNOWN_STYLE_PROFILE_KEYS:
                allowed_profiles = ", ".join(sorted(_KNOWN_STYLE_PROFILES))
                errors.append(
                    f"Invalid visual_style.profile: '{profile_name}'. "
                    f"Allowed values: {allowed_profiles}."
                )

    language_policy = config.get('language_policy', {})
    if language_policy is None:
        language_policy = {}
    if not isinstance(language_policy, dict):
        errors.append("Invalid 'language_policy' section (must be a mapping).")
        language_policy = {}
    else:
        if 'analysis_lang' in language_policy and not isinstance(language_policy.get('analysis_lang'), str):
            errors.append("language_policy.analysis_lang must be a string.")
        if 'plot_lang' in language_policy and not isinstance(language_policy.get('plot_lang'), str):
            errors.append("language_policy.plot_lang must be a string.")
        if 'allow_nonstandard' in language_policy and not isinstance(language_policy.get('allow_nonstandard'), bool):
            errors.append("language_policy.allow_nonstandard must be a boolean.")

    norm_policy = get_language_policy(config)
    if not norm_policy['allow_nonstandard']:
        if norm_policy['analysis_lang'] not in ALLOWED_ANALYSIS_POLICY_LANGS:
            allowed = ", ".join(sorted(ALLOWED_ANALYSIS_POLICY_LANGS))
            errors.append(
                f"language_policy.analysis_lang must be one of: {allowed} "
                "(or set language_policy.allow_nonstandard=true)."
            )
        if norm_policy['plot_lang'] not in ALLOWED_PLOT_POLICY_LANGS:
            allowed = ", ".join(sorted(ALLOWED_PLOT_POLICY_LANGS))
            errors.append(
                f"language_policy.plot_lang must be one of: {allowed} "
                "(or set language_policy.allow_nonstandard=true)."
            )

    presets_raw = config.get('presets', {})
    if presets_raw is None:
        presets_raw = {}
    if not isinstance(presets_raw, dict):
        errors.append("Invalid 'presets' section (must be a mapping).")
    else:
        defined_preset_names = {k for k in presets_raw if k != "_default"}
        default_preset = presets_raw.get("_default")
        if default_preset is not None and default_preset not in defined_preset_names:
            errors.append(
                f"presets._default '{default_preset}' references an undefined preset."
            )
        for preset_name, preset_vals in presets_raw.items():
            if preset_name == "_default":
                continue
            if not isinstance(preset_vals, dict):
                errors.append(f"presets.{preset_name} must be a mapping.")
                continue
            bad_keys = set(preset_vals.keys()) - ALLOWED_PRESET_KEYS
            if bad_keys:
                allowed = ", ".join(sorted(ALLOWED_PRESET_KEYS))
                errors.append(
                    f"presets.{preset_name} contains unknown keys: "
                    f"{', '.join(sorted(bad_keys))}. Allowed: {allowed}."
                )
            if "target_format" in preset_vals:
                tf = preset_vals["target_format"]
                if not isinstance(tf, str) or tf.lower() not in ALLOWED_TARGET_FORMATS:
                    allowed = ", ".join(sorted(ALLOWED_TARGET_FORMATS))
                    errors.append(
                        f"presets.{preset_name}.target_format '{tf}' is invalid. "
                        f"Allowed: {allowed}."
                    )
            if "font_scale" in preset_vals:
                fs = preset_vals["font_scale"]
                if isinstance(fs, bool) or not isinstance(fs, (int, float)) or not (0.5 <= fs <= 3.0):
                    errors.append(
                        f"presets.{preset_name}.font_scale must be a number in [0.5, 3.0]."
                    )
            if "profile" in preset_vals:
                prof = preset_vals["profile"]
                if not isinstance(prof, str) or not prof.strip():
                    errors.append(f"presets.{preset_name}.profile must be a non-empty string.")
            if "output_format" in preset_vals:
                of = preset_vals["output_format"]
                if not isinstance(of, str) or of.strip().lower() not in ALLOWED_OUTPUT_FORMATS:
                    allowed = ", ".join(sorted(ALLOWED_OUTPUT_FORMATS))
                    errors.append(
                        f"presets.{preset_name}.output_format '{of}' is invalid. "
                        f"Allowed: {allowed}."
                    )

    preset_names: set = {k for k in presets_raw if k != "_default"} if isinstance(presets_raw, dict) else set()

    pipeline = config.get('pipeline', {})
    if pipeline is None:
        pipeline = {}
    if not isinstance(pipeline, dict):
        errors.append("Invalid 'pipeline' section (must be a mapping).")
    else:
        analysis_steps = pipeline.get('analysis', [])
        if analysis_steps is None:
            analysis_steps = []
        if not isinstance(analysis_steps, list):
            errors.append("Invalid 'pipeline.analysis' (must be a list).")
        else:
            for i, step in enumerate(analysis_steps, 1):
                if not isinstance(step, dict):
                    errors.append(f"pipeline.analysis[{i}] must be a mapping.")
                    continue
                script = step.get('script')
                if not isinstance(script, str) or not script.strip():
                    errors.append(f"pipeline.analysis[{i}].script is required.")
                inputs = step.get('inputs', None)
                if inputs is not None and not isinstance(inputs, list):
                    errors.append(f"pipeline.analysis[{i}].inputs must be a list.")
                elif isinstance(inputs, list):
                    for inp in inputs:
                        if isinstance(inp, str):
                            if os.path.isabs(inp):
                                errors.append(
                                    f"pipeline.analysis[{i}].inputs: absolute path glob "
                                    f"'{inp}' is not allowed."
                                )
                            elif ".." in inp.split("/"):
                                errors.append(
                                    f"pipeline.analysis[{i}].inputs: path traversal '..' "
                                    f"in '{inp}' is not allowed."
                                )
                outputs = step.get('outputs', None)
                if outputs is not None and not isinstance(outputs, list):
                    errors.append(f"pipeline.analysis[{i}].outputs must be a list.")
                if 'cache' in step and not isinstance(step.get('cache'), bool):
                    errors.append(f"pipeline.analysis[{i}].cache must be a boolean.")
                expand = step.get('expand')
                if expand is not None and expand not in ('batch', 'each'):
                    errors.append(
                        f"pipeline.analysis[{i}].expand must be 'batch' or 'each'."
                    )
                if expand == 'each':
                    errors.append(
                        f"pipeline.analysis[{i}].expand='each' is not supported for analysis steps. "
                        f"Use 'each' only in figures/diagrams sections."
                    )
                if not norm_policy['allow_nonstandard']:
                    step_lang = normalize_lang(step.get('lang', 'r')) or "r"
                    if step_lang != norm_policy['analysis_lang']:
                        errors.append(
                            f"pipeline.analysis[{i}] language '{step_lang}' violates policy "
                            f"(analysis must be '{norm_policy['analysis_lang']}')."
                        )

    _validate_visual_outputs(
        errors,
        config.get('figures', []),
        section_name='figures',
        norm_policy=norm_policy,
        preset_names=preset_names,
    )
    _validate_visual_outputs(
        errors,
        config.get('diagrams', []),
        section_name='diagrams',
        norm_policy=norm_policy,
        preset_names=preset_names,
    )

    execution = config.get('execution', {})
    if execution is None:
        execution = {}
    if not isinstance(execution, dict):
        errors.append("Invalid 'execution' section (must be a mapping).")
    else:
        for key in ('python', 'rscript'):
            if key in execution and not isinstance(execution[key], str):
                errors.append(f"execution.{key} must be a string.")

    environment = config.get('environment', {})
    if environment is None:
        environment = {}
    if not isinstance(environment, dict):
        errors.append("Invalid 'environment' section (must be a mapping).")
    else:
        if 'python_lock' in environment and not isinstance(environment.get('python_lock'), str):
            errors.append("environment.python_lock must be a string.")
        if 'r_lock' in environment and not isinstance(environment.get('r_lock'), str):
            errors.append("environment.r_lock must be a string.")
        if 'strict' in environment and not isinstance(environment.get('strict'), bool):
            errors.append("environment.strict must be a boolean.")

    data_contract = config.get('data_contract', {})
    if data_contract is None:
        data_contract = {}
    if not isinstance(data_contract, dict):
        errors.append("Invalid 'data_contract' section (must be a mapping).")
    else:
        csv_checks = data_contract.get('csv_checks', [])
        if csv_checks is None:
            csv_checks = []
        if not isinstance(csv_checks, list):
            errors.append("data_contract.csv_checks must be a list.")
        else:
            for i, check in enumerate(csv_checks, 1):
                if not isinstance(check, dict):
                    errors.append(f"data_contract.csv_checks[{i}] must be a mapping.")
                    continue
                path = check.get('path')
                if not isinstance(path, str) or not path.strip():
                    errors.append(f"data_contract.csv_checks[{i}].path is required.")
                required_cols = check.get('required_columns', [])
                if required_cols is not None and not isinstance(required_cols, list):
                    errors.append(f"data_contract.csv_checks[{i}].required_columns must be a list.")
                dtypes = check.get('dtypes', {})
                if dtypes is not None and not isinstance(dtypes, dict):
                    errors.append(f"data_contract.csv_checks[{i}].dtypes must be a mapping.")
                min_rows = check.get('min_rows', None)
                if min_rows is not None and (not isinstance(min_rows, int) or min_rows < 0):
                    errors.append(f"data_contract.csv_checks[{i}].min_rows must be a non-negative integer.")

                semantic_checks = check.get('semantic_checks', {})
                if semantic_checks is not None and not isinstance(semantic_checks, dict):
                    errors.append(f"data_contract.csv_checks[{i}].semantic_checks must be a mapping.")
                elif semantic_checks:
                    for col, constraints in semantic_checks.items():
                        if not isinstance(constraints, dict):
                            errors.append(f"Semantic constraints for '{col}' must be a mapping.")
                            continue
                        if 'range' in constraints:
                            r = constraints['range']
                            if not isinstance(r, list) or len(r) != 2:
                                errors.append(f"Semantic range for '{col}' must be a list of 2 numbers.")
                        if 'allow_null' in constraints and not isinstance(constraints['allow_null'], bool):
                            errors.append(f"Semantic allow_null for '{col}' must be a boolean.")
                        if 'unique' in constraints and not isinstance(constraints['unique'], bool):
                            errors.append(f"Semantic unique for '{col}' must be a boolean.")

    golden_metrics = config.get('golden_metrics', [])
    if golden_metrics is None:
        golden_metrics = []
    if not isinstance(golden_metrics, list):
        errors.append("golden_metrics must be a list.")
    else:
        for i, item in enumerate(golden_metrics, 1):
            if not isinstance(item, dict):
                errors.append(f"golden_metrics[{i}] must be a mapping.")
                continue
            path = item.get("path")
            if not isinstance(path, str) or not path.strip():
                errors.append(f"golden_metrics[{i}].path is required.")
            if "atol" in item:
                atol = item.get("atol")
                if isinstance(atol, bool) or not isinstance(atol, (int, float)) or atol < 0:
                    errors.append(f"golden_metrics[{i}].atol must be a non-negative number.")

    return errors


def _validate_visual_outputs(
    errors,
    items,
    *,
    section_name,
    norm_policy,
    preset_names: set | None = None,
):
    if items is None:
        items = []
    if not isinstance(items, list):
        errors.append(f"Invalid '{section_name}' section (must be a list).")
        return

    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append(f"{section_name}[{i}] must be a mapping.")
            continue
        script = item.get('script')
        output = item.get('output')
        lang = normalize_lang(item.get('lang'))

        if lang != "athena":
            if not isinstance(script, str) or not script.strip():
                errors.append(f"{section_name}[{i}].script is required.")

        if not isinstance(output, str) or not output.strip():
            errors.append(f"{section_name}[{i}].output is required for output verification.")
        inputs = item.get('inputs', None)
        if inputs is not None and not isinstance(inputs, list):
            errors.append(f"{section_name}[{i}].inputs must be a list.")
        elif isinstance(inputs, list):
            for inp in inputs:
                if isinstance(inp, str):
                    if os.path.isabs(inp):
                        errors.append(
                            f"{section_name}[{i}].inputs: absolute path "
                            f"'{inp}' is not allowed."
                        )
                    elif ".." in inp.split("/"):
                        errors.append(
                            f"{section_name}[{i}].inputs: path traversal '..' "
                            f"in '{inp}' is not allowed."
                        )
        if 'cache' in item and not isinstance(item.get('cache'), bool):
            errors.append(f"{section_name}[{i}].cache must be a boolean.")
        if 'theme' in item:
            theme = item.get('theme')
            if not isinstance(theme, str) or theme.strip().lower() not in ALLOWED_TARGET_FORMATS:
                allowed = ", ".join(sorted(ALLOWED_TARGET_FORMATS))
                errors.append(f"{section_name}[{i}].theme must be one of: {allowed}.")
        if 'format' in item:
            output_format = item.get('format')
            if not isinstance(output_format, str) or output_format.strip().lower() not in ALLOWED_OUTPUT_FORMATS:
                allowed = ", ".join(sorted(ALLOWED_OUTPUT_FORMATS))
                errors.append(f"{section_name}[{i}].format must be one of: {allowed}.")
        if preset_names is not None and 'preset' in item:
            item_preset = item.get('preset')
            if item_preset not in preset_names:
                errors.append(
                    f"{section_name}[{i}].preset '{item_preset}' references an undefined preset."
                )
        expand = item.get('expand')
        if expand is not None and expand not in ('batch', 'each'):
            errors.append(f"{section_name}[{i}].expand must be 'batch' or 'each'.")
        if expand == 'each' and isinstance(output, str) and '{stem}' not in output:
            errors.append(
                f"{section_name}[{i}].output must contain '{{stem}}' placeholder when expand='each'."
            )
        if not norm_policy['allow_nonstandard'] and isinstance(script, str) and script.strip():
            item_lang = normalize_lang(item.get('lang'))
            if not item_lang:
                item_lang = "r" if script.lower().endswith(".r") else "python"
            if item_lang != norm_policy['plot_lang']:
                errors.append(
                    f"{section_name}[{i}] language '{item_lang}' violates policy "
                    f"(plot must be '{norm_policy['plot_lang']}')."
                )

def load_config(project_dir):
    """프로젝트 루트의 project_config.yaml을 로드."""
    config_path = find_config_path(project_dir)

    if not config_path:
        print(f"❌ Error: project_config.yaml not found in {project_dir}")
        print("   ├─ Run `python orchestrator.py --init --project \"<project>\"` to scaffold one.")
        print("   └─ Or place project_config.yaml at the project root.")
        return None, None, None

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()
            config = yaml.safe_load(raw_text)
    except yaml.YAMLError as e:
        print(f"❌ Error: Invalid YAML in {config_path}\n   └─ {e}")
        print("   └─ Fix the YAML syntax in project_config.yaml and rerun.")
        return None, None, None
    except OSError as e:
        print(f"❌ Error: Failed to read config {config_path}\n   └─ {e}")
        print("   └─ Check file permissions and Google Drive sync state.")
        return None, None, None

    errors = validate_config(config)
    if errors:
        print(f"❌ Error: Invalid config schema in {config_path}")
        for err in errors:
            print(f"   - {err}")
        print("   └─ Compare with the scaffold template or fix the listed fields and rerun.")
        return None, None, None

    # CRLF/LF 차이로 인한 불필요한 캐시 무효화 방지
    config_hash = hashlib.sha256(raw_text.replace('\r\n', '\n').encode('utf-8')).hexdigest()
    return config, config_path, config_hash


def check_project_status(project_path, config, config_hash):
    """프로젝트의 상태를 진단합니다 (Up-to-date, Stale, Missing Figures)."""
    from .cache_manager import load_build_state

    build_state, _ = load_build_state(project_path)

    # 1. Missing Figures 체크
    all_outputs = []
    for section in ['figures', 'diagrams']:
        for item in config.get(section, []):
            if 'output' in item:
                all_outputs.append(os.path.join(project_path, item['output']))

    missing_count = sum(1 for p in all_outputs if not os.path.exists(p))
    if missing_count == len(all_outputs) and all_outputs:
        return "🔴 Missing Figures"
    elif missing_count > 0:
        return f"🟡 Partial ({len(all_outputs)-missing_count}/{len(all_outputs)})"

    # 2. Stale 체크 (config hash 비교)
    if build_state.get("config_hash") != config_hash:
        return "🟡 Stale (Config Changed)"

    return "🟢 Up-to-date"


def list_projects(root_dir, recursive=True, max_depth=4):
    from .ui_utils import ui_print, ui_table

    if max_depth < 1:
        max_depth = 1

    discovered = discover_projects_with_status(root_dir, max_depth=max_depth)
    operational_states = _load_registry_operational_states(root_dir)

    if not discovered:
        ui_print("   [yellow](No configured projects found)[/yellow]")
        return

    rows = []
    valid_count = 0
    for project in discovered:
        status_text = "N/A"
        if project["valid"]:
            valid_count += 1
            # 간이 config 로드하여 상태 확인
            try:
                with open(project["config_path"], 'r', encoding='utf-8') as f:
                    raw_text = f.read()
                    config = yaml.safe_load(raw_text)
                config_hash = hashlib.sha256(raw_text.replace('\r\n', '\n').encode('utf-8')).hexdigest()
                status_text = check_project_status(os.path.join(root_dir, project["path"]), config, config_hash)
            except Exception:
                status_text = "⚠️ Status Error"
        else:
            status_text = "❌ Invalid Config"

        rows.append([
            project['name'],
            project['path'],
            _resolve_operational_state(operational_states, project['path']),
            status_text
        ])

    ui_table(
        title=f"🏛️ Research Projects (depth <= {max_depth})",
        columns=["Project Name", "Path", "Op State", "Status"],
        rows=rows
    )

    valid_str = f"[green]{valid_count}[/green]"
    invalid_count = len(discovered) - valid_count
    invalid_str = f"[red]{invalid_count}[/red]"
    ui_print(
        f"\n   ✅ Found [bold]{len(discovered)}[/bold] project(s) "
        f"({valid_str} valid, {invalid_str} invalid)."
    )


def discover_projects_with_status(root_dir, max_depth=4):
    discovered = []
    root_depth = root_dir.rstrip(os.sep).count(os.sep)

    for current_root, dirs, _files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if not d.startswith((".", "_", "[")) and d != "__pycache__"]
        current_depth = current_root.rstrip(os.sep).count(os.sep) - root_depth
        if current_depth >= max_depth:
            dirs[:] = []

        if current_root == root_dir:
            continue

        cfg = find_config_path(current_root)
        if cfg:
            rel_project = os.path.relpath(current_root, root_dir)
            rel_config = os.path.relpath(cfg, current_root)
            metadata = _load_project_metadata(cfg, os.path.basename(current_root))
            discovered.append({
                'name': metadata["name"],
                'path': rel_project,
                'config': rel_config,
                'config_path': cfg,
                'valid': metadata["valid"],
                'errors': list(metadata["errors"]),
            })

    return sorted(
        discovered,
        key=lambda item: (
            not item['valid'],
            str(item['name']).lower(),
            item['path'],
        ),
    )


def _load_registry_operational_states(root_dir):
    registry_path = os.path.join(root_dir, "ACTIVE_PROJECTS.yaml")
    if not os.path.exists(registry_path):
        return {}

    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = yaml.safe_load(f) or {}
    except Exception:
        return {}

    states = {}
    for section_name in ("active_projects", "published_project_archives", "incubation_candidates"):
        for item in registry.get(section_name, []) or []:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            op_state = item.get("operational_state")
            if isinstance(path, str) and path.strip() and isinstance(op_state, str) and op_state.strip():
                normalized_path = _normalize_registry_path(path.strip())
                states.setdefault(normalized_path, op_state.strip())
    return states


def _normalize_registry_path(path):
    return unicodedata.normalize("NFC", str(path).strip())


def _resolve_operational_state(operational_states, project_path):
    normalized = _normalize_registry_path(project_path)
    if normalized in operational_states:
        return operational_states[normalized]

    best_match = None
    for registered_path, op_state in operational_states.items():
        prefix = registered_path + os.sep
        if normalized.startswith(prefix):
            if best_match is None or len(registered_path) > len(best_match[0]):
                best_match = (registered_path, op_state)

    if best_match is not None:
        return best_match[1]
    return "-"

def get_discoverable_projects(root_dir, max_depth=4):
    """
    연구 루트에서 project_config.yaml이 있는 프로젝트들을 수집하여 리스트로 반환합니다.
    """
    discovered = []
    for project in discover_projects_with_status(root_dir, max_depth=max_depth):
        if not project["valid"]:
            continue
        discovered.append({
            'name': project['name'],
            'path': project['path'],
            'config': project['config'],
        })

    return discovered
