# 03 Phase 2 Controlled Rendering

- Status: Starts only after Phase 1 read-only tools pass no-write tests
- Depends on: `00_protocol_and_safety_contract.md`, `01_phase0_truth_surface_repair.md`, `02_phase1_read_only_mcp.md`
- Blocks: Phase 3 normalization

## Goal

Support "structured CSV in, publication-style graph out" without touching source project trees.

This phase validates that MCP can call existing Graph Hub rendering behavior safely. It does not analyze arbitrary raw instrument files and does not normalize real project folders.

## Tools

### `graphhub.render_csv_graph`

Creates a temporary Hub-compatible job from a structured table and a figure spec.

Inputs:

- `data_path`
- `x_column`
- `y_column`
- `plot_type`
- `target_format`
- `profile`
- `output_format`
- `semantic_checks`
- `dry_run`: default `false`

Behavior:

- copies or links input into an MCP job workspace,
- writes a minimal `project_config.yaml`,
- runs the existing bridge renderer through Graph Hub,
- stores output under the runtime root,
- returns artifact paths and preflight status.

### `graphhub.collect_artifacts`

Returns artifact metadata after a render job.

Result fields:

- `figures`
- `diagrams`
- `assemblies`
- `logs`
- `provenance`
- `visual_preflight_status`
- `manual_review_needed`

## Runtime Rules

- All generated jobs run under `$RESEARCH_HUB_RUNTIME_ROOT/mcp_jobs/` or the documented fallback cache path.
- No temporary rendering job may create `.venv`, `.r_libs`, DVC state, or long-lived cache directories inside source project trees.
- Job manifests must record created, modified, and skipped paths.
- Outputs must include artifact path, config path, log path, style summary, and visual preflight status.
- CSV inputs have a bounded size limit. The default is 64 MiB and operators may lower or raise it with `GRAPH_HUB_MCP_RENDER_CSV_MAX_BYTES`.
- Bridge rendering runs behind a bounded execution timeout. A timeout returns a normal tool execution error instead of leaving the call open-ended.
- Diagnostic errors and warnings must not expose raw local source, hub, or runtime root paths. Returned artifact resources and explicit output paths may remain concrete paths or `file://` resources.

## Style Preservation

Rendering must use Graph Hub's canonical style contract.

The tool must accept the same target formats as Graph Hub core, including `nature_surfur`. It must not use a smaller Athena-only enum.

## Non-Goals

- No raw instrument file analysis.
- No migration of existing project folders.
- No source-tree writes by default.
- No broad batch execution.
- No custom plotting engine.

## Definition of Done

- `render_csv_graph` creates jobs only under the runtime root.
- `collect_artifacts` returns graph resources and manifest paths.
- `nature_surfur` and the rest of Graph Hub target formats are accepted.
- Render failures return execution errors rather than protocol errors.
- Visual preflight failure returns `manual_review_needed=true`.

## Verification

Execution tests:

- rendering creates outputs only under runtime root,
- overwrite refusal works,
- timeout handling produces an execution error instead of a hanging process,
- CSV size limit enforcement runs before creating a job workspace,
- diagnostic path sanitization covers missing inputs and overwrite refusal,
- invalid columns return a useful execution error,
- visual preflight failure is represented in the result envelope,
- artifact manifests include created, modified, and skipped paths.

Compatibility tests:

- rendered config uses `project_config.yaml` contract,
- renderer calls existing Graph Hub bridge behavior,
- style format list matches Graph Hub core.
