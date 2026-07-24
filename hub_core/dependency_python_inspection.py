"""Conservative static dependency extraction for Python scripts.

The scanner is deliberately read-only and bounded: it uses :mod:`ast` to
collect imports and literal arguments to common path APIs, while leaving
dynamic expressions unresolved for caller review.
"""

from __future__ import annotations

import ast
from typing import Any

from .dependency_scan_common import (
    _is_external_url,
    _is_static_local_path,
    _looks_like_path,
)

_PYTHON_PATH_CALLS = {
    "open",
    "path",
    "read_csv",
    "read_table",
    "read_fwf",
    "read_excel",
    "read_json",
    "read_parquet",
    "read_feather",
    "read_pickle",
    "loadtxt",
    "genfromtxt",
    "fromfile",
    "load_workbook",
    "read_text",
    "read_bytes",
    "write_text",
    "write_bytes",
    "savefig",
    "to_csv",
    "to_excel",
    "to_json",
    "to_parquet",
    "to_feather",
}
_PYTHON_LITERAL_PATH_CALLS = _PYTHON_PATH_CALLS - {
    # These are methods on an already selected Path object; their first
    # argument is content, not another path.  Avoid turning ``write_text``
    # labels into dependency candidates.
    "read_text",
    "read_bytes",
    "write_text",
    "write_bytes",
}
_PYTHON_PATH_KEYWORDS = {
    "path",
    "filepath",
    "filename",
    "file",
    "fname",
    "name",
    # Common pandas/numpy/scipy and workbook-loader spellings.  These are
    # path-bearing arguments even when the call has no positional argument.
    "filepath_or_buffer",
    "path_or_buf",
    "fname_or_buf",
    "file_or_buf",
    "io",
}


def _line(node: ast.AST) -> int:
    return int(getattr(node, "lineno", 0) or 0)


def _column(node: ast.AST) -> int:
    return int(getattr(node, "col_offset", 0) or 0)


def _call_name(call: ast.Call) -> str:
    function = call.func
    if isinstance(function, ast.Name):
        return function.id.lower()
    if isinstance(function, ast.Attribute):
        return function.attr.lower()
    return ""


def _constant_path_string(node: ast.AST) -> str | None:
    """Resolve a bounded ``Path("literal")`` wrapper around a path value."""

    direct = _constant_string(node)
    if direct is not None:
        return direct
    if isinstance(node, ast.Call) and _call_name(node) == "path" and node.args:
        return _constant_string(node.args[0])
    return None


def _constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    # A bounded static concatenation is still an explicit literal dependency.
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _constant_string(node.left)
        right = _constant_string(node.right)
        if left is not None and right is not None and len(left) + len(right) <= 4096:
            return left + right
    return None


def _static_assignments(tree: ast.AST) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = _constant_path_string(node.value)
            if value is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            value = _constant_path_string(node.value) if node.value is not None else None
            if value is not None:
                assignments[node.target.id] = value
    return assignments


def _python_candidates(script_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Extract static Python dependency candidates and unresolved findings."""

    try:
        tree = ast.parse(script_text, mode="exec")
    except (SyntaxError, ValueError, TypeError):
        return [], [{"kind": "parse_error", "source": "python", "reason": "Python syntax could not be parsed."}], True

    assignments = _static_assignments(tree)
    candidates: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    incomplete = False

    def add_candidate(kind: str, path: str, node: ast.AST, source: str) -> None:
        text = path.strip()
        if not text:
            return
        candidates.append(
            {
                "kind": kind,
                "path": text,
                "source": source,
                "line": _line(node),
                "column": _column(node),
            }
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add_candidate("import", alias.name, node, "python:import")
        elif isinstance(node, ast.ImportFrom):
            module = "." * int(node.level or 0) + (node.module or "")
            if module:
                add_candidate("import", module, node, "python:from_import")
            elif node.level:
                add_candidate("import", "." * node.level, node, "python:relative_import")

        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name not in _PYTHON_PATH_CALLS:
                continue
            # ``Path.write_text/read_text`` receive content/options, not a
            # path.  Their enclosing ``Path("...")`` call is still visited
            # separately, so only path-bearing methods should inspect a first
            # positional argument here.
            arguments: list[ast.AST] = (
                list(node.args[:1]) if name in _PYTHON_LITERAL_PATH_CALLS else []
            )
            arguments.extend(
                keyword.value
                for keyword in node.keywords
                if keyword.arg is not None and keyword.arg.lower() in _PYTHON_PATH_KEYWORDS
            )
            if not arguments:
                continue
            found_static = False
            for argument in arguments:
                path = _constant_path_string(argument)
                if path is None and isinstance(argument, ast.Name):
                    path = assignments.get(argument.id)
                if path is not None and name in _PYTHON_LITERAL_PATH_CALLS and _is_static_local_path(path):
                    add_candidate("path_literal", path, argument, f"python:{name}")
                    found_static = True
                elif path is None:
                    incomplete = True
                    unresolved.append(
                        {
                            "kind": "dynamic_path",
                            "source": f"python:{name}",
                            "line": _line(argument) or _line(node),
                            "reference": ast.unparse(argument)[:240],
                            "reason": "file path expression is not statically resolvable",
                        }
                    )
                elif name in _PYTHON_LITERAL_PATH_CALLS:
                    # Do not silently discard an empty or remote literal from
                    # a recognised path API.  It cannot be materialised as a
                    # project dependency and therefore remains a blocker.
                    incomplete = True
                    unresolved.append(
                        {
                            "kind": "external_path" if _is_external_url(path) else "invalid_path_literal",
                            "source": f"python:{name}",
                            "line": _line(argument) or _line(node),
                            "reference": path[:240],
                            "reason": (
                                "path literal names an external URL"
                                if _is_external_url(path)
                                else "path literal is empty"
                            ),
                        }
                    )
            if not found_static and not any(_constant_string(argument) is not None for argument in arguments):
                incomplete = True

    # Also retain obvious path literals outside a recognised call.  This is
    # useful for assignments later consumed by a wrapper we cannot evaluate.
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _looks_like_path(node.value):
            add_candidate("path_literal", node.value, node, "python:path_literal")

    return candidates, unresolved, incomplete


__all__ = ["_python_candidates"]
