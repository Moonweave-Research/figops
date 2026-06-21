from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_RAW_INTEGRITY = {
    "manifest": "raw/.raw_manifest.json",
    "mode": "warn",
    "paths": ["raw/"],
}


def raw_integrity_config(config: dict[str, Any]) -> dict[str, Any] | None:
    data_contract = config.get("data_contract", {}) if isinstance(config, dict) else {}
    if not isinstance(data_contract, dict):
        return None
    raw_integrity = data_contract.get("raw_integrity")
    if raw_integrity is None:
        return None
    if not isinstance(raw_integrity, dict):
        return None
    merged = dict(DEFAULT_RAW_INTEGRITY)
    merged.update(raw_integrity)
    if isinstance(merged.get("mode"), str):
        merged["mode"] = merged["mode"].strip().lower()
    if "paths" not in raw_integrity or raw_integrity.get("paths") is None:
        merged["paths"] = list(DEFAULT_RAW_INTEGRITY["paths"])
    return merged


def seal_raw_integrity(project_dir: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(project_dir).resolve()
    raw_cfg = raw_integrity_config(config) or dict(DEFAULT_RAW_INTEGRITY)
    manifest_path = _manifest_path(project_root, raw_cfg)
    files = _collect_hashes(project_root, raw_cfg)
    sealed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "_metadata": {
            "sealed_at": sealed_at,
            "algorithm": "sha256",
        },
        **files,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "manifest_path": str(manifest_path),
        "sealed_at": sealed_at,
        "files": files,
        "file_count": len(files),
    }


def verify_raw_integrity(project_dir: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(project_dir).resolve()
    raw_cfg = raw_integrity_config(config)
    if raw_cfg is None:
        return _empty_result(configured=False)

    try:
        manifest_path = _manifest_path(project_root, raw_cfg)
    except ValueError as exc:
        result = _empty_result(configured=True)
        result.update(
            {
                "mode": str(raw_cfg.get("mode", "warn")),
                "ok": False,
                "errors": [f"raw_integrity configuration error: {exc}"],
            }
        )
        return result
    if not manifest_path.exists():
        result = _empty_result(configured=True)
        result.update(
            {
                "manifest_path": str(manifest_path),
                "mode": str(raw_cfg.get("mode", "warn")),
                "sealed": False,
                "ok": False,
                "errors": [f"raw_integrity manifest not found: {manifest_path}"],
            }
        )
        return result

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result = _empty_result(configured=True)
        result.update(
            {
                "manifest_path": str(manifest_path),
                "mode": str(raw_cfg.get("mode", "warn")),
                "sealed": False,
                "ok": False,
                "errors": [f"raw_integrity manifest could not be read: {exc}"],
            }
        )
        return result

    expected = _manifest_files(manifest)
    try:
        actual = _collect_hashes(project_root, raw_cfg)
    except ValueError as exc:
        result = _empty_result(configured=True)
        result.update(
            {
                "manifest_path": str(manifest_path),
                "mode": str(raw_cfg.get("mode", "warn")),
                "sealed": True,
                "ok": False,
                "sealed_at": _sealed_at(manifest),
                "errors": [f"raw_integrity configuration error: {exc}"],
            }
        )
        return result
    modified = sorted(path for path, digest in expected.items() if path in actual and actual[path] != digest)
    added = sorted(path for path in actual if path not in expected)
    removed = sorted(path for path in expected if path not in actual)
    errors = []
    ok = not (modified or added or removed)
    if not ok:
        errors.append(_drift_message(modified=modified, added=added, removed=removed))

    return {
        "configured": True,
        "sealed": True,
        "ok": ok,
        "manifest_path": str(manifest_path),
        "mode": str(raw_cfg.get("mode", "warn")),
        "sealed_at": _sealed_at(manifest),
        "modified": modified,
        "added": added,
        "removed": removed,
        "errors": errors,
    }


def raw_integrity_drift_message(result: dict[str, Any]) -> str:
    return _drift_message(
        modified=list(result.get("modified", [])),
        added=list(result.get("added", [])),
        removed=list(result.get("removed", [])),
    )


def _empty_result(*, configured: bool) -> dict[str, Any]:
    return {
        "configured": configured,
        "sealed": False,
        "ok": True,
        "manifest_path": "",
        "mode": "",
        "sealed_at": "",
        "modified": [],
        "added": [],
        "removed": [],
        "errors": [],
    }


def _manifest_path(project_root: Path, raw_cfg: dict[str, Any]) -> Path:
    return _project_relative_path(project_root, str(raw_cfg.get("manifest") or DEFAULT_RAW_INTEGRITY["manifest"]))


def _configured_paths(project_root: Path, raw_cfg: dict[str, Any]) -> list[Path]:
    raw_paths = raw_cfg.get("paths") or DEFAULT_RAW_INTEGRITY["paths"]
    if not isinstance(raw_paths, list):
        raw_paths = DEFAULT_RAW_INTEGRITY["paths"]
    return [_project_relative_path(project_root, str(path)) for path in raw_paths]


def _collect_hashes(project_root: Path, raw_cfg: dict[str, Any]) -> dict[str, str]:
    manifest_path = _manifest_path(project_root, raw_cfg)
    files: dict[str, str] = {}
    for configured_path in _configured_paths(project_root, raw_cfg):
        if configured_path.is_file():
            candidates = [configured_path]
        elif configured_path.is_dir():
            candidates = sorted(path for path in configured_path.rglob("*") if path.is_file())
        else:
            candidates = []
        for path in candidates:
            if path.resolve() == manifest_path:
                continue
            rel_path = _project_relative_name(project_root, path)
            files[rel_path] = _sha256_file(path)
    return dict(sorted(files.items()))


def _project_relative_path(project_root: Path, raw_path: str) -> Path:
    normalized = raw_path.strip().replace("\\", "/")
    if not normalized:
        raise ValueError("raw_integrity paths must be non-empty relative paths.")
    if Path(raw_path).is_absolute():
        raise ValueError(f"raw_integrity path must be relative: {raw_path}")
    if ".." in normalized.split("/"):
        raise ValueError(f"raw_integrity path must not contain '..': {raw_path}")
    resolved = (project_root / raw_path).resolve()
    _project_relative_name(project_root, resolved)
    return resolved


def _project_relative_name(project_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"raw_integrity path escapes project root: {path}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_files(manifest: Any) -> dict[str, str]:
    if not isinstance(manifest, dict):
        return {}
    if isinstance(manifest.get("files"), dict):
        return {
            str(path): str(digest)
            for path, digest in manifest["files"].items()
            if isinstance(path, str) and isinstance(digest, str)
        }
    return {
        str(path): str(digest)
        for path, digest in manifest.items()
        if isinstance(path, str) and not path.startswith("_") and isinstance(digest, str)
    }


def _sealed_at(manifest: Any) -> str:
    if not isinstance(manifest, dict):
        return ""
    metadata = manifest.get("_metadata", {})
    if isinstance(metadata, dict) and isinstance(metadata.get("sealed_at"), str):
        return metadata["sealed_at"]
    if isinstance(manifest.get("sealed_at"), str):
        return manifest["sealed_at"]
    return ""


def _drift_message(*, modified: list[str], added: list[str], removed: list[str]) -> str:
    parts = []
    if modified:
        parts.append(f"modified={modified}")
    if added:
        parts.append(f"added={added}")
    if removed:
        parts.append(f"removed={removed}")
    detail = "; ".join(parts) if parts else "no drift"
    return f"raw_integrity drift detected: {detail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seal or verify Graph Hub raw data integrity manifests.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    seal_parser = subparsers.add_parser("seal", help="Write raw integrity manifest for a project.")
    seal_parser.add_argument("project", help="Project root path.")
    args = parser.parse_args(argv)

    if args.command == "seal":
        from hub_core.config_parser import load_config

        config, _config_path, _config_hash = load_config(args.project)
        if not isinstance(config, dict):
            return 1
        result = seal_raw_integrity(args.project, config)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
