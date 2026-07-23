"""Pure canonical policy resolution for figure-integrity policy inputs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from .config_style import ALLOWED_TARGET_FORMATS
from .policy_resolution_json import (
    PolicyResolutionError as PolicyResolutionError,
)
from .policy_resolution_json import (
    closed,
    fail,
    finite_number,
    normalize_json_value,
    parse_json_array,
    set_value,
    sha256,
    token,
)
from .policy_resolution_types import (
    PolicyConstraint,
    PolicyException,
    ResolvedPolicySet,
    ResolvedPolicyValue,
    jsonable,
)

SCHEMA_VERSION: Final = "figops-resolved-policy-set/1"
POLICY_VERSION: Final = "1"
LAYER_ORDER: Final = ("kernel", "operator", "lab", "project", "render")
PRECEDENCE: Final = {source: index for index, source in enumerate(LAYER_ORDER)}
MERGE_OPERATORS: Final = {"require", "minimum", "maximum", "allowed_set", "exact", "selection"}
JOURNAL_TARGETS: Final = tuple(sorted(ALLOWED_TARGET_FORMATS - {"neutral", "default", "ppt"}))
KERNEL_INVARIANTS: Final = frozenset(
    {
        "path_containment",
        "schema_receipt_integrity",
        "runtime_result_disjointness",
        "no_replace_promotion",
    }
)
_MISSING = object()


@dataclass(frozen=True, slots=True)
class _ParamSchema:
    operator: str
    default: Any = None
    allowed: tuple[Any, ...] = ()
    opt_out_allowed: bool = False
    waivable: bool = False


PARAMETER_SCHEMAS: Final = {
    "path_containment": _ParamSchema("require", True),
    "schema_receipt_integrity": _ParamSchema("require", True),
    "runtime_result_disjointness": _ParamSchema("require", True),
    "no_replace_promotion": _ParamSchema("require", True),
    "human_signoff_required": _ParamSchema("require", False),
    "render_policy": _ParamSchema("selection", "neutral", tuple(sorted(ALLOWED_TARGET_FORMATS))),
    "validation_target": _ParamSchema("selection", None, (None, *JOURNAL_TARGETS)),
    "minimum_raster_dpi": _ParamSchema("minimum", None),
    "maximum_physical_width_mm": _ParamSchema("maximum", None),
    "allowed_artifact_formats": _ParamSchema("allowed_set", None),
    "project_role": _ParamSchema("exact", None),
    "require_figure_traceability": _ParamSchema("require", True, opt_out_allowed=True, waivable=True),
    "require_canonical_docs": _ParamSchema("require", True, opt_out_allowed=True, waivable=True),
    "forbid_todo_placeholders": _ParamSchema("require", True, opt_out_allowed=True, waivable=True),
    "raw_integrity_mode": _ParamSchema("selection", "off", ("off", "warn", "strict")),
}


def resolve_policy_set(layers: Sequence[Mapping[str, Any]] | bytes | bytearray | memoryview) -> ResolvedPolicySet:
    constraints = {name: [] for name in PARAMETER_SCHEMAS}
    exceptions: dict[str, list[PolicyException]] = {name: [] for name in PARAMETER_SCHEMAS}
    opt_outs = dict.fromkeys(PARAMETER_SCHEMAS, False)
    seen_sources: set[str] = set()
    for layer in _parse_layers(layers):
        layer = closed(layer, {"source", "policy_id", "version", "parameters"}, "layer")
        source = _source(layer["source"], seen_sources)
        precedence = PRECEDENCE[source]
        policy_id = token(layer["policy_id"], "policy_id")
        version = _version(layer["version"])
        params = closed(layer["parameters"], set(PARAMETER_SCHEMAS), "parameters", subset=True)
        for name, raw in params.items():
            schema = PARAMETER_SCHEMAS[name]
            values, opt_out, found_exceptions = _parts(name, raw, schema)
            if name in KERNEL_INVARIANTS and any(value is False for value in values):
                fail(f"{name} immutable kernel invariant cannot be disabled")
            if opt_out and not schema.opt_out_allowed:
                fail(f"{name} does not allow opt-out")
            opt_outs[name] = opt_outs[name] or opt_out
            constraint_source = source
            if opt_out and not values:
                values = [False]
                constraint_source = _opt_out_source(source)
            constraints[name].extend(
                PolicyConstraint(constraint_source, precedence, policy_id, version, v) for v in values
            )
            exceptions[name].extend(
                PolicyException(source, policy_id, version, e["finding_code"], e.get("subject_digest"))
                for e in found_exceptions
            )
    resolved = (
        _resolve(name, PARAMETER_SCHEMAS[name], tuple(constraints[name]), opt_outs[name], tuple(exceptions[name]))
        for name in PARAMETER_SCHEMAS
    )
    return ResolvedPolicySet(SCHEMA_VERSION, tuple(sorted(resolved, key=lambda item: item.parameter)))


def compatibility_resolved_policy(policy_set: ResolvedPolicySet) -> dict[str, Any]:
    """Project the canonical set into the legacy singular ``resolved_policy`` shape."""

    render_policy = policy_set.value("render_policy").value
    target = policy_set.value("validation_target").value
    if target is None:
        parameters = {"style_policy": render_policy, "mutates_journal_aesthetics": render_policy != "neutral"}
        policy_id = f"render-{render_policy}"
    else:
        parameters = {"render_policy": f"render-{render_policy}", "validation_target": target}
        policy_id = f"journal-{target}"
    return {
        "id": policy_id,
        "version": POLICY_VERSION,
        "source": "policy-set-compatibility-projection",
        "parameters": parameters,
    }


def parse_policy_layers_json(data: bytes | bytearray | memoryview) -> tuple[dict[str, Any], ...]:
    return parse_json_array(data)


def _resolve(
    name: str,
    schema: _ParamSchema,
    constraints: tuple[PolicyConstraint, ...],
    opt_out: bool,
    exceptions: tuple[PolicyException, ...],
) -> ResolvedPolicyValue:
    values = [item.value for item in constraints]
    value = schema.default if not values else _merge(name, schema, values)
    if schema.operator == "require" and opt_out and not any(item.value is True for item in constraints):
        value = False
    selected = _selected(constraints, value)
    return ResolvedPolicyValue(
        name,
        jsonable(value),
        schema.operator,
        selected.source,
        selected.precedence,
        selected.policy_id,
        selected.version,
        opt_out,
        bool(opt_out and value is False),
        constraints,
        exceptions,
    )


def _merge(name: str, schema: _ParamSchema, values: list[Any]) -> Any:
    if schema.operator == "require":
        if not all(isinstance(item, bool) for item in values):
            fail(f"{name} require values must be boolean")
        return any(values)
    if schema.operator in {"minimum", "maximum"}:
        nums = [finite_number(item, name) for item in values]
        return max(nums) if schema.operator == "minimum" else min(nums)
    if schema.operator in {"allowed_set", "selection"}:
        return _merge_set_or_selection(name, schema, values)
    if len({json.dumps(jsonable(item), sort_keys=True) for item in values}) != 1:
        fail(f"{name} exact values conflict")
    return values[0]


def _merge_set_or_selection(name: str, schema: _ParamSchema, values: list[Any]) -> Any:
    allowed, selected = set(schema.allowed) if schema.allowed else None, _MISSING
    for item in values:
        candidate = set(item) if isinstance(item, tuple) else {item}
        allowed = candidate if allowed is None else allowed & candidate
        if not isinstance(item, tuple):
            selected = item
    if not allowed:
        fail(f"{name} has an empty allowed-set intersection")
    if schema.operator == "allowed_set":
        return tuple(sorted(allowed, key=lambda item: "" if item is None else str(item)))
    selection = schema.default if selected is _MISSING else selected
    if selection not in allowed:
        fail(f"{name} selection is outside the resolved allowed set")
    return selection


def _parts(name: str, raw: Any, schema: _ParamSchema) -> tuple[list[Any], bool, list[dict[str, str]]]:
    if not isinstance(raw, Mapping):
        return [_normalize_value(raw, name, schema)], False, []
    item = closed(raw, {"value", "allowed", "opt_out", "exceptions"}, name, subset=True)
    values = []
    if "opt_out" in item and not isinstance(item["opt_out"], bool):
        fail(f"{name}.opt_out must be boolean")
    if "allowed" in item:
        values.append(set_value(item["allowed"], name))
    if "value" in item:
        values.append(_normalize_value(item["value"], name, schema))
    exceptions = [_exception(exc, f"{name}.exceptions") for exc in item.get("exceptions", [])]
    return values, bool(item.get("opt_out", False)), exceptions


def _normalize_value(value: Any, name: str, schema: _ParamSchema) -> Any:
    if value is None:
        return None
    if schema.operator == "require" and not isinstance(value, bool):
        fail(f"{name} must be boolean")
    if schema.operator in {"minimum", "maximum"}:
        return finite_number(value, name)
    if schema.operator == "allowed_set":
        return set_value(value, name)
    value = normalize_json_value(value) if schema.operator in {"allowed_set", "selection", "exact"} else value
    if schema.allowed and value not in schema.allowed:
        fail(f"{name} has unsupported value {value!r}")
    return value


def _parse_layers(
    layers: Sequence[Mapping[str, Any]] | bytes | bytearray | memoryview,
) -> tuple[Mapping[str, Any], ...]:
    if isinstance(layers, (bytes, bytearray, memoryview)):
        return parse_json_array(layers)
    if not isinstance(layers, Sequence) or isinstance(layers, str):
        fail("policy layers must be an array")
    return tuple(normalize_json_value(layer) for layer in layers)


def _source(value: Any, seen: set[str]) -> str:
    source = token(value, "source")
    if source not in PRECEDENCE:
        fail(f"unknown policy source {source!r}")
    if source in seen:
        fail(f"duplicate policy source {source!r}")
    seen.add(source)
    return source


def _opt_out_source(source: str) -> str:
    return "explicit_project_opt_out" if source == "project" else f"explicit_{source}_opt_out"


def _exception(value: Any, field: str) -> dict[str, str]:
    item = closed(value, {"finding_code", "subject_digest"}, field, subset=True)
    result = {"finding_code": token(item.get("finding_code"), f"{field}.finding_code")}
    if "subject_digest" in item:
        result["subject_digest"] = sha256(item["subject_digest"], f"{field}.subject_digest")
    return result


def _selected(constraints: tuple[PolicyConstraint, ...], value: Any) -> PolicyConstraint:
    default = PolicyConstraint("kernel", PRECEDENCE["kernel"], "figops-kernel-defaults", POLICY_VERSION, value)
    if not constraints:
        return default
    matches = [item for item in constraints if item.value == value]
    return sorted(matches or constraints, key=lambda item: item.precedence)[0]


def _version(value: Any) -> str:
    value = token(value, "version")
    if value != POLICY_VERSION:
        fail("version has unsupported policy version")
    return value
