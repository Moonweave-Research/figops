# FigOps

FigOps helps research teams turn raw analysis outputs into reproducible,
publication-ready figures. It is meant to be boring in the best way: one config,
one command, traceable inputs, repeatable outputs.

The short version:

```bash
python -m pip install figops
figops --help
figops-mcp --smoke
```

If those commands work, the public package is installed and the MCP surface is alive.

## Current status

- **Public package:** yes, `figops==0.17.4` is live on PyPI.
- **Current distribution name:** `figops`.
- **Current commands:** `figops` and `figops-mcp` (legacy aliases `graphhub` / `graphhub-mcp` remain for compatibility).
- **GitHub Release assets:** yes, the matching wheel and sdist are attached to `v0.17.4`.
- **License:** Apache-2.0 for public package distribution. Check [LICENSE](./LICENSE) and [NOTICE](./NOTICE) before redistributing.

The repository can remain private/internal while the built wheel and sdist are distributed publicly. Repo-only docs, tests, and internal style packs are not the public API.

## Install from PyPI

For normal users:

```bash
python -m pip install figops
figops --help
figops-mcp --smoke
```

For a pinned install:

```bash
python -m pip install figops==0.17.4
```

The package is available at <https://pypi.org/project/figops/>.

## Install from the current GitHub release

For users who need the exact release asset:

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

Maintainers also verify GitHub Release assets and public package installability:

```bash
python scripts/github_release_asset_smoke.py
python -m pip install figops==0.17.4
figops-mcp --smoke
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

The public package is live. For the next release, keep the same conservative path:

1. bump the version,
2. rebuild wheel/sdist from a clean tree,
3. confirm package artifacts exclude private docs/tests/research markers,
4. publish to TestPyPI through `.github/workflows/publish.yml`,
5. install-check from TestPyPI, then promote the same version to PyPI.

The release checklist is in
[`docs/packaging/public-release-clearance.md`](./docs/packaging/public-release-clearance.md), with exact publishing steps in
[`docs/packaging/trusted-publishing.md`](./docs/packaging/trusted-publishing.md).
