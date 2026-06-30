# FigOps Productization Review Loop

Source of truth: `docs/specs/2026-06-30-figops-productization-loop.plan.json`

## Objective

Run FigOps through a repeating spec -> review -> implementation -> verification
loop until the tool is stable as a shareable lab figure-operations package.

The loop starts from the current v0.17.10 source-line state: core research-ops,
MCP, plotting, provenance, and release-readiness surfaces already exist. The
remaining work should improve operability, trust, and maintainability without
reopening shipped milestone scope.

## Product Identity

FigOps is not a general plotting gallery and not a notebook replacement. It is a
research figure-operations tool:

- project config is the execution contract;
- data contracts and research-ops gates are the safety rail;
- journal/presentation style targets make figures reproducible;
- provenance makes rendered outputs auditable;
- MCP tools let agents inspect and render through the same contract.

## Loop Contract

Each iteration must produce four artifacts or an explicit reason why one is not
needed:

1. **Spec update**: define the problem, scope, non-goals, acceptance criteria,
   and verification commands.
2. **Review**: try to refute the spec against live code, tests, docs, and local
   environment constraints.
3. **Implementation**: make the smallest coherent change that satisfies the
   accepted slice.
4. **Verification receipt**: record commands, pass/fail state, blocked
   environment requirements, and residual risk.

Do not start implementation for a slice until the spec has an acceptance
criterion that can be checked by tests, generated docs, or a deterministic
manual command.

## Priority Lanes

### Lane A - Environment And Install Readiness

Goal: make first-run failure modes obvious and actionable.

Current evidence:

- Local shell may have `python3` but not `python`, `uv`, `pytest`, `pandas`, or
  `matplotlib`.
- `figops.doctor` already reports missing `uv` and `Rscript`, but onboarding
  still depends on the reader choosing the right command path.

Acceptance examples:

- README quickstart distinguishes source-checkout verification from installed
  package verification.
- `doctor` output stays actionable when `uv` or R is absent.
- Verification receipts never count missing environment commands as passing.

### Lane B - Architecture Debt And Guardrails

Goal: keep large-module debt visible while avoiding broad rewrites.

Current evidence:

- `scripts/architecture_inventory.py` reports modules over the 800-line split
  signal.
- `tests/test_architecture_inventory.py` checks that the committed inventory in
  `docs/architecture.md` matches live source.
- Import layering is still policy-only and should not be described as
  mechanically enforced.

Acceptance examples:

- Architecture docs accurately distinguish the CI-checked inventory block from
  non-enforced layering policy.
- Each extraction keeps compatibility shims where public/private imports already
  exist.
- Each moved behavior has a witness test.

### Lane C - Public Release And Version Alignment

Goal: keep public claims true when source and published package differ.

Current evidence:

- Source checkout is `0.17.10`.
- Locally documented public package/release state is `0.17.9`.
- Network verification of latest PyPI/GitHub state is not assumed.

Acceptance examples:

- README, roadmap, packaging docs, and changelog agree about source versus
  published state.
- Release publication remains a human-gated action.
- Public release checks remain green before tagging or upload.

### Lane D - Figure Quality Rubric

Goal: define what "publication-ready" means beyond passing geometry checks.

Current evidence:

- Geometry diagnostics and journal preflight cover objective layout and style
  failures.
- The remaining quality gap is higher-level polish: visual hierarchy, panel
  balance, label density, contrast, and narrative clarity.

Acceptance examples:

- A compact rubric exists for human/agent review of rendered figures.
- The rubric separates hard gates from advisory polish.
- Future diagnostics map to rubric items instead of one-off warnings.

## Initial Iteration

Iteration `2026-06-30.A` is a documentation and truth-alignment slice.

Scope:

- Add this productization loop spec and matching machine-readable plan.
- Correct architecture/roadmap language where it claims the module-size
  inventory is not CI-checked.

Non-goals:

- No package publication.
- No dependency installation.
- No broad module decomposition.
- No import-linter implementation in this slice.

Acceptance criteria:

- The new plan document names the priority lanes and loop gates.
- `docs/architecture.md` says the module-size inventory freshness is checked by
  pytest, while import layering remains policy-only.
- `docs/ROADMAP.md` no longer implies the whole architecture guard surface is
  absent from CI.
- `python3 -m py_compile scripts/architecture_inventory.py` succeeds in a
  dependency-light environment.

## Verification Commands

Use the strongest available command set, recording environment blockers instead
of silently skipping them:

```bash
python3 -m py_compile scripts/architecture_inventory.py
python3 -m pytest tests/test_architecture_inventory.py -q
python3 hub_uv.py run python -m pytest tests/test_architecture_inventory.py -q
```

The pytest commands require a configured Python environment. If `pytest` or
`uv` is unavailable, record the blocker and use `py_compile` as the minimum
syntax check for this documentation slice.
