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
