"""Deterministic, read-only structure audits across discovered projects.

This module is intentionally a reporting layer: it never creates, edits, or
deletes project files.  Discovery metadata is retained even when a project is
invalid or cannot pass the execution-path boundary, so an all-project audit
does not hide the very entries that need attention.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .config_parser import load_config
from .execution_project_boundary import ExecutionProjectPathError, resolve_execution_project_path
from .project_discovery import discover_projects_with_status
from .structure_audit import audit_project_structure

REPORT_SCHEMA_VERSION = "figops.project-structure-audit-report.v1"


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or exc.__class__.__name__


def _project_entry(project: Mapping[str, Any]) -> dict[str, Any]:
    """Copy stable discovery fields while normalising list-valued diagnostics."""

    raw_errors = project.get("errors") or []
    if isinstance(raw_errors, (str, bytes)):
        raw_errors = [raw_errors]
    return {
        "project_id": str(project.get("project_id") or ""),
        "name": str(project.get("name") or project.get("path") or ""),
        "path": str(project.get("path") or ""),
        "config": str(project.get("config") or ""),
        "config_path": str(project.get("config_path") or ""),
        "role": str(project.get("role") or ""),
        "status": str(project.get("status") or ""),
        "classification": str(project.get("classification") or ""),
        "target_format": str(project.get("target_format") or ""),
        "valid": bool(project.get("valid", False)),
        "errors": [str(item) for item in raw_errors],
        "audit_status": "pending",
        "result_status": "pending",
        "proposed_changes": [],
        "audit": None,
    }


def _append_project(projects: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    """Finalize compatibility fields before retaining one project row."""

    entry["result_status"] = entry["audit_status"]
    audit = entry.get("audit")
    if isinstance(audit, Mapping):
        # A report must remain diagnostic-only even if a future producer adds a
        # plan field.  Never leak mutation proposals through this surface.
        entry["proposed_changes"] = []
        if isinstance(audit, dict):
            audit["proposed_changes"] = []
    projects.append(entry)


def build_structure_audit_report(
    root_dir: str | Path,
    *,
    max_depth: int = 4,
    include_worktrees: bool = False,
    include_ephemeral: bool = False,
    include_quarantine: bool = False,
) -> dict[str, Any]:
    """Audit every discovered project beneath *root_dir* in stable order.

    Discovery records are processed independently.  A bad configuration is
    reported as ``invalid``; a path rejected by the execution boundary is
    reported as ``boundary_blocked``; config-less folder-role entries are kept
    as ``skipped``.  One failure therefore cannot make another project vanish
    from the report.
    """

    root = Path(root_dir).expanduser().resolve()
    depth = max(1, int(max_depth or 1))
    discovered = discover_projects_with_status(
        root,
        max_depth=depth,
        include_worktrees=include_worktrees,
        include_ephemeral=include_ephemeral,
        include_quarantine=include_quarantine,
    )
    # The discovery service normally sorts this already, but sorting here is a
    # second deterministic boundary for callers supplying a custom service.
    discovered = sorted(
        (item for item in discovered if isinstance(item, Mapping)),
        key=lambda item: (
            str(item.get("path") or "").casefold(),
            str(item.get("project_id") or "").casefold(),
        ),
    )

    projects: list[dict[str, Any]] = []
    for discovered_project in discovered:
        entry = _project_entry(discovered_project)
        relative_path = entry["path"]
        try:
            project_path = resolve_execution_project_path(root, relative_path)
        except (ExecutionProjectPathError, OSError, RuntimeError, ValueError) as exc:
            entry["audit_status"] = "boundary_blocked"
            entry["errors"].append(_error_text(exc))
            _append_project(projects, entry)
            continue

        if not entry["valid"]:
            entry["audit_status"] = "invalid"
            _append_project(projects, entry)
            continue

        # Config-less folder-role entries are useful discovery evidence but do
        # not contain enough information to construct a structure contract.
        if not entry["config"]:
            entry["audit_status"] = "skipped"
            entry["errors"].append("project configuration was not discovered")
            _append_project(projects, entry)
            continue

        try:
            loaded = load_config(project_path)
        except Exception as exc:  # keep one unreadable project from hiding others
            entry["audit_status"] = "audit_error"
            entry["errors"].append(_error_text(exc))
            _append_project(projects, entry)
            continue
        config = loaded[0] if isinstance(loaded, tuple) and loaded else None
        if not isinstance(config, Mapping):
            entry["audit_status"] = "invalid"
            entry["errors"].append("project configuration could not be loaded")
            _append_project(projects, entry)
            continue

        try:
            audit = audit_project_structure(project_path, config)
            if not isinstance(audit, Mapping):
                raise TypeError("structure audit returned a non-mapping result")
            # Copy to detach the report from mutable producer dictionaries and
            # keep this report strictly read-only.
            audit_copy = dict(audit)
            audit_copy["proposed_changes"] = []
            entry["audit"] = audit_copy
            entry["audit_status"] = "audited"
        except Exception as exc:  # report the failure; never silently omit it
            entry["audit_status"] = "audit_error"
            entry["errors"].append(_error_text(exc))
        _append_project(projects, entry)

    status_counts = Counter(str(item["audit_status"]) for item in projects)
    finding_count = 0
    unknown_count = 0
    finding_codes: Counter[str] = Counter()
    for item in projects:
        audit = item.get("audit")
        if not isinstance(audit, Mapping):
            continue
        findings = audit.get("findings")
        unknowns = audit.get("unknowns")
        if isinstance(findings, list):
            finding_count += len(findings)
            for finding in findings:
                if isinstance(finding, Mapping):
                    finding_codes[str(finding.get("code") or "unknown")] += 1
        if isinstance(unknowns, list):
            unknown_count += len(unknowns)

    summary = {
        "project_count": len(projects),
        "discovered_count": len(projects),
        "audited_count": status_counts.get("audited", 0),
        "invalid_count": status_counts.get("invalid", 0),
        "boundary_blocked_count": status_counts.get("boundary_blocked", 0),
        "skipped_count": status_counts.get("skipped", 0),
        "audit_error_count": status_counts.get("audit_error", 0),
        "finding_count": finding_count,
        "unknown_count": unknown_count,
        "status_counts": dict(sorted(status_counts.items())),
        "finding_counts": dict(sorted(finding_codes.items())),
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "root": str(root),
        "max_depth": depth,
        "projects": projects,
        "proposed_changes": [],
        "summary": summary,
    }


def render_structure_audit_json(report: Mapping[str, Any]) -> str:
    """Render a report as canonical, newline-terminated JSON."""

    return json.dumps(dict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _md(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def render_structure_audit_markdown(report: Mapping[str, Any]) -> str:
    """Render a compact deterministic Markdown report."""

    summary = report.get("summary") if isinstance(report, Mapping) else {}
    summary = summary if isinstance(summary, Mapping) else {}
    projects = report.get("projects") if isinstance(report, Mapping) else []
    projects = projects if isinstance(projects, list) else []
    lines = [
        "# Project Structure Audit",
        "",
        f"Root: `{_md(report.get('root', ''))}`",
        f"Max depth: `{_md(report.get('max_depth', ''))}`",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
    ]
    for key in (
        "project_count",
        "audited_count",
        "invalid_count",
        "boundary_blocked_count",
        "skipped_count",
        "audit_error_count",
        "finding_count",
        "unknown_count",
    ):
        lines.append(f"| {_md(key.replace('_', ' '))} | {_md(summary.get(key, 0))} |")
    lines.extend(
        [
            "",
            "## Projects",
            "",
            "| Path | Name | Role | Lifecycle | Audit status | Findings | Unknowns | Errors |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for item in projects:
        if not isinstance(item, Mapping):
            continue
        audit = item.get("audit") if isinstance(item.get("audit"), Mapping) else {}
        findings = audit.get("findings") if isinstance(audit.get("findings"), list) else []
        unknowns = audit.get("unknowns") if isinstance(audit.get("unknowns"), list) else []
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(item.get("path", "")),
                    _md(item.get("name", "")),
                    _md(item.get("role", "")),
                    _md(item.get("status", "")),
                    _md(item.get("audit_status", "")),
                    str(len(findings)),
                    str(len(unknowns)),
                    _md("; ".join(str(error) for error in (item.get("errors") or []))),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Findings", ""])
    any_findings = False
    for item in projects:
        if not isinstance(item, Mapping):
            continue
        audit = item.get("audit") if isinstance(item.get("audit"), Mapping) else {}
        findings = audit.get("findings") if isinstance(audit.get("findings"), list) else []
        if findings:
            any_findings = True
            lines.append(f"### `{_md(item.get('path', ''))}`")
            for finding in findings:
                if isinstance(finding, Mapping):
                    code = _md(finding.get("code", "finding"))
                    detail = ", ".join(
                        f"{_md(k)}={_md(v)}" for k, v in sorted(finding.items()) if k != "code"
                    )
                    lines.append(f"- `{code}`" + (f": {detail}" if detail else ""))
                else:
                    lines.append(f"- {_md(finding)}")
            lines.append("")
    if not any_findings:
        lines.append("No structure findings.")
    return "\n".join(lines).rstrip() + "\n"


def render_structure_audit_report(report: Mapping[str, Any], *, output_format: str = "markdown") -> str:
    """Render *report* as ``markdown`` (default) or ``json``."""

    selected = str(output_format or "markdown").strip().lower()
    if selected == "json":
        return render_structure_audit_json(report)
    if selected in {"markdown", "md"}:
        return render_structure_audit_markdown(report)
    raise ValueError("output_format must be 'json' or 'markdown'")


# Compatibility names used by early callers of the all-project read-only
# surface.  They intentionally return the same canonical report envelope.
def audit_discovered_projects(
    root_dir: str | Path,
    *,
    max_depth: int = 4,
    include_worktrees: bool = False,
    include_ephemeral: bool = False,
    include_quarantine: bool = False,
) -> dict[str, Any]:
    return build_structure_audit_report(
        root_dir,
        max_depth=max_depth,
        include_worktrees=include_worktrees,
        include_ephemeral=include_ephemeral,
        include_quarantine=include_quarantine,
    )


audit_all_projects = audit_discovered_projects


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "build_structure_audit_report",
    "audit_discovered_projects",
    "audit_all_projects",
    "render_structure_audit_json",
    "render_structure_audit_markdown",
    "render_structure_audit_report",
]
