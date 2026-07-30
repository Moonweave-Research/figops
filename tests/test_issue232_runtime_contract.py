from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from hub_core.mcp.render_response import _project_result_contract
from hub_core.mcp.schemas import list_tool_definitions
from hub_core.mcp.server import FigOpsMCPServer


def _write_project(root: Path, *, workflow_intent: str | None = None) -> Path:
    project = root / "01_contract"
    (project / "hub_scripts").mkdir(parents=True)
    (project / "results" / "data").mkdir(parents=True)
    (project / "results" / "data" / "summary.csv").write_text("x,y\n0,1\n1,2\n", encoding="utf-8")
    workflow = f"workflow:\n  intent: {workflow_intent}\n" if workflow_intent else ""
    (project / "hub_scripts" / "plot.py").write_text(
        "from pathlib import Path\n"
        "from PIL import Image\n"
        "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
        "Image.new('RGB', (32, 24), 'navy').save('results/figures/Fig1.png', format='PNG')\n",
        encoding="utf-8",
    )
    (project / "project_config.yaml").write_text(
        f"""
project:
  name: Contract Fixture
{workflow}visual_style:
  target_format: nature
  profile: baseline
sample_registry:
  - sample_id: S1
experimental_conditions:
  conditions:
    - id: condition_a
data_contract:
  csv_checks:
    - path: results/data/summary.csv
      required_columns: [x, y]
      dtypes: {{x: number, y: number}}
figures:
  - id: Fig1
    script: hub_scripts/plot.py
    inputs: [results/data/summary.csv]
    output: results/figures/Fig1.png
    claim: Contract fixture render completes.
    samples: [S1]
    conditions: [condition_a]
""",
        encoding="utf-8",
    )
    return project


def _render(server: FigOpsMCPServer, project: Path, job_id: str) -> dict:
    return server.render_project_script(
        {
            "project_path": str(project),
            "figure_id": "Fig1",
            "style_policy": "nature",
            "job_id": job_id,
        }
    )


def test_v2_render_response_distinguishes_runtime_only_result_and_preserves_source(tmp_path: Path) -> None:
    project = _write_project(tmp_path / "ResearchOS")
    before = hashlib.sha256((project / "project_config.yaml").read_bytes()).hexdigest()
    runtime = tmp_path / "runtime"
    server = FigOpsMCPServer(
        research_root=tmp_path / "ResearchOS",
        runtime_root=runtime,
        write_tools_enabled=True,
        surface_profile="v2",
    )

    result = _render(server, project, "contract-runtime-only")

    assert result["status"] in {"ok", "warning"}
    assert result["promotion_eligible"] is False
    assert result["source_unchanged"] is True
    assert result["overwrite_scope"] == "job_workspace_only"
    runtime_artifact = result["runtime_artifact"]
    assert runtime_artifact["status"] == "created"
    assert runtime_artifact["source"] == "runtime_snapshot"
    assert runtime_artifact["uri"].startswith("runtime://")
    assert str(runtime) not in runtime_artifact["uri"]
    assert len(runtime_artifact["sha256"]) == 64
    durable = result["durable_result"]
    assert durable["status"] == "not_promoted"
    assert durable["relative_path"] is None
    assert durable["reason_code"] == "PROMOTION_NOT_ELIGIBLE"
    assert hashlib.sha256((project / "project_config.yaml").read_bytes()).hexdigest() == before


def test_exploration_render_is_explicitly_non_promotable(tmp_path: Path) -> None:
    project = _write_project(tmp_path / "ResearchOS", workflow_intent="exploration")
    server = FigOpsMCPServer(
        research_root=tmp_path / "ResearchOS",
        runtime_root=tmp_path / "runtime",
        write_tools_enabled=True,
        surface_profile="v2",
    )

    result = _render(server, project, "contract-exploration")

    assert result["status"] in {"ok", "warning"}
    assert result["promotion_eligible"] is False
    assert result["durable_result"]["status"] == "not_promoted"
    assert result["durable_result"]["reason_code"] == "EXPLORATION_NON_PROMOTABLE"
    assert result["promotion_status"] == "not_promoted"


def test_eligible_render_reports_durable_result_without_host_path(monkeypatch, tmp_path: Path) -> None:
    project = _write_project(tmp_path / "ResearchOS")
    runtime = tmp_path / "runtime"
    server = FigOpsMCPServer(
        research_root=tmp_path / "ResearchOS",
        runtime_root=runtime,
        write_tools_enabled=True,
        surface_profile="v2",
    )
    monkeypatch.setattr(
        "hub_core.mcp.tools.render_project.integrity_context.decide_project_render_promotion_eligibility",
        lambda **_kwargs: {
            "manual_review_needed": False,
            "policy_review_needed": False,
            "projection_ready": True,
            "promotion_eligible": True,
            "workflow_execution_allowed": True,
            "workflow_review_needed": False,
        },
    )
    durable_output = project / "results" / "figures" / "Fig1.png"
    durable_receipt = project / "results" / "evidence" / "Fig1.receipt.json"
    monkeypatch.setattr(
        "hub_core.mcp.tools.render_project.promote_eligible_project_result",
        lambda **_kwargs: (
            SimpleNamespace(path=durable_output),
            SimpleNamespace(path=durable_receipt),
        ),
    )

    result = _render(server, project, "contract-promoted")

    assert result["promotion_eligible"] is True
    assert result["runtime_artifact"]["source"] == "runtime_snapshot"
    assert result["durable_result"] == {
        "status": "promoted",
        "relative_path": "results/figures/Fig1.png",
        "reason_code": None,
        "reason": None,
        "source": "durable_project_result",
    }
    assert result["source_unchanged"] is True
    assert str(tmp_path) not in str(result["durable_result"])


def test_project_render_schema_documents_workspace_only_overwrite() -> None:
    definitions = {item["name"]: item for item in list_tool_definitions()}
    legacy = definitions["figops.render_project_figure"]
    v2 = definitions["figops.render_project_script"]
    basic_output = definitions["figops.render_basic_csv"]["outputSchema"]["properties"]
    assert "runtime_artifact" not in basic_output
    assert "durable_result" not in basic_output
    assert basic_output["failure_stage"]["type"] == ["string", "null"]
    assert basic_output["resolution_hint"]["type"] == ["string", "null"]
    for definition in (legacy, v2):
        description = definition["inputSchema"]["properties"]["overwrite"]["description"]
        assert "job workspace only" in description
        assert "never overwrite" in description
    output = legacy["outputSchema"]["properties"]
    assert {"runtime_artifact", "durable_result", "source_unchanged", "overwrite_scope"} <= set(output)
    assert output["failure_stage"]["type"] == ["string", "null"]
    assert output["resolution_hint"]["type"] == ["string", "null"]


def test_runtime_uri_sanitization_rejects_host_and_traversal_paths() -> None:
    normal = _project_result_contract(
        {
            "status": "created",
            "uri": "runtime://jobs/x/artifact.png",
            "relative_path": "project/artifact.png",
            "source": "runtime_snapshot",
        }
    )
    assert normal is not None
    assert normal["uri"] == "runtime://jobs/x/artifact.png"

    for malicious in ("runtime://../host", "runtime:///absolute", "runtime://C:/host/file.png"):
        result = _project_result_contract(
            {
                "status": "created",
                "uri": malicious,
                "relative_path": "project/artifact.png",
                "source": "runtime_snapshot",
            }
        )
        assert result is not None
        assert result["uri"] is None
