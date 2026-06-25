# FigOps

[![PyPI](https://img.shields.io/pypi/v/figops.svg)](https://pypi.org/project/figops/)
[![Python](https://img.shields.io/pypi/pyversions/figops.svg)](https://pypi.org/project/figops/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)
[![CI](https://github.com/Moonweave-Research/figops/actions/workflows/ci.yml/badge.svg)](https://github.com/Moonweave-Research/figops/actions/workflows/ci.yml)

**From messy analysis folders to traceable, publication-ready figures.**

FigOps is a small research-ops toolkit for figure work: it reads a project
config, checks the declared data contract, runs analysis and plotting scripts,
applies journal/presentation styling, and records enough provenance to make the
figure auditable later.

It is intentionally boring in the best way: one config, one command, clear
inputs, repeatable outputs.

```bash
python -m pip install figops
figops --help
figops-mcp --smoke
```

If those commands work, the CLI is installed and the MCP surface is alive.

---

## Why FigOps exists

Research figures often start as a few scripts and a folder of exported data.
That works until the figure changes, a collaborator asks where a value came
from, or a manuscript revision needs the same plot in a different journal style.

FigOps keeps that workflow lightweight while making the important parts explicit:

- **Data is the API** — inputs are declared, checked, and traceable.
- **Figures are rebuildable** — analysis, plotting, diagrams, and assembly live
  behind the same project contract.
- **Style is reusable** — journal and presentation targets are selected through
  config instead of one-off plotting edits.
- **Agents can inspect safely** — the MCP server exposes read, render, and smoke
  surfaces for tool-assisted figure workflows.

## Current release

| Item | Status |
| --- | --- |
| Package | [`figops==0.17.9`](https://pypi.org/project/figops/0.17.9/) is live on PyPI |
| Python | 3.12+ |
| License | Apache-2.0 for public package distribution |
| Commands | `figops`, `figops-mcp` |
| Compatibility aliases | `graphhub`, `graphhub-mcp` |
| GitHub Release | [`v0.17.9`](https://github.com/Moonweave-Research/figops/releases/tag/v0.17.9) |

## Install

For normal use:

```bash
python -m pip install figops
```

For a pinned, reproducible install:

```bash
python -m pip install figops==0.17.9
```

If you need the exact GitHub Release asset:

```bash
gh release download v0.17.9 --repo Moonweave-Research/figops --pattern "*.whl" --dir dist-release
python -m pip install dist-release/figops-0.17.9-py3-none-any.whl
figops-mcp --smoke
```

## Quick start

Create a new figure project:

```bash
figops --init --project my_figure_project
cd my_figure_project
```

That creates a scaffold with:

```text
my_figure_project/
├── project_config.yaml
├── raw/
│   └── example_input.csv
└── hub_scripts/
    ├── analyze.R
    ├── plot.py
    └── project_context.py
```

Run the project:

```bash
figops --project . --step all
```

For a first sanity check, list the available CLI options:

```bash
figops --help
```

## What FigOps does

A FigOps run coordinates the work around a research figure:

1. read `project_config.yaml`,
2. resolve declared input files,
3. validate data contracts and research-ops rules,
4. run analysis scripts when needed,
5. render figures, diagrams, or assembled panels,
6. apply the selected style profile,
7. write provenance and runtime metadata for auditability.

A minimal config looks like this:

```yaml
project:
  name: "Example Study"

visual_style:
  target_format: nature
  font_scale: 1.0
  profile: baseline

pipeline:
  analysis:
    - script: "hub_scripts/analyze.R"
      lang: R
      cache: true

figures:
  - id: Fig1
    script: "hub_scripts/plot.py"
    output: "results/figures/Fig1.png"
    cache: true
```

R is only required when your configured analysis scripts use R. Python plotting
and package/MCP smoke checks run from the Python package install.

## Everyday commands

```bash
# Choose a configured project interactively
figops

# List configured projects
figops --list-projects

# Run the full pipeline for one project
figops --project "ProjectName" --step all

# Re-render figures only
figops --project "ProjectName" --step plot

# Re-render diagrams only
figops --project "ProjectName" --step diagrams

# Force a clean rerun and bypass cache
figops --project "ProjectName" --step all --force
```

From a source checkout, use the repo-local runtime wrapper:

```bash
python hub_uv.py run python orchestrator.py --list-projects
python hub_uv.py run python -m pytest tests/test_runtime_paths.py -q
```

`hub_uv.py` keeps the Python runtime outside the repository so the working tree
does not get polluted with local virtualenv state.

## MCP for agents

FigOps includes a Model Context Protocol server entry point:

```bash
figops-mcp --smoke
```

A healthy smoke response looks like:

```json
{"status": "ok", "health_status": "ok", "tool_surface": "figops_mcp"}
```

Use this before wiring FigOps into Claude, Codex, or another MCP-capable client.
For compatibility with earlier local setups, `graphhub-mcp` remains available as
an alias.

## Troubleshooting

| Symptom | What to try |
| --- | --- |
| `project_config.yaml not found` | Run `figops --init --project "<project>"` or move into a configured project. |
| `Project directory not found` | Run `figops --list-projects` and copy the exact configured name. |
| Strict lockfile errors | `--strict-lock` is for reproducibility checks. For quick local rendering, rerun without strict mode. |
| Google Drive files feel stuck | Let Drive finish syncing, then rerun. The prefetch layer can help with declared inputs, but it cannot repair a broken Drive login/session. |
| R script fails immediately | Confirm `Rscript` is available if your project config uses `lang: R`. |

## For maintainers

Release candidates are checked with the packaging and test gates below:

```bash
uv build
python scripts/package_metadata_smoke.py
python scripts/public_package_surface.py
python scripts/consumer_install_smoke.py
uv run --with twine python -m twine check dist/*
python hub_uv.py run python -m pytest -q
python hub_uv.py run ruff check .
```

After release assets are uploaded, verify both the GitHub artifact and the public
install path:

```bash
python scripts/github_release_asset_smoke.py
python -m pip install figops==0.17.9
figops-mcp --smoke
```

Publishing uses the manual Trusted Publishing workflow in
[`.github/workflows/publish.yml`](./.github/workflows/publish.yml): TestPyPI
first, install smoke, then PyPI. See
[`docs/packaging/trusted-publishing.md`](./docs/packaging/trusted-publishing.md)
for the exact runbook.

## Repository map

| Path | Purpose |
| --- | --- |
| `orchestrator.py` | CLI entry point and top-level pipeline coordinator |
| `hub_core/` | Config loading, validation, cache, provenance, process execution, MCP logic |
| `hub_core/mcp/` | MCP server, schemas, transport, resources, prompts, and tool handlers |
| `plotting/` | Reusable plotting helpers and figure assembly utilities |
| `themes/` | Journal and presentation style presets |
| `examples/` | Small synthetic projects and package-facing examples |
| `scripts/` | Release, packaging, and distribution checks |
| `tests/` | Regression and contract tests |
| `docs/packaging/` | PyPI readiness, clearance checklist, and Trusted Publishing runbook |

## Next release checklist

The public package is live. For the next release, keep the same conservative path:

1. bump the version,
2. rebuild wheel/sdist from a clean tree,
3. confirm package artifacts exclude private docs/tests/research markers,
4. publish to TestPyPI through `.github/workflows/publish.yml`,
5. install-check from TestPyPI,
6. promote the same version to PyPI,
7. install-check from public PyPI.

## License

FigOps is distributed under the Apache-2.0 license. See [LICENSE](./LICENSE) and
[NOTICE](./NOTICE).
