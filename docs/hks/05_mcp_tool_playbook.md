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
- `provenance`

Do not mutate the source project. Default project renders run under
`runtime_root/mcp_project_jobs/<job_id>/project`.

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
