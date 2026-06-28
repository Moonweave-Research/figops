# FigOps MCP Surface Spec

- Status: Final direction and work-unit index; updated after live ResearchOS audit
- Date: 2026-06-07
- Scope: independent `figops` repository, Athena visualization bridge, ResearchOS project graph inventory
- Decision: FigOps remains the canonical graph engine. MCP is added as a thin, typed agent surface. Athena becomes a caller/client of FigOps, not the owner of FigOps project or style contracts.
- Implementation start point: finish Phase 0 truth-surface repair and style-contract alignment. Write-capable MCP tools are out of scope until discovery, style, validation, and no-write read-only tests pass.

## Executive Decision

FigOps should evolve toward an MCP-compatible surface, but MCP must not replace the existing Hub engine.

The target architecture is:

```text
Agents / Athena / Codex
        |
        | client calls
        v
FigOps MCP Surface
        |
        v
FigOps Core Engine
  - project_config.yaml contract
  - orchestrator.py CLI
  - hub_core validation and execution
  - themes and style profiles
  - plotting bridge renderer
        |
        v
Standardized research project folders and reproducible artifacts
```

The key rule is: MCP exposes FigOps capability; it does not reimplement plotting, style selection, project discovery, cache behavior, provenance, or validation.

Athena must not copy or narrow FigOps's project/style contract. During migration, Athena's existing `hub_bridge` path remains a compatibility adapter until MCP render parity is proven with the same inputs, styles, artifact manifests, and failure modes.

## Why This Is Split

The first full spec mixed permanent architecture, MCP protocol rules, discovery repair, read-only tools, rendering, project normalization, visual quality gates, and future direction in one document. That was useful for deciding direction, but too broad for implementation.

This index keeps the decision stable and splits the work into implementation-sized documents. Each work unit has its own scope, non-goals, deliverables, definition of done, and verification requirements.

## Work-Unit Documents

Read and execute in this order:

1. [00 Protocol and Safety Contract](graph_hub_mcp_surface/00_protocol_and_safety_contract.md)
2. [01 Phase 0 Truth Surface Repair](graph_hub_mcp_surface/01_phase0_truth_surface_repair.md)
3. [02 Phase 1 Read-Only MCP](graph_hub_mcp_surface/02_phase1_read_only_mcp.md)
4. [03 Phase 2 Controlled Rendering](graph_hub_mcp_surface/03_phase2_controlled_rendering.md)
5. [04 Phase 3 Project Normalization](graph_hub_mcp_surface/04_phase3_project_normalization.md)
6. [05 Phase 4 Quality Gate and Batch Operation](graph_hub_mcp_surface/05_phase4_quality_gate_batch.md)
7. [06 Direction Beyond MCP v1](graph_hub_mcp_surface/06_direction_beyond_mcp_v1.md)
8. [07 Athena Client Migration Workflow](graph_hub_mcp_surface/07_athena_client_migration_workflow.md)

Post-migration direction lock:

- [FigOps Independent Completion Spec](graph_hub_independent_completion_spec_20260608.md)

## Current Findings That Drive the Plan

### Live ResearchOS And FigOps State

Live audit on 2026-06-07 found:

- FigOps has been physically externalized as its own Git repository at `/Users/choemun-yeong/workspace/figops`.
- ResearchOS still owns workspace governance and Athena. Athena must resolve FigOps as an external tool path, not as a nested `[Graph_making_hub]` source tree.
- FigOps discovery now reports 14 projects: 13 valid and 1 invalid.
- The invalid project is `synthetic_polymer_project/유전율 측정`, with three `data_contract.csv_checks.path is required` errors.
- Athena `hub_bridge` is enabled and resolves `hub_path` to the local independent FigOps path, with compatibility handling for legacy configured paths.
- Athena can execute a FigOps bridge smoke job, but its `TargetFormat` contract is narrower than FigOps's official style set.
- `workspace_state.md` and `workspace_state.json` can become dirty from health/report generation, so read-only MCP health must not reuse side-effectful report writers.

### Discovery Truth Has Been Repaired, But Phase 0 Is Not Done

The old failure mode was that `python orchestrator.py --list-projects` could report no configured projects while a symlink-aware workspace scan found multiple `project_config.yaml` files.

That discovery gap has been repaired in the current workspace by introducing a shared project discovery path. Phase 0 still remains open until style-contract parity, no-write read-only tests, and MCP discovery parity are in place.

### Style Contracts Must Stay Shared

FigOps supports target formats including:

```text
nature, internal_style_format, science, ppt, default, acs, rsc, elsevier, wiley, cell
```

Athena's bridge model currently narrows that surface to:

```text
nature, science, ppt, default
```

The MCP schema must derive style formats from FigOps's canonical style contract or from a shared model generated from that contract. It must not copy a narrower Athena-only enum.

### Athena Is A Caller, Not The FigOps Owner

The current Athena bridge writes temporary Hub-compatible projects and calls FigOps's CLI. This is a useful compatibility layer, but it is not the target ownership model.

Target ownership:

- FigOps owns project discovery, project config validation, style contracts, rendering execution, provenance, artifacts, and quality status.
- Athena owns research routing, solve/literature/context workflows, and calls FigOps through a typed client interface.
- FigOps MCP becomes the stable interface between them.
- FigOps code should not require Athena imports for core graph rendering. Existing FigOps-to-Athena rendering hooks are transitional/plugin-like and should be reviewed before MCP write tools ship.

### MCP Must Not Become a New Plotting Engine

The existing Hub contracts are the source of truth:

- `project_config_template.yaml`
- `hub_core/config_parser.py`
- `hub_core/process_runner.py`
- `themes/journal_theme.py`
- `themes/style_profiles.py`
- `plotting/bridge_renderer.py`
- Athena's existing Hub bridge path

MCP should import or call those behaviors. It must not duplicate them.

## Global Acceptance Criteria

The MCP direction is accepted only when all of the following remain true:

1. FigOps remains usable through the existing CLI.
2. MCP calls use FigOps core behavior instead of reimplementing plotting.
3. Read-only tools are side-effect free.
4. Write tools are explicit, bounded, and return manifests.
5. Project discovery is symlink-aware and excludes worktrees/ephemeral bridge jobs by default.
6. Invalid project configs are visible to agents.
7. Target style formats are shared across FigOps, Athena bridge, and MCP.
8. `internal_style_format` remains a first-class supported target format.
9. Temporary jobs use an external runtime root.
10. Artifact results distinguish `created`, `validated`, `preflight_passed`, and `manual_review_needed`.
11. Every MCP tool has an input schema, and structured tools have an output schema.
12. Write tools return manifests and never write outside allowed roots.
13. Tool execution errors are distinguishable from protocol errors.
14. MCP resources use validated URIs and MIME types.

## Implementation Gate

- Phase 0 remains the approved starting scope.
- Existing Athena bridge behavior must remain available until MCP parity is proven.
- Phase 1 read-only MCP may start only after CLI/MCP discovery parity is designed and testable.
- Phase 2 rendering may start only after read-only tools pass no-write tests.
- Phase 3 normalization may start only after render jobs are isolated under the runtime root and manifests are proven.
- Phase 4 batch operation may start only after visual preflight and manual-review status are wired into result envelopes.

Any implementation plan that starts by adding broad write tools, workspace-wide batch execution, or a custom plotting implementation is out of spec.

## Local Source of Truth

- `AGENTS.md`
- `README.md`
- `project_config_template.yaml`
- `hub_core/config_parser.py`
- `hub_core/process_runner.py`
- `themes/journal_theme.py`
- `themes/style_profiles.py`
- `plotting/bridge_renderer.py`
- `[Athena]/integrations/hub_bridge.py`
- `[Athena]/integrations/hub_models.py`

## External MCP Reference

- Model Context Protocol server concepts: https://modelcontextprotocol.io/docs/learn/server-concepts
- Model Context Protocol tools specification: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- Model Context Protocol resources specification: https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- Model Context Protocol prompts specification: https://modelcontextprotocol.io/specification/2025-06-18/server/prompts
