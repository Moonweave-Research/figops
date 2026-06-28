from __future__ import annotations

import sys

import orchestrator


def test_init_scaffold_runs_before_runtime_preflight(monkeypatch, tmp_path):
    project_dir = tmp_path / "smoke_project"

    monkeypatch.setattr(orchestrator, "get_hub_path", lambda: str(tmp_path / "hub"))
    monkeypatch.setattr(orchestrator, "get_research_root", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "configure_logging", lambda verbose=False: None)
    monkeypatch.setattr(orchestrator, "ui_panel", lambda *args, **kwargs: None)

    def fail_preflight(*args, **kwargs):
        raise AssertionError("runtime preflight should not run for --init")

    monkeypatch.setattr(orchestrator, "run_preflight_check", fail_preflight)
    monkeypatch.setattr(
        orchestrator,
        "scaffold_project",
        lambda target, hub_path: {"project_name": "smoke_project", "project_dir": str(project_dir)},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["orchestrator.py", "--init", "--project", str(project_dir)],
    )

    assert orchestrator.main() == 0
