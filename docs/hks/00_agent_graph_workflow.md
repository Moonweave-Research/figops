# HKS 00 Agent Graph Workflow

This is the common workflow for agents using Graph Hub directly.

## Default Rule

Use Graph Hub directly when the user explicitly asks for graph generation, project graph validation, figure quality checks, or project graph normalization.

Do not route through Athena unless the user asks for ambiguous natural-language routing, cross-tool research reasoning, solver/literature context, or a combined workflow outside Graph Hub's graph contract.

## Direct MCP Workflow

1. Call `graphhub.list_styles` when style support is unknown.
2. Call `graphhub.health` when server readiness or project discovery health is uncertain.
3. Call `graphhub.list_projects` to find known projects.
4. Call `graphhub.inspect_project` for a selected project.
5. Call `graphhub.validate_project` before any project-based render or migration.
6. Call `graphhub.render_csv_graph` for explicit structured CSV graph requests.
7. Call `graphhub.collect_artifacts` after render.
8. Inspect `manifest_path`, `status_path`, `failure_stage`, `resolution_hint`, `manual_review_needed`, and `visual_preflight_status`.

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
