# Graph Hub Failure UX And Synthetic Fixture Spec - 2026-06-09

## Goal

Improve Graph Hub's near-term product readiness without splitting `graphhub-lite` yet.

This pass focuses on:

- a public-safe synthetic project fixture;
- a project-render smoke target that does not depend on private research folders;
- stronger failure UX assertions for common MCP errors.

## Non-Goals

- Do not split a new repository.
- Do not relicense Graph Hub.
- Do not remove private/internal style packs.
- Do not replace the existing internal gold smoke.

## Synthetic Fixture Contract

Create a small project under:

```text
examples/synthetic_project/
```

The fixture must include:

- `project_config.yaml`
- `hub_scripts/plot_response_curve.py`
- `results/data/response_curve.csv`
- `results/figures/.gitkeep`

The fixture must not include:

- real research project names;
- private/internal style names;
- private workflow references;
- large data files;
- generated figure binaries.

## Expected Figure

Figure id:

```text
FigSynthetic_Response
```

Output path:

```text
results/figures/FigSynthetic_Response.png
```

The plot script should use generic `nature` + `baseline` styling and produce a simple response curve from synthetic data.

## Failure UX Contract

For `graphhub.render_csv_graph`, a missing column error must include:

- `status="error"`
- `failure_stage="CONTRACT"`
- `manual_review_needed=true`
- a non-empty `resolution_hint` mentioning data contract or columns
- a sanitized error string with the missing column name

## Acceptance Criteria

- The synthetic project renders via `graphhub.render_project_figure` in a runtime snapshot.
- The source synthetic project is not modified by the MCP render.
- Missing-column failure UX assertions cover `failure_stage` and `resolution_hint`.
- Existing private gold smoke remains untouched.
