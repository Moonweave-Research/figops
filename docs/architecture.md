# FigOps - Architecture

> Companion to `docs/ROADMAP.md`. Describes the current v0.20.0 release-candidate
> architecture after the v0.19.0 release, including the AI-native v2 agent
> surface and evidence-first render/audit path.

## Layers and dependency direction

Dependencies point **downward only**. A layer may import from layers below it,
never above.

```
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
hub_core/project_config_reader.py     # verified, bounded config discovery/read
hub_core/evidence_*.py                # evidence envelope and semantic validation
hub_core/artifact_*.py                # artifact integrity and explicit-policy audit
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

Current files over the approximate 800-line budget, measured on 2026-07-15 with
the architecture inventory helper:

```bash
python hub_uv.py run python scripts/architecture_inventory.py --format markdown
```

<!-- architecture-inventory:start -->
| File | Lines |
|---|---:|
<!-- architecture-inventory:end -->

No Python module in the tracked architecture roots (`hub_core`, `plotting`, and
`themes`) currently exceeds the 800-line split signal. Overlay
normalization now lives in `plotting/renderers/annotation_normalization.py`,
while the public overlay façade and compatibility imports remain stable.

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

The process-runner façade now delegates non-expanded visual artifacts and
per-input `expand: each` visual execution to focused helper modules. It passes
its cache, command, path, and output-verification collaborators at invocation
time so existing `hub_core.process_runner` monkeypatch paths remain effective.

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
limits live in `hub_core/mcp/preview_artifacts.py`; conversion work lives in
`preview_worker.py`. Raster and PDF-first-page previews are bounded to 5 seconds,
8 megapixels, 256 MiB worker memory, a 2,048-pixel longest edge, and 2 MiB raw
output. SVG returns typed unavailable until a renderer passes the required
Windows safety smoke; source vector bytes are never substituted for a preview.

The primary touched façades remain below the 800-line split signal through
focused modules in the 2026-07-15 working-tree inventory:
`evidence_contract.py` is 680 lines after extracting the 204-line
`evidence_artifact_section.py`; `schemas.py` is 750;
`geometry_diagnostics.py` 782; `preview_artifacts.py` 781;
`render_orchestration.py` 769; and `render_csv.py` 776. Overlay normalization
now lives in the 230-line `annotation_normalization.py`, leaving
`overlays.py` at 597 lines with compatibility exports intact. No Python module
in the tracked architecture roots exceeds the 800-line split signal.

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

## Why this shape

- **Maintainability**: the MCP monolith has been replaced by smaller modules
  behind a facade, making later changes local and reviewable.
- **Generality**: adapters and registries let different environments, project
  conventions, and plot types slot in without touching the dispatch core.
- **DX**: live registries back `figops.describe`, `figops.doctor`,
  `figops.list_styles`, and generated tool documentation.
