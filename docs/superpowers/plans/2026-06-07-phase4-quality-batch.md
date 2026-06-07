# Phase 4 Quality Gate and Batch Operation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Phase 4 MCP quality status, optional baseline comparison, and bounded batch checking without mutating source projects.

**Architecture:** Keep MCP as a thin surface over Graph Hub core contracts. Rendering still uses `plotting.bridge_renderer` and `figure_preflight`; batch checking composes `ProjectDiscoveryService`, existing inspect/validate helpers, and writes only a runtime manifest when explicitly requested.

**Tech Stack:** Python 3.12 through `python3 hub_uv.py run`, standard library JSON/path/hash utilities, existing `hub_core.mcp_surface`, and unittest/pytest.

---

## Files

- Modify: `hub_core/mcp_surface.py`
  - Add `graphhub.batch_check` tool definition and handler.
  - Add `artifact_status` and `baseline_comparison` fields to render and collect results.
  - Add bounded batch runtime manifest writing under `runtime_root/mcp_jobs/<batch_id>/batch_manifest.json`.
- Modify: `docs/02-design/graph_hub_mcp_surface/05_phase4_quality_gate_batch.md`
  - Record the Phase 4 v1 scope: quality status, optional hash baseline comparison, bounded batch check.
- Create: `tests/test_mcp_batch_quality.py`
  - Cover quality status, baseline comparison, bounded batch filtering, runtime logging, resume, and timeout behavior.

---

### Task 1: Quality Status and Baseline Comparison

- [ ] **Step 1: Write failing render/collect tests**

Add tests in `tests/test_mcp_batch_quality.py`:

```python
def test_render_csv_graph_reports_preflight_passed_artifact_status(self):
    # Render a fixture CSV and assert artifact_status == "preflight_passed".

def test_collect_artifacts_reports_manual_review_for_preflight_warning(self):
    # Patch validate_figure_preflight to warn, render, collect, and assert manual_review_needed plus artifact_status.

def test_collect_artifacts_can_compare_baseline_without_mutating_project(self):
    # Render once, copy the figure as a baseline, collect with baseline_path, and assert baseline_matched.
```

- [ ] **Step 2: Run RED**

Run:

```bash
python3 hub_uv.py run python -m pytest tests/test_mcp_batch_quality.py -q
```

Expected: fail because `artifact_status`, `baseline_path`, and `baseline_comparison` are not implemented.

- [ ] **Step 3: Implement quality fields**

In `hub_core/mcp_surface.py`:

- Add optional `baseline_path` to `graphhub.render_csv_graph` and `graphhub.collect_artifacts` schemas.
- Add helper methods:
  - `_artifact_status(preflight, baseline_comparison)`
  - `_baseline_comparison(artifact_path, baseline_path)`
  - `_file_sha256(path)`
- Persist `artifact_status` and `baseline_comparison` in render manifests.
- Make collect recompute baseline comparison only when `baseline_path` is passed.

- [ ] **Step 4: Run GREEN**

Run:

```bash
python3 hub_uv.py run python -m pytest tests/test_mcp_batch_quality.py -q
python3 hub_uv.py run python -m pytest tests/test_mcp_rendering.py tests/test_mcp_batch_quality.py -q
```

Expected: all tests pass.

---

### Task 2: Bounded Batch Check Tool

- [ ] **Step 1: Write failing batch tests**

Add tests in `tests/test_mcp_batch_quality.py`:

```python
def test_tool_definitions_include_batch_check(self):
    # Assert graphhub.batch_check exists with root, max_projects, dry_run, batch_id, resume_manifest_path.

def test_batch_check_dry_run_excludes_invalid_legacy_and_ephemeral_projects_by_default(self):
    # Build fixture valid/invalid/legacy/.worktrees/[Athena]/bridge_jobs projects and assert skip reasons.

def test_batch_check_apply_writes_runtime_manifest_not_source_tree(self):
    # Run dry_run=False and assert only runtime_root/mcp_jobs/<batch_id>/batch_manifest.json is created.

def test_batch_check_resume_uses_prior_manifest(self):
    # Run once, then pass resume_manifest_path and assert resumed_from plus skipped prior projects.

def test_batch_check_timeout_returns_partial_manifest(self):
    # Patch batch deadline very small and assert status warning/manual_review_needed with timeout warning.
```

- [ ] **Step 2: Run RED**

Run:

```bash
python3 hub_uv.py run python -m pytest tests/test_mcp_batch_quality.py -q
```

Expected: fail because `graphhub.batch_check` is not implemented.

- [ ] **Step 3: Implement batch check**

In `hub_core/mcp_surface.py`:

- Add constants:
  - `MCP_BATCH_MAX_PROJECTS = 50`
  - `MCP_BATCH_TIMEOUT_SECONDS = 30.0`
- Add `graphhub.batch_check` to `TOOL_NAMES`, `WRITE_TOOL_NAMES`, tool definitions, and handlers.
- Handler inputs:
  - `root`, `max_depth`, `max_projects`, `include_invalid`, `include_legacy`, `include_worktrees`, `include_ephemeral`, `dry_run`, `batch_id`, `resume_manifest_path`.
- Default behavior:
  - exclude invalid configs from checks unless `include_invalid=true`,
  - exclude legacy unless `include_legacy=true`,
  - exclude `.worktrees/` and Athena `bridge_jobs/` unless explicitly included,
  - cap work to `max_projects <= MCP_BATCH_MAX_PROJECTS`,
  - write manifest only when `dry_run=false`.
- Result fields:
  - `batch_id`, `batch_root`, `manifest_path`, `checked_projects`, `skipped_projects`, `resumed_from`, `log_paths`.

- [ ] **Step 4: Run GREEN**

Run:

```bash
python3 hub_uv.py run python -m pytest tests/test_mcp_batch_quality.py -q
python3 hub_uv.py run python -m pytest tests/test_mcp_read_only.py tests/test_mcp_rendering.py tests/test_mcp_normalization.py tests/test_mcp_batch_quality.py -q
```

Expected: all tests pass.

---

### Task 3: Documentation, Review, and Merge

- [ ] **Step 1: Update Phase 4 doc**

Update `docs/02-design/graph_hub_mcp_surface/05_phase4_quality_gate_batch.md` with the implemented v1 scope and explicit non-goals.

- [ ] **Step 2: Run full verification**

Run:

```bash
python3 hub_uv.py run python -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 3: Request phase review**

Run:

```bash
/home/ubuntu/.codex/wrappers/review.sh deep-review "Review Phase 4 Graph Hub MCP quality gate and batch operation diff against origin/main. Focus on write boundaries, batch bounds, resume manifest correctness, invalid/legacy/ephemeral exclusions, baseline comparison safety, visual preflight/manual_review status, and existing CLI compatibility."
```

- [ ] **Step 4: Address review feedback with TDD**

For any finding, write a failing test first, verify RED, fix, rerun targeted and full tests, and rerun review.

- [ ] **Step 5: Commit, push, PR, merge, post-merge verification**

Use small commits:

```bash
git add docs/superpowers/plans/2026-06-07-phase4-quality-batch.md
git commit -m "plan phase 4 quality batch mcp work"
git add hub_core/mcp_surface.py tests/test_mcp_batch_quality.py docs/02-design/graph_hub_mcp_surface/05_phase4_quality_gate_batch.md
git commit -m "add batch quality mcp tools"
git push -u origin codex/phase4-batch-quality
gh pr create --title "[codex] add Phase 4 MCP quality batch checks" --body-file /tmp/graphhub-phase4-pr.md
gh pr merge --merge
git checkout main
git pull --ff-only
python3 hub_uv.py run python -m pytest -q
find . -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
git status --short --branch
```

---

## Self-Review

- Spec coverage: covers visual preflight status, manual review, optional baseline comparison, bounded batch checks, runtime logging, resume, filtering, and default invalid/legacy/ephemeral exclusions.
- Placeholder scan: no TBD/TODO/fill-in placeholders.
- Type consistency: tool names, result fields, and helper names are consistent across tasks.
- Scope guard: no unrestricted batch rendering and no source-project writes; batch v1 is a quality/check surface only.
