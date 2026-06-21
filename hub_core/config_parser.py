import hashlib
import math
import os
import unicodedata
from copy import deepcopy

import yaml

from .domain_analysis import DOMAIN_HELPER_NAMES
from .logging import get_logger

ALLOWED_TARGET_FORMATS = {
    "nature",
    "nature_surfur",
    "science",
    "ppt",
    "default",
    "acs",
    "rsc",
    "elsevier",
    "wiley",
    "cell",
}
ALLOWED_FONT_STRATEGIES = {"compensate", "as_is"}
CURRENT_CONFIG_SCHEMA_VERSION = "1.0"
SUPPORTED_CONFIG_SCHEMA_VERSIONS = ("0.9", CURRENT_CONFIG_SCHEMA_VERSION)
ALLOWED_PRESET_KEYS = {
    "target_format",
    "font_scale",
    "profile",
    "output_format",
    "colormap",
}
ALLOWED_ANALYSIS_POLICY_LANGS = {"r"}
ALLOWED_PLOT_POLICY_LANGS = {"python"}
ALLOWED_OUTPUT_FORMATS = {"png", "pdf", "svg"}
ALLOWED_MONOTONIC_MODES = {"increasing", "decreasing", "nondecreasing", "nonincreasing"}
ALLOWED_PREFETCH_ADAPTERS = {"none", "noop", "off", "gdrive"}
ALLOWED_ATHENA_ADAPTERS = {"none", "null", "off", "legacy", "on"}
ALLOWED_CONVENTIONS_ADAPTERS = {"none", "generic", "surfur"}
ALLOWED_PROJECT_ROLES = {"master", "module"}
DEFAULT_PROJECT_ROLE = "module"
CONFIG_FILE_CANDIDATES = (
    "project_config.yaml",
    os.path.join("scripts", "project_config.yaml"),
)
logger = get_logger(__name__)


class ConfigMigrationError(ValueError):
    """Raised when a config schema cannot be migrated by this runtime."""


class ConfigVersionTooNewError(ConfigMigrationError):
    """Raised when a config declares a schema newer than this runtime."""

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


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping_no_duplicates(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.YAMLError(f"Duplicate key '{key}' at line {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_no_duplicates,
)


def _load_yaml_with_unique_keys(raw_text: str):
    return yaml.load(raw_text, Loader=_UniqueKeySafeLoader)


def _schema_version_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(version).split("."))
    except ValueError as exc:
        raise ConfigMigrationError(f"schema_version '{version}' must use numeric dot-separated segments.") from exc


def _schema_version(config: dict) -> str:
    raw_version = config.get("schema_version", CURRENT_CONFIG_SCHEMA_VERSION)
    if raw_version is None:
        return CURRENT_CONFIG_SCHEMA_VERSION
    return str(raw_version)


def _migrate_0_9_to_1_0(config: dict) -> dict:
    migrated = deepcopy(config)
    migrated["schema_version"] = CURRENT_CONFIG_SCHEMA_VERSION
    return migrated


_CONFIG_MIGRATIONS = {
    "0.9": _migrate_0_9_to_1_0,
}


def migrate_config(config):
    """Return a config migrated to the current schema version."""
    if not isinstance(config, dict):
        return config

    migrated = deepcopy(config)
    version = _schema_version(migrated)
    current_key = _schema_version_key(CURRENT_CONFIG_SCHEMA_VERSION)

    if _schema_version_key(version) > current_key:
        raise ConfigVersionTooNewError(
            f"project_config.yaml schema_version '{version}' is newer than this Graph Hub runtime supports "
            f"('{CURRENT_CONFIG_SCHEMA_VERSION}'). Upgrade Graph Hub before loading this config."
        )

    while version != CURRENT_CONFIG_SCHEMA_VERSION:
        migration = _CONFIG_MIGRATIONS.get(version)
        if migration is None:
            supported = ", ".join(SUPPORTED_CONFIG_SCHEMA_VERSIONS)
            raise ConfigMigrationError(
                f"project_config.yaml schema_version '{version}' is not supported by this Graph Hub runtime. "
                f"Supported versions: {supported}."
            )
        migrated = migration(migrated)
        next_version = _schema_version(migrated)
        if next_version == version:
            raise ConfigMigrationError(f"Config migration for schema_version '{version}' did not advance.")
        version = next_version

    migrated["schema_version"] = CURRENT_CONFIG_SCHEMA_VERSION
    return migrated


def _validate_grouped_check_config(errors, *, column: str, check_name: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic {check_name} for '{column}' must be a mapping.")
        return

    group_by = raw_check.get("group_by")
    if not isinstance(group_by, list) or not group_by:
        errors.append(f"Semantic {check_name}.group_by for '{column}' must be a non-empty list of column names.")
    elif any(not isinstance(item, str) or not item.strip() for item in group_by):
        errors.append(f"Semantic {check_name}.group_by for '{column}' must contain only non-empty strings.")

    if check_name == "min_replicates":
        min_count = raw_check.get("min_count")
        if isinstance(min_count, bool) or not isinstance(min_count, int) or min_count <= 0:
            errors.append(f"Semantic min_replicates.min_count for '{column}' must be a positive integer.")
        return

    threshold = raw_check.get("threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or threshold <= 0:
        errors.append(f"Semantic grouped_cv.threshold for '{column}' must be a positive number.")

    min_count = raw_check.get("min_count", 2)
    if isinstance(min_count, bool) or not isinstance(min_count, int) or min_count <= 0:
        errors.append(f"Semantic grouped_cv.min_count for '{column}' must be a positive integer when provided.")

    warn_only = raw_check.get("warn_only", True)
    if not isinstance(warn_only, bool):
        errors.append(f"Semantic grouped_cv.warn_only for '{column}' must be a boolean.")


def _validate_errorbar_check_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic error_bar_source for '{column}' must be a mapping.")
        return
    error_column = raw_check.get("column")
    if not isinstance(error_column, str) or not error_column.strip():
        errors.append(f"Semantic error_bar_source.column for '{column}' must be a non-empty string.")
    source = raw_check.get("source", "custom")
    if not isinstance(source, str) or not source.strip():
        errors.append(f"Semantic error_bar_source.source for '{column}' must be a non-empty string.")


def _validate_mean_sem_check_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic mean_sem for '{column}' must be a mapping.")
        return
    for key in ("sem_column", "std_column", "n_column"):
        value = raw_check.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Semantic mean_sem.{key} for '{column}' must be a non-empty string.")
    tolerance = raw_check.get("tolerance", 1.0e-6)
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or tolerance < 0:
        errors.append(f"Semantic mean_sem.tolerance for '{column}' must be a non-negative number.")


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _validate_linear_fit_check_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic linear_fit for '{column}' must be a mapping.")
        return
    x_column = raw_check.get("x_column")
    if not isinstance(x_column, str) or not x_column.strip():
        errors.append(f"Semantic linear_fit.x_column for '{column}' must be a non-empty string.")
    for key in ("slope", "intercept"):
        if not _is_finite_number(raw_check.get(key)):
            errors.append(f"Semantic linear_fit.{key} for '{column}' must be a finite number.")
    if "r2_min" in raw_check:
        r2_min = raw_check.get("r2_min")
        if not _is_finite_number(r2_min) or not 0 <= float(r2_min) <= 1:
            errors.append(f"Semantic linear_fit.r2_min for '{column}' must be a finite number between 0 and 1.")
    tolerance = raw_check.get("tolerance", 1.0e-6)
    if not _is_finite_number(tolerance) or float(tolerance) < 0:
        errors.append(f"Semantic linear_fit.tolerance for '{column}' must be a non-negative finite number.")


def _is_scalar_flag_value(value: object) -> bool:
    return isinstance(value, (str, bool, int, float)) and not (isinstance(value, float) and math.isnan(value))


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


def _validate_outlier_flag_check_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic outlier_flag for '{column}' must be a mapping.")
        return
    flag_column = raw_check.get("column")
    if not isinstance(flag_column, str) or not flag_column.strip():
        errors.append(f"Semantic outlier_flag.column for '{column}' must be a non-empty string.")
    if "allowed" in raw_check:
        allowed = raw_check.get("allowed")
        if not isinstance(allowed, list) or not allowed:
            errors.append(f"Semantic outlier_flag.allowed for '{column}' must be a non-empty list.")
        elif any(not _is_scalar_flag_value(item) for item in allowed):
            errors.append(
                f"Semantic outlier_flag.allowed for '{column}' must contain only scalar strings, numbers, or booleans."
            )
    if "max_fraction" in raw_check:
        max_fraction = raw_check.get("max_fraction")
        if not _is_finite_number(max_fraction) or not 0 <= float(max_fraction) <= 1:
            errors.append(f"Semantic outlier_flag.max_fraction for '{column}' must be a finite number between 0 and 1.")


def _validate_axis_unit_check_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic axis_unit for '{column}' must be a mapping.")
        return
    for key in ("data_unit", "display_unit"):
        value = raw_check.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Semantic axis_unit.{key} for '{column}' must be a non-empty string.")


def _validate_monotonic_within_group_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic monotonic_within_group for '{column}' must be a mapping.")
        return
    group_by = raw_check.get("group_by")
    if not isinstance(group_by, list) or not group_by:
        errors.append(f"Semantic monotonic_within_group.group_by for '{column}' must be a non-empty list.")
    elif any(not isinstance(item, str) or not item.strip() for item in group_by):
        errors.append(f"Semantic monotonic_within_group.group_by for '{column}' must contain only non-empty strings.")
    mode = raw_check.get("mode")
    if not isinstance(mode, str) or mode not in ALLOWED_MONOTONIC_MODES:
        allowed = ", ".join(sorted(ALLOWED_MONOTONIC_MODES))
        errors.append(f"Semantic monotonic_within_group.mode for '{column}' must be one of: {allowed}.")


def _validate_expected_sample_count_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic expected_sample_count for '{column}' must be a mapping.")
        return
    group_by = raw_check.get("group_by")
    if not isinstance(group_by, list) or not group_by:
        errors.append(f"Semantic expected_sample_count.group_by for '{column}' must be a non-empty list.")
    elif any(not isinstance(item, str) or not item.strip() for item in group_by):
        errors.append(f"Semantic expected_sample_count.group_by for '{column}' must contain only non-empty strings.")
    has_count = "count" in raw_check
    has_range = "range" in raw_check
    if has_count == has_range:
        errors.append(f"Semantic expected_sample_count for '{column}' must specify exactly one of count or range.")
    if has_count:
        count = raw_check.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            errors.append(f"Semantic expected_sample_count.count for '{column}' must be a positive integer.")
    if has_range:
        count_range = raw_check.get("range")
        if (
            not isinstance(count_range, list)
            or len(count_range) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in count_range)
        ):
            errors.append(
                f"Semantic expected_sample_count.range for '{column}' must be [min_count, max_count] positive integers."
            )
        elif count_range[0] > count_range[1]:
            errors.append(f"Semantic expected_sample_count.range for '{column}' must have min_count <= max_count.")


def _validate_unit_coherence_config(errors, *, column: str, raw_check: object) -> None:
    if not isinstance(raw_check, dict):
        errors.append(f"Semantic unit_coherence for '{column}' must be a mapping.")
        return
    expected_unit = raw_check.get("expected_unit")
    if not isinstance(expected_unit, str) or not expected_unit.strip():
        errors.append(f"Semantic unit_coherence.expected_unit for '{column}' must be a non-empty string.")
    terms = raw_check.get("terms")
    if not isinstance(terms, list) or not terms:
        errors.append(f"Semantic unit_coherence.terms for '{column}' must be a non-empty list.")
        return
    for idx, term in enumerate(terms, 1):
        if not isinstance(term, dict):
            errors.append(f"Semantic unit_coherence.terms[{idx}] for '{column}' must be a mapping.")
            continue
        for key in ("column", "unit"):
            value = term.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"Semantic unit_coherence.terms[{idx}].{key} for '{column}' must be a non-empty string.")
        exponent = term.get("exponent", 1)
        if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent == 0:
            errors.append(f"Semantic unit_coherence.terms[{idx}].exponent for '{column}' must be a non-zero integer.")


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


def project_role(config):
    project = config.get("project") if isinstance(config, dict) else {}
    if not isinstance(project, dict):
        return DEFAULT_PROJECT_ROLE
    role = project.get("role", DEFAULT_PROJECT_ROLE)
    if not isinstance(role, str):
        return DEFAULT_PROJECT_ROLE
    role = role.strip().lower()
    return role if role else DEFAULT_PROJECT_ROLE


def project_modules(config):
    modules = config.get("modules", []) if isinstance(config, dict) else []
    if not isinstance(modules, list):
        return []
    return [str(module).strip() for module in modules if isinstance(module, str) and module.strip()]


def master_execution_error(config):
    modules = project_modules(config)
    module_list = ", ".join(modules) if modules else "none declared"
    return f"This is a master project root, not an execution module — enter one of its modules: [{module_list}]"


def normalize_project_defaults(config):
    if not isinstance(config, dict):
        return config
    project = config.get("project")
    if isinstance(project, dict):
        if "role" not in project:
            project["role"] = DEFAULT_PROJECT_ROLE
        elif isinstance(project.get("role"), str):
            project["role"] = project["role"].strip().lower()
    return config


def _load_project_metadata(config_path, fallback_name):
    metadata = {
        "name": fallback_name,
        "role": DEFAULT_PROJECT_ROLE,
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
        version = str(schema_version)
        try:
            version_key = _schema_version_key(version)
            current_key = _schema_version_key(CURRENT_CONFIG_SCHEMA_VERSION)
        except ConfigMigrationError as exc:
            errors.append(str(exc))
        else:
            if version_key > current_key:
                errors.append(
                    f"schema_version '{schema_version}' is newer than this Graph Hub runtime supports "
                    f"('{CURRENT_CONFIG_SCHEMA_VERSION}'). Upgrade Graph Hub before loading this config."
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

    if role == "master":
        pipeline = config.get("pipeline", {})
        has_pipeline = isinstance(pipeline, dict) and any(bool(pipeline.get(key)) for key in ("analysis",))
        if has_pipeline:
            errors.append("project.role 'master' must not define pipeline analysis steps; use execution modules.")
        if config.get("figures"):
            errors.append("project.role 'master' must not define figures; use execution modules.")
        if config.get("diagrams"):
            errors.append("project.role 'master' must not define diagrams; use execution modules.")

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

    _validate_visual_outputs(
        errors,
        config.get("figures", []),
        section_name="figures",
        norm_policy=norm_policy,
        preset_names=preset_names,
    )
    _validate_visual_outputs(
        errors,
        config.get("diagrams", []),
        section_name="diagrams",
        norm_policy=norm_policy,
        preset_names=preset_names,
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

                semantic_checks = check.get("semantic_checks", {})
                if semantic_checks is not None and not isinstance(semantic_checks, dict):
                    errors.append(f"data_contract.csv_checks[{i}].semantic_checks must be a mapping.")
                elif semantic_checks:
                    for col, constraints in semantic_checks.items():
                        if not isinstance(constraints, dict):
                            errors.append(f"Semantic constraints for '{col}' must be a mapping.")
                            continue
                        if "range" in constraints:
                            r = constraints["range"]
                            if not isinstance(r, list) or len(r) != 2:
                                errors.append(f"Semantic range for '{col}' must be a list of 2 numbers.")
                            elif any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in r):
                                errors.append(f"Semantic range for '{col}' must contain only numeric bounds.")
                            elif r[0] > r[1]:
                                errors.append(f"Semantic range for '{col}' min must be <= max.")
                        if "allow_null" in constraints and not isinstance(constraints["allow_null"], bool):
                            errors.append(f"Semantic allow_null for '{col}' must be a boolean.")
                        if "unique" in constraints and not isinstance(constraints["unique"], bool):
                            errors.append(f"Semantic unique for '{col}' must be a boolean.")
                        if "monotonic" in constraints:
                            monotonic_mode = constraints["monotonic"]
                            if not isinstance(monotonic_mode, str) or monotonic_mode not in ALLOWED_MONOTONIC_MODES:
                                allowed = ", ".join(sorted(ALLOWED_MONOTONIC_MODES))
                                errors.append(
                                    f"Semantic monotonic for '{col}' must be one of: {allowed}. Got '{monotonic_mode}'."
                                )
                        if "monotonic_within_group" in constraints:
                            _validate_monotonic_within_group_config(
                                errors,
                                column=str(col),
                                raw_check=constraints["monotonic_within_group"],
                            )
                        if "min_replicates" in constraints:
                            _validate_grouped_check_config(
                                errors,
                                column=str(col),
                                check_name="min_replicates",
                                raw_check=constraints["min_replicates"],
                            )
                        if "expected_sample_count" in constraints:
                            _validate_expected_sample_count_config(
                                errors,
                                column=str(col),
                                raw_check=constraints["expected_sample_count"],
                            )
                        if "grouped_cv" in constraints:
                            _validate_grouped_check_config(
                                errors,
                                column=str(col),
                                check_name="grouped_cv",
                                raw_check=constraints["grouped_cv"],
                            )
                        if "log_scale_positive" in constraints and not isinstance(
                            constraints["log_scale_positive"], bool
                        ):
                            errors.append(f"Semantic log_scale_positive for '{col}' must be a boolean.")
                        if "error_bar_source" in constraints:
                            _validate_errorbar_check_config(
                                errors,
                                column=str(col),
                                raw_check=constraints["error_bar_source"],
                            )
                        if "mean_sem" in constraints:
                            _validate_mean_sem_check_config(
                                errors,
                                column=str(col),
                                raw_check=constraints["mean_sem"],
                            )
                        if "linear_fit" in constraints:
                            _validate_linear_fit_check_config(
                                errors,
                                column=str(col),
                                raw_check=constraints["linear_fit"],
                            )
                        if "outlier_flag" in constraints:
                            _validate_outlier_flag_check_config(
                                errors,
                                column=str(col),
                                raw_check=constraints["outlier_flag"],
                            )
                        if "axis_unit" in constraints:
                            _validate_axis_unit_check_config(
                                errors,
                                column=str(col),
                                raw_check=constraints["axis_unit"],
                            )
                        if "unit_coherence" in constraints:
                            _validate_unit_coherence_config(
                                errors,
                                column=str(col),
                                raw_check=constraints["unit_coherence"],
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

    assemblies = config.get("assemblies", {})
    if assemblies is not None:
        if not isinstance(assemblies, dict):
            errors.append("Invalid 'assemblies' section (must be a mapping).")
        else:
            for fig_id, fig_cfg in assemblies.items():
                if not isinstance(fig_cfg, dict):
                    errors.append(f"assemblies.{fig_id} must be a mapping.")
                    continue

                tw = fig_cfg.get("target_width_mm")
                if tw is None:
                    errors.append(f"assemblies.{fig_id}.target_width_mm is required.")
                elif not isinstance(tw, (int, float)) or tw <= 0:
                    errors.append(f"assemblies.{fig_id}.target_width_mm must be a positive number.")

                gap = fig_cfg.get("gap_mm", 3)
                if not isinstance(gap, (int, float)) or gap < 0:
                    errors.append(f"assemblies.{fig_id}.gap_mm must be a non-negative number.")

                layout = fig_cfg.get("layout")
                if not isinstance(layout, str) or not layout.strip():
                    errors.append(f"assemblies.{fig_id}.layout is required (mosaic string).")
                else:
                    rows = [list(r) for r in layout.strip().splitlines() if r.strip()]
                    if rows:
                        row_len = len(rows[0])
                        for ri, row in enumerate(rows):
                            if len(row) != row_len:
                                errors.append(
                                    f"assemblies.{fig_id}.layout row {ri + 1} has {len(row)} cols, expected {row_len}."
                                )

                        # Validate contiguous rectangles
                        chars: dict[str, list[tuple[int, int]]] = {}
                        for ri, row in enumerate(rows):
                            for ci, ch in enumerate(row):
                                if ch != ".":
                                    chars.setdefault(ch, []).append((ri, ci))
                        for ch, cells in chars.items():
                            rows_set = {r for r, _ in cells}
                            cols_set = {c for _, c in cells}
                            if len(cells) != len(rows_set) * len(cols_set):
                                errors.append(
                                    f"assemblies.{fig_id}.layout: character '{ch}' "
                                    f"does not form a contiguous rectangle."
                                )

                # Validate row_height_ratios length
                rhr = fig_cfg.get("row_height_ratios")
                if rhr is not None:
                    if not isinstance(rhr, list):
                        errors.append(f"assemblies.{fig_id}.row_height_ratios must be a list.")
                    elif isinstance(layout, str) and layout.strip():
                        n_layout_rows = len([r for r in layout.strip().splitlines() if r.strip()])
                        if len(rhr) != n_layout_rows:
                            errors.append(
                                f"assemblies.{fig_id}.row_height_ratios has {len(rhr)} entries "
                                f"but layout has {n_layout_rows} rows."
                            )

                panels = fig_cfg.get("panels", {})
                if not isinstance(panels, dict):
                    errors.append(f"assemblies.{fig_id}.panels must be a mapping.")
                else:
                    for pid, p_cfg in panels.items():
                        if not isinstance(p_cfg, dict):
                            errors.append(f"assemblies.{fig_id}.panels.{pid} must be a mapping.")
                            continue
                        if "source" not in p_cfg or not isinstance(p_cfg["source"], str):
                            errors.append(f"assemblies.{fig_id}.panels.{pid}.source is required (string).")
                        else:
                            src = p_cfg["source"]
                            if os.path.isabs(src):
                                errors.append(
                                    f"assemblies.{fig_id}.panels.{pid}.source: absolute paths are not allowed."
                                )
                            elif ".." in src.replace("\\", "/").split("/"):
                                errors.append(
                                    f"assemblies.{fig_id}.panels.{pid}.source: path traversal '..' is not allowed."
                                )
                        fs = p_cfg.get("font_strategy", "compensate")
                        if fs not in ALLOWED_FONT_STRATEGIES:
                            allowed = ", ".join(sorted(ALLOWED_FONT_STRATEGIES))
                            errors.append(f"assemblies.{fig_id}.panels.{pid}.font_strategy must be one of: {allowed}.")

                    # Cross-check: layout characters vs panel keys
                    if isinstance(layout, str) and layout.strip():
                        layout_chars = {ch for row in rows for ch in row if ch != "."}
                        panel_keys = set(panels.keys())
                        missing_panels = layout_chars - panel_keys
                        extra_panels = panel_keys - layout_chars
                        if missing_panels:
                            errors.append(
                                f"assemblies.{fig_id}: layout references "
                                f"{sorted(missing_panels)} but panels section is missing them."
                            )
                        if extra_panels:
                            errors.append(
                                f"assemblies.{fig_id}: panels {sorted(extra_panels)} are not referenced in layout."
                            )

    return errors


def _validate_sweep(sweep: dict) -> list[str]:
    errors: list[str] = []

    if not isinstance(sweep, dict):
        errors.append("sweep must be a mapping.")
        return errors

    enabled = sweep.get("enabled", False)
    if not isinstance(enabled, bool):
        errors.append("sweep.enabled must be a boolean.")

    has_values = "values" in sweep
    has_grid = "grid" in sweep

    if has_values and has_grid:
        errors.append("sweep: specify either 'values' or 'grid', not both.")

    if has_values:
        parameter = sweep.get("parameter")
        if not isinstance(parameter, str) or not parameter.strip():
            errors.append("sweep.parameter is required and must be a non-empty string when 'values' is used.")
        values = sweep.get("values")
        if not isinstance(values, list) or len(values) == 0:
            errors.append("sweep.values must be a non-empty list.")
        elif any(not isinstance(v, (int, float, str)) for v in values):
            errors.append("sweep.values entries must be numbers or strings.")

    if has_grid:
        grid = sweep.get("grid")
        if not isinstance(grid, dict) or len(grid) == 0:
            errors.append("sweep.grid must be a non-empty mapping.")
        else:
            for param_name, param_values in grid.items():
                if not isinstance(param_name, str) or not param_name.strip():
                    errors.append("sweep.grid keys must be non-empty strings.")
                if not isinstance(param_values, list) or len(param_values) == 0:
                    errors.append(f"sweep.grid.{param_name} must be a non-empty list.")
                elif any(not isinstance(v, (int, float, str)) for v in param_values):
                    errors.append(f"sweep.grid.{param_name} entries must be numbers or strings.")

    output_dir_pattern = sweep.get("output_dir_pattern")
    if output_dir_pattern is not None:
        if not isinstance(output_dir_pattern, str) or not output_dir_pattern.strip():
            errors.append("sweep.output_dir_pattern must be a non-empty string.")

    return errors


def _validate_comparison(comparison: dict) -> list[str]:
    errors: list[str] = []

    if not isinstance(comparison, dict):
        errors.append("comparison must be a mapping.")
        return errors

    enabled = comparison.get("enabled", False)
    if not isinstance(enabled, bool):
        errors.append("comparison.enabled must be a boolean.")

    conditions = comparison.get("conditions", [])
    if conditions is None:
        conditions = []
    if not isinstance(conditions, list):
        errors.append("comparison.conditions must be a list.")
    else:
        for i, cond in enumerate(conditions, 1):
            if not isinstance(cond, dict):
                errors.append(f"comparison.conditions[{i}] must be a mapping.")
                continue
            label = cond.get("label")
            if not isinstance(label, str) or not label.strip():
                errors.append(f"comparison.conditions[{i}].label is required and must be a non-empty string.")
            data_override = cond.get("data_override")
            if data_override is not None:
                if not isinstance(data_override, str) or not data_override.strip():
                    errors.append(f"comparison.conditions[{i}].data_override must be a non-empty string.")
                elif os.path.isabs(data_override):
                    errors.append(
                        f"comparison.conditions[{i}].data_override must be a relative path, "
                        f"got absolute: '{data_override}'."
                    )
                elif ".." in data_override.replace("\\", "/").split("/"):
                    errors.append(
                        f"comparison.conditions[{i}].data_override contains path traversal '..': '{data_override}'."
                    )
            env = cond.get("env", {})
            if env is not None and not isinstance(env, dict):
                errors.append(f"comparison.conditions[{i}].env must be a mapping.")
            elif isinstance(env, dict):
                for key, val in env.items():
                    if not isinstance(key, str):
                        errors.append(f"comparison.conditions[{i}].env keys must be strings.")
                    if not isinstance(val, (str, int, float, bool)):
                        errors.append(
                            f"comparison.conditions[{i}].env.{key} value must be a scalar (str/int/float/bool)."
                        )

    overlay_output = comparison.get("overlay_output")
    if overlay_output is not None:
        if not isinstance(overlay_output, str) or not overlay_output.strip():
            errors.append("comparison.overlay_output must be a non-empty string.")
        elif os.path.isabs(overlay_output):
            errors.append("comparison.overlay_output must be a relative path.")
        elif ".." in overlay_output.replace("\\", "/").split("/"):
            errors.append("comparison.overlay_output contains path traversal '..'.")

    return errors


def parse_comparison_config(comparison: dict) -> dict:
    """Return a normalized comparison config with a flat list of condition dicts."""
    enabled = bool(comparison.get("enabled", False))
    conditions: list[dict] = []
    for cond in comparison.get("conditions", []) or []:
        conditions.append(
            {
                "label": str(cond.get("label", "")).strip(),
                "data_override": cond.get("data_override"),
                "env": {str(k): str(v) for k, v in (cond.get("env") or {}).items()},
            }
        )
    overlay_output: str | None = comparison.get("overlay_output")
    return {
        "enabled": enabled,
        "conditions": conditions,
        "overlay_output": overlay_output,
    }


def parse_sweep_config(sweep: dict) -> dict:
    """Return a normalized sweep config with a flat list of (env_var, value) runs."""
    enabled = bool(sweep.get("enabled", False))
    output_dir_pattern = sweep.get("output_dir_pattern", "results/figures/sweep_{parameter}_{value}")

    runs: list[dict[str, str]] = []

    if "values" in sweep:
        parameter = sweep["parameter"].strip()
        for value in sweep["values"]:
            runs.append({parameter: str(value)})
    elif "grid" in sweep:
        grid = sweep["grid"]
        import itertools

        param_names = list(grid.keys())
        param_value_lists = [grid[k] for k in param_names]
        for combo in itertools.product(*param_value_lists):
            runs.append({name: str(val) for name, val in zip(param_names, combo)})

    return {
        "enabled": enabled,
        "output_dir_pattern": output_dir_pattern,
        "runs": runs,
    }


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
        script = item.get("script")
        output = item.get("output")
        lang = normalize_lang(item.get("lang"))

        if lang != "athena":
            if not isinstance(script, str) or not script.strip():
                errors.append(f"{section_name}[{i}].script is required.")

        if not isinstance(output, str) or not output.strip():
            errors.append(f"{section_name}[{i}].output is required for output verification.")
        inputs = item.get("inputs", None)
        if inputs is not None and not isinstance(inputs, list):
            errors.append(f"{section_name}[{i}].inputs must be a list.")
        elif isinstance(inputs, list):
            for inp in inputs:
                if isinstance(inp, str):
                    if os.path.isabs(inp):
                        errors.append(f"{section_name}[{i}].inputs: absolute path '{inp}' is not allowed.")
                    elif ".." in inp.replace("\\", "/").split("/"):
                        errors.append(f"{section_name}[{i}].inputs: path traversal '..' in '{inp}' is not allowed.")
        if "cache" in item and not isinstance(item.get("cache"), bool):
            errors.append(f"{section_name}[{i}].cache must be a boolean.")
        if "theme" in item:
            theme = item.get("theme")
            if not isinstance(theme, str) or theme.strip().lower() not in ALLOWED_TARGET_FORMATS:
                allowed = ", ".join(sorted(ALLOWED_TARGET_FORMATS))
                errors.append(f"{section_name}[{i}].theme must be one of: {allowed}.")
        if "format" in item:
            output_format = item.get("format")
            if not isinstance(output_format, str) or output_format.strip().lower() not in ALLOWED_OUTPUT_FORMATS:
                allowed = ", ".join(sorted(ALLOWED_OUTPUT_FORMATS))
                errors.append(f"{section_name}[{i}].format must be one of: {allowed}.")
        if preset_names is not None and "preset" in item:
            item_preset = item.get("preset")
            if item_preset not in preset_names:
                errors.append(f"{section_name}[{i}].preset '{item_preset}' references an undefined preset.")
        expand = item.get("expand")
        if expand is not None and expand not in ("batch", "each"):
            errors.append(f"{section_name}[{i}].expand must be 'batch' or 'each'.")
        if expand == "each" and isinstance(output, str) and "{stem}" not in output:
            errors.append(f"{section_name}[{i}].output must contain '{{stem}}' placeholder when expand='each'.")
        if not norm_policy["allow_nonstandard"] and isinstance(script, str) and script.strip():
            item_lang = normalize_lang(item.get("lang"))
            if not item_lang:
                item_lang = "r" if script.lower().endswith(".r") else "python"
            if item_lang != norm_policy["plot_lang"]:
                errors.append(
                    f"{section_name}[{i}] language '{item_lang}' violates policy "
                    f"(plot must be '{norm_policy['plot_lang']}')."
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

    discovered = discover_projects_with_status(root_dir, max_depth=max_depth)
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
                project.get("classification", "-"),
                project.get("target_format", "-"),
                _resolve_operational_state(operational_states, project["path"]),
                status_text,
            ]
        )

    ui_table(
        title=f"🏛️ Research Projects (depth <= {max_depth})",
        columns=["Project Name", "Path", "Role", "Class", "Style", "Op State", "Status"],
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
    from .project_discovery import get_discoverable_projects as _get_discoverable_projects

    return _get_discoverable_projects(root_dir, max_depth=max_depth)
