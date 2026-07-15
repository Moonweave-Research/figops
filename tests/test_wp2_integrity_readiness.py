from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from hub_core.artifact_integrity import inspect_manifest_artifacts
from hub_core.config_parser import validate_config
from hub_core.data_contract import validate_data_contract
from hub_core.mcp import GraphHubMCPServer
from hub_core.provenance_inputs import provenance_hash_coverage, resolved_research_ops_evidence
from hub_core.publication_evidence import load_readiness_manifest
from hub_core.publication_readiness import evaluate_publication_readiness

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_artifact_integrity_verifies_bytes_and_output_hash(tmp_path: Path) -> None:
    artifact = tmp_path / "figure.png"
    artifact.write_bytes(PNG_1X1)
    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "artifact_status": "created",
        "failure_stage": "",
        "figures": [{"path": str(artifact), "format": "png"}],
        "provenance": {"output_sha256": _sha(PNG_1X1)},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = inspect_manifest_artifacts(manifest, manifest_path)

    assert result["status"] == "passed"
    assert result["entries"][0]["sha256"] == _sha(PNG_1X1)
    assert result["entries"][0]["width"] == 1


def test_artifact_integrity_rejects_truncated_png(tmp_path: Path) -> None:
    artifact = tmp_path / "truncated.png"
    artifact.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    manifest_path = tmp_path / "manifest.json"
    manifest = {"artifact_status": "created", "figures": [{"path": str(artifact)}]}
    manifest_path.write_text("{}", encoding="utf-8")

    result = inspect_manifest_artifacts(manifest, manifest_path)

    assert result["status"] == "failed"
    assert not result["entries"]


def test_loaded_manifest_combines_artifact_and_provenance_coverage(tmp_path: Path) -> None:
    artifact = tmp_path / "figure.png"
    artifact.write_bytes(PNG_1X1)
    hashes = {
        "source_data_sha256": "1" * 64,
        "config_sha256": "2" * 64,
        "script_sha256": "3" * 64,
        "environment_sha256": "4" * 64,
        "output_sha256": _sha(PNG_1X1),
    }
    manifest = {
        "artifact_status": "created",
        "figures": [{"path": str(artifact), "format": "png"}],
        "provenance": hashes,
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    evidence = load_readiness_manifest(path)
    report = evaluate_publication_readiness(evidence)

    assert evidence["artifact_integrity"]["status"] == "passed"
    assert evidence["provenance_coverage"]["status"] == "passed"
    assert report["readiness_status"] == "needs_review"


def test_missing_script_provenance_blocks_completed_artifact() -> None:
    provenance = {
        "input_sha256": "1" * 64,
        "config_sha256": "2" * 64,
        "environment_sha256": "4" * 64,
        "output_sha256": "5" * 64,
    }
    evidence = {
        "artifact_status": "created",
        "provenance": provenance,
        "provenance_coverage": provenance_hash_coverage(provenance),
    }

    report = evaluate_publication_readiness(evidence)

    assert report["readiness_status"] == "blocked"
    assert {finding["code"] for finding in report["findings"]} == {"PROVENANCE_HASHES_MISSING"}


def test_provenance_coverage_rejects_hashes_hidden_in_unrelated_nested_metadata() -> None:
    nested = {"junk": {field: str(index) * 64 for index, field in enumerate(
        ("input_sha256", "config_sha256", "script_sha256", "environment_sha256", "output_sha256"),
        start=1,
    )}}

    coverage = provenance_hash_coverage(nested)

    assert coverage["status"] == "incomplete"
    assert coverage["hashes"] == {}


def test_required_and_optional_unavailable_diagnostics_are_distinct() -> None:
    evidence = {
        "geometry_diagnostics": {
            "schema_version": "geometry_diagnostics/1",
            "passed": None,
            "checks": [{"name": "tick_label_crowding", "passed": None}],
        }
    }
    optional = evaluate_publication_readiness(evidence)
    required = evaluate_publication_readiness(evidence, required_diagnostic_ids=("artists_outside_figure",))

    assert optional["readiness_status"] == "needs_review"
    assert optional["findings"][0]["code"] == "GEOMETRY_DIAGNOSTIC_UNAVAILABLE"
    assert required["readiness_status"] == "blocked"
    assert any(finding["code"] == "GEOMETRY_REQUIRED_DIAGNOSTICS_MISSING" for finding in required["findings"])


def test_geometry_unavailable_stub_and_nonblocking_false_aggregate_do_not_block() -> None:
    stub = evaluate_publication_readiness(
        {
            "geometry_diagnostics": {
                "schema_version": "geometry_diagnostics/1",
                "passed": None,
                "checks": [],
                "warnings": ["no sidecar"],
            }
        }
    )
    nonblocking = evaluate_publication_readiness(
        {
            "geometry_diagnostics": {
                "schema_version": "geometry_diagnostics/1",
                "passed": False,
                "checks": [{"name": "legend_data_collision", "passed": False}],
            }
        }
    )

    assert stub["readiness_status"] == "needs_review"
    assert nonblocking["readiness_status"] == "needs_review"
    assert all(finding["code"] != "GEOMETRY_SUMMARY_INCONSISTENT" for finding in nonblocking["findings"])


def test_forged_integrity_and_provenance_summaries_fail_closed() -> None:
    report = evaluate_publication_readiness(
        {
            "artifact_status": "created",
            "artifact_integrity": {"status": "passed", "entries": [], "errors": ["bad"]},
            "provenance": {},
            "provenance_coverage": {"status": "passed", "hashes": {}, "missing": []},
        }
    )

    codes = {finding["code"] for finding in report["findings"]}
    assert report["readiness_status"] == "blocked"
    assert "ARTIFACT_INTEGRITY_FAILED" in codes
    assert "PROVENANCE_COVERAGE_INCONSISTENT" in codes


def test_exact_hash_difference_is_informational_not_visual_quality_blocker() -> None:
    report = evaluate_publication_readiness(
        {
            "baseline_comparison": {
                "checked": True,
                "matched": False,
                "algorithm": "sha256",
                "artifact_sha256": "a" * 64,
            }
        }
    )

    assert report["readiness_status"] == "needs_review"
    assert report["findings"][0]["code"] == "EXACT_BYTES_DIFFERENT"
    assert report["findings"][0]["severity"] == "info"


def test_required_canonical_docs_consume_path_evidence() -> None:
    report = evaluate_publication_readiness(
        {
            "canonical_docs_registry": {
                "declared": True,
                "required": True,
                "docs": [
                    {
                        "exists": True,
                        "contained": False,
                        "regular_file": True,
                        "symlinked": False,
                        "status": "ready",
                    }
                ],
            }
        }
    )

    assert report["readiness_status"] == "blocked"
    assert report["findings"][0]["code"] == "CANONICAL_DOC_EVIDENCE_INVALID"


def test_research_ops_policy_records_module_defaults_and_false_opt_out() -> None:
    policy = resolved_research_ops_evidence(
        {
            "project": {"name": "module", "role": "module"},
            "data_contract": {"require_figure_traceability": False},
        }
    )

    assert policy["id"] == "research-ops-v4"
    assert policy["parameters"]["require_canonical_docs"] == {
        "value": True,
        "source": "module-default",
    }
    assert policy["parameters"]["require_figure_traceability"] == {
        "value": False,
        "source": "project_config",
    }


def test_raw_integrity_rejects_symlinked_data_component(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.csv"
    outside.write_text("x,y\n1,2\n", encoding="utf-8")
    raw = tmp_path / "raw"
    raw.mkdir()
    link = raw / "linked.csv"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    config = {
        "project": {"name": "raw"},
        "data_contract": {
            "raw_integrity": {"mode": "strict", "manifest": "raw/.manifest.json", "paths": ["raw"]}
        },
    }

    from hub_core.raw_integrity import seal_raw_integrity

    with pytest.raises(ValueError, match="symlink"):
        seal_raw_integrity(tmp_path, config)


def test_raw_integrity_seal_rejects_symlinked_manifest(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "data.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    target = raw / "actual-manifest.json"
    target.write_text("{}", encoding="utf-8")
    manifest = raw / ".manifest.json"
    try:
        manifest.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    config = {
        "project": {"name": "raw"},
        "data_contract": {
            "raw_integrity": {"mode": "strict", "manifest": "raw/.manifest.json", "paths": ["raw"]}
        },
    }

    from hub_core.raw_integrity import seal_raw_integrity

    with pytest.raises(ValueError, match="symlink or reparse-point"):
        seal_raw_integrity(tmp_path, config)


def test_traceability_true_rejects_all_missing_fields_and_cv_needs_columns() -> None:
    config = {
        "project": {"name": "module"},
        "visual_style": {"target_format": "nature"},
        "data_contract": {"require_figure_traceability": True, "cv_threshold": 0.1},
        "figures": [{"id": "fig", "script": "plot.py", "output": "results/fig.png"}],
    }

    errors = validate_config(config)

    assert any("missing claim" in error for error in errors)
    assert any("missing samples" in error for error in errors)
    assert any("missing conditions" in error for error in errors)
    assert any("cv_columns" in error for error in errors)


def test_cv_quality_scans_only_explicit_measurement_columns(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data.csv"
    data.write_text("identifier,time,measurement\n100,0,1\n200,1,10\n", encoding="utf-8")
    seen: list[str] = []

    def capture(df, *_args, **_kwargs):
        seen.extend(str(column) for column in df.columns)
        return {"quality_passed": True, "cv_warnings": [], "report_path": None}

    monkeypatch.setattr("hub_core.data_contract._check_statistical_quality", capture)
    config = {
        "data_contract": {
            "cv_threshold": 0.1,
            "cv_columns": ["measurement"],
            "csv_checks": [{"path": "data.csv", "required_columns": ["identifier", "time", "measurement"]}],
        }
    }

    assert validate_data_contract(tmp_path, config, write_sidecar=False) is True
    assert seen == ["measurement"]


def test_missing_declared_cv_column_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "data.csv").write_text("identifier,time\n100,0\n200,1\n", encoding="utf-8")
    config = {
        "data_contract": {
            "cv_threshold": 0.1,
            "cv_columns": ["measurement"],
            "csv_checks": [{"path": "data.csv", "required_columns": ["identifier", "time"]}],
        }
    }

    assert validate_data_contract(tmp_path, config, write_sidecar=False) is False


@pytest.mark.parametrize("threshold", [0, -0.1, float("inf"), "0.1", True])
def test_cv_threshold_must_be_positive_finite_number(threshold: object) -> None:
    errors = validate_config(
        {
            "project": {"name": "cv"},
            "visual_style": {"target_format": "nature"},
            "data_contract": {"cv_threshold": threshold, "cv_columns": ["measurement"]},
        }
    )

    assert any("positive finite" in error for error in errors)


def test_csv_render_hashes_pass_without_inventing_legacy_applied_policy(tmp_path: Path) -> None:
    data = tmp_path / "data.csv"
    data.write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    server = GraphHubMCPServer(
        research_root=tmp_path,
        runtime_root=tmp_path / "runtime",
        write_tools_enabled=True,
    )

    rendered = server.call_tool(
        "figops.render_csv_graph",
        {"data_path": str(data), "x_column": "x", "y_column": "y", "job_id": "wp2-five-hashes"},
    )
    assert rendered["isError"] is False, rendered["structuredContent"]
    reviewed = server.call_tool("figops.evaluate_publication_readiness", {"job_id": "wp2-five-hashes"})

    assert reviewed["isError"] is False
    report = reviewed["structuredContent"]["readiness_report"]
    assert report["readiness_status"] == "needs_review"
    assert report["applied_policies"] == []
    assert not any(item["source"] == "policy_projection" for item in report["findings"])
    manifest = json.loads(
        (tmp_path / "runtime" / "mcp_jobs" / "wp2-five-hashes" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    coverage = provenance_hash_coverage(manifest["provenance"])
    assert coverage["status"] == "passed"


@pytest.mark.parametrize(
    "template_path",
    [Path("project_config_template.yaml"), Path("hub_core/templates/project_config_template.yaml")],
)
def test_canonical_project_templates_validate_after_scaffold(template_path: Path) -> None:
    config = yaml.safe_load(template_path.read_text(encoding="utf-8"))

    assert validate_config(config) == []


def test_project_provenance_hashes_declared_input_before_script_mutation(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    original = b"x,y\n0,1\n1,2\n"
    data.write_bytes(original)
    png_text = base64.b64encode(PNG_1X1).decode("ascii")
    script = project / "plot.py"
    script.write_text(
        "from pathlib import Path\n"
        "import base64\n"
        "Path('data.csv').write_text('x,y\\n9,9\\n', encoding='utf-8')\n"
        "Path('results').mkdir(exist_ok=True)\n"
        f"Path('results/figure.png').write_bytes(base64.b64decode('{png_text}'))\n",
        encoding="utf-8",
    )
    config = {
        "project": {"name": "pre-exec provenance"},
        "visual_style": {"target_format": "nature"},
        "language_policy": {"allow_nonstandard": True, "plot_lang": "python"},
        "sample_registry": [{"sample_id": "S1"}],
        "experimental_conditions": {"conditions": [{"id": "condition_a"}]},
        "data_contract": {"csv_checks": [{"path": "data.csv", "required_columns": ["x", "y"]}]},
        "figures": [
            {
                "id": "figure",
                "script": "plot.py",
                "inputs": ["data.csv"],
                "output": "results/figure.png",
                "claim": "Fixture output is rendered.",
                "samples": ["S1"],
                "conditions": ["condition_a"],
            }
        ],
    }
    (project / "project_config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    server = GraphHubMCPServer(
        research_root=tmp_path,
        runtime_root=tmp_path / "runtime",
        write_tools_enabled=True,
    )

    rendered = server.call_tool(
        "figops.render_project_figure",
        {"project_path": "project", "figure_id": "figure", "job_id": "pre-exec-hash"},
    )

    assert rendered["isError"] is False, json.dumps(rendered["structuredContent"], ensure_ascii=False)
    manifest_path = tmp_path / "runtime" / "mcp_project_jobs" / "pre-exec-hash" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_payload = [{"path": "data.csv", "sha256": hashlib.sha256(original).hexdigest()}]
    expected = hashlib.sha256(
        json.dumps(expected_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    assert manifest["provenance"]["input_sha256"] == expected
    assert (manifest_path.parent / "project" / "data.csv").read_text(encoding="utf-8") == "x,y\n9,9\n"
