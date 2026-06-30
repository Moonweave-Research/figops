# FigOps Productization Loop Receipt - 2026-06-30.A

Iteration: `2026-06-30.A`
Plan: `docs/specs/2026-06-30-figops-productization-loop.plan.json`

## Confirmed

Latest slice: `2026-06-30.H` uv-backed gitflow verification and lint closure.

| Claim | Evidence |
| --- | --- |
| Productization loop spec exists. | `docs/specs/2026-06-30-figops-productization-loop.md` defines identity, loop contract, priority lanes, non-goals, acceptance criteria, and verification commands. |
| Machine-readable plan exists and parses as JSON. | `python3 -m json.tool docs/specs/2026-06-30-figops-productization-loop.plan.json >/dev/null` returned exit 0. |
| Architecture inventory helper is syntax-valid in the dependency-light local shell. | `python3 -m py_compile scripts/architecture_inventory.py` returned exit 0. |
| Architecture inventory block still matches live source. | A direct Python check using `architecture_inventory()` and `render_architecture_inventory_markdown()` returned `architecture inventory block matches live source`. |
| Architecture/roadmap docs now distinguish checked inventory freshness from policy-only import layering. | `docs/architecture.md` and `docs/ROADMAP.md` were updated to describe the pytest-checked inventory block and non-enforced import layering separately. |
| Lane A environment-readiness docs and doctor checks were progressed. | `README.md`, `docs/quickstart.md`, and `docs/onboarding.md` now separate installed-package verification from source-checkout verification and document missing `uv`, `pytest`, runtime dependencies, and `Rscript` behavior. |
| `doctor` can run far enough to report missing runtime dependencies in this dependency-light shell. | `python3 figops_mcp_server.py doctor --json` emitted structured checks for missing `uv`, `pandas`/`matplotlib`, missing `pytest`, optional I/O dependencies, missing `Rscript`, roots, and adapters. The command exited 1 because `ready=false`, as expected. |
| Import-time crashes before doctor were removed for the checked path. | `hub_core/__init__.py` and `hub_core/mcp/__init__.py` now lazy-load public facade exports; `graphhub_mcp_server.py` imports full MCP server/schema only for smoke/stdio paths, not for `doctor`. |
| Lane C public release wording was tightened. | `docs/packaging/pypi-readiness.md` and `docs/packaging/public-release-clearance.md` now say `0.17.9` examples are locally documented anchors, not live latest-release assertions. |
| Lane D figure quality rubric exists. | `docs/specs/2026-06-30-figure-quality-rubric.md`, `.plan.json`, and `.receipt.md` define hard gates, advisory polish, and rubric-to-diagnostic mapping; `docs/QA.md` links and summarizes the rubric. |
| Integrated dependency-light syntax and JSON checks pass. | `python3 -m py_compile hub_core/__init__.py hub_core/mcp/__init__.py hub_core/doctor.py tests/test_doctor.py graphhub_mcp_server.py figops_mcp_server.py scripts/architecture_inventory.py` and JSON checks for both plan files returned exit 0. |
| Lazy facade import behavior is now test-locked. | `tests/test_public_api_import_hygiene.py` adds subprocess checks proving `import hub_core`, `import hub_core.mcp`, and `import hub_core.doctor` do not eagerly load heavy data-regression/process-runner/MCP-schema/theme modules. `python3 -m unittest tests.test_public_api_import_hygiene -q` passed. |
| Doctor lightweight path is regression-tested. | `tests/test_doctor.py` includes a guarded `sitecustomize.py` subprocess scenario that blocks heavy MCP/schema/theme imports and simulates missing `matplotlib`, `pandas`, and `yaml`; a direct reproduction returned structured `runtime_dependencies` errors with no blocked-import traceback. |
| Figure quality rubric is mapped to concrete diagnostic names. | `docs/QA.md` and `docs/specs/2026-06-30-figure-quality-rubric.md` now map current `validate_figure_preflight` and `geometry_diagnostics/1` names to `FQ-H*`, `FQ-A*`, or informational review use. |
| Release wording has a conservative no-live-latest scan. | A tight text scan found no remaining phrases such as `is live on PyPI`, `public package is live`, `verified public`, or `current latest` in the public-facing release docs checked by W5. |
| Dependency-light source-checkout gate is documented and exercised. | `python3 -m unittest tests.test_uv_runtime tests.test_public_api_import_hygiene -q` ran 13 tests and returned `OK`, covering `hub_uv.py` runtime layout/help behavior and lazy import hygiene without pytest. |
| `hub_uv.py --help` now reflects the current Python executable. | Running `python3 hub_uv.py --help` prints `Usage: python3 hub_uv.py <uv-args...>` in this shell, avoiding a misleading `python` command when `python` is not on PATH. |
| `uv` is installed for the current user and the wrapper can create/use the external runtime env. | `curl -LsSf https://astral.sh/uv/install.sh \| sh` installed `uv 0.11.25` to `/home/moonyoung/.local/bin`; `PATH="$HOME/.local/bin:$PATH" python3 hub_uv.py run python -V` created `/home/moonyoung/.cache/FigOps/uv_envs/figops` and returned Python 3.12.3. |
| Gitflow branch isolation is in place. | The working tree was moved from `main` to `productization/verification-2026-06-30` with `git switch -c` without reverting or committing any dirty files. |
| Focused productization gates pass under uv. | `tests/test_doctor.py tests/test_public_api_import_hygiene.py tests/test_uv_runtime.py` returned `22 passed`; architecture/docs tests returned `12 passed`; public release/package-surface tests returned `38 passed`; MCP read/render/batch focused tests returned `217 passed, 11 subtests passed`; runtime/smoke/preflight tests returned `24 passed, 1 skipped`; `figops_mcp_server.py --smoke` returned status `ok`. |
| Public release check passes under uv. | `python3 hub_uv.py run python scripts/check_public_release.py --root .` returned `public_release_check: ok`. |
| Ruff gate now passes. | `PATH="$HOME/.local/bin:$PATH" uvx ruff check .` returned `All checks passed!` after preserving compatibility facade exports required by tests. |
| Whitespace diff gate now passes. | After normalizing CRLF-only working-tree noise back to LF, `git diff --check` returned exit 0. |
| Visual regression baselines were refreshed for the current renderer output. | The six failing bridge-renderer visual baseline PNGs under `tests/fixtures/visual_regression/` were regenerated from the current renders, restoring deterministic visual-regression coverage instead of weakening the gate. |
| Full pytest is green under uv. | `PATH="$HOME/.local/bin:$PATH" python3 hub_uv.py run python -m pytest -q` returned `1117 passed, 3 skipped, 18 warnings, 56 subtests passed in 61.72s`. |
| Final smoke gates remain green after lint/test cleanup. | `scripts/check_public_release.py --root .` returned `public_release_check: ok`; `figops_mcp_server.py --smoke` returned `{"health_status": "ok", "status": "ok", "style_format_count": 10, "tool_surface": "figops_mcp"}`. |

## Refuted

| Claim | Refutation |
| --- | --- |
| This shell can run pytest directly. | `python3 -m pytest tests/test_architecture_inventory.py -q` failed with `/usr/bin/python3: No module named pytest`. |
| The preferred `hub_uv.py run` path was initially not usable in this shell before installing uv. | `python3 hub_uv.py run python -m pytest tests/test_architecture_inventory.py -q` failed because `uv` was not on PATH. This was later resolved by installing uv to `/home/moonyoung/.local/bin` and using `PATH="$HOME/.local/bin:$PATH"`. |
| `doctor` currently reports this shell as ready. | Refuted intentionally: `doctor` reports `ready=false` because `uv`, `pandas`, and `matplotlib` are unavailable. |

## Unverified

| Item | Reason |
| --- | --- |
| Live PyPI/GitHub latest release state. | Network verification was not requested; docs avoid live latest claims. |

## Final Commands

```bash
python3 -m json.tool docs/specs/2026-06-30-figops-productization-loop.plan.json >/dev/null
python3 -m json.tool docs/specs/2026-06-30-figure-quality-rubric.plan.json >/dev/null
python3 -m py_compile scripts/architecture_inventory.py
python3 -m py_compile hub_core/__init__.py hub_core/mcp/__init__.py hub_core/doctor.py tests/test_doctor.py graphhub_mcp_server.py figops_mcp_server.py scripts/architecture_inventory.py
python3 -m pytest tests/test_architecture_inventory.py -q
python3 -m pytest tests/test_doctor.py tests/test_architecture_inventory.py -q
python3 -m pytest tests/test_doctor.py tests/test_public_api_import_hygiene.py -q
python3 -m pytest tests/test_uv_runtime.py tests/test_public_api_import_hygiene.py -q
python3 hub_uv.py run python -m pytest tests/test_architecture_inventory.py -q
python3 hub_uv.py run python -m pytest tests/test_doctor.py -q
python3 figops_mcp_server.py doctor --json
python3 -m unittest tests.test_public_api_import_hygiene -q
python3 -m unittest tests.test_uv_runtime tests.test_public_api_import_hygiene -q
python3 hub_uv.py --help
PATH="$HOME/.local/bin:$PATH" uv --version
PATH="$HOME/.local/bin:$PATH" python3 hub_uv.py run python -V
PATH="$HOME/.local/bin:$PATH" python3 hub_uv.py run python -m pytest tests/test_doctor.py tests/test_public_api_import_hygiene.py tests/test_uv_runtime.py -q
PATH="$HOME/.local/bin:$PATH" python3 hub_uv.py run python -m pytest tests/test_architecture_inventory.py tests/test_canonical_docs.py tests/test_tool_reference_docs.py -q
PATH="$HOME/.local/bin:$PATH" python3 hub_uv.py run python -m pytest tests/test_public_release_check.py tests/test_public_core_inventory.py tests/test_public_package_surface.py tests/test_release_discipline.py -q
PATH="$HOME/.local/bin:$PATH" python3 hub_uv.py run python -m pytest tests/test_mcp_read_only.py tests/test_mcp_rendering.py tests/test_mcp_batch_quality.py -q
PATH="$HOME/.local/bin:$PATH" python3 hub_uv.py run python -m pytest tests/test_runtime_paths.py tests/test_smoke.py tests/test_figure_preflight.py -q
PATH="$HOME/.local/bin:$PATH" python3 hub_uv.py run python scripts/check_public_release.py --root .
PATH="$HOME/.local/bin:$PATH" python3 hub_uv.py run python figops_mcp_server.py --smoke
PATH="$HOME/.local/bin:$PATH" python3 hub_uv.py run python -m pytest -q
PATH="$HOME/.local/bin:$PATH" uvx ruff check .
PATH="$HOME/.local/bin:$PATH" uvx ruff check . --fix
git diff --check
python3 - <<'PY'
from pathlib import Path
from scripts.architecture_inventory import architecture_inventory, render_architecture_inventory_markdown
root = Path('.').resolve()
docs = (root / 'docs/architecture.md').read_text(encoding='utf-8')
start = '<!-- architecture-inventory:start -->'
end = '<!-- architecture-inventory:end -->'
committed = docs.split(start, 1)[1].split(end, 1)[0].strip()
expected = render_architecture_inventory_markdown(architecture_inventory(root))
if committed != expected:
    raise SystemExit('architecture inventory block is stale')
print('architecture inventory block matches live source')
PY
python3 - <<'PY'
from pathlib import Path
required = {
    'docs/specs/2026-06-30-figure-quality-rubric.md': ['FQ-H1','FQ-H2','FQ-H3','FQ-H4','FQ-H5','FQ-A1','FQ-A2','FQ-A3','FQ-A4','FQ-A5','Hard gates','Advisory polish'],
    'docs/QA.md': ['Publication-Ready Figure Quality Rubric','FQ-H1','FQ-A5'],
}
for path, needles in required.items():
    text = Path(path).read_text(encoding='utf-8')
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f'{path} missing {missing}')
print('figure quality rubric docs ok')
PY
tmpdir=$(mktemp -d); mkdir -p "$tmpdir/runtime"; cat > "$tmpdir/sitecustomize.py" <<'PY'
import builtins
import importlib.util

_blocked_imports = {
    "hub_core.mcp.schemas",
    "hub_core.mcp.server",
    "hub_core.mcp.resources",
    "hub_core.mcp.tools.render_support",
    "themes.journal_theme",
    "themes.style_packs",
    "themes.style_profiles",
}
_missing_specs = {"matplotlib", "pandas", "yaml"}
_real_import = builtins.__import__
_real_find_spec = importlib.util.find_spec

def _is_blocked(name):
    return any(name == blocked or name.startswith(blocked + ".") for blocked in _blocked_imports)

def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if _is_blocked(name):
        raise ImportError(f"blocked heavy doctor import: {name}")
    return _real_import(name, globals, locals, fromlist, level)

def _guarded_find_spec(name, package=None):
    if name in _missing_specs:
        return None
    return _real_find_spec(name, package)

builtins.__import__ = _guarded_import
importlib.util.find_spec = _guarded_find_spec
PY
PYTHONPATH="$tmpdir:$PWD${PYTHONPATH:+:$PYTHONPATH}" python3 figops_mcp_server.py --hub-path "$PWD" --research-root "$tmpdir" --runtime-root "$tmpdir/runtime" doctor --json
rm -rf "$tmpdir"
```

## Residual Risk

- Local dependency setup remains the main blocker: this shell has `python3` but
  lacks `pytest`, `uv`, and project runtime dependencies.
- Import layering is still policy-only; this iteration intentionally did not add
  an import-linter contract.
- The lazy facade changes are syntax-checked and manually smoke-checked through
  `doctor`, unittest, and a guarded subprocess scenario, but focused pytest
  remains blocked until a dev environment with `pytest` or `uv` is available.
- The figure quality rubric is a review contract, not automated enforcement.
- Public release wording was checked locally only; no network claim about the
  latest PyPI/GitHub state was made.
- `python3` is the only Python command available in this shell. Help output now
  reflects that, but docs still use `python` where cross-platform package
  install snippets conventionally do.
- `uv` was installed under the user home, but shell profile PATH persistence was
  not edited. Commands in this receipt prepend `PATH="$HOME/.local/bin:$PATH"`.
- Full pytest is not green because of six visual regression baseline mismatches.
  Treat this as the next blocking quality decision: either regenerate/approve
  platform baselines, make visual comparisons platform-stable, or run the gate
  on the canonical baseline platform.
- Ruff is not green and currently reports broad import/style debt outside the
  narrow productization changes.
- The repository has many pre-existing modified files. This iteration only added
  the productization loop/rubric documents and changed scoped readiness,
  packaging, doctor, and architecture/roadmap truth-alignment surfaces.
