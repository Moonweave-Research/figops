from __future__ import annotations

import re
from typing import Any

_TOKEN_START_RE = re.compile(r"^(TODO|FIXME|TBD|XXX|\?\?\?)(?:$|[\s:_-])", re.IGNORECASE)
_TOKEN_END_RE = re.compile(r"(?:^|[\s:_-])(TODO|FIXME|TBD|XXX|\?\?\?)$", re.IGNORECASE)
_ANGLE_START_RE = re.compile(r"^<[^<>\n]+>(?:$|[\s:/_-])")
_ANGLE_END_RE = re.compile(r"(?:^|[\s:/_-])<[^<>\n]+>$")


def placeholder_report(config: dict[str, Any]) -> dict[str, Any]:
    placeholders = []
    if isinstance(config, dict):
        _scan_value(config, "", placeholders)
    return {
        "detected": bool(placeholders),
        "strict": forbid_todo_placeholders(config),
        "placeholders": placeholders,
        "paths": [item["path"] for item in placeholders],
    }


def forbid_todo_placeholders(config: dict[str, Any]) -> bool:
    data_contract = config.get("data_contract", {}) if isinstance(config, dict) else {}
    return isinstance(data_contract, dict) and data_contract.get("forbid_todo_placeholders") is True


def placeholder_message(report: dict[str, Any]) -> str:
    return f"Config placeholder(s) detected at: {', '.join(report.get('paths', []))}."


def _scan_value(value: Any, path: str, placeholders: list[dict[str, str]]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = _join_path(path, str(key))
            _scan_value(item, child_path, placeholders)
        return
    if isinstance(value, list):
        for index, item in enumerate(value, 1):
            _scan_value(item, f"{path}[{index}]", placeholders)
        return
    if isinstance(value, str):
        token = _placeholder_token(value)
        if token:
            placeholders.append({"path": path, "value": value, "token": token})


def _join_path(parent: str, key: str) -> str:
    return f"{parent}.{key}" if parent else key


def _placeholder_token(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    start_match = _TOKEN_START_RE.search(stripped)
    if start_match:
        return start_match.group(1).upper()
    end_match = _TOKEN_END_RE.search(stripped)
    if end_match:
        return end_match.group(1).upper()
    if _ANGLE_START_RE.search(stripped) or _ANGLE_END_RE.search(stripped):
        match = re.search(r"<[^<>\n]+>", stripped)
        return match.group(0) if match else "<...>"
    return ""
