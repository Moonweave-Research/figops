"""Immutable DTOs for canonical policy resolution."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .policy_resolution_json import canonical_json_bytes


@dataclass(frozen=True, slots=True)
class PolicyConstraint:
    source: str
    precedence: int
    policy_id: str
    version: str
    value: Any


@dataclass(frozen=True, slots=True)
class PolicyException:
    source: str
    policy_id: str
    version: str
    finding_code: str
    subject_digest: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedPolicyValue:
    parameter: str
    value: Any
    merge_operator: str
    source: str
    precedence: int
    policy_id: str
    version: str
    opt_out_requested: bool
    opt_out_accepted: bool
    constraints: tuple[PolicyConstraint, ...]
    exceptions: tuple[PolicyException, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "value": jsonable(self.value),
            "merge_operator": self.merge_operator,
            "source": self.source,
            "precedence": self.precedence,
            "policy_id": self.policy_id,
            "version": self.version,
            "opt_out_requested": self.opt_out_requested,
            "opt_out_accepted": self.opt_out_accepted,
            "constraints": [_dc_json(item) for item in self.constraints],
            "exceptions": [_dc_json(item) for item in self.exceptions],
        }


@dataclass(frozen=True, slots=True)
class ResolvedPolicySet:
    schema_version: str
    parameters: tuple[ResolvedPolicyValue, ...]

    def value(self, parameter: str) -> ResolvedPolicyValue:
        for item in self.parameters:
            if item.parameter == parameter:
                return item
        raise KeyError(parameter)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "parameters": {value.parameter: value.to_json() for value in self.parameters},
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_json())

    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def jsonable(value: Any) -> Any:
    return [jsonable(item) for item in value] if isinstance(value, tuple) else value


def _dc_json(value: PolicyConstraint | PolicyException) -> dict[str, Any]:
    return {
        key: jsonable(getattr(value, key))
        for key in value.__dataclass_fields__
        if getattr(value, key) is not None
    }
