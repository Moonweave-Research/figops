# Graph Making Hub / FigOps

Graph Making Hub helps research teams turn raw analysis outputs into reproducible,
publication-ready figures. It is meant to be boring in the best way: one config,
one command, traceable inputs, repeatable outputs.

The short version:

```bash
graphhub --help
graphhub-mcp --smoke
```

If those two commands work, the package is installed and the MCP surface is alive.

## Current status

- **Installable package:** yes. The wheel is built and smoke-tested like an external user would run it.
- **Current distribution name:** `graph-making-hub`.
- **Current commands:** `graphhub` and `graphhub-mcp`.
- **GitHub Release assets:** yes, for users who already have repository access.
- **Public PyPI:** not yet. The public release gate is intentionally blocked until the license and distribution policy are changed.

This means the project is technically ready for controlled sharing, but it is not
licensed as open source yet. Repository access or a downloaded wheel does not
grant redistribution, public mirroring, commercial use, or derivative-publication
rights. Check [LICENSE](./LICENSE) and [NOTICE](./NOTICE) before sharing it.

## Install from the current GitHub release

For internal users with repository access:

```bash
gh release download v0.16.11 --repo Moonweave-Research/figops --pattern "*.whl" --dir dist-release
python -m pip install dist-release/graph_making_hub-0.16.11-py3-none-any.whl
graphhub-mcp --smoke
```

For local development from a clone:

```bash
python hub_uv.py run python orchestrator.py --list-projects
python hub_uv.py run python -m pytest tests/test_runtime_paths.py -q
```

`hub_uv.py` keeps the Python runtime outside the repo so the working tree does
not get polluted with local virtualenv state.

## What it does

Graph Making Hub coordinates the work around a research figure:

1. read a project's `project_config.yaml`,
2. validate declared data contracts,
3. run analysis scripts when needed,
4. render figures and diagrams,
5. apply journal/presentation styling,
6. write provenance so the run can be audited later.

It is designed around a simple rule: **data is the API**. A figure should be
traceable back to declared inputs, scripts, config, environment, and output files.

## Daily commands

```bash
# Choose a configured project interactively
graphhub

# List configured projects
graphhub --list-projects

# Run the full pipeline for one project
graphhub --project "ProjectName" --step all

# Re-render figures only
graphhub --project "ProjectName" --step plot

# Re-render diagrams only
graphhub --project "ProjectName" --step diagrams

# Force a clean rerun
graphhub --project "ProjectName" --step all --force
```

From a source checkout, the equivalent command is `python orchestrator.py ...` or
`python hub_uv.py run python orchestrator.py ...`.

## Starting a new project

```bash
graphhub --init --project "new_project_folder"
```

That creates a scaffold with a `project_config.yaml`, script folders, and output
folders. The config is the contract between your data, analysis, and figures.

A minimal project shape looks like this:

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

## MCP smoke check

The package exposes a Model Context Protocol server entry point:

```bash
graphhub-mcp --smoke
```

A healthy smoke response looks like:

```json
{"status": "ok", "health_status": "ok", "tool_surface": "graphhub_mcp"}
```

Use this before wiring the package into an agent or external MCP client.

## Quality gates

The repository currently verifies release candidates with these checks:

```bash
uv build
python scripts/package_metadata_smoke.py
python scripts/public_package_surface.py
python scripts/consumer_install_smoke.py
uv run --with twine python -m twine check dist/*
python hub_uv.py run python -m pytest -q
python hub_uv.py run ruff check .
```

After the GitHub Release is created and the wheel/sdist are uploaded, maintainers
also run:

```bash
python scripts/github_release_asset_smoke.py
```

`python scripts/check_public_release.py` is expected to block today because the
repo is still private/internal and the license is not public/open-source.

## When something goes wrong

- `project_config.yaml not found`
  Run `graphhub --init --project "<project>"` or move into a configured project.

- `Project directory not found`
  Run `graphhub --list-projects` and copy the exact configured name.

- Strict lockfile errors
  `--strict-lock` is for reproducibility checks. For a quick local render, rerun
  without strict mode; for release or audit work, add/fix the lockfiles.

- Google Drive files feel stuck
  Let Drive finish syncing, then rerun. The hub also has a prefetch layer for
  declared inputs, but it cannot repair a broken Drive login/session.

## Repo map

- `orchestrator.py` — CLI entry point.
- `hub_core/` — config parsing, validation, cache, provenance, process execution, MCP logic.
- `plotting/` — reusable plotting helpers.
- `themes/` — journal and presentation style presets.
- `scripts/` — release, packaging, and distribution checks.
- `tests/` — regression and contract tests.
- `docs/packaging/pypi-readiness.md` — current packaging and public-release boundary.

## What is next

The next real public-distribution step is not more packaging code. It is a policy
decision:

1. choose the public license or source-available terms,
2. decide whether the PyPI name remains `graph-making-hub` or changes,
3. remove or split private docs/tests/style packs from the public release surface,
4. make `scripts/check_public_release.py` pass,
5. then publish to TestPyPI/PyPI through the guarded uploader.

Until then, the supported sharing path is the GitHub Release wheel for users who
already have repository access.
