# HKS 00 Agent Graph Workflow

This is the common workflow for agents using Graph Hub directly.

## Default Rule

Use Graph Hub directly when the user explicitly asks for graph generation, project graph validation, figure quality checks, or project graph normalization.

Do not route graph work through Athena. The agent using Graph Hub should decide whether the request is graph-only, mixed, or outside Graph Hub's scope.

Use Athena or another explicit toolbox only for a separate non-graph step such as solver/literature context, then pass the resulting data or claim back into Graph Hub MCP.

## Direct MCP Workflow

1. Call `graphhub.list_styles` when style support is unknown.
2. Call `graphhub.health` when server readiness or project discovery health is uncertain.
3. Call `graphhub.list_projects` to find known projects.
4. Call `graphhub.inspect_project` for a selected project.
5. Call `graphhub.validate_project` before any project-based render or migration.
6. Call `graphhub.render_project_figure` for configured `project_config.yaml` figures.
7. Call `graphhub.render_csv_graph` for explicit structured CSV graph requests.
8. Call `graphhub.collect_artifacts` after render.
9. Inspect `manifest_path`, `status_path`, `failure_stage`, `resolution_hint`, `manual_review_needed`, `visual_preflight_status`, and `provenance`.

## Required Agent Behavior

- Treat `status=error` as a valid tool result when returned in `structuredContent`.
- Use `resolution_hint` as the next-action source.
- Do not hide `manual_review_needed=true`.
- Do not claim publication readiness from syntax-only render success.
- Do not read raw data, PDFs, images, or binary outputs into chat unless explicitly required.
- Keep Graph Hub independent from Athena.

## Stop Conditions

Stop and ask for user direction when:

- a project migration would modify source files,
- a render requires overwriting an existing job and the user did not request overwrite,
- `manual_review_needed=true` and the next action requires human visual judgment,
- required methodology or calculation rules are missing from HKS/common docs.
