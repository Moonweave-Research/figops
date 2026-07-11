import hashlib
import os

import yaml

from . import config_schema as _config_schema
from .config_assemblies import validate_assemblies as _validate_assemblies_impl
from .config_language_policy import get_language_policy as _get_language_policy_impl
from .config_language_policy import normalize_lang as normalize_lang
from .config_project_registry import load_registry_operational_states as _load_registry_operational_states
from .config_project_registry import normalize_registry_path as _normalize_registry_path  # noqa: F401
from .config_project_registry import resolve_operational_state as _resolve_operational_state
from .config_research_metadata import condition_sample_references as _condition_sample_references
from .config_research_metadata import experimental_condition_ids as _experimental_condition_ids
from .config_research_metadata import validate_canonical_docs as _validate_canonical_docs
from .config_research_metadata import validate_experimental_conditions as _validate_experimental_conditions
from .config_research_metadata import validate_relative_path_value as _validate_relative_path_value  # noqa: F401
from .config_research_metadata import validate_sample_registry as _validate_sample_registry
from .config_semantic_checks import ALLOWED_MONOTONIC_MODES as ALLOWED_MONOTONIC_MODES
from .config_semantic_checks import validate_csv_semantic_checks as _validate_csv_semantic_checks
from .config_style import ALLOWED_FONT_STRATEGIES as ALLOWED_FONT_STRATEGIES
from .config_style import ALLOWED_PRESET_KEYS as ALLOWED_PRESET_KEYS
from .config_style import ALLOWED_TARGET_FORMATS as ALLOWED_TARGET_FORMATS
from .config_style import INTERNAL_STYLE_TARGET_FORMAT as INTERNAL_STYLE_TARGET_FORMAT
from .config_style import KNOWN_STYLE_PROFILE_KEYS as _KNOWN_STYLE_PROFILE_KEYS
from .config_style import KNOWN_STYLE_PROFILES as _KNOWN_STYLE_PROFILES
from .config_style import PROFILE_ALIASES as PROFILE_ALIASES
from .config_style import list_profiles as list_profiles
from .config_style import resolve_presets as resolve_presets
from .config_style import resolve_profile_name as resolve_profile_name
from .config_style import resolve_step_style as resolve_step_style
from .config_sweep_comparison import parse_comparison_config as parse_comparison_config
from .config_sweep_comparison import parse_sweep_config as parse_sweep_config
from .config_sweep_comparison import validate_comparison as _validate_comparison
from .config_sweep_comparison import validate_sweep as _validate_sweep
from .config_top_level_keys import KNOWN_TOP_LEVEL_CONFIG_KEYS as KNOWN_TOP_LEVEL_CONFIG_KEYS
from .config_top_level_keys import levenshtein_distance as _levenshtein_distance  # noqa: F401
from .config_top_level_keys import top_level_key_fingerprint as _top_level_key_fingerprint  # noqa: F401
from .config_top_level_keys import top_level_key_suggestion as _top_level_key_suggestion  # noqa: F401
from .config_top_level_keys import validate_top_level_key_near_misses as _validate_top_level_key_near_misses
from .config_visual_outputs import validate_visual_outputs as _validate_visual_outputs_impl
from .domain_analysis import DOMAIN_HELPER_NAMES
from .execution_security import is_positive_finite_timeout
from .logging import get_logger
from .project_roles import ALLOWED_FOLDER_ROLES as ALLOWED_FOLDER_ROLES
from .project_roles import ALLOWED_PROJECT_ROLES as ALLOWED_PROJECT_ROLES
from .project_roles import ALLOWED_PROJECT_STATUSES as ALLOWED_PROJECT_STATUSES
from .project_roles import DEFAULT_PROJECT_ROLE as DEFAULT_PROJECT_ROLE
from .project_roles import DEFAULT_PROJECT_STATUS as DEFAULT_PROJECT_STATUS
from .project_roles import folder_role_map as folder_role_map
from .project_roles import master_execution_error as master_execution_error
from .project_roles import normalize_project_defaults as normalize_project_defaults
from .project_roles import project_modules as project_modules
from .project_roles import project_role as project_role
from .project_roles import project_status as project_status

CURRENT_CONFIG_SCHEMA_VERSION = _config_schema.CURRENT_CONFIG_SCHEMA_VERSION
SUPPORTED_CONFIG_SCHEMA_VERSIONS = _config_schema.SUPPORTED_CONFIG_SCHEMA_VERSIONS
ConfigMigrationError = _config_schema.ConfigMigrationError
ConfigVersionTooNewError = _config_schema.ConfigVersionTooNewError
_UniqueKeySafeLoader = _config_schema.UniqueKeySafeLoader
_construct_mapping_no_duplicates = _config_schema.construct_mapping_no_duplicates
_load_yaml_with_unique_keys = _config_schema.load_yaml_with_unique_keys
load_yaml_with_unique_keys = _config_schema.load_yaml_with_unique_keys
_schema_version_key = _config_schema.schema_version_key
_schema_version = _config_schema.schema_version
_migrate_0_9_to_1_0 = _config_schema.migrate_0_9_to_1_0
_CONFIG_MIGRATIONS = _config_schema.CONFIG_MIGRATIONS
migrate_config = _config_schema.migrate_config

ALLOWED_ANALYSIS_POLICY_LANGS = {"r"}
ALLOWED_PLOT_POLICY_LANGS = {"python"}
ALLOWED_OUTPUT_FORMATS = {"png", "pdf", "svg"}
ALLOWED_PREFETCH_ADAPTERS = {"none", "noop", "off", "gdrive"}
ALLOWED_ATHENA_ADAPTERS = {"none", "null", "off", "legacy", "on"}
ALLOWED_CONVENTIONS_ADAPTERS = {"none", "generic", "surfur"}
ALLOWED_RAW_INTEGRITY_MODES = {"warn", "strict"}
CONFIG_FILE_CANDIDATES = (
    "project_config.yaml",
    os.path.join("scripts", "project_config.yaml"),
)
logger = get_logger(__name__)


def _validate_raw_integrity_config(errors: list[str], raw_integrity: object) -> None:
    from .config_research_metadata import validate_raw_integrity_config

    return validate_raw_integrity_config(errors, raw_integrity, allowed_modes=ALLOWED_RAW_INTEGRITY_MODES)


def _validate_named_adapter(
    errors: list[str],
    adapters: dict,
    key: str,
    allowed_values: set[str],
) -> None:
    if key not in adapters:
        return
    raw_value = adapters.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        errors.append(f"environment.adapters.{key} must be a non-empty string.")
        return
    value = raw_value.strip().lower()
    if value not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        errors.append(f"environment.adapters.{key} '{raw_value}' is invalid. Allowed: {allowed}.")


def get_language_policy(config):
    """Compatibility wrapper that preserves the local language-normalizer seam."""
    return _get_language_policy_impl(config, normalize_lang_func=normalize_lang)


def find_config_path(project_dir):
    for rel_path in CONFIG_FILE_CANDIDATES:
        candidate = os.path.join(project_dir, rel_path)
        if os.path.exists(candidate):
            return candidate
    return None


def data_contract_bool(config: dict, key: str) -> bool | None:
    data_contract = config.get("data_contract", {}) if isinstance(config, dict) else {}
    if not isinstance(data_contract, dict):
        return None
    value = data_contract.get(key)
    return value if isinstance(value, bool) else None


def module_default_contract_bool(config: dict, key: str) -> bool:
    explicit = data_contract_bool(config, key)
    if explicit is not None:
        return explicit
    return project_role(config) == DEFAULT_PROJECT_ROLE


def _load_project_metadata(config_path, fallback_name):
    metadata = {
        "name": fallback_name,
        "role": DEFAULT_PROJECT_ROLE,
        "status": DEFAULT_PROJECT_STATUS,
        "valid": False,
        "errors": [],
    }

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            conf_data = _load_yaml_with_unique_keys(f.read())
    except Exception as exc:
        metadata["errors"] = [f"Failed to read config: {exc}"]
        return metadata

    if not isinstance(conf_data, dict):
        metadata["errors"] = validate_config(conf_data)
        return metadata

    try:
        conf_data = migrate_config(conf_data)
    except ConfigMigrationError as exc:
        metadata["errors"] = [str(exc)]
        return metadata
    conf_data = normalize_project_defaults(conf_data)

    project_section = conf_data.get("project")
    if not isinstance(project_section, dict):
        project_section = {}
    metadata["name"] = project_section.get("name", fallback_name)
    metadata["role"] = project_role(conf_data)
    metadata["status"] = project_status(conf_data)
    metadata["errors"] = validate_config(conf_data)
    metadata["valid"] = len(metadata["errors"]) == 0
    return metadata


def _read_project_metadata(config_path, fallback_name):
    metadata = _load_project_metadata(config_path, fallback_name)
    return metadata["name"], metadata["valid"], list(metadata["errors"])


def _validate_assemblies(errors: list[str], assemblies) -> None:
    """Compatibility wrapper for multi-panel figure assembly validation."""
    _validate_assemblies_impl(
        errors,
        assemblies,
        allowed_font_strategies=ALLOWED_FONT_STRATEGIES,
    )


def validate_config(config):
    errors = []

    if not isinstance(config, dict):
        return ["Config root must be a YAML mapping/object."]

    _validate_top_level_key_near_misses(errors, config)

    schema_version = config.get("schema_version")
    if schema_version is not None:
        version = str(schema_version)
        try:
            version_key = _schema_version_key(version)
            current_key = _schema_version_key(CURRENT_CONFIG_SCHEMA_VERSION)
        except ConfigMigrationError as exc:
            errors.append(str(exc))
        else:
            if version_key > current_key:
                errors.append(
                    f"schema_version '{schema_version}' is newer than this FigOps runtime supports "
                    f"('{CURRENT_CONFIG_SCHEMA_VERSION}'). Upgrade FigOps before loading this config."
                )
            elif version != CURRENT_CONFIG_SCHEMA_VERSION:
                supported = ", ".join(SUPPORTED_CONFIG_SCHEMA_VERSIONS)
                errors.append(
                    f"schema_version '{schema_version}' must be migrated to "
                    f"'{CURRENT_CONFIG_SCHEMA_VERSION}' before validation. "
                    f"Use migrate_config()/load_config(); supported versions: {supported}."
                )

    project = config.get("project")
    role = DEFAULT_PROJECT_ROLE
    if not isinstance(project, dict):
        errors.append("Missing or invalid 'project' section (must be a mapping).")
    else:
        name = project.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append("Missing required field: project.name (non-empty string).")
        raw_role = project.get("role", DEFAULT_PROJECT_ROLE)
        if not isinstance(raw_role, str) or raw_role.strip().lower() not in ALLOWED_PROJECT_ROLES:
            allowed = ", ".join(sorted(ALLOWED_PROJECT_ROLES))
            errors.append(f"Invalid project.role: '{raw_role}'. Allowed values: {allowed}.")
        else:
            role = raw_role.strip().lower() or DEFAULT_PROJECT_ROLE
        raw_status = project.get("status", DEFAULT_PROJECT_STATUS)
        if not isinstance(raw_status, str) or raw_status.strip().lower() not in ALLOWED_PROJECT_STATUSES:
            allowed = ", ".join(sorted(ALLOWED_PROJECT_STATUSES))
            errors.append(f"Invalid project.status: '{raw_status}'. Allowed values: {allowed}.")

    modules = config.get("modules", [])
    if modules is None:
        modules = []
    if not isinstance(modules, list):
        errors.append("modules must be a list of relative module paths when provided.")
    else:
        for i, module_path in enumerate(modules, 1):
            if not isinstance(module_path, str) or not module_path.strip():
                errors.append(f"modules[{i}] must be a non-empty relative path.")
                continue
            if os.path.isabs(module_path):
                errors.append(f"modules[{i}] must be a relative path, got absolute path '{module_path}'.")
            elif ".." in module_path.replace("\\", "/").split("/"):
                errors.append(f"modules[{i}] must not contain path traversal '..': '{module_path}'.")

    folder_roles = config.get("folder_roles", {})
    if folder_roles is None:
        folder_roles = {}
    normalized_folder_roles = {}
    if not isinstance(folder_roles, dict):
        errors.append("folder_roles must be a mapping of relative folder paths to folder roles when provided.")
    else:
        for raw_path, raw_folder_role in folder_roles.items():
            if not isinstance(raw_path, str) or not raw_path.strip():
                errors.append("folder_roles keys must be non-empty relative paths.")
                continue
            folder_path = raw_path.strip().strip("/\\").replace("\\", "/")
            if not folder_path:
                errors.append("folder_roles keys must be non-empty relative paths.")
                continue
            if os.path.isabs(raw_path):
                errors.append(f"folder_roles.{raw_path} must be a relative path.")
            elif ".." in folder_path.split("/"):
                errors.append(f"folder_roles.{raw_path} must not contain path traversal '..'.")
            if not isinstance(raw_folder_role, str) or raw_folder_role.strip().lower() not in ALLOWED_FOLDER_ROLES:
                allowed = ", ".join(sorted(ALLOWED_FOLDER_ROLES))
                errors.append(
                    f"Invalid folder_roles.{raw_path}: '{raw_folder_role}'. Allowed values: {allowed}."
                )
                continue
            normalized_folder_roles[folder_path] = raw_folder_role.strip().lower()

    module_paths = {module_path.strip().strip("/\\").replace("\\", "/") for module_path in project_modules(config)}
    for module_path in sorted(module_paths):
        mapped_role = normalized_folder_roles.get(module_path)
        if mapped_role and mapped_role != "module":
            errors.append(
                f"modules entry '{module_path}' conflicts with folder_roles role '{mapped_role}'. "
                "Module paths must not be assigned a non-module folder role."
            )

    if role == "master":
        pipeline = config.get("pipeline", {})
        has_pipeline = isinstance(pipeline, dict) and any(bool(pipeline.get(key)) for key in ("analysis",))
        if has_pipeline:
            errors.append("project.role 'master' must not define pipeline analysis steps; use execution modules.")
        if config.get("figures"):
            errors.append("project.role 'master' must not define figures; use execution modules.")
        if config.get("diagrams"):
            errors.append("project.role 'master' must not define diagrams; use execution modules.")

    _validate_canonical_docs(errors, config.get("canonical_docs"))
    _validate_experimental_conditions(errors, config.get("experimental_conditions"))
    sample_ids = _validate_sample_registry(errors, config.get("sample_registry"))
    if sample_ids is not None:
        unknown_sample_ids = sorted(_condition_sample_references(config.get("experimental_conditions")) - sample_ids)
        if unknown_sample_ids:
            errors.append(
                "Unknown sample_id(s) referenced by experimental_conditions.conditions[].parameters.samples: "
                f"{', '.join(unknown_sample_ids)}."
            )

    visual_style = config.get("visual_style", {})
    if visual_style is None:
        visual_style = {}
    if not isinstance(visual_style, dict):
        errors.append("Invalid 'visual_style' section (must be a mapping).")
    else:
        target_format = visual_style.get("target_format", "nature")
        if not isinstance(target_format, str) or target_format.lower() not in ALLOWED_TARGET_FORMATS:
            allowed = ", ".join(sorted(ALLOWED_TARGET_FORMATS))
            errors.append(f"Invalid visual_style.target_format: '{target_format}'. Allowed values: {allowed}.")

        font_scale = visual_style.get("font_scale", 1.0)
        if isinstance(font_scale, bool) or not isinstance(font_scale, (int, float)) or font_scale <= 0:
            errors.append("visual_style.font_scale must be a positive number.")

        profile_name = visual_style.get("profile", "baseline")
        if not isinstance(profile_name, str) or not profile_name.strip():
            errors.append("visual_style.profile must be a non-empty string.")
        else:
            profile_key = profile_name.strip().lower()
            if _KNOWN_STYLE_PROFILE_KEYS and profile_key not in _KNOWN_STYLE_PROFILE_KEYS:
                allowed_profiles = ", ".join(sorted(_KNOWN_STYLE_PROFILES))
                errors.append(f"Invalid visual_style.profile: '{profile_name}'. Allowed values: {allowed_profiles}.")

    language_policy = config.get("language_policy", {})
    if language_policy is None:
        language_policy = {}
    if not isinstance(language_policy, dict):
        errors.append("Invalid 'language_policy' section (must be a mapping).")
        language_policy = {}
    else:
        if "analysis_lang" in language_policy and not isinstance(language_policy.get("analysis_lang"), str):
            errors.append("language_policy.analysis_lang must be a string.")
        if "plot_lang" in language_policy and not isinstance(language_policy.get("plot_lang"), str):
            errors.append("language_policy.plot_lang must be a string.")
        if "allow_nonstandard" in language_policy and not isinstance(language_policy.get("allow_nonstandard"), bool):
            errors.append("language_policy.allow_nonstandard must be a boolean.")

    norm_policy = get_language_policy(config)
    if not norm_policy["allow_nonstandard"]:
        if norm_policy["analysis_lang"] not in ALLOWED_ANALYSIS_POLICY_LANGS:
            allowed = ", ".join(sorted(ALLOWED_ANALYSIS_POLICY_LANGS))
            errors.append(
                f"language_policy.analysis_lang must be one of: {allowed} "
                "(or set language_policy.allow_nonstandard=true)."
            )
        if norm_policy["plot_lang"] not in ALLOWED_PLOT_POLICY_LANGS:
            allowed = ", ".join(sorted(ALLOWED_PLOT_POLICY_LANGS))
            errors.append(
                f"language_policy.plot_lang must be one of: {allowed} (or set language_policy.allow_nonstandard=true)."
            )

    presets_raw = config.get("presets", {})
    if presets_raw is None:
        presets_raw = {}
    if not isinstance(presets_raw, dict):
        errors.append("Invalid 'presets' section (must be a mapping).")
    else:
        defined_preset_names = {k for k in presets_raw if k != "_default"}
        default_preset = presets_raw.get("_default")
        if default_preset is not None and default_preset not in defined_preset_names:
            errors.append(f"presets._default '{default_preset}' references an undefined preset.")
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
                    f"presets.{preset_name} contains unknown keys: {', '.join(sorted(bad_keys))}. Allowed: {allowed}."
                )
            if "target_format" in preset_vals:
                tf = preset_vals["target_format"]
                if not isinstance(tf, str) or tf.lower() not in ALLOWED_TARGET_FORMATS:
                    allowed = ", ".join(sorted(ALLOWED_TARGET_FORMATS))
                    errors.append(f"presets.{preset_name}.target_format '{tf}' is invalid. Allowed: {allowed}.")
            if "font_scale" in preset_vals:
                fs = preset_vals["font_scale"]
                if isinstance(fs, bool) or not isinstance(fs, (int, float)) or not (0.5 <= fs <= 3.0):
                    errors.append(f"presets.{preset_name}.font_scale must be a number in [0.5, 3.0].")
            if "profile" in preset_vals:
                prof = preset_vals["profile"]
                if not isinstance(prof, str) or not prof.strip():
                    errors.append(f"presets.{preset_name}.profile must be a non-empty string.")
            if "output_format" in preset_vals:
                of = preset_vals["output_format"]
                if not isinstance(of, str) or of.strip().lower() not in ALLOWED_OUTPUT_FORMATS:
                    allowed = ", ".join(sorted(ALLOWED_OUTPUT_FORMATS))
                    errors.append(f"presets.{preset_name}.output_format '{of}' is invalid. Allowed: {allowed}.")

    preset_names: set = {k for k in presets_raw if k != "_default"} if isinstance(presets_raw, dict) else set()

    pipeline = config.get("pipeline", {})
    if pipeline is None:
        pipeline = {}
    if not isinstance(pipeline, dict):
        errors.append("Invalid 'pipeline' section (must be a mapping).")
    else:
        analysis_steps = pipeline.get("analysis", [])
        if analysis_steps is None:
            analysis_steps = []
        if not isinstance(analysis_steps, list):
            errors.append("Invalid 'pipeline.analysis' (must be a list).")
        else:
            for i, step in enumerate(analysis_steps, 1):
                if not isinstance(step, dict):
                    errors.append(f"pipeline.analysis[{i}] must be a mapping.")
                    continue
                script = step.get("script")
                domain_helper = step.get("domain_helper")
                has_script = isinstance(script, str) and bool(script.strip())
                has_domain_helper = isinstance(domain_helper, str) and bool(domain_helper.strip())
                if has_script == has_domain_helper:
                    errors.append(f"pipeline.analysis[{i}] must define exactly one of script or domain_helper.")
                if domain_helper is not None:
                    if not isinstance(domain_helper, str) or not domain_helper.strip():
                        errors.append(f"pipeline.analysis[{i}].domain_helper must be a non-empty string.")
                    elif domain_helper not in DOMAIN_HELPER_NAMES:
                        allowed = ", ".join(sorted(DOMAIN_HELPER_NAMES))
                        errors.append(
                            f"pipeline.analysis[{i}].domain_helper '{domain_helper}' is invalid. Allowed: {allowed}."
                        )
                    if "params" in step and not isinstance(step.get("params"), dict):
                        errors.append(f"pipeline.analysis[{i}].params must be a mapping.")
                inputs = step.get("inputs", None)
                if inputs is not None and not isinstance(inputs, list):
                    errors.append(f"pipeline.analysis[{i}].inputs must be a list.")
                elif isinstance(inputs, list):
                    for inp in inputs:
                        if isinstance(inp, str):
                            if os.path.isabs(inp):
                                errors.append(
                                    f"pipeline.analysis[{i}].inputs: absolute path glob '{inp}' is not allowed."
                                )
                            elif ".." in inp.replace("\\", "/").split("/"):
                                errors.append(
                                    f"pipeline.analysis[{i}].inputs: path traversal '..' in '{inp}' is not allowed."
                                )
                outputs = step.get("outputs", None)
                if outputs is not None and not isinstance(outputs, list):
                    errors.append(f"pipeline.analysis[{i}].outputs must be a list.")
                elif has_domain_helper and not outputs:
                    errors.append(f"pipeline.analysis[{i}].outputs is required for domain_helper steps.")
                if "cache" in step and not isinstance(step.get("cache"), bool):
                    errors.append(f"pipeline.analysis[{i}].cache must be a boolean.")
                expand = step.get("expand")
                if expand is not None and expand not in ("batch", "each"):
                    errors.append(f"pipeline.analysis[{i}].expand must be 'batch' or 'each'.")
                if expand == "each":
                    errors.append(
                        f"pipeline.analysis[{i}].expand='each' is not supported for analysis steps. "
                        f"Use 'each' only in figures/diagrams sections."
                    )
                if has_script and not norm_policy["allow_nonstandard"]:
                    step_lang = normalize_lang(step.get("lang", "r")) or "r"
                    if step_lang != norm_policy["analysis_lang"]:
                        errors.append(
                            f"pipeline.analysis[{i}] language '{step_lang}' violates policy "
                            f"(analysis must be '{norm_policy['analysis_lang']}')."
                        )

    require_figure_traceability = module_default_contract_bool(config, "require_figure_traceability")
    condition_ids = _experimental_condition_ids(config.get("experimental_conditions"))

    _validate_visual_outputs(
        errors,
        config.get("figures", []),
        section_name="figures",
        norm_policy=norm_policy,
        preset_names=preset_names,
        sample_ids=sample_ids,
        condition_ids=condition_ids,
        require_traceability=require_figure_traceability,
    )
    _validate_visual_outputs(
        errors,
        config.get("diagrams", []),
        section_name="diagrams",
        norm_policy=norm_policy,
        preset_names=preset_names,
        sample_ids=sample_ids,
        condition_ids=condition_ids,
        require_traceability=False,
    )

    execution = config.get("execution", {})
    if execution is None:
        execution = {}
    if not isinstance(execution, dict):
        errors.append("Invalid 'execution' section (must be a mapping).")
    else:
        for key in ("python", "rscript"):
            if key in execution and execution[key] is not None and not isinstance(execution[key], str):
                errors.append(f"execution.{key} must be a string or null.")
        if "timeout_seconds" in execution and not is_positive_finite_timeout(execution["timeout_seconds"]):
            errors.append("execution.timeout_seconds must be a positive finite number.")

    environment = config.get("environment", {})
    if environment is None:
        environment = {}
    if not isinstance(environment, dict):
        errors.append("Invalid 'environment' section (must be a mapping).")
    else:
        if "python_lock" in environment and not isinstance(environment.get("python_lock"), str):
            errors.append("environment.python_lock must be a string.")
        if "r_lock" in environment and not isinstance(environment.get("r_lock"), str):
            errors.append("environment.r_lock must be a string.")
        if "strict" in environment and not isinstance(environment.get("strict"), bool):
            errors.append("environment.strict must be a boolean.")
        adapters = environment.get("adapters", {})
        if adapters is None:
            adapters = {}
        if not isinstance(adapters, dict):
            errors.append("environment.adapters must be a mapping.")
        else:
            _validate_named_adapter(errors, adapters, "prefetch", ALLOWED_PREFETCH_ADAPTERS)
            _validate_named_adapter(errors, adapters, "athena", ALLOWED_ATHENA_ADAPTERS)
            _validate_named_adapter(errors, adapters, "conventions", ALLOWED_CONVENTIONS_ADAPTERS)

    data_contract = config.get("data_contract", {})
    if data_contract is None:
        data_contract = {}
    if not isinstance(data_contract, dict):
        errors.append("Invalid 'data_contract' section (must be a mapping).")
    else:
        if "require_figure_traceability" in data_contract and not isinstance(
            data_contract.get("require_figure_traceability"), bool
        ):
            errors.append("data_contract.require_figure_traceability must be a boolean.")
        if "require_canonical_docs" in data_contract and not isinstance(
            data_contract.get("require_canonical_docs"), bool
        ):
            errors.append("data_contract.require_canonical_docs must be a boolean.")
        if "forbid_todo_placeholders" in data_contract and not isinstance(
            data_contract.get("forbid_todo_placeholders"), bool
        ):
            errors.append("data_contract.forbid_todo_placeholders must be a boolean.")
        _validate_raw_integrity_config(errors, data_contract.get("raw_integrity"))
        csv_checks = data_contract.get("csv_checks", [])
        if csv_checks is None:
            csv_checks = []
        if not isinstance(csv_checks, list):
            errors.append("data_contract.csv_checks must be a list.")
        else:
            for i, check in enumerate(csv_checks, 1):
                if not isinstance(check, dict):
                    errors.append(f"data_contract.csv_checks[{i}] must be a mapping.")
                    continue
                path = check.get("path")
                if not isinstance(path, str) or not path.strip():
                    errors.append(f"data_contract.csv_checks[{i}].path is required.")
                required_cols = check.get("required_columns", [])
                if required_cols is not None and not isinstance(required_cols, list):
                    errors.append(f"data_contract.csv_checks[{i}].required_columns must be a list.")
                dtypes = check.get("dtypes", {})
                if dtypes is not None and not isinstance(dtypes, dict):
                    errors.append(f"data_contract.csv_checks[{i}].dtypes must be a mapping.")
                min_rows = check.get("min_rows", None)
                if min_rows is not None and (not isinstance(min_rows, int) or min_rows < 0):
                    errors.append(f"data_contract.csv_checks[{i}].min_rows must be a non-negative integer.")

                _validate_csv_semantic_checks(
                    errors,
                    check.get("semantic_checks", {}),
                    check_index=i,
                )

    golden_metrics = config.get("golden_metrics", [])
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

    sweep = config.get("sweep", None)
    if sweep is not None:
        errors.extend(_validate_sweep(sweep))

    comparison = config.get("comparison", None)
    if comparison is not None:
        errors.extend(_validate_comparison(comparison))

    if sweep is not None and comparison is not None:
        sweep_enabled = isinstance(sweep, dict) and sweep.get("enabled", False)
        comparison_enabled = isinstance(comparison, dict) and comparison.get("enabled", False)
        if sweep_enabled and comparison_enabled:
            errors.append("sweep.enabled and comparison.enabled cannot both be true; they are mutually exclusive.")

    _validate_assemblies(errors, config.get("assemblies", {}))

    return errors


def _validate_visual_outputs(
    errors,
    items,
    *,
    section_name,
    norm_policy,
    preset_names: set | None = None,
    sample_ids: set[str] | None = None,
    condition_ids: set[str] | None = None,
    require_traceability: bool = False,
):
    _validate_visual_outputs_impl(
        errors,
        items,
        section_name=section_name,
        norm_policy=norm_policy,
        normalize_lang_func=normalize_lang,
        allowed_target_formats=ALLOWED_TARGET_FORMATS,
        allowed_output_formats=ALLOWED_OUTPUT_FORMATS,
        preset_names=preset_names,
        sample_ids=sample_ids,
        condition_ids=condition_ids,
        require_traceability=require_traceability,
    )


def load_config(project_dir):
    """프로젝트 루트의 project_config.yaml을 로드."""
    config_path = find_config_path(project_dir)

    if not config_path:
        logger.error("❌ Error: project_config.yaml not found in %s", project_dir)
        logger.error('   ├─ Run `python orchestrator.py --init --project "<project>"` to scaffold one.')
        logger.error("   └─ Or place project_config.yaml at the project root.")
        return None, None, None

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_text = f.read()
            config = _load_yaml_with_unique_keys(raw_text)
    except yaml.YAMLError as e:
        logger.error("❌ Error: Invalid YAML in %s\n   └─ %s", config_path, e)
        logger.error("   └─ Fix the YAML syntax in project_config.yaml and rerun.")
        return None, None, None
    except OSError as e:
        logger.error("❌ Error: Failed to read config %s\n   └─ %s", config_path, e)
        logger.error("   └─ Check file permissions and local file availability.")
        return None, None, None

    try:
        config = migrate_config(config)
    except ConfigMigrationError as e:
        logger.error("❌ Error: Invalid config schema in %s", config_path)
        logger.error("   - %s", e)
        logger.error("   └─ Compare with the scaffold template or fix the listed fields and rerun.")
        return None, None, None
    config = normalize_project_defaults(config)

    errors = validate_config(config)
    if errors:
        logger.error("❌ Error: Invalid config schema in %s", config_path)
        for err in errors:
            logger.error("   - %s", err)
        logger.error("   └─ Compare with the scaffold template or fix the listed fields and rerun.")
        return None, None, None

    # CRLF/LF 차이로 인한 불필요한 캐시 무효화 방지
    config_hash = hashlib.sha256(raw_text.replace("\r\n", "\n").encode("utf-8")).hexdigest()
    return config, config_path, config_hash


def check_project_status(project_path, config, config_hash):
    """프로젝트의 상태를 진단합니다 (Up-to-date, Stale, Missing Figures)."""
    from .cache_manager import load_build_state

    build_state, _ = load_build_state(project_path)

    # 1. Missing Figures 체크
    all_outputs = []
    for section in ["figures", "diagrams"]:
        for item in config.get(section, []):
            if "output" in item:
                all_outputs.append(os.path.join(project_path, item["output"]))

    missing_count = sum(1 for p in all_outputs if not os.path.exists(p))
    if missing_count == len(all_outputs) and all_outputs:
        return "🔴 Missing Figures"
    elif missing_count > 0:
        return f"🟡 Partial ({len(all_outputs) - missing_count}/{len(all_outputs)})"

    # 2. Stale 체크 (config hash 비교)
    if build_state.get("config_hash") != config_hash:
        return "🟡 Stale (Config Changed)"

    return "🟢 Up-to-date"


def list_projects(root_dir, recursive=True, max_depth=4):
    from .ui_utils import ui_print, ui_table

    if max_depth < 1:
        max_depth = 1

    scan_depth = max_depth if recursive else 1
    discovered = discover_projects_with_status(root_dir, max_depth=scan_depth)
    operational_states = _load_registry_operational_states(root_dir)

    if not discovered:
        ui_print("   [yellow](No configured projects found)[/yellow]")
        return

    rows = []
    valid_count = 0
    invalid_projects = []
    for project in discovered:
        status_text = "N/A"
        if project["valid"]:
            valid_count += 1
            if project.get("role") == "master":
                status_text = "N/A (master manifest)"
            else:
                # 간이 config 로드하여 상태 확인
                try:
                    with open(project["config_path"], "r", encoding="utf-8") as f:
                        raw_text = f.read()
                        config = _load_yaml_with_unique_keys(raw_text)
                    config_hash = hashlib.sha256(raw_text.replace("\r\n", "\n").encode("utf-8")).hexdigest()
                    status_text = check_project_status(os.path.join(root_dir, project["path"]), config, config_hash)
                except Exception:
                    status_text = "⚠️ Status Error"
        else:
            status_text = "❌ Invalid Config"
            invalid_projects.append(project)

        rows.append(
            [
                project["name"],
                project["path"],
                project.get("role", "-"),
                project.get("status", "-"),
                project.get("classification", "-"),
                project.get("target_format", "-"),
                _resolve_operational_state(operational_states, project["path"]),
                status_text,
            ]
        )

    ui_table(
        title=f"🏛️ Research Projects (depth <= {max_depth})",
        columns=["Project Name", "Path", "Role", "Lifecycle", "Class", "Style", "Op State", "Status"],
        rows=rows,
    )

    valid_str = f"[green]{valid_count}[/green]"
    invalid_count = len(discovered) - valid_count
    invalid_str = f"[red]{invalid_count}[/red]"
    ui_print(f"\n   ✅ Found [bold]{len(discovered)}[/bold] project(s) ({valid_str} valid, {invalid_str} invalid).")
    if invalid_projects:
        ui_print("\n   [red]Invalid project config errors:[/red]")
        for project in invalid_projects:
            ui_print(f"   - {project['path']} ({project.get('config', 'project_config.yaml')})")
            for error in project.get("errors", []):
                ui_print(f"     • {error}")


def discover_projects_with_status(root_dir, max_depth=4):
    from .project_discovery import discover_projects_with_status as _discover_projects_with_status

    return _discover_projects_with_status(root_dir, max_depth=max_depth)


def get_discoverable_projects(root_dir, max_depth=4):
    """
    연구 루트에서 project_config.yaml이 있는 프로젝트들을 수집하여 리스트로 반환합니다.
    """
    from .project_discovery import get_discoverable_projects as _get_discoverable_projects

    return _get_discoverable_projects(root_dir, max_depth=max_depth)
