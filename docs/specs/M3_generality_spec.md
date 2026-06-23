# M3 — Generality / decoupling — implementer spec

> Goal (`docs/ROADMAP.md`): a fresh user, in a different environment and domain, can run Graph Hub
> without the bespoke assumptions. Biggest lever for the "shareable lab tool" north star
> (generality 3→7). **Depends on M1** (decomposition) — specified at interface/contract level so it
> doesn't go stale; firm up exact file refs against `hub_core/mcp/` + `hub_core/adapters/` when M1
> has landed.

## M3.1 — Adapters layer — L

**Problem:** bespoke integrations are baked into the core, so a clean checkout in another
environment can't run: GDrive prefetch (`ensure_local_files`), the Athena bridge
(`hub_core/athena_bridge.py`, `orchestrator.py` health/draft hooks), and workspace naming
conventions (e.g. project-specific style aliases, `.worktrees`/`ResearchOS` discovery assumptions).

**Design:** introduce `hub_core/adapters/` with small interfaces and **generic defaults**:

```python
# hub_core/adapters/prefetch.py
class Prefetcher(Protocol):
    def ensure_local(self, paths: list[str]) -> None: ...
class NoopPrefetcher:        # default
    def ensure_local(self, paths): return None
class GDrivePrefetcher:      # opt-in (current ensure_local_files behavior)
    ...

# hub_core/adapters/athena.py    -> AthenaBridge protocol; NullAthena default (no health/draft hooks)
# hub_core/adapters/conventions.py -> naming/discovery policy; GenericConventions default,
#                                      Project conventions opt-in (worktrees/ResearchOS/default style)
```

- Selection via config (`environment.adapters: {prefetch: gdrive|none, athena: on|off,
  conventions: workspace|generic}`) and/or env, **defaulting to none/generic**.
- The orchestrator and MCP render path call adapters through their interfaces only.
- Athena timeout handling from PR #55 stays; the bridge becomes a `NullAthena` no-op by default.

**Acceptance:** with all adapters at their defaults and **zero bespoke env vars**, a clean checkout
can `scaffold → render` a figure (verified by a CI smoke test). GDrive/Athena/workspace conventions are opt-in and
covered by their own tests. No project-specific style alias, `ResearchOS`, or `ensure_local_files` reference remains
outside `adapters/` + the style packs.

## M3.2 — Plot-type registry & render-backend interface — M

**Problem:** plot types are a hardcoded set (`SUPPORTED_RENDER_PLOT_TYPES = {bar, line, scatter, xy,
heatmap}` in the MCP layer) and the renderer (`plotting/bridge_renderer.py`) dispatches by string.
New types require editing the dispatch core, and the set isn't discoverable via the API (M5 gap).

**Design:** a registry in `hub_core/rendering/`:

```python
@dataclass
class PlotType:
    name: str
    render: Callable[[Axes, list[Point], BridgeFigureSpec], None]
    arg_schema: dict      # JSON Schema fragment for this type's extra args
    capabilities: dict    # supports_series, supports_yerr, supports_broken_axis, ...
PLOT_TYPES: dict[str, PlotType]   # registered at import; bar/line/scatter/xy/heatmap migrated in
def render_plot(ax, points, spec): PLOT_TYPES[spec.plot_type].render(ax, points, spec)
```

- Migrate the existing `_render_*` functions in `bridge_renderer.py` into registry entries
  (behavior-preserving). The MCP `render_csv_graph`/`render_project_figure` enums + the RPC validator
  read `PLOT_TYPES.keys()` (no more drift).
- Keep matplotlib as the **default backend** behind a thin `RenderBackend` seam (full pluggable-SPI
  is M6 only — do not over-build now; see ROADMAP decision points).

**Acceptance:** adding a plot type = registering one `PlotType` (no dispatch-core edit); the MCP enum
and discovery API reflect it automatically; existing render tests unchanged.

## M3.3 — Config schema versioning & migration — S

**Problem:** `project_config.yaml` evolves; there's a `CURRENT_CONFIG_SCHEMA_VERSION` in
`config_parser.py` but no migration path for older configs.

**Design:** explicit `schema_version` handling with an ordered migration chain
(`migrate_config(cfg) -> cfg'`), applied on load; clear error if a config is newer than the runtime
supports. **Acceptance:** an old-version config loads via migration (or fails with a precise
upgrade message); a round-trip test per supported version.

## M3.4 — Root/runtime configuration & env trust finalization — S

**Problem:** `research_root`/runtime resolution still leans on bespoke env assumptions; the env trust
model was documented in PR #55 (`AGENTS.md`) but not fully closed.

**Design:** make `research_root` + runtime root fully config-driven (constructor/CLI/config),
with env as one (validated) source — building on the `GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS` validation
from PR #55. Finalize the trust-model doc to cover the adapter env vars introduced in M3.1.
**Acceptance:** the server runs with explicit config and no special env; the trust-model doc lists
every env var that affects roots/adapters/security.

## Definition of done (M3)

- Clean-checkout smoke test: scaffold → render with **zero** bespoke env vars / adapters, in CI.
- Adapters opt-in with generic defaults; plot types register without touching dispatch; config
  migrates across versions. Generality lifted from "bespoke" toward "portable".
