# FigOps AI-Native Figure Integrity Plan

**Status:** canonical successor plan; implementation has not started.

**Date:** 2026-07-20

**Contract targets:** `figops-human-review/1` and `figops-promotion-gate/1`
**Baseline:** `v0.20.0` is published on PyPI and as a GitHub Release. This plan
governs a later additive increment; it does not reopen or relabel that release.

## 1. Authority and relationship to current release work

This is the single source of truth for the next integrity increment: a closed
human-review/signoff receipt, a promotion gate that consumes it, one policy
resolution path, and the associated workflow and release governance. It is an
additive successor, not a rewrite of the published-release corrective work.

The [2026-07-15 project-structure and runtime-integrity plan](2026-07-15-project-structure-runtime-integrity-plan.md)
is the historical corrective baseline for PR #224 and the published `v0.20.0`
release. Its role contract, runtime/result boundary, durable receipts, raw
integrity, copy-only organization, acceptance matrix, and release-gate evidence
remain binding foundation facts. This plan does not weaken, duplicate, or move
those requirements.

The [architecture inventory](../architecture.md) and [roadmap](../ROADMAP.md)
contain the contemporaneous `v0.20.0` release-candidate implementation record;
their historical status wording does not supersede the published-release fact
above. The earlier [AI-native rearchitecture plan](2026-07-14-ai-native-figops-rearchitecture.md)
remains implemented context for bounded evidence, previews, policy projections,
and the v2/compatibility surface. Where those documents describe a current
implementation, they are evidence for this plan; where this plan specifies a
future approval lifecycle, this plan controls that new scope.

The governing rule is:

> Tools prove bounded facts and enforce declared boundaries. Models assemble
> evidence and propose work. A named accountable human alone accepts the
> scientific and communicative claim; promotion records that acceptance but
> never manufactures it.

## 2. Purpose and success condition

FigOps must remain useful to an AI-native research workflow without converting
an LLM's persuasive summary, a green renderer, or `manual_review_needed=false`
into a false publication claim. The target state is a reproducible, reviewable
chain from declared source data and scripts through a rendered artifact to an
explicit, revocable human decision that is bound to exactly those bytes and
their evidence.

At completion, a protected publication promotion is possible only when all of
the following are true:

1. Existing structural, provenance, claim, policy, and no-replace promotion
   invariants pass.
2. The candidate has a closed, schema-valid review receipt whose subject digest
   recomputes from the exact durable artifact and referenced evidence.
3. The receipt is an affirmative decision by an authorized human reviewer for
   the requested decision scope, has not expired or been superseded, and
   records no unresolved required concerns.
4. A single deterministic promotion-gate evaluator records every satisfied,
   failed, unavailable, and explicitly waived gate before the existing durable
   promotion primitive is invoked.

This is evidence of a FigOps-controlled promotion decision, not a guarantee of
scientific truth, ethical approval, co-author consent, institutional approval,
or publisher acceptance.

## 3. Responsibility boundary

The terms **tool**, **LLM**, and **human** identify responsibility, not a
particular process. An LLM may be used by a human; it must still not be credited
as the accountable reviewer. A tool may make a deterministic recommendation;
it must still not claim scientific approval.

| Decision area | Tool/kernel responsibility | LLM responsibility | Human responsibility |
|---|---|---|---|
| Inputs and execution | Contain paths; preserve raw identity; prefetch/verify authorized external raw; execute declared producers; hash inputs, scripts, config, environment, and outputs | Propose input mapping and run plan; explain failures | Confirm data selection is scientifically appropriate and authorized |
| Figure construction | Enforce declared I/O, timeouts, format facts, policy measurement, and immutable candidate identity | Select encodings; author/revise code; inspect bounded previews; propose targeted changes | Decide whether the figure communicates the intended result honestly |
| Evidence | Produce/recompute facts, typed lineage, policy projections, and durable receipts; reject missing or malformed evidence | Correlate evidence; identify uncertainty; prepare a review brief; never fill missing evidence by inference | Assess whether evidence supports the scientific claim and whether caveats are adequate |
| Policy | Resolve versioned policy inputs deterministically and disclose defaults, inheritance, and opt-outs | Recommend a policy only when supplied constraints support it | Choose lab/venue policy and approve a justified scoped exception where policy permits |
| Review and release | Verify review-receipt closure, subject binding, expiry/revocation, and gate precedence; perform no-replace promotion | Request review and summarize what changed; never self-sign or assert approval | Record the decision, identity/role assertion, scope, concerns, and authorization to promote or decline |

### 3.1 Three classes of conclusions

1. **Enforceable invariants** are binary system promises. They include
   containment, role resolution, raw/source identity, artifact hashes,
   schema validity, declared producer/output binding, runtime/result
   disjointness, no-replace promotion, receipt closure, review subject digest,
   signature/identity verification when configured, and gate precedence. A
   missing, malformed, stale, or unverifiable invariant fails closed.
2. **Assistive evidence** is objective but incomplete information: visual
   preflight, geometry diagnostics, regression deltas, policy measurements,
   claim-inventory candidates, bounded previews, and LLM-written review briefs.
   It may request revision or review. It cannot become an approval solely by
   aggregation, confidence score, or absence of warnings.
3. **Human scientific judgement** covers causal interpretation, statistical
   appropriateness in context, claim strength, visual honesty, accessibility
   tradeoffs, authorship/consent, ethical or legal obligations, venue fit, and
   submission. FigOps records an explicit decision about this judgement; it
   neither computes nor substitutes for it.

`needs_review` remains a queue state, not approval. `manual_review_needed=false`
means only that its producing checks did not request manual review; it is never
a signoff, a publishability verdict, or a bypass of an explicit review policy.

## 4. Canonical research object model

The human-facing project model is intentionally simple; declared roles, not
directory spelling or file extension, give it meaning.

```text
project/
├─ raw/                 immutable or externally governed scientific inputs
├─ hub_scripts/         tracked analysis, figure, and shared source
├─ results/             durable derived data, tables, figures, evidence, publication
└─ (external runtime)   jobs, snapshots, cache, logs, manifests, previews, temp
```

`raw`, `hub_scripts`, and `results` retain the `figops-project-v1.1` role
semantics specified by the 2026-07-15 SSOT. `runtime.*` remains external,
disposable, and path-disjoint from project and durable result roots. A runtime
manifest is operational evidence; a receipt is a compact durable projection.
No review receipt may embed a runtime path, raw data content, secret, or preview
blob. It may refer only to allow-listed durable logical IDs, content hashes,
policy IDs/versions, opaque manifest IDs, and compact evidence digests.

The new review receipt is a `result.evidence` artifact. It does not replace the
existing durable lineage receipt:

| Record | Owner and lifetime | Purpose |
|---|---|---|
| Runtime manifest | runtime; disposable | Detailed execution, diagnostics, logs, and preview references |
| Durable lineage receipt | `results/evidence`; durable | Binds raw/scripts/config/environment/input/output/claim lineage while remaining independent of runtime deletion |
| Human review receipt | `results/evidence`; durable and append-only | Binds a human decision to a candidate subject digest and the reviewed evidence set |
| Promotion-gate receipt | `results/evidence` and, when promoted, publication bundle; durable | Records deterministic admission/denial from the candidate, policy, lineage, and human review receipt |
| Publication bundle | `results/publication`; immutable after promotion | Frozen promoted figure(s) plus the minimum verified receipts and manifest |

An existing result figure can remain reviewable without a signoff. It becomes
**promotion eligible** only through the existing machine eligibility plus the
new gate when the selected policy requires human signoff. It becomes
**promoted** only after the gate receipt and existing native no-replace
publication mechanism succeed. These terms are deliberately not synonyms for
scientific correctness or publisher acceptance.

## 5. Ranked gap register

This register records the observed delta from the published `v0.20.0` baseline,
not an assertion that current controls are absent. Existing safeguards named in
the evidence column are retained.

| Rank | Gap | Why it matters | Current evidence/control | Required resolution |
|---:|---|---|---|---|
| P0 | No closed human review/signoff receipt or subject-bound approval lifecycle | A future promotion surface could mistake readiness or a model statement for approval | `publication_readiness/1` ends at `needs_review`; `artifact_audit` is explicitly non-approving | Add a closed review receipt, verifier, revocation/supersession semantics, and mandatory gate consumption |
| P0 | Existing result promotion admits machine-eligible project renders before an explicit review-policy gate | Machine eligibility is necessary but cannot represent human scientific acceptance | `hub_core/result_promotion.py` checks claim/policy/manifest eligibility and writes durable lineage receipt | Put a fail-closed promotion-gate admission boundary before promotion; keep the existing primitive unchanged |
| P1 | Policy resolution is distributed across render selection, artifact measurement, research-ops evidence, and readiness | Defaults, inheritances, and opt-outs can become inconsistent or impossible to audit as one decision | `artifact_policy_measurement.py`, `provenance_inputs.py`, and evidence `resolved_policy` snapshots | Add one canonical resolver/provenance model; migrate callers through compatibility adapters |
| P1 | No first-class distinction between exploratory artifacts and execution candidates | Draft work can be over-read as reproducible or promotable | Runtime boundary, durable receipt, and read-only readiness already distinguish evidence availability | Add declared workflow intent/state and promote only execution candidates with complete evidence |
| P1 | Review scope, reviewer authority, and conflict/exception handling are not encoded | A generic yes/no comment cannot establish what was reviewed or whether a waiver is authorized | Existing `manual_review_needed` and readiness findings surface uncertainty | Specify narrow decision scopes, role assertions, concern disposition, and policy-governed exception receipts |
| P2 | Legacy projects are readable/render-disabled but have no migration path into signoff-gated promotion | Forcing a schema upgrade would damage compatibility; silently exempting them would weaken trust | `legacy_structure_resolver.py`; legacy render refusal in CLI/MCP | Preserve legacy behavior; require explicit v1.1 migration plus fresh execution for new promotion workflows |
| P2 | CI proves code behavior but does not yet run approval-lifecycle or stale-review adversarial matrices | A new human-facing state machine needs resistance to replay, tampering, expiry, and profile drift | Current CI gates platform containment, actual-R, tests, Ruff; release discipline checks exist | Add deterministic lifecycle tests and release evidence gates without expanding ordinary PR workload unnecessarily |
| P3 | AI review briefs lack a stable non-authoritative exchange contract | Useful summaries can obscure missing evidence or sound like an approval | Bounded previews/evidence and non-approval language are present | Define an optional, redacted review-brief schema that tools label as assistive only |

P0 blocks any release that exposes signoff-gated promotion. P1 blocks the
default-on policy or execution workflow. P2 may ship only with an explicit
owner and compatibility evidence. P3 is not a prerequisite for the core gate.

## 6. Target architecture

### 6.1 Closed human review receipt

`figops-human-review/1` is a closed, canonical JSON DTO. Unknown keys,
duplicate JSON keys, non-finite values, absolute paths, raw values, runtime
paths, and mutable external references are rejected. It is an append-only
evidence record; corrections create a new receipt that explicitly supersedes an
older receipt. No mutation in place is allowed.

The minimum receipt shape is conceptually:

```json
{
  "schema_version": "figops-human-review/1",
  "receipt_id": "review:sha256:...",
  "decision": "approve_for_promotion",
  "decision_scope": "figure_scientific_and_communication",
  "subject": {
    "project_id": "opaque-project-id",
    "artifact_id": "result.figure:...",
    "artifact_sha256": "...",
    "lineage_receipt_sha256": "...",
    "evidence_digest": "...",
    "resolved_policy_digest": "...",
    "subject_digest": "..."
  },
  "reviewer": {
    "principal_id": "configured-opaque-id",
    "role": "scientific_reviewer",
    "authority_assertion": "lab-policy/1"
  },
  "reviewed_at": "2026-07-20T00:00:00Z",
  "expires_at": "2026-10-18T00:00:00Z",
  "concerns": [],
  "waivers": [],
  "supersedes": null,
  "integrity": {"canonical_sha256": "..."}
}
```

The concrete schema may add allow-listed fields only through a schema-version
change. Its canonicalization is fixed, not left to an implementation:

1. Parse UTF-8 without a BOM; reject duplicate object keys, non-finite numbers,
   unsupported JSON values, and text that is not Unicode NFC. Normalize every
   accepted string to Unicode NFC before validation. Times are RFC 3339 UTC with
   a `Z` suffix and seconds precision. SHA-256 strings are lowercase hexadecimal.
2. Form the **review payload** by removing exactly the top-level `receipt_id`
   and top-level `integrity` members. Validate the remaining closed DTO,
   including its nested objects and ordered arrays, before hashing it.
3. Serialize that payload as UTF-8 JSON with lexicographically sorted object
   keys by Unicode code point, compact separators `,` and `:`, no insignificant
   whitespace, no escaping of non-ASCII characters, and no trailing newline.
   Array order is semantic and is never sorted. Let `D` be the lowercase
   SHA-256 digest of these bytes.
4. Require `receipt_id` to be exactly `review:sha256:<D>` and `integrity` to be
   exactly `{ "canonical_sha256": "<D>" }` after canonical JSON parsing. The
   two fields are derived witnesses of the same payload, not independent input.
5. Any local attestation or future signature signs the review-payload bytes
   from step 3. It is stored outside the receipt payload or in a separately
   versioned, non-self-signed envelope. A verifier recomputes `D` before it
   considers the attestation.

This makes the self-reference rule exact: neither `receipt_id` nor
`integrity.canonical_sha256` participates in `D`; all scientific, policy,
reviewer, scope, concern, waiver, expiry, and supersession content does.

The receipt must also define these exact semantics:

- Decisions are `approve_for_promotion`, `request_revision`, or `decline`;
  only the first can satisfy a signoff-required gate.
- A receipt has one immutable subject digest. It binds the durable artifact
  SHA-256, durable lineage receipt digest, normalized evidence digest, resolved
  policy digest, project/figure logical identity, and decision scope. Any
  changed input produces a different subject and requires a fresh review.
- Reviewer identity is a verified principal when an organization identity
  provider is configured; otherwise it is a clearly labeled local attestation.
  A local attestation can satisfy only policies that explicitly allow it. Free
  text names alone are not an authorization mechanism.
- `authority_assertion` names the policy/role binding that permits the recorded
  scope. It is a verifiable policy fact, not an LLM-produced label.
- Concerns are closed typed records. Each is resolved, waived by an authorized
  exception, or blocks approval. A waiver contains policy rule, rationale,
  authorized principal/role, subject digest, and expiry. A waiver never
  suppresses an invariant, a P0/P1 security failure, or a required scientific
  signoff.
- Revocation and supersession are durable, append-only records. A revoked,
  expired, non-current, malformed, or mismatched receipt cannot pass the gate.
  The first delivery may support supersession by local receipt index; remote
  revocation synchronization is an optional later integration, not an assumed
  capability.
- The tool verifies receipt closure, `D`, and the applicable attestation before
  use. A verifier never trusts a supplied `receipt_id` or integrity digest.

The receipt records an accountable decision but intentionally cannot prove the
reviewer actually looked at pixels, understood the experiment, had all required
coauthor consent, or satisfied an external journal process. Those remain human
and organizational responsibilities.

### 6.2 Deterministic promotion gate

`figops-promotion-gate/1` is a pure domain evaluator plus a narrow admission
integration. Its inputs are: declared workflow intent, candidate artifact and
hash, existing verified runtime manifest/evidence, existing durable lineage
receipt, canonical resolved policy, optional valid review receipt, and requested
destination. The pure evaluator returns a complete stable list of gates and
exactly one of: `blocked`, `needs_revision`, `needs_review`, or `eligible`.

Precedence is fixed:

1. malformed, missing, untrusted, escaped, stale, or mismatched evidence;
   failed invariant; invalid policy; or invalid receipt => `blocked`;
2. failed required automated or unresolved non-waivable finding =>
   `needs_revision`;
3. selected policy requires signoff and no matching current affirmative receipt
   exists => `needs_review`;
4. all required gates and required signoff pass => `eligible`.

The gate does not copy artifacts, modify reviews, or infer waivers. The
integration calls the current `result_promotion`/`durable_promotion` path only
after the pure gate emits `eligible`; it then persists a promotion-gate receipt
whose subject and evidence digests match the reviewed candidate. The promotion
operation, not the evaluator, may report `promoted` only after the existing
native no-replace durable promotion returns success. A failed or raced
destination is never presented as promoted.

### 6.3 Central policy resolution and opt-outs

All policy decisions must flow through a single domain resolver. The proposed
new `hub_core/policy_resolution.py` owns a versioned `ResolvedPolicySet` with
one canonical digest. It evaluates inputs in this decreasing authority order:

1. immutable kernel invariants (not opt-out capable);
2. trusted launcher/operator policy;
3. repository/lab policy, when configured and verified;
4. declared project policy;
5. explicit per-render/per-promotion selection.

This order is executable rather than advisory. Every shipped policy parameter
declares one merge operator in its schema: `require` (boolean OR), `minimum`
(numeric maximum), `maximum` (numeric minimum), `allowed_set` (set
intersection), `exact` (all specified values must be equal), or `selection`
(the requested value must belong to the intersection of allowed values). The
resolver rejects an unknown parameter or operator. It accumulates constraints
from every applicable layer; an empty intersection, an impossible numeric range,
an unequal `exact` value, a non-membership selection, or a type/version mismatch
is `POLICY_CONFLICT` and blocks execution/promotion. It never chooses a winner
by source order.

An opt-out is a typed request only for a parameter whose schema declares
`opt_out_allowed=true`. It resolves to disabled only when no higher layer emits
`require=true` for that parameter and no applicable `minimum`, `maximum`,
`allowed_set`, or `exact` constraint is violated. Exceptions and waivers do not
participate in policy resolution and cannot change a resolved parameter value.
They are instead gate inputs: an exception must name one emitted policy finding
code, the exact candidate subject digest, an authorized principal/role,
rationale, and expiry; the gate accepts it only when that finding's parameter
schema declares `waivable=true`. Kernel-invariant parameters declare both
`opt_out_allowed=false` and `waivable=false`.

The resolved output lists every candidate constraint and records `value`,
`merge_operator`, `source`, `policy_id`, `version`, `opt_out_requested`, and
`opt_out_accepted`. It is canonicalized with the same JSON rules stated for
review payloads, except it has no derived receipt fields; its SHA-256 is the
policy-set digest. Ambiguity, unknown policy versions, or an invalid policy
source therefore fail closed.

Existing module defaults and explicit `false` research-ops opt-outs remain
backward compatible. They migrate as explicit resolved facts, preserving the
current source distinctions (for example `module-default`, `project_config`,
and `explicit_project_opt_out` where already emitted). The following are never
opt-out capable: path containment, raw/producer verification where selected,
schema/receipt integrity, no-replace promotion, runtime/result disjointness,
or a human signoff demanded by the resolved promotion policy. A policy may
choose that a class of exploratory result does not require signoff, but it must
say so explicitly and it cannot call that result promoted or publication-ready.

During migration, the existing singular evidence `resolved_policy` field stays
readable. It becomes a compatibility projection of the canonical policy set for
render-policy consumers; it must not be duplicated under competing names.

### 6.4 Exploration versus execution

The workflow has explicit intent rather than accidental status inferred from a
directory:

| Mode | Permitted work | Required evidence | Promotion meaning |
|---|---|---|---|
| `exploration` | Inspect data, author scripts, render drafts, revise from bounded previews, use advisory diagnostics | Containment and safe render evidence; incomplete provenance is surfaced, not invented | Never eligible or promotable; no signoff is requested as a substitute for missing execution evidence |
| `execution` | Run declared project producer against declared inputs under the role/runtime contract | Complete required provenance, claim/measurement policy evidence, candidate identity, and durable lineage receipt | May become `needs_review`, `eligible`, then `promoted` only through the full gate |
| `review` | Read exact candidate/evidence, record decision/concerns/waivers | Closed review receipt bound to an execution candidate | Cannot alter candidate bytes or evidence; a new candidate requires a new review |
| `promotion` | Evaluate admission and invoke existing no-replace result publication | Passed deterministic gate and, where required, current signoff receipt | Produces immutable publication bundle and promotion receipt, or fails without replacement |

Exploration may produce durable draft outputs if the current result contract
allows them, but the workflow marks them `non_promotable` and preserves that
fact in the evidence. Execution does not make a figure scientifically correct;
it makes it a well-bound candidate for review.

For compatibility, workflow intent resolves by the operation rather than by a
silent global default:

| Existing path without `workflow.intent` | Resolved intent | Source and effect |
|---|---|---|
| `orchestrator.py --project ... --step all`, `analysis`, or `plot` on an active project | `execution` | `compatibility-project-execution`; preserves the current declared project-pipeline behavior and remains subject to all current evidence gates |
| MCP `figops.render_project_script` or `figops.render_project_figure` on an active project | `execution` | `compatibility-project-execution`; preserves current project-render and machine-promotion eligibility behavior until a selected policy requires the new review gate |
| MCP one-call render paths (`figops.render_basic_csv`, `figops.render_csv_graph`, and `figops.render_csv_multipanel`), previews, and direct draft render helpers | `exploration` | `compatibility-direct-exploration`; output is non-promotable unless the caller moves to an explicit declared project execution |
| Read, inspect, audit, validation, and readiness paths | no execution intent | read-only; they create no candidate and cannot make a result promotable |
| `project.status: legacy` or an existing refused legacy render path | unchanged legacy behavior | rendering stays disabled where currently disabled; no compatibility intent bypass exists |

New scaffolded/configured projects must write `workflow.intent: execution`
explicitly. A caller may select `exploration` explicitly for a project draft,
but no direct-render or legacy compatibility route may select `execution` merely
by supplying a review receipt. Every resolved intent and its source enters the
policy/evidence projection.

### 6.5 Legacy behavior

`project.status: legacy` retains the existing render-disabled behavior. The
in-memory legacy structure resolver remains read-only. Legacy aliases and
compatibility defaults continue to behave as documented; no new aliases are
added solely for approval or promotion.

A legacy project cannot obtain a new signoff-gated publication promotion from
historical artifacts. The migration is explicit: adopt the v1.1 role contract,
declare policy/workflow intent, run a fresh contained execution, produce current
lineage/evidence, and review the resulting candidate. The migration never
moves, rewrites, or retroactively certifies legacy bytes. Read-only readiness
evaluation of legacy evidence stays available and reports its limits.

## 7. Phased work packages

Each package is a coherent change with a named owner and an independent review.
No package changes the published `v0.20.0` corrective baseline or its release
state. Module names below distinguish existing targets from planned new modules.

### Phase 0 — Contract lock and adversarial fixtures

**Goal:** freeze public semantics before a write surface exists.

- Record this plan's schema-closure decisions in a Phase 0 implementation
  receipt that explicitly references this SSOT, and add machine-readable
  fixtures under `tests/fixtures/figure_integrity/` (planned). The receipt
  carries evidence only; it does not become a competing authority.
- Inventory current producer and receipt shapes in existing
  `hub_core/evidence_contract.py`, `hub_core/durable_receipt.py`,
  `hub_core/result_promotion.py`, `hub_core/publication_readiness.py`, and
  `hub_core/provenance_inputs.py`; do not change producers in this phase.
- Establish fixture cases for canonicalization, duplicate keys, absolute paths,
  malformed SHA-256, stale/expired/withdrawn/superseded review, subject mismatch,
  policy drift, reviewer-role mismatch, replay to another figure, blocked
  waiver, and no-signoff exploratory results.

**Likely tests:** new `tests/test_human_review_receipt.py`, new
`tests/test_promotion_gate.py`, plus existing `tests/test_durable_receipt.py`,
`tests/test_evidence_contract.py`, `tests/test_claim_boundaries.py`, and
`tests/test_release_discipline.py`.

**Exit:** an approved schema/precedence fixture matrix exists; each field has an
owner, privacy classification, and canonicalization rule; no runtime path or
approval claim can enter an existing receipt accidentally.

### Phase 1 — Closed review receipt domain

**Goal:** implement and verify `figops-human-review/1` without promotion writes.

- Add planned `hub_core/human_review_receipt.py` for DTO construction,
  canonical bytes/digest, strict parsing, subject binding, expiry, concern,
  supersession, and revocation-index validation.
- Add planned `hub_core/human_review_identity.py` for a minimal verifier
  interface. The first implementation supports a local policy-controlled
  attestation and a test verifier; it must not silently claim federated identity
  verification.
- Reuse `hub_core/durable_receipt.py` opaque-ID/redaction discipline and
  `hub_core/evidence_contract.py` closed-envelope validation rather than
  serializing arbitrary mappings.
- Add a read-only review inspection surface only after the domain contract is
  stable, likely through existing `hub_core/mcp/tools/readiness_tools.py` and
  `hub_core/mcp/schemas.py`; do not add a `graphhub.*` alias.

**Likely tests:** new receipt tests above; existing
`tests/test_mcp_publication_readiness.py`, `tests/test_mcp_preview_resources.py`,
`tests/test_workflow_security.py`, and `tests/test_claim_boundaries.py` for
non-approval wording.

**Exit:** receipt validation rejects all hostile fixtures; subject digest
recomputes; a clean automatic readiness report cannot be transformed into an
approval; no write tool or promotion behavior changes.

### Phase 2 — Canonical policy resolver and workflow intent

**Goal:** make policy selection and allowed opt-outs explainable from one
digestible source.

- Add planned `hub_core/policy_resolution.py` and
  `hub_core/workflow_intent.py`; provide a compatibility adapter for existing
  `resolved_policy` evidence.
- Refactor only through focused callers: existing
  `hub_core/artifact_policy_measurement.py`, `hub_core/render_evidence.py`,
  `hub_core/provenance_inputs.py`, `hub_core/research_ops_enforcement.py`,
  `hub_core/publication_readiness.py`, and
  `hub_core/mcp/tools/render_project.py`.
- Extend `project_config_template.yaml` and
  `hub_core/templates/project_config_template.yaml` together after the resolver
  contract is locked. Preserve existing module defaults and `false` opt-outs.
- Teach `hub_core/config_parser.py` validation and migration to recognize the
  additive workflow/policy fields. Unknown future policy versions fail closed
  for execution/promotion but remain inspectable.

**Likely tests:** existing `tests/test_render_evidence.py`,
`tests/test_render_project_policy_integration.py`,
`tests/test_wp2_integrity_readiness.py`, `tests/test_evidence_contract.py`,
`tests/test_research_ops_render_gates.py`, `tests/test_config_placeholders.py`,
and new `tests/test_policy_resolution.py` / `tests/test_workflow_intent.py`.

**Exit:** all call paths emit equivalent policy decisions for equivalent input;
source and opt-out provenance are stable; exploration cannot be marked
promotable; no existing render/default behavior changes without an explicit
compatibility test.

### Phase 3 — Pure promotion-gate evaluator

**Goal:** decide eligibility deterministically without performing promotion.

- Add planned `hub_core/promotion_gate.py` and
  `hub_core/promotion_gate_receipt.py`.
- Consume, but do not reimplement, existing `hub_core/result_promotion.py`
  eligibility facts, `hub_core/publication_evidence.py` normalization,
  `hub_core/publication_readiness.py` state/finding evidence,
  `hub_core/claim_inventory.py`, `hub_core/calculation_evidence.py`, and
  `hub_core/durable_receipt.py`.
- Specify gate code ownership and stable precedence. The evaluator returns a
  deterministic report/receipt candidate and has no filesystem mutation API.
- Add a read-only evaluation route alongside existing publication readiness,
  likely in `hub_core/publication_cli.py`, `orchestrator.py`, and
  `hub_core/mcp/tools/readiness_tools.py`, once its public schema is reviewed.

**Likely tests:** new `tests/test_promotion_gate.py`; existing
`tests/test_publication_readiness.py`, `tests/test_publication_cli.py`,
`tests/test_mcp_publication_readiness.py`, `tests/test_result_promotion_integration.py`,
and `tests/test_calculation_evidence_lineage.py`.

**Exit:** the exact same inputs yield byte-stable gate reports through domain,
CLI, and MCP; invalid review/lineage/policy evidence blocks; `needs_review`
never becomes `eligible` without a valid required receipt.

### Phase 4 — Narrow signoff and promotion integration

**Goal:** expose an explicitly write-gated review-recording path and interpose
the gate before the existing durable promotion primitive.

- Add planned `hub_core/review_recording.py` to create append-only review
  records below the declared evidence role using the same contained/no-clobber
  standards as durable results.
- Integrate `hub_core/result_promotion.py` with `promotion_gate.py` only at its
  admission boundary. Keep `hub_core/durable_promotion.py` and
  `hub_core/atomic_no_clobber.py` as the only byte-publication primitives.
- Extend existing `hub_core/mcp/security.py`, `hub_core/mcp/schemas.py`, and
  focused handler modules under `hub_core/mcp/tools/` for deliberate write
  authorization. Read-only inspection stays available with writes disabled.
- Persist a promotion-gate receipt with the result and include it in the frozen
  publication bundle. Failures leave no competing destination overwritten and
  never backfill a review decision.

**Likely tests:** existing `tests/test_durable_promotion.py`,
`tests/test_result_promotion_integration.py`, `tests/test_mcp_write_gating.py`
(if present at implementation time; otherwise add it), `tests/test_workflow_security.py`,
`tests/test_symlink_policy.py`, `tests/test_structure_path_security.py`, and
new end-to-end lifecycle fixtures.

**Exit:** write-disabled MCP cannot record signoff or promote; a valid review
for a different hash cannot promote; concurrent destinations preserve the race
winner; runtime deletion leaves review and gate receipts verifiable; existing
non-review promotion behavior is unchanged until a policy explicitly selects
the new gate.

### Phase 5 — Migration, release governance, and operational dogfood

**Goal:** make the new lifecycle trustworthy in supported workflows without
making normal development CI perform expensive visual work.

- Publish migration examples for active v1.1 projects and a read-only legacy
  explanation. Add deprecation warnings only after compatibility evidence.
- Update generated tool references through the live registry process; preserve
  v2/compatibility surface counts unless an explicit release decision changes
  them.
- Extend `.github/workflows/ci.yml` with deterministic receipt/gate tests in
  existing gating jobs. Keep full render-pack/model visual dogfood manually
  dispatched, local, or path-filtered as [the roadmap](../ROADMAP.md) requires.
- Extend `tests/test_release_discipline.py`, `tests/test_public_release_check.py`,
  and packaging/release decision records with a gate that prevents a release
  from claiming signoff-gated promotion before lifecycle and platform witnesses
  exist.

**Exit:** migration and downgrade behavior are documented and tested; CI runs
the lifecycle adversarial matrix on supported platforms; release review has an
exact-commit, signed/attested human decision record where the selected release
policy requires one.

## 8. Compatibility and migration rules

1. The existing public evidence schemas, readiness states, role contract,
   `manual_review_needed`, `promotion_eligible`, CLI commands, and frozen MCP
   aliases remain readable. New fields and tools are additive during the first
   release that contains this work.
2. Existing `publication_readiness/1` retains exactly `blocked`,
   `needs_revision`, and `needs_review`. The promotion-gate state machine is a
   separate contract; it does not redefine readiness.
3. Existing `result_promotion` callers retain their current machine eligibility
   behavior until a selected policy explicitly requires the new gate. A release
   must document when the default changes, provide a migration example, and
   preserve an explicit compatibility selection for at least two minor releases
   unless a security issue requires faster removal.
4. Existing research-ops `false` opt-outs remain honored only for their current
   scoped rules. Migration must not broaden them into a signoff or invariant
   bypass. The resolved policy records exactly why each default or opt-out was
   used.
5. Legacy projects remain read-only/disabled as specified in the 2026-07-15
   SSOT. No automatic folder move, receipt backfill, or retrospective approval
   occurs.
6. Receipt schemas are versioned and migratable for reading. A migration may
   normalize/annotate legacy data but cannot invent a reviewer, signature,
   affirmative decision, expiry, or missing subject binding.

## 9. Non-goals

- Automatic scientific approval, authorship attribution, coauthor consent,
  IRB/ethics determination, legal review, or publisher acceptance.
- An arbitrary-code API, a broad external identity/SSO integration, a hosted
  approval service, blockchain/notarization, or remote approval synchronization
  in the first implementation.
- Replacing the `figops-project-v1.1` structure contract, external runtime
  boundary, native no-replace promotion primitive, durable lineage receipt, or
  current v2/legacy MCP compatibility policy.
- Treating an LLM visual inspection, a model score, a preview read, or a
  generated narrative as a human signoff.
- Silently changing scientific/visual policy defaults, mutating historical
  results, moving legacy projects, or adding a mandatory cloud provider/DVC.
- Running costly render packs, live-model evaluation, or external publication
  actions as an automatic result of ordinary source changes.

## 10. Acceptance criteria and release gates

### 10.1 Product acceptance

- A closed review receipt binds its decision to exact durable artifact,
  lineage/evidence/policy subject digests and fails verification on any mismatch.
- Unknown fields, duplicate keys, bad encoding, path/secret leaks, non-finite
  values, invalid hash/ID, stale receipts, replay, revoked/superseded receipt,
  unclosed concern, unauthorized reviewer role, and invalid waiver fail closed.
- A policy resolver emits one canonical policy-set digest and explains every
  applied default, inheritance, opt-out, and exception; immutable invariants
  cannot be disabled.
- Exploratory renders are visibly non-promotable. Execution candidates require
  complete current evidence before a review receipt can satisfy promotion.
- Readiness remains non-approving. An affirmative human receipt is insufficient
  if automatic invariants or required policy gates fail.
- The promotion gate evaluates identically through pure domain, CLI, and MCP
  surfaces. It does not mutate state; only the dedicated write-gated integration
  records receipts or calls promotion.
- A successful promotion uses the existing native no-replace path, writes
  durable lineage/review/gate receipts, and remains verifiable after runtime
  deletion. All failed paths preserve existing artifacts and do not create a
  false promoted state.
- Legacy and compatibility behaviors retain their documented read-only/default
  semantics and receive no invented approval.

### 10.2 CI and release gates

Before any release exposes signoff-gated promotion, all are required on the
exact release commit:

1. Locked full pytest and Ruff are green, including the current macOS path
   identity, Windows containment/symlink zero-skip, and actual-R gates required
   by the 2026-07-15 SSOT.
2. Receipt and promotion-gate fixture matrices pass on Windows and macOS, with
   zero skipped security/lifecycle cases. At minimum they cover tampering,
   stale/revoked/superseded state, role/authority mismatch, policy drift,
   cross-project/hash replay, write-disabled MCP, and no-replace race behavior.
3. Domain/CLI/MCP parity and deterministic canonical-byte/golden-report tests
   pass; generated schemas and tool documentation show no unreviewed drift.
4. Compatibility and legacy regression suites pass. A release note identifies
   every new default, migration step, and remaining policy-limited capability.
5. One operational dogfood run records a real execution candidate, bounded
   review evidence, an explicit human decision, and a successful or safely
   denied promotion. It is evidence of workflow operation, not a scientific or
   publisher acceptance claim.
6. Required repository, legal, and release approvals are recorded separately
   from figure-review receipts. The release process rechecks the technical gates
   on the exact commit and follows the `v0.20.0` corrective baseline's release
   discipline until its successor release policy is formally adopted.

## 11. Decision log and review questions

The following decisions are fixed for implementation unless a later dated SSOT
explicitly changes them:

- Automatic quality evidence is never human approval.
- Review is bound to immutable subject digests, not a filename, job ID, or
  mutable manifest path.
- Human approval records a limited decision scope; it does not claim universal
  scientific or publication truth.
- Kernel invariants are not waivable. Policy exceptions are narrow, attributable,
  expiring, and cannot convert missing evidence into a pass.
- Legacy artifacts are not retroactively approved.
- The existing durable promotion primitive remains the sole mechanism that can
  publish bytes into the protected result/publication destination.

Implementation must resolve the following before Phase 4 through an approved
Phase 0/1 receipt that explicitly points back to this SSOT: whether the first
supported human identity is local attestation only or a specific verified
identity provider; what review scopes/roles each shipped policy recognizes; the
default receipt expiry; and the operational owner of a local revocation index.
Until resolved, the system must expose read-only evaluation only and fail closed
for policies requiring verified signoff.
