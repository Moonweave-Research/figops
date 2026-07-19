"""Research metadata and relative-path config validators."""

from __future__ import annotations

import os

from .project_paths import ProjectPathError, normalize_project_relative_path


def validate_experimental_conditions(errors: list[str], experimental_conditions: object) -> None:
    if experimental_conditions is None:
        return
    if not isinstance(experimental_conditions, dict):
        errors.append("experimental_conditions must be a mapping.")
        return

    common = experimental_conditions.get("common", {})
    if common is not None and not isinstance(common, dict):
        errors.append("experimental_conditions.common must be a mapping when provided.")

    conditions = experimental_conditions.get("conditions", [])
    seen_condition_ids: set[str] = set()
    if conditions is None:
        conditions = []
    if not isinstance(conditions, list):
        errors.append("experimental_conditions.conditions must be a list when provided.")
    else:
        for index, condition in enumerate(conditions, 1):
            if not isinstance(condition, dict):
                errors.append(f"experimental_conditions.conditions[{index}] must be a mapping.")
                continue
            condition_id = condition.get("id")
            if not isinstance(condition_id, str) or not condition_id.strip():
                errors.append(
                    f"experimental_conditions.conditions[{index}].id is required and must be a non-empty string."
                )
            else:
                normalized_id = condition_id.strip()
                if normalized_id in seen_condition_ids:
                    errors.append(f"Duplicate experimental_conditions.conditions id: '{normalized_id}'.")
                seen_condition_ids.add(normalized_id)

            description = condition.get("description")
            if description is not None and not isinstance(description, str):
                errors.append(f"experimental_conditions.conditions[{index}].description must be a string.")

            parameters = condition.get("parameters", {})
            if parameters is not None and not isinstance(parameters, dict):
                errors.append(
                    f"experimental_conditions.conditions[{index}].parameters must be a mapping when provided."
                )
                continue
            if isinstance(parameters, dict):
                samples = parameters.get("samples")
                if samples is not None and not isinstance(samples, list):
                    errors.append(f"experimental_conditions.conditions[{index}].parameters.samples must be a list.")
                batch = parameters.get("batch")
                if batch is not None and not isinstance(batch, str):
                    errors.append(f"experimental_conditions.conditions[{index}].parameters.batch must be a string.")

    equipment = experimental_conditions.get("equipment", [])
    if equipment is None:
        equipment = []
    if not isinstance(equipment, list):
        errors.append("experimental_conditions.equipment must be a list when provided.")
    else:
        for index, item in enumerate(equipment, 1):
            if not isinstance(item, dict):
                errors.append(f"experimental_conditions.equipment[{index}] must be a mapping.")
                continue
            name = item.get("name")
            if name is not None and not isinstance(name, str):
                errors.append(f"experimental_conditions.equipment[{index}].name must be a string.")
            role = item.get("role")
            if role is not None and not isinstance(role, str):
                errors.append(f"experimental_conditions.equipment[{index}].role must be a string.")


def validate_sample_registry(errors: list[str], sample_registry: object) -> set[str] | None:
    if sample_registry is None:
        return None
    if not isinstance(sample_registry, list):
        errors.append("sample_registry must be a list when provided.")
        return set()

    sample_ids: set[str] = set()
    for index, sample in enumerate(sample_registry, 1):
        if not isinstance(sample, dict):
            errors.append(f"sample_registry[{index}] must be a mapping.")
            continue

        sample_id = sample.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id.strip():
            errors.append(f"sample_registry[{index}].sample_id is required and must be a non-empty string.")
        else:
            normalized_id = sample_id.strip()
            if normalized_id in sample_ids:
                errors.append(f"Duplicate sample_registry sample_id: '{normalized_id}'.")
            sample_ids.add(normalized_id)

        composition = sample.get("composition")
        if composition is not None and (
            isinstance(composition, bool) or not isinstance(composition, (str, int, float))
        ):
            errors.append(f"sample_registry[{index}].composition must be a string or number.")

        for key in ("material", "batch", "fabrication_date", "status", "notes"):
            value = sample.get(key)
            if value is not None and not isinstance(value, str):
                errors.append(f"sample_registry[{index}].{key} must be a string.")

        raw_paths = sample.get("raw_paths")
        if raw_paths is None:
            continue
        if not isinstance(raw_paths, list):
            errors.append(f"sample_registry[{index}].raw_paths must be a list when provided.")
            continue
        for path_index, raw_path in enumerate(raw_paths, 1):
            if not isinstance(raw_path, str) or not raw_path.strip():
                errors.append(f"sample_registry[{index}].raw_paths[{path_index}] must be a non-empty relative path.")
                continue
            if os.path.isabs(raw_path):
                errors.append(
                    f"sample_registry[{index}].raw_paths[{path_index}] must be a relative path; "
                    "absolute path is not allowed."
                )
            elif ".." in raw_path.replace("\\", "/").split("/"):
                errors.append(f"sample_registry[{index}].raw_paths[{path_index}] must not contain path traversal '..'.")

    return sample_ids


def condition_sample_references(experimental_conditions: object) -> set[str]:
    if not isinstance(experimental_conditions, dict):
        return set()
    conditions = experimental_conditions.get("conditions", [])
    if not isinstance(conditions, list):
        return set()

    sample_refs: set[str] = set()
    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        parameters = condition.get("parameters", {})
        if not isinstance(parameters, dict):
            continue
        samples = parameters.get("samples", [])
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if isinstance(sample, str) and sample.strip():
                sample_refs.add(sample.strip())
    return sample_refs


def validate_raw_integrity_config(
    errors: list[str], raw_integrity: object, *, allowed_modes: set[str]
) -> None:
    if raw_integrity is None:
        return
    if not isinstance(raw_integrity, dict):
        errors.append("data_contract.raw_integrity must be a mapping when provided.")
        return

    manifest = raw_integrity.get("manifest", "raw/.raw_manifest.json")
    if not isinstance(manifest, str) or not manifest.strip():
        errors.append("data_contract.raw_integrity.manifest must be a non-empty relative path.")
    else:
        validate_relative_path_value(errors, "data_contract.raw_integrity.manifest", manifest)

    mode = raw_integrity.get("mode", "warn")
    if not isinstance(mode, str) or mode.strip().lower() not in allowed_modes:
        allowed = ", ".join(sorted(allowed_modes))
        errors.append(f"data_contract.raw_integrity.mode must be one of: {allowed}.")

    paths = raw_integrity.get("paths", ["raw/"])
    if paths is None:
        paths = ["raw/"]
    if not isinstance(paths, list):
        errors.append("data_contract.raw_integrity.paths must be a list of relative paths when provided.")
        return
    for index, path in enumerate(paths, 1):
        if not isinstance(path, str) or not path.strip():
            errors.append(f"data_contract.raw_integrity.paths[{index}] must be a non-empty relative path.")
            continue
        validate_relative_path_value(errors, f"data_contract.raw_integrity.paths[{index}]", path)

    no_raw_inputs = raw_integrity.get("no_raw_inputs")
    if no_raw_inputs is None:
        return
    if not isinstance(no_raw_inputs, dict):
        errors.append("data_contract.raw_integrity.no_raw_inputs must be a typed mapping.")
        return
    extra = set(no_raw_inputs) - {"type", "reason"}
    if extra:
        errors.append(
            "data_contract.raw_integrity.no_raw_inputs contains unsupported fields: "
            f"{', '.join(sorted(extra))}."
        )
    if no_raw_inputs.get("type") != "no_raw_inputs":
        errors.append("data_contract.raw_integrity.no_raw_inputs.type must equal 'no_raw_inputs'.")
    reason = no_raw_inputs.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        errors.append("data_contract.raw_integrity.no_raw_inputs.reason must be a non-empty string.")


def validate_relative_path_value(errors: list[str], field_name: str, path: str) -> None:
    try:
        normalize_project_relative_path(path, purpose=field_name)
    except ProjectPathError as exc:
        errors.append(str(exc))


def validate_canonical_docs(errors: list[str], canonical_docs: object) -> None:
    if canonical_docs is None:
        return
    if not isinstance(canonical_docs, list):
        errors.append("canonical_docs must be an ordered list when provided.")
        return

    seen_paths: set[str] = set()
    for index, item in enumerate(canonical_docs, 1):
        field_name = f"canonical_docs[{index}].path"
        label: object = None
        if isinstance(item, str):
            path = item
        elif isinstance(item, dict):
            path = item.get("path")
            label = item.get("label")
        else:
            errors.append(f"canonical_docs[{index}] must be a relative path string or a mapping with path.")
            continue

        if not isinstance(path, str) or not path.strip():
            errors.append(f"{field_name} must be a non-empty relative path.")
            continue
        validate_relative_path_value(errors, field_name, path)
        if label is not None and not isinstance(label, str):
            errors.append(f"canonical_docs[{index}].label must be a string when provided.")

        normalized_path = path.strip().replace("\\", "/").strip("/")
        if normalized_path in seen_paths:
            errors.append(f"Duplicate canonical_docs path: '{normalized_path}'.")
        seen_paths.add(normalized_path)


def experimental_condition_ids(experimental_conditions: object) -> set[str] | None:
    if not isinstance(experimental_conditions, dict) or "conditions" not in experimental_conditions:
        return None
    conditions = experimental_conditions.get("conditions", [])
    if not isinstance(conditions, list):
        return set()
    return {
        condition["id"].strip()
        for condition in conditions
        if isinstance(condition, dict) and isinstance(condition.get("id"), str) and condition["id"].strip()
    }
