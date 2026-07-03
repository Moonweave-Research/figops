# Final QA Release Readiness and Next Roadmap

Source of truth: `docs/specs/2026-07-03-final-qa-release-readiness.plan.json`

Review date: 2026-07-03

Team artifact root: `.omo/teams/team-e58a2c43/artifacts/`

## Objective

Record the final team QA result, the follow-on `0.17.11` TestPyPI dry run, and
the public PyPI promotion. This is a readiness and claim-boundary receipt, not a
GitHub Release record.

## Team Slices

| Slice | Artifact | Result |
| --- | --- | --- |
| Release gates | `.omo/teams/team-e58a2c43/artifacts/release-gates-report.md` | Source metadata prepared for `0.17.11`; no tag, release, or publish action taken. |
| Graph qualification | `.omo/teams/team-e58a2c43/artifacts/graph-qualification-report.md` | Graph tooling supports publication-oriented claims; top-level pass fields alone must not be treated as publishable evidence. |
| Agent docs/contracts | `.omo/teams/team-e58a2c43/artifacts/agent-doc-contracts-report.md` | README overclaim fixed from publication-ready to publication-oriented; QA/rubric/quality-gate contracts aligned. |
| Next roadmap | `.omo/teams/team-e58a2c43/artifacts/member-D-improvement-roadmap.md` | No broad roadmap release blocker; next work should focus on claim truth, graph fixture qualification, and maintenance decomposition. |

## Current Release State

- Source metadata is now `0.17.11` in `pyproject.toml`.
- `CHANGELOG.md` has a top `0.17.11` entry dated `2026-07-03`.
- README and roadmap source-state references now point at `0.17.11`.
- Latest documented PyPI package is `figops==0.17.11`, published by the manual
  `pypi` workflow promotion and install-smoke verified.
- TestPyPI has `figops==0.17.11`, published by the manual `testpypi` workflow
  dry run and install-smoke verified.
- Latest documented GitHub Release asset remains `v0.17.10`.
- No tag or GitHub Release was created during this QA pass.

Release decision:

- Source readiness: ready for maintainer review.
- Public PyPI release action: completed for `0.17.11`; future promotions remain
  operator-controlled.
- Repository-public decision: still separate from package distribution and must
  remain owner-controlled.

## Verification Evidence

Passed in this QA pass:

```bash
python scripts/check_public_release.py
# public_release_check: ok

python -m build
# built dist/figops-0.17.11-py3-none-any.whl and dist/figops-0.17.11.tar.gz

python scripts/package_metadata_smoke.py
# ok true for 0.17.11 artifacts

python scripts/public_package_surface.py
# ok true for 0.17.11 artifacts

python -m pytest tests/test_bridge_renderer.py tests/test_bridge_renderer_robustness.py -q
# 142 passed, 4 warnings, 10 subtests passed
```

Hosted evidence:

- Latest `main` CI for commit `70a64c3` succeeded:
  <https://github.com/Moonweave-Research/figops/actions/runs/28658580567>
- Jobs `Test (gating)`, `Ruff (advisory)`, and
  `Dependency audit (advisory)` all succeeded.
- Manual TestPyPI publish workflow for commit `70a64c3` succeeded:
  <https://github.com/Moonweave-Research/figops/actions/runs/28660384625>
- Workflow jobs `Verify release ref`, `Build and verify distributions`, and
  `Publish to TestPyPI` succeeded; `Publish to PyPI` was skipped.
- Manual PyPI publish workflow for commit `6fd9fb5` succeeded:
  <https://github.com/Moonweave-Research/figops/actions/runs/28662615485>
- Workflow jobs `Verify release ref`, `Build and verify distributions`, and
  `Publish to PyPI` succeeded; `Publish to TestPyPI` was skipped.

TestPyPI install evidence:

```bash
python -m venv C:\dev\figops-testpypi-smoke
C:\dev\figops-testpypi-smoke\Scripts\python.exe -m pip install \
  --index-url https://pypi.org/simple \
  --extra-index-url https://test.pypi.org/simple \
  figops==0.17.11
C:\dev\figops-testpypi-smoke\Scripts\figops-mcp.exe --smoke
# {"health_status": "ok", "status": "ok", ...}
```

PyPI install evidence:

```bash
python -m venv C:\dev\figops-pypi-smoke
C:\dev\figops-pypi-smoke\Scripts\python.exe -m pip install figops==0.17.11
C:\dev\figops-pypi-smoke\Scripts\figops-mcp.exe --smoke
# {"health_status": "ok", "status": "ok", ...}
```

Environment caveats:

- Several member-local checks could not use `python hub_uv.py run ...` because
  `uv` was not on `PATH` in those member environments.
- Artifact-local graph tests produced visual-regression image-size mismatches
  under an ad hoc dependency stack. The Windows-native project test environment
  passed the bridge renderer and robustness suite, so those mismatches are
  recorded as stack sensitivity, not product regression evidence.

## Graph Qualification Boundary

Approved public wording remains publication-oriented, not unqualified
publication-ready.

The generated MCP render evidence had:

- `status: ok`
- `manual_review_needed: False`
- `visual_preflight_status.passed: True`
- `geometry_diagnostics.passed: True`
- `layout_report.passed: True`
- one unmeasured hard-gate-relevant check:
  `artist_overlaps` with `passed: None` because reportable artist-pair count
  exceeded the configured cap.

Therefore, agents and docs must not treat top-level pass fields alone as proof
that a graph is publishable. A `publishable` verdict still requires cited hard
gate evidence, no unresolved `manual_review_needed=true`, and no unmeasured
hard-gate diagnostic being counted as a pass.

## Next Improvement Queue

P0 - Claim and release truth reconciliation:

- Keep README and public docs on publication-oriented wording unless a specific
  render receives a rubric-backed `publishable` verdict.
- Keep source version, changelog, README, roadmap, and packaging docs aligned
  whenever post-tag commits exist.
- Treat GitHub Release, PyPI, and future TestPyPI publication as explicit
  operator actions, not automatic consequences of metadata readiness.

P1 - Graph QA fixture qualification pack:

- Add fixtures for crowded point labels, dense legends, long category labels,
  multipanel/shared legends, low-contrast overlays, and annotation callouts.
- Store expected `geometry_diagnostics` and `layout_report` summaries beside
  representative generated examples.
- Tie visual baselines to the locked project dependency stack.

P1b - Diagnostic-to-rubric guard:

- Add a generated or checked mapping from every `geometry_diagnostics/1` check
  name to a rubric classification or explicit informational status.
- Ensure unmeasured hard-gate checks cannot silently look like complete passes
  to agents consuming render envelopes.

P1c - Lightweight docs verification:

- Add or document a docs-only verification command that can check claim-boundary
  anchors and JSON plan files without requiring the full plotting/test stack.

P2 - Maintenance decomposition:

- Continue behavior-preserving decomposition of over-budget architecture
  modules from the live inventory.
- Do not mix visual pixel changes and broad architecture movement in one PR
  unless fixture evidence is captured first.

P3 - Optional external publisher matrix:

- Only required if future marketing claims current journal-specific compliance
  beyond encoded FigOps tokens.
- If added, include publisher URL, checked date, encoded token values, and
  fixture coverage per journal/profile target.

## Final QA Verdict

The current source checkout is released to public PyPI as `figops==0.17.11`,
with local package artifacts, TestPyPI, and public PyPI install smoke verified.
It is not yet a GitHub Release. No tag or GitHub Release should be performed
without explicit operator approval.

Graph tooling is qualified as publication-oriented with diagnostics and manual
review escalation. It is not qualified for unconditional publication-ready,
optimal-labeling, or latest-publisher-compliance claims.
