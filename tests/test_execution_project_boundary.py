import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import orchestrator
from hub_core.execution_project_boundary import (
    PROJECT_EXECUTION_REPARSE_ERROR,
    ExecutionProjectPathError,
    resolve_execution_project_path,
)
from hub_core.visual_regression import run_check_all
from tests._symlink import symlink_or_skip


def _project_config(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "project_config.yaml").write_text(
        "project:\n  name: Boundary Fixture\nvisual_style:\n  target_format: neutral\n",
        encoding="utf-8",
    )


def test_execution_project_boundary_rejects_alias_and_accepts_real_project(tmp_path):
    root = tmp_path / "research"
    project = root / "real"
    _project_config(project)
    alias = root / "alias"
    symlink_or_skip(alias, project, target_is_directory=True)

    assert resolve_execution_project_path(root, project) == project.resolve()
    with pytest.raises(ExecutionProjectPathError, match=PROJECT_EXECUTION_REPARSE_ERROR):
        resolve_execution_project_path(root, alias)


def test_orchestrator_explicit_alias_fails_before_config_or_producer(tmp_path):
    root = tmp_path / "research"
    project = root / "real"
    _project_config(project)
    alias = root / "alias"
    symlink_or_skip(alias, project, target_is_directory=True)

    with (
        patch.object(sys, "argv", ["orchestrator.py", "--project", str(alias), "--step", "analysis"]),
        patch("orchestrator.get_research_root", return_value=str(root)),
        patch("orchestrator.load_config") as load_config,
        patch("orchestrator.run_analysis") as run_analysis,
    ):
        result = orchestrator.main()

    assert result == 1
    load_config.assert_not_called()
    run_analysis.assert_not_called()


def test_check_all_reports_alias_contract_failure_without_subprocess(tmp_path):
    root = tmp_path / "research"
    root.mkdir()
    discovered = [
        {
            "name": "Alias",
            "path": "alias",
            "config": "project_config.yaml",
            "valid": True,
            "errors": [],
        }
    ]
    baseline_state = {
        "baseline_dir": str(tmp_path / "baselines"),
        "files_dir": str(tmp_path / "baselines" / "files"),
        "manifest_path": str(tmp_path / "baselines" / "baseline_manifest.json"),
        "manifest": {"schema_version": 1, "updated_at": None, "figures": {}},
        "dirty": False,
        "was_updated": False,
    }

    with (
        patch("hub_core.visual_regression.discover_projects_with_status", return_value=discovered),
        patch(
            "hub_core.visual_regression.resolve_execution_project_path",
            side_effect=ExecutionProjectPathError(PROJECT_EXECUTION_REPARSE_ERROR),
        ),
        patch("hub_core.visual_regression._run_single_project") as run_single,
        patch("hub_core.visual_regression._load_baseline_state", return_value=baseline_state),
        patch("hub_core.visual_regression.write_check_all_report", return_value="report.json"),
    ):
        _report_path, report = run_check_all(tmp_path, root)

    run_single.assert_not_called()
    assert report["success"] is False
    assert report["results"][0]["failure_stage"] == "CONTRACT"
    assert PROJECT_EXECUTION_REPARSE_ERROR in report["results"][0]["message"]
