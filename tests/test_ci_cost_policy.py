from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from scripts.check_ci_cost_policy import WorkflowNode, check_workflow_policy

HUB_ROOT = Path(__file__).resolve().parent.parent
CHECKER = HUB_ROOT / "scripts" / "check_ci_cost_policy.py"
CANDIDATE_WORKFLOW = HUB_ROOT / "docs" / "ops" / "ci-cost-control-workflow.candidate.yml"
DOCS_ONLY_PATTERNS = ["docs/**", "**/*.md", ".omo/**"]


def _run_checker(workflow: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--workflow", str(workflow)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _write_workflow(path: Path, workflow: dict[str, WorkflowNode]) -> None:
    path.write_text(yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8")


def _trigger_with_paths_ignore(patterns: list[str]) -> dict[str, WorkflowNode]:
    return {
        "pull_request": {"paths-ignore": patterns},
        "workflow_dispatch": {"inputs": {"run_heavy_gates": {"type": "boolean", "default": False}}},
    }


def _standard_workflow(jobs: dict[str, WorkflowNode]) -> dict[str, WorkflowNode]:
    return {
        "name": "Test Workflow",
        "on": _trigger_with_paths_ignore(DOCS_ONLY_PATTERNS),
        "concurrency": {"group": "test-policy", "cancel-in-progress": True},
        "jobs": jobs,
    }


def _quick_job() -> dict[str, WorkflowNode]:
    return {
        "runs-on": "ubuntu-latest",
        "timeout-minutes": 10,
        "steps": [{"run": "pytest tests/test_runtime_paths.py"}],
    }


def _gated_heavy_job() -> dict[str, WorkflowNode]:
    return {
        "if": "${{ github.event_name == 'workflow_dispatch' && inputs.run_heavy_gates }}",
        "runs-on": "ubuntu-latest",
        "timeout-minutes": 20,
        "steps": [{"run": "pytest -q"}],
    }


def _write_standard_workflow(path: Path, jobs: dict[str, WorkflowNode]) -> None:
    _write_workflow(path, _standard_workflow(jobs))


def test_checker_passes_candidate_workflow_when_required_controls_exist():
    completed = _run_checker(CANDIDATE_WORKFLOW)

    assert completed.returncode == 0
    assert "PASS: timeout-minutes" in completed.stdout
    assert "PASS: concurrency" in completed.stdout
    assert "PASS: docs-only avoidance" in completed.stdout
    assert "PASS: manual heavy gates" in completed.stdout
    assert "required CI cost controls are present" in completed.stdout


def test_checker_fails_when_required_controls_are_missing(tmp_path: Path):
    workflow = tmp_path / "missing-controls.yml"
    _write_workflow(
        workflow,
        {"name": "Missing Controls", "on": {"pull_request": None}, "jobs": {"test": {"runs-on": "ubuntu-latest"}}},
    )

    completed = _run_checker(workflow)

    assert completed.returncode == 1
    assert "FAIL: timeout-minutes" in completed.stdout
    assert "FAIL: concurrency" in completed.stdout
    assert "FAIL: docs-only avoidance" in completed.stdout
    assert "FAIL: manual heavy gates" in completed.stdout
    assert "required CI cost controls are missing" in completed.stderr


def test_checker_rejects_path_policy_without_docs_only_coverage(tmp_path: Path):
    workflow = tmp_path / "weak-paths.yml"
    payload = _standard_workflow({"test": _quick_job(), "heavy": _gated_heavy_job()})
    payload["on"] = _trigger_with_paths_ignore(["src/generated/**"])
    _write_workflow(workflow, payload)

    completed = _run_checker(workflow)

    assert completed.returncode == 1
    assert "FAIL: docs-only avoidance" in completed.stdout
    assert "docs/**, **/*.md, and .omo/**" in completed.stdout


def test_checker_rejects_paths_ignore_superset_with_non_docs_ignore(tmp_path: Path):
    workflow = tmp_path / "paths-ignore-superset.yml"
    payload = _standard_workflow({"test": _quick_job(), "heavy": _gated_heavy_job()})
    payload["on"] = _trigger_with_paths_ignore([*DOCS_ONLY_PATTERNS, "src/generated/**"])
    _write_workflow(workflow, payload)

    completed = _run_checker(workflow)

    assert completed.returncode == 1
    assert "FAIL: docs-only avoidance" in completed.stdout


def test_checker_rejects_paths_policy_that_includes_docs_only_changes(tmp_path: Path):
    workflow = tmp_path / "docs-including-paths.yml"
    payload = _standard_workflow({"test": _quick_job(), "heavy": _gated_heavy_job()})
    payload["on"] = {
        "pull_request": {"paths": DOCS_ONLY_PATTERNS},
        "workflow_dispatch": {"inputs": {"run_heavy_gates": {"type": "boolean", "default": False}}},
    }
    _write_workflow(workflow, payload)

    completed = _run_checker(workflow)

    assert completed.returncode == 1
    assert "FAIL: docs-only avoidance" in completed.stdout


def test_checker_accepts_path_filter_output_gating_test_job(tmp_path: Path):
    workflow = tmp_path / "path-filter.yml"
    payload = _standard_workflow({"path-filter": _path_filter_job("!docs/**\n!**/*.md\n!.omo/**"), "heavy": _gated_heavy_job()})
    payload["on"] = {"pull_request": None, "workflow_dispatch": {"inputs": {"run_heavy_gates": {"type": "boolean", "default": False}}}}
    payload["jobs"]["test"] = _path_gated_test_job()
    _write_workflow(workflow, payload)

    completed = _run_checker(workflow)

    assert completed.returncode == 0
    assert "PASS: docs-only avoidance" in completed.stdout
    assert "path-filter job gates the full test job" in completed.stdout


def _path_filter_job(filters: str) -> dict[str, WorkflowNode]:
    return {
        "name": "Path filter",
        "runs-on": "ubuntu-latest",
        "timeout-minutes": 5,
        "outputs": {"non_docs": "${{ steps.filter.outputs.non_docs }}"},
        "steps": [{"uses": "dorny/paths-filter@v3", "id": "filter", "with": {"filters": filters}}],
    }


def _path_gated_test_job() -> dict[str, WorkflowNode]:
    job = _quick_job()
    job["needs"] = "path-filter"
    job["if"] = "${{ needs.path-filter.outputs.non_docs == 'true' }}"
    return job


def test_checker_rejects_path_filter_without_docs_only_coverage(tmp_path: Path):
    workflow = tmp_path / "weak-path-filter.yml"
    payload = _standard_workflow({"path-filter": _path_filter_job("src/generated/**"), "heavy": _gated_heavy_job()})
    payload["on"] = {"pull_request": None, "workflow_dispatch": {"inputs": {"run_heavy_gates": {"type": "boolean", "default": False}}}}
    payload["jobs"]["test"] = _path_gated_test_job()
    _write_workflow(workflow, payload)

    completed = _run_checker(workflow)

    assert completed.returncode == 1
    assert "FAIL: docs-only avoidance" in completed.stdout


def test_checker_rejects_ungated_full_suite_pr_job(tmp_path: Path):
    workflow = tmp_path / "ungated-full-suite.yml"
    _write_standard_workflow(workflow, {"full-suite": {"name": "Full suite", **_quick_job(), "timeout-minutes": 45}})

    completed = _run_checker(workflow)

    assert completed.returncode == 1
    assert "FAIL: manual heavy gates" in completed.stdout
    assert "workflow_dispatch input gate" in completed.stdout


def test_checker_rejects_heavy_gate_using_or_expression(tmp_path: Path):
    workflow = tmp_path / "or-heavy-gate.yml"
    full_suite = {"name": "Full suite", **_quick_job(), "timeout-minutes": 45}
    full_suite["if"] = "${{ github.event_name == 'workflow_dispatch' || inputs.run_heavy_gates }}"
    _write_standard_workflow(workflow, {"full-suite": full_suite})

    completed = _run_checker(workflow)

    assert completed.returncode == 1
    assert "FAIL: manual heavy gates" in completed.stdout
    assert "workflow_dispatch input gate" in completed.stdout


def test_checker_reports_malformed_or_missing_workflow_cleanly(tmp_path: Path):
    missing_completed = _run_checker(tmp_path / "missing.yml")

    assert missing_completed.returncode == 2
    assert "ERROR: cannot read workflow" in missing_completed.stderr

    malformed = tmp_path / "malformed.yml"
    malformed.write_text("jobs: [", encoding="utf-8")
    malformed_completed = _run_checker(malformed)

    assert malformed_completed.returncode == 2
    assert "ERROR: cannot parse workflow YAML" in malformed_completed.stderr


def test_checker_reads_workflow_path_at_runtime_not_cached_state(tmp_path: Path):
    workflow = tmp_path / "mutable.yml"
    _write_standard_workflow(workflow, {"test": _quick_job(), "heavy": _gated_heavy_job()})

    first_report = check_workflow_policy(workflow)

    _write_workflow(workflow, {"name": "Second State", "on": {"pull_request": None}, "jobs": {"test": {"runs-on": "ubuntu-latest"}}})
    second_completed = _run_checker(workflow)

    assert not isinstance(first_report, str)
    assert first_report.passed
    assert second_completed.returncode == 1
    assert "FAIL: timeout-minutes" in second_completed.stdout
