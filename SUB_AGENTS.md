# Graph Making Hub - Sub-Agent Protocol (v4.0)

> Scope: This file defines model-agnostic sub-agent ownership for `[Graph_making_hub]`.
> Main agent and global rules are defined in `AGENTS.md`.

---

## 1) Sub-Agent Topology

| Sub-agent | Primary Ownership | Key Responsibilities (v4.0) |
|---|---|---|
| `Pipeline-Orchestrator` | `hub_core/` (config, cache, runner, provenance, utils) | Interactive CLI selection, Smart Build caching logic, DVC/Git provenance logging. |
| `Academic-Stylist` | `themes/*`, `plotting/*` | Journal preset management, palette SSOT (`palettes.yaml`), reusable plot primitives. |
| `Data-Contract Guardian` | `hub_core/data_contract.py` | Basic (Dtypes) and **Semantic (Range, Null, Unique)** validation logic. |
| `Project-Migrator` | `project_config_template.yaml`, onboarding | Mapping raw research folders to hub-compliant pipelines and `analysis_helpers` integration. |

---

## 2) Key Role Updates

### 2.1 Pipeline-Orchestrator
- **Interactive Mode**: Must support a selection menu when project paths are omitted.
- **Prefetcher**: Must ensure file availability for GDrive sync folders before starting execution.

### 2.2 Data-Contract Guardian
- **Semantic Logic**: Responsible for enforcing physical/logical bounds on data values.
- **Strip Normalization**: Must handle column name whitespace issues during validation.

### 2.3 Academic-Stylist
- **Determinism**: Must ensure figure metadata (timestamp) is fixed for reproducibility.
- **Shared Libraries**: Maintain `analysis_helpers` for cross-project signal/physics logic.

---

**Last Update**: 2026-03-05 (Refactored Modular Ownership)
