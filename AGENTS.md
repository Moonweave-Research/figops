# AGENTS.md — Research Hub Unified Agent Protocol (v4.0)

> Identity: This is the single, model-agnostic operating protocol for `[Graph_making_hub]`.
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
3. **Data Provenance**: Every run must output DVC status and environment hashes to guarantee 100% reproducibility.
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

**Last Update**: 2026-03-05 (Modularized Architecture, Semantic Contracts, GDrive Integration)
