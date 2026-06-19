# Graph Hub MCP Error Taxonomy

Graph Hub MCP uses a small error taxonomy across JSON-RPC protocol errors and
tool `structuredContent` error envelopes. The JSON-RPC `error.code` remains the
protocol-level code. Graph Hub adds stable taxonomy fields so clients do not
need to parse human-readable messages.

## Categories

| Category | Symbolic code | JSON-RPC code | Meaning |
| --- | --- | ---: | --- |
| `validation` | `GRAPHHUB_VALIDATION` | `-32602` | Caller-supplied arguments, config, data contract, or render settings are invalid. |
| `not_found` | `GRAPHHUB_NOT_FOUND` | `-32002` | A requested MCP resource, project, job, data file, or artifact does not exist. |
| `disabled` | `GRAPHHUB_DISABLED` | `-32600` | The requested operation is disabled by server policy, such as the write-tool guard. |
| `internal` | `GRAPHHUB_INTERNAL` | `-32603` | An unexpected Graph Hub, runtime, or handler failure occurred. |

## JSON-RPC Errors

Protocol errors use the standard JSON-RPC shape and include taxonomy data:

```json
{
  "jsonrpc": "2.0",
  "id": 99,
  "error": {
    "code": -32602,
    "message": "Tool argument 'max_depth' must be <= 12.",
    "data": {
      "category": "validation",
      "code": "GRAPHHUB_VALIDATION",
      "jsonrpc_code": -32602
    }
  }
}
```

`error.data.jsonrpc_code` always matches the enclosing JSON-RPC `error.code`.

## Tool Error Envelopes

Tool calls that reach a handler return MCP tool content with `isError=true` and
an error `structuredContent` envelope. Error envelopes include:

```json
{
  "status": "error",
  "errors": ["Write tools are disabled for this Graph Hub MCP server."],
  "error_category": "disabled",
  "error_code": "GRAPHHUB_DISABLED",
  "jsonrpc_code": -32600
}
```

Existing fields such as `status`, `errors`, `failure_stage`, and
`manual_review_needed` remain the primary human-facing diagnostics.
