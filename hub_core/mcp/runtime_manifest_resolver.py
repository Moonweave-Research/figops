"""Strict discovery of one completed-job manifest across runtime roots."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_JOB_KINDS = ("mcp_jobs", "mcp_project_jobs")


@dataclass(frozen=True)
class RuntimeManifestSelection:
    root: Path
    path: Path


class JobManifestResolutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def resolve_unique_job_manifest(
    runtime_roots: Iterable[str | os.PathLike[str]],
    job_id: str,
) -> RuntimeManifestSelection:
    """Return exactly one lexical manifest candidate or fail closed."""

    if _JOB_ID.fullmatch(job_id) is None:
        raise JobManifestResolutionError("JOB_ID_INVALID", "job_id has an invalid format.")
    candidates: list[RuntimeManifestSelection] = []
    seen_roots: set[str] = set()
    for raw_root in runtime_roots:
        try:
            root = Path(raw_root).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        key = os.path.normcase(str(root))
        if key in seen_roots:
            continue
        seen_roots.add(key)
        for kind in _JOB_KINDS:
            path = root / kind / job_id / "manifest.json"
            if os.path.lexists(path):
                candidates.append(RuntimeManifestSelection(root=root, path=path))
    if not candidates:
        raise FileNotFoundError(f"No render manifest exists for job_id {job_id!r}.")
    if len(candidates) != 1:
        raise JobManifestResolutionError(
            "JOB_AMBIGUOUS",
            "The requested job_id exists in more than one runtime job location.",
        )
    return candidates[0]


__all__ = [
    "JobManifestResolutionError",
    "RuntimeManifestSelection",
    "resolve_unique_job_manifest",
]
