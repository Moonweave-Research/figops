# FigOps Review Remediation Workflow

Source of truth: `docs/specs/2026-06-29-figops-review-remediation-workflow.plan.json`

## Objective

Turn the 2026-06-29 repository review findings into a staged remediation run
that fixes correctness and safety issues before documentation and maintenance
polish.

## Scope

- Repository: `C:/dev/workspace/figops`
- Primary code surfaces: CLI runtime, MCP render/security, data contracts,
  plotting preflight, release/docs.
- Out of scope without approval: dependency installation, package publishing,
  release tagging, secret access, destructive runtime cleanup outside isolated
  test tempdirs.

## Workflow Shape

Pattern: Parallel Fan-Out / Fan-In with adversarial verification.

The run starts with one baseline slice, then proceeds through gated waves:

1. Baseline and scope lock.
2. P1 correctness remediation.
3. P2 safety and runtime remediation.
4. Docs, examples, and policy alignment.
5. Independent adversarial verification.

## Wave 0 - Baseline

Goal: record the real local execution state before edits.

Required receipt: `baseline.receipt.md`

Minimum fields:

- `git_status`
- `available_python_env`
- `blocked_commands`
- `r_runtime_status`
- `initial_test_slice`

Commands to try, without installing dependencies:

```powershell
git status --short --branch
python hub_uv.py --print-env
python hub_uv.py run python orchestrator.py --list-projects
python -m pytest tests/test_runtime_paths.py tests/test_smoke.py -q
```

If `uv`, `pytest`, `yaml`, or `Rscript` is unavailable, record that as
environment evidence rather than fixing it in this wave.

## Wave 1 - P1 Correctness

Goal: make MCP render behavior match FigOps' fail-fast data/style contract.

Slices:

- MCP project render data-contract parity.
- MCP visual preflight target parity.

Expected fixes:

- `figops.render_project_figure` should not render a project whose full data
  contract would fail under the CLI path.
- MCP visual preflight should evaluate supported formats such as `wiley`,
  `cell`, and internal styles as themselves, not as `nature`.

Required tests:

```powershell
python -m pytest tests/test_mcp_rendering.py tests/test_journal_theme_layout.py -q
```

## Wave 2 - P2 Safety And Runtime

Goal: remove high-friction runtime and MCP safety gaps.

Slices:

- Runtime destination symlink safety for MCP job/latest writes.
- `render_csv_multipanel` overwrite behavior parity with other render tools.
- Documented smoke command health.
- `--list-root-only` behavior.
- Stale `graphhub_mcp_launcher.py` path/runtime drift.

Required tests:

```powershell
python -m pytest tests/test_mcp_rendering.py tests/test_mcp_read_only.py tests/test_smoke.py tests/test_uv_runtime.py -q
```

Dependency installation remains human-gated. If `uv` is missing, do not install
it automatically.

## Wave 3 - Docs, Examples, Policy

Goal: make docs describe live behavior and avoid misleading public release
claims.

Slices:

- Reconcile `README.md`, `pyproject.toml`, `CHANGELOG.md`, roadmap, and
  packaging docs around published versus development version.
- Clarify canonical document hierarchy across `AGENTS.md`,
  `Research_Central_Architecture.md`, `task.md`, `docs/ROADMAP.md`, and
  `docs/architecture.md`.
- Align public examples with publication-safe helpers or explicitly mark them as
  simple smoke fixtures.
- Decide and document vector preflight width policy.

Suggested checks:

```powershell
rg -n "0\\.17\\.9|0\\.17\\.10|Current release|GitHub Release|PyPI" README.md CHANGELOG.md pyproject.toml docs
python scripts/check_public_release.py --root .
```

If network verification is needed for PyPI/GitHub latest state, stop for user
approval first.

## Wave 4 - Adversarial Verification

Goal: try to refute every claimed fix against source and tests.

Verifier output: `verification.report.md`

Required sections:

- `confirmed`
- `refuted`
- `unverified`
- `final_commands`
- `residual_risk`

The final report should not treat environment-blocked commands as passing. It
should separate code behavior, local environment readiness, and public release
state.

## Risk Gates

- Installing dependencies: default no.
- Publishing/tagging/uploading release artifacts: default no.
- Deleting runtime directories outside isolated tempdirs: default no.
- Removing CLI/MCP compatibility aliases: default preserve.
- Network checks for latest public package state: default unverified unless
  approved.

## First Runnable Slice

Create `baseline.receipt.md` only. Do not edit implementation files in the first
slice.

Completion check:

```powershell
python -c "from pathlib import Path; p=Path('baseline.receipt.md'); assert p.exists() and all(k in p.read_text() for k in ['git_status','blocked_commands','initial_test_slice'])"
```

After this receipt exists, start Wave 1 with the P1 MCP correctness fixes.
