#!/usr/bin/env python3
"""Build a project_config.yaml figure inventory for FigOps projects."""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class FigureInventoryEntry:
    project_path: str
    project_name: str
    figure_id: str
    script: str
    output: str
    target_format: str
    profile: str
    input_count: int
    missing_inputs: tuple[str, ...]
    symlinked_paths: tuple[str, ...]
    invalid_paths: tuple[str, ...]
    script_exists: bool
    output_exists: bool
    render_candidate: bool
    config_error: str = ""


def _read_yaml(path: Path) -> tuple[dict[str, Any], str]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, f"Failed to read config: {exc}"
    except yaml.YAMLError as exc:
        return {}, f"Invalid YAML: {exc}"
    if not isinstance(payload, dict):
        return {}, "Config root must be a mapping."
    return payload, ""


def _config_validation_errors(config: dict[str, Any]) -> list[str]:
    hub_root = Path(__file__).resolve().parents[1]
    hub_root_text = str(hub_root)
    if hub_root_text not in sys.path:
        sys.path.insert(0, hub_root_text)
    from hub_core.config_parser import validate_config

    return validate_config(config)


def _rel(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return unicodedata.normalize("NFC", rel)


EXCLUDED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".dvc", ".worktrees"}


def _config_project_dir(config_path: Path) -> Path:
    if config_path.name == "project_config.yaml" and config_path.parent.name == "scripts":
        return config_path.parent.parent
    return config_path.parent


def _script_snapshot_path(script: str) -> str:
    return script.split("::")[0]


def _declared_inputs(figure: dict[str, Any]) -> list[str]:
    raw_inputs = figure.get("inputs") or figure.get("input") or []
    if isinstance(raw_inputs, str):
        raw_inputs = [raw_inputs]
    if not isinstance(raw_inputs, list):
        return []
    return [str(item) for item in raw_inputs if isinstance(item, str) and item.strip()]


def _invalid_project_relative_paths(paths: list[tuple[str, str]]) -> tuple[str, ...]:
    invalid: list[str] = []
    for field_name, raw_path in paths:
        if not raw_path.strip():
            continue
        relpath = Path(raw_path.strip())
        if relpath.is_absolute() or ".." in relpath.parts:
            invalid.append(f"{field_name}: {raw_path}")
    return tuple(invalid)


def _escaped_project_paths(project_dir: Path, paths: list[tuple[str, str]]) -> tuple[str, ...]:
    project_root = project_dir.resolve()
    escaped: list[str] = []
    for field_name, raw_path in paths:
        if not raw_path.strip():
            continue
        candidate = project_dir / raw_path
        if not candidate.exists():
            continue
        try:
            candidate.resolve().relative_to(project_root)
        except ValueError:
            escaped.append(f"{field_name}: {raw_path}")
    return tuple(escaped)


def _contains_symlink(path: Path) -> bool:
    if path.is_symlink():
        return True
    if not path.is_dir():
        return False
    for current_root, dirs, files in os.walk(path):
        current = Path(current_root)
        for dirname in dirs:
            if (current / dirname).is_symlink():
                return True
        for filename in files:
            if (current / filename).is_symlink():
                return True
    return False


def _snapshot_symlinked_paths(project_dir: Path, config_path: Path, script: str, inputs: list[str]) -> tuple[str, ...]:
    candidates = [os.path.relpath(config_path, project_dir)]
    if script:
        candidates.append(script)
    candidates.extend(inputs)
    candidates.extend(["hub_scripts", "results/data"])

    symlinked_paths: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        normalized = unicodedata.normalize("NFC", str(item))
        if normalized in seen:
            continue
        seen.add(normalized)
        path = project_dir / item
        if path.is_dir() and any(existing.startswith(f"{normalized}/") for existing in symlinked_paths):
            continue
        if path.exists() and _contains_symlink(path):
            symlinked_paths.append(normalized)
    return tuple(symlinked_paths)


def discover_project_configs(root: Path, *, max_depth: int = 4) -> list[Path]:
    root = root.resolve()
    configs: list[Path] = []
    visited: set[Path] = set()
    for current_root, dirs, files in os.walk(root, followlinks=True):
        current_path = Path(current_root)
        try:
            resolved = current_path.resolve()
        except OSError:
            dirs[:] = []
            continue
        if resolved in visited:
            dirs[:] = []
            continue
        visited.add(resolved)

        rel_parts = current_path.relative_to(root).parts
        depth = len(rel_parts)
        dirs[:] = [dirname for dirname in dirs if dirname not in EXCLUDED_DIRS]
        if depth >= max_depth:
            dirs[:] = []

        direct_config = current_path / "project_config.yaml"
        legacy_config = current_path / "scripts" / "project_config.yaml"
        if "project_config.yaml" in files and direct_config.exists():
            configs.append(direct_config)
            dirs[:] = []
            continue
        if legacy_config.exists():
            configs.append(legacy_config)
            dirs[:] = []
    return sorted(configs, key=lambda item: unicodedata.normalize("NFC", item.as_posix()))


def build_inventory(root: Path, *, max_depth: int = 4) -> list[FigureInventoryEntry]:
    root = root.resolve()
    entries: list[FigureInventoryEntry] = []
    for config_path in discover_project_configs(root, max_depth=max_depth):
        project_dir = _config_project_dir(config_path)
        config, config_error = _read_yaml(config_path)
        if not config_error:
            config_error = "; ".join(_config_validation_errors(config))
        project = config.get("project") if isinstance(config.get("project"), dict) else {}
        style = config.get("visual_style") if isinstance(config.get("visual_style"), dict) else {}
        figures = config.get("figures")
        if config_error:
            entries.append(
                FigureInventoryEntry(
                    project_path=_rel(project_dir, root),
                    project_name=unicodedata.normalize("NFC", project_dir.name),
                    figure_id="(config error)",
                    script="",
                    output="",
                    target_format="",
                    profile="",
                    input_count=0,
                    missing_inputs=(),
                    symlinked_paths=(),
                    invalid_paths=(),
                    script_exists=False,
                    output_exists=False,
                    render_candidate=False,
                    config_error=unicodedata.normalize("NFC", config_error),
                )
            )
            continue
        if not isinstance(figures, list):
            figures = []

        for figure in figures:
            if not isinstance(figure, dict):
                continue
            figure_id = str(figure.get("id") or "").strip()
            script = str(figure.get("script") or "").strip()
            output = str(figure.get("output") or "").strip()
            script_path = _script_snapshot_path(script)
            inputs = _declared_inputs(figure)
            snapshot_paths = [("script", script_path), ("output", output), *[("input", item) for item in inputs]]
            invalid_paths = _invalid_project_relative_paths(snapshot_paths) + _escaped_project_paths(
                project_dir, snapshot_paths
            )
            missing_inputs = tuple(item for item in inputs if not (project_dir / item).exists())
            symlinked_paths = _snapshot_symlinked_paths(project_dir, config_path, script_path, inputs)
            script_exists = bool(script_path) and (project_dir / script_path).is_file()
            output_exists = bool(output) and (project_dir / output).exists()
            entries.append(
                FigureInventoryEntry(
                    project_path=_rel(project_dir, root),
                    project_name=unicodedata.normalize("NFC", str(project.get("name") or project_dir.name)),
                    figure_id=unicodedata.normalize("NFC", figure_id),
                    script=unicodedata.normalize("NFC", script),
                    output=unicodedata.normalize("NFC", output),
                    target_format=unicodedata.normalize("NFC", str(style.get("target_format") or "")),
                    profile=unicodedata.normalize("NFC", str(style.get("profile") or "")),
                    input_count=len(inputs),
                    missing_inputs=tuple(unicodedata.normalize("NFC", item) for item in missing_inputs),
                    symlinked_paths=tuple(unicodedata.normalize("NFC", item) for item in symlinked_paths),
                    invalid_paths=tuple(unicodedata.normalize("NFC", item) for item in invalid_paths),
                    script_exists=script_exists,
                    output_exists=output_exists,
                    render_candidate=bool(
                        figure_id
                        and script_exists
                        and output
                        and not invalid_paths
                        and not missing_inputs
                        and not symlinked_paths
                    ),
                )
            )
    return entries


def render_markdown(entries: list[FigureInventoryEntry], *, title: str, root: Path) -> str:
    lines = [
        f"# {title}",
        "",
        f"Root: `{root}`",
        "",
        "## Summary",
        "",
        f"- projects listed: {len({entry.project_path for entry in entries})}",
        f"- inventory rows: {len(entries)}",
        f"- render candidates: {sum(1 for entry in entries if entry.render_candidate)}",
        f"- existing outputs: {sum(1 for entry in entries if entry.output_exists)}",
        "",
        "## Figure Targets",
        "",
        "| Project | Figure ID | Candidate | Output Exists | Missing Inputs | Symlinks | Invalid Paths | "
        "Config Error | Script | Output |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for entry in entries:
        missing = ", ".join(entry.missing_inputs) if entry.missing_inputs else "-"
        symlinks = ", ".join(entry.symlinked_paths) if entry.symlinked_paths else "-"
        invalid_paths = ", ".join(entry.invalid_paths) if entry.invalid_paths else "-"
        config_error = entry.config_error if entry.config_error else "-"
        lines.append(
            "| "
            f"`{entry.project_path}` | "
            f"`{entry.figure_id}` | "
            f"{'yes' if entry.render_candidate else 'no'} | "
            f"{'yes' if entry.output_exists else 'no'} | "
            f"{missing} | "
            f"{symlinks} | "
            f"{invalid_paths} | "
            f"{config_error} | "
            f"`{entry.script}` | "
            f"`{entry.output}` |"
        )
    lines.extend(
        [
            "",
            "## MCP Workflow",
            "",
            "For a candidate row, call:",
            "",
            "```text",
            "figops.inspect_project",
            "figops.validate_project",
            "figops.render_project_figure with dry_run=true",
            "figops.render_project_figure",
            "figops.collect_artifacts",
            "```",
            "",
            "Use the concrete subproject path. Do not render a master workspace root directly.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(
    entries: list[FigureInventoryEntry],
    *,
    markdown_path: Path | None,
    json_path: Path | None,
    root: Path,
) -> None:
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(
            render_markdown(entries, title="FigOps Figure Target Inventory", root=root),
            encoding="utf-8",
        )
    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps([asdict(entry) for entry in entries], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Project workspace root to scan")
    parser.add_argument("--max-depth", type=int, default=4, help="Maximum project_config.yaml depth below root")
    parser.add_argument("--markdown-out", type=Path, help="Write markdown inventory to this path")
    parser.add_argument("--json-out", type=Path, help="Write JSON inventory to this path")
    args = parser.parse_args(argv)

    entries = build_inventory(args.root, max_depth=args.max_depth)
    write_outputs(entries, markdown_path=args.markdown_out, json_path=args.json_out, root=args.root.resolve())
    if not args.markdown_out and not args.json_out:
        print(render_markdown(entries, title="FigOps Figure Target Inventory", root=args.root.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
