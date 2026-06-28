# FigOps Maintenance Execution Workflow - 2026-06-28

## Purpose

Turn `docs/specs/2026-06-28-maintenance-agent-spec.md` into an end-to-end
workflow that an implementation agent can run until no known gaps remain.

This workflow is intentionally iterative:

1. choose a bounded scope,
2. implement,
3. review twice,
4. audit for omissions,
5. either close the scope or loop back.

No scope is complete until its acceptance criteria, edge cases, and verification
evidence are all accounted for.

## Workflow State Model

Track each finding with one of these statuses:

| Status | Meaning |
| --- | --- |
| `open` | Finding has not been addressed. |
| `in_progress` | Implementation is underway. |
| `implemented` | Code/docs changed, but reviews are not complete. |
| `review_1_done` | Implementation correctness review passed. |
| `review_2_done` | Operational edge-case review passed. |
| `verified` | Required verification ran or blockers are explicitly documented. |
| `closed` | Acceptance criteria, edge cases, and handoff evidence are complete. |
| `blocked` | Work cannot continue without an external dependency, decision, or environment. |

The agent should keep this state in its PR description or handoff notes. Do not
add a permanent tracking file unless the maintainer asks for one.

## Master Loop

Repeat this loop until every in-scope finding is `closed` or intentionally
`blocked` with a clear owner and next action.

```text
1. Intake
   - Read the agent spec and this workflow.
   - Read the current code/docs for the selected finding.
   - Capture git status.

2. Scope selection
   - Pick the smallest coherent PR from the suggested sequence.
   - State which findings are in scope and which are explicitly out of scope.

3. Pre-implementation witness
   - Identify the behavior to prove.
   - Add or update a focused test when practical.
   - If no test is practical, write the exact manual/runtime check before coding.

4. Implementation
   - Make the smallest code/docs changes that satisfy the target behavior.
   - Preserve public imports, CLI commands, MCP tool names, and package boundary.

5. Review Pass 1 - implementation correctness
   - Check behavior against the finding acceptance criteria.
   - Fix any mismatch, then rerun this pass.

6. Review Pass 2 - operational edge cases
   - Check missing tools, Windows paths/encoding, public/private boundary,
     generated docs, and handoff honesty.
   - Fix any mismatch, then rerun both review passes.

7. Verification
   - Run narrow tests.
   - Run compileall.
   - Run broader tests only when dependencies are available and scope warrants.
   - Record commands not run and why.

8. Gap audit
   - Compare implementation against every acceptance criterion and edge case.
   - Mark each criterion `covered`, `not_applicable`, or `blocked`.
   - If any criterion is uncovered, return to step 3 or split a follow-up PR.

9. Handoff
   - Summarize files changed.
   - Report finding statuses.
   - Include Review Pass 1/2 results.
   - Include verification evidence and blockers.
```

## Finding Coverage Matrix

Use this matrix as the minimum closure checklist.

| Finding | Must prove | Required review emphasis |
| --- | --- | --- |
| F1 missing `uv` bootstrap | Missing `uv` gives clear non-zero failure; env path isolation still holds. | Windows PATH behavior, ASCII-safe error, no repo-local `.venv`. |
| F2 ISPD trap density placeholder | Function cannot silently return `None`; unsupported science is explicit. | No guessed formula, no change to fit return shapes. |
| F3 top-level import hygiene | Import bugs and missing dependencies are not swallowed silently. | `__all__` honesty, standalone checkout compatibility. |
| F4 scaffold target prompt | Wizard cannot write invalid `target_format` from its own prompt. | case/whitespace handling, `internal` handling, non-interactive scaffold still valid. |
| F5 stale roadmap/architecture docs | Docs match `0.17.9` line and current large-module inventory. | No false CI/public-release claims, generated docs not hand-edited. |

## PR Workflow

### PR 1 - Reliability hardening

Findings:

- F1
- F2
- F4 if the change remains small

Implementation order:

1. Add missing-`uv` test coverage around `hub_core.uv_runtime.run_uv()` or the
   narrowest existing seam.
2. Implement explicit missing-`uv` handling.
3. Add ISPD placeholder test, then replace `pass` with explicit failure.
4. Add scaffold target validation/prompt coverage if in scope.
5. Run Review Pass 1 and Review Pass 2.
6. Run verification or record dependency blockers.

Exit conditions:

- F1 and F2 are `closed`.
- F4 is either `closed` or explicitly left `open` for PR 2 with rationale.
- Handoff states whether tests ran through direct Python or `hub_uv.py`.

### PR 2 - Import hygiene and docs truth

Findings:

- F3
- F5
- F4 if deferred from PR 1

Implementation order:

1. Decide whether top-level re-export should be removed, narrowed, or made
   honest through conditional `__all__`.
2. Add import behavior coverage if practical.
3. Refresh architecture and roadmap wording against live code.
4. Recompute large-module line counts with a documented command.
5. Update docs only where they describe current reality.
6. Run both review passes.
7. Run verification or record dependency blockers.

Exit conditions:

- F3 and F5 are `closed`.
- F4 is `closed` if it entered this PR.
- Docs do not claim generated references are fresh unless the generator or
  freshness test ran.

### PR 3 - Decomposition planning

Findings:

- Large-module debt follow-up from F5.

Implementation order:

1. Inventory current over-budget files.
2. For each target module, identify stable public functions/classes.
3. Propose extraction seams and compatibility shims.
4. List required witness tests before each future extraction.
5. Run both review passes against the plan.

Exit conditions:

- The plan names concrete modules and avoids broad behavior changes.
- No implementation refactor is mixed in unless it is tiny and fully covered.

## Final Merge Workflow

Use this workflow after the selected implementation scope has passed both
review passes. It is designed for autonomous execution up to the point where
the repository or hosting platform requires protected-branch permissions.

1. **Branch safety**
   - Work on a `codex/` branch, not directly on `main`.
   - If work started on `main`, create a `codex/` branch before staging.
   - Confirm `git status --short` contains only intended files.

2. **Final verification gate**
   - Run the full local regression command when the environment supports it:
     `python hub_uv.py run python -m pytest -q`.
   - Run the project lint command:
     `python hub_uv.py run ruff check __init__.py orchestrator.py hub_core plotting themes scripts tests`.
   - Run bytecode compilation:
     `python hub_uv.py run python -m compileall -q orchestrator.py hub_core plotting themes graphhub_mcp_server.py figops_mcp_server.py tests`.
   - Run whitespace validation:
     `git diff --check`.

3. **Final review gate**
   - Review Pass 1 must report no correctness issues.
   - Review Pass 2 must report no operational edge-case issues.
   - If either pass finds an issue, fix it and rerun the full verification
     gate.

4. **Commit gate**
   - Stage only intended files.
   - Commit with a message that names the maintenance scope and verification.
   - Re-run `git status --short`; it should be clean after commit.

5. **Merge/publish gate**
   - If local policy allows direct merge, fast-forward or no-ff merge the
     verified `codex/` branch into `main`, then rerun at least `git status
     --short` and record the resulting commit.
   - If the remote uses protected branches, push the `codex/` branch and open a
     PR instead of forcing a direct merge.
   - Do not bypass failing checks, unresolved review findings, or protected
     branch policy.

6. **Handoff**
   - Report branch, commit hash, verification commands, and Review Pass 1/2
     results.
   - Explicitly state whether the branch was merged locally, pushed for PR, or
     blocked by external permissions.

## Review Templates

### Review Pass 1 Template

```text
Review Pass 1 - Implementation Correctness

Scope:
- Findings:
- Files:

Checks:
- Acceptance criteria covered:
- Tests cover success path:
- Tests cover failure path:
- Silent fallback introduced: yes/no
- Compatibility changed: yes/no

Issues found:
- None, or list fixes made.

Result:
- pass/fail
```

### Review Pass 2 Template

```text
Review Pass 2 - Operational Edge Cases

Checks:
- Missing dependency/tool behavior:
- Windows path/encoding behavior:
- Public package/private repo boundary:
- Generated docs handling:
- CI/release/doc claims:
- Handoff evidence:

Issues found:
- None, or list fixes made.

Result:
- pass/fail
```

### Gap Audit Template

```text
Gap Audit

Finding:
- Acceptance criteria:
  - [covered/not_applicable/blocked] ...
- Edge cases:
  - [covered/not_applicable/blocked] ...
- Verification:
  - [ran/not_run/blocked] ...
- Remaining work:
  - None, or list follow-up.

Status:
- open/in_progress/implemented/review_1_done/review_2_done/verified/closed/blocked
```

## Verification Ladder

Use the highest rung available. Do not skip lower-rung failures.

1. Syntax:

```bash
python -m compileall -q orchestrator.py hub_core plotting themes graphhub_mcp_server.py figops_mcp_server.py
```

2. Narrow tests:

```bash
python -m pytest tests/test_uv_runtime.py -q
python -m pytest <focused-test-file> -q
```

3. Source-checkout runtime:

```bash
python hub_uv.py run python -m pytest <focused-test-file> -q
python hub_uv.py run ruff check <changed-python-files>
```

4. Package/release surface:

```bash
python scripts/package_metadata_smoke.py
python scripts/public_package_surface.py
python scripts/check_public_release.py
```

5. Full local regression, when warranted:

```bash
python hub_uv.py run python -m pytest -q
python hub_uv.py run ruff check .
```

Expected blockers in an unbootstrapped shell:

- `uv` may be missing.
- `pytest` may be missing.
- `pyyaml` may be missing.
- `ruff` may be missing.

When a rung is blocked, record the exact missing command/module and continue
only with checks that are still meaningful.

## Completion Definition

The maintenance workflow is complete when:

- F1-F5 are all `closed`, or a maintainer explicitly accepts a `blocked` status
  for one finding.
- Each closed finding has acceptance criteria and edge cases accounted for.
- Review Pass 1 and Review Pass 2 were completed for each PR.
- Verification commands are recorded honestly.
- `git status --short` contains only intended files for the final handoff.
- No public/private boundary was widened.
- No generated-doc freshness claim is made without evidence.
