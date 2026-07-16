from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hub_core.mcp import FigOpsMCPServer
from hub_core.render_evidence import build_render_evidence


def _write_project(
    root: Path,
    *,
    claim_inventory: bool,
    dpi: int = 300,
    geometry_mode: str = "direct",
    validation_target: str | None = None,
    declare_claim: bool = True,
) -> Path:
    project = root / "project"
    (project / "hub_scripts").mkdir(parents=True)
    (project / "results" / "data").mkdir(parents=True)
    (project / "results" / "evidence").mkdir(parents=True)
    (project / "results" / "data" / "summary.csv").write_text(
        "x,y\n0,1\n1,2\n",
        encoding="utf-8",
    )
    if geometry_mode in {"compliant", "tiny-sidecar"}:
        font_size = 6 if geometry_mode == "compliant" else 1
        line_width = 1.0 if geometry_mode == "compliant" else 0.01
        script = (
            "from pathlib import Path\n"
            "import matplotlib.pyplot as plt\n"
            "from themes.journal_theme import save_journal_fig\n"
            "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
            "fig, ax = plt.subplots(figsize=(3, 2))\n"
            f"ax.plot([0, 1], [0, 1], linewidth={line_width})\n"
            f"ax.set_xlabel('x', fontsize={font_size})\n"
            f"ax.set_ylabel('y', fontsize={font_size})\n"
            f"ax.tick_params(labelsize={font_size}, width={line_width})\n"
            f"save_journal_fig(fig, 'results/figures/Fig1.png', dpi={dpi})\n"
            "plt.close(fig)\n"
        )
    elif geometry_mode == "tiny-direct":
        script = (
            "from pathlib import Path\n"
            "import matplotlib.pyplot as plt\n"
            "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
            "fig, ax = plt.subplots(figsize=(3, 2))\n"
            "ax.plot([0, 1], [0, 1], linewidth=0.01)\n"
            "ax.set_xlabel('tiny', fontsize=1)\n"
            f"fig.savefig('results/figures/Fig1.png', format='PNG', dpi={dpi})\n"
            "plt.close(fig)\n"
        )
    else:
        script = (
            "from pathlib import Path\n"
            "from PIL import Image\n"
            "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
            "Image.new('RGB', (640, 480), 'navy').save("
            f"'results/figures/Fig1.png', format='PNG', dpi=({dpi}, {dpi}))\n"
        )
    (project / "hub_scripts" / "plot.py").write_text(script, encoding="utf-8")
    inventory_line = "    claim_inventory: results/evidence/Fig1.claims.json\n" if claim_inventory else ""
    claim_line = "    claim: Fixture render completes.\n" if declare_claim else ""
    validation_line = f"  validation_target: {validation_target}\n" if validation_target else ""
    (project / "project_config.yaml").write_text(
        "project:\n"
        "  name: Project policy integration\n"
        "visual_style:\n"
        "  target_format: nature\n"
        "  profile: baseline\n"
        f"{validation_line}"
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
        f"{claim_line}"
        f"{inventory_line}"
        "    samples: [S1]\n"
        "    conditions: [condition_a]\n",
        encoding="utf-8",
    )
    if claim_inventory:
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
    return project


def _render(
    tmp_path: Path,
    *,
    job_id: str,
    claim_inventory: bool,
    validation_target: str | None = None,
    dpi: int = 300,
    geometry_mode: str = "direct",
    declare_claim: bool = True,
):
    research_root = tmp_path / "research"
    project = _write_project(
        research_root,
        claim_inventory=claim_inventory,
        dpi=dpi,
        geometry_mode=geometry_mode,
        validation_target=validation_target,
        declare_claim=declare_claim,
    )
    runtime_root = tmp_path / "runtime"
    server = FigOpsMCPServer(
        research_root=research_root,
        runtime_root=runtime_root,
        write_tools_enabled=True,
    )
    arguments = {
        "project_path": str(project),
        "figure_id": "Fig1",
        "job_id": job_id,
    }
    if validation_target is not None:
        arguments["validation_target"] = validation_target
    response = server.call_tool("figops.render_project_script", arguments)["structuredContent"]
    manifest_path = runtime_root / "mcp_project_jobs" / job_id / "manifest.json"
    return response, json.loads(manifest_path.read_text(encoding="utf-8"))


def test_v2_project_render_is_neutral_and_exploratory_without_validation_target(tmp_path: Path) -> None:
    response, manifest = _render(
        tmp_path,
        job_id="project-exploratory",
        claim_inventory=True,
    )

    assert response["status"] == "warning", (response, manifest)
    assert response["evidence"]["resolved_policy"]["id"] == "render-neutral"
    assert response["evidence"]["policy_projections"] == []
    assert manifest["style_summary"]["target_format"] == "neutral"
    assert manifest["style_summary"]["render_policy"] == "render-neutral"
    assert manifest["style_summary"]["validation_target"] is None
    assert manifest["claim_inventory"]["status"] == "unverified"
    assert manifest["publication_status"] == "unverified"
    assert manifest["promotion_eligible"] is False
    assert manifest["manual_review_needed"] is True


def test_publication_projection_is_persisted_and_unverified_claims_block_promotion(tmp_path: Path) -> None:
    response, manifest = _render(
        tmp_path,
        job_id="project-publication",
        claim_inventory=False,
        validation_target="nature",
    )

    assert response["status"] == "warning", (response, manifest)
    evidence = response["evidence"]
    assert evidence == manifest["evidence"]
    assert evidence["resolved_policy"]["id"] == "journal-nature"
    parameters = evidence["resolved_policy"]["parameters"]
    assert parameters["validation_target"] == "nature"
    assert parameters["render_policy"] == "render-neutral"
    assert parameters["artifact_sha256"] == response["artifact"]["sha256"]
    assert len(evidence["policy_projections"]) == 1
    assert evidence["policy_projections"][0]["id"] == "journal-nature"
    assert manifest["style_summary"]["target_format"] == "neutral"
    assert manifest["style_summary"]["validation_target"] == "nature"
    assert manifest["claim_inventory"]["status"] == "unverified"
    assert manifest["publication_status"] == "unverified"
    assert manifest["promotion_eligible"] is False
    assert manifest["manual_review_needed"] is True


def test_publication_missing_projection_blocks_promotion_with_verified_claims(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    research_root = tmp_path / "research"
    project = _write_project(
        research_root,
        claim_inventory=True,
        validation_target="nature",
        declare_claim=False,
    )
    runtime_root = tmp_path / "runtime"
    server = FigOpsMCPServer(
        research_root=research_root,
        runtime_root=runtime_root,
        write_tools_enabled=True,
    )
    def without_projection(*args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs["validation_target"] = None
        return build_render_evidence(*args, **kwargs)

    monkeypatch.setattr(
        "hub_core.mcp.tools.render_project.build_render_evidence",
        without_projection,
    )
    response = server.call_tool(
        "figops.render_project_script",
        {
            "project_path": str(project),
            "figure_id": "Fig1",
            "job_id": "project-missing-projection",
            "validation_target": "nature",
        },
    )["structuredContent"]
    manifest = json.loads(
        (runtime_root / "mcp_project_jobs" / "project-missing-projection" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert response["status"] == "warning"
    assert response["evidence"]["policy_projections"] == []
    assert manifest["claim_inventory"]["status"] == "verified"
    assert manifest["publication_status"] == "verified"
    assert manifest["promotion_eligible"] is False
    assert manifest["manual_review_needed"] is True


def test_passing_measured_journal_minima_make_verified_claims_promotion_eligible(
    tmp_path: Path,
) -> None:
    response, manifest = _render(
        tmp_path,
        job_id="project-promotion-ready",
        claim_inventory=True,
        validation_target="nature",
        dpi=600,
        geometry_mode="compliant",
        declare_claim=False,
    )

    assert "evidence" in manifest, (response, manifest)
    projection = manifest["evidence"]["policy_projections"][0]
    assert projection["status"] == "informational"
    assert manifest["manual_review_needed"] is False
    assert manifest["promotion_eligible"] is True
    project = tmp_path / "research" / "project"
    assert (project / "results" / "figures" / "Fig1.png").is_file()
    assert len(list((project / "results" / "evidence").glob("*.receipt.json"))) == 1


def test_direct_tiny_font_and_line_without_geometry_sidecar_blocks_promotion(
    tmp_path: Path,
) -> None:
    _, manifest = _render(
        tmp_path,
        job_id="project-tiny-direct-blocked",
        claim_inventory=True,
        validation_target="nature",
        dpi=600,
        geometry_mode="tiny-direct",
        declare_claim=False,
    )

    results = manifest["evidence"]["resolved_policy"]["parameters"]["results"]
    assert manifest["evidence"]["policy_projections"][0]["status"] == "needs_review"
    assert all(
        item["status"] == "not_applicable"
        for item in results
        if item["check_id"] in {"minimum_font_size", "minimum_line_width"}
    )
    assert manifest["promotion_eligible"] is False
    assert not (tmp_path / "research" / "project" / "results" / "figures" / "Fig1.png").exists()


def test_bound_geometry_diagnostics_reject_tiny_font_and_line(
    tmp_path: Path,
) -> None:
    _, manifest = _render(
        tmp_path,
        job_id="project-tiny-sidecar-blocked",
        claim_inventory=True,
        validation_target="nature",
        dpi=600,
        geometry_mode="tiny-sidecar",
        declare_claim=False,
    )

    results = manifest["evidence"]["resolved_policy"]["parameters"]["results"]
    assert manifest["evidence"]["policy_projections"][0]["status"] == "blocked"
    assert {
        item["check_id"]
        for item in results
        if item["status"] == "fail"
    } >= {"minimum_font_size", "minimum_line_width"}
    assert manifest["promotion_eligible"] is False


def test_failed_required_journal_minimum_blocks_verified_claim_promotion(
    tmp_path: Path,
) -> None:
    _, manifest = _render(
        tmp_path,
        job_id="project-promotion-blocked",
        claim_inventory=True,
        validation_target="nature",
        dpi=300,
        declare_claim=False,
    )

    projection = manifest["evidence"]["policy_projections"][0]
    assert projection["status"] == "blocked"
    assert manifest["promotion_eligible"] is False
