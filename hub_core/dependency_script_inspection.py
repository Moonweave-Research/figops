"""Conservative, read-only discovery of script dependencies.

This facade preserves the public scanner API while delegating language-specific
lexing to :mod:`dependency_python_inspection` and
:mod:`dependency_r_inspection`.  The returned mapping is JSON-friendly and
deterministic evidence for review; it never executes or rewrites source files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .dependency_python_inspection import _python_candidates
from .dependency_r_inspection import _r_candidates
from .dependency_scan_common import _deduplicate

_SUPPORTED_SUFFIXES = {".py", ".python", ".r"}
_GROUPING_ROLE_ROOTS = {"scripts", "results"}


def _suffix(value: object, script_path: object = None) -> str:
    """Normalise a language/suffix hint without inferring a role."""

    candidate = value
    if candidate is None and script_path is not None:
        candidate = Path(script_path).suffix
    text = str(candidate or "").strip().lower()
    if text in {"python", "py"}:
        return ".py"
    if text in {"r", ".r"}:
        return ".r"
    if text and not text.startswith("."):
        text = "." + text
    return text


def _explicit_role(path: str, role_roots: Mapping[str, str] | None) -> str | None:
    """Resolve the most-specific declared terminal root, without guessing.

    The v1.1 contract deliberately nests semantic roots below the aggregate
    ``scripts`` and ``results`` roots.  A dependency below
    ``hub_scripts/analysis`` therefore has two lexical matches, but the
    terminal ``analysis_scripts`` declaration is the only actionable one.
    Aggregate roots never clear a blocker by themselves, and equal-depth
    matches remain unresolved.
    """

    if not isinstance(role_roots, Mapping):
        return None
    normalized = path.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
        return None
    normalized = normalized.lstrip("./")
    matches: list[tuple[int, str]] = []
    for role, root in role_roots.items():
        if not isinstance(role, str) or not isinstance(root, str) or not root.strip():
            continue
        if role in _GROUPING_ROLE_ROOTS:
            continue
        prefix = root.replace("\\", "/").strip("/")
        if normalized == prefix or normalized.startswith(prefix + "/"):
            depth = len(tuple(part for part in prefix.split("/") if part))
            matches.append((depth, role))
    if not matches:
        return None
    deepest = max(depth for depth, _ in matches)
    roles = [role for depth, role in matches if depth == deepest]
    return roles[0] if len(roles) == 1 else None


def analyze_dependency_script(
    script: str | Path,
    suffix: str | None = None,
    *,
    language: str | None = None,
    script_path: str | Path | None = None,
    role_roots: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Inspect Python/R source and return deterministic dependency evidence.

    ``role_roots`` is optional and is intentionally an explicit mapping.  A
    path resolves only to the most-specific terminal semantic root; aggregate
    ``scripts``/``results`` roots are excluded and equal-depth matches remain
    unresolved.  Paths matching zero or multiple actionable roots are retained
    in ``hardcoded_unresolved_references`` rather than being assigned a guessed
    role.  Parsing errors return ``inspectable=False`` and
    ``dependency_scan_incomplete=True``; no exception escapes for malformed
    source or an unreadable :class:`~pathlib.Path`.
    """

    source_path = script_path
    if isinstance(script, Path):
        source_path = source_path or script
        if suffix is None:
            suffix = script.suffix
        try:
            script_text = script.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return {
                "inspectable": False,
                "dependency_scan_incomplete": True,
                "static_candidates": [],
                "hardcoded_unresolved_references": [
                    {"kind": "read_error", "source": str(script), "reason": "script could not be read."}
                ],
            }
    elif isinstance(script, str):
        script_text = script
    else:
        return {
            "inspectable": False,
            "dependency_scan_incomplete": True,
            "static_candidates": [],
            "hardcoded_unresolved_references": [
                {"kind": "input_error", "source": "script", "reason": "script source must be text or a Path."}
            ],
        }

    normalized_suffix = _suffix(language or suffix, source_path)
    if normalized_suffix not in _SUPPORTED_SUFFIXES:
        return {
            "inspectable": False,
            "dependency_scan_incomplete": True,
            "static_candidates": [],
            "hardcoded_unresolved_references": [
                {
                    "kind": "unsupported_language",
                    "source": normalized_suffix or "unknown",
                    "reason": "only Python and R source are statically inspectable.",
                }
            ],
        }

    if normalized_suffix == ".py":
        candidates, unresolved, incomplete = _python_candidates(script_text)
    else:
        candidates, unresolved, incomplete = _r_candidates(script_text)

    candidates = _deduplicate(candidates)
    unresolved = _deduplicate(unresolved)

    # A literal path is actionable evidence but remains unresolved until the
    # caller supplies an exact, unambiguous terminal semantic role mapping.
    # Aggregate roots are deliberately excluded and ties remain unresolved.
    # This is the important boundary: the scanner never decides that ``data/``
    # means raw, results, or any other semantic role.
    for candidate in candidates:
        if candidate.get("kind") != "path_literal":
            continue
        path = str(candidate.get("path") or "")
        if _explicit_role(path, role_roots) is not None:
            continue
        unresolved.append(
            {
                "kind": "hardcoded_path",
                "path": path,
                "source": candidate.get("source", ""),
                "line": candidate.get("line", 0),
                "column": candidate.get("column", 0),
                "reason": "hard-coded path has no single explicit declared role mapping",
            }
        )

    return {
        "inspectable": not any(item.get("kind") == "parse_error" for item in unresolved),
        "dependency_scan_incomplete": bool(incomplete),
        "static_candidates": candidates,
        "hardcoded_unresolved_references": _deduplicate(unresolved),
    }


# Descriptive aliases keep the API discoverable for callers that use
# ``inspect`` or ``scan`` terminology while preserving one implementation.
inspect_dependency_script = analyze_dependency_script
scan_dependency_script = analyze_dependency_script
inspect_script_dependencies = analyze_dependency_script

__all__ = [
    "analyze_dependency_script",
    "inspect_dependency_script",
    "scan_dependency_script",
    "inspect_script_dependencies",
]
