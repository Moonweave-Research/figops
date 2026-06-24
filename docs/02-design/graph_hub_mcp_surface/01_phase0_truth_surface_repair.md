# 01 Phase 0 Truth Surface Repair

- Status: Approved first implementation scope; partially implemented
- Depends on: `00_protocol_and_safety_contract.md`
- Blocks: every write-capable MCP tool

## Goal

Make existing FigOps state trustworthy before exposing it through MCP.

Phase 0 fixes the truth surface: project discovery, config classification, style contract sharing, and no-write health/discovery behavior. It does not implement rendering or project normalization.

## Original Failure Mode

`python orchestrator.py --list-projects` can report no configured projects while a symlink-aware workspace scan finds multiple `project_config.yaml` files under ResearchOS.

That failure means an MCP wrapper around the current CLI discovery path would expose false state to agents. This must be fixed first.

## Current Live Status

As of the 2026-06-07 live audit:

- shared discovery has been introduced in `hub_core/project_discovery.py`,
- `orchestrator.py --list-projects` reports 14 projects,
- 13 projects are valid and 1 project is invalid,
- the invalid project is `02_Surfur_Polymer/유전율 측정`,
- default discovery excludes `.worktrees/` and Athena `bridge_jobs/`,
- Athena still narrows FigOps's target format set and must be aligned.

Therefore Phase 0 is no longer blocked by missing discovery, but it is not complete until style-contract parity, no-write checks, and MCP parity tests are present.

## Scope

Required work:

1. Create a shared `ProjectDiscoveryService` in `hub_core/`.
2. Make `orchestrator.py --list-projects`, `orchestrator.py --check-all`, and future MCP `list_projects` use the same discovery service.
3. Add symlink-aware workspace scanning with default exclusions for `.worktrees/` and Athena `bridge_jobs/`.
4. Detect both `project_config.yaml` and legacy `scripts/project_config.yaml`.
5. Surface invalid configs with errors instead of hiding them.
6. Produce a read-only graph inventory report that classifies discovered folders as `official`, `suspect`, `legacy`, `invalid`, or `ephemeral`.
7. Define stable project IDs.
8. Create a shared style contract helper that exposes target formats and profiles.
9. Align Athena bridge target format validation with FigOps's full target format set.
10. Confirm runtime-state policy: no new materialized runtime state inside source trees.

Current first workflow:

1. Align Athena `TargetFormat` with FigOps's `ALLOWED_TARGET_FORMATS`.
2. Add a parity test so future FigOps style additions fail Athena tests until the bridge contract is updated.
3. Keep existing Athena bridge behavior working.

## Non-Goals

- No MCP server write tools.
- No `render_csv_graph`.
- No project migration.
- No broad workspace batch execution.
- No plotting behavior rewrite.

## Deliverables

- `ProjectDiscoveryService` or equivalent shared discovery module.
- CLI integration for `--list-projects` and `--check-all`.
- Shared style contract export.
- Athena bridge style compatibility update.
- Read-only inventory report shape.
- Tests for discovery, style contracts, invalid configs, and no-write behavior.

## Discovery Defaults

Default discovery must:

- follow symlinked ResearchOS project folders intentionally,
- exclude `.worktrees/`,
- exclude Athena `bridge_jobs/`,
- include invalid configs with error details,
- include legacy configs but mark them as `legacy`,
- return stable project IDs.

## Definition of Done

- CLI `--list-projects` reports the same project set as the shared discovery service.
- `--check-all` uses the same project source as `--list-projects`.
- `nature_surfur` is accepted through every intended agent-facing graph path.
- Every discovered config has stable project ID, classification, and validation state.
- Read-only health/discovery calls have no filesystem side effects.

## Verification

Unit tests:

- symlinked project discovery,
- `.worktrees/` exclusion,
- Athena `bridge_jobs/` exclusion,
- invalid config visibility,
- legacy config path support,
- stable project ID generation,
- style contract export.

Parity tests:

- CLI `--list-projects` and discovery service return the same filtered project set.
- Athena bridge validation accepts FigOps target formats.

No-write tests:

- read-only discovery does not change git status,
- read-only discovery does not create workspace state files,
- read-only discovery does not create runtime job directories.
