"""Conservative static dependency extraction for R scripts.

R does not provide a safe standard AST in the runtime used by FigOps, so this
scanner uses a quote/comment-aware bounded call lexer.  Dynamic expressions and
malformed delimiters remain unresolved findings instead of being guessed.
"""

from __future__ import annotations

import re
from typing import Any

from .dependency_scan_common import _is_external_url, _is_static_local_path

_R_PATH_CALLS = {
    "source",
    "read.csv",
    "read_csv",
    "read.delim",
    "read_delim",
    "read.table",
    "read_table",
    "readr::read_csv",
    "readr::read_delim",
    "readlines",
    "readlines",
    "readr::read_lines",
    "readr::read_rds",
    "readr::read_rda",
    "readr::read_rds",
    "readr::write_csv",
    "readr::write_delim",
    "readr::write_lines",
    "readr::write_rds",
    "readr::write_rds",
    "readr::write_rds",
    "readr::read_file",
    "readr::write_file",
    "readr::read_lines",
    "readr::read_table",
    "readr::read_csv",
    "readr::read_tsv",
    "readr::read_delim",
    "readr::read_fwf",
    "readr::read_log",
    "readr::read_rds",
    "readr::write_csv",
    "readr::write_tsv",
    "readr::write_delim",
    "readr::write_rds",
    "readr::write_excel_csv",
    "readr::write_excel_csv2",
    "readr::write_lines",
    "readr::write_file",
    "readRDS",
    "readLines",
    "load",
    "save",
    "saveRDS",
    "write.csv",
    "write.table",
    "writeLines",
    "file",
    "file.exists",
    "normalizePath",
}
_R_PATH_KEYWORDS = {"file", "path", "file_name", "filename", "name", "description"}
_R_CALL_RE = re.compile(r"(?<![A-Za-z0-9_.])([A-Za-z.][A-Za-z0-9_.]*(?:::[A-Za-z.][A-Za-z0-9_.]*)?)\s*\(")


def _r_scan_state(script_text: str) -> tuple[bool, str | None]:
    """Validate quotes/comments/brackets enough for safe call extraction."""

    stack: list[str] = []
    quote: str | None = None
    escaped = False
    comment = False
    pairs = {
        "(": ")",
        "[": "]",
        "{": "}",
    }
    for char in script_text:
        if comment:
            if char in "\r\n":
                comment = False
            continue
        if quote is not None:
            if quote in {'"', "'"} and escaped:
                escaped = False
            elif quote in {'"', "'"} and char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char == "#":
            comment = True
        elif char in {'"', "'", "`"}:
            quote = char
        elif char in pairs:
            stack.append(char)
        elif char in pairs.values():
            if not stack or pairs[stack.pop()] != char:
                return False, "R delimiters are unbalanced."
    if quote is not None:
        return False, "R string literal is unterminated."
    if stack:
        return False, "R delimiters are unbalanced."
    return True, None


def _r_matching_call(script_text: str, opening: int) -> int | None:
    depth = 1
    quote: str | None = None
    escaped = False
    comment = False
    for index in range(opening + 1, len(script_text)):
        char = script_text[index]
        if comment:
            if char in "\r\n":
                comment = False
            continue
        if quote is not None:
            if quote in {'"', "'"} and escaped:
                escaped = False
            elif quote in {'"', "'"} and char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char == "#":
            comment = True
        elif char in {'"', "'", "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _r_split_arguments(text: str) -> list[str]:
    values: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(text):
        if quote is not None:
            if quote in {'"', "'"} and escaped:
                escaped = False
            elif quote in {'"', "'"} and char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'", "`"}:
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            values.append(text[start:index].strip())
            start = index + 1
    tail = text[start:].strip()
    if tail:
        values.append(tail)
    return values


def _r_string(value: str) -> str | None:
    value = value.strip()
    if len(value) < 2 or value[0] not in {'"', "'"} or value[-1] != value[0]:
        return None
    body = value[1:-1]
    # Keep the evaluator intentionally bounded; R's full string semantics are
    # not needed to identify an explicit path candidate.
    return re.sub(r"\\([\\\"'])", r"\1", body)


def _r_candidates(script_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Extract static R dependency candidates and unresolved findings."""

    valid, reason = _r_scan_state(script_text)
    if not valid:
        return [], [{"kind": "parse_error", "source": "r", "reason": reason or "R source could not be parsed."}], True

    candidates: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    incomplete = False
    for match in _R_CALL_RE.finditer(script_text):
        raw_name = match.group(1)
        name = raw_name.lower()
        canonical = name if "::" not in name else name
        if canonical not in {item.lower() for item in _R_PATH_CALLS} and name.split("::")[-1] not in {
            item.lower() for item in _R_PATH_CALLS
        }:
            continue
        opening = match.end() - 1
        closing = _r_matching_call(script_text, opening)
        if closing is None:
            # The full scanner should already have caught this, but retain a
            # fail-closed diagnostic if a future lexer change misses it.
            return [], [{"kind": "parse_error", "source": "r", "reason": "R call delimiters are unbalanced."}], True
        raw_arguments = _r_split_arguments(script_text[opening + 1 : closing])
        arguments: list[str] = []
        for index, argument in enumerate(raw_arguments):
            named = re.match(r"^\s*([A-Za-z.][A-Za-z0-9_.]*)\s*=\s*(.*)$", argument, re.DOTALL)
            if named:
                if named.group(1).lower() in _R_PATH_KEYWORDS:
                    arguments.append(named.group(2).strip())
            elif index == 0:
                arguments.append(argument.strip())
        if not arguments:
            continue
        found_static = False
        for argument in arguments:
            path = _r_string(argument)
            if path is not None and _is_static_local_path(path):
                line = script_text.count("\n", 0, match.start()) + 1
                candidates.append(
                    {
                        "kind": "path_literal",
                        "path": path.strip(),
                        "source": f"r:{raw_name}",
                        "line": line,
                        "column": match.start(),
                    }
                )
                found_static = True
            elif path is None:
                incomplete = True
                unresolved.append(
                    {
                        "kind": "dynamic_path",
                        "source": f"r:{raw_name}",
                        "line": script_text.count("\n", 0, match.start()) + 1,
                        "reference": argument[:240],
                        "reason": "file path expression is not statically resolvable",
                    }
                )
            else:
                # A recognised R file API with an empty or remote literal is
                # not a clean scan: the reference cannot be represented as a
                # local project dependency, so retain a fail-closed finding.
                incomplete = True
                unresolved.append(
                    {
                        "kind": "external_path" if _is_external_url(path) else "invalid_path_literal",
                        "source": f"r:{raw_name}",
                        "line": script_text.count("\n", 0, match.start()) + 1,
                        "reference": path[:240],
                        "reason": (
                            "path literal names an external URL"
                            if _is_external_url(path)
                            else "path literal is empty"
                        ),
                    }
                )
        if not found_static and arguments:
            incomplete = True
    return candidates, unresolved, incomplete


__all__ = ["_r_candidates"]
