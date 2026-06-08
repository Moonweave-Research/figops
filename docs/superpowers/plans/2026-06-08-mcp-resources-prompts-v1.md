# MCP Resources and Prompts v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MCP `resources/*` and `prompts/*` JSON-RPC support to the existing Graph Hub MCP stdio server.

**Architecture:** Keep the current dependency-free JSON-RPC server in `hub_core/mcp_surface.py`. Add small helper functions for resource metadata, resource reading, prompt metadata, prompt rendering, URI parsing, and prompt argument validation without changing existing tool behavior.

**Tech Stack:** Python 3.12, stdlib JSON-RPC framing, `pytest`, existing `GraphHubMCPServer`, existing project discovery and runtime manifest lookup helpers.

---

## File Structure

- Modify: `hub_core/mcp_surface.py`
  - Add `JSONRPC_RESOURCE_NOT_FOUND = -32002`.
  - Add `list_resource_definitions()`.
  - Add `list_resource_templates()`.
  - Add `list_prompt_definitions()`.
  - Add `GraphHubMCPServer.read_resource(uri)`.
  - Add `GraphHubMCPServer.get_prompt(name, arguments)`.
  - Extend `_handle_json_rpc()` for `resources/list`, `resources/templates/list`, `resources/read`, `prompts/list`, and `prompts/get`.
- Modify: `tests/test_mcp_read_only.py`
  - Add protocol tests for resources and prompts.
  - Add no-write tests for resource and prompt calls.
- Keep: `docs/02-design/graph_hub_mcp_surface/08_mcp_resources_prompts_v1.md`
  - Source spec for expected behavior.

## Task 1: Protocol Capabilities and Listings

**Files:**
- Modify: `hub_core/mcp_surface.py`
- Test: `tests/test_mcp_read_only.py`

- [ ] **Step 1: Write failing tests**

Add tests:

```python
def test_json_rpc_initialize_advertises_resources_and_prompts(self):
    server = GraphHubMCPServer()

    response = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 10, "method": "initialize"})

    capabilities = response["result"]["capabilities"]
    self.assertIn("tools", capabilities)
    self.assertIn("resources", capabilities)
    self.assertIn("prompts", capabilities)


def test_json_rpc_resources_and_prompts_list(self):
    server = GraphHubMCPServer()

    resources = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 11, "method": "resources/list"})
    templates = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 12, "method": "resources/templates/list"})
    prompts = _handle_json_rpc(server, {"jsonrpc": "2.0", "id": 13, "method": "prompts/list"})

    self.assertIn("graphhub://styles", {item["uri"] for item in resources["result"]["resources"]})
    self.assertIn(
        "graphhub://projects/{project_id}/config",
        {item["uriTemplate"] for item in templates["result"]["resourceTemplates"]},
    )
    self.assertIn("make_publication_graph_from_csv", {item["name"] for item in prompts["result"]["prompts"]})
```

- [ ] **Step 2: Run RED**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_read_only.py::ReadOnlyMCPTest::test_json_rpc_initialize_advertises_resources_and_prompts tests/test_mcp_read_only.py::ReadOnlyMCPTest::test_json_rpc_resources_and_prompts_list -q
```

Expected: fail because resources/prompts methods are not implemented and initialize only advertises tools.

- [ ] **Step 3: Implement listings**

Add list helpers and JSON-RPC branches. Keep existing tool methods unchanged.

- [ ] **Step 4: Run GREEN**

Run the same focused tests. Expected: pass.

## Task 2: Static Resources

**Files:**
- Modify: `hub_core/mcp_surface.py`
- Test: `tests/test_mcp_read_only.py`

- [ ] **Step 1: Write failing tests**

Add tests for:

```python
def test_resources_read_styles_matches_list_styles(self):
    server = GraphHubMCPServer()

    resource = _handle_json_rpc(
        server,
        {"jsonrpc": "2.0", "id": 20, "method": "resources/read", "params": {"uri": "graphhub://styles"}},
    )
    styles = server.call_tool("graphhub.list_styles", {})["structuredContent"]
    payload = json.loads(resource["result"]["contents"][0]["text"])

    self.assertEqual(resource["result"]["contents"][0]["mimeType"], "application/json")
    self.assertEqual(payload["target_formats"], styles["target_formats"])
    self.assertIn("nature_surfur", payload["target_formats"])
```

- [ ] **Step 2: Run RED**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_read_only.py::ReadOnlyMCPTest::test_resources_read_styles_matches_list_styles -q
```

- [ ] **Step 3: Implement static resource reads**

Implement `graphhub://styles` and `graphhub://profiles`.

- [ ] **Step 4: Run GREEN**

Run the focused test plus full `tests/test_mcp_read_only.py`.

## Task 3: Project and Job Resources

**Files:**
- Modify: `hub_core/mcp_surface.py`
- Test: `tests/test_mcp_read_only.py`

- [ ] **Step 1: Write failing tests**

Add tests for:

- `graphhub://projects` returns JSON with `projects`, `root`, and `count`.
- `graphhub://projects/{project_id}/config` reads discovered `config_path`, including legacy `scripts/project_config.yaml`.
- `graphhub://jobs/{job_id}/manifest` returns a sanitized manifest after a controlled render.
- malformed URI returns `-32602`.
- valid-but-missing resource returns `-32002`.

- [ ] **Step 2: Run RED**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_read_only.py -q
```

Expected: new resource tests fail.

- [ ] **Step 3: Implement dynamic resources**

Use strict URI parsing:

- scheme must be `graphhub`,
- no query or fragment,
- static resources use URI authority only,
- project config resource uses authority `projects` and path `/{project_id}/config`,
- job manifest resource uses authority `jobs` and path `/{job_id}/manifest`,
- job IDs must match `[A-Za-z0-9_-]{1,80}`.

Use the discovered project object's `config_path`. Use existing `_find_job_manifest_path()` for job manifests and do not activate/create runtime roots.

- [ ] **Step 4: Run GREEN**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_read_only.py tests/test_mcp_rendering.py -q
```

Expected: pass.

## Task 4: Prompts

**Files:**
- Modify: `hub_core/mcp_surface.py`
- Test: `tests/test_mcp_read_only.py`

- [ ] **Step 1: Write failing tests**

Add tests for:

- `prompts/list` returns three v1 prompt names.
- `prompts/get make_publication_graph_from_csv` includes dry-run render, `calculation_checks`, `visual_preflight_status`, `graphhub.collect_artifacts`, and manual review.
- missing required prompt arguments return `-32602`.
- unknown prompt returns `-32002`.
- prompt calls do not create runtime job folders.

- [ ] **Step 2: Run RED**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_read_only.py -q
```

- [ ] **Step 3: Implement prompt list/get**

Use static prompt definitions and strict argument validation. Prompt generation must interpolate user values as inert text and must not inspect paths.

- [ ] **Step 4: Run GREEN**

Run:

```bash
python hub_uv.py run python -m pytest tests/test_mcp_read_only.py -q
```

## Task 5: Verification and Commit

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run related tests**

```bash
python hub_uv.py run python -m pytest tests/test_mcp_read_only.py tests/test_mcp_rendering.py tests/test_mcp_batch_quality.py tests/test_mcp_normalization.py -q
```

- [ ] **Step 2: Run ruff**

```bash
python hub_uv.py run --with ruff python -m ruff check hub_core/mcp_surface.py tests/test_mcp_read_only.py
```

- [ ] **Step 3: Run full core regression**

```bash
python hub_uv.py run python -m pytest tests/test_mcp_rendering.py tests/test_mcp_batch_quality.py tests/test_mcp_read_only.py tests/test_project_discovery.py tests/test_mcp_normalization.py tests/test_data_contract_new.py tests/test_data_contract_quality.py -q
```

- [ ] **Step 4: Commit and push**

```bash
git add docs/02-design/graph_hub_mcp_surface/08_mcp_resources_prompts_v1.md docs/superpowers/plans/2026-06-08-mcp-resources-prompts-v1.md hub_core/mcp_surface.py tests/test_mcp_read_only.py
git commit -m "feat: add mcp resources and prompts"
git push origin main
```

## Self-Review

- Spec coverage: covers resources/list, resources/templates/list, resources/read, prompts/list, prompts/get, error taxonomy, no-write rules, and tests.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: uses existing `GraphHubMCPServer`, `_handle_json_rpc`, and `tests/test_mcp_read_only.py` patterns.
