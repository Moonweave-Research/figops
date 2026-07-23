from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import hub_core.structure_audit_report as report_module


def _discovered(*items):
    defaults = {
        "project_id": "id",
        "name": "Project",
        "path": "project",
        "config": "project_config.yaml",
        "role": "module",
        "status": "active",
        "classification": "official",
        "target_format": "nature",
        "valid": True,
        "errors": [],
    }
    return [{**defaults, **item} for item in items]


def test_build_report_audits_in_stable_path_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    projects = _discovered(
        {"project_id": "b", "name": "B", "path": "b"},
        {"project_id": "a", "name": "A", "path": "a"},
    )
    monkeypatch.setattr(report_module, "discover_projects_with_status", lambda *a, **k: projects)
    monkeypatch.setattr(report_module, "resolve_execution_project_path", lambda root, path: root / path)
    monkeypatch.setattr(report_module, "load_config", lambda path: ({"project": {"name": path.name}}, "cfg", "hash"))
    monkeypatch.setattr(
        report_module,
        "audit_project_structure",
        lambda path, config: {"roles": {}, "graph": {}, "findings": [{"code": "x"}], "unknowns": []},
    )
    report = report_module.build_structure_audit_report(tmp_path)
    assert [item["path"] for item in report["projects"]] == ["a", "b"]
    assert report["summary"]["audited_count"] == 2
    assert report["summary"]["finding_count"] == 2


def test_invalid_and_boundary_blocked_entries_are_retained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    projects = _discovered(
        {"project_id": "invalid", "path": "invalid", "valid": False, "errors": ["bad yaml"]},
        {"project_id": "alias", "path": "alias"},
    )
    monkeypatch.setattr(report_module, "discover_projects_with_status", lambda *a, **k: projects)

    def resolve(root, path):
        if path == "alias":
            raise report_module.ExecutionProjectPathError("outside root")
        return root / path

    monkeypatch.setattr(report_module, "resolve_execution_project_path", resolve)
    report = report_module.build_structure_audit_report(tmp_path)
    statuses = {item["project_id"]: item["audit_status"] for item in report["projects"]}
    assert statuses == {"alias": "boundary_blocked", "invalid": "invalid"}
    assert report["summary"]["boundary_blocked_count"] == 1
    assert report["summary"]["invalid_count"] == 1


def test_json_renderer_is_canonical_and_markdown_contains_summary():
    report = {"summary": {"project_count": 0}, "projects": [], "root": "/tmp/root", "max_depth": 4}
    encoded = report_module.render_structure_audit_report(report, output_format="json")
    assert json.loads(encoded) == report
    assert encoded.endswith("\n")
    markdown = report_module.render_structure_audit_report(report)
    assert "# Project Structure Audit" in markdown
    assert "project count" in markdown


def test_report_uses_documented_schema_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(report_module, "discover_projects_with_status", lambda *a, **k: [])
    report = report_module.build_structure_audit_report(tmp_path)
    assert report["schema_version"] == "figops.project-structure-audit-report.v1"


def test_renderer_rejects_unknown_format():
    with pytest.raises(ValueError):
        report_module.render_structure_audit_report({}, output_format="xml")


def test_loader_exception_is_retained_as_audit_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "project").mkdir()
    monkeypatch.setattr(report_module, "discover_projects_with_status", lambda *a, **k: _discovered({}))
    monkeypatch.setattr(report_module, "resolve_execution_project_path", lambda root, path: root / path)
    monkeypatch.setattr(report_module, "load_config", lambda path: (_ for _ in ()).throw(OSError("unreadable")))
    report = report_module.build_structure_audit_report(tmp_path)
    assert report["projects"][0]["audit_status"] == "audit_error"
    assert "unreadable" in report["projects"][0]["errors"]


def test_audit_proposals_are_stripped_from_read_only_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "project").mkdir()
    monkeypatch.setattr(report_module, "discover_projects_with_status", lambda *a, **k: _discovered({}))
    monkeypatch.setattr(report_module, "resolve_execution_project_path", lambda root, path: root / path)
    monkeypatch.setattr(report_module, "load_config", lambda path: ({"project": {}}, None, None))
    monkeypatch.setattr(
        report_module,
        "audit_project_structure",
        lambda path, config: {"findings": [], "unknowns": [], "proposed_changes": [{"copy": "x"}]},
    )
    report = report_module.build_structure_audit_report(tmp_path)
    assert report["projects"][0]["proposed_changes"] == []
    assert report["projects"][0]["audit"]["proposed_changes"] == []
    assert report["proposed_changes"] == []


def test_markdown_enumerates_unknown_paths_reasons_and_audit_errors():
    report = {
        "root": "/tmp/root",
        "max_depth": 4,
        "summary": {"project_count": 2},
        "projects": [
            {
                "project_id": "b",
                "path": "b",
                "audit": {
                    "findings": [],
                    "unknowns": [
                        {
                            "path": "legacy/plot.R",
                            "candidate": {
                                "candidate_role": "unknown",
                                "reason": "ambiguous candidates: analysis_scripts, figure_scripts",
                            },
                        }
                    ],
                },
                "errors": ["configuration unreadable"],
            },
            {
                "project_id": "a",
                "path": "a",
                "audit": {
                    "findings": [],
                    "unknowns": [{"path": "misc.bin", "reason": "no semantic declaration"}],
                },
                "errors": [{"path": "a/project_config.yaml", "reason": "invalid YAML"}],
            },
        ],
    }

    markdown = report_module.render_structure_audit_markdown(report)

    assert "## Unknowns" in markdown
    assert "`legacy/plot.R`" in markdown
    assert "ambiguous candidates: analysis_scripts, figure_scripts" in markdown
    assert "`misc.bin`" in markdown
    assert "no semantic declaration" in markdown
    assert "## Audit Errors" in markdown
    assert "`a/project_config.yaml`: invalid YAML" in markdown
    assert "`b`: configuration unreadable" in markdown


def test_markdown_diagnostic_sections_are_deterministic_and_do_not_mutate_report():
    report = {
        "root": "/tmp/root",
        "max_depth": 4,
        "summary": {"project_count": 2},
        "projects": [
            {
                "project_id": "b",
                "path": "b",
                "audit": {
                    "findings": [],
                    "unknowns": [
                        {"path": "z.txt", "reason": "z reason"},
                        {"path": "a.txt", "reason": "a reason"},
                    ],
                },
                "errors": ["z error", "a error"],
            },
            {
                "project_id": "a",
                "path": "a",
                "audit": {"findings": [], "unknowns": [{"path": "m.txt", "reason": "m reason"}]},
                "errors": ["m error"],
            },
        ],
    }
    before = copy.deepcopy(report)

    first = report_module.render_structure_audit_markdown(report)
    second = report_module.render_structure_audit_markdown(report)

    assert first == second
    assert report == before
    assert first.index("### `a`") < first.index("### `b`")
    assert first.index("`a.txt`") < first.index("`z.txt`")
    assert first.index("`b`: a error") < first.index("`b`: z error")
