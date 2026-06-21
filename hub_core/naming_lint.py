from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_DATE_LIKE_RE = re.compile(r"\d{5,}")


def lint_project_naming(project_path: str | Path) -> dict[str, Any]:
    path = Path(project_path)
    warnings: list[str] = []
    for segment in path.parts:
        warnings.extend(_date_warnings(segment))
        warnings.extend(_control_warnings(segment))
    return {"checked": True, "warnings": warnings}


def empty_naming_lint() -> dict[str, Any]:
    return {"checked": False, "warnings": []}


def _date_warnings(segment: str) -> list[str]:
    warnings = []
    for match in _DATE_LIKE_RE.finditer(segment):
        value = match.group(0)
        if len(value) != 6:
            warnings.append(
                f"Naming lint: folder segment '{segment}' contains date-like stamp '{value}'; "
                "use YYMMDD for lab date stamps."
            )
    return warnings


def _control_warnings(segment: str) -> list[str]:
    lower_segment = segment.lower()
    if "control" in lower_segment and not lower_segment.endswith("_control"):
        return [
            f"Naming lint: control folder segment '{segment}' should use the '*_control' convention.",
        ]
    return []
