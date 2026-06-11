# HKS 05 MCP Tool Playbook

This playbook maps common user requests to Graph Hub MCP tools.

## Explicit CSV Render

User request:

```text
Render this CSV as a Nature-style line plot with x=time and y=voltage.
```

Tool sequence:

```text
graphhub.list_styles
graphhub.render_csv_graph
graphhub.collect_artifacts
```

Required result inspection:

- `status`
- `output_path`
- `manifest_path`
- `status_path`
- `failure_stage`
- `resolution_hint`
- `manual_review_needed`
- `geometry_diagnostics`

## Project Figure Render

User request:

```text
Render Fig1 for this Graph Hub project using its project_config.yaml style.
```

Tool sequence:

```text
graphhub.list_projects
graphhub.inspect_project
graphhub.validate_project
graphhub.render_project_figure with dry_run=true
graphhub.render_project_figure
graphhub.collect_artifacts
```

Required result inspection:

- `selected_figure`
- `snapshot_project_path`
- `output_path`
- `manifest_path`
- `status_path`
- `failure_stage`
- `resolution_hint`
- `manual_review_needed`
- `visual_preflight_status`
- `geometry_diagnostics`
- `provenance`

Do not mutate the source project. Default project renders run under
`runtime_root/mcp_project_jobs/<job_id>/project`.

## Geometry Diagnostics

Both render tools attach a `geometry_diagnostics` object (and embed it in the
manifest) reporting deterministic, objective matplotlib geometry facts measured
on the fully-drawn figure: tick-label overlaps/crowding, out-of-axes/out-of-figure
artists, legend/colorbar collisions, blank-area ratio, and point-annotation
overlaps. There is no subjective scoring — every number traces to an artist extent.

Consumption rules:

- Read `schema_version` (`geometry_diagnostics/1`) before branching on check names.
- `passed` is tri-state: test `passed is False` for a real finding and `passed is None`
  for "not measured" (dry-run, render budget skip, no sidecar emitted, or engine error).
  Never use truthiness (`if not passed:` conflates `None` and `False`).
- Branch only on `name` + `passed` + `detail`; the per-check `data` sub-dict is advisory.
- Warning-eligible findings (`passed is False`) flip top-level `status` to `warning`
  through the existing `manual_review_needed` path, intentionally raising the `warning`
  rate (mainly on dense/rotated ticks). Diagnostics never hard-fail a render: the artifact
  is saved before they run, and an engine error degrades to `passed:null`.

Diagnostics are render-scoped via two env vars (`GEOMETRY_DIAGNOSTICS_OUT`,
`GEOMETRY_DIAGNOSTICS_DEADLINE`) that are set and cleared per render, and enter no
provenance/fingerprint hash. For fully cross-platform tick reproducibility, normalize
`LC_NUMERIC`/the tick formatter in the render environment (the two tick metrics depend
on per-machine font metrics; a `near_boundary` flag softens locale-driven width drift).

## Surfur Project Render

The Surfur root is a master workspace, not a direct render target:

```text
ResearchOS/02_Surfur_Polymer
```

For graph-only requests, call Graph Hub MCP directly against a concrete
subproject. The current gold target is:

```text
ResearchOS/02_Surfur_Polymer/저항 측정/PI_control
figure_id = FigPI_CvS_Fits
```

Use the same project render sequence:

```text
graphhub.inspect_project
graphhub.validate_project
graphhub.render_project_figure with dry_run=true
graphhub.render_project_figure
graphhub.collect_artifacts
```

Do not use Athena as a graph router for this case. Use Athena only when the
same user request also needs a separate non-graph solver, literature, or local
knowledge-base step.

## Health Check

User request:

```text
Check whether Graph Hub MCP is ready.
```

Tool sequence:

```text
graphhub.health
```

Use this for readiness and discovery health. Do not use it to generate reports or write workspace state.

## Project Validation

User request:

```text
Check whether this project is ready for Graph Hub rendering.
```

Tool sequence:

```text
graphhub.inspect_project
graphhub.validate_project
```

If invalid, report exact config, data contract, lockfile, and style errors.

## Project Normalization

User request:

```text
Standardize this graph project folder.
```

Tool sequence:

```text
graphhub.inspect_project
graphhub.normalize_project_structure with dry_run=true
```

Apply only after the user approves the dry-run manifest.

## Batch Quality Review

User request:

```text
Review active projects for graph readiness.
```

Tool sequence:

```text
graphhub.batch_check
```

Do not use passive health checks for write/report generation.

## Optional Non-Graph Toolbox Escalation

Do not use Athena as the graph router or default natural-language router.
The agent using Graph Hub should decide whether the request is graph-only,
mixed, or out of scope.

Use Athena or another explicit toolbox only when the request needs a separate
non-graph capability:

- solver or literature reasoning,
- Zotero/local knowledge-base context,
- legacy Athena slash-command compatibility explicitly requested by the user,
- a mixed workflow where the non-graph result is passed back into Graph Hub MCP.

If Graph Hub MCP is unavailable, fix or report Graph Hub MCP. Do not hide that
failure by routing graph work through Athena.
