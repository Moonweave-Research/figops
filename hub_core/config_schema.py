"""Schema-version and YAML-loading helpers for project configuration."""

from __future__ import annotations

from copy import deepcopy

import yaml

LEGACY_CONFIG_SCHEMA_VERSION = "1.0"
CURRENT_CONFIG_SCHEMA_VERSION = "1.1"
SUPPORTED_CONFIG_SCHEMA_VERSIONS = ("0.9", LEGACY_CONFIG_SCHEMA_VERSION, CURRENT_CONFIG_SCHEMA_VERSION)


class ConfigMigrationError(ValueError):
    """Raised when a config schema cannot be migrated by this runtime."""


class ConfigVersionTooNewError(ConfigMigrationError):
    """Raised when a config declares a schema newer than this runtime."""


class UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def construct_mapping_no_duplicates(loader, node, deep=False):
    loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.YAMLError(f"Duplicate key '{key}' at line {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_mapping_no_duplicates,
)


def load_yaml_with_unique_keys(raw_text: str):
    return yaml.load(raw_text, Loader=UniqueKeySafeLoader)


def schema_version_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(version).split("."))
    except ValueError as exc:
        raise ConfigMigrationError(f"schema_version '{version}' must use numeric dot-separated segments.") from exc


def schema_version(config: dict) -> str:
    # A schema-less document predates the additive v1.1 contract.  Treat it as
    # v1.0 and advance only the detached, in-memory mapping returned by
    # ``migrate_config``; loading must never rewrite the project file.
    raw_version = config.get("schema_version", LEGACY_CONFIG_SCHEMA_VERSION)
    if raw_version is None:
        return LEGACY_CONFIG_SCHEMA_VERSION
    return str(raw_version)


def migrate_0_9_to_1_0(config: dict) -> dict:
    migrated = deepcopy(config)
    migrated["schema_version"] = LEGACY_CONFIG_SCHEMA_VERSION
    return migrated


def migrate_1_0_to_1_1(config: dict) -> dict:
    """Advance config syntax without inventing an explicit structure layout."""

    migrated = deepcopy(config)
    migrated["schema_version"] = CURRENT_CONFIG_SCHEMA_VERSION
    return migrated


CONFIG_MIGRATIONS = {
    "0.9": migrate_0_9_to_1_0,
    LEGACY_CONFIG_SCHEMA_VERSION: migrate_1_0_to_1_1,
}


def migrate_config(config):
    """Return a config migrated to the current schema version."""
    if not isinstance(config, dict):
        return config

    migrated = deepcopy(config)
    version = schema_version(migrated)
    current_key = schema_version_key(CURRENT_CONFIG_SCHEMA_VERSION)

    if schema_version_key(version) > current_key:
        raise ConfigVersionTooNewError(
            f"project_config.yaml schema_version '{version}' is newer than this FigOps runtime supports "
            f"('{CURRENT_CONFIG_SCHEMA_VERSION}'). Upgrade FigOps before loading this config."
        )

    while version != CURRENT_CONFIG_SCHEMA_VERSION:
        migration = CONFIG_MIGRATIONS.get(version)
        if migration is None:
            supported = ", ".join(SUPPORTED_CONFIG_SCHEMA_VERSIONS)
            raise ConfigMigrationError(
                f"project_config.yaml schema_version '{version}' is not supported by this FigOps runtime. "
                f"Supported versions: {supported}."
            )
        migrated = migration(migrated)
        next_version = schema_version(migrated)
        if next_version == version:
            raise ConfigMigrationError(f"Config migration for schema_version '{version}' did not advance.")
        version = next_version

    migrated["schema_version"] = CURRENT_CONFIG_SCHEMA_VERSION
    return migrated
