# Graph Hub — Upgrade Roadmap & Spec

> North star: **a shareable lab tool** — keep the strong reproducibility vision, harden the
> fundamentals, pay down maintainability debt first, decouple the bespoke conventions, and add
> the docs/DX so a new lab member or collaborator can run it. Not a full OSS product yet, but
> every milestone keeps that path open.
>
> Sequencing decision (2026-06-18): **maintainability first**, then fundamentals → generality →
> features → DX. Each later milestone is easier to land on a clean, decomposed base.
>
> Status baseline: the 2026-06 adversarial-audit remediation (P0–P3 + R contract / env trust /
> dep bump) is fully merged to `main` across 16 PRs. This roadmap is what comes next.

## How to read this

- Milestones **M1…M6**, executed roughly in order; tracks inside a milestone can parallelize.
- **M1 is specified in the most detail** (it's next). Later milestones are specified at intent +
  workstream level and will be hardened into per-PR specs when approached (write a focused
  `docs/<milestone>_spec.md` like `audit_remaining_handoff_spec.md` at that point).
- Each workstream: concrete change + file refs + acceptance. Effort is rough (S/M/L), risk is
  the chance of breaking existing behavior.

## Execution methodology (applies to every milestone)

- **TDD**: every behavioral change needs a runtime-witness test that fails on the pre-change code.
- **One PR per coherent change**, branched off `main`, base `main`; disjoint files where possible.
- **Multi-agent workflow + adversarial review-until-clean** is the proven engine for substantive
  changes (find → verify → fix loop, Opus for reasoning / Sonnet for mechanical + test review).
  Treat the workflow's `clean` flag as advisory; the authoritative gate is main-loop verification
  (read the changed code + full `uv run python -m pytest` + ruff on changed files).
- **CI** (`.github/workflows/ci.yml`): `Test` gating; `Ruff`/`Dependency audit` advisory until M1
  flips ruff to gating. Run everything via `uv run` (a hook blocks bare `python`).
- **Sandbox caveat**: editing `pyproject.toml` deps in the dev sandbox can lock the session (uv
  cache corrupts on fresh-package install). Do dependency work in a clean env / via CI.

## Current-state scorecard (2026-06, post-audit)

| Dimension | Score | Read |
|---|---|---|
| Vision & feature breadth | 9/10 | Data contracts + provenance + regression + geometry QA + journal themes — rare depth. |
| Fundamentals & security | 8/10 | Hardened by the audit; transport, trust boundary, regression integrity solid. |
| Code maintainability | 5/10 | `mcp_surface.py` ~4.8k-line God script; ~190 ruff findings; uneven module boundaries. |
| Generality / portability | 3/10 | Bespoke conventions (Surfur/ResearchOS, GDrive prefetch, Athena bridge) baked in. |
| DX / docs / discoverability | 4/10 | Improving (enums, sanitized errors), but no quickstart, thin plot-type discovery. |

Roadmap goal: maintainability 5→8, generality 3→7, DX 4→8, while holding vision/fundamentals ≥8.

---

## North-star target architecture

```
graphhub_mcp_server.py        # thin entrypoint (stdio)
hub_core/
  mcp/                        # NEW subpackage — was mcp_surface.py (~4.8k lines)
    transport.py              # JSON-RPC framing, dispatch, batch, lifecycle (run_stdio_server)
    server.py                 # GraphHubMCPServer façade: wires services + tool registry
    security.py               # path guards, write gating, env trust (allowed roots)
    tools/                     # one module per tool group
      read_tools.py           #   health, list_styles, list_projects, inspect/validate
      render_tools.py         #   render_csv_graph, render_project_figure
      project_tools.py        #   scaffold, normalize
      batch_tools.py          #   batch_check, collect_artifacts
    render_orchestration.py   # worker spawning, snapshotting, geometry-diagnostics wiring
    resources.py / prompts.py # MCP resources + prompts
  contracts/                  # data_contract split (load / schema / semantic / calculation)
  rendering/                  # bridge_renderer + a plot-type REGISTRY (pluggable engines)
  pipeline/                   # orchestrator, process_runner, cache, provenance, regression
  adapters/                   # NEW — bespoke integrations behind interfaces:
    prefetch.py               #   GDrive ensure_local_files (no-op default)
    athena.py                 #   Athena bridge (optional)
    conventions.py            #   Surfur/ResearchOS naming (config-driven, with generic default)
themes/                       # journal styles, palettes, font tokens
docs/                         # quickstart, tool reference, contributor guide, this roadmap
```

Principles: a thin transport/dispatch layer; tools as small modules behind a registry; bespoke
behavior behind `adapters/` with generic defaults; a plot-type registry so capabilities are
discoverable and extensible; every public function typed; no module a "God Script".

---

## M1 — Maintainability & architecture (NEXT, specified)

**Goal:** decompose the God script, establish enforceable module boundaries, clear lint debt,
raise coverage on the security/protocol core — so M2–M6 land on a clean base. Behavior-preserving.

**Why now:** maintainability is the lowest score (5/10) and the multiplier on everything else.
`mcp_surface.py` violates the repo's own AGENTS.md rule ("No God Scripts").

### M1.1 — Decompose `hub_core/mcp_surface.py` into `hub_core/mcp/` (L, medium risk)
- Extract, **behavior-preserving**, into the `mcp/` layout above. Move in slices, each its own PR,
  re-exporting from `mcp_surface.py` only transiently within a PR and removing the shim by end of
  the slice (no lingering back-compat per repo rules). Suggested slice order:
  1. `transport.py` — `run_stdio_server`, `_read_stdio_message`, `_dispatch_json_rpc`,
     `_handle_json_rpc`, framing, batch, lifecycle, envelope validation.
  2. `security.py` — `_resolve_under_root`, `_resolve_allowed_data_path`, `_allowed_data_roots`,
     `_broad_data_root_warning`, write-tool gating, `_scan_root`, `_resolve_project_path`.
  3. `render_orchestration.py` — worker spawn, `redirect_stdout` wrapping, snapshot copy,
     geometry-diagnostics env, render failure artifacts.
  4. `tools/*.py` — the 11 tool handlers grouped as in the target arch; a tool registry
     (name → handler + schema) replaces the inline `_handlers` dict + `list_tool_definitions`.
  5. `resources.py` / `prompts.py`.
  6. `server.py` — `GraphHubMCPServer` becomes a thin façade wiring services + registry.
- **Safety net:** the existing ~625 tests (esp. `test_mcp_*`) are the regression oracle; run the
  full suite after each slice. No behavioral change is allowed in this milestone — diffs are
  moves + re-wiring only.
- **Acceptance:** no module > ~800 lines; full suite green unchanged; public import surface
  (`from hub_core.mcp_surface import GraphHubMCPServer, run_stdio_server, list_tool_definitions`)
  preserved via `hub_core/mcp/__init__.py` re-exports; `graphhub_mcp_server.py` still works.

### M1.2 — Enforce module boundaries (S)
- Add an architecture doc (`docs/architecture.md`) describing the layers + dependency direction
  (transport → server → tools → services; adapters are leaves).
- Add a CI guard: a module-size budget check (fail if any `hub_core/**.py` exceeds N lines) and/or
  an `import-linter` contract pinning the layering. Wire into the `Test`/a new `Arch` job.
- **Acceptance:** the guard runs in CI and passes; adding a God script fails CI.

### M1.3 — Pay down lint debt, flip ruff to gating (M)
- Resolve the ~190 pre-existing ruff findings (mostly E501/F401/F841/I). Mechanical; do per-package
  PRs so review is easy. Add type hints on public signatures (the codebase is partly typed; target
  `hub_core/mcp/`, `contracts/`, `rendering/` public APIs first; prefer `str | None`).
- Once clean, change `ci.yml` `Ruff` job from advisory (`continue-on-error: true`) to **gating**.
- **Acceptance:** `uv run ruff check .` clean; CI ruff job gating; no new findings can merge.

### M1.4 — Coverage discipline on the core (M)
- Measure coverage (`pytest --cov`) on the security/JSON-RPC/path-guard layers; fill gaps
  (path-guard rejections, write gating, batch/lifecycle, Content-Length bound — several were
  untested before the audit). Consider a coverage floor in CI for `hub_core/mcp/`.
- **Acceptance:** documented coverage % for the core; gaps in the trust-boundary code closed.

---

## M2 — Fundamentals deepening (specified at intent level)

**Goal:** finish the robustness tail the audit identified but deferred, plus real observability —
now safe to do on the decomposed base.

- **M2.1 Structured logging** (M): full `print()` → `logging` migration (process_runner ~74,
  orchestrator ~81). Leveled, filterable; the stdio server path stays fd1-pure (P3-2 already
  guards the wire). A `--verbose`/`GRAPH_HUB_LOG_LEVEL` knob. This is the rest of the
  "print→logging" item (the wire risk is already handled).
- **M2.2 Concurrency hardening** (M): the multiprocessing `Queue(maxsize=1)` large-payload deadlock
  (`mcp/render_orchestration.py`, was `mcp_surface.py:425/437/2114/3744`) — switch to a pipe/file
  IPC or chunked result, and report "result too big" instead of a misleading timeout. Document /
  remove the `run_command` monkeypatch re-entrancy hazard (`process_runner.py:755/919`).
- **M2.3 Verdict-pollution & edge robustness** (S): optional-dep (`[io]` pyarrow/tables, pint)
  absence should report "feature unavailable", not flip `quality_passed` (`data_contract.py:620`).
  Fix the `_style_diff` legend(Line2D diameter) vs scatter(√area) marker-scale mismatch surfaced in
  the P1a review (`geometry_diagnostics.py` ~949/988).
- **M2.4 Release-gate i18n** (S): `check_public_release.py:52` `errors="ignore"` + NFC normalization
  so an NFD Korean private marker can't pass the gate; scan provenance fingerprints in binaries.
- **M2.5 Error taxonomy** (S): unify error envelopes/codes across tools; document them.
- **Acceptance:** each item has a witness test; logging is the only stdout on the MCP wire;
  no env-dependent verdict flips.

---

## M3 — Generality / decoupling (toward shareable)

**Goal:** a fresh user in a different environment/domain can run Graph Hub without the bespoke
assumptions. This is the biggest lever for the "shareable lab tool" north star (generality 3→7).

- **M3.1 Adapters layer** (L): move `adapters/prefetch.py` (GDrive `ensure_local_files` → no-op
  default), `adapters/athena.py` (optional), `adapters/conventions.py` (Surfur/ResearchOS naming →
  config-driven with a generic default) behind interfaces. The core must run with all adapters off.
- **M3.2 Plot-type registry & render-backend interface** (M): replace the hardcoded
  `SUPPORTED_RENDER_PLOT_TYPES = {bar,line,scatter,xy,heatmap}` with a registry (name → renderer +
  schema + capabilities). Enables M4 features and fixes plot-type discoverability (M5). Keep
  matplotlib as the default backend behind a clean interface.
- **M3.3 Config schema versioning** (S): explicit `schema_version` + a migration path; validate &
  migrate old `project_config.yaml`. (`config_parser.py` already has `CURRENT_CONFIG_SCHEMA_VERSION`.)
- **M3.4 Root/runtime configuration** (S): make `research_root`/runtime fully config-driven without
  bespoke env assumptions; finalize the env trust model doc started in #64.
- **Acceptance:** a clean-checkout smoke test scaffolds → renders a figure with **zero** bespoke env
  vars / adapters; adapters are opt-in; new plot types register without touching the dispatch core.

---

## M4 — Feature breadth (on the registry)

**Goal:** the user-facing capabilities that were limited or refused. Each new plot type ships via
the M3.2 registry.

- **M4.1 Multi-series broken-axis** (M): implement the case P1c currently refuses (series split +
  error bars + legend + overlays on `ax_top`/`ax_bot`); remove the guard.
- **M4.2 New plot types / layouts** (M): faceting / small-multiples, box/violin parity in the bridge
  renderer, more statistical overlays (CI bands, fits), grouped-bar replicate aggregation.
- **M4.3 Domain analysis helpers** (M): materials/polymer-specific R/Python helpers as first-class,
  documented analysis steps (build on `analysis_helpers/`), behind the data-contract framework.
- **M4.4 Richer data contracts** (S): more semantic checks; surface them in `list_styles`/a
  capabilities resource.
- **Acceptance:** each feature has tests + a docs example; capabilities are discoverable via the API.

---

## M5 — DX, docs, shareability

**Goal:** a new lab member or collaborator can go from clone → first figure in minutes; the API is
self-describing for both humans and LLM agents (DX 4→8).

- **M5.1 Capabilities/discovery API** (S): a `graphhub.describe` (or enriched `list_styles`) that
  returns plot types + per-type argument schemas + examples, from the M3.2 registry — closes the
  current plot-type discovery gap.
- **M5.2 Docs set** (M): quickstart, auto-generated tool reference (from inputSchemas),
  worked examples, contributor guide, the env trust model, "getting started for a new lab member".
- **M5.3 Self-check** (S): a `graphhub doctor` / `--smoke` that validates the environment (R,
  optional deps, write gating, roots) and reports readiness — the friendly front door.
- **M5.4 Release discipline** (S): semver, CHANGELOG, tagged releases — prerequisites for sharing.
- **Acceptance:** a documented clone→figure path verified in CI; `describe` lists every capability;
  CHANGELOG + tags exist.

---

## M6 — (Optional, deferred) OSS-product path

Only if the north star expands later: packaging/distribution (PyPI), plugin API for third-party
plot backends/adapters, multi-project/multi-user concerns, broader transport (HTTP/SSE MCP),
security review for untrusted callers. Explicitly **out of scope** for the shareable-lab-tool goal;
listed so M1–M5 don't foreclose it (the adapters layer + registry + docs already pave the way).

---

## Decision points (resolve when reached, not now)

- **M1.1 slice granularity**: one big decomposition PR vs. 6 thin slices. Recommend thin slices
  (each green, easy review) given the file's size and central role.
- **M1.3 ruff scope**: fix-all-then-gate vs. gate-new-only (ratchet). Recommend fix-all (the count
  is ~190, mostly mechanical) so the gate is unconditional.
- **M3.2 backend abstraction depth**: thin registry vs. full pluggable-engine SPI. Recommend thin
  registry now (matplotlib only), SPI only if M6 is pursued.
- **M4 feature priority**: driven by your actual paper/figure needs — pull from `task.md` when you
  start M4.

## Dependencies (what blocks what)

- M2/M3/M4 all benefit from **M1.1** (decomposition) landing first; M1 is the gate.
- **M3.2 registry** is a prerequisite for **M4** (new plot types) and **M5.1** (discovery).
- **M3.1 adapters** is the prerequisite for the "clone→figure with zero bespoke env" acceptance.

## Tracking

- Keep `task.md` as the live execution backlog; this file is the stable plan.
- Per milestone, write a focused `docs/<milestone>_spec.md` when you start it (the
  `audit_remaining_handoff_spec.md` is the template), then drive it with the workflow engine.
