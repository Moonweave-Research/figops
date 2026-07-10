"""Bounded, schema-minimal readers for persisted MCP JSON manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MCP_MAX_RUNTIME_MANIFEST_BYTES = 16 * 1024 * 1024


def read_json_object_file(path: str | Path, *, max_bytes: int = MCP_MAX_RUNTIME_MANIFEST_BYTES) -> dict[str, Any]:
    """Read a bounded UTF-8 JSON object without exposing file contents on failure."""
    if max_bytes <= 0:
        raise ValueError("Manifest byte limit must be positive.")
    manifest_path = Path(path)
    try:
        if not manifest_path.is_file():
            raise ValueError("Manifest must be a regular file.")
        if manifest_path.stat().st_size > max_bytes:
            raise ValueError(f"Manifest exceeds the {max_bytes}-byte limit.")
        with manifest_path.open("rb") as handle:
            payload = handle.read(max_bytes + 1)
    except OSError as exc:
        raise ValueError("Manifest could not be read safely.") from exc
    if len(payload) > max_bytes:
        raise ValueError(f"Manifest exceeds the {max_bytes}-byte limit.")
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Manifest is not valid UTF-8.") from exc
    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ValueError("Manifest is not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Manifest JSON value must be an object.")
    return parsed


def resolve_runtime_manifest_file(runtime_root: str | Path, candidate: str | Path) -> Path:
    """Resolve a discovered manifest only when every component stays non-symlinked in root."""
    root = Path(runtime_root).expanduser().resolve()
    raw_candidate = Path(candidate).expanduser()
    try:
        relative = raw_candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Discovered manifest must stay under the runtime root.") from exc
    current = root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError("Discovered manifest must not include symlinked path components.")
    try:
        resolved = raw_candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Discovered manifest is unavailable.") from exc
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("Discovered manifest must be a regular file inside the runtime root.")
    return resolved
