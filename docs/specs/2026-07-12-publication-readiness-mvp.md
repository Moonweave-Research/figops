# FigOps Publication Readiness MVP

Source of truth: `docs/specs/2026-07-12-publication-readiness-mvp.plan.json`

## Objective

Unify FigOps' existing validation evidence into one conservative answer to:

> Is this figure ready for a researcher to review?

The MVP is a read-only evaluator, not an approval system. It reports exactly
one of three states:

- `blocked`: required evidence is missing, malformed, unsupported, unknown, or
  a hard gate failed.
- `needs_revision`: all required evidence is usable, but at least one major
  actionable quality finding remains.
- `needs_review`: required automatic gates passed and no major actionable
  finding remains; human scientific review is still required.

Automatic evaluation never claims that a figure is publication-approved.

## Research And Prior Art

FigOps already produces the evidence needed for a useful first decision:

- project data-contract and semantic validation;
- calculation and research-ops checks;
- render/preflight and geometry diagnostics;
- optional baseline or regression comparison;
- config, Git, input, and environment provenance.

The current quality-gate protocol deliberately warns that render success and
`manual_review_needed=false` do not prove publication readiness. The MVP keeps
that principle. It consolidates existing evidence without replacing scientific
judgment or changing producer schemas.

The design follows provenance-oriented build systems and policy evaluators:
normalize heterogeneous evidence, evaluate a pure decision table, and render
machine- and human-readable reports from the same result. Missing evidence is
an explicit failure mode rather than an implicit pass.

## Product Position And Non-Goals

The MVP turns scattered QA output into an actionable review queue. Its value is
clarity and consistency, not new plotting capability.

In scope:

- a versioned readiness report contract;
- normalization adapters for live FigOps evidence;
- deterministic JSON and Markdown reports;
- a CLI evaluation path for an existing persisted render-job manifest;
- a read-only `figops.evaluate_publication_readiness` MCP tool;
- stable finding codes, evidence references, and recommended actions.

Explicitly out of scope:

- human approval or reviewer identity storage;
- `approved` or `stale` states;
- approval invalidation or subject digests;
- Figure Pack, submission bundles, or checksum manifests;
- automatic remediation;
- publisher acceptance guarantees;
- new `graphhub.*` compatibility aliases;
- changes to existing evidence producer schemas.

Approval, stale-state tracking, and Figure Pack generation require separate
usage evidence and a later specification.

## Public Contract

The report schema is `publication_readiness/1`. At minimum it contains:

```json
{
  "schema_version": "publication_readiness/1",
  "readiness_status": "needs_review",
  "project_id": "01_Project",
  "figure_id": "Fig2b",
  "target_format": "nature",
  "gates": [],
  "findings": [],
  "manual_review_required": true
}
```

Every gate records a stable code, outcome, source schema, and evidence
reference. Every actionable finding records a stable code, severity, source,
message, optional affected panel, and recommended action. Reports must not
contain absolute local paths, secrets, or raw private-data values.

State precedence is strict:

1. Missing, malformed, unsupported-version, unknown, or `passed=null`
   required evidence produces `blocked`.
2. Any failed hard gate produces `blocked`.
3. Otherwise, any major actionable finding produces `needs_revision`.
4. Otherwise, the result is `needs_review`.

Warnings that are explicitly advisory remain findings but do not promote a
clean result to `needs_revision`. The contract receipt created in Wave 0 must
map each live diagnostic code to hard, major, or advisory before implementation
begins. Unknown codes are never silently downgraded.

## Deterministic Reporting

JSON and Markdown are rendered from one normalized result. Deterministic
content uses sorted keys, compact canonical JSON, UTF-8, POSIX relative paths,
and LF line endings. Absolute paths, filesystem mtimes, locale-formatted
numbers, and evaluation timestamps are excluded from byte-stable content.

If operational metadata such as an evaluation time is later required, it must
be separated from the deterministic payload and must not change readiness
semantics or golden report comparisons.

The Markdown report presents the same state, gates, findings, and actions as the
JSON. It may improve layout but must not introduce requirements absent from the
JSON source.

## CLI And MCP

The CLI adds an additive evaluation path while preserving existing commands.
It reads a persisted render-job manifest directly and writes no report file:

```powershell
python orchestrator.py --readiness-manifest <FILE> --readiness-format json
python orchestrator.py --readiness-manifest <FILE> --readiness-format markdown
```

`--readiness-format` accepts exactly `json` or `markdown`, and the selected
representation is emitted to stdout. The manifest must contain the complete
render evidence required by the contract; unknown or unsupported evidence
blocks evaluation.

Exit codes:

- `0`: `needs_review`;
- `2`: `needs_revision`;
- `1`: `blocked`, invalid input, or internal failure.

MCP adds only:

```text
figops.evaluate_publication_readiness
```

The tool accepts `job_id`, is read-only, and remains available when MCP write
tools are disabled. It resolves the persisted job manifest through the existing
safe runtime-manifest lookup rather than accepting an arbitrary filesystem
path. It uses current runtime-root, symlink, schema, structured-error, and
redaction policies. It returns the same readiness semantics as the CLI. The
existing 13 legacy aliases remain unchanged, and no new `graphhub.*` alias is
added.

## Workflow Architecture

The implementation has four separable layers:

1. Evidence adapters read existing producer outputs and normalize them without
   importing CLI or MCP transports.
2. A pure evaluator applies the state table and creates stable gate/finding
   records.
3. JSON and Markdown renderers serialize the same domain result.
4. The CLI reads an explicitly named persisted render manifest, while MCP
   resolves `job_id` through the existing safe runtime lookup; both call the
   shared domain interface.

The domain layer must not import MCP modules. CLI and MCP must not implement
their own policy tables. Existing producer schemas remain authoritative; an
adapter must report unsupported evidence instead of guessing.

## Team Execution Model

Work proceeds in gated waves with at most three active agents and no overlapping
file ownership:

1. **Contract lock:** a Deep contract architect inventories live producers
   while a Deep threat reviewer challenges fail-closed behavior and scope.
2. **Domain:** a Standard implementer builds normalization, the pure evaluator,
   and deterministic reports.
3. **Surfaces:** Standard CLI and Deep MCP workers run in parallel after the
   domain interface is stable.
4. **Verification:** a read-only Deep verifier attempts to refute state,
   determinism, containment, compatibility, and scope claims.

Each wave emits a receipt with changed files, public-contract changes, tests,
risks, and open decisions. A subsequent wave starts only when the prior receipt
parses, required evidence exists, tests pass, and open decisions are empty.

## Safety And Risk Gates

Default behavior is to stop rather than widen scope when a slice would require:

- changing existing producer schemas or compatibility aliases;
- adding or locking a dependency;
- widening allowed roots or enabling MCP writes;
- reading secrets or private external data;
- implementing approval, stale-state, or Figure Pack behavior;
- tagging, publishing, deploying, or sending external messages.

All such changes require a separate explicit approval. Evaluation must fail
closed on escaping paths, symlinks, malformed JSON, duplicate keys, unknown
schema versions, truncated evidence, and unavailable required checks.

## Evaluation Fixtures

The minimum fixture matrix covers:

- every state-precedence branch;
- missing, malformed, unsupported-version, unknown, and `passed=null` evidence;
- hard-gate failure, major finding, advisory-only finding, and clean evidence;
- shuffled JSON keys, Windows/POSIX separators, CRLF/LF, locale, and timezone;
- absolute-path and secret redaction;
- escaping path and symlink attempts;
- an identical persisted render-job manifest through CLI and MCP;
- MCP evaluation with write tools disabled;
- repository search proving approval, stale-state, and Figure Pack surfaces were
  not added.

Golden JSON must be byte-stable. Golden Markdown must be content-stable and
semantically identical to JSON.

## Acceptance And Release Gates

The MVP is complete when:

- exactly three public states exist and `needs_review` always retains
  `manual_review_required=true`;
- no missing or unknown required evidence can produce `needs_review`;
- CLI and MCP return identical states, gates, and finding codes for the same
  normalized evidence;
- deterministic fixtures reproduce across supported Windows and macOS CI;
- MCP containment, symlink, read-only, and redaction tests pass with zero
  security skips;
- existing CLI and MCP compatibility suites remain green;
- generated MCP schemas and documentation have no drift;
- locked Ruff and full pytest pass;
- no approval, stale-state, or Figure Pack implementation appears in the public
  surface.

Release tagging and package publishing are not part of this workflow. The run
ends with local implementation, test evidence, and an independent verification
receipt.

## First Runnable Wave

Before code changes, two read-only slices inventory live evidence producers and
challenge the decision/threat model. Their fan-in artifact is
`publication-readiness-contract.receipt.json` with:

- `evidence_map`;
- `state_precedence`;
- `finding_codes`;
- `serialization_contract`;
- an empty `open_decisions` array.

Only after that receipt is verified may the domain implementation begin.
