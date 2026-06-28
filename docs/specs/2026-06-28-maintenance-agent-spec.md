# FigOps Maintenance Agent Spec - 2026-06-28

## Purpose

Guide the next implementation agent through the highest-value maintenance work
identified in the repository review. The goal is not to add broad new features.
The goal is to tighten FigOps' operational reliability, keep documentation
honest, and remove silent-failure paths while preserving the existing public
package surface.

Use this spec together with
`docs/specs/2026-06-28-maintenance-execution-workflow.md`, which defines the
implementation, two-pass review, verification, and gap-audit loop required to
close these findings without omissions.

## Operating Role

Act as a focused maintenance agent for the independent `figops` repository.

Follow the repository protocol:

- Put behavior changes in the appropriate `hub_core/`, `plotting/`, `themes/`,
  or `scripts/` module. Do not grow `orchestrator.py` or create new god scripts.
- Preserve fail-fast behavior. Missing tools, invalid configuration, unsupported
  science models, and dependency mismatches should produce explicit errors.
- Keep public package boundaries intact. The full repo may still contain private
  docs/style packs; built wheel/sdist artifacts must remain clean.
- Prefer small, reviewable PRs. One PR should have one coherent reason to
  change.

## Initial Context Snapshot

The review that produced this spec observed:

- Git working tree was clean before this spec was added.
- Python syntax compilation passed for the main source tree.
- Full tests, MCP smoke, release checks, generated docs freshness, and Ruff could
  not be verified in the local shell because key dev/runtime dependencies were
  missing (`uv`, `pytest`, `pyyaml`, `ruff`).
- Current package metadata reports `figops==0.17.9`.
- The full repository is intentionally not cleared for public release; public
  wheel/sdist artifacts are the intended public distribution surface.

Do not treat the failed local checks as product regressions until reproduced in
a correctly bootstrapped dev environment.

## Agent Execution Protocol

Before editing:

1. Read this spec, `docs/specs/2026-06-28-maintenance-execution-workflow.md`,
   `AGENTS.md`, `docs/ROADMAP.md`, `docs/architecture.md`, and the files
   directly listed under the finding being addressed.
2. Run `git status --short` and note any unrelated user changes. Do not revert
   them.
3. Prefer the smallest PR that satisfies one coherent cluster of findings.
4. For behavior changes, write or update a test first when the target behavior
   is easy to isolate.

While editing:

- Do not change generated docs by hand unless the repo already expects them to
  be committed and the generator cannot run in the current environment. If that
  happens, clearly mark the limitation in handoff.
- Do not move public imports without a compatibility shim and tests.
- Do not add optional dependencies just to make a test easier.
- Do not broaden MCP write access, runtime roots, or data roots.
- Keep Windows behavior in mind: path handling, `PATH` lookup, Unicode console
  output, and drive-root guards need explicit care.

After editing:

1. Run the narrow tests for the modified area.
2. Run `python -m compileall -q orchestrator.py hub_core plotting themes graphhub_mcp_server.py figops_mcp_server.py`.
3. If dependencies are missing, stop claiming verification at that point and
   record the exact missing executable/module.
4. Run `git status --short` and summarize only files touched by this work.

## Decision Rules For Ambiguous Cases

- If a change could be either a bug fix or a broad refactor, treat it as a bug
  fix only when it has a concrete failing behavior and a narrow witness test.
- If a missing dependency prevents validation, do not patch around the dependency
  unless the missing-dependency behavior itself is the bug being fixed.
- If documentation conflicts with code, code and live registries win. Update the
  document to reflect reality instead of changing behavior to satisfy stale
  prose.
- If a function is domain-science-specific and the formula is not documented,
  prefer explicit unsupported behavior over a guessed implementation.
- If a compatibility alias is confusing but still used, document it rather than
  removing it in this maintenance pass.
- If generated docs are stale but the generator cannot run, do not manually
  rewrite large generated sections. Record the blocker and leave the generated
  artifact unchanged unless the PR is specifically about docs freshness and can
  verify the output.

## Failure Mode Matrix

| Failure mode | Expected agent response |
| --- | --- |
| `uv` missing | Improve or rely on explicit missing-tool error; do not create repo-local `.venv`. |
| `pytest` missing | Do not claim tests passed; record missing module/tool. |
| `pyyaml` missing | Treat import/release-check failures as environment blockers, not code regressions. |
| `ruff` missing | Do not claim lint verification; use `python hub_uv.py run ruff check .` only after `uv` is available. |
| Windows console cannot render Unicode | Keep new error messages ASCII-safe unless surrounding file has a strong reason otherwise. |
| Existing unrelated git changes | Leave them untouched and scope summaries to files changed by this task. |
| Full-repo public gate fails on private markers | Expected under current policy; do not sanitize private docs/style packs unless explicitly requested. |
| Generated docs freshness test fails | Regenerate with the documented script if dependencies allow; otherwise report the blocker. |
| Large module looks tempting to split | Create a focused decomposition plan first unless the extraction is tiny and behavior-covered. |
| MCP write tools/root env behavior is nearby | Do not widen access as part of this maintenance work. |

## Current Findings To Address

### F1 - Local runtime bootstrap is not friendly enough

Observed behavior:

- `python hub_uv.py run ...` fails with a raw `FileNotFoundError` when `uv` is
  not installed or not on `PATH`.
- README recommends `hub_uv.py` for source-checkout workflows, so this failure
  path is user-facing.

Target behavior:

- `hub_uv.py` should still fail fast when `uv` is unavailable.
- The error should be explicit and actionable, for example: "`uv` was not found
  on PATH. Install uv or use a Python environment with FigOps dev dependencies."
- Add or update tests around the missing-uv path without requiring `uv` itself.

Likely files:

- `hub_core/uv_runtime.py`
- `tests/test_uv_runtime.py`
- `README.md` or `docs/QA.md` only if command guidance changes.

Acceptance criteria:

- Missing `uv` produces a clear message and non-zero exit.
- Existing uv environment path isolation behavior remains unchanged.
- Tests cover the error path by patching executable lookup or subprocess call.

Edge cases to cover:

- `uv` is missing from `PATH`.
- `uv` exists but exits non-zero.
- Runtime root contains Unicode path segments.
- `UV_PROJECT_ENVIRONMENT` would resolve inside the repo and must still be
  refused.
- The failure message should avoid emoji or non-ASCII-only assumptions because
  Windows terminals may use legacy encodings.

### F2 - Silent placeholder API in ISPD physics

Observed behavior:

- `hub_core/ispd_physics.py::calculate_trap_density()` is a placeholder with
  `pass`, so callers receive `None` silently.

Target behavior:

- Replace the silent return with explicit fail-fast behavior.
- If no validated general formula exists, raise `NotImplementedError` with a
  message that explains the model is project-specific.
- If implementing a formula, require explicit model/prefactor inputs and tests.
  Do not invent a scientific default without provenance.

Likely files:

- `hub_core/ispd_physics.py`
- Add a focused test file or extend an existing physics/domain test.

Acceptance criteria:

- Calling `calculate_trap_density(...)` cannot silently return `None`.
- The raised error explains what the caller must provide or why the operation is
  unsupported.
- No existing plotting path is broken.

Edge cases to cover:

- Scalar and array inputs should both fail explicitly if no model is selected.
- Existing functions `fit_ispd_data()` and `fit_ispd_data_with_offset()` must not
  change their return tuple shape.
- Do not infer a physical formula from `analysis_helpers/general/ispd_analysis.R`
  unless the agent can prove the assumptions and add tests for that model.

### F3 - Top-level package import hides real errors

Observed behavior:

- The repository root `__init__.py` catches all `ImportError` and silently
  skips re-exports.

Target behavior:

- Avoid swallowing unrelated import failures.
- Either remove the broad re-export shim or narrow the exception handling to the
  exact standalone context it was meant to support.
- If compatibility requires best-effort re-export, expose a clear warning or
  avoid declaring names in `__all__` when imports fail.

Likely files:

- `__init__.py`
- Add/adjust a small import behavior test if practical.

Acceptance criteria:

- Real import bugs are not masked as successful package import.
- Existing standalone source-checkout import workflows still work or fail with a
  clear explanation.

Edge cases to cover:

- Missing third-party dependency during import should not look like a successful
  package import.
- A genuine bug inside `hub_core` or `plotting` should propagate.
- If best-effort re-export remains, `__all__` must not advertise names that were
  not actually imported.

### F4 - Scaffold wizard suggests an invalid style target

Observed behavior:

- `hub_core/scaffold.py` prompts for `nature/internal/science/ppt`, but
  `internal` is not a valid `visual_style.target_format`.

Target behavior:

- The prompt should list valid target formats from
  `hub_core.config_parser.ALLOWED_TARGET_FORMATS`, or use a stable curated
  subset that is actually valid.
- If user input is invalid, the wizard should reject it before writing a broken
  config.

Likely files:

- `hub_core/scaffold.py`
- `tests/test_config_parser_*` or a focused scaffold test.

Acceptance criteria:

- Wizard guidance cannot direct a user to an invalid target format.
- Invalid target input fails before producing a misleading project config.

Edge cases to cover:

- User enters uppercase or mixed-case style names.
- User enters whitespace around a valid style.
- User enters `internal`; this should either be rejected or mapped only if a
  documented valid alias exists.
- Non-interactive `scaffold_project()` should keep producing a valid default
  config.

### F5 - Architecture and roadmap docs are stale against live code

Observed behavior:

- `pyproject.toml` reports `0.17.9`, but some architecture/roadmap text still
  says `v0.15.0`.
- The architecture module-size table is stale. `hub_core/data_contract.py` is
  now small after decomposition; current large files include
  `plotting/bridge_renderer.py`, `hub_core/data_contract_semantics.py`,
  `hub_core/config_parser.py`, `hub_core/geometry_diagnostics.py`, and
  `hub_core/mcp/tools/render_csv.py`.

Target behavior:

- Update docs to describe the current code honestly.
- Do not imply CI architecture guards exist unless they are actually enforced.
- Prefer generated or easily reproducible inventory for line-count tables.

Likely files:

- `docs/architecture.md`
- `docs/ROADMAP.md`
- Optional: a small script/test for architecture inventory freshness, but only if
  scoped and low-maintenance.

Acceptance criteria:

- Version baseline wording matches the current release line.
- The large-module debt list matches a fresh line-count inventory.
- The next decomposition target is updated from `data_contract.py` to the true
  current hotspots.

Edge cases to cover:

- Do not update docs to claim Ruff, dependency audit, or architecture guards are
  gating unless CI actually gates them.
- If docs mention line counts, include the command or method used to compute
  them.
- If generated files such as `docs/tools.md` drift, regenerate them with the
  documented script instead of editing by hand.

## Suggested PR Sequence

### PR 1 - Bootstrap and silent-failure hardening

Scope:

- F1 missing-uv error.
- F2 ISPD placeholder fail-fast.
- F4 scaffold target prompt validation if small.

Reason:

These are direct user/runtime reliability fixes with low architectural risk.

Verification:

```bash
python -m compileall -q orchestrator.py hub_core plotting themes graphhub_mcp_server.py figops_mcp_server.py
python -m pytest tests/test_uv_runtime.py -q
python -m pytest <new-or-updated-physics/scaffold-tests> -q
```

If local dev dependencies are missing, first bootstrap with the documented uv
path once `uv` is installed:

```bash
python hub_uv.py run python -m pytest tests/test_uv_runtime.py -q
```

Fallback when `uv` is not available:

- Do not install tools into the repo.
- Use the current Python only for checks that do not need missing dependencies,
  such as `compileall`.
- Leave an explicit handoff note: "Not run: pytest/Ruff/MCP smoke because `uv`
  is unavailable."

### PR 2 - Import hygiene and docs honesty

Scope:

- F3 top-level `__init__.py` import behavior.
- F5 roadmap/architecture refresh.

Reason:

This PR makes the repository easier for future agents to reason about without
changing runtime execution semantics broadly.

Verification:

```bash
python -m compileall -q orchestrator.py hub_core plotting themes graphhub_mcp_server.py figops_mcp_server.py
python -m pytest tests/test_public_package_surface.py tests/test_public_release_check.py -q
python -m pytest tests/test_tool_reference_docs.py tests/test_style_profiles.py tests/test_style_packs.py -q
```

Fallback when package dependencies are missing:

- Do not infer package-surface correctness from import failures caused by missing
  `pyyaml` or `pytest`.
- Record the dependency blocker and leave package/release claims unchanged.

### PR 3 - Large-module decomposition plan only

Scope:

- No behavior change unless a narrow extraction is clearly safe.
- Write or update a focused decomposition plan for:
  - `plotting/bridge_renderer.py`
  - `hub_core/data_contract_semantics.py`
  - `hub_core/config_parser.py`
  - `hub_core/geometry_diagnostics.py`
  - `hub_core/mcp/tools/render_csv.py`

Reason:

The largest remaining debt is real, but risky. Do not mix major extraction with
small reliability fixes.

Acceptance criteria:

- Each proposed split has a target module, public import compatibility strategy,
  and required regression tests.
- No broad refactor starts without a witness test for the behavior being moved.

## Optional Future PRs

Only consider these after PRs 1-3 are complete or explicitly deferred:

- Make Ruff gating in CI if and only if CI has been observed clean and the
  maintainers want lint failures to block merges.
- Add a lightweight architecture inventory script if line-count drift keeps
  recurring. Keep it advisory unless the team explicitly wants a hard budget.
- Split a public source repository from the private development repository.
  This is a product/release decision, not a maintenance cleanup.

## Non-Goals

- Do not make the full repository public.
- Do not remove internal style packs or private docs unless a public-source
  release pass is explicitly requested.
- Do not add new plot types, MCP tools, or domain science defaults as part of
  this maintenance pass.
- Do not turn advisory CI jobs into gating jobs unless the repo is verified clean
  in CI and the change is called out explicitly.
- Do not remove compatibility aliases such as `graphhub` or `graphhub-mcp`
  during this pass.
- Do not normalize all historical `GraphHub` naming in docs as a drive-by
  cleanup. Touch naming only where it affects the current finding.

## Review Pass Requirements

Every PR produced from this spec should include two self-reviews before handoff.

### Review Pass 1 - Implementation Correctness

Check:

- The changed behavior matches the finding's target behavior.
- Tests exercise both success and failure paths where practical.
- The implementation remains fail-fast and does not introduce silent fallbacks.
- Public imports, CLI entry points, and MCP tool names remain compatible unless
  the PR explicitly documents a breaking change.

### Review Pass 2 - Operational Edge Cases

Check:

- Missing dependency/tool behavior is explicit.
- Windows path and encoding behavior has been considered.
- Public package/private repository boundaries are unchanged.
- Documentation does not overclaim verification, CI gates, or public-release
  readiness.
- Handoff includes commands run, commands not run, and why.

If either review pass finds a problem, fix the issue and repeat both passes for
the affected PR. Do not hand off known ambiguous behavior as "probably fine."

## Minimum Handoff Checklist

Before handing work back:

- Report which findings were addressed and which remain.
- Include the exact verification commands run.
- If tests could not run because dependencies are missing, state that clearly
  and include the first missing dependency or tool.
- Confirm `git status --short`.
- Do not claim docs/tool references are fresh unless the generation or freshness
  test was run successfully.
- State whether Review Pass 1 and Review Pass 2 were completed, and summarize
  any issues found during those reviews.
