# FigOps - Architecture

> Companion to `docs/ROADMAP.md`. Describes the v0.20.0 published architecture
> baseline plus current Phase 2 follow-up/Draft PR context, including the
> AI-native v2 agent surface and the PR #224 declared-project/runtime-result
> integrity path.

## Layers and dependency direction

Dependencies point **downward only**. A layer may import from layers below it,
never above.

```
orchestrator.py                    # CLI pipeline coordinator and read-only audit mode
figops_mcp_server.py                # entrypoint (stdio); --smoke; thin
        |
        v
hub_core/mcp/transport.py             # JSON-RPC 2.0: framing, batch, lifecycle, dispatch
        |
        v
hub_core/mcp/server.py                # FigOps facade + historical GraphHub Python alias
        |
        +-- hub_core/mcp/tools/*      # handler groups backed by live schemas
        +-- hub_core/mcp/resources.py # MCP resources
        +-- hub_core/mcp/prompts.py   # MCP prompts
        +-- hub_core/mcp/security.py  # path guards, write gating, env trust
        +-- hub_core/mcp/config.py    # trusted root/runtime/server config
        +-- hub_core/mcp/errors.py    # JSON-RPC / tool error envelopes
        +-- hub_core/mcp/schemas.py   # shared tool schema helpers
        +-- hub_core/mcp/surface_profiles.py # v2/compatibility discovery projection
        +-- hub_core/mcp/preview_*    # bounded, manifest-bound preview production
        +-- hub_core/mcp/render_*     # render orchestration, evidence response, manifests
        +-- hub_core/mcp/manifest_io.py # verified runtime-manifest reads
                |
                v
hub_core/project_paths.py             # contained project input/output resolution
hub_core/execution_project_boundary.py # alias-free producer/write project selection
hub_core/project_config_reader.py     # verified, bounded config discovery/read
hub_core/project_structure_contract.py # v1.1 role/DAG/alias contract
hub_core/legacy_structure_resolver.py  # schema-less 1.0 -> in-memory 1.1 view
hub_core/project_layout.py             # one scaffold/normalization layout inventory
hub_core/structure_inventory.py         # read-only semantic inventory
hub_core/structure_audit.py             # findings, graph, unresolved classification
hub_core/structure_audit_report.py      # all-project diagnostic report assembly/rendering
hub_core/structure_plan.py              # deterministic reviewed copy plan
hub_core/structure_role_binding.py       # destination -> declared role-root binding
hub_core/structure_stage_cleanup.py      # ownership-safe private-stage/lease cleanup
hub_core/structure_apply.py              # token/CAS-guarded copy-only transaction
hub_core/runtime_boundary.py           # project/result/runtime disjointness
hub_core/atomic_no_clobber.py          # native consuming no-replace namespace move
hub_core/durable_promotion.py          # destination-filesystem staged promotion
hub_core/durable_receipt.py            # closed runtime-independent receipt DTO
hub_core/result_promotion.py            # eligible project-render result admission
hub_core/evidence_*.py                # evidence envelope and semantic validation
hub_core/artifact_*.py                # artifact integrity and explicit-policy audit
hub_core/calculation_evidence.py       # durable calculation artifact lineage
hub_core/claim_inventory.py            # publication claim verification
hub_core/claim_script_inspection.py    # conservative dynamic-claim discovery
hub_core/external_raw.py               # trusted external-input descriptor verification
hub_core/external_raw_execution.py     # authorized materialization before producer use
hub_core/publication_*                # readiness evidence, policy projection, report, CLI
hub_core/data_inspection*.py          # bounded data profiling worker/service
hub_core/data_contract.py             # data-contract loading, validation, checks
hub_core/config_parser.py             # project config validation and migration
hub_core/process_runner.py            # pipeline execution helpers
hub_core/rendering/                   # plot registry and render backend surface
        |
        v
hub_core/adapters/*                   # opt-in integrations behind generic defaults
themes/                               # styling leaf
```

- **transport** knows JSON-RPC framing and dispatch, not FigOps domain logic.
- **server** is the facade that wires config, roots, registries, and services.
- **tools** are grouped handler modules under `hub_core/mcp/tools/`.
- **services** such as config parsing, data contracts, rendering, provenance,
  process execution, discovery, and regression logic stay below the MCP layer.
- **adapters** are opt-in integration leaves; generic/no-op behavior is the
  default path.

The old monolithic `hub_core/mcp_surface.py` is no longer part of the current
codebase. M1 shipped in 0.5.0 by decomposing that surface into the
`hub_core/mcp/` package.

## Module-size and boundary rules

The 800-line architecture budget is a split signal, not a hard failure threshold.
Inventory freshness is checked by `tests/test_architecture_inventory.py`, which
compares the committed block below against live source. Import layering remains
policy-only; there is no import-linter contract in `.github/workflows/ci.yml` as
of v0.20.0. Remaining over-budget files should be handled as scoped maintenance
tracks rather than broad rewrites.

Current files over the approximate 800-line budget, measured on 2026-07-23 with
the architecture inventory helper:

```bash
python hub_uv.py run python scripts/architecture_inventory.py --format markdown
```

<!-- architecture-inventory:start -->
| File | Lines |
|---|---:|
<!-- architecture-inventory:end -->

No Python module in the tracked architecture roots (`hub_core`, `plotting`, and
`themes`) currently exceeds the 800-line split signal. Render-project
workflow/policy integrity decisions now live in
`hub_core/mcp/render_project_integrity_context.py`, while the project-render MCP
tool preserves its compatibility imports. Overlay normalization now lives in `plotting/renderers/annotation_normalization.py`,
while the public overlay façade and compatibility imports remain stable.
Structure-plan destination binding now lives in
`hub_core/structure_role_binding.py`, while private-stage and directory-lease
cleanup lives in `hub_core/structure_stage_cleanup.py`;
`hub_core/structure_apply.py` retains its private compatibility aliases while
focusing on transactional execution and config compare-and-swap.
Workflow-intent config defaults, validation, and inspectable report assembly now
live in `hub_core/config_workflow_intent.py`, while `hub_core/config_parser.py`
keeps the public compatibility imports.

The 2026-06-29 decomposition wave reduced the previous primary hotspots below
1000 lines while preserving compatibility shims:
`plotting/bridge_renderer.py`, `hub_core/config_parser.py`,
`hub_core/data_contract_semantics.py`, `hub_core/geometry_diagnostics.py`,
`hub_core/mcp/tools/render_csv.py`, and `hub_core/mcp/schemas.py`.
`hub_core/data_contract.py` has already been reduced to a
compatibility/orchestration surface after IO and semantic helpers were
extracted.

The visual-regression façade now delegates baseline manifest loading, durable
snapshot updates, baseline decision flow, and check-all summary aggregation to
`hub_core/visual_regression_baselines.py`. Existing private helper names remain
available from `hub_core.visual_regression` for downstream compatibility and
monkeypatching.

The geometry-diagnostics façade now delegates display-space marker footprints,
paintability checks, and severe marker-overlap reporting to
`hub_core/geometry_marker_footprints.py`. Its existing private helper names
remain wrappers so renderer and test monkeypatch contracts continue to resolve
through `hub_core.geometry_diagnostics`.

The config-parser façade now delegates multi-panel assembly validation to
`hub_core/config_assemblies.py` and language-policy normalization to
`hub_core/config_language_policy.py`. `get_language_policy` remains a local
wrapper so callers that patch `config_parser.normalize_lang` retain their
existing behavior.

The process-runner façade now delegates non-expanded visual artifacts,
per-input `expand: each` visual execution, and contained/external input
resolution to focused helper modules. `process_runner_inputs.py` owns the
prefetch/revalidation and launcher-authorized external-raw materialization
sequence, while the façade preserves its historical private helper aliases. It
passes visual cache, command, path, and output-verification collaborators at
invocation time so existing `hub_core.process_runner` monkeypatch paths remain
effective.

The CSV render mixin now delegates the complete multipanel tool envelope to
`hub_core/mcp/tools/render_csv_multipanel_handler.py`, passing its renderer
instance through unchanged. Runtime-root activation, write safety, manifest,
status, and envelope methods therefore retain their existing instance-level
contracts.

The MCP render-orchestration façade now inherits project snapshot copying,
figure-script supervision, output redaction, and failure-artifact persistence
from `hub_core/mcp/render_project_runtime.py`. The façade continues to expose
the project-render error types and supplies the live timeout value, preserving
existing imports and timeout monkeypatch contracts.

The AI-native hardening keeps security and evidence mechanics below the tool
surface. `hub_core/project_paths.py` owns contained project inputs and verified
descriptor reads. `hub_core/project_config_reader.py` applies that boundary to
discovery, inspect, validate, batch, and config resources without reopening a
validated pathname. `hub_core/mcp/manifest_io.py` does the same for collected,
readiness, audit, and resource manifests, including duplicate-key, hardlink,
job-ID, post-read identity, and duplicate root/kind ambiguity checks.
`hub_core/evidence_contract.py`,
`hub_core/evidence_artifact_section.py`, and `hub_core/evidence_semantics.py`
own the closed `figops_evidence/2` envelope;
the canonical selected-policy snapshot is the singular `resolved_policy`.
Artifact verification and explicit-policy audit are separated into
`hub_core/artifact_integrity.py` and `hub_core/artifact_audit.py`, while bounded
data profiling is isolated in `hub_core/data_inspection.py` and its worker.

Preview lookup, manifest membership, MIME/header checks, lazy base64, and worker
launch orchestration live in `hub_core/mcp/preview_artifacts.py`; Windows Job
Object containment lives in `preview_process_limits.py`, while conversion work
lives in `preview_worker.py`. Raster and PDF-first-page previews are bounded to 5 seconds,
8 megapixels, a 2,048-pixel longest edge, and 2 MiB raw output, with a hard
256 MiB worker-memory limit where the host provides a reliable primitive.
macOS reports `memory_limit_enforced=false` because Darwin lacks a
reliable `RLIMIT_AS`; bounded source/output sizes, pixel/edge caps, the worker
deadline, CPU/file limits, and process-session containment remain active and
are exposed by `figops.health`. SVG returns typed unavailable until a renderer passes the required
Windows safety smoke; source vector bytes are never substituted for a preview.

The AI-native façade split remains intact after the structure work. Shared tool
schema primitives live in `hub_core/mcp/tool_schema_common.py`, and the v1.1
project-structure tool schema lives in `hub_core/mcp/structure_schemas.py`,
while Phase 2 project-render policy and workflow response schemas live in
`hub_core/mcp/phase2_render_schemas.py`. The registry façade continues to feed
validation, discovery, and generated references. Overlay normalization remains in
`plotting/renderers/annotation_normalization.py`, with compatibility exports in
the public overlay façade.

The PR #224 corrective structure is organized around explicit lower-level
contracts. `project_structure_contract.py` validates v1.1 role roots, nesting,
aliases, and external-raw references; `legacy_structure_resolver.py` provides a
read-only in-memory view for schema-less projects. `project_layout.py` is the
single layout inventory consumed by scaffolding and normalization. Read-only
classification and planning are separated into `structure_inventory.py`,
`structure_audit.py`, and `structure_plan.py`; `structure_role_binding.py` binds
every approved destination back to its declared semantic root, while
`structure_stage_cleanup.py` owns transaction-private stage and lease cleanup.
Reviewed mutation is isolated in `structure_apply.py` and remains copy-only.

Runtime and durable-result mechanics are separate from structure discovery.
`runtime_boundary.py` enforces project/result/runtime disjointness,
`atomic_no_clobber.py` provides the only publication primitive: Windows
`os.rename`, Linux `renameat2(RENAME_NOREPLACE)`, or macOS
`renamex_np(RENAME_EXCL)`. It consumes the private stage name, never replaces a
race winner, and fails closed where the native guarantee is unavailable.
Rollback deletion is identity-bound: Windows verifies file ID and SHA-256
through one non-write-shared handle before applying delete disposition to that
same object. POSIX does not attempt check-then-unlink; ambiguous or still-owned
paths remain in place and produce `FIGOPS_DURABLE_MANUAL_CLEANUP_REQUIRED` for
review instead of risking deletion of a competing inode.
`durable_promotion.py` stages verified bytes on the destination filesystem, and
`result_promotion.py` is the production admission boundary that checks the
persisted runtime manifest, eligibility, policy, and claim gates before invoking
that primitive. `durable_receipt.py` emits the closed receipt DTO that survives
runtime deletion. `external_raw.py` validates trusted source identity;
`external_raw_execution.py` binds launcher authority, materializes below runtime,
and rechecks bytes before CLI or MCP producers receive them. Calculation
artifacts and publication claims are bound through `calculation_evidence.py` and
`claim_inventory.py`; `claim_script_inspection.py` conservatively identifies
dynamic statistical annotation candidates without rejecting unrelated dynamic
author labels. `artifact_policy_measurement.py` and `render_evidence.py` persist
measured render-policy and validation-target outcomes without restyling the
artifact.

The journal-theme façade now delegates its opt-in text/marker overlap nudge,
leader-line targeting, axes-edge correction, and convergence reporting to
`themes/declutter.py`. Journal style tokens, rcParams, compliance floors,
save-format behavior, and the `save_journal_fig` chokepoint remain in
`themes/journal_theme.py` unchanged.

The same façade delegates the application of already-resolved font and line
floors to `themes/compliance.py`, covering rcParams and live figure artists.
Preset definitions and compliance-token resolution remain in
`themes/journal_theme.py`, while the original private clamp names are direct
imports so warning messages and stack levels remain stable.

Font-token preset construction and scale/profile resolution now live in
`themes/font_token_resolver.py`. The public `FontTokens` class remains owned by
`themes/journal_theme.py`, and the façade passes its live profile collaborators
into the resolver so return-type identity and compatibility behavior remain
stable. The façade is now below the 800-line split signal.

The first `plotting.bridge_renderer` extraction wave moved box/violin
distribution rendering into `plotting/renderers/distribution.py`, heatmap
rendering into `plotting/renderers/heatmap.py`, and bar rendering plus bar
aggregate helpers into `plotting/renderers/bar.py`. Shared renderer ordering,
grouping, and error-bar helpers now live in `plotting/renderers/common.py`.
Line/scatter XY rendering now lives in `plotting/renderers/xy.py`, and
broken-axis XY drawing now lives in `plotting/renderers/broken_axis.py`. The
facet rendering now lives in `plotting/renderers/facet.py`. Overlay,
shared-legend, manuscript layout, and figure-style helpers also live under
`plotting/renderers/`. Multi-panel specifications, draft/manuscript composition,
validation, image-panel embedding, and save/fingerprint orchestration now live
in `plotting/renderers/multipanel.py`; the bridge-renderer facade supplies its
live collaborators so existing save hooks and private imports remain effective.
CSV required-column collection, numeric validity filtering, point payload
normalization, x-value parsing, and point-label option normalization now live
in `plotting/renderers/point_loader.py`. The original private helper names are
direct aliases and `plotting/bridge_renderer.py` is below the 800-line split
signal.
The old private import paths remain available for compatibility.

## Current architecture constraints

1. **No new God Scripts.** New logic should land in the appropriate focused
   module. Existing over-budget modules are debt, not precedent.
2. **One reason to change per module.** Transport, registry/schema, security,
   render orchestration, and domain services should remain separate.
3. **Layering is downward.** MCP transport/server/tools may call lower-level
   services; lower-level services should not import MCP internals.
4. **Public surface is explicit.** `hub_core/mcp/__init__.py` re-exports stable
   MCP names such as `GraphHubMCPServer`, `run_stdio_server`, and
   `list_tool_definitions`.
5. **Adapters are opt-in.** The core must run end-to-end with bespoke adapters
   disabled.

## Tool registry

The MCP tool surface is registry-backed. Tool definitions, schemas, and handler
wiring live under `hub_core/mcp/`, with grouped handlers in
`hub_core/mcp/tools/`. This shared surface feeds `tools/list`,
`figops.describe`, RPC validation, write-tool gating, and generated
references. `docs/tools-v2.md` is the compact default-surface reference,
`docs/tools-compatibility.md` documents the frozen migration surface without
duplicating alias schemas, and `docs/tools.md` remains the full registry
maintenance reference. All three are generated and freshness-tested.

The stdio launcher now defaults to the AI-native `v2` discovery profile. It
exposes at most seven concise tools and uses summary → kind → optional name
progressive disclosure in `figops.describe`. A `compatibility` profile exposes
the frozen pre-v2 contract of 14 canonical tools plus 13 `graphhub.*` aliases.
The handler registry remains a superset so migration does not remove callability;
profile selection only controls discovery. When writes are disabled, mutating
and executing tools are omitted from `tools/list`, and the independent dispatch
guard still rejects remembered canonical or alias names before side effects.

`GraphHubMCPServer` remains a historical embedded-Python class name and selects
the same truthful `compatibility` profile. New launcher and embedded clients
should use `FigOpsMCPServer(surface_profile="v2" | "compatibility")` or the
`GRAPH_HUB_MCP_SURFACE_PROFILE` launcher environment setting. Profile-aware
references can be rendered from the live registry without duplicating alias schemas.

## All-project structure audit (CLI)

The CLI exposes an independent, read-only structure diagnostic for the whole
discovery root:

```bash
python orchestrator.py --audit-structure
python orchestrator.py --audit-structure --audit-structure-format json --scan-depth 2
```

`orchestrator.py` resolves the research root, records the attempt as
`selector_kind: audit_structure`, and delegates to
`hub_core.structure_audit_report.build_structure_audit_report(root_dir,
max_depth=...)`. It selects the module's deterministic Markdown or JSON
renderer for the requested format and writes the result to stdout (Markdown by
default). Attempt provenance remains on stderr.
`--audit-structure-format` is valid only with `--audit-structure`.

This mode is deliberately independent from project selection and execution:
pipeline selectors and mutating/execution options (including `--project`,
`--check-all`, and `--list-projects`) are rejected rather than silently
combined. The audit walks the discovered projects up to `--scan-depth` and
uses the read-only inventory/audit modules; it does not run analysis, plotting,
diagram, or promotion steps and does not modify project files.

The aggregate retains invalid-configuration and execution-boundary-blocked
projects as diagnostic rows instead of silently dropping them. Its report
schema is `figops.project-structure-audit-report.v1`; aggregate and per-project
`proposed_changes` are always empty on this surface.

Selection follows the canonical matrix in
[`docs/project-structure-contract.md`](project-structure-contract.md):
`invalid`, `boundary_blocked`, `skipped`, and `audit_error` rows are report-only;
ambiguous/heuristic `unknowns` and `proposed_mappings` are candidate-only; and
only explicit, reviewer-supplied `approved_mappings` (plus typed config edits)
can form a copy-only plan. A reviewed dry-run returns a deterministic
`plan_digest` and its `FIGOPS-APPLY-<plan_digest>` confirmation token. Apply
requires the identical reviewed inputs and token, and fails closed on stale
identity/configuration, collisions, unresolved dependencies, or token mismatch.
The token proves integrity and exact replay of that plan; it does not prove an
independent human identity, reviewer authority, or attestation, and the current
workflow does not close self-approval. A host-issued `approval_receipt` (or
equivalent immutable reviewed-plan authority) bound to reviewer identity and
the plan digest is a Phase 5 gap, not a current capability.

The emitted structure report is diagnostic output, not a runtime manifest,
durable result, or evidence receipt. It describes current structure findings
for review; it must not be treated as a promoted artifact or copied into a
project's `results/` tree as if it were research output. Runtime job state,
logs, caches, snapshots, and detailed manifests remain under the external
runtime root, while durable results and receipts remain under their declared
project role roots.
Plans, digests, and confirmation tokens are likewise control-plane evidence;
they do not move runtime state into `results/` or turn a diagnostic finding into
a durable research result.

## Why this shape

- **Maintainability**: the MCP monolith has been replaced by smaller modules
  behind a facade, making later changes local and reviewable.
- **Generality**: adapters and registries let different environments, project
  conventions, and plot types slot in without touching the dispatch core.
- **DX**: live registries back `figops.describe`, `figops.doctor`,
  `figops.list_styles`, and generated tool documentation.
