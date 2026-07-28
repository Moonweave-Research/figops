"""CLI coverage for the independent, read-only structure audit mode."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import hub_core
import hub_core.structure_audit_report  # noqa: F401  # ensure package attribute exists for the test double
import orchestrator


def _report_module(build_calls: list[tuple[object, int]], render_calls: list[str]) -> types.ModuleType:
    module = types.ModuleType("hub_core.structure_audit_report")

    def build_structure_audit_report(root_dir: object, *, max_depth: int = 4) -> dict[str, object]:
        build_calls.append((root_dir, max_depth))
        return {"schema_version": "test", "projects": []}

    def render_structure_audit_report(report: dict[str, object], *, output_format: str = "markdown") -> str:
        del report
        render_calls.append(output_format)
        if output_format == "json":
            return json.dumps({"format": output_format})
        return "# Structure audit\n"

    module.build_structure_audit_report = build_structure_audit_report
    module.render_structure_audit_report = render_structure_audit_report
    return module


def test_audit_structure_json_is_independent_and_emits_stdout_only_report(tmp_path: Path) -> None:
    build_calls: list[tuple[object, int]] = []
    render_calls: list[str] = []
    report_module = _report_module(build_calls, render_calls)
    stdout = io.StringIO()
    stderr = io.StringIO()

    with (
        patch.object(
            sys,
            "argv",
            ["orchestrator.py", "--audit-structure", "--audit-structure-format", "json", "--scan-depth", "2"],
        ),
        patch("orchestrator.get_hub_path", return_value=str(tmp_path / "hub")),
        patch("orchestrator.get_research_root", return_value=str(tmp_path)),
        patch.object(hub_core, "structure_audit_report", report_module),
        patch.dict(sys.modules, {"hub_core.structure_audit_report": report_module}),
        patch("orchestrator.run_analysis") as run_analysis,
        patch("orchestrator.run_plots") as run_plots,
        patch("orchestrator.run_check_all") as run_check_all,
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        result = orchestrator.main()

    assert result == 0
    assert json.loads(stdout.getvalue()) == {"format": "json"}
    assert build_calls == [(str(tmp_path), 2)]
    assert render_calls == ["json"]
    run_analysis.assert_not_called()
    run_plots.assert_not_called()
    run_check_all.assert_not_called()


def test_audit_structure_defaults_to_markdown_and_does_not_touch_project_files(tmp_path: Path) -> None:
    build_calls: list[tuple[object, int]] = []
    render_calls: list[str] = []
    report_module = _report_module(build_calls, render_calls)
    project_file = tmp_path / "project_config.yaml"
    project_file.write_text("project:\n  name: untouched\n", encoding="utf-8")
    original = project_file.read_bytes()

    with (
        patch.object(sys, "argv", ["orchestrator.py", "--audit-structure"]),
        patch("orchestrator.get_hub_path", return_value=str(tmp_path / "hub")),
        patch("orchestrator.get_research_root", return_value=str(tmp_path)),
        patch.object(hub_core, "structure_audit_report", report_module),
        patch.dict(sys.modules, {"hub_core.structure_audit_report": report_module}),
    ):
        result = orchestrator.main()

    assert result == 0
    assert render_calls == ["markdown"]
    assert project_file.read_bytes() == original


def test_audit_structure_rejects_execution_and_selector_modes(tmp_path: Path) -> None:
    build_calls: list[tuple[object, int]] = []
    render_calls: list[str] = []
    report_module = _report_module(build_calls, render_calls)

    for extra in (("--project", "module"), ("--check-all",), ("--list-projects",)):
        stdout = io.StringIO()
        with (
            patch.object(sys, "argv", ["orchestrator.py", "--audit-structure", *extra]),
            patch("orchestrator.get_hub_path", return_value=str(tmp_path / "hub")),
            patch("orchestrator.get_research_root", return_value=str(tmp_path)),
            patch.object(hub_core, "structure_audit_report", report_module),
            patch.dict(sys.modules, {"hub_core.structure_audit_report": report_module}),
            contextlib.redirect_stdout(stdout),
        ):
            result = orchestrator.main()

        assert result == 1
        assert "independent read-only mode" in stdout.getvalue()

    assert build_calls == []
    assert render_calls == []


def test_audit_structure_format_requires_audit_mode() -> None:
    stdout = io.StringIO()
    with (
        patch.object(sys, "argv", ["orchestrator.py", "--audit-structure-format", "json"]),
        contextlib.redirect_stdout(stdout),
    ):
        result = orchestrator.main()

    assert result == 1
    assert "requires --audit-structure" in stdout.getvalue()
