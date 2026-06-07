# AGENTS.md — Research Hub Unified Agent Protocol (v4.0)

> Identity: This is the single, model-agnostic operating protocol for the independent `graph-making-hub` repository.
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

---

## 4) Public Contract (Runtime Env)

Orchestrator injects the following vars:
- `RESEARCH_HUB_PATH`: Absolute path to the hub.
- `PROJECT_ROOT`: Absolute path to the active research project.
- `THEME_FORMAT`: `nature | science | ppt | default`
- `THEME_SCALE`: Font scaling factor.
- `THEME_PROFILE`: Active style profile name.

---

## 5) Local Operational Ownership

Graph Hub locally owns per-project analysis and plotting orchestration via `orchestrator.py` and `project_config.yaml` contracts. Workspace-level figure or schematic integrations may reference this repo, but current operational ownership for analysis, plotting, cache behavior, and project scaffolding stays here.

Programmatic schematic Hub integration may be described in workspace-level specs, but it is not wired into the current Hub orchestrator CLI unless this repository documents that change.

## 6) Common Commands

Run from the independent `graph-making-hub/` clone:

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
- Prefer `python hub_uv.py ...` over bare `uv run ...` inside this repo. The wrapper pins `UV_PROJECT_ENVIRONMENT` and `UV_CACHE_DIR` under the external Graph Hub runtime root so a materialized repo-local `.venv/` is not recreated.

## 9) Standardized Plotting Policy

Before adding plot-specific utility code, check `plotting/utils.py` for an existing shared helper. Reuse and extend shared helpers such as `compress_sample_label` instead of re-implementing ad-hoc formatting logic inside project plots.

---

**Last Update**: 2026-06-07 (independent repo cleanup, uv/Docker alignment, retired DVC wording)
