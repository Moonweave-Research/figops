from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .config_parser import DEFAULT_PROJECT_ROLE, project_role
from .external_raw import ExternalRawError, validate_external_raw_descriptors
from .project_paths import (
    normalize_project_relative_path,
    open_verified_project_input,
    project_path_has_symlink_component,
    resolve_project_input,
    snapshot_project_input,
)

DEFAULT_RAW_INTEGRITY = {
    "manifest": "raw/.raw_manifest.json",
    "mode": "warn",
    "paths": ["raw/"],
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NO_RAW_KEYS = frozenset({"type", "reason"})
_EXTERNAL_PREFIX = "external_raw:"


@dataclass(frozen=True, slots=True)
class RawDependencyGraph:
    """Filesystem-independent summary plus local raw manifest membership."""

    producers: tuple[str, ...]
    raw_members: tuple[str, ...]
    external_raw_ids: tuple[str, ...]
    unresolved_inputs: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def nonempty(self) -> bool:
        return bool(self.producers)

    @property
    def has_raw_terminal(self) -> bool:
        return bool(self.raw_members or self.external_raw_ids)


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
    if "mode" not in raw_integrity or raw_integrity.get("mode") is None:
        merged["mode"] = "strict" if project_role(config) == DEFAULT_PROJECT_ROLE else DEFAULT_RAW_INTEGRITY["mode"]
    if isinstance(merged.get("mode"), str):
        merged["mode"] = merged["mode"].strip().lower()
    if "paths" not in raw_integrity or raw_integrity.get("paths") is None:
        merged["paths"] = list(DEFAULT_RAW_INTEGRITY["paths"])
    return merged


def seal_raw_integrity(project_dir: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(project_dir).resolve()
    raw_cfg = raw_integrity_config(config) or dict(DEFAULT_RAW_INTEGRITY)
    mode = str(raw_cfg.get("mode", "warn"))
    manifest_declaration = str(raw_cfg.get("manifest") or DEFAULT_RAW_INTEGRITY["manifest"])
    if project_path_has_symlink_component(
        project_root,
        manifest_declaration,
        purpose="raw_integrity manifest",
    ):
        raise ValueError("raw_integrity manifest must not contain symlink or reparse-point components")
    graph = derive_raw_dependency_graph(project_root, config, raw_cfg=raw_cfg)
    no_raw_ok, no_raw_error = _validated_no_raw_exception(raw_cfg, graph, project_root)
    if mode == "strict":
        graph_errors = _strict_graph_errors(graph, no_raw_ok=no_raw_ok, no_raw_error=no_raw_error)
        if graph_errors:
            raise ValueError("; ".join(graph_errors))
    manifest_path = _manifest_path(project_root, raw_cfg)
    members = graph.raw_members if mode == "strict" else None
    files = _collect_hashes(project_root, raw_cfg, members=members)
    if mode == "strict" and graph.raw_members and not files:
        raise ValueError("raw_integrity strict mode requires at least one local raw manifest entry")
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

    mode = str(raw_cfg.get("mode", "warn"))
    try:
        manifest_path = _manifest_path(project_root, raw_cfg)
        graph = derive_raw_dependency_graph(project_root, config, raw_cfg=raw_cfg)
        no_raw_ok, no_raw_error = _validated_no_raw_exception(raw_cfg, graph, project_root)
    except ValueError as exc:
        result = _empty_result(configured=True)
        result.update(
            {
                "mode": mode,
                "ok": False,
                "errors": [f"raw_integrity configuration error: {exc}"],
            }
        )
        return result
    strict_graph_errors = (
        _strict_graph_errors(graph, no_raw_ok=no_raw_ok, no_raw_error=no_raw_error)
        if mode == "strict"
        else ([no_raw_error] if no_raw_error else [])
    )
    if not manifest_path.exists():
        strict = mode == "strict"
        if strict and no_raw_ok and not strict_graph_errors:
            result = _empty_result(configured=True)
            result.update(
                {
                    "manifest_path": str(manifest_path),
                    "mode": mode,
                    "ok": True,
                    "no_raw_inputs": True,
                    "dependency_graph": _graph_result(graph),
                }
            )
            return result
        result = _empty_result(configured=True)
        result.update(
            {
                "manifest_path": str(manifest_path),
                "mode": mode,
                "sealed": False,
                "ok": False,
                "errors": strict_graph_errors
                or (
                    ["raw_integrity strict mode requires a valid seal manifest"]
                    if strict
                    else ["raw_integrity is configured but no seal manifest exists"]
                ),
                "dependency_graph": _graph_result(graph),
            }
        )
        return result

    try:
        manifest_declaration = str(raw_cfg.get("manifest") or DEFAULT_RAW_INTEGRITY["manifest"])
        if project_path_has_symlink_component(
            project_root,
            manifest_declaration,
            purpose="raw_integrity manifest",
        ):
            raise ValueError("raw_integrity manifest must not contain symlink components")
        snapshot = snapshot_project_input(
            project_root,
            manifest_declaration,
            purpose="raw_integrity manifest",
        )
        with open_verified_project_input(
            project_root,
            manifest_declaration,
            expected_snapshot=snapshot,
            purpose="raw_integrity manifest",
        ) as stream:
            manifest = json.loads(stream.read().decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, ValueError) as exc:
        result = _empty_result(configured=True)
        result.update(
            {
                "manifest_path": str(manifest_path),
                "mode": mode,
                "sealed": False,
                "ok": False,
                "errors": [f"raw_integrity manifest could not be read: {exc}"],
            }
        )
        return result

    expected, manifest_errors = _validated_manifest_files(manifest)
    try:
        members = graph.raw_members if mode == "strict" else None
        actual = _collect_hashes(project_root, raw_cfg, members=members)
    except ValueError as exc:
        result = _empty_result(configured=True)
        result.update(
            {
                "manifest_path": str(manifest_path),
                "mode": mode,
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
    errors = [*manifest_errors, *strict_graph_errors]
    if modified or added or removed:
        errors.append(_drift_message(modified=modified, added=added, removed=removed))
    if mode == "strict" and graph.raw_members and not expected:
        errors.append("raw_integrity strict mode requires at least one valid local raw manifest entry")
    ok = not errors

    return {
        "configured": True,
        "sealed": not manifest_errors,
        "ok": ok,
        "manifest_path": str(manifest_path),
        "mode": mode,
        "sealed_at": _sealed_at(manifest),
        "modified": modified,
        "added": added,
        "removed": removed,
        "errors": errors,
        "no_raw_inputs": no_raw_ok,
        "dependency_graph": _graph_result(graph),
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
        "no_raw_inputs": False,
        "dependency_graph": _graph_result(RawDependencyGraph((), (), (), (), ())),
    }


def _manifest_path(project_root: Path, raw_cfg: dict[str, Any]) -> Path:
    return _project_relative_path(project_root, str(raw_cfg.get("manifest") or DEFAULT_RAW_INTEGRITY["manifest"]))


def derive_raw_dependency_graph(
    project_dir: str | Path,
    config: Mapping[str, Any],
    *,
    raw_cfg: dict[str, Any] | None = None,
) -> RawDependencyGraph:
    """Derive raw terminals from declared producer inputs, never heuristics."""

    project_root = Path(project_dir).resolve()
    effective_raw_cfg = raw_cfg or raw_integrity_config(dict(config)) or dict(DEFAULT_RAW_INTEGRITY)
    errors: list[str] = []
    try:
        configured_roots = _configured_paths(project_root, effective_raw_cfg)
    except ValueError as exc:
        configured_roots = []
        errors.append(str(exc))
    for configured_root in configured_roots:
        candidates = [configured_root] if configured_root.is_file() else list(configured_root.rglob("*"))
        for candidate in candidates:
            try:
                relative = candidate.relative_to(project_root).as_posix()
            except ValueError:
                continue
            if project_path_has_symlink_component(project_root, relative, purpose="raw_integrity file"):
                errors.append(f"raw_integrity file must not contain symlink components: {relative}")
    try:
        external = {item.id: item for item in validate_external_raw_descriptors(config.get("external_raw"))}
    except ExternalRawError as exc:
        external = {}
        errors.append(str(exc))

    records = _producer_records(config, errors)
    output_owner: dict[str, str] = {}
    for producer_id, _inputs, outputs in records:
        for output in outputs:
            try:
                normalized = normalize_project_relative_path(output, purpose=f"{producer_id} output")
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if normalized in output_owner:
                errors.append(f"dependency graph output has multiple producers: {normalized}")
            output_owner[normalized] = producer_id

    raw_members: set[str] = set()
    external_ids: set[str] = set()
    unresolved: set[str] = set()
    edges: dict[str, set[str]] = {producer_id: set() for producer_id, _inputs, _outputs in records}
    manifest_path = _manifest_path(project_root, effective_raw_cfg)
    for producer_id, inputs, _outputs in records:
        for raw_input in inputs:
            if raw_input.startswith(_EXTERNAL_PREFIX):
                external_id = raw_input[len(_EXTERNAL_PREFIX) :]
                if not external_id or external_id not in external:
                    errors.append(f"{producer_id} references unknown external raw input: {raw_input}")
                else:
                    external_ids.add(external_id)
                continue
            try:
                declaration = normalize_project_relative_path(raw_input, purpose=f"{producer_id} input")
            except ValueError as exc:
                errors.append(str(exc))
                continue
            owner = output_owner.get(declaration)
            if owner is not None:
                edges[producer_id].add(owner)
                continue
            matches = _expand_dependency_input(project_root, declaration)
            if not matches:
                unresolved.add(declaration)
                continue
            raw_matches = [
                path
                for path in matches
                if any(path == root or _is_relative_to(path, root) for root in configured_roots)
            ]
            if len(raw_matches) != len(matches):
                unresolved.add(declaration)
                continue
            for path in raw_matches:
                if path.resolve() == manifest_path:
                    continue
                raw_members.add(path.relative_to(project_root).as_posix())

    # ``raw_integrity.paths`` is itself an explicit raw declaration.  Legacy
    # producer records often omitted ``inputs``; attach those declared members
    # only when the graph has no other terminal declaration at all.
    if records and not any(record[1] for record in records) and not external_ids and not unresolved:
        for configured_root in configured_roots:
            candidates = [configured_root] if configured_root.is_file() else configured_root.rglob("*")
            for path in candidates:
                if path.is_file() and path.resolve() != manifest_path:
                    raw_members.add(path.relative_to(project_root).as_posix())

    _append_cycle_errors(edges, errors)
    return RawDependencyGraph(
        producers=tuple(record[0] for record in records),
        raw_members=tuple(sorted(raw_members)),
        external_raw_ids=tuple(sorted(external_ids)),
        unresolved_inputs=tuple(sorted(unresolved)),
        errors=tuple(errors),
    )


def _producer_records(
    config: Mapping[str, Any], errors: list[str]
) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    records: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    pipeline = config.get("pipeline", {})
    analysis = pipeline.get("analysis", []) if isinstance(pipeline, Mapping) else []
    _append_producers(records, errors, analysis, section="pipeline.analysis", output_key="outputs")
    _append_producers(records, errors, config.get("figures", []), section="figures", output_key="output")
    _append_producers(records, errors, config.get("diagrams", []), section="diagrams", output_key="output")
    return records


def _append_producers(
    records: list[tuple[str, tuple[str, ...], tuple[str, ...]]],
    errors: list[str],
    value: object,
    *,
    section: str,
    output_key: str,
) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        errors.append(f"dependency graph section {section} must be a list")
        return
    for index, item in enumerate(value, 1):
        if not isinstance(item, Mapping):
            errors.append(f"dependency graph producer {section}[{index}] must be a mapping")
            continue
        producer_id = f"{section}[{index}]"
        inputs_value = item.get("inputs", [])
        if not isinstance(inputs_value, list) or any(
            not isinstance(entry, str) or not entry.strip() for entry in inputs_value
        ):
            errors.append(f"{producer_id}.inputs must be a list of non-empty strings")
            inputs: tuple[str, ...] = ()
        else:
            inputs = tuple(entry.strip() for entry in inputs_value)
        output_value = item.get(output_key, [] if output_key == "outputs" else None)
        if output_key == "outputs":
            if not isinstance(output_value, list) or any(
                not isinstance(entry, str) or not entry.strip() for entry in output_value
            ):
                errors.append(f"{producer_id}.outputs must be a list of non-empty strings")
                outputs: tuple[str, ...] = ()
            else:
                outputs = tuple(entry.strip() for entry in output_value)
        elif output_value is None:
            outputs = ()
        elif not isinstance(output_value, str) or not output_value.strip():
            errors.append(f"{producer_id}.output must be a non-empty string")
            outputs = ()
        else:
            outputs = (output_value.strip(),)
        records.append((producer_id, inputs, outputs))


def _expand_dependency_input(project_root: Path, declaration: str) -> list[Path]:
    candidate = project_root / declaration
    if glob.has_magic(declaration):
        raw_matches = [Path(match) for match in glob.glob(str(candidate), recursive=True)]
    elif candidate.is_dir():
        raw_matches = list(candidate.rglob("*"))
    elif candidate.exists():
        raw_matches = [candidate]
    else:
        return []
    matches: list[Path] = []
    for path in raw_matches:
        if not path.is_file():
            continue
        relative = path.relative_to(project_root).as_posix()
        matches.append(resolve_project_input(project_root, relative, purpose="raw dependency input"))
    return sorted(set(matches))


def _append_cycle_errors(edges: Mapping[str, set[str]], errors: list[str]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append(f"dependency graph contains a producer cycle at {node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for dependency in edges.get(node, set()):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in edges:
        visit(node)


def _validated_no_raw_exception(
    raw_cfg: Mapping[str, Any], graph: RawDependencyGraph, project_root: Path
) -> tuple[bool, str]:
    declaration = raw_cfg.get("no_raw_inputs")
    if declaration is None:
        return False, ""
    if not isinstance(declaration, Mapping):
        return False, "raw_integrity.no_raw_inputs must be a typed mapping"
    extra = set(declaration) - _NO_RAW_KEYS
    if extra:
        return False, f"raw_integrity.no_raw_inputs contains unsupported fields: {', '.join(sorted(extra))}"
    if declaration.get("type") != "no_raw_inputs":
        return False, "raw_integrity.no_raw_inputs.type must equal 'no_raw_inputs'"
    reason = declaration.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return False, "raw_integrity.no_raw_inputs.reason must be a non-empty string"
    if not graph.nonempty:
        return False, "raw_integrity.no_raw_inputs requires a nonempty producer graph"
    if graph.errors or graph.unresolved_inputs or graph.has_raw_terminal:
        return False, "raw_integrity.no_raw_inputs contradicts the derived dependency graph"
    try:
        configured_files = _collect_hashes(project_root, dict(raw_cfg))
    except ValueError as exc:
        return False, str(exc)
    if configured_files:
        return False, "raw_integrity.no_raw_inputs requires configured raw paths to contain no files"
    return True, ""


def _strict_graph_errors(
    graph: RawDependencyGraph, *, no_raw_ok: bool, no_raw_error: str
) -> list[str]:
    errors = list(graph.errors)
    if graph.unresolved_inputs:
        errors.append(f"dependency graph has unresolved terminal inputs: {list(graph.unresolved_inputs)}")
    if not graph.nonempty:
        errors.append("raw_integrity strict mode requires a nonempty dependency graph")
    if not graph.has_raw_terminal and not no_raw_ok:
        errors.append("raw_integrity strict dependency graph must terminate in raw or external_raw input")
    if no_raw_error:
        errors.append(no_raw_error)
    return list(dict.fromkeys(errors))


def _graph_result(graph: RawDependencyGraph) -> dict[str, Any]:
    return {
        "producers": list(graph.producers),
        "raw_members": list(graph.raw_members),
        "external_raw_ids": list(graph.external_raw_ids),
        "unresolved_inputs": list(graph.unresolved_inputs),
        "errors": list(graph.errors),
    }


def _configured_paths(project_root: Path, raw_cfg: dict[str, Any]) -> list[Path]:
    raw_paths = raw_cfg.get("paths", DEFAULT_RAW_INTEGRITY["paths"])
    if raw_paths is None:
        raw_paths = DEFAULT_RAW_INTEGRITY["paths"]
    if not isinstance(raw_paths, list):
        raise ValueError("raw_integrity paths must be a list")
    configured: list[Path] = []
    for raw_path in raw_paths:
        declaration = normalize_project_relative_path(str(raw_path), purpose="raw_integrity path")
        prospective = project_root / declaration
        if not prospective.exists():
            raise ValueError(f"raw_integrity configured path does not exist: {declaration}")
        if project_path_has_symlink_component(project_root, declaration, purpose="raw_integrity path"):
            raise ValueError(f"raw_integrity path must not contain symlink components: {raw_path}")
        configured.append(
            resolve_project_input(
                project_root,
                declaration,
                regular_file=False,
                purpose="raw_integrity path",
            )
        )
    return configured


def _collect_hashes(
    project_root: Path,
    raw_cfg: dict[str, Any],
    *,
    members: tuple[str, ...] | None = None,
) -> dict[str, str]:
    manifest_path = _manifest_path(project_root, raw_cfg)
    files: dict[str, str] = {}
    configured_paths = _configured_paths(project_root, raw_cfg)
    if members is None:
        candidates: list[Path] = []
        for configured_path in configured_paths:
            if configured_path.is_file():
                candidates.append(configured_path)
            elif configured_path.is_dir():
                candidates.extend(path for path in configured_path.rglob("*") if path.is_file())
        candidates = sorted(set(candidates))
    else:
        candidates = [project_root / member for member in members]
    for path in candidates:
        if not path.exists() or not path.is_file():
            raise ValueError(f"raw_integrity manifest member is missing or not a regular file: {path}")
        if not any(path == root or _is_relative_to(path, root) for root in configured_paths):
            raise ValueError(f"raw_integrity manifest member is outside configured raw paths: {path}")
        if path.resolve() == manifest_path:
            continue
        try:
            rel_path = path.relative_to(project_root).as_posix()
        except ValueError as exc:
            raise ValueError(f"raw_integrity path escapes project root: {path}") from exc
        if project_path_has_symlink_component(project_root, rel_path, purpose="raw_integrity file"):
            raise ValueError(f"raw_integrity file must not contain symlink components: {rel_path}")
        snapshot = snapshot_project_input(project_root, rel_path, purpose="raw_integrity file")
        with open_verified_project_input(
            project_root,
            rel_path,
            expected_snapshot=snapshot,
            purpose="raw_integrity file",
        ) as stream:
            files[rel_path] = _sha256_stream(stream)
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


def _sha256_stream(handle: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _validated_manifest_files(manifest: Any) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    if not isinstance(manifest, Mapping):
        return {}, ["raw_integrity manifest root must be a JSON object"]
    metadata = manifest.get("_metadata")
    if not isinstance(metadata, Mapping):
        errors.append("raw_integrity manifest requires an _metadata object")
    else:
        if metadata.get("algorithm") != "sha256":
            errors.append("raw_integrity manifest _metadata.algorithm must equal 'sha256'")
        sealed_at = metadata.get("sealed_at")
        if not isinstance(sealed_at, str) or not sealed_at.strip():
            errors.append("raw_integrity manifest _metadata.sealed_at must be a non-empty timestamp")
        else:
            try:
                datetime.fromisoformat(sealed_at.replace("Z", "+00:00"))
            except ValueError:
                errors.append("raw_integrity manifest _metadata.sealed_at must be an ISO-8601 timestamp")

    unknown_control = [key for key in manifest if isinstance(key, str) and key.startswith("_") and key != "_metadata"]
    if unknown_control:
        errors.append(f"raw_integrity manifest contains unsupported control fields: {sorted(unknown_control)}")
    if "files" in manifest:
        flat_entries = [key for key in manifest if key != "_metadata" and key != "files"]
        if flat_entries:
            errors.append("raw_integrity manifest must not mix files object and flat file entries")
        entries = manifest.get("files")
        if not isinstance(entries, Mapping):
            errors.append("raw_integrity manifest files must be an object")
            entries = {}
    else:
        entries = {key: value for key, value in manifest.items() if key != "_metadata"}

    files: dict[str, str] = {}
    normalized_seen: set[str] = set()
    for path, digest in entries.items():
        if not isinstance(path, str) or not path:
            errors.append("raw_integrity manifest file paths must be non-empty strings")
            continue
        try:
            normalized = normalize_project_relative_path(path, purpose="raw_integrity manifest member")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if normalized != path.replace("\\", "/") or "\\" in path:
            errors.append(f"raw_integrity manifest path must be canonical: {path!r}")
            continue
        if normalized in normalized_seen:
            errors.append(f"raw_integrity manifest contains duplicate member: {normalized}")
            continue
        normalized_seen.add(normalized)
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            errors.append(f"raw_integrity manifest digest for {normalized!r} must be 64 lowercase hex characters")
            continue
        files[normalized] = digest
    return files, errors


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


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
    parser = argparse.ArgumentParser(description="Seal or verify FigOps raw data integrity manifests.")
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
