# 05 Phase 4 Quality Gate and Batch Operation

- Status: Starts only after normalization and render manifests are proven
- Depends on: all previous work units

## Goal

Make batch graph work useful without hiding quality issues.

Phase 4 adds stronger visual quality reporting, optional baseline comparison, and bounded batch operations. It must not treat file existence as publication readiness.

## Required Work

1. Wire visual preflight into MCP result status.
2. Add optional baseline comparison for official figures.
3. Add bounded batch execution only after project discovery is reliable.
4. Return `manual_review_needed` when graphical quality cannot be proven automatically.
5. Keep batch jobs resumable and logged.

## Result Status Requirements

Artifact results must distinguish:

- `created`
- `validated`
- `preflight_passed`
- `baseline_matched`
- `manual_review_needed`
- `failed`

No MCP write or execute tool may return bare success for a visually unverified graph.

Phase 4 v1 represents this status as `artifact_status` on render and artifact collection results:

- `validated`: request/config/data checks passed in dry-run mode,
- `preflight_passed`: output passed visual preflight with no warnings,
- `baseline_matched`: output hash matched an explicit baseline file,
- `manual_review_needed`: output exists but preflight warnings, failed checks, or baseline mismatch require review,
- `failed`: execution or artifact lookup failed before quality could be established.

The v1 baseline comparison is a non-mutating sha256 comparison between an explicit `baseline_path` and the produced artifact. It is a regression guard, not a perceptual image similarity claim.

## Batch Operation Rules

Batch operations must be:

- explicit,
- bounded,
- resumable,
- logged,
- filterable by project classification,
- blocked for invalid projects unless explicitly requested in dry-run/report mode.

Default exclusions:

- `.worktrees/`
- Athena `bridge_jobs/`
- invalid configs for execution
- legacy folders unless explicitly selected

Phase 4 v1 exposes `graphhub.batch_check` as the bounded batch surface. It discovers projects, applies the default exclusions, validates selected projects through existing Graph Hub validation, and writes a runtime manifest only when `dry_run=false`.

Inputs:

- `root`
- `max_depth`: default `4`
- `max_projects`: capped by the server
- `include_invalid`: default `false`
- `include_legacy`: default `false`
- `include_worktrees`: default `false`
- `include_ephemeral`: default `false`
- `dry_run`: default `true`
- `batch_id`
- `resume_manifest_path`

Outputs:

- `checked_projects`
- `skipped_projects` with reason codes
- `manifest_path`
- `log_paths`
- `resumed_from`

## Non-Goals

- No unrestricted workspace-wide batch execution.
- No batch rendering in Phase 4 v1.
- No silent overwrite of existing figures.
- No automatic publication-readiness claim.
- No batch execution before visual preflight is wired.

## Definition of Done

- Visual preflight status appears in every relevant result envelope.
- Manual visual review is explicitly represented.
- Batch operations are bounded, logged, and resumable.
- Invalid or legacy projects are skipped by default for execution.
- Baseline comparison can be run without mutating source projects.

## Verification

Quality tests:

- visual preflight pass is reported,
- visual preflight fail sets `manual_review_needed=true`,
- missing output is not treated as success,
- blank or invalid output is not treated as success.

Batch tests:

- batch filters exclude invalid/legacy/ephemeral projects by default,
- timeout does not hang the batch,
- resume uses a prior manifest,
- log paths are returned,
- skipped projects include reasons.
