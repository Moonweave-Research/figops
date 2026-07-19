# FigOps - Sub-Agent Protocol (v4.0)

> Scope: This file defines model-agnostic sub-agent ownership for the
> independent `figops` repository. Main-agent and global rules live in
> `AGENTS.md`; PR #224 package ownership and serial handoffs live in
> `docs/specs/2026-07-15-project-structure-runtime-integrity-plan.md`.

---

## 1) Sub-Agent Topology

| Sub-agent | Primary ownership | Key responsibilities |
|---|---|---|
| `Pipeline-Orchestrator` | `orchestrator.py`, `hub_core/process_*`, `hub_core/cache_manager.py`, `hub_core/execution_log.py` | CLI/pipeline coordination, cache behavior, external runtime logs, and provenance plumbing. |
| `Project-Structure Guardian` | `hub_core/project_structure_contract.py`, `project_layout.py`, `legacy_structure_resolver.py`, `structure_inventory.py`, `structure_audit.py`, `structure_plan.py`, `structure_role_binding.py`, `structure_apply.py`, `atomic_no_clobber.py` | Declared-role/DAG validation, legacy in-memory resolution, shared scaffold layout, deterministic audit/plan, destination-role binding, and native no-clobber copy-only apply. |
| `Evidence-Integrity Guardian` | `hub_core/durable_*`, `result_promotion.py`, `calculation_evidence.py`, `claim_inventory.py`, `claim_script_inspection.py`, `raw_integrity.py`, `external_raw.py`, `external_raw_execution.py`, `render_evidence.py` | Durable receipts and production result promotion, calculation/claim lineage, conservative dynamic-claim review, non-vacuous raw integrity, launcher-authorized external-raw execution, and measured policy evidence. |
| `MCP-Interface Guardian` | `hub_core/mcp/`, `scripts/gen_tool_reference.py`, `docs/tools*.md` | Registry/schema and handler consistency, v2/compatibility profiles, write gating, bounded responses, and source-generated references. |
| `Data-Contract Guardian` | `hub_core/data_contract*`, config contract integration | Dtype and semantic validation, bounded input resolution, and normalized validation diagnostics. |
| `Academic-Stylist` | `themes/`, `plotting/` | Journal/presentation presets, palette and style SSOTs, reusable render primitives, and deterministic figure output. |
| `Project-Migrator` | `project_config_template.yaml`, `hub_core/templates/`, onboarding and migration docs | Mapping research projects to the declared structure contract without silent moves or destructive cleanup. |

No two agents edit a shared file simultaneously. A dated corrective SSOT may
temporarily narrow these standing ownership areas; its explicit package table
and handoff order take precedence for that change.

## 2) Cross-Cutting Rules

- `Pipeline-Orchestrator` keeps runtime state outside project and durable-result
  roots and uses the prefetch path for cloud-synchronized inputs.
- `Project-Structure Guardian` treats folder names as defaults; declared roles,
  provenance, references, and containment determine meaning. Copy apply uses the
  native consuming same-filesystem no-replace move and fails closed rather than
  falling back to hardlink or replacing publication.
- `Evidence-Integrity Guardian` fails closed on missing, empty, forged, or
  self-referential evidence, verifies external inputs before execution, admits
  only clean eligible runtime results to durable promotion, and never serializes
  detailed runtime manifests as durable receipts.
- `MCP-Interface Guardian` regenerates all tool references from live registries
  and measures the default profile through JSON-RPC rather than hand-counting.
- `Academic-Stylist` preserves authored output by default and records any
  explicit transformation or compatibility policy.

---

**Last Update**: 2026-07-16 (FigOps identity and current structure/runtime
ownership aligned)
