# Graph Hub — Architecture (target)

> Companion to `docs/ROADMAP.md`. Describes the **target** layering the milestones move toward.
> Written 2026-06 while the audit context was fresh; the current code still has the monolithic
> `hub_core/mcp_surface.py` (~4,970 lines) — M1 decomposes it into the layout below.

## Layers and dependency direction

Dependencies point **downward only**. A layer may import from layers below it, never above.

```
graphhub_mcp_server.py                # entrypoint (stdio); --smoke; thin
        │
        ▼
hub_core/mcp/transport.py             # JSON-RPC 2.0: framing, batch, lifecycle, dispatch
        │
        ▼
hub_core/mcp/server.py                # GraphHubMCPServer façade: registry + service wiring
        │
        ├─► hub_core/mcp/tools/*      # one module per tool group; pure handlers
        ├─► hub_core/mcp/resources.py # MCP resources
        ├─► hub_core/mcp/prompts.py   # MCP prompts
        ├─► hub_core/mcp/security.py  # path guards, write gating, env trust
        └─► hub_core/mcp/render_orchestration.py  # worker spawn, snapshot, geometry wiring
                │
                ▼
hub_core/{contracts,rendering,pipeline}/   # domain services (below the MCP layer)
        │
        ▼
hub_core/adapters/*                   # bespoke integrations as leaves (opt-in, generic default)
themes/                               # styling (leaf)
```

- **transport** knows JSON-RPC, not Graph Hub domain logic.
- **server** is a thin façade: it owns the tool **registry** (name → handler + input/output schema)
  and constructs the services; it contains no business logic itself.
- **tools** are small, focused handler modules; they call services, never each other's internals.
- **services** (`contracts`, `rendering`, `pipeline`) are domain logic, independent of MCP.
- **adapters** (GDrive prefetch, Athena, Surfur/ResearchOS conventions) are leaves behind
  interfaces, default to no-op/generic, and are the only place bespoke assumptions live.

## Module-size & boundary rules (enforced in CI — see M1.2)

1. **No God Scripts.** No `hub_core/**.py` exceeds ~800 lines. A file approaching the budget is a
   signal to split along a seam, not to raise the budget.
2. **One reason to change per module.** Transport changes ≠ tool changes ≠ security changes.
3. **Layering is acyclic and downward.** Enforced by an `import-linter` contract (or equivalent):
   `transport → server → {tools, resources, prompts} → {security, render_orchestration} →
   services → adapters/themes`. No upward or sideways-into-internals imports.
4. **Public surface is explicit.** `hub_core/mcp/__init__.py` re-exports the stable names
   (`GraphHubMCPServer`, `run_stdio_server`, `list_tool_definitions`); everything else is internal.
5. **Adapters are opt-in.** The core must run end-to-end with every adapter disabled.

## Tool registry (target)

The inline `_handlers` dict + `list_tool_definitions()` (currently ~325 lines of hand-written
schemas in `mcp_surface.py`) become a registry where each tool declares, in one place:

```python
@register_tool(
    name="graphhub.render_csv_graph",
    input_schema=...,           # JSON Schema (enums from the canonical constants)
    output_schema=...,
    capabilities={"writes": True, "plot_types": PLOT_TYPE_REGISTRY.keys()},
)
def render_csv_graph(server, arguments): ...
```

This single source feeds `tools/list`, the RPC arg validator, the write-tool gate, and the M5
discovery API — removing today's drift between advertised schema and behavior.

## Why this shape

- **Maintainability**: a 4.9k-line file with ~110 methods is the lowest-scoring dimension; small
  modules behind a façade make every later change local and reviewable.
- **Generality**: adapters + registry are what let a fresh user (different env, no GDrive/Athena)
  and new plot types/backends slot in without touching the dispatch core.
- **DX**: the registry's `capabilities` is the source for the discovery API and auto-generated docs.

The MCP **wire contract does not change** during the decomposition (M1) — only the internal
arrangement. Behavioral evolution happens in M2+.
