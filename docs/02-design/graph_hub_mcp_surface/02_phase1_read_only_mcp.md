# 02 Phase 1 Read-Only MCP

- Status: Starts after Phase 0 design and parity tests are in place
- Depends on: `00_protocol_and_safety_contract.md`, `01_phase0_truth_surface_repair.md`
- Blocks: Phase 2 rendering

## Goal

Expose Graph Hub state safely to agents without creating files, running project scripts, or modifying workspace state.

Phase 1 proves that MCP can inspect Graph Hub reliably before it is allowed to execute or write anything.

For Athena migration, Phase 1 is the first point where Athena should start consuming Graph Hub through a client surface. Athena should read health, style, project, and validation state from Graph Hub MCP or a compatibility client before any render path is replaced.

## Tools

### `graphhub.health`

Returns Hub server health and configuration.

Result fields:

- `hub_path`
- `version`
- `python_executable`
- `runtime_root`
- `style_format_count`
- `discovery_status`
- `write_tools_enabled`
- `warnings`

Acceptance criteria:

- no files are created or modified,
- no project scripts are executed,
- no generated workspace state files are written.

### `graphhub.list_styles`

Returns available target formats, output formats, style profiles, aliases, and default style.

Result fields:

- `target_formats`
- `output_formats`
- `profiles`
- `profile_aliases`
- `default_target_format`
- `default_profile`

Acceptance criteria:

- includes `nature_surfur`,
- matches Graph Hub core style contract,
- does not hard-code a narrower Athena-only enum.

### `graphhub.list_projects`

Returns discovered project configs.

Inputs:

- `root`: optional scan root, default ResearchOS workspace root
- `include_invalid`: default `true`
- `include_worktrees`: default `false`
- `include_ephemeral`: default `false`
- `max_depth`: bounded integer

Result fields:

- `project_id`
- `project_root`
- `config_path`
- `status`: `valid | invalid | legacy | ephemeral`
- `errors`
- `declared_figures`
- `declared_diagrams`
- `target_format`

Acceptance criteria:

- MCP and CLI discovery use the same underlying implementation,
- symlinked projects are handled intentionally,
- invalid configs are visible with validation messages.

### `graphhub.inspect_project`

Summarizes one project without running it.

Inputs:

- `project_id` or `project_path`

Result fields:

- `project_metadata`
- `folder_structure_status`
- `data_contract_summary`
- `pipeline_steps`
- `figure_outputs`
- `diagram_outputs`
- `missing_inputs`
- `missing_outputs`
- `style_summary`
- `normalization_needed`

### `graphhub.validate_project`

Runs schema and contract checks without executing analysis or plotting scripts.

Inputs:

- `project_id` or `project_path`
- `strict_lock`: default `false`

Result fields:

- `valid`
- `config_errors`
- `data_contract_errors`
- `lockfile_status`
- `style_errors`
- `recommended_next_action`

## Resources

Read-only resources:

```text
graphhub://styles
graphhub://styles/{target_format}
graphhub://profiles
graphhub://projects
graphhub://projects/{project_id}/config
graphhub://projects/{project_id}/artifacts
```

Resources must use validated URIs and MIME types.

## Non-Goals

- No rendering.
- No scaffolding.
- No project normalization.
- No batch execution.
- No resource subscriptions.

## Definition of Done

- Read-only MCP server skeleton exists.
- `graphhub.health`, `graphhub.list_styles`, and `graphhub.list_projects` are implemented first.
- `graphhub.inspect_project` and `graphhub.validate_project` are implemented after project discovery parity is proven.
- All tools return the standard result envelope.
- Every tool has `inputSchema`; structured tools have `outputSchema`.

## Verification

Protocol tests:

- tool listing includes expected read-only tools,
- every tool exposes schema metadata,
- structured results are returned in `structuredContent`,
- execution errors and protocol errors are distinguishable.

No-write tests:

- read-only tools do not change git status,
- read-only tools do not create workspace state files,
- read-only tools do not create runtime job directories,
- health checks do not execute project scripts.

Parity tests:

- `graphhub.list_projects` matches CLI discovery with the same filters.
- `graphhub.list_styles` matches Graph Hub core style contract.
