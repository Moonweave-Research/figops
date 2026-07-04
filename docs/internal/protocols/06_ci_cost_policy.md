# CI Cost-Control Policy

Date: 2026-07-04
Status: local-first operating protocol

## Policy

FigOps qualification is local-first. Agents must prove focused changes with
local commands before spending remote GitHub Actions minutes. For this branch of
work, use no GitHub Actions and no push unless the operator explicitly changes
the instruction.

The active workflow file remains `.github/workflows/ci.yml`. This protocol does
not activate a workflow by itself. The operator-ready candidate policy lives at
`docs/ops/ci-cost-control-workflow.candidate.yml` and must stay outside
`.github/workflows/` until an operator intentionally promotes it.

## Required Controls

Any proposed GitHub Actions workflow for FigOps must have:

- `timeout-minutes` at the workflow/job level as applicable, with every normal
  job bounded when no workflow-level timeout is available.
- `concurrency` at workflow level or on every job, so superseded runs are
  cancelled.
- Docs-only avoidance through trigger `paths`/`paths-ignore` or an explicit
  path-filter job that prevents full-suite work for documentation-only changes.
- Manual or opt-in heavy gates, such as `workflow_dispatch` with an input for
  full/evidence/dogfood jobs.

Validate these controls locally:

```powershell
C:/dev/figops-ascii-venv/Scripts/python.exe scripts/check_ci_cost_policy.py --workflow docs/ops/ci-cost-control-workflow.candidate.yml
```

Fallback:

```powershell
python hub_uv.py run python scripts/check_ci_cost_policy.py --workflow docs/ops/ci-cost-control-workflow.candidate.yml
```

## Workflow-Scope Caveat

Editing a file under `.github/workflows/` is a workflow-scope change. Pushing
that change can be rejected unless the credential has the GitHub `workflow`
scope, and a successful push can start paid Actions work. Keep workflow changes
as candidate files under `docs/ops/` until the operator confirms budget, token
scope, and promotion timing.

## Forbidden During No-CI Work

Do not run:

```powershell
gh workflow run ...
gh pr checks --watch ...
git push
```

Do not edit `.github/workflows/ci.yml` during a no-CI handoff unless the user
explicitly reopens that scope.
