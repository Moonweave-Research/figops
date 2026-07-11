# Maintenance Decomposition Next Slice - 2026-07-04

## Decision

The next maintenance decomposition slice should target
`hub_core/process_runner.py` command execution helpers only. This is a
behavior-preserving planning decision, not a source movement task.

No source movement is part of this task. No journal style tokens, render output,
MCP tool names, input schema keys, output schema keys, write-tool behavior, or
runtime root security rules may change in this slice.

## Gate Evidence

This plan is gated behind the post-release QA hardening work:

- Journal track fixture qualification passed for basic, crowded-label, and
  dense-legend cases across Nature, Science, ACS, RSC, Elsevier, Wiley, and
  Cell.
- MCP agent-consumability, local operator readiness, diagnostic-to-rubric
  mapping, and publication-claim boundary guards are in place.
- Task 9 pre-edit gate passed with:
  `python hub_uv.py run python -m pytest tests/test_journal_track_fixtures.py tests/test_mcp_agent_consumability.py tests/test_doctor.py tests/test_geometry_rubric_map.py tests/test_claim_boundaries.py -q`
  reporting `40 passed`.
- Current inventory was generated with:
  `python hub_uv.py run python scripts/architecture_inventory.py --format markdown`.

Current over-budget inventory:

| File | Lines |
|---|---:|
| `themes/journal_theme.py` | 1178 |
| `plotting/bridge_renderer.py` | 1088 |
| `hub_core/process_runner.py` | 1086 |
| `hub_core/mcp/tools/render_csv.py` | 991 |
| `hub_core/mcp/render_orchestration.py` | 958 |
| `hub_core/visual_regression.py` | 902 |
| `hub_core/config_parser.py` | 900 |
| `hub_core/geometry_diagnostics.py` | 850 |
| `hub_core/mcp/schemas.py` | 833 |

The 800-line budget remains a split signal, not a hard failure threshold.

## Selected Candidate

### M1 - `hub_core/process_runner.py` command execution extraction

Scope for the future implementation PR:

- Move command execution and temporary environment overlay helpers from
  `hub_core/process_runner.py` into the existing command-helper area.
- Keep `hub_core.process_runner.run_command` importable and monkeypatchable.
- Preserve the current `uv` environment pinning behavior.
- Preserve stderr/stdout logging behavior.
- Preserve fail-fast return behavior for non-zero process exits.
- Preserve sweep and comparison behavior that depends on the module-level
  `run_command` reference.

Exact files for the future implementation slice:

- `hub_core/process_runner.py`
- `hub_core/process_runner_commands.py`
- `tests/test_process_runner_new.py`
- `tests/test_logging.py`
- `docs/architecture.md`

Potential implementation shape:

- Add a focused command execution function to
  `hub_core/process_runner_commands.py`.
- Leave `hub_core.process_runner.run_command` as the compatibility surface.
- Keep `_run_command_env_overlay` either as a compatibility wrapper or a local
  private alias until tests prove no monkeypatch seam depends on it.
- Update `docs/architecture.md` only after the inventory helper output changes.

Witness tests for the future implementation PR:

- `python hub_uv.py run python -m pytest tests/test_process_runner_new.py::TestProcessRunner::test_run_command_pins_uv_environment_outside_repo -q`
- `python hub_uv.py run python -m pytest tests/test_process_runner_new.py::RunSweepRestorationTests -q`
- `python hub_uv.py run python -m pytest tests/test_logging.py::TestLogging::test_process_runner_logs_progress_to_stderr_not_stdout -q`
- `python hub_uv.py run python -m pytest tests/test_architecture_inventory.py -q`

Stop conditions:

- Any visual regression fixture changes.
- Any change to journal style tokens or render summaries.
- Any change to MCP schema keys, handler names, aliases, or write-tool default
  behavior.
- Any loss of `hub_core.process_runner.run_command` monkeypatch compatibility.
- Any inventory doc update without a matching generated inventory command.

## Deferred Candidates

These remain valid backlog items, but they are not the next slice:

| Candidate | Reason to defer |
|---|---|
| `themes/journal_theme.py` | Highest line count, but style-token changes are visually sensitive after journal QA hardening. Plan a separate token-free inventory pass before touching it. |
| `plotting/bridge_renderer.py` | Directly affects rendering paths and visual regressions; only continue after a dedicated visual witness matrix is chosen. |
| `hub_core/mcp/tools/render_csv.py` | MCP render behavior is now guarded by agent-consumability and journal fixtures; defer until the fixture pack has run in CI. |
| `hub_core/mcp/render_orchestration.py` | Runtime/error mapping is broad; split only after render_csv follow-up risk is lower. |
| `hub_core/visual_regression.py` | Useful target, but it should be planned with baseline regeneration policy and CI artifact behavior. |
| `hub_core/config_parser.py` | Config semantics are broad and user-facing; defer until process runner command extraction proves the next maintenance cadence. |
| `hub_core/geometry_diagnostics.py` | Newly tied to the rubric map; defer until the generated mapping guard has accumulated CI signal. |
| `hub_core/mcp/schemas.py` | Schema drift risk is high; only split with `docs/tools.md` and MCP discovery witness tests in the same PR. |

## Backlog

1. Implement M1 command execution extraction with compatibility shims.
2. Add a lightweight CI job or make target for the post-release QA guard set:
   journal fixtures, MCP consumability, doctor readiness, geometry rubric map,
   and claim-boundary guard.
3. Add generated contact-sheet evidence for journal fixtures as an optional CI
   artifact rather than a committed binary.
4. Draft a token-free `themes/journal_theme.py` audit before any style module
   movement.
5. Decide whether `docs/architecture.md` should track the post-0.17.11
   inventory date after M1 lands.

## Follow-up token-free journal audit (2026-07-11)

The journal-theme follow-up selected only `_declutter_text_artists` for
movement into `themes/declutter.py`. The helper owns optional text/marker
overlap correction and has a dedicated visual witness set in
`tests/test_journal_theme_layout.py`. The extraction does not move or modify
`STYLE_PRESETS`, font tokens, compliance floors, output-format decisions,
geometry-diagnostics ordering, or the `save_journal_fig` chokepoint.

A subsequent bounded slice moved only the application of already-resolved
compliance floors into `themes/compliance.py`. The preset dictionaries and
`_journal_compliance_tokens` resolution remain in `themes/journal_theme.py`;
the extracted functions preserve their warning text and stack levels and are
covered by the rcParams, explicit-artist, and diagnostics compliance witnesses.

The final bounded journal slice moved font-token preset construction and
scale/profile resolution into `themes/font_token_resolver.py`. `FontTokens`
remains defined in the façade, which passes its profile functions into the
resolver and therefore preserves return-type identity and compatibility. This
cleared the remaining over-800-line architecture inventory entry.

## Non-Goals

- No source movement in this task.
- No broad refactor of `hub_core/process_runner.py`.
- No changes to plotting output, journal formats, target-format semantics, or
  publication-readiness claims.
- No automatic installation of `uv`, Python, R, or optional dependencies.
