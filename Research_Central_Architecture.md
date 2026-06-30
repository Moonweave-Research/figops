# FigOps / Graph Hub Architecture

> Purpose: provide a reproducible, project-agnostic analysis and plotting hub for research projects.
> Principle: data contracts define the API; visual style and quality gates are centralized here.
> Current status: historical architecture blueprint for the independent FigOps repository.

This document preserves the earlier Graph Hub architecture language. For current
module inventory, release-state reading, and maintenance priorities, prefer
`docs/architecture.md` and `docs/ROADMAP.md`. Public package and command names
are now FigOps (`figops`, `figops-mcp`), while Graph Hub names remain as
compatibility aliases.

## 1. Repository Boundary

FigOps, formerly documented as Graph Hub, lives as its own Git repository:

```text
C:/dev/workspace/figops
```

Research projects remain outside this repository. The Hub discovers project folders through `project_config.yaml` and executes only the configured analysis, plot, diagram, and validation steps.

Expected sibling layout on the local machine:

```text
workspace/
  figops/                 # this repository
  ResearchOS/             # workspace control plane and research project links
```

The old in-workspace folder name `[Graph_making_hub]` is legacy terminology. Use it only when referring to historical paths or compatibility docs.

## 2. Core Structure

```text
graph-making-hub/
  orchestrator.py                 # CLI entry point
  hub_uv.py                       # uv wrapper that keeps runtime env outside the repo
  hub_core/                       # config, validation, cache, provenance, runner, scaffold
  analysis_helpers/               # shared R-side analysis helpers
  plotting/                       # reusable Python plotting helpers
  themes/                         # journal and presentation style presets
  tests/                          # focused regression tests for Hub behavior
  docs/                           # operator docs and MCP migration specs
  project_config_template.yaml    # canonical project contract template
  pyproject.toml                  # Python dependency source
  uv.lock                         # Python lockfile
  renv.lock                       # R lockfile
```

Do not commit project `results/`, generated figures, caches, `.venv/`, `.r_libs/`, DVC cache, or local runtime state into this repository.

## 3. Runtime Model

The orchestrator injects these public environment variables into project scripts:

- `RESEARCH_HUB_PATH`: absolute path to this Hub clone.
- `PROJECT_ROOT`: absolute path to the active research project.
- `THEME_FORMAT`: active journal/presentation target.
- `THEME_SCALE`: font scaling factor.
- `THEME_PROFILE`: active style profile.

Project scripts should treat those variables as the stable integration API instead of hard-coding Hub paths.

## 4. Reproducibility Gate

The current reproducibility baseline is:

- Python dependencies: `pyproject.toml` + `uv.lock`.
- R dependencies: repo-level `renv.lock`.
- Runtime state: external runtime/cache path, not the Git repository.
- Provenance: Git/config/environment hashes recorded by Hub execution.

DVC/data registry integration is retired from the required runtime surface. Reintroduce it only through a new spec and tests.

## 5. MCP Direction

MCP should be layered on top of the existing Hub contracts, not replace them:

1. read-only discovery of projects, configs, styles, and validation status;
2. controlled rendering through the same orchestrator paths;
3. explicit project normalization helpers;
4. quality-gated batch execution.

The MCP server must preserve project-local `project_config.yaml` style contracts and continue using Hub style presets as the single plotting policy source.

## 6. Current Verification Commands

```bash
python hub_uv.py run python orchestrator.py --list-projects
python hub_uv.py run python -m pytest tests/test_runtime_paths.py -q
python -m pytest tests/test_project_discovery.py tests/test_uv_runtime.py -q
```

Last update: 2026-06-07.
