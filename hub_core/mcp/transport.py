from __future__ import annotations

import json
import re
import sys
from contextlib import redirect_stdout
from typing import Any

from hub_core.mcp.errors import (
    JSONRPC_INTERNAL_ERROR,
    JSONRPC_INVALID_PARAMS,
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    JSONRPC_RESOURCE_NOT_FOUND,
    taxonomy_data,
    taxonomy_entry_for_jsonrpc_code,
)

MCP_MAX_MESSAGE_BYTES = 16 * 1024 * 1024
MCP_MAX_HEADER_BYTES = 8 * 1024
MCP_MAX_HEADER_COUNT = 64

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
        from hub_core.mcp.server import FigOpsMCPServer

        active_server = FigOpsMCPServer()
    else:
        active_server = server
    in_stream = input_stream or sys.stdin.buffer
    out_stream = output_stream or sys.stdout.buffer

    while True:
        framing = "content-length"
        terminate_after_response = False
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
            terminate_after_response = exc.fatal
        except json.JSONDecodeError as exc:
            response = _json_rpc_error(None, JSONRPC_PARSE_ERROR, f"Parse error: {exc}")
        except Exception as exc:
            response = _json_rpc_error(None, JSONRPC_INTERNAL_ERROR, str(exc))
        if response is not None:
            _write_stdio_message(out_stream, response, framing)
        if terminate_after_response:
            return 1
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
                "serverInfo": {"name": "figops", "version": server._read_version()},
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
    validation_names = {tool_name}
    if tool_name.startswith("graphhub."):
        validation_names.add(tool_name.replace("graphhub.", "figops.", 1))
    if definitions is None:
        definitions = _tool_definitions_for(None)
    elif not any(definition.get("name") in validation_names for definition in definitions):
        # Discovery profiles intentionally omit tools to keep the LLM context
        # bounded, while the compatibility handler registry remains callable.
        # A guessed/compatibility-hidden canonical name must still be validated
        # against its real schema before dispatch; omission is never a schema
        # bypass.
        definitions = _tool_definitions_for(None)
    for definition in definitions:
        if definition["name"] not in validation_names:
            continue
        schema = definition.get("inputSchema", {})
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        errors = [
            f"Missing required tool argument(s): {key}"
            for key in required
            if key not in arguments or not _required_tool_argument_present(arguments.get(key), properties.get(key, {}))
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
                errors.extend(_validate_schema_value(key, value, prop_schema))
        return errors
    return []


def _required_tool_argument_present(value: Any, prop_schema: dict[str, Any]) -> bool:
    expected_type = prop_schema.get("type") if isinstance(prop_schema, dict) else None
    if expected_type == "string":
        return isinstance(value, str) and bool(value.strip())
    if expected_type == "array":
        return isinstance(value, list) and bool(value)
    if expected_type == "object":
        return isinstance(value, dict) and bool(value)
    return value is not None


def _enum_contains(value: Any, enum: list[Any]) -> bool:
    # Case-normalized fields (profile, target_format, output_format, plot_type) are
    # lowercased by the handler before use, so match the enum case-insensitively for
    # strings to avoid rejecting mixed-case input the handler would accept.
    if isinstance(value, str):
        normalized = value.strip().lower()
        return any(isinstance(option, str) and option.lower() == normalized for option in enum)
    if isinstance(value, bool):
        return any(isinstance(option, bool) and option is value for option in enum)
    if isinstance(value, (int, float)):
        return any(
            isinstance(option, (int, float)) and not isinstance(option, bool) and option == value
            for option in enum
        )
    return any(type(option) is type(value) and option == value for option in enum)


def _validate_schema_value(key: str, value: Any, schema: dict[str, Any]) -> list[str]:
    expected_type = schema.get("type")
    if not _matches_json_schema_type(value, expected_type):
        return [f"Tool argument '{key}' must be {expected_type}."]
    return _validate_tool_argument_constraints(key, value, schema)


def _validate_tool_argument_constraints(key: str, value: Any, prop_schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    any_of = prop_schema.get("anyOf")
    if isinstance(any_of, list) and any_of:
        branches = [branch for branch in any_of if isinstance(branch, dict)]
        if not branches or not any(not _validate_schema_value(key, value, branch) for branch in branches):
            errors.append(f"Tool argument '{key}' must match at least one allowed schema.")
    one_of = prop_schema.get("oneOf")
    if isinstance(one_of, list) and one_of:
        branches = [branch for branch in one_of if isinstance(branch, dict)]
        matches = sum(not _validate_schema_value(key, value, branch) for branch in branches)
        if not branches or matches != 1:
            errors.append(f"Tool argument '{key}' must match exactly one allowed schema.")
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
        exclusive_minimum = prop_schema.get("exclusiveMinimum")
        if (
            isinstance(exclusive_minimum, (int, float))
            and not isinstance(exclusive_minimum, bool)
            and value <= exclusive_minimum
        ):
            errors.append(f"Tool argument '{key}' must be > {exclusive_minimum}.")
        exclusive_maximum = prop_schema.get("exclusiveMaximum")
        if (
            isinstance(exclusive_maximum, (int, float))
            and not isinstance(exclusive_maximum, bool)
            and value >= exclusive_maximum
        ):
            errors.append(f"Tool argument '{key}' must be < {exclusive_maximum}.")
    if isinstance(value, str):
        min_length = prop_schema.get("minLength")
        if isinstance(min_length, int) and not isinstance(min_length, bool) and len(value) < min_length:
            errors.append(f"Tool argument '{key}' must have length >= {min_length}.")
        max_length = prop_schema.get("maxLength")
        if isinstance(max_length, int) and not isinstance(max_length, bool) and len(value) > max_length:
            errors.append(f"Tool argument '{key}' must have length <= {max_length}.")
        pattern = prop_schema.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            errors.append(f"Tool argument '{key}' does not match its required pattern.")
    if isinstance(value, dict):
        properties = prop_schema.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        required = prop_schema.get("required")
        if isinstance(required, list):
            for child_key in required:
                child_schema = properties.get(child_key, {})
                if child_key not in value or not _required_tool_argument_present(value.get(child_key), child_schema):
                    errors.append(f"Missing required tool argument(s): {key}.{child_key}")
        additional = prop_schema.get("additionalProperties")
        if additional is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                errors.append(f"Unknown tool argument(s): {', '.join(f'{key}.{item}' for item in unknown)}")
        for child_key, child_value in value.items():
            child_schema = properties.get(child_key)
            if child_schema is None and isinstance(additional, dict):
                child_schema = additional
            if not isinstance(child_schema, dict):
                continue
            child_path = f"{key}.{child_key}"
            errors.extend(_validate_schema_value(child_path, child_value, child_schema))
    if isinstance(value, list):
        min_items = prop_schema.get("minItems")
        max_items = prop_schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append(f"Tool argument '{key}' must contain at least {min_items} item(s).")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(f"Tool argument '{key}' must contain at most {max_items} item(s).")
        if prop_schema.get("uniqueItems") is True:
            serialized = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value]
            if len(serialized) != len(set(serialized)):
                errors.append(f"Tool argument '{key}' must contain unique items.")
        item_schema = prop_schema.get("items")
        if isinstance(item_schema, dict):
            for index, child in enumerate(value):
                child_path = f"{key}[{index}]"
                errors.extend(_validate_schema_value(child_path, child, item_schema))
    return errors


def _matches_json_schema_type(value: Any, expected_type: Any) -> bool:
    if isinstance(expected_type, list):
        return bool(expected_type) and all(isinstance(item, str) for item in expected_type) and any(
            _matches_json_schema_type(value, item) for item in expected_type
        )
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
    if expected_type == "null":
        return value is None
    if expected_type is None:
        return True
    return False


def _json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    entry = taxonomy_entry_for_jsonrpc_code(code)
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message, "data": taxonomy_data(entry, jsonrpc_code=code)},
    }


class _StdioParseError(ValueError):
    """Carries the detected framing so an error reply matches the client's wire format."""

    def __init__(self, error: ValueError, framing: str, *, fatal: bool = False) -> None:
        super().__init__(str(error))
        self.error = error
        self.framing = framing
        self.fatal = fatal


def _read_stdio_message(stream: Any) -> tuple[dict[str, Any] | list[Any] | None, str]:
    first_line = stream.readline(MCP_MAX_MESSAGE_BYTES + 2)
    if first_line == b"" or first_line == "":
        return None, "content-length"
    if isinstance(first_line, str):
        first_line = first_line.encode("utf-8")

    if first_line.lstrip().startswith((b"{", b"[")):
        encoded_payload = first_line.rstrip(b"\r\n")
        if len(encoded_payload) > MCP_MAX_MESSAGE_BYTES:
            raise _StdioParseError(
                ValueError(f"newline MCP message exceeds {MCP_MAX_MESSAGE_BYTES}-byte limit."),
                "newline",
                fatal=True,
            )
        try:
            return json.loads(first_line.decode("utf-8")), "newline"
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _StdioParseError(exc, "newline") from exc

    try:
        headers = _read_headers(stream, first_line)
        content_length = headers.get("content-length")
        if content_length is None:
            raise ValueError("Missing Content-Length header.")
        expected_size = int(content_length)
        # Reject before reading: a negative size makes stream.read(-1) buffer the whole stream,
        # and an oversized size invites a single huge allocation - both memory-exhaustion DoS.
        if expected_size < 0 or expected_size > MCP_MAX_MESSAGE_BYTES:
            raise ValueError(f"Content-Length out of range: {expected_size} (allowed 0..{MCP_MAX_MESSAGE_BYTES}).")
    except ValueError as exc:
        raise _StdioParseError(exc, "content-length", fatal=True) from exc
    body = stream.read(expected_size)
    if isinstance(body, str):
        body = body.encode("utf-8")
    if len(body) != expected_size:
        raise ValueError(f"Incomplete MCP message body: expected {expected_size} bytes, got {len(body)}.")
    return json.loads(body.decode("utf-8")), "content-length"


def _read_headers(stream: Any, first_line: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    line = first_line
    total_bytes = 0
    header_count = 0
    while line not in (b"", b"\n", b"\r\n"):
        if len(line) > MCP_MAX_HEADER_BYTES:
            raise ValueError(f"MCP header line exceeds {MCP_MAX_HEADER_BYTES}-byte limit.")
        total_bytes += len(line)
        header_count += 1
        if total_bytes > MCP_MAX_HEADER_BYTES or header_count > MCP_MAX_HEADER_COUNT:
            raise ValueError("MCP headers exceed the configured size or count limit.")
        text = line.decode("ascii", errors="replace").strip()
        if ":" in text:
            key, value = text.split(":", 1)
            headers[key.lower()] = value.strip()
        line = stream.readline(MCP_MAX_HEADER_BYTES + 1)
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
