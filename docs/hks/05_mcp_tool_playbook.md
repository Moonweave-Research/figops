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

## Athena Escalation

Use Athena only when the request needs:

- natural-language routing,
- solver or literature reasoning,
- multiple tools outside Graph Hub,
- user intent classification before selecting a graph workflow.
