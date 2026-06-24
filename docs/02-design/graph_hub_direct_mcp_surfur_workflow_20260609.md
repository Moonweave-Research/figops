# FigOps Direct MCP Workflow For Surfur - 2026-06-09

## Decision

Use FigOps MCP directly for graph work. Do not route graph-only requests
through Athena by default.

The Surfur research folder is a master workspace, not one runnable FigOps
project:

```text
/Users/choemun-yeong/workspace/ResearchOS/02_Surfur_Polymer
```

Render through standardized subprojects that contain `project_config.yaml`,
`hub_scripts/`, and reproducible `results/data/` inputs.

## Current Gold Target

Primary MCP smoke target:

```text
ResearchOS/02_Surfur_Polymer/저항 측정/PI_control
```

Figure:

```text
FigPI_CvS_Fits
```

This target existed before FigOps became MCP-based and now serves as the
real-project acceptance check for the MCP surface.

## User-Facing Scenario

When the user says:

```text
이 프로젝트 그래프 허브로 그려줘
```

the agent should:

1. identify the concrete subproject path, not the Surfur root;
2. call `figops.inspect_project`;
3. call `figops.validate_project`;
4. run `figops.render_project_figure` with `dry_run=true`;
5. run `figops.render_project_figure`;
6. call `figops.collect_artifacts`;
7. report `status`, `manual_review_needed`, `output_path`, `manifest_path`,
   `failure_stage`, and `resolution_hint`.

## Root Workspace Rule

Do not render the Surfur root directly unless a root-level `project_config.yaml`
is intentionally added later. The root currently coordinates many submodules,
docs, references, simulation folders, and figure plans.

Valid Surfur render targets are subprojects such as:

- `저항 측정/PI_control`
- `저항 측정/260130`
- `저항 측정/PET_control`
- `저항 측정/PDMS_control`
- `유전율 측정`
- `기계적특성 측정`
- `Charge trapping 측정`

## Verification Command

From the FigOps repository:

```bash
python hub_uv.py run python - <<'PY'
from pathlib import Path
from hub_core.mcp_surface import GraphHubMCPServer

research_root = Path("/Users/choemun-yeong/workspace/ResearchOS")
project_path = research_root / "02_Surfur_Polymer" / "저항 측정" / "PI_control"
server = GraphHubMCPServer(
    research_root=research_root,
    runtime_root=Path("/Users/choemun-yeong/ws/research-runtime/graphhub-real-smoke"),
)
result = server.call_tool(
    "figops.render_project_figure",
    {
        "project_path": str(project_path),
        "figure_id": "FigPI_CvS_Fits",
        "job_id": "surfur-pi-control-smoke",
        "overwrite": True,
    },
)["structuredContent"]
print(result["status"], result["manual_review_needed"], result["output_path"])
PY
```

Expected status:

```text
ok False <runtime output path>
```

## Acceptance Criteria

- Synthetic single-panel fixture remains public-safe.
- Synthetic multipanel fixture renders through MCP without modifying source.
- Surfur PI_control renders through MCP from ResearchOS using runtime output.
- Direct MCP playbook tells agents not to call Athena for graph-only work.
