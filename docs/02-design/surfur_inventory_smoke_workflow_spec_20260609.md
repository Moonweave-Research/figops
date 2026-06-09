# Surfur Inventory And Smoke Workflow Spec - 2026-06-09

## Goal

Make the Surfur graph workflow operational through Graph Hub MCP without using
Athena as a graph router.

## Scope

- Build a figure-target inventory from Surfur subproject `project_config.yaml`
  files.
- Identify render candidates from configured scripts and inputs, including
  MCP-compatible `script::entrypoint` and single `input` aliases.
- Follow symlinked project directories during discovery, while marking
  symlinked snapshot support paths as non-candidates because MCP project
  snapshots reject symlinks during export.
- Resolve legacy `scripts/project_config.yaml` from the project root.
- Keep the Surfur root as a master workspace, not a direct render target.
- Keep `저항 측정/PI_control` `FigPI_CvS_Fits` as the current real-project
  gold smoke.

## Workflow Loop

1. Inventory:
   `scripts/project_figure_inventory.py` scans the Surfur root with symlink
   traversal and writes markdown/JSON target lists.
2. Review:
   Check candidate rows for missing inputs, missing scripts, and stale outputs.
3. Smoke:
   Render one high-confidence target through `graphhub.render_project_figure`
   into a runtime root.
4. Update:
   Refresh the inventory after project configs or generated data change.
5. Repeat:
   Promote the next candidate only after validation and visual review.

## Acceptance Criteria

- Inventory lists all configured Surfur figure targets visible under the root.
- Inventory marks render candidates only when script and inputs exist.
- Inventory does not mark rows as render candidates when `project_config.yaml`,
  the selected script, declared inputs, `hub_scripts/`, or `results/data/`
  contain symlinks.
- Inventory handles both root-level `project_config.yaml` and legacy
  `scripts/project_config.yaml`.
- Invalid or unreadable configs are surfaced as non-candidate inventory rows
  instead of being silently omitted.
- Current PI_control gold target renders through Graph Hub MCP.
- Generated inventory documents the exact MCP call sequence.
