# Graph Hub — Remaining Audit Remediation Spec (handoff to implementer)

> Status: implementation spec. The concrete-defect roadmap from the 2026-06 adversarial
> audit (P0/P1/P2 + two P3 items) is **already merged to `main`** across PRs
> #50, #54, #55, #56, #57, #58, #59, #60, #61. This document specifies the **three
> remaining items**, which were deliberately deferred because they need policy judgment,
> exploratory audit, or an environment the dev sandbox cannot provide.
>
> Scope of this doc: precise findings + required changes + tests + acceptance, so an
> external implementer (e.g. Codex) can execute without re-deriving context.

## Repository constraints (MUST follow)

- Python ≥3.12, dependency state in `pyproject.toml` + `uv.lock`. Run everything via
  `uv run ...` (a hook blocks bare `python`/`python3`). Tests: `uv run python -m pytest`.
- The test suite opts into write tools via a `conftest.py` session fixture that sets
  `GRAPH_HUB_MCP_WRITE_TOOLS_ENABLED=1`; the MCP server itself fails **closed** by default.
- CI (`.github/workflows/ci.yml`): `Test` job is gating; `Ruff` and `Dependency audit`
  (pip-audit) are advisory (the repo carries ~190 pre-existing ruff findings). New code
  must be ruff-clean even though the repo isn't.
- TDD: every behavioral change needs a runtime-witness test that fails on the pre-fix code.
- One logical change per commit; branch off `main`; open a PR per item; keep PRs to
  disjoint files where possible.
- Do **not** add backward-compat shims; update all call sites on a rename.

---

## Item A — R analysis subsystem

### A.1 Finding (HIGH, real): input-path contract is three-way inconsistent → silent dummy data

The canonical input contract (`project_config_template.yaml`) is:
- `pipeline.analysis[].inputs: ["raw/"]` (line ~104), examples use `raw/<file>.csv` (line ~163), and
- the orchestrator exposes resolved inputs to scripts via the **`GRAPH_HUB_INPUTS`** env
  var (colon-separated resolved paths; documented at template line ~10).

But the scaffolded analysis script disagrees:
- `hub_core/scaffold.py` `DEFAULT_ANALYZE_R` (line ~11): `raw_dir <- file.path(getwd(), "data", "raw")`
  — reads **`data/raw/`**, and `scaffold.py` (~line 214) creates `data/raw/`.
- `hub_core/project_normalization.py` (line ~418): raw inputs are migrated to **`raw/`**
  (`return (Path("raw") / tail), "raw/data input preserved", "copy"`), matching the template.

Consequence: a project produced/normalized via `normalize_project_structure` (or any project
following the documented `raw/` convention) has its inputs in `raw/`, but the scaffolded
`analyze.R` looks in `data/raw/`, finds no CSV, and **falls back to a hardcoded dummy tibble
of zeros** (`scaffold.py` DEFAULT_ANALYZE_R lines ~19-24) — rendering a zeros figure with no
error. This is the audit's "silent wrong data" signature.

### A.2 Required fix

Make `analyze.R` consume the canonical contract instead of a hardcoded path:
1. In `DEFAULT_ANALYZE_R` (`hub_core/scaffold.py`, mirrored in `hub_core/project_normalization.py`
   which writes the same template at line ~356): resolve inputs from the **`GRAPH_HUB_INPUTS`**
   env var first (split on the OS path separator; these are already-resolved absolute paths),
   and fall back to globbing **`raw/`** (not `data/raw/`) when the env var is empty. Remove the
   `data/raw` hardcode.
2. When **no** input file is found, **fail loudly** (`stop(...)`) instead of silently emitting
   the dummy-zeros tibble — or, if a no-input bootstrap is genuinely wanted, gate it behind an
   explicit `GRAPH_HUB_ALLOW_EMPTY_ANALYSIS=1` and print a clear warning. Silent zeros are
   prohibited.
3. Align scaffold's created input directory with the chosen convention (`raw/`), and confirm
   `project_config_template.yaml` (`inputs: ["raw/"]`) stays consistent.

### A.3 Finding (LOW, mitigated): R command construction interpolates the script path

`hub_core/process_runner.py` `_build_r_cmd` (lines 138-151): when `environment.r_strict` is
true it builds `Rscript -e "...; source('{safe_path}')"`, where
`safe_path = str(script_path).replace("\\","\\\\").replace("'","\\'")`. The single-quote and
backslash escaping is **correct for an R single-quoted string**, and the non-strict path passes
the script as plain argv (`[runner, script_path]`, no shell), so there is **no active injection
vuln**. Recommendation (defense-in-depth, not a bug): replace the `-e "...source('<path>')"`
interpolation with `Rscript --file=<path>` (path as argv, no string interpolation) or pass the
path via an env var / `commandArgs()`, and keep the `renv::activate()` bootstrap via a tiny
fixed wrapper script rather than an interpolated `-e` expression.

### A.4 Finding (context): R reads trusted env vars

`themes/journal_theme.R` reads `Sys.getenv("RESEARCH_HUB_PATH")` (line ~74) and
`Sys.getenv("SOURCE_DATE_EPOCH")` (line ~98). No `system()`/`eval(parse())`/`shell()` exists in
any `.R` file (grep-confirmed), so there is no R-side command-injection surface. The
`RESEARCH_HUB_PATH` dependency ties into Item B (env trust).

### A.5 Tests

- A normalized-layout project (inputs in `raw/`) renders **real** data through `analyze.R`
  (assert the produced `results/data/summary.csv` reflects the input, not zeros).
- A project with **no** input files makes the analysis step **fail** (non-zero / raised),
  not silently produce zeros (unless the explicit allow-empty flag is set).
- These can be driven through the existing process-runner / orchestrator test harness;
  gate on `Rscript` availability with a skip if R is not installed in CI.

---

## Item B — Environment trust model

### B.1 Finding (MEDIUM, threat-model): env vars silently widen the security sandbox

Several env vars feed the security-relevant surfaces hardened in P0 (PR #50):
- `GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS` — `GraphHubMCPServer._allowed_data_roots`
  (`hub_core/mcp_surface.py` ~lines 907-920) splits this on the path separator and appends each
  entry as an allowed data root **with no validation**. Setting it to `/` (or any broad path)
  silently neutralizes the `_resolve_under_root` / `_resolve_allowed_data_path` containment that
  P0 added.
- `RESEARCH_HUB_PATH`, `RESEARCH_HUB_RUNTIME_ROOT` / `_HOME`, `PROJECT_ROOT`, `ATHENA_PATH` —
  feed `sys.path` inserts (import surface), the runtime/output root, and the allowed-roots set
  (the runtime root becomes an allowed data root, ~`mcp_surface.py:1192` ordering).

The server's trust model is "the launching environment is trusted." That is reasonable, but it
is **undocumented**, and `GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS` provides an unvalidated, unlogged
way to widen the sandbox — surprising for an operator and dangerous if the launch env is even
partly attacker-influenced.

### B.2 Required changes (validation + documentation, NOT a behavior lockdown)

This is intentionally conservative — broad roots may be a legitimate operator choice, so do not
hard-reject them. Instead:
1. **Validate** each `GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS` entry: it must be a non-empty, absolute,
   existing directory; skip (with a `warning`) entries that are not, so a typo silently widening
   nothing-or-everything is surfaced.
2. **Warn** (do not reject) when a configured data root is a filesystem root (`/`, a drive root)
   or the user home, since that effectively disables containment — make the operator's choice
   loud, not silent. Consider a `GRAPH_HUB_MCP_STRICT_ROOTS=1` that upgrades that warning to a
   refusal for locked-down deployments.
3. Validate that `RESEARCH_HUB_RUNTIME_ROOT`/`PROJECT_ROOT`-derived paths resolve to existing
   directories before they are used / inserted into `sys.path`.
4. **Document** the trust model: a short section (e.g. in `AGENTS.md` or a security doc) listing
   every env var that affects the security boundary, what it widens, and the expectation that the
   launcher is trusted.

### B.3 Tests

- `GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS` with a non-existent / relative entry → that entry is
  dropped and a warning is emitted; valid entries still take effect.
- With `GRAPH_HUB_MCP_ALLOWED_DATA_ROOTS=/` (or strict mode), assert the warning (or refusal in
  strict mode) and that a data path outside `research_root` behaves per the chosen policy.
- A path-guard regression test confirming containment still holds for the default (no env)
  configuration.

---

## Item C — Supply-chain dependency bump

### C.1 Finding (MEDIUM, real CVEs)

The CI `Dependency audit` job (advisory) reports, on every run:
- **`lxml 6.0.4` → PYSEC-2026-87**, fixed in **6.1.0**. (lxml parses panel SVGs in
  `plotting/figure_assembler.py`; P0 added `_safe_svg_fromfile` hardening, but the dependency
  itself is below the fix floor.)
- **`pymdown-extensions 10.21.2` → CVE-2026-46338**, fixed in **10.21.3**.

### C.2 Required changes (one PR; trivial but environment-sensitive)

1. In `pyproject.toml` `[project].dependencies`, bump the floors:
   - `"lxml>=5.0"` → `"lxml>=6.1.0"`
   - `"pymdown-extensions>=10.21.2"` → `"pymdown-extensions>=10.21.3"`
2. `uv lock` to update `uv.lock`, then `uv sync`.
3. Verify: `uv run python -m pytest -q` (full suite green), and `uvx pip-audit -r <(uv export
   --no-emit-project --no-hashes)` reports the two findings resolved.

### C.3 Environment caveat (why this was deferred)

In the original dev sandbox, **editing `pyproject.toml` dependencies triggers a PreToolUse hook
that runs `uv run`, which tries to sync the new `lxml 6.1.1` wheel into a uv cache that corrupts
on fresh-package install — locking every mutating tool in the session.** Do this work in a
**clean environment** (a normal dev machine or CI), where `uv lock` / `uv sync` / `pip-audit`
run without that cache pathology. Recovery if a sandbox does lock up: clear the corrupt cache
entry under the uv cache dir and `git checkout -- pyproject.toml uv.lock` from an isolated
git worktree.

---

## Global acceptance criteria

- Each item is a separate PR off `main` with logical commits.
- Full suite (`uv run python -m pytest -q`) green; new/changed code ruff-clean.
- Every behavioral change has a runtime-witness test (fails on pre-fix code).
- No silent fallbacks introduced; loud failures preferred (matches `AGENTS.md`:
  "Silent failure is prohibited. Fail-fast.").
- Item C additionally: pip-audit clean for the two named advisories.
