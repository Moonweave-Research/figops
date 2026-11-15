# Interpreting diagnostics

## A partial folder inventory is a sample

Structure inspection is read-only and stops at a global 10,000-entry limit.
Each declared root gets a turn, so a large raw-data tree cannot consume the
entire budget before smaller script or output roots are sampled. A small root
with a deeply nested file can still be incomplete; sampling is not an exhaustive
filesystem census.

When `inventory_entry_limit` appears,
`declared_vs_actual.inventory_complete` is `false`. Inferred orphan findings and
unknown entries carry `provisional: true`. Use them as review candidates, not
proof that a file is unused or safe to delete. Configured inputs, including
source-data inputs, count as references. Existing declared grouping directories
are not stale references merely because they contain subdirectories.

## Readiness uses the target you actually declared

Call `figops.audit_artifact` with the public policy pack
`publication-readiness-v1`. For a neutral exploratory render, it checks generic
readiness and explains that no journal validation target was selected. It does
not invent a journal or require a nonexistent projection.

For journal-specific checks, pass an explicit `validation_target` when rendering
(for example, `nature`). The audit requires that target's matching journal
projection; a missing projection remains a blocking error. Legacy internal
projection identifiers are not public policy-pack arguments.

An audit always requires manual review. Removing a false missing-projection
error does not waive failed integrity, provenance, artifact, or data checks and
does not mean that the figure is publication-approved.

## Existing raw files are not a reviewed integrity baseline

When `data_contract.raw_integrity` is configured, `warn` reports integrity
problems and `strict` blocks them. The canonical project-render policy context
records that configured mode. Without raw-integrity configuration, the internal
policy default is `off`; `off` is not a supported explicit configuration mode.

If a manifest is missing, first review the declared raw inputs. Then deliberately
create a baseline from those reviewed files:

```bash
python -m hub_core.raw_integrity seal /path/to/project
```

Run this command in the Python environment containing FigOps. It writes the
manifest selected by `data_contract.raw_integrity.manifest`, defaulting to
`raw/.raw_manifest.json`. It does not prove that the input data is correct.
Do not reseal changed data simply to silence an unexpected drift warning:
review the change first. Inspection, audit, and rendering do not automatically
seal or rewrite the source data.
