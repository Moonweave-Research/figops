from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hub_core.calculation_evidence import verify_calculation_evidence
from hub_core.claim_inventory import verify_claim_inventory


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _descriptor(path: Path, root: Path, artifact_id: str, role: str) -> dict[str, str]:
    return {
        "artifact_id": artifact_id,
        "role": role,
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha(path),
    }


def _lineage_fixture(root: Path) -> tuple[Path, dict[str, object]]:
    script = root / "hub_scripts" / "analysis" / "calculate.py"
    config = root / "project_config.yaml"
    source = root / "results" / "data" / "source" / "observations.csv"
    calculation = root / "results" / "evidence" / "claim-result.json"
    for path in (script, config, source, calculation):
        path.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("# deterministic calculation\n", encoding="utf-8")
    config.write_text("project: {name: lineage}\n", encoding="utf-8")
    source.write_text("group,value\na,1\nb,2\n", encoding="utf-8")
    calculation.write_text(
        json.dumps(
            {
                "schema_version": "figops_calculation_artifact/1",
                "evidence_id": "claim:fig1:p-value",
                "producer": "calculate.py",
                "test_metadata": {"test_name": "welch_t_test", "model": "two-sided"},
                "result": {"status": "passed", "p_value": 0.01},
                "assertion": {
                    "metric": "p_value",
                    "operator": "lt",
                    "threshold": 0.05,
                    "display_label": "p < 0.05",
                    "display_kind": "threshold",
                },
                "marker_binding": {"x1": 0, "x2": 1},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    calc_descriptor = _descriptor(calculation, root, "calc:fig1:p-value", "result.evidence")
    payload: dict[str, object] = {
        "schema_version": "figops_calculation_evidence/2",
        "figops_version": "0.20.0",
        "run_id": "run-lineage-1",
        "timestamp": "2026-07-15T00:00:00Z",
        "git_sha256": "1" * 64,
        "environment_lock_sha256": "2" * 64,
        "claim_ids": ["claim:fig1:p-value"],
        "calculation_artifact": calc_descriptor,
        "producer": {
            "script": _descriptor(script, root, "script:calculate", "script.analysis"),
            "config": _descriptor(config, root, "config:project", "config"),
        },
        "input_artifacts": [_descriptor(source, root, "source:observations", "result.source_data")],
        "output_artifacts": [calc_descriptor],
    }
    evidence = root / "results" / "evidence" / "claim-lineage.json"
    evidence.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return evidence, payload


def test_verified_calculation_evidence_hashes_real_artifact_and_complete_lineage(tmp_path: Path) -> None:
    evidence, payload = _lineage_fixture(tmp_path)

    record = verify_calculation_evidence(tmp_path, evidence.relative_to(tmp_path).as_posix())

    calculation = payload["calculation_artifact"]
    assert isinstance(calculation, dict)
    assert record["analysis_artifact_sha256"] == calculation["sha256"]
    assert record["analysis_artifact_sha256"] != _sha(evidence)
    assert record["verification_status"] == "verified"
    assert record["durable_receipt"]["claim_ids"][0].startswith("claim:")
    assert "p-value" not in record["durable_receipt"]["claim_ids"][0]


def test_forged_and_self_referential_calculation_evidence_fail_closed(tmp_path: Path) -> None:
    evidence, payload = _lineage_fixture(tmp_path)
    calculation = payload["calculation_artifact"]
    assert isinstance(calculation, dict)
    calculation["sha256"] = "f" * 64
    outputs = payload["output_artifacts"]
    assert isinstance(outputs, list) and isinstance(outputs[0], dict)
    outputs[0]["sha256"] = "f" * 64
    evidence.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="declared hash does not match"):
        verify_calculation_evidence(tmp_path, evidence.relative_to(tmp_path).as_posix())

    evidence, payload = _lineage_fixture(tmp_path)
    calculation = payload["calculation_artifact"]
    outputs = payload["output_artifacts"]
    assert isinstance(calculation, dict) and isinstance(outputs, list) and isinstance(outputs[0], dict)
    calculation["path"] = evidence.relative_to(tmp_path).as_posix()
    outputs[0]["path"] = evidence.relative_to(tmp_path).as_posix()
    evidence.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="own document"):
        verify_calculation_evidence(tmp_path, evidence.relative_to(tmp_path).as_posix())


def test_legacy_evidence_document_self_hash_is_never_verified(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"schema_version": "figops_calculation_evidence/1"}), encoding="utf-8")

    with pytest.raises(ValueError, match="self-hashes"):
        verify_calculation_evidence(tmp_path, legacy.name)


def test_claim_inventory_binds_claim_calculation_artifact_and_source_dependency(tmp_path: Path) -> None:
    evidence, payload = _lineage_fixture(tmp_path)
    calculation = payload["calculation_artifact"]
    inputs = payload["input_artifacts"]
    assert isinstance(calculation, dict) and isinstance(inputs, list) and isinstance(inputs[0], dict)
    dependency = {key: inputs[0][key] for key in ("artifact_id", "role", "sha256")}
    inventory = tmp_path / "results" / "evidence" / "Fig1.claims.json"
    inventory.write_text(
        json.dumps(
            {
                "schema_version": "figops_claim_inventory/1",
                "figure_id": "Fig1",
                "calculation_evidence_paths": [evidence.relative_to(tmp_path).as_posix()],
                "claims": [
                    {
                        "claim_id": "claim:fig1:p-value",
                        "kind": "statistical",
                        "displayed_text": "p < 0.05",
                        "displayed_region": "panel-a",
                        "calculation_artifact_id": calculation["artifact_id"],
                        "dependencies": [dependency],
                    }
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    verified = verify_claim_inventory(
        tmp_path,
        inventory.relative_to(tmp_path).as_posix(),
        figure_id="Fig1",
        discovered_candidates=[{"source": "script_literal", "text": "p < 0.05"}],
    )

    assert verified["status"] == "verified"
    assert verified["claims"][0]["calculation_artifact_id"] == calculation["artifact_id"]
    assert verified["claims"][0]["dependencies"] == [dependency]
