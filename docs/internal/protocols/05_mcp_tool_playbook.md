# HKS 05 MCP Tool Playbook

This playbook maps common user requests to FigOps MCP tools.

## Tool Coverage Matrix

Agents should prefer canonical `figops.*` tool names. Legacy `graphhub.*`
aliases are handler-backed compatibility names, not the preferred guidance
surface.

| Tool | Agent guidance |
| --- | --- |
| `figops.health` | Check server readiness, roots, write-tool state, adapters, and discovery health. |
| `figops.describe` | Inspect the registered FigOps surface when tool, plot-type, or semantic-check support is unknown. |
| `figops.list_styles` | List supported target formats, output formats, profiles, aliases, and public style packs. |
| `figops.list_projects` | Discover known projects before selecting a project ID or path. |
| `figops.inspect_project` | Read project metadata, figures, style summary, and readiness context without executing scripts. |
| `figops.validate_project` | Validate config, data contracts, lockfiles, and style compatibility before project renders. |
| `figops.render_csv_graph` | Render an explicit single-panel CSV graph from structured columns. |
| `figops.render_csv_multipanel` | Render explicit multi-panel CSV figures when the request supplies panel specs. |
| `figops.render_project_figure` | Render configured `project_config.yaml` figures; use `dry_run=true` first. |
| `figops.collect_artifacts` | Collect manifest, status, output, and related artifacts after a render job. |
| `figops.scaffold_project` | Scaffold a new project only after the user asks for project creation; keep dry-run previews visible. |
| `figops.normalize_project_structure` | Preview and then apply project folder normalization only after user approval. |
| `figops.batch_check` | Review multiple active projects for graph readiness and quality-report generation. |
| `figops.evaluate_publication_readiness` | Evaluate an existing render job's bounded manifest evidence; treat the result as an automatic QA triage that still requires human review. |

## Publication Readiness Evaluation

This is automatic evidence triage, not publication approval and not automatically publication-ready.
A `needs_review` result still requires cited hard gates to pass and manual scientific review.

After a render returns a `job_id`, call `figops.evaluate_publication_readiness`
with that ID. The tool is read-only and remains available when MCP write tools
are disabled. Inspect `readiness_report.readiness_status` and `findings`; never
interpret `needs_review` as human approval or a publication guarantee.

## Explicit CSV Render

User request:

```text
Render this CSV as a Nature-style line plot with x=time and y=voltage.
```

Tool sequence:

```text
figops.list_styles
figops.render_csv_graph
figops.collect_artifacts
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

Same-dataset, all-public-journal render example:

```json
[
  {
    "tool": "figops.list_styles",
    "arguments": {}
  },
  {
    "tool": "figops.render_csv_graph",
    "arguments": {
      "data_path": "/allowed/measurements.csv",
      "x_column": "strain",
      "y_column": "stress",
      "series_column": "sample",
      "plot_type": "line",
      "target_format": "nature",
      "output_format": "png",
      "job_id": "journal-nature"
    }
  },
  {
    "tool": "figops.render_csv_graph",
    "arguments": {
      "data_path": "/allowed/measurements.csv",
      "x_column": "strain",
      "y_column": "stress",
      "series_column": "sample",
      "plot_type": "line",
      "target_format": "science",
      "output_format": "png",
      "job_id": "journal-science"
    }
  },
  {
    "tool": "figops.render_csv_graph",
    "arguments": {
      "data_path": "/allowed/measurements.csv",
      "x_column": "strain",
      "y_column": "stress",
      "series_column": "sample",
      "plot_type": "line",
      "target_format": "acs",
      "output_format": "png",
      "job_id": "journal-acs"
    }
  },
  {
    "tool": "figops.render_csv_graph",
    "arguments": {
      "data_path": "/allowed/measurements.csv",
      "x_column": "strain",
      "y_column": "stress",
      "series_column": "sample",
      "plot_type": "line",
      "target_format": "rsc",
      "output_format": "png",
      "job_id": "journal-rsc"
    }
  },
  {
    "tool": "figops.render_csv_graph",
    "arguments": {
      "data_path": "/allowed/measurements.csv",
      "x_column": "strain",
      "y_column": "stress",
      "series_column": "sample",
      "plot_type": "line",
      "target_format": "elsevier",
      "output_format": "png",
      "job_id": "journal-elsevier"
    }
  },
  {
    "tool": "figops.render_csv_graph",
    "arguments": {
      "data_path": "/allowed/measurements.csv",
      "x_column": "strain",
      "y_column": "stress",
      "series_column": "sample",
      "plot_type": "line",
      "target_format": "wiley",
      "output_format": "png",
      "job_id": "journal-wiley"
    }
  },
  {
    "tool": "figops.render_csv_graph",
    "arguments": {
      "data_path": "/allowed/measurements.csv",
      "x_column": "strain",
      "y_column": "stress",
      "series_column": "sample",
      "plot_type": "line",
      "target_format": "cell",
      "output_format": "png",
      "job_id": "journal-cell"
    }
  }
]
```

Use the same `data_path`, `x_column`, `y_column`, `series_column`, and
`plot_type` across tracks; change only journal style/output controls such as
`target_format`, `output_format`, and `job_id`. Do not use stale `x`, `y`, or
`chart_type` keys.

## Project Figure Render

User request:

```text
Render Fig1 for this FigOps project using its project_config.yaml style.
```

Tool sequence:

```text
figops.list_projects
figops.inspect_project
figops.validate_project
figops.render_project_figure with dry_run=true
figops.render_project_figure
figops.collect_artifacts
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
ResearchOS/synthetic_polymer_project
```

For graph-only requests, call FigOps MCP directly against a concrete
subproject. The current gold target is:

```text
ResearchOS/synthetic_polymer_project/measurement_data/control_sample
figure_id = FigPI_CvS_Fits
```

Use the same project render sequence:

```text
figops.inspect_project
figops.validate_project
figops.render_project_figure with dry_run=true
figops.render_project_figure
figops.collect_artifacts
```

Do not use Athena as a graph router for this case. Use Athena only when the
same user request also needs a separate non-graph solver, literature, or local
knowledge-base step.

## Health Check

User request:

```text
Check whether FigOps MCP is ready.
```

Tool sequence:

```text
figops.health
```

Use this for readiness and discovery health. Do not use it to generate reports or write workspace state.

## Project Validation

User request:

```text
Check whether this project is ready for FigOps rendering.
```

Tool sequence:

```text
figops.inspect_project
figops.validate_project
```

If invalid, report exact config, data contract, lockfile, and style errors.

## Project Normalization

User request:

```text
Standardize this graph project folder.
```

Tool sequence:

```text
figops.inspect_project
figops.normalize_project_structure with dry_run=true
```

Apply only after the user approves the dry-run manifest.

## Batch Quality Review

User request:

```text
Review active projects for graph readiness.
```

Tool sequence:

```text
figops.batch_check
```

Do not use passive health checks for write/report generation.

## Optional Non-Graph Toolbox Escalation

Do not use Athena as the graph router or default natural-language router.
The agent using FigOps should decide whether the request is graph-only,
mixed, or out of scope.

Use Athena or another explicit toolbox only when the request needs a separate
non-graph capability:

- solver or literature reasoning,
- Zotero/local knowledge-base context,
- legacy Athena slash-command compatibility explicitly requested by the user,
- a mixed workflow where the non-graph result is passed back into FigOps MCP.

If FigOps MCP is unavailable, fix or report FigOps MCP. Do not hide that
failure by routing graph work through Athena.
