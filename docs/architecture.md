# FigOps - Architecture

> Companion to `docs/ROADMAP.md`. Describes the current v0.17.9 architecture
> after the 0.5.0 MCP decomposition and later release work.

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
hub_core/mcp/server.py                # GraphHubMCPServer facade: registry + service wiring
        |
        +-- hub_core/mcp/tools/*      # handler groups backed by live schemas
        +-- hub_core/mcp/resources.py # MCP resources
        +-- hub_core/mcp/prompts.py   # MCP prompts
        +-- hub_core/mcp/security.py  # path guards, write gating, env trust
        +-- hub_core/mcp/config.py    # trusted root/runtime/server config
        +-- hub_core/mcp/errors.py    # JSON-RPC / tool error envelopes
        +-- hub_core/mcp/schemas.py   # shared tool schema helpers
        +-- hub_core/mcp/render_*     # render orchestration, geometry, error mapping
                |
                v
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

The architecture budget is aspirational, not currently CI-enforced. There is no
module-size or import-linter guard in `.github/workflows/ci.yml` as of v0.17.9.
Future changes should still treat about 800 lines per core module as a split
signal, but the current tree has known over-budget files.

Current files over the approximate 800-line budget, measured on 2026-06-28 with
the architecture inventory helper:

```bash
python hub_uv.py run python scripts/architecture_inventory.py --format markdown
```

<!-- architecture-inventory:start -->
| File | Lines |
|---|---:|
| `hub_core/data_contract_semantics.py` | 1861 |
| `hub_core/config_parser.py` | 1858 |
| `plotting/bridge_renderer.py` | 1833 |
| `hub_core/geometry_diagnostics.py` | 1828 |
| `hub_core/mcp/tools/render_csv.py` | 1670 |
| `themes/journal_theme.py` | 1390 |
| `hub_core/mcp/schemas.py` | 1151 |
| `hub_core/process_runner.py` | 1137 |
| `hub_core/mcp/render_orchestration.py` | 938 |
| `hub_core/visual_regression.py` | 902 |
<!-- architecture-inventory:end -->

`hub_core/data_contract_semantics.py`, `hub_core/config_parser.py`, and
`plotting/bridge_renderer.py` are now the clearest candidates for future
behavior-preserving decomposition. `hub_core/data_contract.py` has already been
reduced to a compatibility/orchestration surface after IO and semantic helpers
were extracted.

The first `plotting.bridge_renderer` extraction wave moved box/violin
distribution rendering into `plotting/renderers/distribution.py`, heatmap
rendering into `plotting/renderers/heatmap.py`, and bar rendering plus bar
aggregate helpers into `plotting/renderers/bar.py`. Shared renderer ordering,
grouping, and error-bar helpers now live in `plotting/renderers/common.py`.
Line/scatter XY rendering now lives in `plotting/renderers/xy.py`, and
broken-axis XY drawing now lives in `plotting/renderers/broken_axis.py`. The
facet rendering now lives in `plotting/renderers/facet.py`. The old private
import paths remain available for compatibility.

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
`docs/tools.md`.

## Why this shape

- **Maintainability**: the MCP monolith has been replaced by smaller modules
  behind a facade, making later changes local and reviewable.
- **Generality**: adapters and registries let different environments, project
  conventions, and plot types slot in without touching the dispatch core.
- **DX**: live registries back `figops.describe`, `figops.doctor`,
  `figops.list_styles`, and generated tool documentation.
