# M1 — Maintainability & Architecture (decomposition) — implementer spec

> Milestone goal (`docs/ROADMAP.md`): decompose `hub_core/mcp_surface.py` (~4,970 lines, ~110
> methods) into the `hub_core/mcp/` layout (`docs/architecture.md`), enforce module boundaries,
> clear lint debt, and raise coverage on the trust-boundary core. **Behavior-preserving** — the
> MCP wire contract and all outputs stay identical; this is moves + re-wiring only.
> Safety net: the ~625-test suite (esp. `tests/test_mcp_*`) is the regression oracle.

## Inventory snapshot (current `mcp_surface.py`, 2026-06)

Module-level: geometry/layout helpers (`_geometry_*`, `_layout_*`, L173–414), worker entrypoints
`_render_bridge_figure_worker`/`_batch_discovery_worker` (L432/444), `ToolDefinition` +
`_object_schema`/`_standard_output_schema`/`list_tool_definitions` (L459–835),
`list_resource_definitions`/`list_resource_templates`/`list_prompt_definitions` (L835–917).
`GraphHubMCPServer` (L917) holds the 11 tool handlers + ~90 private helpers. JSON-RPC transport
(`run_stdio_server`, `_dispatch_json_rpc`, `_handle_json_rpc`, `_read_stdio_message`,
`_read_headers`, `_write_stdio_message`, `_json_rpc_error`, `_StdioParseError`, `JSONRPC_*`,
`MCP_MAX_MESSAGE_BYTES`) lives near the file tail (~L4560+).

## Target placement (function → module)

| Target module | Functions / members (current names) |
|---|---|
| `hub_core/mcp/transport.py` | `run_stdio_server`, `_dispatch_json_rpc`, `_handle_json_rpc`, `_read_stdio_message`, `_read_headers`, `_write_stdio_message`, `_json_rpc_error`, `_StdioParseError`, `JSONRPC_*` consts, `MCP_MAX_MESSAGE_BYTES`, batch/lifecycle/envelope logic |
| `hub_core/mcp/security.py` | `_allowed_data_roots`, `_broad_data_root_warning`, `_is_relative_to`, `_resolve_under_root`, `_resolve_allowed_data_path`, `_scan_root`, `_resolve_project_path`, `_resolve_write_tools_enabled`, `_resolve_runtime_root`, `_activate_runtime_root_for_runtime_access`, `security_warnings` state |
| `hub_core/mcp/schemas.py` | `ToolDefinition`, `_object_schema`, `_standard_output_schema`, `list_tool_definitions`, `list_resource_definitions`, `list_resource_templates`, `list_prompt_definitions`, the **tool registry** |
| `hub_core/mcp/render_orchestration.py` | `_render_bridge_figure_worker`, `_batch_discovery_worker`, `_render_status_payload`, `_write_render_failure_artifacts`, `_geometry_diagnostics_env`, `_run_render_bridge_figure`, `_project_render_error`, `_copy_project_snapshot(_directory)`, `_run_project_figure_script`, `_normalize_script_stream`, `_script_output_tail`, `_write_project_script_output`, `_read_project_script_output`, `_project_failure_script_output`, `_exception_error_lines`, `_pythonpath_with_hub`, `_project_context_render_warnings`, `_write_project_render_failure_artifacts`, `_mcp_render_provenance`, `_mcp_project_render_provenance`, `_baseline_comparison`, `_geometry_*`/`_layout_*` helpers |
| `hub_core/mcp/tools/read_tools.py` | `health`, `list_styles`, `list_projects`, `inspect_project`, `validate_project`, `_serialize_project`, `_project_status`, `_validation_summary`, `_load_project_config`, `_list_section`, `_outputs`, `_missing_paths`, `_missing_inputs` |
| `hub_core/mcp/tools/render_tools.py` | `render_csv_graph`, `render_project_figure`, `_resolve_project_render_path`, `_project_figure_entries`, `_select_project_figure`, `_figure_selector_summary`, `_public_selected_figure`, `_selected_figure_*`, `_project_relative_path` |
| `hub_core/mcp/tools/project_tools.py` | `scaffold_project`, `normalize_project_structure` |
| `hub_core/mcp/tools/batch_tools.py` | `batch_check`, `collect_artifacts`, `_discover_batch_projects`, `_batch_*`, `_find_job_manifest_path`, `_max_depth`, `_batch_max_projects` |
| `hub_core/mcp/resources.py` | `read_resource`, `_parse_resource_uri`, `_validate_resource_config_path`, `_resource_text`, `_json_resource_text`, `_sanitize_resource_payload`, `_styles_payload`, `_public_manifest*`, `_manifest_*`, `_discover_project_by_id` |
| `hub_core/mcp/prompts.py` | `get_prompt`, `_prompt_payload`, `_prompt_quote`, `_validate_prompt_arguments` |
| `hub_core/mcp/server.py` | `GraphHubMCPServer` façade: `__init__`, `call_tool`, `_envelope`, `_operation_id`, `_read_version`/`_read_version`, `_git_commit`, `_file_sha256`, `_display_path`/`_public_*` path helpers, registry wiring |

(Place shared tiny helpers — `_file_sha256`, `_git_commit`, path-publicizers — in a
`hub_core/mcp/_util.py` if they're used across modules, to avoid a cycle through `server`.)

## Slice plan (one PR per slice; each green before the next)

Extract bottom-up so each slice's dependencies already exist. Within a slice, move code +
re-export from `mcp_surface.py` *only within that PR*, then delete the shim by the slice's end
(no lingering back-compat per repo rules). After **every** slice: `uv run python -m pytest`.

1. **transport.py** — pure JSON-RPC, no domain deps. Lowest risk.
2. **security.py** — path/root/write-gate/env-trust helpers.
3. **schemas.py + registry** — `ToolDefinition`, schema builders, `list_*_definitions`; introduce
   the registry but keep handlers where they are for now (registry points at bound methods).
4. **render_orchestration.py** — workers + render/provenance/snapshot/geometry helpers.
5. **tools/*.py** — move the 11 handlers into their group modules; registry now points at them.
6. **resources.py / prompts.py**.
7. **server.py** — `GraphHubMCPServer` becomes the thin façade; `mcp_surface.py` is deleted and
   `hub_core/mcp/__init__.py` re-exports `GraphHubMCPServer`, `run_stdio_server`,
   `list_tool_definitions` (preserve the public import path used by tests + `figops_mcp_server.py`).

## Constraints

- **Zero behavior change.** No output, error code, envelope, or schema may change. If a move
  *reveals* a bug, file it for M2 — do not fix it inside M1 (keeps the regression oracle valid).
- **Imports:** follow the downward layering in `docs/architecture.md`; no cycles. If two modules
  need a helper, push it down to `_util.py` or a service.
- **Tests:** keep the existing tests passing unchanged. Update only import paths in tests if a
  test imported a private symbol directly (prefer not to; route through the public surface).
- **Run via `uv run`**; new code ruff-clean.

## M1.2 — boundary enforcement (after decomposition)

- Add `docs/architecture.md` layering as a CI guard: an `import-linter` contract pinning the
  downward layering, **and** a module-size check (fail if any `hub_core/**.py` > 800 lines). Wire
  as a new CI job (`Arch`) or into `Test`.
- **Acceptance:** introducing a God script or an upward import fails CI.

## M1.3 — lint debt → ruff gating

- Resolve the ~190 pre-existing ruff findings (E501/F401/F841/I) in per-package PRs. Add type
  hints on public signatures of `hub_core/mcp/` (prefer `str | None`).
- Flip `ci.yml` `Ruff` job from `continue-on-error: true` to gating.
- **Acceptance:** `uv run ruff check .` clean; CI ruff gating.

## M1.4 — coverage on the core

- `uv run python -m pytest --cov=hub_core/mcp` (add `pytest-cov` to the dev group). Fill gaps in
  `transport.py` (batch/lifecycle/framing edge cases) and `security.py` (path-guard rejections,
  write gating, allowed-root validation). Optional: a coverage floor for `hub_core/mcp/` in CI.
- **Acceptance:** documented coverage %; trust-boundary branches covered.

## Definition of done (M1)

- `hub_core/mcp_surface.py` gone; `hub_core/mcp/` populated; no module > 800 lines.
- Full suite green, unchanged behavior; public import path preserved; `figops_mcp_server.py --smoke` works.
- CI: ruff gating + arch/size guard green.
