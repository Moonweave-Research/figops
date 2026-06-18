# M2 — Fundamentals deepening — implementer spec

> Goal (`docs/ROADMAP.md`): finish the robustness tail the 2026-06 audit flagged but deferred, plus
> real observability — now safe on the M1-decomposed base. Each item is a separate PR with a
> runtime-witness test. File refs are current (pre-M1); where a symbol moves in M1, the **post-M1
> home** is noted.

## M2.1 — Structured logging (the rest of print→logging) — M

**Problem:** ~74 `print()` in `hub_core/process_runner.py`, ~81 in `orchestrator.py`, plus scattered
`print` in `data_contract.py`/`config_parser.py`/`cache_manager.py`. No leveled/filterable logging.
The stdio wire is already protected (P3-2 wraps handler dispatch in `redirect_stdout(sys.stderr)`),
so this is the **observability** half, not a wire-safety fix.

**Change:**
- Introduce a `hub_core/logging.py` (or `hub_core/_log.py`) with `get_logger(__name__)` and a single
  `configure_logging(level)` honoring `GRAPH_HUB_LOG_LEVEL` (default WARNING) and `--verbose` on the
  orchestrator CLI. Format to **stderr** (never stdout).
- Convert `print()` calls to `logger.{debug,info,warning,error}` by intent. The user-facing CLI
  (`orchestrator.py`, `ui_utils`) may keep `rich`-based human output, but it must go to stderr or be
  clearly the CLI presentation layer — never the MCP path.
- Keep the `❌`/`⚠️` semantics as `error`/`warning` levels.

**Acceptance:** `GRAPH_HUB_LOG_LEVEL=DEBUG` surfaces diagnostics; default is quiet; an integration
test asserts the MCP stdio path still emits only JSON-RPC on fd1 (extends the P3-2 test). No `print(`
remains in `hub_core/` non-CLI modules (grep gate optional).

## M2.2 — Concurrency hardening — M

**Problem A — large-payload deadlock.** `_render_bridge_figure_worker` / `_batch_discovery_worker`
(currently `mcp_surface.py:432/444`; **post-M1:** `hub_core/mcp/render_orchestration.py`) `put()` into a
`multiprocessing.Queue(maxsize=1)` while the parent does `get(timeout=...)` then `terminate()`. A
result larger than the OS pipe buffer (~64KB) blocks the child on `put`, the parent times out and
kills it, and the failure is reported as a **timeout**, not "result too big". Hits real research
roots with many projects.

**Change:** switch the result channel to a `Pipe`/file-based transfer or chunk the payload; detect
oversize and report a distinct "result too large" error. Confirm the start method (py3.12/darwin =
`spawn`) re-imports the module cleanly (no import-time side effects differ parent vs child).
**Test:** a synthetic 100k-entry discovery result returns (or errors clearly) instead of hanging.

**Problem B — monkeypatch re-entrancy.** `process_runner.py` sweep/comparison (~L755-761, ~L919-925)
reassign the module-global `run_command` and restore in `finally`. Not re-entrant / not thread-safe.

**Change:** document that the MCP server is strictly sequential (read-handle-write loop) and must not
be made concurrent without removing this monkeypatch; or refactor to pass the runner explicitly
instead of mutating the global. **Test:** nested sweep-in-comparison restores the global correctly.

## M2.3 — Verdict-pollution & a residual marker bug — S

**Optional-dep verdict pollution.** Missing `[io]` (pyarrow/tables) or `pint` flips
`quality_passed=False` (`data_contract.py` ~L620) instead of reporting "feature unavailable". An
env-dependent verdict violates "env mismatch → fail-fast, not silent fail".
**Change:** when an optional dep is absent, mark the affected check `skipped`/`unavailable` with a
clear reason and do not flip `quality_passed`. **Test:** validator in a venv without `[io]`/pint
reports unavailability, not failure.

**`_style_diff` marker-scale mismatch** (surfaced in the P1a review, deferred). In
`geometry_diagnostics.py` (~L949 `_collection_marker_style` vs ~L988 `_style_diff`), a scatter
PathCollection's marker "size" is `sqrt(area)` while a legend Line2D's is `get_markersize()` (a
diameter) — compared with a fixed 0.5pt threshold across **different scales**.
**Change:** normalize both sides to the same scale (convert collection `s` to diameter via
`2*sqrt(s/pi)`, matching the footprint convention fixed in PR #51) before diffing. **Test:** a legend
vs data marker of equal visual size no longer reports a spurious style diff.

## M2.4 — Release-gate i18n / completeness — S

**Problem:** `scripts/check_public_release.py:52` reads with `errors="ignore"` (silently drops
undecodable bytes) and does plain substring matching of Korean private markers with **no Unicode
normalization** — an NFD-stored marker (common on macOS) passes the gate. Binary suffixes are
skipped entirely, so a marker embedded in a committed PNG/PDF (incl. provenance fingerprints) is
never scanned.

**Change:** NFC-normalize file text before matching; stop using `errors="ignore"` on
security-relevant scans (surface decode failures); scan provenance-fingerprint payloads in binaries
for markers. **Test:** an NFD-form Korean marker is caught; a marker inside a committed PDF is caught.

## M2.5 — Error taxonomy unification — S

**Problem:** error envelopes/codes are consistent at the JSON-RPC layer but ad-hoc inside handlers
(`status="error"` envelopes, raised `ValueError`s caught and stringified). No single documented map.

**Change:** define and document an error taxonomy (validation vs not-found vs internal vs disabled)
and apply it uniformly across tool handlers; align with the JSON-RPC codes already in transport.
Document in `docs/architecture.md` or a `docs/mcp_errors.md`. **Test:** representative errors per
category return the documented shape/code.

## Definition of done (M2)

- Each sub-item: a PR + runtime-witness test; full suite green; ruff-clean (gating after M1.3).
- No `print()` on the MCP path; no env-dependent quality verdict flips; release gate catches NFD
  markers; concurrency hazards documented or removed.
