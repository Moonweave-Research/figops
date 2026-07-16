"""Resolved trust boundary for disposable FigOps runtime state."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .project_structure_contract import resolve_project_structure
from .structure_contract_types import RESULT_ROLES

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


class RuntimeBoundaryError(RuntimeError):
    """The configured runtime storage violates the external-runtime contract."""


def _resolved(path: str | os.PathLike[str]) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def paths_overlap(left: str | os.PathLike[str], right: str | os.PathLike[str]) -> bool:
    """Return whether either fully resolved path contains the other."""

    left_path = _resolved(left)
    right_path = _resolved(right)
    try:
        common = os.path.commonpath((_key(left_path), _key(right_path)))
    except ValueError:
        return False
    return common in {_key(left_path), _key(right_path)}


def durable_role_roots(
    project_root: str | os.PathLike[str], config: Mapping[str, object] | None
) -> tuple[Path, ...]:
    """Resolve the durable result roots declared by the project contract."""

    if config is None:
        return ()
    root = _resolved(project_root)
    contract = resolve_project_structure(config, project_root=root)
    roles = ("results", *RESULT_ROLES)
    return tuple((root / contract.roots[role]).resolve(strict=False) for role in roles)


def validate_runtime_location(
    runtime_root: str | os.PathLike[str],
    *,
    project_root: str | os.PathLike[str] | None = None,
    config: Mapping[str, object] | None = None,
    durable_roots: Iterable[str | os.PathLike[str]] = (),
) -> Path:
    """Validate external placement without creating the runtime directory."""

    root = _resolved(runtime_root)
    protected: list[tuple[str, Path]] = []
    if project_root is not None:
        project = _resolved(project_root)
        protected.append(("project root", project))
        protected.extend(("durable role root", item) for item in durable_role_roots(project, config))
    protected.extend(("durable role root", _resolved(item)) for item in durable_roots)
    for label, candidate in protected:
        if paths_overlap(root, candidate):
            raise RuntimeBoundaryError(
                f"FigOps runtime root must be external and disjoint from every project and durable role root; "
                f"it overlaps the configured {label}."
            )
    return root


def activate_runtime_root(
    runtime_root: str | os.PathLike[str],
    *,
    project_root: str | os.PathLike[str] | None = None,
    config: Mapping[str, object] | None = None,
    durable_roots: Iterable[str | os.PathLike[str]] = (),
) -> Path:
    """Validate, create, and probe an external runtime root or fail fast."""

    root = validate_runtime_location(
        runtime_root,
        project_root=project_root,
        config=config,
        durable_roots=durable_roots,
    )
    try:
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir():
            raise NotADirectoryError(root)
        probe = root / f".figops-write-probe-{os.getpid()}-{secrets.token_hex(8)}"
        descriptor = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(descriptor, b"figops-runtime-probe\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        probe.unlink()
    except OSError as exc:
        raise RuntimeBoundaryError("FigOps runtime root is missing, invalid, or not writable.") from exc
    return root


def runtime_project_id(project_root: str | os.PathLike[str]) -> str:
    """Return a stable opaque namespace without embedding the user path."""

    digest = hashlib.sha256(_key(_resolved(project_root)).encode("utf-8")).hexdigest()
    return f"project-{digest[:20]}"


def safe_runtime_segment(value: object, *, fallback: str) -> str:
    text = str(value or "").strip()
    return text if _SAFE_SEGMENT.fullmatch(text) else fallback


@dataclass(frozen=True, slots=True)
class RuntimeBoundary:
    root: Path

    @classmethod
    def activate(
        cls,
        root: str | os.PathLike[str],
        *,
        project_root: str | os.PathLike[str] | None = None,
        config: Mapping[str, object] | None = None,
        durable_roots: Iterable[str | os.PathLike[str]] = (),
    ) -> "RuntimeBoundary":
        return cls(
            activate_runtime_root(
                root,
                project_root=project_root,
                config=config,
                durable_roots=durable_roots,
            )
        )

    def child(self, role: str, *parts: object) -> Path:
        segments = [safe_runtime_segment(role, fallback="runtime")]
        segments.extend(safe_runtime_segment(part, fallback="item") for part in parts)
        candidate = self.root.joinpath(*segments)
        if not candidate.resolve(strict=False).is_relative_to(self.root):
            raise RuntimeBoundaryError("Runtime path escaped the configured runtime root.")
        return candidate

    def relative_id(self, path: str | os.PathLike[str]) -> str:
        try:
            return _resolved(path).relative_to(self.root).as_posix()
        except ValueError as exc:
            raise RuntimeBoundaryError("Runtime identifier must be relative to the runtime root.") from exc


__all__ = [
    "RuntimeBoundary",
    "RuntimeBoundaryError",
    "activate_runtime_root",
    "durable_role_roots",
    "paths_overlap",
    "runtime_project_id",
    "safe_runtime_segment",
    "validate_runtime_location",
]
