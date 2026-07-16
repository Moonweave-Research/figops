from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from hub_core.artifact_policy_measurement import measure_artifact_policy
from hub_core.claim_inventory import evaluate_project_claim_inventory
from hub_core.durable_promotion import verify_promoted_result
from hub_core.mcp import FigOpsMCPServer
from hub_core.result_promotion import ResultPromotionError, promote_eligible_project_result


def _manifest(*, job_id: str, output_sha256: str, eligible: bool = True) -> dict[str, object]:
    digest = "1" * 64
    return {
        "job_id": job_id,
        "publication_status": "verified",
        "promotion_eligible": eligible,
        "manual_review_needed": False,
        "style_summary": {"validation_target": "nature", "profile": "baseline"},
        "provenance": {
            "job_id": job_id,
            "timestamp_utc": "2026-07-16T00:00:00+00:00",
            "mcp_surface_version": "0.20.0",
            "hub_git_commit": "abc123",
            "input_sha256": digest,
            "config_sha256": "2" * 64,
            "script_sha256": "3" * 64,
            "environment_sha256": "4" * 64,
            "output_sha256": output_sha256,
        },
        "evidence": {
            "artifacts": {
                "entries": [
                    {
                        "logical_role": "primary",
                        "relative_path": "project/results/figures/Fig1.png",
                        "sha256": output_sha256,
                    }
                ]
            }
        },
        "claim_inventory": {
            "status": "verified",
            "explicit_no_claims": True,
            "claims": [],
        },
    }


def _write_compliant_png(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4328, 100), "navy").save(path, dpi=(601, 601))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_no_claim_snapshot(snapshot_root: Path) -> dict[str, object]:
    script = snapshot_root / "hub_scripts" / "plot.py"
    inventory = snapshot_root / "results" / "evidence" / "Fig1.claims.json"
    script.parent.mkdir(parents=True, exist_ok=True)
    inventory.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("from PIL import Image\n", encoding="utf-8")
    inventory.write_text(
        json.dumps(
            {
                "schema_version": "figops_claim_inventory/1",
                "figure_id": "Fig1",
                "calculation_evidence_paths": [],
                "claims": [],
            }
        ),
        encoding="utf-8",
    )
    return {
        "id": "Fig1",
        "script": "hub_scripts/plot.py",
        "output": "results/figures/Fig1.png",
        "claim_inventory": "results/evidence/Fig1.claims.json",
    }


def _bind_policy(manifest: dict[str, object], artifact: Path, digest: str) -> None:
    geometry = {
        "metric_id": "style_geometry_observations",
        "availability": "available",
        "unit": "structured",
        "scope": "figure",
        "value": {
            "figure_height_mm": 50.0,
            "font_sizes": [{"axes": 0, "role": "x_axis", "fontsize_pt": 6.0}],
            "line_widths": [
                {"axes": 0, "role": "line", "artist_index": 0, "linewidth_pt": 1.0}
            ],
        },
    }
    raw_provenance = manifest["provenance"]
    assert isinstance(raw_provenance, dict)
    producer = {"status": "passed", "kind": "test-render", "version": "0.20.0"}
    provenance = {
        "status": "passed",
        "input_sha256": raw_provenance["input_sha256"],
        "config_sha256": raw_provenance["config_sha256"],
        "script_sha256": raw_provenance["script_sha256"],
        "environment_sha256": raw_provenance["environment_sha256"],
        "output_sha256": digest,
        "unavailable_fields": [],
    }
    measured = measure_artifact_policy(
        artifact,
        validation_target="nature",
        artifact_sha256=digest,
        render_policy="neutral",
        geometry_measurements=[geometry],
        producer_binding={"producer": producer, "provenance": provenance},
        validation_profile="baseline",
    )
    evidence = manifest["evidence"]
    assert isinstance(evidence, dict)
    evidence["producer"] = producer
    evidence["provenance"] = provenance
    evidence["measurements"] = [geometry, *measured["measurements"]]
    evidence["resolved_policy"] = measured["resolved_policy"]
    evidence["policy_projections"] = [measured["policy_projection"]]


def test_eligible_runtime_result_is_promoted_with_runtime_independent_receipt(tmp_path: Path) -> None:
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    runtime_artifact = runtime / "mcp_project_jobs" / "job-a" / "project" / "results" / "figures" / "Fig1.png"
    output_sha256 = _write_compliant_png(runtime_artifact)
    snapshot_root = runtime_artifact.parents[2]
    selected = _write_no_claim_snapshot(snapshot_root)
    manifest = _manifest(job_id="job-a", output_sha256=output_sha256)
    manifest["claim_inventory"] = evaluate_project_claim_inventory(snapshot_root, selected)
    _bind_policy(manifest, runtime_artifact, output_sha256)
    manifest_path = runtime_artifact.parents[3] / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    (project / "results" / "figures").mkdir(parents=True)
    (project / "results" / "evidence").mkdir(parents=True)

    promoted = promote_eligible_project_result(
        project_root=project,
        config={"visual_style": {"validation_target": "nature"}},
        runtime_root=runtime,
        runtime_artifact=runtime_artifact,
        output_relpath="results/figures/Fig1.png",
        manifest=manifest,
        manifest_path=manifest_path,
        figure_id="Fig1",
        selected_figure=selected,
    )

    assert promoted is not None
    artifact, receipt = promoted
    assert artifact.path == project / "results" / "figures" / "Fig1.png"
    assert receipt.path.parent == project / "results" / "evidence"
    payload = receipt.path.read_text(encoding="utf-8")
    assert str(project.resolve()) not in payload
    assert str(runtime.resolve()) not in payload
    shutil.rmtree(runtime)
    verified = verify_promoted_result(
        artifact.path,
        receipt.path,
        durable_root=project / "results",
        forbidden_roots=(runtime,),
    )
    assert verified.durable_artifact["role"] == "result.figure"
    assert verified.claim_ids[0].startswith("claim:")
    assert "explicit-no-claims" not in verified.claim_ids[0]
    assert verified.publication_policy == {
        "profile_id": "journal-nature",
        "rule_version": manifest["evidence"]["resolved_policy"]["version"],
        "measurement_version": manifest["evidence"]["resolved_policy"]["parameters"][
            "measurement_version"
        ],
        "outcomes_sha256": manifest["evidence"]["resolved_policy"]["parameters"][
            "results_sha256"
        ],
    }


def test_unverified_or_review_required_runtime_result_is_never_promoted(tmp_path: Path) -> None:
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    artifact = runtime / "figure.png"
    artifact.write_bytes(b"runtime-only")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = _manifest(job_id="job-b", output_sha256=digest, eligible=False)
    manifest_path = runtime / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (project / "results" / "figures").mkdir(parents=True)

    promoted = promote_eligible_project_result(
        project_root=project,
        config={},
        runtime_root=runtime,
        runtime_artifact=artifact,
        output_relpath="results/figures/Fig1.png",
        manifest=manifest,
        manifest_path=manifest_path,
        figure_id="Fig1",
        selected_figure={"id": "Fig1"},
    )

    assert promoted is None
    assert not (project / "results" / "figures" / "Fig1.png").exists()
    assert list(project.rglob("*.receipt.json")) == []


def test_tampered_policy_projection_cannot_promote_runtime_bytes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    artifact = runtime / "job" / "Fig1.png"
    digest = _write_compliant_png(artifact)
    manifest = _manifest(job_id="job-tampered", output_sha256=digest)
    _bind_policy(manifest, artifact, digest)
    evidence = manifest["evidence"]
    assert isinstance(evidence, dict)
    projections = evidence["policy_projections"]
    assert isinstance(projections, list)
    projections[0]["findings"].append(
        {
            "code": "FORGED_PASS",
            "metric_id": "artifact.format",
            "severity": "informational",
            "outcome": "informational",
            "message": "forged",
        }
    )
    manifest_path = runtime / "job" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (project / "results" / "figures").mkdir(parents=True)
    (project / "results" / "evidence").mkdir(parents=True)

    with pytest.raises(ResultPromotionError, match="failed recomputation"):
        promote_eligible_project_result(
            project_root=project,
            config={"visual_style": {"validation_target": "nature"}},
            runtime_root=runtime,
            runtime_artifact=artifact,
            output_relpath="results/figures/Fig1.png",
            manifest=manifest,
            manifest_path=manifest_path,
            figure_id="Fig1",
            selected_figure={"id": "Fig1"},
        )

    assert not (project / "results" / "figures" / "Fig1.png").exists()
    assert list((project / "results" / "evidence").glob("*.receipt.json")) == []


def test_in_memory_manifest_must_equal_persisted_runtime_manifest(tmp_path: Path) -> None:
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    artifact = runtime / "job" / "Fig1.png"
    digest = _write_compliant_png(artifact)
    persisted = _manifest(job_id="job-manifest", output_sha256=digest)
    manifest_path = runtime / "job" / "manifest.json"
    manifest_path.write_text(json.dumps(persisted), encoding="utf-8")
    inspected = dict(persisted)
    inspected["summary"] = "forged-after-write"
    (project / "results" / "figures").mkdir(parents=True)

    with pytest.raises(ResultPromotionError, match="persisted runtime manifest"):
        promote_eligible_project_result(
            project_root=project,
            config={"visual_style": {"validation_target": "nature"}},
            runtime_root=runtime,
            runtime_artifact=artifact,
            output_relpath="results/figures/Fig1.png",
            manifest=inspected,
            manifest_path=manifest_path,
            figure_id="Fig1",
            selected_figure={"id": "Fig1"},
        )

    assert not (project / "results" / "figures" / "Fig1.png").exists()


def test_trusted_config_rejects_manifest_selected_target_substitution(tmp_path: Path) -> None:
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    artifact = runtime / "job" / "project" / "results" / "figures" / "Fig1.png"
    digest = _write_compliant_png(artifact)
    snapshot_root = artifact.parents[2]
    selected = _write_no_claim_snapshot(snapshot_root)
    manifest = _manifest(job_id="job-target-substitution", output_sha256=digest)
    manifest["claim_inventory"] = evaluate_project_claim_inventory(snapshot_root, selected)
    _bind_policy(manifest, artifact, digest)
    manifest_path = runtime / "job" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (project / "results" / "figures").mkdir(parents=True)
    (project / "results" / "evidence").mkdir(parents=True)

    with pytest.raises(ResultPromotionError, match="trusted project validation target"):
        promote_eligible_project_result(
            project_root=project,
            config={"visual_style": {"validation_target": "science", "profile": "baseline"}},
            runtime_root=runtime,
            runtime_artifact=artifact,
            output_relpath="results/figures/Fig1.png",
            manifest=manifest,
            manifest_path=manifest_path,
            figure_id="Fig1",
            selected_figure=selected,
        )

    assert not (project / "results" / "figures" / "Fig1.png").exists()
    assert list((project / "results" / "evidence").glob("*.receipt.json")) == []


def test_forged_top_level_eligibility_cannot_override_nested_claim_failure(tmp_path: Path) -> None:
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    artifact = runtime / "job" / "project" / "results" / "figures" / "Fig1.png"
    digest = _write_compliant_png(artifact)
    snapshot_root = artifact.parents[2]
    selected = _write_no_claim_snapshot(snapshot_root)
    manifest = _manifest(job_id="job-nested-claim-forgery", output_sha256=digest)
    _bind_policy(manifest, artifact, digest)
    manifest["claim_inventory"] = {
        "status": "unverified",
        "promotion_eligible": False,
        "manual_review_needed": True,
        "errors": ["forged nested failure"],
        "claims": [],
    }
    manifest_path = runtime / "job" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    (project / "results" / "figures").mkdir(parents=True)
    (project / "results" / "evidence").mkdir(parents=True)

    with pytest.raises(ResultPromotionError, match="nested claim inventory"):
        promote_eligible_project_result(
            project_root=project,
            config={"visual_style": {"validation_target": "nature", "profile": "baseline"}},
            runtime_root=runtime,
            runtime_artifact=artifact,
            output_relpath="results/figures/Fig1.png",
            manifest=manifest,
            manifest_path=manifest_path,
            figure_id="Fig1",
            selected_figure=selected,
        )

    assert not (project / "results" / "figures" / "Fig1.png").exists()
    assert list((project / "results" / "evidence").glob("*.receipt.json")) == []


def test_verified_claim_lineage_membership_is_copied_into_runtime_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "research" / "project"
    snapshot = tmp_path / "runtime" / "job" / "project"
    members = {
        "project_config.yaml": "project: {name: membership}\n",
        "hub_scripts/plot.py": "# render\n",
        "analysis/calculate.py": "# calculation producer\n",
        "analysis/calculation.yaml": "model: welch\n",
        "raw/observations.csv": "group,value\na,1\nb,2\n",
        "results/evidence/claim-result.json": '{"status":"passed"}\n',
    }
    for declaration, content in members.items():
        path = source / declaration
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    lineage_ref = "results/evidence/claim-lineage.json"
    lineage = {
        "calculation_artifact": {"path": "results/evidence/claim-result.json"},
        "producer": {
            "script": {"path": "analysis/calculate.py"},
            "config": {"path": "analysis/calculation.yaml"},
        },
        "input_artifacts": [{"path": "raw/observations.csv"}],
        "output_artifacts": [{"path": "results/evidence/claim-result.json"}],
    }
    (source / lineage_ref).write_text(json.dumps(lineage), encoding="utf-8")
    inventory_ref = "results/evidence/Fig1.claims.json"
    (source / inventory_ref).write_text(
        json.dumps({"calculation_evidence_paths": [lineage_ref]}),
        encoding="utf-8",
    )
    server = FigOpsMCPServer(
        research_root=source.parent,
        runtime_root=tmp_path / "runtime",
    )

    copied = server._copy_project_snapshot(
        source_project=source,
        snapshot_project=snapshot,
        config_relpath="project_config.yaml",
        selected_figure={
            "id": "Fig1",
            "script": "hub_scripts/plot.py",
            "inputs": [],
            "claim_inventory": inventory_ref,
        },
        claim_inventory={"status": "verified", "artifact_ref": inventory_ref},
    )

    copied_members = {Path(path).relative_to(snapshot).as_posix() for path in copied}
    assert {
        inventory_ref,
        lineage_ref,
        "analysis/calculate.py",
        "analysis/calculation.yaml",
        "raw/observations.csv",
        "results/evidence/claim-result.json",
    } <= copied_members


def test_project_render_production_caller_promotes_only_after_clean_gates(tmp_path: Path) -> None:
    research = tmp_path / "research"
    project = research / "project"
    runtime = tmp_path / "runtime"
    (project / "hub_scripts").mkdir(parents=True)
    (project / "results" / "data").mkdir(parents=True)
    (project / "results" / "evidence").mkdir(parents=True)
    (project / "results" / "data" / "summary.csv").write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    (project / "hub_scripts" / "plot.py").write_text(
        "from pathlib import Path\n"
        "import matplotlib.pyplot as plt\n"
        "from themes.journal_theme import save_journal_fig\n"
        "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
        "fig, ax = plt.subplots(figsize=(3, 2))\n"
        "ax.plot([0, 1], [0, 1], linewidth=1.0)\n"
        "ax.set_xlabel('x', fontsize=6)\n"
        "ax.set_ylabel('y', fontsize=6)\n"
        "ax.tick_params(labelsize=6, width=1.0)\n"
        "save_journal_fig(fig, 'results/figures/Fig1.png', dpi=601)\n"
        "plt.close(fig)\n",
        encoding="utf-8",
    )
    (project / "results" / "evidence" / "Fig1.claims.json").write_text(
        json.dumps(
            {
                "schema_version": "figops_claim_inventory/1",
                "figure_id": "Fig1",
                "calculation_evidence_paths": [],
                "claims": [],
            }
        ),
        encoding="utf-8",
    )
    (project / "project_config.yaml").write_text(
        "project:\n"
        "  name: Promotion integration\n"
        "visual_style:\n"
        "  target_format: neutral\n"
        "  profile: baseline\n"
        "  validation_target: nature\n"
        "sample_registry:\n"
        "  - sample_id: S1\n"
        "experimental_conditions:\n"
        "  conditions:\n"
        "    - id: condition_a\n"
        "data_contract:\n"
        "  csv_checks:\n"
        "    - path: results/data/summary.csv\n"
        "      required_columns: [x, y]\n"
        "      dtypes: {x: number, y: number}\n"
        "  require_figure_traceability: false\n"
        "figures:\n"
        "  - id: Fig1\n"
        "    script: hub_scripts/plot.py\n"
        "    inputs: [results/data/summary.csv]\n"
        "    output: results/figures/Fig1.png\n"
        "    claim_inventory: results/evidence/Fig1.claims.json\n"
        "    samples: [S1]\n"
        "    conditions: [condition_a]\n",
        encoding="utf-8",
    )
    server = FigOpsMCPServer(
        research_root=research,
        runtime_root=runtime,
        write_tools_enabled=True,
        surface_profile="v2",
    )
    server._visual_preflight_with_geometry_overlaps = lambda *_args: {
        "passed": True,
        "checks": [],
        "warnings": [],
        "target": "nature",
    }
    response = server.call_tool(
        "figops.render_project_script",
        {
            "project_path": str(project),
            "figure_id": "Fig1",
            "job_id": "promote-clean-result",
            "validation_target": "nature",
        },
    )["structuredContent"]

    assert response["status"] == "ok", response
    durable_figure = project / "results" / "figures" / "Fig1.png"
    receipts = list((project / "results" / "evidence").glob("*.receipt.json"))
    assert durable_figure.is_file()
    assert len(receipts) == 1
    verify_promoted_result(
        durable_figure,
        receipts[0],
        durable_root=project / "results",
        forbidden_roots=(runtime,),
    )
    assert (runtime / "mcp_project_jobs" / "promote-clean-result" / "manifest.json").is_file()
    assert (
        runtime
        / "mcp_project_jobs"
        / "promote-clean-result"
        / "project"
        / "results"
        / "evidence"
        / "Fig1.claims.json"
    ).is_file()
