# Multipanel Project Tutorial

This fixture is a public-safe FigOps project that assembles three SVG panels into one
publication-style SVG plate.

## What It Contains

- `project_config.yaml`: project metadata, style settings, and one SVG figure.
- `assets/panel_response.svg`: main response panel.
- `assets/panel_distribution.svg`: distribution panel.
- `assets/panel_summary.svg`: summary panel.
- `hub_scripts/assemble_multipanel.py`: the assembly script.

## Run It

From the repository root:

```bash
uv run python orchestrator.py --project examples/multipanel_project --step plot --force
```

## Expected Output

- Figure: `examples/multipanel_project/results/figures/FigSynthetic_Multipanel.svg`
- The output should contain three labeled panels: response, distribution, and summary.
- The process should exit with status 0.

Use this example when you want to understand project-configured figure assembly rather than
CSV-to-plot rendering.
