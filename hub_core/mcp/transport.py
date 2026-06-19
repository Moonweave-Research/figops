from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from typing import Any

MCP_MAX_MESSAGE_BYTES = 16 * 1024 * 1024

JSONRPC_INVALID_REQUEST = -32600
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_PARSE_ERROR = -32700
JSONRPC_RESOURCE_NOT_FOUND = -32002

DEFAULT_PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = frozenset({"2024-11-05", "2025-03-26", DEFAULT_PROTOCOL_VERSION})


def run_stdio_server(
    server: Any | None = None,
    *,
    input_stream: Any | None = None,
    output_stream: Any | None = None,
) -> int:
    """Run a JSON-RPC stdio MCP server (newline-delimited or Content-Length framed)."""
    if server is None:
        from hub_core.mcp.server import GraphHubMCPServer

        active_server = GraphHubMCPServer()
    else:
        active_server = server
    in_stream = input_stream or sys.stdin.buffer
    out_stream = output_stream or sys.stdout.buffer

    while True:
        framing = "content-length"
        try:
            request, framing = _read_stdio_message(in_stream)
            if request is None:
                break
            # Keep fd1 pure for framed JSON-RPC: any stray print() inside a handler or a
            # library it calls goes to stderr, never interleaved into the wire response.
            with redirect_stdout(sys.stderr):
                response = _dispatch_json_rpc(active_server, request)
        except _StdioParseError as exc:
            framing = exc.framing
            response = _json_rpc_error(None, JSONRPC_PARSE_ERROR, f"Parse error: {exc.error}")
        except json.JSONDecodeError as exc:
            response = _json_rpc_error(None, JSONRPC_PARSE_ERROR, f"Parse error: {exc}")
        except Exception as exc:
            response = _json_rpc_error(None, JSONRPC_INTERNAL_ERROR, str(exc))
        if response is not None:
            _write_stdio_message(out_stream, response, framing)
    return 0


def _dispatch_json_rpc(
    server: Any, request: dict[str, Any] | list[Any]
) -> dict[str, Any] | list[dict[str, Any]] | None:
    if isinstance(request, list):
        if not request:
            return _json_rpc_error(None, JSONRPC_INVALID_REQUEST, "JSON-RPC batch must not be empty.")
        responses = [response for entry in request if (response := _handle_json_rpc(server, entry)) is not None]
        return responses or None
    return _handle_json_rpc(server, request)


def _handle_json_rpc(server: Any, request: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return _json_rpc_error(None, JSONRPC_INVALID_REQUEST, "JSON-RPC request must be an object.")
    method = request.get("method")
    request_id = request.get("id")
    is_notification = "id" not in request
    if request.get("jsonrpc") != "2.0":
        if is_notification:
            return None
        return _json_rpc_error(request_id, JSONRPC_INVALID_REQUEST, 'JSON-RPC "jsonrpc" must equal "2.0".')
    if not is_notification and not isinstance(request_id, (str, int, type(None))):
        return _json_rpc_error(None, JSONRPC_INVALID_REQUEST, "JSON-RPC id must be a string, integer, or null.")
    if not is_notification and isinstance(request_id, bool):
        return _json_rpc_error(None, JSONRPC_INVALID_REQUEST, "JSON-RPC id must be a string, integer, or null.")
    if is_notification:
        return None
    raw_params = request.get("params")
    if raw_params is None:
        params = {}
    elif isinstance(raw_params, dict):
        params = raw_params
    else:
        return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "JSON-RPC params must be an object when provided.")

    if method == "initialize":
        server.initialized = True
        client_protocol = params.get("protocolVersion")
        protocol_version = (
            client_protocol if client_protocol in SUPPORTED_PROTOCOL_VERSIONS else DEFAULT_PROTOCOL_VERSION
        )
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": "graph-making-hub", "version": server._read_version()},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if server.require_initialize and not server.initialized:
        return _json_rpc_error(request_id, JSONRPC_INVALID_REQUEST, "Server not initialized: call initialize first.")
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": _tool_definitions_for(server)}}
    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        if arguments is None:
            arguments = {}
        handlers = getattr(server, "_handlers", {})
        if not isinstance(tool_name, str) or tool_name not in handlers:
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, f"Unknown tool: {tool_name}")
        if not isinstance(arguments, dict):
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "Tool arguments must be an object.")
        argument_errors = _validate_tool_arguments(tool_name, arguments, _tool_definitions_for(server))
        if argument_errors:
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "; ".join(argument_errors))
        return {"jsonrpc": "2.0", "id": request_id, "result": server.call_tool(tool_name, arguments)}
    if method == "resources/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"resources": _resource_definitions_for(server)}}
    if method == "resources/templates/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"resourceTemplates": _resource_templates_for(server)},
        }
    if method == "resources/read":
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri.strip():
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "Resource uri is required.")
        try:
            result = server.read_resource(uri)
        except ValueError as exc:
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, str(exc))
        except FileNotFoundError as exc:
            return _json_rpc_error(request_id, JSONRPC_RESOURCE_NOT_FOUND, str(exc))
        except Exception as exc:
            return _json_rpc_error(request_id, JSONRPC_INTERNAL_ERROR, str(exc))
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"prompts": _prompt_definitions_for(server)}}
    if method == "prompts/get":
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not name.strip():
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "Prompt name is required.")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, "Prompt arguments must be an object.")
        try:
            result = server.get_prompt(name.strip(), arguments)
        except ValueError as exc:
            return _json_rpc_error(request_id, JSONRPC_INVALID_PARAMS, str(exc))
        except FileNotFoundError as exc:
            return _json_rpc_error(request_id, JSONRPC_RESOURCE_NOT_FOUND, str(exc))
        except Exception as exc:
            return _json_rpc_error(request_id, JSONRPC_INTERNAL_ERROR, str(exc))
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    return _json_rpc_error(request_id, JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}")


def _tool_definitions_for(server: Any) -> list[dict[str, Any]]:
    provider = getattr(server, "list_tool_definitions", None)
    if callable(provider):
        return provider()
    from hub_core.mcp.schemas import list_tool_definitions

    return list_tool_definitions()


def _resource_definitions_for(server: Any) -> list[dict[str, str]]:
    provider = getattr(server, "list_resource_definitions", None)
    if callable(provider):
        return provider()
    from hub_core.mcp.schemas import list_resource_definitions

    return list_resource_definitions()


def _resource_templates_for(server: Any) -> list[dict[str, str]]:
    provider = getattr(server, "list_resource_templates", None)
    if callable(provider):
        return provider()
    from hub_core.mcp.schemas import list_resource_templates

    return list_resource_templates()


def _prompt_definitions_for(server: Any) -> list[dict[str, Any]]:
    provider = getattr(server, "list_prompt_definitions", None)
    if callable(provider):
        return provider()
    from hub_core.mcp.schemas import list_prompt_definitions

    return list_prompt_definitions()


def _validate_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any],
    definitions: list[dict[str, Any]] | None = None,
) -> list[str]:
    if definitions is None:
        definitions = _tool_definitions_for(None)
    for definition in definitions:
        if definition["name"] != tool_name:
            continue
        schema = definition.get("inputSchema", {})
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        errors = [
            f"Missing required tool argument(s): {key}"
            for key in required
            if key not in arguments or not isinstance(arguments.get(key), str) or not arguments.get(key).strip()
        ]
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(arguments) - set(properties))
            if unknown:
                errors.append(f"Unknown tool argument(s): {', '.join(unknown)}")
        one_of = schema.get("oneOf")
        if isinstance(one_of, list) and one_of:
            branches = [branch for branch in one_of if isinstance(branch, dict)]
            satisfied_count = sum(
                1
                for branch in branches
                if all(
                    branch_key in arguments
                    and isinstance(arguments.get(branch_key), str)
                    and arguments.get(branch_key).strip()
                    for branch_key in branch.get("required", [])
                )
            )
            if satisfied_count != 1:
                branch_options = " or ".join(", ".join(branch.get("required", [])) for branch in branches)
                errors.append(f"Must supply exactly one of: {branch_options}.")
        for key, value in arguments.items():
            prop_schema = properties.get(key)
            if isinstance(prop_schema, dict):
                expected_type = prop_schema.get("type")
                if not _matches_json_schema_type(value, expected_type):
                    errors.append(f"Tool argument '{key}' must be {expected_type}.")
                    continue
                errors.extend(_validate_tool_argument_constraints(key, value, prop_schema))
        return errors
    return []


def _enum_contains(value: Any, enum: list[Any]) -> bool:
    # Case-normalized fields (profile, target_format, output_format, plot_type) are
    # lowercased by the handler before use, so match the enum case-insensitively for
    # strings to avoid rejecting mixed-case input the handler would accept.
    if isinstance(value, str):
        normalized = value.strip().lower()
        return any(isinstance(option, str) and option.lower() == normalized for option in enum)
    return value in enum


def _validate_tool_argument_constraints(key: str, value: Any, prop_schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    enum = prop_schema.get("enum")
    if isinstance(enum, list) and not _enum_contains(value, enum):
        allowed = ", ".join(json.dumps(option, ensure_ascii=False) for option in enum)
        errors.append(f"Tool argument '{key}' must be one of: {allowed}.")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = prop_schema.get("minimum")
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) and value < minimum:
            errors.append(f"Tool argument '{key}' must be >= {minimum}.")
        maximum = prop_schema.get("maximum")
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool) and value > maximum:
            errors.append(f"Tool argument '{key}' must be <= {maximum}.")
    if isinstance(value, str):
        min_length = prop_schema.get("minLength")
        if isinstance(min_length, int) and not isinstance(min_length, bool) and len(value) < min_length:
            errors.append(f"Tool argument '{key}' must have length >= {min_length}.")
        max_length = prop_schema.get("maxLength")
        if isinstance(max_length, int) and not isinstance(max_length, bool) and len(value) > max_length:
            errors.append(f"Tool argument '{key}' must have length <= {max_length}.")
    return errors


def _matches_json_schema_type(value: Any, expected_type: Any) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type is None:
        return True
    return False


def _json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class _StdioParseError(Exception):
    """Carries the detected framing so an error reply matches the client's wire format."""

    def __init__(self, error: ValueError, framing: str) -> None:
        super().__init__(str(error))
        self.error = error
        self.framing = framing


def _read_stdio_message(stream: Any) -> tuple[dict[str, Any] | list[Any] | None, str]:
    first_line = stream.readline()
    if first_line == b"" or first_line == "":
        return None, "content-length"
    if isinstance(first_line, str):
        first_line = first_line.encode("utf-8")

    if first_line.lstrip().startswith((b"{", b"[")):
        try:
            return json.loads(first_line.decode("utf-8")), "newline"
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _StdioParseError(exc, "newline") from exc

    headers = _read_headers(stream, first_line)
    content_length = headers.get("content-length")
    if content_length is None:
        raise ValueError("Missing Content-Length header.")
    try:
        expected_size = int(content_length)
    except ValueError as exc:
        raise ValueError(f"Invalid Content-Length header: {content_length}") from exc
    # Reject before reading: a negative size makes stream.read(-1) buffer the whole stream,
    # and an oversized size invites a single huge allocation - both memory-exhaustion DoS.
    if expected_size < 0 or expected_size > MCP_MAX_MESSAGE_BYTES:
        raise ValueError(f"Content-Length out of range: {expected_size} (allowed 0..{MCP_MAX_MESSAGE_BYTES}).")
    body = stream.read(expected_size)
    if isinstance(body, str):
        body = body.encode("utf-8")
    if len(body) != expected_size:
        raise ValueError(f"Incomplete MCP message body: expected {expected_size} bytes, got {len(body)}.")
    return json.loads(body.decode("utf-8")), "content-length"


def _read_headers(stream: Any, first_line: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    line = first_line
    while line not in (b"", b"\n", b"\r\n"):
        text = line.decode("ascii", errors="replace").strip()
        if ":" in text:
            key, value = text.split(":", 1)
            headers[key.lower()] = value.strip()
        line = stream.readline()
        if isinstance(line, str):
            line = line.encode("utf-8")
    return headers


def _write_stdio_message(
    stream: Any, response: dict[str, Any] | list[dict[str, Any]], framing: str = "content-length"
) -> None:
    body = json.dumps(response, ensure_ascii=False).encode("utf-8")
    if framing == "newline":
        payload = body + b"\n"
    else:
        payload = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    stream.write(payload)
    if hasattr(stream, "flush"):
        stream.flush()
