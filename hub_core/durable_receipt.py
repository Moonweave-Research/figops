"""Closed, canonical DTO for durable lineage receipts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from .structure_contract_types import CANONICAL_PROJECT_ROLES

SCHEMA_VERSION = "figops-durable-receipt/2"
LEGACY_SCHEMA_VERSION = "figops-durable-receipt/1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_ID_RE = re.compile(r"^(run|manifest):[0-9a-f]{32}$")
_ARTIFACT_ID_RE = re.compile(r"^(artifact|config|evidence|figure|publication|raw|script|source|table):[0-9a-f]{32}$")
_CLAIM_ID_RE = re.compile(r"^claim:[0-9a-f]{32}$")
_POLICY_PROFILES = frozenset(
    {
        "journal-acs",
        "journal-cell",
        "journal-elsevier",
        "journal-nature",
        "journal-rsc",
        "journal-science",
        "journal-wiley",
    }
)
_POLICY_VERSION_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){0,3}$")
_SEMVER_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:alpha|beta|rc|dev)\.(?:0|[1-9][0-9]*))?$"
)
_RFC3339_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
_ARTIFACT_ROLES = frozenset(role for role in CANONICAL_PROJECT_ROLES if role != "runtime.*")
_MAX_ARTIFACTS = 256
_MAX_CLAIMS = 256


def _text(value: object, field: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"durable receipt requires non-empty {field}")
    if value != value.strip() or len(value) > max_length:
        raise ValueError(f"durable receipt {field} must be canonical and at most {max_length} characters")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError(f"durable receipt {field} may not contain control characters")
    return value


def _opaque_id(value: object, field: str, *, namespace: str) -> str:
    value = _text(value, field, max_length=64)
    match = _OPAQUE_ID_RE.fullmatch(value)
    if match is None or match.group(1) != namespace:
        raise ValueError(f"durable receipt {field} must be an opaque {namespace}:<128-bit-hex> identifier")
    return value


def _domain_digest(domain: str, value: str) -> str:
    framed = b"figops-durable-receipt-v2\0" + domain.encode("ascii") + b"\0" + value.encode("utf-8")
    return hashlib.sha256(framed).hexdigest()[:32]


def opaque_receipt_id(namespace: str, value: object) -> str:
    """Irreversibly reduce an external run/manifest label to a receipt-safe ID."""

    if namespace not in {"run", "manifest"}:
        raise ValueError("durable receipt opaque ID namespace must be 'run' or 'manifest'")
    text = _text(value, f"{namespace}_source_id", max_length=1024)
    return f"{namespace}:{_domain_digest(f'receipt-id:{namespace}', text)}"


def _artifact_id(value: object, field: str) -> str:
    value = _text(value, field, max_length=64)
    if not _ARTIFACT_ID_RE.fullmatch(value):
        raise ValueError(f"durable receipt {field} must be a typed opaque artifact identifier")
    return value


def _artifact_namespace(role: str) -> str:
    if role == "raw":
        return "raw"
    if role == "config":
        return "config"
    if role.startswith("script."):
        return "script"
    return {
        "result.evidence": "evidence",
        "result.figure": "figure",
        "result.intermediate": "artifact",
        "result.publication": "publication",
        "result.source_data": "source",
        "result.table": "table",
    }[role]


def opaque_artifact_id(role: str, value: object) -> str:
    """Irreversibly reduce an external artifact label to a typed receipt ID."""

    normalized_role = _role(role, "artifact.role")
    namespace = _artifact_namespace(normalized_role)
    text = _text(value, "artifact.source_id", max_length=1024)
    return f"{namespace}:{_domain_digest(f'artifact-id:{normalized_role}', text)}"


def opaque_claim_id(value: object) -> str:
    """Irreversibly reduce a stable claim label without retaining claim text."""

    text = _text(value, "claim.source_id", max_length=1024)
    return f"claim:{_domain_digest('claim-id', text)}"


def _figops_version(value: object) -> str:
    value = _text(value, "figops_version", max_length=64)
    if not _SEMVER_RE.fullmatch(value):
        raise ValueError(
            "durable receipt figops_version must be a canonical release or alpha/beta/rc/dev numeric prerelease"
        )
    return value


def _timestamp(value: object) -> str:
    value = _text(value, "timestamp", max_length=35)
    if not _RFC3339_RE.fullmatch(value):
        raise ValueError("durable receipt timestamp must be an RFC 3339 date-time with timezone")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("durable receipt timestamp must be a valid RFC 3339 date-time") from exc
    return value


def _sha256(value: object, field: str) -> str:
    value = _text(value, field, max_length=64)
    if not _SHA256_RE.fullmatch(value):
        raise ValueError(f"durable receipt {field} must be a lowercase SHA-256")
    return value


def _role(value: object, field: str) -> str:
    value = _text(value, field, max_length=32)
    if value not in _ARTIFACT_ROLES:
        raise ValueError(f"durable receipt {field} must be a canonical durable artifact role")
    return value


def _publication_policy(value: object) -> dict[str, str]:
    required = {"profile_id", "rule_version", "measurement_version", "outcomes_sha256"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError(f"durable receipt publication_policy must contain {', '.join(sorted(required))} only")
    profile_id = _text(value["profile_id"], "publication_policy.profile_id", max_length=32)
    if profile_id not in _POLICY_PROFILES:
        raise ValueError("durable receipt publication_policy.profile_id must name a public journal profile")
    versions: dict[str, str] = {}
    for field in ("rule_version", "measurement_version"):
        version = _text(value[field], f"publication_policy.{field}", max_length=32)
        if not _POLICY_VERSION_RE.fullmatch(version):
            raise ValueError(f"durable receipt publication_policy.{field} must be a numeric version token")
        versions[field] = version
    return {
        "profile_id": profile_id,
        **versions,
        "outcomes_sha256": _sha256(value["outcomes_sha256"], "publication_policy.outcomes_sha256"),
    }


def _artifact(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"artifact_id", "role", "sha256"}:
        raise ValueError(f"durable receipt {field} must contain artifact_id, role, and sha256 only")
    role = _role(value["role"], f"{field}.role")
    artifact_id = _artifact_id(value["artifact_id"], f"{field}.artifact_id")
    if artifact_id.partition(":")[0] != _artifact_namespace(role):
        raise ValueError(f"durable receipt {field}.artifact_id namespace must match its role")
    return {
        "artifact_id": artifact_id,
        "role": role,
        "sha256": _sha256(value["sha256"], f"{field}.sha256"),
    }


def _artifacts(value: object, field: str) -> tuple[dict[str, str], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"durable receipt {field} must be a sequence")
    if len(value) > _MAX_ARTIFACTS:
        raise ValueError(f"durable receipt {field} exceeds {_MAX_ARTIFACTS} artifacts")
    normalized = tuple(_artifact(item, f"{field}[{index}]") for index, item in enumerate(value))
    ids = [item["artifact_id"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError(f"durable receipt {field} contains duplicate artifact IDs")
    return normalized


def _claim_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("durable receipt requires at least one stable claim ID")
    if len(value) > _MAX_CLAIMS:
        raise ValueError(f"durable receipt claim_ids exceeds {_MAX_CLAIMS} claims")
    claims = tuple(_text(item, "claim_ids[]", max_length=64) for item in value)
    if any(not _CLAIM_ID_RE.fullmatch(claim) for claim in claims):
        raise ValueError("durable receipt claim_ids must be opaque claim:<128-bit-hex> identifiers")
    if len(claims) != len(set(claims)):
        raise ValueError("durable receipt claim_ids contains duplicates")
    return claims


@dataclass(frozen=True, slots=True)
class DurableReceipt:
    """Minimal durable binding between an artifact, its producer, and claims."""

    figops_version: str
    run_id: str
    timestamp: str
    git_sha256: str
    config_sha256: str
    script_sha256: str
    environment_lock_sha256: str
    durable_artifact: Mapping[str, str]
    input_artifacts: Sequence[Mapping[str, str]]
    output_artifacts: Sequence[Mapping[str, str]]
    claim_ids: Sequence[str]
    publication_policy: Mapping[str, str] | None = None
    manifest_id: str | None = None
    manifest_sha256: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"durable receipt schema_version must be {SCHEMA_VERSION!r}")
        object.__setattr__(self, "figops_version", _figops_version(self.figops_version))
        object.__setattr__(self, "run_id", _opaque_id(self.run_id, "run_id", namespace="run"))
        object.__setattr__(self, "timestamp", _timestamp(self.timestamp))
        for field in (
            "git_sha256",
            "config_sha256",
            "script_sha256",
            "environment_lock_sha256",
        ):
            object.__setattr__(self, field, _sha256(getattr(self, field), field))
        object.__setattr__(self, "durable_artifact", _artifact(self.durable_artifact, "durable_artifact"))
        object.__setattr__(self, "input_artifacts", _artifacts(self.input_artifacts, "input_artifacts"))
        outputs = _artifacts(self.output_artifacts, "output_artifacts")
        bound_output = next(
            (item for item in outputs if item["artifact_id"] == self.durable_artifact["artifact_id"]),
            None,
        )
        if bound_output is None:
            raise ValueError("durable receipt output_artifacts must include durable_artifact")
        if bound_output != self.durable_artifact:
            raise ValueError("durable receipt durable_artifact hash must match its output binding")
        object.__setattr__(self, "output_artifacts", outputs)
        input_ids = {item["artifact_id"] for item in self.input_artifacts}
        output_ids = {item["artifact_id"] for item in outputs}
        if input_ids & output_ids:
            raise ValueError("durable receipt input and output artifact IDs must be disjoint")
        object.__setattr__(self, "claim_ids", _claim_ids(self.claim_ids))
        if self.publication_policy is not None:
            object.__setattr__(self, "publication_policy", _publication_policy(self.publication_policy))
        if self.manifest_id is not None:
            manifest_id = _opaque_id(self.manifest_id, "manifest_id", namespace="manifest")
            object.__setattr__(self, "manifest_id", manifest_id)
            if self.manifest_sha256 is None:
                raise ValueError("durable receipt manifest_sha256 is required with manifest_id")
        if self.manifest_sha256 is not None:
            if self.manifest_id is None:
                raise ValueError("durable receipt manifest_id is required with manifest_sha256")
            object.__setattr__(self, "manifest_sha256", _sha256(self.manifest_sha256, "manifest_sha256"))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DurableReceipt:
        """Parse the closed durable JSON form through all field validators."""

        if not isinstance(payload, Mapping):
            raise ValueError("durable receipt must be a mapping")
        if payload.get("schema_version") == LEGACY_SCHEMA_VERSION:
            payload = _migrate_legacy_payload(payload)
        required = {
            "schema_version",
            "figops_version",
            "run_id",
            "timestamp",
            "git_sha256",
            "producer",
            "durable_artifact",
            "input_artifacts",
            "output_artifacts",
            "claim_ids",
        }
        optional = {"publication_policy", "runtime_manifest"}
        if not required <= set(payload) <= required | optional:
            raise ValueError("durable receipt contains missing or unsupported fields")
        producer = payload.get("producer")
        if not isinstance(producer, Mapping) or set(producer) != {
            "config_sha256",
            "script_sha256",
            "environment_lock_sha256",
        }:
            raise ValueError("durable receipt producer must contain the three SHA-256 bindings only")
        runtime_manifest = payload.get("runtime_manifest")
        if runtime_manifest is not None:
            if not isinstance(runtime_manifest, Mapping) or set(runtime_manifest) != {
                "id",
                "sha256",
                "required_for_reproduction",
            }:
                raise ValueError("durable receipt runtime_manifest has an invalid shape")
            if runtime_manifest["required_for_reproduction"] is not False:
                raise ValueError("durable receipt runtime manifest must remain disposable")
        manifest = runtime_manifest or {}
        return cls(
            figops_version=payload["figops_version"],
            run_id=payload["run_id"],
            timestamp=payload["timestamp"],
            git_sha256=payload["git_sha256"],
            config_sha256=producer["config_sha256"],
            script_sha256=producer["script_sha256"],
            environment_lock_sha256=producer["environment_lock_sha256"],
            durable_artifact=payload["durable_artifact"],
            input_artifacts=payload["input_artifacts"],
            output_artifacts=payload["output_artifacts"],
            claim_ids=payload["claim_ids"],
            publication_policy=payload.get("publication_policy"),
            manifest_id=manifest.get("id"),
            manifest_sha256=manifest.get("sha256"),
            schema_version=payload["schema_version"],
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "figops_version": self.figops_version,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "git_sha256": self.git_sha256,
            "producer": {
                "config_sha256": self.config_sha256,
                "script_sha256": self.script_sha256,
                "environment_lock_sha256": self.environment_lock_sha256,
            },
            "durable_artifact": dict(self.durable_artifact),
            "input_artifacts": [dict(item) for item in self.input_artifacts],
            "output_artifacts": [dict(item) for item in self.output_artifacts],
            "claim_ids": list(self.claim_ids),
        }
        if self.publication_policy is not None:
            payload["publication_policy"] = dict(self.publication_policy)
        if self.manifest_id is not None:
            payload["runtime_manifest"] = {
                "id": self.manifest_id,
                "sha256": self.manifest_sha256,
                "required_for_reproduction": False,
            }
        return payload

    def canonical_bytes(self) -> bytes:
        return canonical_serialize(self.to_dict())

    def canonical_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @classmethod
    def from_runtime_diagnostics(cls, diagnostics: Mapping[str, Any]) -> DurableReceipt:
        """Project a detailed manifest through the closed durable allow-list."""

        if not isinstance(diagnostics, Mapping):
            raise ValueError("runtime diagnostics must be a mapping")
        allowed = {
            "figops_version",
            "run_id",
            "timestamp",
            "git_sha256",
            "config_sha256",
            "script_sha256",
            "environment_lock_sha256",
            "durable_artifact",
            "input_artifacts",
            "output_artifacts",
            "claim_ids",
            "publication_policy",
            "manifest_id",
            "manifest_sha256",
        }
        projected = {key: diagnostics[key] for key in allowed if key in diagnostics}
        if "run_id" in projected:
            projected["run_id"] = opaque_receipt_id("run", projected["run_id"])
        if "manifest_id" in projected:
            projected["manifest_id"] = opaque_receipt_id("manifest", projected["manifest_id"])
        for field in ("durable_artifact",):
            if field in projected:
                descriptor = projected[field]
                if isinstance(descriptor, Mapping):
                    projected[field] = {
                        **descriptor,
                        "artifact_id": opaque_artifact_id(str(descriptor.get("role")), descriptor.get("artifact_id")),
                    }
        for field in ("input_artifacts", "output_artifacts"):
            descriptors = projected.get(field)
            if isinstance(descriptors, (list, tuple)):
                projected[field] = [
                    {
                        **descriptor,
                        "artifact_id": opaque_artifact_id(str(descriptor.get("role")), descriptor.get("artifact_id")),
                    }
                    if isinstance(descriptor, Mapping)
                    else descriptor
                    for descriptor in descriptors
                ]
        claims = projected.get("claim_ids")
        if isinstance(claims, (list, tuple)):
            projected["claim_ids"] = [opaque_claim_id(claim) for claim in claims]
        return cls(**projected)


def _migrate_legacy_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce v1's readable runtime IDs while retaining its lineage bindings."""

    migrated = dict(payload)
    migrated["schema_version"] = SCHEMA_VERSION
    if "run_id" in migrated:
        migrated["run_id"] = opaque_receipt_id("run", migrated["run_id"])
    for field in ("durable_artifact",):
        descriptor = migrated.get(field)
        if isinstance(descriptor, Mapping):
            migrated[field] = {
                **descriptor,
                "artifact_id": opaque_artifact_id(str(descriptor.get("role")), descriptor.get("artifact_id")),
            }
    for field in ("input_artifacts", "output_artifacts"):
        descriptors = migrated.get(field)
        if isinstance(descriptors, (list, tuple)):
            migrated[field] = [
                {
                    **descriptor,
                    "artifact_id": opaque_artifact_id(str(descriptor.get("role")), descriptor.get("artifact_id")),
                }
                if isinstance(descriptor, Mapping)
                else descriptor
                for descriptor in descriptors
            ]
    claims = migrated.get("claim_ids")
    if isinstance(claims, (list, tuple)):
        migrated["claim_ids"] = [opaque_claim_id(claim) for claim in claims]
    runtime_manifest = migrated.get("runtime_manifest")
    if isinstance(runtime_manifest, Mapping):
        reduced_manifest = dict(runtime_manifest)
        if "id" in reduced_manifest:
            reduced_manifest["id"] = opaque_receipt_id("manifest", reduced_manifest["id"])
        migrated["runtime_manifest"] = reduced_manifest
    return migrated


def canonical_serialize(receipt: DurableReceipt | Mapping[str, Any]) -> bytes:
    payload = receipt.to_dict() if isinstance(receipt, DurableReceipt) else DurableReceipt.from_dict(receipt).to_dict()
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def receipt_sha256(receipt: DurableReceipt | Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_serialize(receipt)).hexdigest()


def verify_receipt(receipt: DurableReceipt | Mapping[str, Any], expected_sha256: str) -> bool:
    expected = _sha256(expected_sha256, "expected_sha256")
    return hashlib.sha256(canonical_serialize(receipt)).hexdigest() == expected


build_durable_receipt = DurableReceipt.from_runtime_diagnostics
