# 07 Athena Client Migration Workflow

- Status: Required migration workflow after live ResearchOS audit
- Depends on: `00_protocol_and_safety_contract.md`, `01_phase0_truth_surface_repair.md`, `02_phase1_read_only_mcp.md`
- Purpose: separate FigOps ownership from Athena orchestration without losing current bridge behavior

## Decision

FigOps should become the independently callable graph engine. Athena should become a client of FigOps, not the owner of FigOps project structure, style validation, temporary Hub project writing, or render execution.

The physical split has now started: FigOps is an independent clone at `/Users/choemun-yeong/workspace/figops`, while Athena remains in the ResearchOS workspace. Treat any remaining `[Graph_making_hub]` path as a legacy compatibility reference, not as the current code owner.

## Current Bridge Shape

Current Athena-to-Hub path:

```text
Athena command / visualization flow
  -> integrations.hub_bridge
  -> integrations.hub_project_writer
  -> integrations.hub_runner
  -> FigOps orchestrator.py
  -> FigOps core rendering and artifacts
```

This path works and must remain available while MCP parity is built.

Current FigOps-to-Athena path:

```text
FigOps hub_core.athena_bridge
  -> imports Athena visualizer engine
  -> renders Athena-style diagrams from Hub specs
```

This path is useful but increases coupling. Treat it as a transitional adapter or plugin candidate, not as the core FigOps ownership model.

## Migration Principles

1. Preserve existing Athena bridge behavior until an MCP path proves equivalent output and diagnostics.
2. Move ownership of style, discovery, validation, execution, provenance, and artifacts to FigOps.
3. Make Athena depend on FigOps through a typed client interface, not by duplicating FigOps enums or file layout assumptions.
4. Keep read-only inspection side-effect free.
5. Run write/render jobs only under an external runtime root unless a user explicitly chooses a project apply operation.
6. Do not delete `hub_bridge`, `hub_project_writer`, or `hub_runner` until a compatibility test proves the MCP replacement covers the same scenarios.

## Workflow

### Step 0 - Contract Alignment

Goal: remove known contract mismatch before MCP wrapping.

Required:

- Athena accepts every FigOps official target format.
- A parity test compares Athena's bridge target format set with FigOps's `ALLOWED_TARGET_FORMATS`.
- `nature_surfur` is explicitly tested.
- Unsupported values such as `baseline` and `ieee` remain rejected.

### Step 1 - Read-Only FigOps MCP

Goal: let Athena inspect Hub state without writing files.

Athena should first call:

- `figops.health`
- `figops.list_styles`
- `figops.list_projects`
- `figops.inspect_project`
- `figops.validate_project`

Do not replace rendering yet.

### Step 2 - Athena Client Adapter

Goal: introduce an Athena-side FigOps client that can use MCP when available and fall back to the existing bridge when not.

The Athena caller should know only:

- figure spec,
- data source,
- requested style,
- render mode,
- returned manifest/resource links.

It should not need to know the Hub temporary project layout.

### Step 3 - Controlled Render Parity

Goal: add `figops.render_ephemeral` or `figops.render_csv_graph` and prove it matches the current bridge.

Parity checks:

- same accepted target formats,
- same output path semantics,
- same project config validation,
- same artifact collection,
- same failure-stage taxonomy,
- same manual-review/preflight status.

### Step 4 - Deprecate Direct Project Writer

Goal: stop Athena from constructing Hub project folders directly.

Only after Step 3 passes:

- mark `hub_project_writer` as compatibility-only,
- route normal Athena graph rendering through FigOps MCP,
- keep fallback for emergency/local operation until a release checkpoint.

### Step 5 - Review Reverse Imports

Goal: reduce FigOps-to-Athena coupling.

Options:

- keep `hub_core.athena_bridge` as an optional plugin adapter,
- move Athena-style diagram rendering into FigOps,
- or expose the Athena visualizer as a separate typed tool that FigOps calls intentionally.

Do not mix this with the first MCP render rollout.

## Acceptance Criteria

- Existing Athena bridge smoke still succeeds.
- `nature_surfur` can flow through Athena into FigOps.
- FigOps read-only MCP calls do not change git status.
- Athena can list FigOps styles/projects through MCP or a compatibility client.
- Render replacement is not considered done until output files, manifests, and failure diagnostics match the current bridge path.
- The final architecture has one graph contract owner: FigOps.
