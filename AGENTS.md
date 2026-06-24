# AGENTS.md — Research Hub Unified Agent Protocol (v4.0)

> Identity: This is the single, model-agnostic operating protocol for the independent `figops` repository.
> Principle: Data is the API. Quality is absolute. Silent failure is prohibited.

---

## 1) Canonical Documents (Single Source of Truth)

- Main protocol: `AGENTS.md` (this file)
- Sub-agent responsibilities: `SUB_AGENTS.md`
- Architecture blueprint: `Research_Central_Architecture.md` (Modular Phoenix)
- Execution backlog and handover memory: `task.md`

---

## 2) Main Agent: `Research Hub Commander`

### Mission
Coordinate end-to-end planning, implementation, and verification across the modularized orchestrator, data contracts, and publication-quality plotting.

---

## 3) Engineering Rules (v4.0 Core)

1. **Modular Consistency**: Any logic change must be placed in the appropriate `hub_core/` module. No "God Scripts".
2. **Fail-Fast Enforcement**: Pipeline must exit on script absence, semantic validation failure, or environment mismatch.
3. **Data Provenance**: Every run must output Git/config/environment hashes for reproducibility. DVC is not part of the current required runtime surface.
4. **Cloud-Native Awareness**: Use the Prefetcher (`ensure_local_files`) for any input file to prevent GDrive sync deadlocks.
5. **Research-Ops Enforcement**: Tier 1-3 research-ops rules enforce by default for `project.role: module` projects, with explicit `false` opt-outs for scoped relaxation. `project.status: legacy` is supported for legacy projects.

---

## 4) Public Contract (Runtime Env)

Orchestrator injects the following vars:
- `RESEARCH_HUB_PATH`: Absolute path to the hub.
- `PROJECT_ROOT`: Absolute path to the active research project.
- `THEME_FORMAT`: `nature | nature_surfur | science | ppt | default | acs | rsc | elsevier | wiley | cell`. The live source of truth is `ALLOWED_TARGET_FORMATS` in `hub_core/config_parser.py`; agents can also call `figops.list_styles` or consult generated `docs/tools.md`.
- `THEME_SCALE`: Font scaling factor.
- `THEME_PROFILE`: Active style profile name.

---

## 5) Local Operational Ownership

FigOps locally owns per-project analysis and plotting orchestration via `orchestrator.py` and `project_config.yaml` contracts. Workspace-level figure or schematic integrations may reference this repo, but current operational ownership for analysis, plotting, cache behavior, and project scaffolding stays here.

Programmatic schematic Hub integration may be described in workspace-level specs, but it is not wired into the current Hub orchestrator CLI unless this repository documents that change.

## 6) Common Commands

Run from the independent `figops/` clone:

```bash
# Preferred uv entry point: keeps uv's project env outside the repo
python hub_uv.py run python orchestrator.py --list-projects
python hub_uv.py run python -m pytest tests/test_runtime_paths.py -q

# Interactive project selection
python orchestrator.py

# Run full pipeline
python orchestrator.py --project "01_Ionoelastomer" --step all

# Replot only
python orchestrator.py --project "01_Ionoelastomer" --step plot

# Force rerun
python orchestrator.py --project "프로젝트명" --step all --force

# Scaffold a new project
python orchestrator.py --init --project "새_프로젝트_폴더"

# List configured projects
python orchestrator.py --list-projects

# Smoke tests
python -m unittest tests.test_smoke

# Full regression check across all projects
python orchestrator.py --check-all --step all --force --strict-lock
```

## 7) Key Architecture

- `orchestrator.py`: CLI entry point and top-level pipeline coordinator.
- `hub_core/`: Config loading, validation, cache logic, provenance, process execution, scaffolding, and runtime helpers.
- `analysis_helpers/`: Shared R-side analysis utilities.
- `plotting/`: Shared Python plotting helpers and reusable style logic.
- `themes/`: Journal and presentation style presets.
- `project_config_template.yaml`: Canonical template for new `project_config.yaml` files.

## 8) Dependencies

- Python dependency state from `pyproject.toml` and `uv.lock` for orchestration and plotting.
- R runtime from `renv.lock` for project analysis scripts.
- Keep runtime environments outside tracked source unless a repo-level exception is documented.
- Prefer `python hub_uv.py ...` over bare `uv run ...` inside this repo. The wrapper pins `UV_PROJECT_ENVIRONMENT` and `UV_CACHE_DIR` under the external FigOps runtime root so a materialized repo-local `.venv/` is not recreated.

## 9) Standardized Plotting Policy

Before adding plot-specific utility code, check `plotting/utils.py` for an existing shared helper. Reuse and extend shared helpers such as `compress_sample_label` instead of re-implementing ad-hoc formatting logic inside project plots.

## 10) MCP Env Trust Model

The MCP launcher is trusted. Prefer explicit server config/CLI values for
`hub_path`, `research_root`, `runtime_root`, write-tool enablement, and
allowed data roots. Environment variables remain a supported operator-policy
source and must be validated before they widen access. Boundary-widening values
report warnings through `figops.health`.

- `GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS`: widens read access for MCP data inputs
  beyond the research root and runtime root. Entries must be non-empty,
  absolute, and existing directories. Bad entries are skipped with warnings.
  Broad roots such as `/`, a drive root, or the current user's home directory
  warn by default. Set `GRAPH_HUB_MCP_STRICT_ROOTS=1` to refuse broad roots.
- `GRAPH_HUB_MCP_STRICT_ROOTS`: refuses broad roots listed in
  `GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS` when set to `1`, `true`, `yes`, or `on`.
- `GRAPH_HUB_MCP_STRICT_DATA_ROOTS`: requires explicit MCP data roots when enabled.
- `GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED`: enables MCP tools that write files or
  execute render jobs. It defaults closed when unset.
- `GRAPH_HUB_MCP_RENDER_CSV_MAX_BYTES`: limits MCP CSV render input size.
  Invalid or non-positive values are ignored in favor of the default limit.
- `RESEARCH_HUB_RUNTIME_ROOT` / `RESEARCH_HUB_RUNTIME_HOME`: select where MCP
  jobs, manifests, logs, and generated artifacts are stored. Runtime access
  must stay under the resolved runtime root.
- `GRAPH_HUB_RUNTIME_ROOT`: launcher-compatible fallback for runtime storage root selection.
- `RESEARCH_HUB_PATH`: tells project scripts where to import FigOps helpers.
  The launcher must point it at this repository, not at a user-controlled path.
- `PROJECT_ROOT`: points project scripts at the active project or runtime
  snapshot. Render code must use resolved project/snapshot paths and fail if
  the selected script or output path escapes that tree.
- `GRAPH_HUB_PREFETCH_ADAPTER`: selects the prefetch adapter (`none`/`noop` or
  `gdrive`). Default is no prefetch.
- `GRAPH_HUB_ATHENA_ADAPTER`: selects the Athena bridge (`off`/`null` or
  `legacy`/`on`). Default is no Athena bridge.
- `GRAPH_HUB_CONVENTIONS_ADAPTER`: selects naming/discovery conventions
  (`generic` or `surfur`). Default is generic.
- `ATHENA_PATH`: path used only by the opt-in legacy Athena bridge.

### Runtime / diagnostic env vars

These variables are runtime knobs or diagnostics transport, not MCP
trust-boundary inputs. Do not add them to `ROOT_ADAPTER_SECURITY_ENV_VARS`
unless they start widening roots, write access, or adapter trust.

- `GRAPH_HUB_LOG_LEVEL`: selects FigOps logging verbosity; default is
  `WARNING`.
- `GEOMETRY_DIAGNOSTICS_OUT`: render-scoped sidecar path used for geometry
  diagnostics output.
- `GEOMETRY_DIAGNOSTICS_DEADLINE`: render-scoped absolute epoch deadline used
  by geometry diagnostics to skip work when the render budget is nearly
  exhausted.
- `MPLBACKEND`: matplotlib backend. Render paths default it to `Agg` when a
  headless environment needs a non-interactive backend.
- `GRAPH_HUB_INPUTS`: path-list of resolved analysis input files injected for
  scaffolded analysis scripts.
- `GRAPH_HUB_ALLOW_EMPTY_ANALYSIS`: explicit scaffold escape hatch; when set
  to `1`, generated analysis templates may write empty bootstrap data with a
  warning instead of failing on missing inputs.

---

**Last Update**: 2026-06-21 (v0.15.0 docs drift correction; MCP decomposition, style enum, research-ops, and env docs aligned)
