# 04 Phase 3 Project Normalization

- Status: Starts only after controlled rendering is isolated and manifest-proven
- Depends on: `00_protocol_and_safety_contract.md`, `01_phase0_truth_surface_repair.md`, `02_phase1_read_only_mcp.md`, `03_phase2_controlled_rendering.md`
- Blocks: Phase 4 batch operation

## Goal

Convert scattered graph folders into standard Graph Hub projects while preserving raw data, existing outputs, and project-specific style choices.

This phase addresses the original workflow problem: many graph projects exist in many folders, and they need consistent structure and Hub connection without flattening their individual formats.

## Tools

### `graphhub.scaffold_project`

Creates a standardized project folder and starter `project_config.yaml`.

Inputs:

- `project_name`
- `project_root`: destination project directory
- `target_format`
- `template`: `standard | researchos`
- `dry_run`: default `true`
- `overwrite`: default `false`

Acceptance criteria:

- dry run returns the planned file tree,
- apply mode refuses to overwrite existing files unless explicitly allowed,
- generated structure follows the ResearchOS project template.

### `graphhub.normalize_project_structure`

Plans or applies migration of an existing graph folder into the standard Hub structure.

Inputs:

- `project_path`
- `dry_run`: default `true`
- `move_policy`: `copy | move | symlink`
- `include_raw`: default `false`
- `overwrite`: default `false`

Behavior:

- discovers current scripts, data, figures, and docs,
- proposes a migration plan,
- maps files into `raw/`, `work/`, `hub_scripts/`, `results/data/`, `results/figures/`, and `docs/`,
- preserves nested relative subpaths under known legacy folders,
- preserves raw/data inputs by copying them even when `move_policy=move`,
- writes or updates `project_config.yaml` only in apply mode.

## Project-Specific Style Preservation

Normalization must preserve existing project-level style choices.

Rules:

- keep project `visual_style` when present,
- keep named `presets` when present,
- keep figure-level style overrides when present,
- avoid converting all projects to one global format,
- propose style updates as a plan, not an automatic overwrite.

## Migration Manifest

Apply mode must write a reversible manifest that records:

- source path,
- destination path,
- operation: `copy | move | symlink | skip`,
- reason,
- checksum when cheap and appropriate,
- whether the file was created, modified, or skipped.

Manifest files:

- scaffold apply writes `.graphhub_scaffold_manifest.json`,
- normalization apply writes `.graphhub_normalization_manifest.json`.

## Non-Goals

- No batch normalization by default.
- No raw data mutation.
- No automatic deletion of legacy files.
- No forced conversion to a single journal style.
- No `run_project_step(all)` as part of normalization.

## Definition of Done

- Plan mode is default and side-effect free.
- Apply mode writes a reversible manifest.
- Raw data is preserved.
- Generated or updated projects pass `validate_project`.
- Existing project styles are preserved unless explicitly changed.

## Verification

No-write tests:

- `dry_run=true` does not change git status,
- plan mode does not create files,
- plan mode does not touch raw data.

Apply tests:

- apply mode writes the expected file tree,
- overwrite refusal works,
- manifest includes all created, modified, and skipped paths,
- generated `project_config.yaml` passes validation.

Style tests:

- existing `visual_style` is preserved,
- existing presets are preserved,
- figure-level overrides are not dropped.
