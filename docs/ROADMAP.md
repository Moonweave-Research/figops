# FigOps - Roadmap and Current State

> North star: **a shareable lab tool** with reproducible project execution,
> publication-quality plotting, self-describing MCP tools, and honest
> operational guardrails.
>
> Status baseline: source checkout `0.18.0` release candidate after authentic
> journal-style integration and runtime, packaging, and release hardening. The
> latest published PyPI package and GitHub Release remain `0.17.11`. M1 through
> M5 have shipped across the 0.5.0+ release line. The
> remaining roadmap is maintenance, scoped debt reduction, and bounded
> polish-layer waves that preserve journal constraints.

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
- Journal visual evidence uses a three-gate policy: quick pytest/text checks for
  normal PRs; full MCP visual dogfood only locally, manually, or through an
  explicitly dispatched/path-filtered evidence workflow; and release review that
  combines package readiness with preserved `render-pack/summary.json`,
  `render-pack/style_delta_summary.json`, and contact-sheet inspection. The existing `CI`
  workflow is not the place to regenerate large render packs for unrelated
  changes.

## Current-state scorecard (0.18.0 release-candidate source line, 2026-07-10)

| Dimension | Score | Read |
|---|---:|---|
| Vision and feature breadth | 9/10 | Data contracts, provenance, regression checks, geometry QA, semantic checks, journal styles, and domain helpers are deep for a lab tool. |
| Fundamentals and security | 9/10 | Audit-fix issues #153-158 are resolved; MCP root/runtime trust, duplicate-key YAML loading, symlink guards, and runtime-root isolation are in place. |
| Code maintainability | 8/10 | The MCP monolith is decomposed, data-contract IO/semantics are split, and the 2026-06-29 decomposition wave brought the prior primary hotspots below 1000 lines with compatibility shims intact. Remaining size debt is narrower and tracked as maintenance, not a blocking milestone. |
| Generality / portability | 7/10 | Prefetch, Athena, and conventions adapters are opt-in with generic defaults; project status and schema versioning are explicit. |
| DX / docs / discoverability | 8/10 | Registry-backed `figops.describe`, generated `docs/tools.md`, `docs/mcp_errors.md`, and `figops.doctor` have shipped. |

Roadmap goal: keep fundamentals and DX >=8 while paying down concentrated module
size debt without reintroducing broad refactors.

Post-release total QA checkpoint:

- Current checkpoint: `docs/specs/2026-07-04-post-release-total-qa-plan.md`.
- Journal tracks are implemented as encoded minimum-compliance token
  differences, not only labels:
  Nature, Science, ACS, RSC, Elsevier, Wiley, and Cell resolve distinct width,
  font, line, marker, errorbar, height, and distribution-rendering tokens.
- Authentic visual-language differences are bounded by the dated
  `docs/specs/2026-07-04-journal-visual-language-matrix.md` and comparison
  evidence from `docs/specs/2026-07-04-journal-style-delta-report.md`; they are
  source-backed where possible and explicitly heuristic where the matrix says
  so. These documents do not claim current publisher compliance beyond their
  source dates and recorded limitations.
- MCP agent surface is complete for the current contract: 13 canonical
  `figops.*` tools, 13 legacy `graphhub.*` aliases, generated schemas, and
  handler mappings are present.
- Operational release controls are in place: latest checked `main` CI passed,
  publish is manual-only and main-branch guarded, and PyPI/TestPyPI/GitHub
  Release install-smoke evidence is documented.
- Public claim wording remains publication-oriented; `manual_review_needed=false`
  is not by itself a publishable verdict. `publishable` or `journal-ready`
  wording requires cited hard-gate evidence and `manual_review_needed` not true.
- Current journal-style dogfood evidence for Todo 10 is recorded at
  `.omo/evidence/task-10-journal-style-real-use-hardening-final/render-pack/`;
  it supports review of rendered differences but is not a publisher acceptance
  signal.
- Remaining work is quality hardening rather than release repair: journal-track
  fixture qualification, MCP agent-consumability guards, local operator
  readiness around `uv`, diagnostic-to-rubric mapping, and maintenance
  decomposition.

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
  data_contract.py            # data-contract orchestration and compatibility surface
  data_contract_io.py         # table loading, supported formats, path collection
  data_contract_semantics.py  # compatibility surface for semantic validators
  data_contract_semantic_*    # focused semantic validator families
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
- The module-size budget remains a split signal rather than a hard threshold.
  Inventory freshness is pytest-checked through `tests/test_architecture_inventory.py`;
  import layering remains policy-only.

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

The first polish-layer implementation waves have shipped through shared legend
polish: typed complex MCP schemas, series visual hierarchy controls, Smart
Callout v1, bounded legend/axis controls, dense point-label polish, contrast
diagnostics, tick readability, multipanel layout controls, fit/trend overlay
styling, and shared multipanel legend placement. The active polish roadmap now
lives in:

- `docs/specs/polish-layer-adversarial-roadmap.md`
- `docs/specs/polish-layer-legend-axis-wave.md`
- `docs/specs/polish-fixture-manifest.json`

The first graph-QA hardening slices are now shipped and guarded:

1. `tests/fixtures/journal_tracks/` contains manifest-backed Nature, Science,
   ACS, RSC, Elsevier, Wiley, and Cell fixture coverage with expected summaries,
   token floors, geometry diagnostics, and layout-report expectations.
2. `tests/test_mcp_agent_consumability.py` keeps live tool names, legacy
   aliases, handler discovery, generated `docs/tools.md`, prompts, and internal
   playbooks aligned.
3. `figops.doctor` checks `uv`, the external source-checkout runtime root, and
   the active Python environment without weakening `hub_uv.py` fail-fast
   behavior.
4. `scripts/check_geometry_rubric_map.py` and its tests require every
   `geometry_diagnostics/1` metric to resolve to a hard, advisory, or explicit
   informational rubric status.

The next priority is behavior-preserving maintenance decomposition from the
live architecture inventory. Do not reclassify shipped polish controls as open
gaps unless a regression is proven.

### R1 - Large-module decomposition

`hub_core/data_contract.py` has already had its IO and semantic helper layers
extracted. Data loading, supported-format checks, optional I/O dependency
detection, contract path collection, and prefetcher resolution live in
`hub_core/data_contract_io.py`. Semantic-check definitions, semantic validators,
calculation sidecar helpers, statistical quality checks, unit helpers, and
ordering helpers live in focused semantic modules. `hub_core.data_contract`
keeps compatibility shims for existing private imports and monkeypatch surfaces.

The 2026-06-29 decomposition wave completed the active primary-hotspot track:

- `plotting/bridge_renderer.py` is below 1000 lines after plot-type renderer,
  overlay, shared-legend, manuscript-layout, and figure-style helper
  extraction.
- `hub_core/config_parser.py` is below 1000 lines after style/schema,
  research-metadata, semantic-check, project-registry, sweep/comparison, and
  visual-output validation extraction.
- `hub_core/data_contract_semantics.py` is below 600 lines after registry,
  unit, ordering, grouped, statistical, scalar, quality, and calculation-check
  helper extraction.
- `hub_core/geometry_diagnostics.py`, `hub_core/mcp/tools/render_csv.py`, and
  `hub_core/mcp/schemas.py` have also been reduced through focused helper
  modules while preserving compatibility aliases.

Remaining over-budget files are listed in `docs/architecture.md`. Future
extractions should be selected from that live inventory, remain
behavior-preserving, keep public imports compatible, and add a witness test for
the behavior being moved.

The 2026-07-11 bounded slice extracted sweep and comparison orchestration from
`hub_core.process_runner` behind its existing public compatibility façade. The
facade preserves environment-overlay, failure-stage, path-containment, and
monkeypatch contracts while reducing variation-specific control flow in the base
pipeline module.

The subsequent 2026-07-11 slice extracted visual-regression baseline manifest
state, snapshot persistence, decision flow, and reporting aggregation into
`hub_core.visual_regression_baselines`. The `hub_core.visual_regression` façade
retains its existing private helper import and monkeypatch surface while keeping
comparison algorithms in their established module.

The next 2026-07-11 slice extracted display-space marker footprints,
paintability handling, and severe marker-overlap reporting into
`hub_core.geometry_marker_footprints`. The geometry-diagnostics façade retains
the corresponding private helper names to preserve renderer and test patch
contracts.

The subsequent 2026-07-11 slice extracted multi-panel assembly validation and
language-policy normalization into `hub_core.config_assemblies` and
`hub_core.config_language_policy`. `hub_core.config_parser` preserves its
assembly entry point and retains `get_language_policy` as a wrapper so the
existing `normalize_lang` monkeypatch seam remains intact.

The next 2026-07-11 slice extracted the visual artifact batch and per-input
expansion execution paths into `hub_core.process_runner_visual_batch` and
`hub_core.process_runner_visual_expansion`. The process-runner façade passes
low-level collaborators at call time, preserving command, cache, and output
verification monkeypatch seams.

The current execution plan for that maintenance track lives in
`docs/specs/2026-06-28-large-module-decomposition-plan.md`.

### R2 - Architecture guardrails

The large-module inventory is now pytest-checked for freshness through
`tests/test_architecture_inventory.py`, which keeps `docs/architecture.md`
aligned with live source. The 800-line budget remains a split signal rather than
a hard failure threshold, and downward import layering is still policy-only. If
layering regressions become recurring, add an import-linter contract as its own
PR. Do not imply that import-layer enforcement exists until it does.

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
