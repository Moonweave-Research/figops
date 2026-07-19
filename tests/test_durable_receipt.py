from __future__ import annotations

import json
import shutil

import pytest

from hub_core.durable_receipt import (
    DurableReceipt,
    canonical_serialize,
    opaque_artifact_id,
    opaque_claim_id,
    opaque_receipt_id,
    receipt_sha256,
    verify_receipt,
)


def _diagnostics() -> dict[str, object]:
    output = {"artifact_id": "calc-1", "role": "result.source_data", "sha256": "9" * 64}
    return {
        "figops_version": "0.20.0",
        "run_id": "run-1",
        "timestamp": "2026-07-15T00:00:00Z",
        "git_sha256": "1" * 64,
        "config_sha256": "2" * 64,
        "script_sha256": "3" * 64,
        "environment_lock_sha256": "4" * 64,
        "durable_artifact": output,
        "input_artifacts": [
            {"artifact_id": "raw-1", "role": "raw", "sha256": "5" * 64},
        ],
        "output_artifacts": [output],
        "claim_ids": ["claim:figure-1:p-value"],
        "manifest_id": "manifest-a1b2",
        "manifest_sha256": "6" * 64,
        "logs": ["C:/Users/researcher/runtime/job.log"],
        "sample_rows": [{"restricted": "secret"}],
        "environment": {"HOME": "C:/Users/researcher"},
    }


def test_durable_receipt_normalizes_diagnostics_and_hides_runtime_root() -> None:
    receipt = DurableReceipt.from_runtime_diagnostics(_diagnostics())
    serialized = receipt.canonical_bytes().decode("utf-8")
    assert "C:/Users" not in serialized
    assert "sample_rows" not in serialized
    assert "logs" not in serialized
    assert json.loads(serialized)["runtime_manifest"] == {
        "id": opaque_receipt_id("manifest", "manifest-a1b2"),
        "required_for_reproduction": False,
        "sha256": "6" * 64,
    }


def test_receipt_binds_durable_artifact_producer_inputs_outputs_and_claims() -> None:
    receipt = DurableReceipt.from_runtime_diagnostics(_diagnostics())
    payload = receipt.to_dict()
    assert payload["durable_artifact"]["sha256"] == "9" * 64
    assert payload["producer"] == {
        "config_sha256": "2" * 64,
        "script_sha256": "3" * 64,
        "environment_lock_sha256": "4" * 64,
    }
    assert payload["input_artifacts"][0]["sha256"] == "5" * 64
    assert payload["output_artifacts"][0]["sha256"] == "9" * 64
    assert payload["claim_ids"] == [opaque_claim_id("claim:figure-1:p-value")]


def test_canonical_serialization_and_hash_verification() -> None:
    receipt = DurableReceipt.from_runtime_diagnostics(_diagnostics())
    digest = receipt_sha256(receipt)
    assert digest == receipt.canonical_sha256()
    assert verify_receipt(receipt, digest)
    assert not verify_receipt(receipt, "0" * 64)


@pytest.mark.parametrize("manifest_id", ["C:/runtime/manifest.json", "../manifest", "a/b", "file:manifest"])
def test_runtime_manifest_labels_are_reduced_to_opaque_ids(manifest_id: str) -> None:
    diagnostics = _diagnostics()
    diagnostics["manifest_id"] = manifest_id

    receipt = DurableReceipt.from_runtime_diagnostics(diagnostics)

    assert receipt.manifest_id == opaque_receipt_id("manifest", manifest_id)
    assert manifest_id not in receipt.canonical_bytes().decode("utf-8")


def test_receipt_verifies_after_runtime_tree_deletion(tmp_path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "manifest.json").write_text("disposable detail", encoding="utf-8")
    receipt = DurableReceipt.from_runtime_diagnostics(_diagnostics())
    digest = receipt_sha256(receipt)

    shutil.rmtree(runtime)

    assert not runtime.exists()
    assert verify_receipt(receipt, digest)


def test_closed_json_form_round_trips_through_contract_validation() -> None:
    original = DurableReceipt.from_runtime_diagnostics(_diagnostics())

    parsed = DurableReceipt.from_dict(original.to_dict())

    assert parsed == original
    assert canonical_serialize(parsed.to_dict()) == original.canonical_bytes()


@pytest.mark.parametrize(
    ("field", "sensitive_value"),
    [
        ("figops_version", "0.20.0 patient=Alice"),
        ("timestamp", "2026-07-15T00:00:00Z patient-17"),
    ],
)
def test_scalar_fields_reject_sensitive_content_smuggling(field: str, sensitive_value: str) -> None:
    diagnostics = _diagnostics()
    diagnostics[field] = sensitive_value

    with pytest.raises(ValueError):
        DurableReceipt.from_runtime_diagnostics(diagnostics)


@pytest.mark.parametrize(
    ("field", "namespace", "sensitive_value"),
    [
        ("run_id", "run", "run 17 patient Alice sample Jane Doe"),
        ("manifest_id", "manifest", "manifest patient Alice sample secret"),
    ],
)
def test_runtime_identifiers_are_irreversibly_reduced(field: str, namespace: str, sensitive_value: str) -> None:
    diagnostics = _diagnostics()
    diagnostics[field] = sensitive_value

    receipt = DurableReceipt.from_runtime_diagnostics(diagnostics)
    serialized = receipt.canonical_bytes().decode("utf-8")

    assert sensitive_value not in serialized
    assert getattr(receipt, field) == opaque_receipt_id(namespace, sensitive_value)


def test_opaque_looking_external_ids_are_always_domain_reduced() -> None:
    hex_value = "a" * 32
    apparent_run_id = f"run:{hex_value}"
    apparent_manifest_id = f"manifest:{hex_value}"
    apparent_artifact_id = f"source:{hex_value}"
    apparent_claim_id = f"claim:{hex_value}"

    assert opaque_receipt_id("run", apparent_run_id) != apparent_run_id
    assert opaque_receipt_id("manifest", apparent_manifest_id) != apparent_manifest_id
    assert opaque_artifact_id("result.source_data", apparent_artifact_id) != apparent_artifact_id
    assert opaque_claim_id(apparent_claim_id) != apparent_claim_id
    assert opaque_receipt_id("run", hex_value) != opaque_receipt_id("manifest", hex_value)


@pytest.mark.parametrize("sensitive_value", ["patient:Alice:sample-17", "patient Alice sample 17"])
def test_artifact_ids_are_irreversibly_reduced(sensitive_value: str) -> None:
    diagnostics = _diagnostics()
    descriptor = dict(diagnostics["durable_artifact"])
    descriptor["artifact_id"] = sensitive_value
    diagnostics["durable_artifact"] = descriptor
    diagnostics["output_artifacts"] = [descriptor]

    receipt = DurableReceipt.from_runtime_diagnostics(diagnostics)

    assert sensitive_value not in receipt.canonical_bytes().decode("utf-8")
    assert receipt.durable_artifact["artifact_id"] == opaque_artifact_id("result.source_data", sensitive_value)


@pytest.mark.parametrize("sensitive_role", ["result.source_data patient=Alice", "patient.sample"])
def test_artifact_roles_reject_patient_or_sample_content(sensitive_role: str) -> None:
    diagnostics = _diagnostics()
    descriptor = dict(diagnostics["durable_artifact"])
    descriptor["role"] = sensitive_role
    diagnostics["durable_artifact"] = descriptor
    diagnostics["output_artifacts"] = [descriptor]

    with pytest.raises(ValueError):
        DurableReceipt.from_runtime_diagnostics(diagnostics)


@pytest.mark.parametrize(
    "claim_id",
    [
        "patient:Alice:sample-17",
        "claim:patient Alice:sample 17",
        '{"patient":"Alice","sample":"secret"}',
        "claim:/clinical/patient-17",
    ],
)
def test_claim_ids_are_irreversibly_reduced(claim_id: str) -> None:
    diagnostics = _diagnostics()
    diagnostics["claim_ids"] = [claim_id]

    receipt = DurableReceipt.from_runtime_diagnostics(diagnostics)

    assert claim_id not in receipt.canonical_bytes().decode("utf-8")
    assert receipt.claim_ids == (opaque_claim_id(claim_id),)


def test_v2_json_rejects_readable_ids_instead_of_silently_accepting_them() -> None:
    payload = DurableReceipt.from_runtime_diagnostics(_diagnostics()).to_dict()
    payload["durable_artifact"]["artifact_id"] = "source:patient-Alice"
    payload["output_artifacts"][0]["artifact_id"] = "source:patient-Alice"
    payload["claim_ids"] = ["claim:patient-Alice:sample-17"]

    with pytest.raises(ValueError, match="opaque"):
        DurableReceipt.from_dict(payload)


def test_v2_artifact_id_namespace_must_match_declared_role() -> None:
    payload = DurableReceipt.from_runtime_diagnostics(_diagnostics()).to_dict()
    wrong_id = opaque_artifact_id("raw", "raw-17")
    payload["durable_artifact"]["artifact_id"] = wrong_id
    payload["output_artifacts"][0]["artifact_id"] = wrong_id

    with pytest.raises(ValueError, match="namespace must match"):
        DurableReceipt.from_dict(payload)


def test_mapping_serialization_cannot_bypass_closed_receipt_contract() -> None:
    payload = DurableReceipt.from_runtime_diagnostics(_diagnostics()).to_dict()
    payload["sample_rows"] = [{"patient": "Alice", "sample": "secret"}]

    with pytest.raises(ValueError, match="missing or unsupported"):
        canonical_serialize(payload)


def test_optional_publication_policy_is_closed_and_canonical() -> None:
    diagnostics = _diagnostics()
    diagnostics["publication_policy"] = {
        "profile_id": "journal-nature",
        "rule_version": "2",
        "measurement_version": "2.1",
        "outcomes_sha256": "7" * 64,
    }

    receipt = DurableReceipt.from_runtime_diagnostics(diagnostics)

    assert receipt.to_dict()["publication_policy"] == diagnostics["publication_policy"]
    assert DurableReceipt.from_dict(receipt.to_dict()) == receipt


@pytest.mark.parametrize(
    "policy",
    [
        {
            "profile_id": "journal-patient-Alice",
            "rule_version": "2",
            "measurement_version": "2",
            "outcomes_sha256": "7" * 64,
        },
        {
            "profile_id": "journal-nature",
            "rule_version": "patient-Alice",
            "measurement_version": "2",
            "outcomes_sha256": "7" * 64,
        },
        {
            "profile_id": "journal-nature",
            "rule_version": "2",
            "measurement_version": "patient-Alice",
            "outcomes_sha256": "7" * 64,
        },
        {
            "profile_id": "journal-nature",
            "rule_version": "2",
            "measurement_version": "2",
            "outcomes_sha256": "patient-Alice",
        },
        {
            "profile_id": "journal-nature",
            "rule_version": "2",
            "measurement_version": "2",
            "outcomes_sha256": "7" * 64,
            "sample_id": "patient-Alice",
        },
    ],
)
def test_publication_policy_cannot_carry_sensitive_free_text(policy: dict[str, str]) -> None:
    diagnostics = _diagnostics()
    diagnostics["publication_policy"] = policy

    with pytest.raises(ValueError, match="publication_policy"):
        DurableReceipt.from_runtime_diagnostics(diagnostics)


@pytest.mark.parametrize(
    "timestamp",
    ["2026-02-30T00:00:00Z", "2026-07-15 00:00:00Z", "2026-07-15T00:00:00"],
)
def test_timestamp_requires_a_real_timezone_qualified_rfc3339_value(timestamp: str) -> None:
    diagnostics = _diagnostics()
    diagnostics["timestamp"] = timestamp

    with pytest.raises(ValueError, match="timestamp"):
        DurableReceipt.from_runtime_diagnostics(diagnostics)


def test_semver_and_namespaced_ids_keep_legitimate_receipts_compatible() -> None:
    diagnostics = _diagnostics()
    diagnostics["figops_version"] = "0.20.0-rc.1"
    diagnostics["timestamp"] = "2026-07-15T09:30:00.123456+09:00"
    output = {
        "artifact_id": "calc:figure-1:p-value",
        "role": "result.evidence",
        "sha256": "9" * 64,
    }
    diagnostics["durable_artifact"] = output
    diagnostics["output_artifacts"] = [output]
    diagnostics["claim_ids"] = ["analysis:figure-1:p-value"]

    receipt = DurableReceipt.from_runtime_diagnostics(diagnostics)

    assert receipt.figops_version == "0.20.0-rc.1"
    assert receipt.durable_artifact["artifact_id"] == opaque_artifact_id("result.evidence", "calc:figure-1:p-value")


def test_legacy_v1_receipt_migrates_readable_runtime_ids_without_leaking_them() -> None:
    receipt = DurableReceipt.from_runtime_diagnostics(_diagnostics())
    legacy = receipt.to_dict()
    legacy["schema_version"] = "figops-durable-receipt/1"
    legacy["run_id"] = "patient-Alice-sample-17"
    legacy["runtime_manifest"]["id"] = "patient-Alice-clinical-manifest"

    migrated = DurableReceipt.from_dict(legacy)
    serialized = migrated.canonical_bytes().decode("utf-8")

    assert migrated.schema_version == "figops-durable-receipt/2"
    assert "patient-Alice" not in serialized


@pytest.mark.parametrize(
    "version",
    [
        "0.20.0-patient-Alice",
        "0.20.0-rc.patient-Alice",
        "0.20.0+patient-Alice",
        "0.20.0-rc.1+patient-Alice",
    ],
)
def test_figops_version_cannot_be_used_as_a_free_text_channel(version: str) -> None:
    diagnostics = _diagnostics()
    diagnostics["figops_version"] = version

    with pytest.raises(ValueError, match="figops_version"):
        DurableReceipt.from_runtime_diagnostics(diagnostics)
