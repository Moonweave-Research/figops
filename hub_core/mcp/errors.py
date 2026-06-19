from __future__ import annotations

from dataclasses import dataclass

JSONRPC_INVALID_REQUEST = -32600
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_PARSE_ERROR = -32700
JSONRPC_RESOURCE_NOT_FOUND = -32002


@dataclass(frozen=True)
class McpErrorTaxonomyEntry:
    category: str
    code: str
    jsonrpc_code: int
    description: str


VALIDATION_ERROR = McpErrorTaxonomyEntry(
    category="validation",
    code="GRAPHHUB_VALIDATION",
    jsonrpc_code=JSONRPC_INVALID_PARAMS,
    description="Caller-supplied input, arguments, config, or contract data is invalid.",
)
NOT_FOUND_ERROR = McpErrorTaxonomyEntry(
    category="not_found",
    code="GRAPHHUB_NOT_FOUND",
    jsonrpc_code=JSONRPC_RESOURCE_NOT_FOUND,
    description="A requested MCP resource, project, job, input, or artifact does not exist.",
)
DISABLED_ERROR = McpErrorTaxonomyEntry(
    category="disabled",
    code="GRAPHHUB_DISABLED",
    jsonrpc_code=JSONRPC_INVALID_REQUEST,
    description="The requested operation is disabled by server policy.",
)
INTERNAL_ERROR = McpErrorTaxonomyEntry(
    category="internal",
    code="GRAPHHUB_INTERNAL",
    jsonrpc_code=JSONRPC_INTERNAL_ERROR,
    description="An unexpected Graph Hub or runtime failure occurred.",
)

ERROR_TAXONOMY = {
    entry.category: entry
    for entry in (
        VALIDATION_ERROR,
        NOT_FOUND_ERROR,
        DISABLED_ERROR,
        INTERNAL_ERROR,
    )
}


def taxonomy_entry_for_category(category: str | None) -> McpErrorTaxonomyEntry:
    if category and category in ERROR_TAXONOMY:
        return ERROR_TAXONOMY[category]
    return INTERNAL_ERROR


def taxonomy_entry_for_jsonrpc_code(code: int) -> McpErrorTaxonomyEntry:
    if code == JSONRPC_INTERNAL_ERROR:
        return INTERNAL_ERROR
    if code in {JSONRPC_METHOD_NOT_FOUND, JSONRPC_RESOURCE_NOT_FOUND}:
        return NOT_FOUND_ERROR
    return VALIDATION_ERROR


def taxonomy_entry_for_exception(exc: Exception) -> McpErrorTaxonomyEntry:
    if isinstance(exc, FileNotFoundError):
        return NOT_FOUND_ERROR
    if isinstance(exc, ValueError):
        return VALIDATION_ERROR
    return INTERNAL_ERROR


def infer_tool_error_entry(
    *,
    error_category: str | None = None,
    failure_stage: str | None = None,
    errors: list[str] | None = None,
) -> McpErrorTaxonomyEntry:
    if error_category:
        return taxonomy_entry_for_category(error_category)

    error_text = " ".join(errors or []).lower()
    if any(fragment in error_text for fragment in ("not found", "not a file", "no such file")):
        return NOT_FOUND_ERROR
    if any(fragment in error_text for fragment in ("already exists", " is required", " must ")):
        return VALIDATION_ERROR
    if str(failure_stage or "").upper() in {"CONFIG", "CONTRACT"}:
        return VALIDATION_ERROR
    return INTERNAL_ERROR


def taxonomy_data(entry: McpErrorTaxonomyEntry, *, jsonrpc_code: int | None = None) -> dict[str, int | str]:
    return {
        "category": entry.category,
        "code": entry.code,
        "jsonrpc_code": entry.jsonrpc_code if jsonrpc_code is None else jsonrpc_code,
    }
