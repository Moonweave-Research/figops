# Synthetic Project Tutorial

This fixture is a public-safe FigOps project that renders one response-curve figure from
`results/data/response_curve.csv`.

## What It Contains

- `project_config.yaml`: project metadata, style settings, data-contract checks, and one figure.
- `results/data/response_curve.csv`: synthetic input data with `time_s` and `response_au`.
- `hub_scripts/plot_response_curve.py`: the project plot script.

## Run It

From the repository root:

```bash
uv run python orchestrator.py --project examples/synthetic_project --step plot --force
```

## Expected Output

- Figure: `examples/synthetic_project/results/figures/FigSynthetic_Response.png`
- The command may print a data-quality warning for the deliberately small synthetic dataset.
- The process should exit with status 0.

Use this example when you want the smallest complete project-level render.
