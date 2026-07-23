# Project structure and migration contract

FigOps config schema `1.1` adds the read-only `figops-project-v1.1` structure
contract. Declared roles, rather than folder names or extensions, determine the
meaning of project files. The canonical declaration is in
`project_config_template.yaml`.

The top-level roots `raw`, `scripts`, and `results` must be mutually disjoint.
Analysis, figure, and shared-script roots must be distinct descendants of
`scripts`; intermediate data, source data, tables, figures, evidence, and
publication roots must be distinct descendants of `results`. Runtime is
launcher-owned and is never a project-configured root. All declared roots are
normalized project-relative paths. An existing symlink or junction that resolves
outside the project is rejected.

Configs without `structure.contract` are diagnosed as declared contract `1.0`
and resolved to an effective `1.1` view in memory. Loading may advance the
in-memory `schema_version`, but does not rewrite the YAML or move files. Use
`hub_core.project_structure_contract.structure_diagnostics` to inspect declared
and effective versions plus inferred mappings.

External raw data is declared separately with top-level `external_raw`
descriptors. Producer inputs refer to descriptors as `external_raw:<id>`. A
descriptor cannot widen launcher-approved roots and must contain a stable
version and lowercase SHA-256 identity. Standalone CLI runs grant authority
explicitly and per invocation with repeatable
`--external-raw-root ID=ABSOLUTE_PATH` options; paths inside project YAML never
grant that authority. MCP runs reuse their validated `allowed_data_roots` and
bind each descriptor's `allowed_root` to the exact approved root identifier.
Both paths prefetch, materialize below external runtime storage, and verify the
declared SHA-256 before a producer sees the resolved `GRAPH_HUB_INPUTS` path.

`figops.inspect_data` requires `external_raw_id` before returning samples from
even a public or internal external descriptor. It first verifies the full
project config and typed descriptor, then binds ID, allowed root, version, path,
and post-prefetch SHA-256. Restricted, ambiguous, invalid, mismatched, or
unverified external data remains metadata-only.

New v1.1 configs default to advisory, automatic language selection. Projects can
opt into enforcement through `language_policy.mode: enforce`; legacy configs
retain the prior R-analysis/Python-plot compatibility policy. Rendering policy
and publication validation are separate: `visual_style.render_policy` controls
styling, while `visual_style.validation_target` selects measurement rules. When
both a recognized `project.target_journal` and validation target are declared,
they must identify the same journal family.

## Reviewable organization workflow

Existing projects are never silently reformatted. The default operation is a
read-only audit: inventory declared references and provenance, propose semantic
roles, report confidence/conflicts/unresolved dependencies, and build a
deterministic plan. Filename and extension heuristics may suggest a mapping but
cannot approve one.

The compact v2 surface exposes current structure facts through
`figops.describe` with `kind: project_structure`; this does not write files. The
compatibility surface retains the separately write-gated
`figops.normalize_project_structure` workflow:

1. Call it with `dry_run: true` and the default `move_policy: adopt` to inspect
   proposed and unresolved mappings.
2. Review roles, destinations, collisions, config references, and hard-coded
   dependencies. Submit only accepted entries as `approved_mappings`, with any
   typed `config_diff`, using `move_policy: copy` and `dry_run: true`.
3. Preserve the returned plan digest and confirmation token. Apply only the
   identical reviewed inputs with `dry_run: false` and that token.
4. Verify the returned copy receipt and project validation. Original inputs
   remain byte-identical; cleanup is a separate user-authorized action.

Apply refuses automatic mappings, moves, symlinks, overwrites, stale source or
config hashes, destination collisions, changed confirmation inputs, and any
unresolved hard-coded dependency. Copies are staged beside their destination,
hashed, and fsynced where supported. Publication then uses the platform's native
same-filesystem, consuming, no-replace namespace move: Windows `os.rename`,
Linux `renameat2(RENAME_NOREPLACE)`, or macOS `renamex_np(RENAME_EXCL)`. It does
not use a hardlink or replacing rename, preserves a destination race winner, and
fails closed when the native guarantee is unavailable. Failure rollback removes
only newly created files whose hashes still match the reviewed plan; FigOps
never deletes or moves raw inputs.

### Finding-to-plan selection matrix

The audit report is a selection aid, not an approval list. The following matrix
is normative for the transition from a read-only finding to a reviewed copy
plan:

| Report item | Surface/status | Selection class | Plan/apply effect |
| --- | --- | --- | --- |
| Invalid project/configuration | `audit_status: invalid` | Report-only | Retain the row and errors; do not inspect, propose, or apply mappings until the project is repaired and audited again. |
| Execution-path rejection | `audit_status: boundary_blocked` | Report-only | Retain the row and boundary error; no project files may be selected from this row. |
| Config-less discovery entry | `audit_status: skipped` | Report-only | Retain the discovery evidence; provide a valid project configuration before any plan can be built. |
| Loader or audit exception | `audit_status: audit_error` | Report-only | Preserve the error and rerun after it is resolved; an exception never becomes a mapping candidate. |
| Audited structural finding | `audit.findings[]` (for example `collision`, `stale_reference`, or `provenance_incomplete`) | Report-only diagnostic | Findings inform review and may block a safe plan, but are never copied into `approved_mappings`. |
| Semantic role proposal | `audit.unknowns[]` with one candidate, or `proposed_mappings[]` | Candidate-only | A candidate role, confidence, or destination is a suggestion only; a reviewer must choose the explicit source, destination, and role. |
| Ambiguous/heuristic unknown | An `unknowns[]` candidate with conflicting or heuristic evidence | Report-only candidate | Keep the item unresolved. It may be discussed during review, but it cannot enter a plan until the reviewer supplies an explicit mapping. |
| Unresolved proposal/dependency | `unresolved_proposals[]` or `hardcoded_unresolved_references[]` | Report-only blocker | Keep it unresolved; apply is refused while it can affect a copied artifact. FigOps never guesses or rewrites arbitrary source text. |
| Reviewed mapping | `approved_mappings[]` (with any typed `config_diff`) | Explicit plan input | Only this reviewer-supplied list is eligible to enter a copy-only plan. Every source, destination, and semantic role is validated and bound to declared roots. |
| Reviewed dry-run plan | `plan_digest` and `confirmation_token` | Review checkpoint | The canonical plan digest is deterministic and the returned token binds the exact plan; dry-run writes nothing. |
| Exact reviewed apply | `dry_run: false`, `move_policy: copy` | Apply confirmation | Re-submit the identical reviewed inputs and token. Stale hashes/config, changed inputs, collisions, unresolved dependencies, or token mismatch fail closed. |

In particular, an ambiguous/heuristic `unknown` remains report-only even when a
candidate role is displayed, while a high-confidence `proposed_mapping` remains
candidate-only. Neither is an implicit approval.
`approved_mappings` must be authored from the reviewed evidence (or an
intentional, documented mapping) and must not be synthesized by replaying the
audit output.

### Approval-token workflow

1. Run `figops.describe` with `kind: project_structure` or the CLI
   `--audit-structure` mode. Treat `invalid`, `boundary_blocked`, `skipped`,
   and `audit_error` rows as report-only. Treat `findings`, ambiguous/heuristic
   `unknowns`, `proposed_mappings`, and unresolved proposals as evidence for
   review, not as approvals.
2. Request `figops.normalize_project_structure` with `dry_run: true` and
   `move_policy: adopt` to inspect candidate mappings. Select only the entries
   the reviewer accepts, then submit those as explicit `approved_mappings` (and
   any typed compare-and-swap `config_diff`) with `move_policy: copy` and
   `dry_run: true`.
3. Record the returned `plan_digest` and `confirmation_token`. The digest is a
   SHA-256 of the canonical plan payload (sorted semantic entries and verified
   source/config identities, excluding the self-referential digest); the token
   is `FIGOPS-APPLY-<plan_digest>`. This proves integrity and exact replay of
   the reviewed plan, not the independent identity, role, authorization, or
   attestation of the person or process that supplied it. It is a review
   checkpoint, not a write.
4. Apply only by resubmitting the identical project path, mappings, config edits,
   unresolved-reference list, and `plan_digest`-bound token with
   `move_policy: copy` and `dry_run: false`. The apply path revalidates source
   identity, configuration, containment, collisions, and the token before any
   copy, then emits the copy receipt and validation result.
5. Verify the receipt and validation. Original inputs remain byte-identical;
   cleanup is separate and user-authorized. A plan, digest, or token is control
   evidence, not a research result, runtime manifest, or evidence receipt.

### Phase 4 boundary and Phase 5 gap

Phase 4 keeps the mapping policy explicit: only reviewer-supplied
`approved_mappings` and typed config edits may enter the copy-only plan. The
current `FIGOPS-APPLY-<plan_digest>` token binds the exact canonical payload and
the verified source/config identities, but it does not establish independent
human identity, reviewer authority, or an attestation. The current workflow
therefore does not close self-approval; reviewer provenance remains an
out-of-band policy/process requirement rather than a machine-enforced claim.

The next Phase 5 gap is a host-issued `approval_receipt` (or equivalent
immutable reviewed-plan authority) bound to the plan digest and reviewed
inputs, with verifiable reviewer identity/role, authorization, and attestation
semantics. Until that authority exists and is consumed by apply, no plan token
or copy receipt may be described as independent approval evidence.

## Runtime and durable results

Launcher-owned runtime state is external to the project and disposable. Jobs,
snapshots, materialized inputs, caches, logs, previews, diagnostics, detailed
manifests, and temporary files remain below the resolved runtime root. Declared
intermediate/source data, tables, figures, compact evidence receipts, and
publication bundles remain below their durable project roles.

Promotion first stages and verifies bytes on the destination filesystem, then
uses the same native consuming no-replace move. `result_promotion.py` admits only
runtime renders whose persisted manifest, claim inventory, policy projection,
and eligibility gates all verify. A durable receipt records logical IDs and
hashes, not absolute runtime or user-home paths, so deleting the runtime tree
after success does not invalidate result verification.
