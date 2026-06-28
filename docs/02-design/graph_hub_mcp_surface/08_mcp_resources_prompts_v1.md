# 08 MCP Resources and Prompts v1

- Status: implementation spec for MCP v1 completion surface
- Depends on:
  - `00_protocol_and_safety_contract.md`
  - `02_phase1_read_only_mcp.md`
  - `03_phase2_controlled_rendering.md`
  - `07_athena_client_migration_workflow.md`

## Goal

Complete FigOps MCP v1 by adding read-only resources and workflow prompts to the existing tool server.

The current MCP surface already exposes tools for health, styles, project discovery, project inspection, validation, controlled CSV rendering, artifact collection, scaffolding, normalization, and bounded batch checks. The missing MCP-native pieces are:

- resource listing and reading for stable Hub context,
- prompt listing and prompt retrieval for reusable graph workflows,
- protocol tests proving tools/resources/prompts can coexist without side effects.

## Why This Matters

Tools are good for actions. Resources and prompts are better for shared context.

FigOps should not require every agent to rediscover style contracts, project config shape, or artifact manifest rules by calling action tools repeatedly. A client should be able to ask for stable context such as `figops://styles`, `figops://projects`, or `figops://jobs/{job_id}/manifest`.

Prompts should give agents a safe workflow template while preserving FigOps ownership. They must guide users through inspect, validate, render, collect, and review without silently normalizing projects or claiming publication readiness.

## MCP Protocol Additions

### JSON-RPC methods

Add support for:

- `resources/list`
- `resources/templates/list`
- `resources/read`
- `prompts/list`
- `prompts/get`

`initialize` must advertise:

```json
{
  "capabilities": {
    "tools": {},
    "resources": {},
    "prompts": {}
  }
}
```

The server must keep existing `tools/list` and `tools/call` behavior unchanged.

### Request Parameter Shapes

`resources/read` accepts:

```json
{
  "uri": "figops://styles"
}
```

`prompts/get` accepts:

```json
{
  "name": "make_publication_graph_from_csv",
  "arguments": {
    "data_path": "results/data/summary.csv",
    "x_column": "x",
    "y_column": "y"
  }
}
```

`arguments` defaults to `{}` when omitted. If present, it must be an object.

### Error Taxonomy

Use JSON-RPC errors consistently:

- malformed params, unsupported scheme, unsupported authority, extra URI path segments, invalid prompt arguments: `-32602`
- syntactically valid but missing resources, unknown project IDs, unknown job manifests, unknown prompt names: `-32002`
- server/internal failures: `-32603`

## Resources

### URI Grammar

V1 supports only these URI forms:

- `figops://styles`
- `figops://profiles`
- `figops://projects`
- `figops://projects/{project_id}/config`
- `figops://jobs/{job_id}/manifest`

Parsing rules:

- the URI scheme must be exactly `graphhub`,
- query strings and fragments are rejected,
- `figops://styles`, `figops://profiles`, and `figops://projects` use the URI authority with an empty path,
- dynamic resources use authority `projects` or `jobs` plus exactly two path segments,
- dynamic path segments are percent-decoded once,
- project IDs may contain `::` because `ProjectDiscoveryService` generates IDs in that shape,
- job IDs in resource URIs are strict: they must already match `[A-Za-z0-9_-]{1,80}` and must not be auto-sanitized or remapped.

### `figops://styles`

Returns FigOps style contract metadata as JSON.

Required fields:

- `target_formats`
- `output_formats`
- `profiles`
- `profile_aliases`
- `default_target_format`
- `default_profile`

Acceptance:

- Includes `internal_style_format`.
- Matches `figops.list_styles` output for the same fields.
- Does not create runtime folders or modify source files.

### `figops://profiles`

Returns profile metadata as JSON.

Required fields:

- `profiles`
- `profile_aliases`
- `default_profile`

Acceptance:

- Matches `themes.style_profiles.list_profiles()`.
- Does not expose unrelated environment/config state.

### `figops://projects`

Returns discovered project metadata as JSON.

Query parameters are not supported in v1. Use the server's configured `research_root`, default max depth, and default exclusions. Custom-root project resources can be added later only after a URI and authorization policy is defined.

Required fields:

- `projects`: same serialized project shape as `figops.list_projects`
- `root`
- `count`

Acceptance:

- Uses `ProjectDiscoveryService`.
- Includes invalid projects with errors.
- Excludes worktrees and ephemeral runtime folders by default.
- Does not run project scripts.

### `figops://projects/{project_id}/config`

Returns the selected project config YAML as text.

Acceptance:

- `project_id` is resolved through `ProjectDiscoveryService`.
- Resolution uses the server's configured `research_root` and default discovery exclusions.
- The returned config is read from the discovered `config_path`, so legacy `scripts/project_config.yaml` projects work.
- Unknown `project_id` returns JSON-RPC resource-not-found error `-32002`.
- The resource result includes MIME type `application/x-yaml`.
- Raw data, PDFs, media, and generated binaries are never read through this resource.
- Symlinked config files, config paths that resolve outside the discovered project root, and configs larger than 1 MiB are rejected with `-32602`.

### `figops://jobs/{job_id}/manifest`

Returns a render job manifest JSON.

Acceptance:

- Reads only from configured runtime-root candidates.
- The resource must use existing job-manifest lookup candidates and must not call runtime-root activation or directory-creating runtime resolution.
- Unknown `job_id` returns JSON-RPC resource-not-found error `-32002`.
- `job_id` must already match `[A-Za-z0-9_-]{1,80}`. Do not call the render job sanitizer for resource lookup, because sanitizer remapping can hide invalid input.
- Result includes MIME type `application/json`.
- The manifest JSON is returned as an LLM-facing sanitized projection. Runtime, research, and Hub roots must be replaced the same way diagnostic text is sanitized. The persisted manifest file itself is not altered.

## Resource Result Shape

`resources/list` returns:

```json
{
  "resources": [
    {
      "uri": "figops://styles",
      "name": "FigOps Styles",
      "description": "Canonical target formats, output formats, profiles, and aliases.",
      "mimeType": "application/json"
    }
  ]
}
```

`resources/templates/list` returns:

```json
{
  "resourceTemplates": [
    {
      "uriTemplate": "figops://projects/{project_id}/config",
      "name": "FigOps Project Config",
      "description": "Project configuration YAML resolved by discovered project ID.",
      "mimeType": "application/x-yaml"
    },
    {
      "uriTemplate": "figops://jobs/{job_id}/manifest",
      "name": "FigOps Render Job Manifest",
      "description": "Sanitized render job manifest resolved by job ID.",
      "mimeType": "application/json"
    }
  ]
}
```

`resources/read` returns:

```json
{
  "contents": [
    {
      "uri": "figops://styles",
      "mimeType": "application/json",
      "text": "{...}"
    }
  ]
}
```

Resource content values that are JSON should be pretty-printed with deterministic key ordering where practical. Project config content remains YAML text.

## Prompts

### `make_publication_graph_from_csv`

Purpose: guide an agent through an explicit CSV graph request.

Arguments:

- `data_path` required
- `x_column` required
- `y_column` required
- `target_format` optional
- `plot_type` optional

The prompt must instruct the client to:

1. call `figops.list_styles` if style support is uncertain,
2. run `figops.render_csv_graph` with `dry_run=true`,
3. inspect `calculation_checks`, `visual_preflight_status`, `failure_stage`, and `resolution_hint`,
4. rerun without `dry_run` only when the dry run is clean or the user accepts warnings,
5. call `figops.collect_artifacts`,
6. never claim publication readiness without manual review when `manual_review_needed=true`.

### `inspect_graph_project_quality`

Purpose: guide project-level inspection without execution.

Arguments:

- `project_id` optional
- `project_path` optional

At least one selector should be provided by the caller.
If neither selector is present, `prompts/get` returns `-32602`.

The prompt must instruct the client to:

1. call `figops.inspect_project`,
2. call `figops.validate_project`,
3. inspect config errors, data contract errors, style errors, missing inputs, missing outputs, and normalization status,
4. avoid rendering or normalization unless the user explicitly asks.

### `standardize_existing_graph_project`

Purpose: guide safe project normalization.

Arguments:

- `project_path` required
- `move_policy` optional

The prompt must instruct the client to:

1. call `figops.inspect_project`,
2. call `figops.normalize_project_structure` with `dry_run=true`,
3. show the manifest and preserve project style choices,
4. apply only after user approval,
5. call `figops.validate_project` after apply.

## Prompt Result Shape

`prompts/list` returns:

```json
{
  "prompts": [
    {
      "name": "make_publication_graph_from_csv",
      "description": "Workflow for rendering a publication-style graph from structured CSV data.",
      "arguments": [
        {"name": "data_path", "required": true}
      ]
    }
  ]
}
```

Prompt argument validation:

- required arguments must be non-empty strings,
- optional arguments, when provided, must be strings,
- unknown prompt arguments are rejected with `-32602`,
- `arguments` must be an object when supplied,
- prompt text generation must escape/interpolate user values only as inert quoted text,
- prompt generation must not check whether paths exist.

`prompts/get` returns:

```json
{
  "description": "Workflow for rendering a publication-style graph from structured CSV data.",
  "messages": [
    {
      "role": "user",
      "content": {
        "type": "text",
        "text": "..."
      }
    }
  ]
}
```

## Safety Rules

- Resource reads must be read-only.
- Prompt retrieval must be read-only.
- Resource URI parsing must reject path traversal, unknown schemes, unknown authorities, and extra path segments.
- `figops://projects/{project_id}/config` must resolve by project ID, not by arbitrary path.
- `figops://jobs/{job_id}/manifest` must strictly validate `job_id` and reject invalid characters instead of remapping them.
- `figops://projects/{project_id}/config` must reject symlinked config files instead of following them.
- No resource may expose `.env`, credentials, raw data files, PDFs, images, or binary output contents in v1.
- Resources may expose manifest JSON and project config YAML because these are graph contract artifacts.
- Prompt arguments must be interpolated as inert text only; prompt generation must not call tools, inspect paths, or validate file existence.

## V1 Scope Reconciliation

Earlier phase documents mention `figops://styles/{target_format}` and `figops://projects/{project_id}/artifacts`.

For this v1 work unit:

- `figops://styles/{target_format}` is deferred because `figops://styles` already exposes all target formats and profile metadata.
- `figops://projects/{project_id}/artifacts` is deferred because reliable project artifact inventory needs a separate inventory-board spec.
- Render job artifacts are represented through `figops://jobs/{job_id}/manifest` plus `figops.collect_artifacts`.

## Non-Goals

- No resource subscriptions.
- No binary image resources in v1.
- No prompt that executes tools automatically.
- No automatic project normalization.
- No Athena client code changes in this work unit.
- No new rendering behavior.

## Acceptance Criteria

- `initialize` advertises `tools`, `resources`, and `prompts`.
- `resources/list` returns stable resources for styles, profiles, and projects.
- `resources/templates/list` returns templates for project config and job manifest resources.
- `resources/read` supports `figops://styles`, `figops://profiles`, `figops://projects`, `figops://projects/{project_id}/config`, and `figops://jobs/{job_id}/manifest`.
- `prompts/list` returns the three v1 prompts.
- `prompts/get` returns a valid MCP prompt message for each v1 prompt.
- Malformed resource URIs and invalid prompt arguments return `-32602`.
- Valid-but-missing resources and unknown prompt names return `-32002`.
- Resource and prompt calls do not create runtime job folders and do not modify source files.
- Existing tool tests continue to pass.

## Verification

Add tests for:

- JSON-RPC `initialize` capabilities include tools/resources/prompts.
- `resources/list` schema and core resource names.
- `resources/templates/list` exposes dynamic project config and job manifest templates.
- `resources/read figops://styles` matches `figops.list_styles`.
- `resources/read figops://projects` uses project discovery and remains read-only.
- `resources/read figops://projects/{project_id}/config` returns YAML for known project ID.
- `resources/read figops://projects/{project_id}/config` reads legacy discovered config paths.
- `resources/read figops://projects/{project_id}/config` rejects symlinked config files.
- `resources/read figops://jobs/{job_id}/manifest` returns a render manifest after a controlled render.
- `resources/read figops://jobs/{job_id}/manifest` sanitizes the original input data path from the returned JSON text.
- malformed resource URI returns `-32602`.
- valid-but-missing resource returns `-32002`.
- non-object JSON-RPC `params` returns `-32602`.
- `prompts/list` returns the three prompt names.
- `prompts/get make_publication_graph_from_csv` returns text that references dry-run render, calculation checks, visual preflight, collect artifacts, and manual review.
- missing required prompt argument returns `-32602`.
- unknown prompt returns `-32002`.
- full core MCP regression remains green.
