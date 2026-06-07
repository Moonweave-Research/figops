# 00 Protocol and Safety Contract

- Status: Required cross-cutting contract
- Applies to: every Graph Hub MCP work unit
- Implementation order: define this before writing any MCP tool

## Purpose

This document defines the protocol and safety rules that every Graph Hub MCP tool, resource, and prompt must obey.

MCP tools are model-callable, so they need stricter boundaries than the existing CLI. The server must expose Graph Hub capability without making it easy for an agent to write into the wrong project, leak sensitive paths, run unbounded jobs, or treat a syntactically created graph as publication-ready.

## Ownership Contract

Graph Hub owns the graph contract:

- project discovery,
- `project_config.yaml` validation,
- target format and profile definitions,
- rendering execution,
- provenance and artifact manifests,
- graph quality status.

Athena and other agents are clients of this contract. They may request graphs, inspect Hub state, or consume artifact resources, but they must not narrow Graph Hub's style set or duplicate project discovery rules as a separate source of truth.

The existing Athena bridge remains a compatibility adapter during migration. It should be replaced only after MCP parity tests prove equivalent behavior. Existing Graph Hub code that imports Athena should be treated as optional or transitional, not as required core graph behavior.

## MCP Server Capabilities

The server should declare:

- `tools` for callable operations,
- `resources` for read-only Hub context,
- `prompts` only after reusable workflows are implemented.

Do not enable resource subscriptions until change notifications are actually implemented.

## Tool Definition Contract

Every tool must define:

- `inputSchema`,
- `outputSchema` when the tool returns structured results,
- bounded timeout behavior,
- explicit error taxonomy,
- stable result envelope.

Structured results must be returned in `structuredContent`. For compatibility, the same structured JSON should also be available as serialized text content.

Execution failures from valid tool calls should use MCP tool execution errors with `isError: true`. Protocol-level errors should be reserved for unknown tools, invalid arguments, and server failures.

## Standard Result Envelope

All structured tool results must include:

```text
status: ok | warning | error
operation_id: stable identifier for this call
is_dry_run: boolean
summary: short human-readable result
created_paths: list
modified_paths: list
skipped_paths: list
artifact_resources: list of graphhub:// or file:// resource links
warnings: list
errors: list
manual_review_needed: boolean
```

Write and execute tools may add fields, but they must keep this envelope so clients and agents can reason about results consistently.

## Path Safety Rules

Minimum safety rules:

- all input paths must be normalized before use,
- reads must stay inside configured allowed roots unless an explicit external input path is allowed,
- writes must stay inside either a declared project root or the external runtime root,
- write tools must return a manifest of created, modified, and skipped paths,
- write tools must refuse to overwrite existing files unless an explicit overwrite flag is set,
- symlinks may be followed for discovery but must not allow writes to escape the allowed write root,
- tool calls must have bounded timeouts and file-size limits,
- raw data, credentials, environment files, PDFs, media, and binary assets must not be read into tool output unless the user explicitly asks for that asset class,
- tool outputs must sanitize absolute paths, environment values, and stderr content before returning them to an LLM-facing client.

## Read-Only Side-Effect Rule

Read-only MCP tools must not reuse side-effectful health/report flows that write `workspace_state.md`, `workspace_state.json`, bridge jobs, cache folders, or timestamp-only report updates. If a report is useful, it must be generated only by an explicit write/report tool and returned with a manifest.

## Runtime Root

MCP-generated temporary work should go under an external runtime root, not under arbitrary source folders by default.

Default:

```text
$RESEARCH_HUB_RUNTIME_ROOT/mcp_jobs/
```

Fallback:

```text
~/Library/Caches/research-hub/mcp_jobs/
```

The MCP server must not create `.venv`, `.r_libs`, DVC state, or long-lived cache directories inside source project trees.

## Resource Requirements

Suggested resources:

```text
graphhub://styles
graphhub://styles/{target_format}
graphhub://profiles
graphhub://projects
graphhub://projects/{project_id}/config
graphhub://projects/{project_id}/artifacts
graphhub://jobs/{job_id}/manifest
```

Requirements:

- each resource must declare a MIME type,
- resource templates must use valid URI templates,
- binary artifacts such as PNG previews must be returned as binary resource contents or file/resource links, not embedded as arbitrary text,
- `graphhub://` resource URIs must be validated before reading,
- resources exposing project configs or manifests should include `lastModified` metadata when available.

## Prompt Requirements

Suggested prompts:

- `standardize_existing_graph_project`
- `make_publication_graph_from_csv`
- `inspect_graph_project_quality`
- `prepare_manuscript_figure_batch`

Requirements:

- prompts are user-invoked workflow templates, not background automation,
- prompt arguments must be validated before composing messages,
- prompts should embed or reference resources instead of copying large file contents into the prompt,
- prompts must clearly separate inspect, plan, and apply steps.

## Definition of Done

- Shared result envelope models exist.
- Path normalization and allowed-root helpers exist.
- Error taxonomy is defined.
- MCP tool tests can assert `inputSchema`, `outputSchema`, `structuredContent`, and `isError` behavior.
- No write-capable tool bypasses this contract.

## Verification

- Unit tests cover result envelope serialization.
- Unit tests cover path traversal, symlink escape, overwrite refusal, timeout, and file-size policy.
- Protocol contract tests cover schemas, structured content, and execution error handling.
