"""Sanitized provenance for each user-visible FigOps invocation."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

_CONFIG_STATUSES: Final = frozenset({"valid", "invalid", "missing", "unreadable"})


def build_attempt_provenance(
    *,
    surface: str,
    step: str,
    selector_kind: str,
    hub_path: str | Path,
    config_path: str | Path | None = None,
    config_status: str | None = None,
) -> dict[str, object]:
    """Build the stable, path-free attempt record emitted by a CLI or MCP surface."""
    raw_config_sha256, resolved_status, unavailable = _config_provenance(config_path, config_status)
    git_commit = _git_commit(hub_path)
    if not git_commit:
        unavailable.append("git_commit")

    return {
        "attempt_id": uuid.uuid4().hex,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "surface": surface,
        "step": step,
        "selector_kind": selector_kind,
        "git_commit": git_commit,
        "raw_config_sha256": raw_config_sha256,
        "config_status": resolved_status,
        "environment_sha256": _environment_sha256(),
        "python_version": sys.version.split()[0],
        "unavailable_fields": sorted(set(unavailable)),
    }


def update_attempt_provenance(
    attempt: dict[str, object],
    *,
    config_path: str | Path | None,
    config_status: str | None = None,
) -> dict[str, object]:
    """Refresh only configuration-derived fields while retaining one attempt identity."""
    raw_config_sha256, resolved_status, unavailable = _config_provenance(config_path, config_status)
    prior_unavailable = attempt.get("unavailable_fields")
    fields = set(prior_unavailable) if isinstance(prior_unavailable, list) else set()
    fields.discard("raw_config_sha256")
    fields.discard("config_path")
    fields.update(unavailable)
    attempt["raw_config_sha256"] = raw_config_sha256
    attempt["config_status"] = resolved_status
    attempt["unavailable_fields"] = sorted(fields)
    return attempt


def render_attempt_provenance(attempt: Mapping[str, object]) -> str:
    """Return a deterministic line suitable for a human-readable CLI diagnostic."""
    return json.dumps(dict(attempt), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _config_provenance(
    config_path: str | Path | None,
    config_status: str | None,
) -> tuple[str, str, list[str]]:
    if config_status is not None and config_status not in _CONFIG_STATUSES:
        raise ValueError(f"Unsupported config provenance status: {config_status}")
    if config_path is None:
        return "", config_status or "missing", ["raw_config_sha256", "config_path"]

    path = Path(config_path)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return "", config_status or "missing", ["raw_config_sha256"]
    except OSError:
        return "", config_status or "unreadable", ["raw_config_sha256"]
    return hashlib.sha256(raw).hexdigest(), config_status or "valid", []


def _environment_sha256() -> str:
    """Hash the effective environment without persisting its potentially secret values."""
    serialized = "\n".join(f"{key}={value}" for key, value in sorted(os.environ.items()))
    return hashlib.sha256(serialized.encode("utf-8", errors="surrogateescape")).hexdigest()


def _git_commit(hub_path: str | Path) -> str:
    """Read the checked-out commit without spawning a process used by render hooks."""
    try:
        git_marker = Path(hub_path) / ".git"
        git_dir = _git_directory(git_marker)
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref: "):
            reference = head.removeprefix("ref: ").strip()
            head = _read_git_reference(git_dir, reference)
    except OSError:
        return ""
    return head if len(head) == 40 else ""


def _git_directory(marker: Path) -> Path:
    if marker.is_dir():
        return marker
    content = marker.read_text(encoding="utf-8").strip()
    if not content.startswith("gitdir: "):
        raise OSError("Invalid Git directory marker")
    raw_directory = content.removeprefix("gitdir: ").strip()
    return (marker.parent / raw_directory).resolve() if not Path(raw_directory).is_absolute() else Path(raw_directory)


def _read_git_reference(git_dir: Path, reference: str) -> str:
    local_reference = git_dir / reference
    if local_reference.is_file():
        return local_reference.read_text(encoding="utf-8").strip()
    common_dir = _common_git_directory(git_dir)
    return (common_dir / reference).read_text(encoding="utf-8").strip()


def _common_git_directory(git_dir: Path) -> Path:
    common_marker = git_dir / "commondir"
    if not common_marker.is_file():
        return git_dir
    raw_directory = common_marker.read_text(encoding="utf-8").strip()
    return (git_dir / raw_directory).resolve() if not Path(raw_directory).is_absolute() else Path(raw_directory)
