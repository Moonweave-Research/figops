# FigOps

FigOps helps research teams turn raw analysis outputs into reproducible,
publication-ready figures. It is meant to be boring in the best way: one config,
one command, traceable inputs, repeatable outputs.

The short version:

```bash
figops --help
figops-mcp --smoke
```

If those two commands work, the package is installed and the MCP surface is alive.

## Current status

- **Installable package:** yes. The wheel is built and smoke-tested like an external user would run it.
- **Current distribution name:** `figops`.
- **Current commands:** `figops` and `figops-mcp` (legacy aliases `graphhub` / `graphhub-mcp` remain for compatibility).
- **GitHub Release assets:** yes, for users who already have repository access.
- **Public PyPI:** not uploaded yet. The package policy is now Apache-2.0, and the next gate is TestPyPI/PyPI account publishing.

This means the built package is ready for public package-distribution checks, while the full repository can remain private until repo-only docs/tests/internal style packs are separated. Check [LICENSE](./LICENSE) and [NOTICE](./NOTICE) before redistributing.

## Install from the current GitHub release

For internal users with repository access:

```bash
gh release download v0.17.4 --repo Moonweave-Research/figops --pattern "*.whl" --dir dist-release
python -m pip install dist-release/figops-0.17.4-py3-none-any.whl
figops-mcp --smoke
```

For local development from a clone:

```bash
python hub_uv.py run python orchestrator.py --list-projects
python hub_uv.py run python -m pytest tests/test_runtime_paths.py -q
```

`hub_uv.py` keeps the Python runtime outside the repo so the working tree does
not get polluted with local virtualenv state.

## What it does

FigOps coordinates the work around a research figure:

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
figops

# List configured projects
figops --list-projects

# Run the full pipeline for one project
figops --project "ProjectName" --step all

# Re-render figures only
figops --project "ProjectName" --step plot

# Re-render diagrams only
figops --project "ProjectName" --step diagrams

# Force a clean rerun
figops --project "ProjectName" --step all --force
```

From a source checkout, the equivalent command is `python orchestrator.py ...` or
`python hub_uv.py run python orchestrator.py ...`.

## Starting a new project

```bash
figops --init --project "new_project_folder"
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
figops-mcp --smoke
```

A healthy smoke response looks like:

```json
{"status": "ok", "health_status": "ok", "tool_surface": "figops_mcp"}
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

`python scripts/check_public_release.py` may still block for repo-only private docs/tests.
For PyPI, the manual Trusted Publishing workflow runs the guarded uploader before publishing, so distribution policy, LICENSE/NOTICE, and the built wheel/sdist package surface are checked first.

## When something goes wrong

- `project_config.yaml not found`
  Run `figops --init --project "<project>"` or move into a configured project.

- `Project directory not found`
  Run `figops --list-projects` and copy the exact configured name.

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

The next public-distribution step is TestPyPI, then PyPI, through the manual Trusted Publishing workflow:

1. keep `figops` as the public PyPI name unless a final product review changes it,
2. rebuild wheel/sdist from a clean tree,
3. confirm package artifacts exclude private docs/tests/research markers,
4. make `scripts/guarded_pypi_upload.py --repository testpypi` pass in dry-run mode,
5. run `publish.yml` for TestPyPI, install-check from TestPyPI, then run `publish.yml` for PyPI.

The working checklist is in
[`docs/packaging/public-release-clearance.md`](./docs/packaging/public-release-clearance.md), with exact publishing setup in
[`docs/packaging/trusted-publishing.md`](./docs/packaging/trusted-publishing.md).
