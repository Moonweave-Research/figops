# FigOps Project Structure and Runtime Integrity Plan

**Status:** implementation, cross-platform CI, actual-R, and package gates are
green for source head `9e4d340b718529bd0f65ba46b2124dda718918a2`; repository
owner authorization for v0.20.0 is recorded in
[PR #224](https://github.com/Moonweave-Research/figops/pull/224#issuecomment-5016360221).
Merge, tag, and publication remain operational steps, and require a technical
gate recheck on the exact release commit before execution.

**Contract target:** `figops-project-v1.1`

**Release target:** PR #224 / `v0.20.0`; do not merge, tag, publish, or create a GitHub Release until every P1 gate below is green
**Date:** 2026-07-15

## 1. Purpose

FigOps must help an LLM organize and verify research work without replacing the
LLM's planning, interpretation, or visual judgment. The tool owns invariants the
model can easily miss: immutable inputs, declared roles, complete lineage,
reproducible outputs, publication minima, and a hard boundary between disposable
runtime state and durable research results.

This document is the single source of truth for the corrective work included in
PR #224 and `v0.20.0`. It replaces ad-hoc structure proposals for this work. For
the requirements, sequencing, and acceptance gates named here, this document
takes priority over `docs/architecture.md`, `docs/ROADMAP.md`,
`Research_Central_Architecture.md`, `task.md`, and the earlier AI-native plan.
Those documents remain authoritative outside this scope. Before PR #224 leaves
Draft, implementation agents update their current-state descriptions to point to
this document; after merge, `docs/architecture.md` and `docs/ROADMAP.md` become
the durable current-state summaries and retain a history link back here. No
second plan may restate or silently supersede these requirements.

The governing rule is:

> Runtime enables an execution and must be safely deletable. A result has
> research meaning and must remain explainable after runtime deletion.

## 2. Non-goals

- FigOps does not prescribe scientific interpretation, chart composition, a
  programming language, or a fixed number of revision passes.
- FigOps does not silently move existing projects into a preferred layout.
- Folder names are defaults, not meaning. Declared roles are the contract.
- Compatibility mode does not weaken integrity checks or expose internal names.
- This plan does not introduce DVC or make a cloud provider mandatory.

## 3. Priority and severity

| Severity | Meaning | Release effect |
|---|---|---|
| P0 | Data loss, trust-boundary escape, or false verified publication | Stop all mutation and release |
| P1 | Core promise can be bypassed or gives materially false assurance | Must be fixed before merge/release |
| P2 | Inconsistent behavior, incomplete UX, or avoidable migration risk | May follow only with an explicit issue and owner |
| P3 | Ergonomics or documentation improvement | Normal backlog |

This plan begins with seven P1 corrections. They are part of PR #224 and
`v0.20.0`, not deferred follow-up. Structure v1.1 work may proceed in parallel
only where file ownership does not overlap, but PR #224 may not merge and
`v0.20.0` may not be tagged or released while a P1 remains open.

## 4. Project role model

The human-facing model retains the useful three-way split—raw data, hub scripts,
and figures/results—while adding the derived-data boundary needed for honest
lineage.

```text
project/
├─ project_config.yaml
├─ raw/                         # immutable inputs or references
├─ hub_scripts/                 # tracked analysis and figure code
│  ├─ analysis/
│  ├─ figures/
│  └─ shared/
└─ results/                     # durable research outputs only
   ├─ data/
   │  ├─ intermediate/
   │  └─ source/
   ├─ tables/
   ├─ figures/
   ├─ evidence/                 # compact durable receipts
   └─ publication/              # validated promoted bundles
```

The canonical roles are:

| Role | Meaning | Mutability |
|---|---|---|
| `raw` | Irreplaceable or externally governed input | Read-only during a run |
| `script.analysis` | Code producing derived data/statistics | Tracked source |
| `script.figure` | Code producing visual outputs | Tracked source |
| `script.shared` | Reusable project code | Tracked source |
| `result.intermediate` | Reproducible analysis output | Replace atomically |
| `result.source_data` | Data directly supporting a table/figure | Replace atomically, retain for publication |
| `result.table` | Durable research table | Replace atomically |
| `result.figure` | Reviewable research figure | Replace atomically |
| `result.evidence` | Compact verified lineage receipt | Append/promote atomically |
| `result.publication` | Frozen, validated submission bundle | Immutable after promotion |
| `runtime.*` | Job state, cache, snapshot, log, preview, diagnostics, temp | Disposable |

Role, not extension, determines classification. A CSV may be raw, intermediate,
source data, or a table. An image may be a raw microscopy input, a reference, a
working figure, or a publication figure.

## 5. Runtime/result boundary

Runtime lives below the resolved external FigOps runtime root, never below the
project or `results/` tree:

```text
RESEARCH_HUB_RUNTIME_ROOT/
├─ jobs/
├─ snapshots/
├─ materialized/
├─ cache/
├─ logs/
├─ previews/
├─ diagnostics/
├─ manifests/
└─ temp/
```

### 5.1 Hard invariants

1. After symlink, junction, reparse-point, case, drive, and UNC normalization,
   the resolved runtime root is ancestor/descendant disjoint from the project
   root and every durable result root; equality or overlap is a fail-fast startup
   error. Durable roots remain inside the project and obey the role DAG and alias
   rules in section 6.1 rather than being pairwise disjoint from their project.
2. A final declared output resolving under a runtime root is invalid.
3. Runtime files may not be copied into `results/` merely to preserve execution
   detail; they must be reduced to a durable receipt.
4. Publication artifacts may not depend on runtime paths.
5. Deleting the runtime tree after success must not invalidate the durable
   lineage graph.
6. Logs, caches, previews, failure dumps, detailed job manifests, snapshots, and
   materialized cloud inputs are runtime, not results.
7. Inputs materialized for a run retain their source identity and hash; the
   materialized copy does not become raw data.
8. A runtime producer may compute bytes anywhere below runtime, but promotion
   first copies them to a uniquely named sibling staging path on the destination
   filesystem. FigOps fsyncs the staged file and its parent as supported, hashes
   the staged bytes against the producer output, and only then performs an atomic
   same-filesystem, no-replace namespace move into the declared result path.
   The move consumes the private stage name; a destination race winner is
   preserved, and platforms without a native no-replace move fail closed. Direct
   cross-volume "atomic" promotion is forbidden; cross-volume rename semantics
   must never be assumed.
9. Resolved paths must remain inside their declared role root after symlink,
   junction, and reparse-point resolution.
10. A durable artifact may refer to runtime only through an opaque manifest ID or
    a runtime-root-relative manifest ID. Absolute runtime paths, `file:` URIs,
    user-home paths, and runtime-root identities never enter durable output.

### 5.2 Runtime manifest versus durable receipt

The detailed runtime manifest may contain logs, diagnostics, environment detail,
job states, and preview references. It remains external and disposable.

The durable receipt stored under `results/evidence/` is produced through one
normalized DTO owned by WP0. The DTO accepts detailed runtime diagnostics and
emits a closed, versioned, allow-listed representation; callers may not serialize
runtime manifests directly. It contains only:

- schema and FigOps versions;
- run ID and timestamp;
- Git, config, script, environment-lock, input, and output SHA-256 values;
- declared role and logical artifact IDs;
- dependency edges from raw/script/config through derived data to outputs;
- statistical claim evidence references and calculation artifact hashes;
- policy profile and measured publication-minimum outcomes;
- an opaque or runtime-root-relative manifest identifier and SHA-256, explicitly
  marked optional for later inspection rather than required for reproduction.

No sample rows, secrets, absolute user-home paths, or restricted input contents
are included in a durable receipt.

Calculation artifacts are durable research artifacts, not disposable receipt
payloads. The calculation result itself is promoted as `result.source_data`,
`result.table`, or a dedicated typed `result.evidence` artifact. Its lineage
binds the producer script SHA, config SHA, every input artifact ID/SHA, every
output artifact ID/SHA, and the stable claim IDs it supports. A receipt hashes
that independently stored artifact; it never hashes itself or treats an evidence
JSON document as the calculation result merely because both share a schema.

## 6. `figops-project-v1.1` contract

Projects may declare role roots in `project_config.yaml`:

```yaml
structure:
  contract: figops-project-v1.1
  roots:
    raw: raw
    scripts: hub_scripts
    analysis_scripts: hub_scripts/analysis
    figure_scripts: hub_scripts/figures
    shared_scripts: hub_scripts/shared
    results: results
    intermediate: results/data/intermediate
    source_data: results/data/source
    tables: results/tables
    figures: results/figures
    evidence: results/evidence
    publication: results/publication
  discovery: declared_first
  undeclared_files: warn
```

### 6.1 Contract rules

- Every configured path is project-relative, normalized, and contained by the
  resolved project root.
- Role nesting follows the explicit DAG below; any edge not listed is forbidden:

  ```text
  project
  ├─ raw
  ├─ scripts ─┬─ analysis_scripts
  │           ├─ figure_scripts
  │           └─ shared_scripts
  └─ results ─┬─ intermediate
              ├─ source_data
              ├─ tables
              ├─ figures
              ├─ evidence
              └─ publication
  external runtime root                         # never in this DAG
  ```

- Alias matrix: `raw`, `scripts`, `results`, and `runtime` may never equal,
  contain, or be contained by one another. Leaf script roles may nest only under
  `scripts`; leaf result roles may nest only under `results`. Sibling leaves may
  not equal or contain one another. `publication` may contain its own frozen
  bundle copies but may not be an alias of `figures`, `source_data`, `tables`, or
  `evidence`. External descriptors do not grant a nesting exception.
- Runtime root is configured by trusted launcher/CLI/operator policy, never by a
  project-controlled `structure.roots` value.
- `declared_first` means explicit config and recorded provenance win over
  heuristics. Heuristics may propose, never silently decide.
- Undeclared files default to warning during exploration and fail only during
  publication if they are dependencies of a promoted artifact.
- The contract records logical roles; it does not require the default names.

### 6.2 Compatibility

- Projects without `structure.contract` retain current paths through a generated
  in-memory legacy mapping. No file moves occur.
- Legacy `results/data` maps to both intermediate and source-data discovery until
  the project explicitly separates them; publication must report this ambiguity.
- Existing config keys remain readable through at least the next minor release
  after `v0.20.0`; removal requires a later minor release, release-note notice,
  and a previously emitted actionable deprecation warning.
- Compatibility warnings include an actionable dry-run command and never change
  execution output solely because the project has an older layout.
- The v2 compact MCP surface remains compact. Structure inspection is initially
  exposed as a `figops.describe` kind; a separate read-only audit tool requires
  evidence that the response no longer fits that contract.
- Default v2 discovery exposes at most 8 tools after this work. Compatibility
  discovery is separately budgeted and may expose the documented legacy surface.
- Internal/private style identifiers remain unavailable from public schemas,
  documentation, and package artifacts.

### 6.3 External raw descriptors

Raw data outside the project is declared separately from role roots. A descriptor
contains a logical input ID, normalized path or URI, the trusted allowed-root ID,
source version/ETag when available, immutable SHA-256, and optional access class.
The project cannot widen allowed roots. Local descriptors must resolve beneath a
launcher-approved root; URI schemes require an enabled adapter. Materialization
records the descriptor identity and observed hash but never rewrites the
descriptor to a runtime path. Missing version/hash, an unapproved root, mutable
identity, or observed-hash mismatch fails before execution in strict/publication
mode.

```yaml
external_raw:
  - id: instrument-export-2026-07-15
    uri: gdrive://lab/exports/run-042.csv
    allowed_root: lab-exports
    version: "etag-or-source-version"
    sha256: "<64 lowercase hex characters>"
```

### 6.4 Contract-version resolution

- A config with no `structure.contract` is identified as legacy contract `1.0`.
- Loading `1.0` resolves an in-memory `1.1` view and advances only the in-memory
  effective-version field to `1.1`; it never rewrites the project file.
- The legacy resolver is a separate adapter module. The `1.1` parser does not
  accumulate aliases or conditionals for historical shapes.
- Diagnostics report both declared version (`1.0` when schema-less) and effective
  version (`1.1`) plus every inferred mapping.
- A reviewed migration may later write `1.1`, but normal execution, describe,
  validation, and dry-run discovery are read-only with respect to config files.

## 7. Organization workflow

Organization is a reviewable transaction, not an eager formatter.

1. **Discover read-only:** inventory files, config references, script imports,
   provenance, and existing outputs.
2. **Classify provisionally:** emit proposed role, reason, confidence, conflicts,
   and dependents for each item.
3. **Plan:** create a deterministic dry-run manifest containing source, proposed
   destination, expected hash, config edits, collisions, and unresolved items.
4. **Confirm:** require explicit user acceptance of role mappings and destination
   roots.
5. **Apply copy-only:** copy into a destination-filesystem sibling staging path,
   verify containment/hash, fsync as supported, then atomically move with native
   no-replace semantics. The move consumes the private stage and preserves any
   destination race winner; unsupported platforms fail closed.
   Never delete or move raw inputs.
6. **Rewrite declared references:** update config only when its original value and
   expected edit match the reviewed plan. Do not rewrite arbitrary script text.
7. **Verify:** run config, lineage, raw-integrity, pipeline smoke, and output-hash
   checks in the new structure.
8. **Report:** retain rollback manifest. Original cleanup is always a separate,
   user-authorized operation outside the organizer.

The normative finding-to-plan selection matrix and approval-token syntax live in
[`docs/project-structure-contract.md`](../project-structure-contract.md). In
summary, invalid, boundary-blocked, skipped, and audit-error projects are
report-only; ambiguous/heuristic unknowns and proposed mappings are
candidate-only; and only explicit reviewer-supplied `approved_mappings` plus
typed config edits enter a copy-only plan. A reviewed dry-run fixes a
deterministic `plan_digest` and `FIGOPS-APPLY-<plan_digest>` token. Apply must
repeat the identical reviewed inputs with that token and remains blocked by
stale identities, collisions, unresolved dependencies, or token mismatch.
The token proves integrity and exact replay of the canonical plan, not
independent reviewer identity, authority, or attestation; the compatibility
workflow does not close self-approval. A host-issued `approval_receipt` or
equivalent immutable reviewed-plan authority, bound to reviewer identity/role
and the plan digest and rooted in a host trust root, is specified by the Phase 6
contract below. A process-local implementation now exists: the exact
host-owned `ApprovalAuthorityRoot` mints immutable approval records, and secure
MCP normalization (`require_host_approval: true`) verifies the host receipt and
rechecks it at the mutation boundary.

The production `graphhub_mcp_server.py` launcher (also used by
`figops_mcp_server.py`) is the trusted injection boundary: it creates or receives
the host-owned process-local root, sets `require_host_approval: true`, and passes
the root through the constructor-only `host_authority_root` channel. Tool
arguments, project configuration, plan JSON, environment variables, runtime
manifests, and durable/evidence receipts cannot create, select, or replace that
root. An embedded host may opt into the same secure mode by supplying its own
host-owned root through that constructor-only channel together with
`require_host_approval: true`; if the secure flag/root are omitted, the embedded
constructor remains compatibility/token-only. The Phase 6 host-approval
gate is therefore satisfied for the production launcher; full release still
requires the remaining exact-commit gates below.
Audit reports, plans, digests, and tokens are control evidence, not runtime
manifests, durable results, or evidence receipts; runtime remains externally
rooted and disposable.

### Phase 6 host-rooted approval authority contract

Phase 6 is the normative authority boundary for structure migration. It closes
the self-approval gap without making the planner, an LLM, or a project file an
authority. Secure mode (`require_host_approval: true`) now enforces this
contract: missing/untrusted roots, missing or invalid receipts, stale/revoked
records, binding mismatches, and mutation-boundary revocation fail closed. The
default compatibility mode remains token-only for backward compatibility; its
valid plan and `FIGOPS-APPLY-<plan_digest>` token prove replay integrity only
and MUST NOT be described as independent approval or release evidence. The
production `graphhub_mcp_server.py`/`figops_mcp_server.py` launcher enables
secure mode with a host-owned process-local `ApprovalAuthorityRoot`, so the
Phase 6 host-approval gate is satisfied for that launcher. The compatibility
constructor/class remains token-only and cannot satisfy the Phase 6 or release
gate; full release still depends on the remaining exact-commit gates.

The following prove integrity, provenance, replay, or execution lineage, but do
**not** prove approval or reviewer authority: the `FIGOPS-APPLY-<plan_digest>`
token; any source/config/environment provenance; a copy, runtime, durable, or
evidence receipt; an audit report or plan; and any LLM-authored JSON field such
as `approved`, `reviewer`, or `authorization`. These values may be inputs to
review, but none can authorize mutation when presented by the planner, model,
project, or runtime filesystem.

#### Minimum canonical approval payload

The host approval is a canonical `figops_approval/1` payload. Its signed or
capability-bound bytes include every field below (empty lists are still hashed,
not omitted):

```json
{
  "schema": "figops_approval/1",
  "receipt_id": "<host-issued opaque id>",
  "plan_digest": "<sha256 of canonical reviewed plan>",
  "project_root_identity": "<launcher-resolved root identity digest>",
  "config_identity": {
    "relative_path": "project_config.yaml",
    "sha256": "<config bytes>"
  },
  "approved_mappings_digest": "<sha256 of canonical approved_mappings>",
  "config_diff_digest": "<sha256 of canonical typed config_diff>",
  "unresolved_digest": "<sha256 of canonical unresolved-reference list>",
  "reviewer": {
    "subject": "<host identity>",
    "role": "<host-authorized reviewer role>"
  },
  "issued_at": "<UTC timestamp>",
  "expires_at": "<UTC timestamp>",
  "currentness": {
    "state": "current",
    "checked_at": "<UTC timestamp>",
    "revocation_epoch": "<host value>"
  },
  "revocation": {
    "state": "not_revoked",
    "checked_at": "<UTC timestamp>"
  }
}
```

The canonicalization rules are deterministic (UTF-8 JSON, sorted object keys,
no insignificant whitespace, fixed digest encoding). `project_root_identity`
is derived from the launcher-resolved, normalized root and its stable filesystem
identity; it is not accepted from project configuration. `config_identity` is
the reviewed config path relative to that root plus its exact bytes; for a
config-less legacy project, an explicit `null` identity is bound into the plan
and cannot be supplied later by the model. The three
component digests bind the exact mappings, typed compare-and-swap config edits,
and unresolved-reference set used to compute `plan_digest`; changing order,
content, or even an empty-versus-omitted value changes the digest. Reviewer
subject and role are assertions only when the host trust policy authorizes them.
The process-local implementation stores the unresolved component as separate
digests for `hardcoded_unresolved_references` and `unresolved_proposals` (plus
the reviewed-entry digest); these are the concrete encoding of the minimum
`unresolved_digest` binding and are all rechecked.

The payload MUST be accompanied by one of these out-of-band authority proofs:

1. a host capability handle resolved and consumed through a launcher/host
   authority channel, with the host returning the canonical payload and its
   current, non-revoked status; or
2. a host signature over the canonical payload, verified against a
   launcher/operator-pinned trust root and key identifier (for example,
   `trust_root_id`, `key_id`, `algorithm`, and detached `signature`).

The current secure MCP implementation uses the first form through a
process-local `ApprovalAuthorityRoot`: the root object is supplied by the host
at server construction, cannot be copied, and is required by object identity
when `verify_approval_authority` checks an `approval_receipt_id`. The secure
`figops.normalize_project_structure` schema accepts only that opaque receipt
ID; self-described approval JSON is rejected. The default compatibility
constructor leaves `require_host_approval` false and therefore intentionally
retains token-only behavior; compatibility apply is not an independent approval
path and must not be presented as one.

Trust roots, capability validation, reviewer-role policy, revocation state, and
currentness are host/operator state. They MUST NOT be supplied by the LLM,
project config, plan JSON, runtime manifest, or a durable/evidence receipt. A
missing, unknown, malformed, expired, revoked, stale, or unverifiable proof
fails closed. An LLM response that contains the same JSON without a host proof
is untrusted data, even if it says `approved: true` or reproduces a valid token.

#### Apply ordering and revalidation

Apply performs these steps in order, with no file or config mutation before step
4 succeeds:

1. Parse the reviewed plan and host payload; reject non-canonical or
   self-described authority fields.
2. Recompute `plan_digest`, `approved_mappings_digest`, `config_diff_digest`,
   and `unresolved_digest`; verify the `FIGOPS-APPLY-<plan_digest>` token,
   project-root identity, config identity, containment, and all stale/collision
   and unresolved-dependency guards.
3. Verify the host capability or signature against the pinned trust root,
   enforce the reviewer role, and require `issued_at <= now < expires_at` plus
   host-confirmed current, non-revoked `receipt_id`/`revocation_epoch`.
4. Acquire the apply transaction lease and repeat the identity, digest, and
   host-currentness checks at the mutation boundary. A capability is consumed
   according to host policy; a revoked, expired, or otherwise changed approval
   aborts before staging.
5. Execute the existing copy-only transaction: destination-filesystem sibling
   staging, containment/hash verification, fsync where supported, native
   same-filesystem no-replace publication, and typed config CAS. Revalidate
   approval currentness before any subsequent mutation, then emit a copy
   receipt that records the approval `receipt_id` as lineage, never as a
   replacement for the approval proof.

#### Adversarial acceptance criteria

In secure MCP mode, a Phase 6 implementation must fail closed on the following
cases before any copy or config write. Compatibility mode may retain its
historical token-only behavior for backward compatibility, but it must expose no
host-approval status and must never describe that behavior as independent
approval or as satisfying the Phase 6/release gate.

| Adversarial input | Required result |
| --- | --- |
| Valid plan/token/provenance or durable/runtime/evidence receipt but no host proof | Secure mode rejects as unauthorised with no mutation; compatibility mode may follow its legacy token-only path but cannot claim approval. |
| LLM JSON containing `approved: true`, reviewer fields, or a forged receipt | Reject; model/project data is not an authority. |
| Signature over a payload whose plan, root, config, mappings, diff, unresolved set, reviewer, or validity window changed | Reject signature/digest mismatch. |
| Approval for another project root, config hash, plan digest, or mapping/diff/unresolved digest | Reject binding mismatch. |
| Unknown trust root/key, malformed capability, missing host policy, or unavailable authority channel | Reject and fail closed. |
| Expired, revoked, stale, non-current, or replayed one-time capability | Reject before staging; preserve all existing files. |
| Source/config identity, collision, unresolved dependency, or root containment changes after approval | Recompute and reject before mutation. |
| Revocation or expiry races after preflight | Mutation-boundary/currentness recheck aborts before the affected mutation. |

The focused adversarial suite MUST exercise each row with both CLI and MCP apply
surfaces where available, and must verify byte-identical originals, no partial
config rewrite, and no destination clobber on every rejection.

Low-confidence, multi-role, content-sensitive, unreferenced, and collision cases
stay unresolved. Extension-only classification may not cross a role boundary.
Any hard-coded script/import/config dependency that cannot be represented as a
reviewed compare-and-swap edit remains an `unresolved_dependency`. Migration
apply is blocked while even one such dependency can affect a copied artifact;
warnings are insufficient and the tool may not guess or rewrite arbitrary source.

### Conservative dependency-script inspection

The migration planner uses the read-only
`hub_core.dependency_script_inspection.analyze_dependency_script` API for
bounded dependency evidence. It accepts Python or R source text (or a `Path`)
and optional `suffix`/`language`, `script_path`, and explicit `role_roots`
arguments. The deterministic JSON-friendly result contains `inspectable`,
`dependency_scan_incomplete`, `static_candidates`, and
`hardcoded_unresolved_references`. Static candidates include imports and
obvious literal file/path references, but they are evidence only: the scanner
never executes a script, rewrites source, or guesses `raw`, `results`, script,
or any other semantic role from a name, extension, or directory.

A literal path is cleared only through the most-specific declared terminal
semantic root selected by the caller-provided `role_roots` mapping. Grouping
roots `scripts` and `results` never clear blockers, and equal-depth terminal
matches remain unresolved. Otherwise it remains an unresolved `hardcoded_path`
entry. Dynamic path expressions remain unresolved and set
`dependency_scan_incomplete`; read errors, unsupported languages, and parse
failures set `inspectable: false`, preserve a diagnostic, and set the same
incomplete signal. Thus a partial or failed scan is incomplete evidence and a
plan blocker, not a clean pass. The planner carries these entries into
`hardcoded_unresolved_references`; scanner output never becomes an approved
mapping.

`structure_apply.apply_structure_plan` enforces the corresponding fail-closed
guard: a non-empty `hardcoded_unresolved_references` **or**
`unresolved_proposals` rejects the plan before project-root identity checks or
copy, even when the plan digest and confirmation token are valid. An unresolved
proposal is therefore a plan blocker, not a warning or an approval surrogate.

## 8. Seven P1 corrections

### P1-1 Calculation evidence binds to the real artifact

`analysis_artifact_sha256` must hash the declared analysis artifact, not the
evidence document itself. Verification resolves the artifact, checks containment,
hashes its bytes, and rejects missing, mismatched, malformed, or self-referential
evidence. The calculation artifact is first promoted as durable source data,
table, or typed evidence and is bound to producer script/config/input/output
hashes and stable claim IDs. Receipt verification traverses those edges; a bare
hash with no producer lineage is unverified.

### P1-2 Project-script renders cannot bypass claim validation

Every publication-mode project-script render must emit a structured claim
inventory, including an explicit empty inventory when no claim exists. Each claim
has a stable ID, kind, displayed text/region, supporting calculation artifact ID,
and source-data/table dependencies. Text/image detection is conservative discovery
only. If a script is uninspectable, inventory is missing, a claim is detected but
undeclared, or an inventory edge cannot be verified, publication status is
`unverified` and blocks promotion. Explicit no-claim declarations are recorded
and auditable but do not override detected contradictions.

### P1-3 Strict raw integrity rejects vacuous seals

Strict mode requires at least one valid manifest entry when raw inputs are
declared, canonical relative paths, valid SHA-256 digests, existing regular files,
containment, and exact set/hash agreement. An empty seal cannot validate a
dependency graph. The dependency graph must be nonempty and terminate in at least
one raw or external-raw descriptor. The only exception is a typed, explicit
`no_raw_inputs` declaration with a reason and a graph containing only genuinely
input-free producers; absence, an empty list, or an inferred "no raw" state is
not an exception.

### P1-4 Journal minima are measured and persisted

Render evidence must populate policy projections with the selected validation
target, measured geometry/text/resolution/color outcomes, rule version,
measurement implementation/version, artifact SHA-256, pass/fail status, and any
inapplicable reason. Measurements are derived only from rendered artifact bytes
and metadata and must be reproducible from the recorded artifact SHA plus rule
and measurement versions. A profile name or renderer intent is not proof.

### P1-5 Neutral style is the implicit default

For v2 and the new v1.1 contract, omitting render style selects `neutral`,
preserving authored choices. An explicitly selected compatibility profile retains
the legacy Nature default for backward compatibility. Nature, Science, and other
publication render policies otherwise apply only when explicitly requested.
`render_policy` controls rendering; `validation_target` independently selects
which publication rules to measure. A validator never restyles or rerenders an
artifact and measures only the supplied artifact. Publication validation may
therefore assess a neutral render against an explicit journal target without
changing it.

### P1-6 One structure SSOT and one scaffold path

Scaffolding and normalization share one structure-contract module and one
template inventory. `scaffold.py` and `project_normalization.py` may coordinate
but may not independently define directory layouts.

### P1-7 Classification is semantic and reference-safe

Normalization uses declarations, provenance, config references, and script/output
relationships before names or extensions. A reviewed plan includes config edits;
apply refuses stale config, destination collisions, ambiguous roles, or reference
breakage.

## 9. Work packages, ownership, and dependencies

The main session orchestrates only: assigns disjoint ownership, reviews agent
evidence, integrates in dependency order, and owns final go/no-go. Agents must not
edit outside their package without reassignment.

| WP | Exclusive scope and primary files | Depends on / serial handoff | Acceptance |
|---|---|---|---|
| WP0 | Freeze this SSOT and requirement matrix; own the new normalized receipt DTO module `hub_core/durable_receipt.py` and its tests. Architecture agent. | None; DTO API freezes before WP1/WP3/WP8 | Every requirement maps to an exact test/gate; runtime diagnostics cannot bypass the DTO allow-list. |
| WP1 | P1-1/P1-2: `hub_core/calculation_evidence.py`, `hub_core/claim_inventory.py`, `hub_core/claim_script_inspection.py`, and project-render call sites only. Evidence agent. | WP0 DTO; hands frozen claim API to WP8/WP9 | Forged/self-hashed evidence, missing lineage, uninspectable or dynamically claim-bearing script, and claim bypass fail closed. |
| WP2 | P1-3: `hub_core/raw_integrity.py`, `hub_core/external_raw.py`, and the descriptor-integrity API consumed by execution. Integrity agent. | WP0; hands frozen raw graph API to WP4/WP8 | Empty/malformed/escape/mismatch fail; typed `no_raw_inputs` alone permits an input-free graph. |
| WP3 | P1-4/P1-5: `hub_core/render_evidence.py`, new `hub_core/artifact_policy_measurement.py`, v2 schema/default call sites. Rendering agent. | WP0; hands frozen measurement DTO to WP8/WP9 | Neutral/new default and explicit legacy default are observable; validation never mutates rendering. |
| WP4 | New `hub_core/project_structure_contract.py` and `hub_core/legacy_structure_resolver.py`; config schema/template docs. Contract agent. | WP0, then consumes frozen external-raw shape from WP2 | v1.1 valid/invalid/schema-less fixtures pass; root/DAG/alias rules fail fast; no file rewrite. |
| WP5 | P1-6: new `hub_core/project_layout.py`; then serially refactor `hub_core/scaffold.py` and only the layout constants in `hub_core/project_normalization.py`. Scaffold agent. | WP4 API freeze; hands those files to WP6 after merge | Both entry points use one layout inventory and produce identical declared structure. |
| WP6 | P1-7 read-only inventory/classifier and deterministic dry-run in `hub_core/structure_inventory.py`, `hub_core/structure_audit.py`, and `hub_core/structure_plan.py`; destination-to-role binding lives in `hub_core/structure_role_binding.py`. Discovery agent. | WP4, then exclusive serial handoff from WP5 | Semantic precedence, ambiguity, hard-coded dependency, collision, declared custom-root binding, and stable-plan tests pass. |
| WP7 | `hub_core/structure_apply.py` plus `hub_core/atomic_no_clobber.py`: copy-only apply, destination-filesystem sibling staging, config CAS, rollback, and a native consuming same-filesystem no-replace namespace move. Migration agent. | WP6 API freeze; no shared-file edits | Failure injection leaves originals unchanged; destination races preserve the competing file; unsupported no-replace primitives fail closed; unresolved dependencies block; raw is never moved/deleted. |
| WP8 | Runtime externalization/integration across `hub_core/runtime_boundary.py`, `runtime_paths.py`, `execution_log.py`, `error_dumper.py`, `cache_manager.py`, `external_raw_execution.py`, `durable_promotion.py`, `result_promotion.py`, process/data-contract call sites, and MCP runtime/security/render call sites. Runtime agent. | Serial after WP0/WP1/WP2/WP3/WP4 APIs freeze; those owners make no further edits until WP8 returns files | Roots are disjoint, all transient diagnostics remain runtime, CLI and MCP consume verified external raw, eligible results alone are promoted with native same-FS no-replace publication, and deletion drill preserves durable verification. |
| WP9 | MCP/CLI integration and generated tool docs; may edit interface files only after WP1/WP3/WP8 handoff. Interface agent. | WP4, WP6, WP7, then serial handoff from WP1/WP3/WP8 | No surface sprawl, installed budget and compatibility tests pass, output contains no absolute runtime path. |
| WP10 | End-to-end fixtures, packaging, release notes, migration guide only; no production logic. Release agent. | WP1-WP9 merged | All DoD/release gates pass from clean install and exact release commit. |

No file has two simultaneous owners. A listed serial handoff requires the first
owner to commit or otherwise freeze its diff, report exact tests, and explicitly
transfer ownership in the orchestration log before the next agent edits it. New
cross-cutting behavior goes into the named new modules rather than being copied
into existing call sites.

### 9.1 Implementation and release-evidence checkpoint (2026-07-19)

This checkpoint records working-tree integration, not merge, release, human
approval, or fulfillment of the complete Definition of Done.

| Work package | Current state | Working-tree evidence |
|---|---|---|
| WP0 | implementation complete | `durable_receipt.py` owns the closed receipt DTO and canonical verification. |
| WP1 | implementation complete | Durable calculation lineage and structured project claim inventory are integrated into project-render evidence; conservative script inspection blocks undeclared dynamic statistical annotations without treating unrelated dynamic labels as claims. |
| WP2 | implementation complete | Strict raw graphs reject vacuous seals; typed external-raw descriptors preserve trusted source identity and are verified before both CLI and MCP producer execution. |
| WP3 | implementation complete | Neutral v1.1/v2 defaults, independent validation targets, and artifact-derived policy measurements are integrated. |
| WP4 | implementation complete | v1.1 role/DAG/alias validation and legacy 1.0 in-memory resolution are integrated with config parsing and templates. |
| WP5 | implementation complete | Scaffolding and normalization consume the shared `project_layout.py` inventory. |
| WP6 | implementation complete | `structure_inventory`, `structure_audit`, `structure_plan`, and `structure_role_binding` use semantic/reference precedence and bind approved destinations to declared roots. The conservative `dependency_script_inspection.analyze_dependency_script` API supplies deterministic Python/R dependency evidence; parse/dynamic/incomplete findings remain blockers, and apply rejects non-empty `unresolved_proposals` fail-closed. |
| WP7 | implementation complete | Reviewed application is copy-only, token/CAS guarded, rollback-aware, and publishes a verified sibling stage only through the native consuming no-replace primitive; race winners are preserved. |
| WP8 | implementation complete; independent adversarial gate green | Runtime containment, pre-execution external-raw verification, eligible-result promotion, staged durable publication, and runtime-independent receipt verification are integrated across CLI and MCP producers. Handle-bound rollback deletion closes the hash-to-unlink swap window; the independent rollback suite passed 34 tests with two platform skips. |
| WP9 | implementation complete | v2 exposes structure detail through `figops.describe`; compatibility apply remains write-gated without expanding the seven-tool default surface. |
| WP10 | technical gates complete; owner authorization recorded | Live references and the v2 baseline fixture are current. Cross-platform Python, actual R, public-release, docs/architecture, package build/check/scan, clean consumer install, and installed-surface gates are green for the exact source head below. Repository owner authorization for v0.20.0 is recorded in PR #224; release operations still require technical-gate recheck on the exact selected release commit. |

The definitive cross-platform CI run was
[`29689087108`](https://github.com/Moonweave-Research/figops/actions/runs/29689087108)
for source head `9e4d340b718529bd0f65ba46b2124dda718918a2`. Its macOS full
suite passed **2,322 passed, 22 skipped, 104 subtests**; its native
`/var`/`/private/var` alias gate passed **9/0**. Its Windows containment and
symlink gate passed **48/0** with zero skipped security tests. The locked
actual-R job used **R 4.4.2**, **readr 2.2.0**, and **dplyr 1.2.0**, then passed
the two required integration nodes **2/0**. Ruff and the advisory dependency
audit also passed in that run.

The final package gate rebuilt from that exact source head and produced
non-published witnesses in the external, ephemeral package-gate artifact
directory `figops-package-9e4d340b-r1/artifacts/` (not this checkout's
`dist/`):

- `figops-0.20.0-py3-none-any.whl` — 634,485 bytes; SHA-256
  `9623cb8675af47a184ab83636ef390220608514957da885f8ca1dd42b8403cbd`
- `figops-0.20.0.tar.gz` — 526,180 bytes; SHA-256
  `b7128735c0f3eba259eea30bcadbda4e864f3bd101d05246a04a5cae9fbc7511`

Twine validation, package-surface inspection, and clean consumer smoke passed.
Installed discovery exposed 7 v2 tools and 27 compatibility tools. These
artifacts are not published release artifacts. The authoritative public-release
status now records `repository_public_release_authorized=true` with the
[PR #224 owner authorization](https://github.com/Moonweave-Research/figops/pull/224#issuecomment-5016360221)
as approval evidence. Merge, tag, package publication, and GitHub Release are
authorized for v0.20.0, subject to rechecking technical gates on the exact
selected release commit.

### 9.2 Token-efficient agent routing

- **Small/fast agent (WP0 docs/matrix, WP10 docs/fixtures):** inventory,
  documentation drift, fixture generation, mechanical schema updates, focused
  lint; target one context slice and under 25k input tokens.
- **Standard agent (WP5, WP6, WP9):** bounded module implementation with explicit
  tests; read only its owned modules, public interfaces, and mapped test files.
- **Deep-reasoning agent (WP0 DTO, WP1-WP4, WP7-WP8):** trust boundaries, path
  containment, evidence semantics, version resolution, migration transactions,
  and adversarial cases; split author and verifier contexts.
- **Independent verifier:** read-only cross-WP review after integration; it must not
  be the author of the reviewed package.
- Prefer targeted tests during a WP. Run global gates once at integration points,
  not independently in every agent.
- Agent reports contain changed files, commands/results, remaining risks, and no
  pasted large diffs. The main session makes no implementation edits.

## 10. Test plan and acceptance matrix

Every named node below must exist; renaming it requires updating this SSOT in the
same change. The focused command is `python hub_uv.py run python -m pytest -q
<node>` and success means exit 0 with the named node collected and passed.

| Requirement | Exact test file/node | Release gate |
|---|---|---|
| PR #224 P1 release block | `tests/test_release_discipline.py::test_v020_release_requires_structure_p1_gate` | full pytest + human approvals |
| Calculation artifact/lineage, no self-hash | `tests/test_evidence_contract.py::test_calculation_receipt_binds_durable_artifact_and_lineage` | full pytest |
| Structured claims/uninspectable script | `tests/test_claim_boundaries.py::test_publication_project_script_requires_verified_claim_inventory` | full pytest |
| Strict nonempty raw graph/typed exception | `tests/test_raw_integrity.py::test_strict_graph_rejects_vacuous_seal_unless_no_raw_inputs` | full pytest |
| Neutral new default/legacy compatibility | `tests/test_mcp_surface_profiles.py::test_new_contract_is_neutral_and_compatibility_keeps_nature` | installed consumer smoke |
| Render-policy/validation separation | `tests/test_render_evidence.py::test_validator_measures_artifact_without_render_mutation` | journal fixture gate |
| Recomputable policy projection | `tests/test_render_evidence.py::test_policy_projection_binds_artifact_rule_and_measurement_versions` | journal fixture gate |
| One layout/scaffold path | `tests/test_project_roles.py::test_scaffold_and_normalizer_share_v11_layout` | full pytest |
| Runtime/project-result boundary | `tests/test_runtime_paths.py::RuntimePathTest::test_runtime_root_is_disjoint_from_project_and_durable_roots` | full pytest |
| Same-FS staged atomic promotion | `tests/test_durable_promotion.py::test_result_promotion_stages_on_destination_filesystem` | Windows + POSIX CI |
| Native consuming no-replace move | `tests/test_atomic_no_clobber.py::test_atomic_move_consumes_source_name` | Windows + POSIX CI |
| Destination race winner preserved | `tests/test_atomic_no_clobber.py::test_atomic_move_preserves_race_winner` and `tests/test_structure_apply.py::test_apply_race_never_clobbers_competing_destination` | Windows + POSIX CI |
| Promotion race winner preserved | `tests/test_durable_promotion.py::test_promotion_race_never_clobbers_competing_destination` | Windows + POSIX CI |
| Artifact rollback swap preserves competitor | `tests/test_durable_promotion.py::test_artifact_rollback_hash_then_inode_swap_preserves_competitor` | Windows + POSIX CI |
| Receipt rollback swap preserves competitor | `tests/test_durable_promotion.py::test_receipt_rollback_hash_then_inode_swap_preserves_competitor` | Windows + POSIX CI |
| Unsupported atomic primitive fails closed | `tests/test_atomic_no_clobber.py::test_unsupported_native_primitive_fails_before_publication` | full pytest |
| Receipt DTO/opaque manifest ID | `tests/test_durable_receipt.py::test_durable_receipt_normalizes_diagnostics_and_hides_runtime_root` | public/package scan |
| External raw descriptor | `tests/test_raw_integrity.py::test_external_raw_requires_allowed_root_version_and_sha` | full pytest |
| External raw reaches MCP producer only after verification | `tests/test_external_raw_execution.py::test_mcp_project_render_consumes_verified_external_raw_from_runtime` | MCP integration gate |
| External raw reaches CLI producer only after verification | `tests/test_external_raw_execution.py::test_cli_external_raw_root_grant_reaches_actual_producer` | CLI integration gate |
| Dynamic claim cannot bypass empty inventory | `tests/test_claim_boundaries.py::test_dynamic_claim_annotations_cannot_bypass_explicit_empty_inventory` | full pytest |
| Eligible result promotion production caller | `tests/test_result_promotion_integration.py::test_project_render_production_caller_promotes_only_after_clean_gates` | end-to-end gate |
| DAG/forbidden alias matrix | `tests/test_project_structure_contract.py::test_v11_role_nesting_dag_rejects_forbidden_aliases` | full pytest |
| Legacy 1.0 in-memory advance | `tests/test_config_parser_sweep.py::test_schema_less_structure_resolves_in_memory_without_rewrite` | config sweep |
| Hard-coded unresolved dependency | `tests/test_project_roles.py::test_migration_apply_blocks_unresolved_hard_coded_dependency` | full pytest |
| Runtime leakage across WP8 scope | `tests/test_runtime_paths.py::RuntimePathTest::test_all_runtime_producers_stay_external_and_disposable` | deletion drill |
| Runtime deletion durability | `tests/test_durable_receipt.py::test_receipt_verifies_after_runtime_tree_deletion` | end-to-end gate |
| Public surface and private-name hygiene | `tests/test_public_package_surface.py::test_installed_ai_native_surface_budget` | public scan + clean install |

### 10.1 Unit and property tests

- Role-root normalization, overlap, containment, traversal, symlink/junction, case
  normalization, and Windows drive/UNC edge cases.
- Strict raw manifest non-vacuity, digest syntax, exact membership, regular-file
  identity, and mutation between validation/use.
- Evidence artifact binding, receipt canonicalization, sensitive-field exclusion,
  and output/input hash relationships.
- Neutral implicit style and explicit policy selection.
- Semantic classification precedence and deterministic dry-run serialization.
- Copy verification, atomic promotion, stale-plan/config compare-and-swap, and
  rollback under injected failures.

### 10.2 Integration tests

- Fresh v1.1 scaffold through analysis, plot, evidence, and publication promotion.
- Legacy project runs without relocation; audit proposes a mapping.
- Existing `results/data` ambiguity is warned and blocks only publication evidence
  that requires an unambiguous source-data role.
- Project-script statistical annotation without calculation evidence cannot be
  marked publication-ready.
- Journal render persists measured minimum-rule outcomes.
- Prefetched cloud input retains source URI/hash while materialization stays in
  external runtime.
- Runtime root deletion after a successful run leaves result hashes and durable
  receipt verification intact.
- Copy-only migration followed by smoke execution; originals remain byte-identical.

### 10.3 Repository and release gates

- `python hub_uv.py run python -m pytest -q`
- `python hub_uv.py run ruff check .`
- `python scripts/check_public_release.py --root .`
- Generated schema/tool documentation is current.
- Package build, Twine check, clean-environment install, installed-surface budget,
  and consumer smoke pass.
- No Python module exceeds the repository size policy.
- `git diff --check` is clean.
- Actual R integration/render is executed in an R-capable environment; absence of
  `Rscript` is a release blocker for this structure release, not a silent skip.
  The exact CI gate is `Rscript -e "suppressPackageStartupMessages(library(readr))"`
  followed by `python hub_uv.py run python -m pytest -q
  tests/test_smoke.py::HubSmokeTest::test_scaffold_all_and_cache
  tests/test_process_runner_new.py::TestScaffoldRAnalysisInputContract::test_scaffold_r_analysis_reads_real_data_from_normalized_raw_dir`;
  acceptance is exactly two passed nodes and zero skipped nodes.

## 11. Rollback and safety

- Organizer application is disabled by default and separately write-gated.
- Every apply consumes an immutable reviewed plan ID and emits a rollback manifest.
- Raw inputs are copy-only; automatic cleanup is forbidden.
- Result promotion always uses a sibling staging path on the destination
  filesystem, fsync/hash verification, then a same-filesystem atomic no-replace
  move that consumes the private stage name and preserves a destination race winner.
  A runtime-to-destination cross-volume copy may populate that sibling stage, but
  direct cross-volume rename/promotion is forbidden.
- Config edits use compare-and-swap against the reviewed original hash.
- On any failure, new promoted paths are removed only when their hashes match the
  rollback manifest and deletion remains bound to that same file identity.
  Windows performs file-ID/hash verification and delete disposition through one
  non-write-shared handle. POSIX never uses check-then-unlink; when ownership
  cannot be proven atomically, the path is preserved and a typed manual-cleanup
  error is emitted. Pre-existing, racing, or user-modified files are never deleted.
- Feature flags permit disabling v1.1 organization/apply while leaving read-only
  audit and existing orchestration intact.
- Rollback of the release means disabling new mutation paths and restoring prior
  config interpretation; it never reverses user data movement automatically.

## 12. Release sequence

1. Land and verify P1-1 through P1-7.
2. Land v1.1 contract and shared scaffold behind non-mutating defaults.
3. Land read-only discovery/dry-run; publish migration examples.
4. Land write-gated copy-only apply and failure-injection evidence.
5. Externalize remaining runtime leakage and validate durable receipts.
6. Run independent adversarial review and the complete gate matrix.
7. Merge only after CI and repository-required human/legal approvals.
8. Tag, build, publish, and create the GitHub release from the approved release
   commit according to repository release policy.

Existing Draft PR #224 must not be presented as released merely because tests or
packaging pass. Tag, package publication, and GitHub Release are separate verified
events.

## 13. Definition of Done

The work is complete only when all statements below are true and every command
exits 0 from a clean checkout of the exact release commit: `python hub_uv.py run
python -m pytest -q`; `python hub_uv.py run ruff check .`; `python
scripts/check_public_release.py --root .`; `python hub_uv.py run python -m build`;
`python hub_uv.py run python -m twine check dist/*`; `python
scripts/consumer_install_smoke.py --root .`; and `git diff --check`. Generated
tool/schema docs must reproduce byte-identically, the installed v2/compatibility
surface budget tests must pass, and an R-capable CI job must execute (not skip)
the real R integration/render gate. Independent review must report zero P0/P1,
all repository-required approvals must be recorded, and the release commit/tag
and built artifact hashes must agree before publication.

- All seven P1 corrections have regression tests and no open blocker.
- One v1.1 role contract drives config validation, scaffold, normalization, audit,
  and migration; no duplicate layout constants remain.
- Raw, scripts, derived data, figures, publication, and runtime have explicit,
  non-overlapping semantics.
- Runtime is externally rooted and deletable; durable results remain verifiable
  after a deletion drill.
- Organization defaults to read-only dry-run, reports ambiguity, and applies only
  an explicitly accepted copy-only plan.
- No automatic operation moves or deletes raw data.
- Legacy projects run unchanged and receive actionable compatibility diagnostics.
- Neutral is the implicit v2/v1.1 render policy; explicit compatibility retains
  its legacy Nature default. Validation targets are independent and their
  measured minima are persisted without mutating the artifact.
- Statistical claims and raw-integrity seals cannot obtain verified status through
  missing, empty, self-referential, or forged evidence.
- Full Python and actual R gates, public-release checks, generated docs, package
  build/install, installed surface, and end-to-end fixtures pass.
- Independent review reports no P0/P1 issue.
- Release notes state migrations, compatibility behavior, runtime/result boundary,
  remaining limitations, exact commit/tag, and artifact hashes.

## 14. Decision log

- Keep the user's three-part mental model at the top level, but distinguish
  intermediate/source data within durable results.
- Encode meaning as declared roles rather than mandatory folder names.
- Treat runtime/detail manifests as disposable and durable receipts as research
  results.
- Prefer explicit policy selection and evidence-backed enforcement over defaults
  that reduce LLM discretion.
- Favor read-only discovery and reversible copy-only migration over automatic
  cleanup.
