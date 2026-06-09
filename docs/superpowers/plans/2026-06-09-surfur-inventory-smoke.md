# Surfur Inventory And Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run the Surfur figure-target inventory and MCP smoke loop.

**Architecture:** Add a small read-only inventory script that parses
`project_config.yaml` files and emits markdown/JSON reports. Keep actual figure
rendering in Graph Hub MCP runtime snapshots.

**Tech Stack:** Python 3.12, PyYAML, pytest, ruff, GraphHubMCPServer.

---

### Task 1: Inventory Script

**Files:**
- Create: `scripts/project_figure_inventory.py`
- Test: `tests/test_project_figure_inventory.py`

- [x] **Step 1: Add inventory tests**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_project_figure_inventory.py -v
```

Expected: tests pass and prove render-candidate marking.

- [x] **Step 2: Add script**

The script discovers `project_config.yaml`, parses `figures[]`, checks scripts,
inputs, outputs, and writes markdown/JSON.

- [x] **Step 3: Review-loop hardening**

The implementation follows symlinked project directories, resolves legacy
`scripts/project_config.yaml` from the project root, normalizes Korean paths to
NFC, and refuses to mark symlinked scripts or declared inputs as render
candidates.

### Task 2: Surfur Generated Inventory

**Files:**
- Create: `docs/02-design/surfur_graphhub_mcp_targets_20260609.md`
- Create: `docs/02-design/surfur_graphhub_mcp_targets_20260609.json`

- [x] **Step 1: Generate inventory**

Run:

```bash
python hub_uv.py run python scripts/project_figure_inventory.py \
  /Users/choemun-yeong/workspace/ResearchOS/02_Surfur_Polymer \
  --markdown-out docs/02-design/surfur_graphhub_mcp_targets_20260609.md \
  --json-out docs/02-design/surfur_graphhub_mcp_targets_20260609.json
```

Expected: inventory documents Surfur subproject figure targets.

### Task 3: Real-Project Smoke

**Files:**
- Read-only runtime verification.

- [x] **Step 1: Render PI_control gold target**

Run:

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
    "graphhub.render_project_figure",
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

Expected: `ok False <runtime output path>`.
