# FigOps - Roadmap and Current State

> North star: **a shareable lab tool** with reproducible project execution,
> publication-quality plotting, self-describing MCP tools, and honest
> operational guardrails.
>
> Status baseline: v0.17.9+ after polish-layer PRs #196-#198. M1 through M5 have shipped across
> the 0.5.0+ release line. The remaining roadmap is maintenance, scoped debt
> reduction, and bounded polish-layer waves that preserve journal constraints.

## How to read this

- This file is now a current-state roadmap, not the pre-0.5.0 implementation
  plan.
- Release history for shipped milestones lives in `CHANGELOG.md`.
- `task.md` remains historical handover memory; `AGENTS.md` remains the
  operating protocol.

## Execution methodology

- Behavioral changes need runtime-witness tests.
- Use one PR per coherent change, branched off `main`, base `main`.
- Keep diffs minimal and scoped to the stated contract.
- Run local verification before PR: `python hub_uv.py run python -m pytest`
  and `ruff check .` unless the change explicitly justifies a narrower gate.
- Actions are not part of local verification and should not be triggered for
  docs-only work.

## Current-state scorecard (v0.15.0, 2026-06-21)

| Dimension | Score | Read |
|---|---:|---|
| Vision and feature breadth | 9/10 | Data contracts, provenance, regression checks, geometry QA, semantic checks, journal styles, and domain helpers are deep for a lab tool. |
| Fundamentals and security | 9/10 | Audit-fix issues #153-158 are resolved; MCP root/runtime trust, duplicate-key YAML loading, symlink guards, and runtime-root isolation are in place. |
| Code maintainability | 7/10 | The MCP monolith is decomposed and ruff is clean. Remaining debt is concentrated in large modules, especially `hub_core/data_contract.py`. |
| Generality / portability | 7/10 | Prefetch, Athena, and conventions adapters are opt-in with generic defaults; project status and schema versioning are explicit. |
| DX / docs / discoverability | 8/10 | Registry-backed `figops.describe`, generated `docs/tools.md`, `docs/mcp_errors.md`, and `figops.doctor` have shipped. |

Roadmap goal: keep fundamentals and DX >=8 while paying down concentrated module
size debt without reintroducing broad refactors.

---

## Current architecture

```
figops_mcp_server.py        # thin stdio entrypoint and --smoke
hub_core/
  mcp/                        # shipped decomposition of the former mcp_surface.py
    transport.py              # JSON-RPC framing, dispatch, batch, lifecycle
    server.py                 # GraphHubMCPServer facade
    config.py                 # trusted root/runtime/server config
    security.py               # path guards, write gating, env trust
    errors.py                 # MCP/tool error mapping
    schemas.py                # shared schema helpers
    tools/                    # grouped handlers backed by live schemas
    render_orchestration.py   # worker spawn, snapshots, geometry env wiring
    render_geometry.py        # render geometry helpers
    resources.py / prompts.py # MCP resources and prompts
  adapters/                   # opt-in prefetch, Athena, and conventions adapters
  rendering/                  # plot-type registry and render backend surface
  domain_analysis.py          # registered domain analysis helpers
  data_contract.py            # largest remaining module; future split candidate
  process_runner.py           # pipeline execution helpers
themes/                       # journal styles, palettes, font tokens
docs/                         # quickstart, generated tool refs, specs, roadmap
```

Principles: thin transport/dispatch, registry-backed tools and plot types,
generic defaults for bespoke integrations, and docs generated from live
registries wherever possible.

---

## Shipped milestones

### M1 - Maintainability and architecture

**Shipped in 0.5.0.** The MCP surface was decomposed into focused modules under
`hub_core/mcp/`. The old `hub_core/mcp_surface.py` file is deleted.

What is true now:

- `figops_mcp_server.py` remains a thin entrypoint.
- `GraphHubMCPServer`, `run_stdio_server`, and `list_tool_definitions` are
  exported from the decomposed MCP package.
- Ruff debt has been cleared; `ruff check .` is expected to pass with 0 errors.
- The module-size budget remains aspirational, not CI-enforced. Current
  over-budget files are listed in `docs/architecture.md`.

### M2 - Fundamentals

**Shipped across 0.5.0 and later audit-fix releases.** Transport safety, error
behavior, public-release checks, reproducibility gates, structured logging
entry points, and trust-boundary handling were strengthened.

Current remaining fundamentals debt is narrow and should be tracked as concrete
issues rather than a broad milestone.

### M3 - Generality / decoupling

**Shipped.** The adapter layer, plot-type registry, config schema versioning,
and root/runtime configuration trust model are in place.

Current state:

- Prefetch, Athena, and conventions adapters default to off/generic behavior.
- `project_config.yaml` supports schema versioning and migration.
- `project.status` supports `active` and `legacy`.
- Root/runtime and allowed-data-root env inputs are documented in `AGENTS.md`
  and validated before widening access.

### M4 - Feature breadth

**Shipped in 0.6.0 and later releases.**

- M4.1 multi-series broken-axis rendering shipped.
- M4.2 plot coverage expanded to box plots, violin plots, faceting /
  small-multiples, statistical overlays, and grouped-bar aggregation.
- M4.3 materials/polymer domain helpers shipped.
- M4.4 richer semantic data contracts shipped, including monotonic checks,
  expected sample counts, and unit-coherence checks.

### M5 - DX, docs, shareability

**Shipped across 0.5.0 and later releases.**

- M5.1 registry-backed `figops.describe` shipped.
- M5.2 generated tool docs and MCP error docs shipped and are checked for
  freshness.
- M5.3 `figops.doctor` / smoke-style environment readiness checks shipped.
- M5.4 release discipline is active through `pyproject.toml`, `CHANGELOG.md`,
  and tags beginning at v0.6.0.

---

## Research-ops enforcement

Research-operations philosophy Tiers 1-3 have shipped.

As of v0.15.0, module projects enforce the Tier 1-3 rules by default across CLI
and MCP render paths: master-root execution is refused, raw-integrity drift
blocks renders, declared figure traceability chains are validated, placeholder
markers are forbidden, and declared canonical docs must exist.

This is strict but scoped:

- Default enforcement applies to `project.role: module`.
- Master projects are governance / aggregation roots, not runnable modules.
- Explicit `false` opt-outs remain available for scoped relaxation.
- `project.status: legacy` is supported to describe legacy projects without
  treating the status as a runnable-success signal.

---

## Remaining roadmap

### R0 - Polish-layer roadmap and fixture refresh

The first polish-layer implementation waves have shipped: typed complex MCP schemas,
series visual hierarchy controls, and Smart Callout v1. The active polish roadmap
now lives in:

- `docs/specs/polish-layer-adversarial-roadmap.md`
- `docs/specs/polish-layer-legend-axis-wave.md`
- `docs/specs/polish-fixture-manifest.json`

Next implementation priority: bounded legend and axis polish controls. Follow-up
priorities are dense point-label polish, contrast diagnostics, tick readability,
and multipanel layout polish. Do not reclassify shipped schema, series hierarchy,
or Smart Callout v1 capabilities as open gaps unless a regression is proven.

### R1 - Data-contract decomposition

`hub_core/data_contract.py` is the largest remaining module at 2600 lines
(`wc -l`, 2026-06-21). A future decomposition should split loading, schema
validation, semantic validation, calculation checks, and reporting only when a
small behavior-preserving sequence can keep the full suite green.

### R2 - Architecture guardrails

The 800-line module budget and downward-layering rule are not currently
CI-enforced. If this becomes a recurring regression, add a small architecture
check or import-linter contract as its own PR. Do not imply the guard exists
until it does.

### R3 - Release and docs hygiene

Keep `CHANGELOG.md`, generated docs, `AGENTS.md`, and `docs/architecture.md`
aligned with live registries and code. Prefer generated docs for MCP surfaces
and small hand-maintained docs for policy and architecture.

### M6 - Pluggable render backend SPI

Deferred / not planned for the current shareable-lab-tool goal. The current
registry and backend surface are enough for in-repo matplotlib-backed plot
types. A third-party plugin/SPI path should wait until there is a real consumer
and a packaging/distribution decision.

## Tracking

- Keep `CHANGELOG.md` as the release-history source for 0.5.0+ shipped work.
- Keep `task.md` as historical handover memory, not the source of current
  roadmap truth.
- Use focused GitHub issues for new debt and feature work.
