# HKS 04 Quality Gate Contract

FigOps quality gates separate rendered output from publication-ready output.

## Required Result Fields

Every write-capable FigOps MCP result must preserve:

- `status`
- `operation_id`
- `job_id` when job-based
- `failure_stage`
- `resolution_hint`
- `created_paths`
- `modified_paths`
- `skipped_paths`
- `artifact_resources`
- `manual_review_needed`
- `manifest_path`
- `status_path`
- `latest_alias`

## Render Quality Fields

Render results must include:

- `style_summary`
- `visual_preflight_status`
- `artifact_status`
- `baseline_comparison`

## Failure Stages

Allowed render-stage values:

```text
CONFIG
CONTRACT
EXPORT
TIMEOUT
PLOT
```

Clients may add adapter-side `HUB_PATH` when FigOps cannot be reached.

## Manual Review

`manual_review_needed=true` means the artifact may exist but cannot be treated as final. Agents must report this state.

## Path Safety

Diagnostics must sanitize local absolute paths. Explicit artifact paths and `file://` resources may be returned for generated outputs.
