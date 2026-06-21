# Research Operations Philosophy

Graph Hub enforces a simple research-operations rule: every figure traces to validated data, and validated data traces to a declared experiment. The repository structure must enforce that chain, not merely document it.

The philosophy is reproducibility-first and FAIR-aligned, but sized for a single researcher or small research workflow. Graph Hub should make the correct research structure the default runtime path, fail fast when the structure is violated, and keep migrations opt-in and non-destructive.

Out of scope: enterprise governance bloat. This includes approval gates, contributor/role/institution governance, data-governance tiers, and lifecycle approval chains.

## Tier 1

1. Master/module boundary enforcement: a master manifest coordinates execution modules but is not itself runnable. Status: done.
2. Folder role taxonomy and re-run-surface filtering: project folders declare their operational role, and only module configs appear in runnable re-run sets. Status: done.
3. `experimental_conditions` schema and validation: experiments declare their conditions in machine-checkable form. Status: done.

Tier 1 is complete.

## Tier 2

1. Sample registry across modules. Status: done.
2. Figure-data-claim traceability manifest.
3. Raw data immutability and provenance enforcement.

## Tier 3

1. Naming and quarantine-zone validation.
2. Canonical-docs precedence registry.
3. Config TODO/placeholder checks.

Applying this philosophy to an existing research project is a separate migration step. That migration must be explicit, opt-in, and non-destructive.
