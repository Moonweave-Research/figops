# FigOps - Roadmap and Current State

> North star: **a shareable lab tool** with reproducible project execution,
> publication-quality plotting, self-describing MCP tools, and honest
> operational guardrails.
>
> Status baseline: source checkout `0.20.0` release-candidate line, with the
> AI-native v2 surface and bounded evidence/policy-projection path
> implemented after the `0.19.0` publication-readiness release. PR #224 adds
> the `figops-project-v1.1` role contract, external runtime/durable-result
> boundary, receipt/claim/raw-integrity corrections, and reviewed copy-only
> organization workflow. The latest published PyPI package and GitHub Release
> remain `0.19.0` until a separate approved promotion. M1 through
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

## Current-state scorecard (0.20.0 release candidate, 2026-07-19)

| Dimension | Score | Read |
|---|---:|---|
| Vision and feature breadth | 9/10 | Data contracts, provenance, regression checks, geometry QA, semantic checks, journal styles, and domain helpers are deep for a lab tool. |
| Fundamentals and security | 9/10 | Project/allowed-data inputs share contained descriptors; v1.1 roles, runtime/result disjointness, native no-replace promotion, durable receipts, raw-integrity, dynamic-claim review, and write gating fail closed. |
| Code maintainability | 8/10 | Structure contract/layout/inventory/audit/plan/role-binding/apply, runtime boundary/result promotion/receipt, external-raw execution, claim inspection, preview, schema, and inspection responsibilities are focused modules guarded by the live architecture inventory. |
| Generality / portability | 8/10 | Declared roles replace mandatory folder names; legacy projects resolve in memory, external raw stays launcher-authorized, and bespoke adapters remain opt-in. |
| DX / docs / discoverability | 9/10 | AI-native v2 discovery is compact and filterable; generated `tools-v2.md`, `tools-compatibility.md`, and the full maintenance reference keep the frozen surface available on demand. |

Roadmap goal: keep fundamentals and DX >=8 while paying down concentrated module
size debt without reintroducing broad refactors.

Current release-candidate checkpoint:

- Current checkpoint: PR #224 and
  `docs/specs/2026-07-15-project-structure-runtime-integrity-plan.md`. That
  corrective SSOT governs the remaining acceptance matrix, actual-R gate,
  independent review, approvals, and promotion sequence.
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
- MCP agent surface is complete for the current contract: 14 canonical
  `figops.*` tools, 13 frozen legacy `graphhub.*` aliases, generated schemas, and
  handler mappings are present.
- MCP discovery is now profile-aware. The launcher defaults to `v2` with at
  most seven evidence-first tools; `compatibility` exposes the frozen 14 + 13
  contract. Writes-disabled discovery omits denied operations while the
  independent handler guard rejects remembered canonical and alias names.
- Operational release controls are in place: latest checked `main` CI passed,
  publish is manual-only and main-branch guarded, and PyPI/TestPyPI/GitHub
  Release install-smoke evidence is documented.
- Public claim wording remains publication-oriented; `manual_review_needed=false`
  is not by itself a publishable verdict. `publishable` or `journal-ready`
  wording requires cited hard-gate evidence and `manual_review_needed` not true.
- The 0.19.0 Publication Readiness MVP remains a read-only synthesis
  layer over existing evidence. It reports `blocked`, `needs_revision`, or
  `needs_review`; approval lifecycle and submission packaging remain future work.
- Current journal-style dogfood evidence for Todo 10 is recorded at
  `.omo/evidence/task-10-journal-style-real-use-hardening-final/render-pack/`;
  it supports review of rendered differences but is not a publisher acceptance
  signal.
- The AI-native rearchitecture remains implemented in the working tree: bounded data
  inspection, one-call basic/project rendering, explicit-policy audit, lazy
  preview resources, raw-preserving authored output, and outcome-based agent
  guidance are covered by runtime witnesses. The newer corrective implementation
  adds the v1.1 declared-role contract, one shared layout, semantic structure
  inventory/audit/plan/role-binding/apply, launcher-authorized external-raw
  execution, native no-replace result promotion, durable receipts, measured
  policy evidence, and verified project-script claims including conservative
  dynamic-annotation discovery. CI run
  [`29689087108`](https://github.com/Moonweave-Research/figops/actions/runs/29689087108)
  passed for source head `9e4d340b718529bd0f65ba46b2124dda718918a2`: macOS full
  pytest was 2,322 passed, 22 skipped, and 104 subtests, including the native
  `/var`/`/private/var` alias gate at 9/0; Windows containment and symlinks was
  48/0 with zero skipped security tests; and actual R was 2/0 on R 4.4.2,
  readr 2.2.0, and dplyr 1.2.0. Ruff and dependency audit passed as well.
  Final package witnesses were built from that head in the external
  `figops-package-9e4d340b-r1/artifacts/` directory, not repository `dist/`:
  wheel `figops-0.20.0-py3-none-any.whl` (634,485 bytes,
  `9623cb8675af47a184ab83636ef390220608514957da885f8ca1dd42b8403cbd`) and
  sdist `figops-0.20.0.tar.gz` (526,180 bytes,
  `b7128735c0f3eba259eea30bcadbda4e864f3bd101d05246a04a5cae9fbc7511`).
  Twine validation, package-surface inspection, and clean consumer smoke
  passed; installed discovery remains 7 v2 tools and 27 compatibility tools.
  The artifacts are not yet published. Repository owner authorization for the
  v0.20.0 public release is recorded as
  `repository_public_release_authorized=true` with one approval-evidence
  reference: [PR #224 owner authorization](https://github.com/Moonweave-Research/figops/pull/224#issuecomment-5016360221).
  Execute merge, tag, package publication, GitHub Release, and release
  promotion only after rechecking technical gates for the exact release commit.

---

## Current architecture

```
figops_mcp_server.py        # thin stdio entrypoint and --smoke
hub_core/
  mcp/                        # shipped decomposition of the former mcp_surface.py
    transport.py              # JSON-RPC framing, dispatch, batch, lifecycle
    server.py                 # FigOps facade + historical GraphHub Python alias
    config.py                 # trusted root/runtime/server config
    security.py               # path guards, write gating, env trust
    errors.py                 # MCP/tool error mapping
    schemas.py                # shared schema helpers
    tools/                    # grouped handlers backed by live schemas
    render_orchestration.py   # worker spawn, snapshots, geometry env wiring
    render_manifest.py        # immutable job manifest and preview sealing
    manifest_io.py            # verified, bounded runtime-manifest reads
    preview_artifacts.py      # safe lazy preview/resource validation
    preview_worker.py         # bounded raster/PDF conversion worker
    render_geometry.py        # render geometry helpers
    resources.py / prompts.py # MCP resources and prompts
    surface_profiles.py       # compact v2 and frozen compatibility discovery
  adapters/                   # opt-in prefetch, Athena, and conventions adapters
  rendering/                  # plot-type registry and render backend surface
  domain_analysis.py          # registered domain analysis helpers
  data_contract.py            # data-contract orchestration and compatibility surface
  data_contract_io.py         # table loading, supported formats, path collection
  data_contract_semantics.py  # compatibility surface for semantic validators
  data_contract_semantic_*    # focused semantic validator families
  project_paths.py            # contained project I/O resolver
  project_config_reader.py    # verified config discovery/resource reads
  project_structure_contract.py # v1.1 role/DAG/alias resolution
  legacy_structure_resolver.py  # legacy 1.0 in-memory compatibility view
  project_layout.py             # shared scaffold/normalization inventory
  structure_inventory.py / structure_audit.py / structure_plan.py
                               # read-only semantic discovery and reviewed plan
  structure_role_binding.py    # approved destinations bound to declared roots
  structure_apply.py           # write-gated copy-only apply transaction
  runtime_boundary.py          # project/result/runtime disjointness
  atomic_no_clobber.py         # native consuming same-FS no-replace publication
  durable_promotion.py         # staged same-filesystem result promotion
  durable_receipt.py           # runtime-independent lineage receipt
  result_promotion.py          # production eligibility/admission integration
  external_raw.py / external_raw_execution.py
                               # trusted identity and verified runtime materialization
  calculation_evidence.py / claim_inventory.py / claim_script_inspection.py
                               # durable lineage and conservative dynamic-claim review
  artifact_policy_measurement.py / render_evidence.py
                               # artifact-derived policy measurements
  evidence_contract.py        # closed figops_evidence/2 validation
  evidence_artifact_section.py # focused artifact/evidence validation
  artifact_integrity.py       # verified artifact facts
  artifact_audit.py           # integrity kernel + explicit policy packs
  data_inspection*.py         # bounded data facts and worker limits
  process_runner.py           # pipeline execution helpers
themes/                       # journal styles, palettes, font tokens
plotting/renderers/
  overlays.py                 # overlay rendering compatibility façade
  annotation_normalization.py # bounded annotation/callout normalization
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
- Normal Test and Ruff CI use pinned uv plus `--locked`; both jobs are gating.
- The advisory dependency audit pins uv and pip-audit, exports from the lock,
  and runs in explicit UTF-8 mode for locale-independent diagnostics.
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
- The manual publish build pins uv, validates the project lock before testing,
  builds standards-compliant artifacts with `--no-sources`, and lock-enforces
  metadata checks, consumer installation smoke, and upload-policy validation.

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

The subsequent 2026-07-11 slice extracted the complete
`figops.render_csv_multipanel` envelope into
`hub_core.mcp.tools.render_csv_multipanel_handler`. The CSV render mixin still
supplies its original renderer instance, preserving runtime-root, write safety,
manifest, status, and response-envelope behavior.

The next 2026-07-11 slice extracted project snapshot, figure-script runtime,
redaction, and failure-artifact helpers into
`hub_core.mcp.render_project_runtime`. The render-orchestration façade remains
the compatibility surface for project-render error types and the patchable
render timeout; its source is now below the 800-line maintenance signal.

The subsequent 2026-07-11 slice extracted multi-panel specifications and
draft/manuscript composition orchestration into
`plotting.renderers.multipanel`. `plotting.bridge_renderer` retains its public
spec names and private composition helpers as context-backed compatibility
wrappers, including the existing `save_journal_fig` patch seam.

The next 2026-07-11 token-free journal slice extracted only the opt-in text
decluttering engine into `themes.declutter`. Journal presets, font and line
tokens, compliance clamps, output formats, diagnostics ordering, and the
`save_journal_fig` chokepoint remain unchanged in the journal-theme façade.

The subsequent 2026-07-11 journal slice extracted the application of resolved
font and line compliance floors into `themes.compliance`. It preserves the
original private clamp names and warning stack levels; preset values,
compliance-token resolution, output formats, and diagnostics ordering remain
in `themes.journal_theme`.

The next 2026-07-11 bridge slice extracted CSV required-column validation,
finite-number filtering, point payload normalization, x parsing, and
point-label option normalization into `plotting.renderers.point_loader`.
`plotting.bridge_renderer` directly re-exports its original private helpers and
is now below the 800-line architecture split signal.

The subsequent 2026-07-11 journal slice extracted font-token preset creation
and scale/profile resolution into `themes.font_token_resolver`. The public
`FontTokens` type remains façade-owned, and the live profile collaborators are
passed through explicitly. With `themes.journal_theme` now below 800 lines, no
tracked Python module exceeds the current architecture split signal.

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
