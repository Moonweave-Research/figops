# Research Operations Philosophy

FigOps makes research-operations structure the default path for execution
modules, while keeping migrations explicit and non-destructive. The enforcement
posture is strict but scoped: modules fail fast on declared research-ops contract
violations, but FigOps does not require every possible contract to be present
in every project.

The philosophy is reproducibility-first and FAIR-aligned, but sized for a single
researcher or small research workflow. Master manifests coordinate modules and
are not runnable execution surfaces.

Out of scope: enterprise governance bloat. This includes approval gates,
contributor/role/institution governance, data-governance tiers, and lifecycle
approval chains.

## Module Enforcement Defaults

| Rule | Enforced by default for `role: module` | Explicit opt-out |
| --- | --- | --- |
| Master/module boundary | Yes. Master configs cannot define runnable pipeline, figure, or diagram surfaces. | None. Use `project.role: module` for runnable projects. |
| Raw integrity | Yes, when `data_contract.raw_integrity` is configured and its manifest is sealed. Drift blocks render by default. Missing/unsealed manifests have no effect. | Set `data_contract.raw_integrity.mode: warn`. |
| Config placeholders | Yes. TODO/FIXME/TBD/XXX/`???` and angle-bracket placeholder tokens fail validation by default. | Set `data_contract.forbid_todo_placeholders: false`. |
| Figure traceability | Yes, for figures that declare any part of `claim`/`samples`/`conditions`. The declared chain must be complete and references must resolve when registries are present. Figures with no traceability declaration are allowed. | Set `data_contract.require_figure_traceability: false`. |
| Canonical docs | Yes, when `canonical_docs` are declared. Declared docs must exist. Modules do not have to declare `canonical_docs`. | Set `data_contract.require_canonical_docs: false`. |

Absent `project.role` defaults to `module`, so these module defaults apply unless
the config explicitly opts out. Master configs keep the module-default rules off
unless a rule is explicitly enabled.

## Tier Status

Tier 1 is implemented: master/module boundary enforcement, folder role taxonomy,
and machine-checkable `experimental_conditions`.

Tier 2 is implemented with scoped enforcement: sample registries, declared
figure-data-claim traceability, and raw integrity checks for sealed manifests.

Tier 3 is implemented with scoped enforcement: naming/quarantine validation,
canonical-docs precedence when declared, and config placeholder checks.

Applying this philosophy to an existing research project remains a separate
migration step. That migration must be explicit, opt-in, and non-destructive.
