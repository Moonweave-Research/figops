from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _manifest(
    artifact_path: Path,
    *,
    visual_passed: bool = True,
    include_layout: bool = True,
) -> dict[str, object]:
    artifact_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    artifact_path.write_bytes(artifact_bytes)
    manifest: dict[str, object] = {
        "project_id": "demo",
        "figure_id": "Fig1",
        "artifact_status": "created",
        "figures": [{"path": str(artifact_path), "format": "png"}],
        "provenance": {
            "input_sha256": "1" * 64,
            "config_sha256": "2" * 64,
            "script_sha256": "3" * 64,
            "environment_sha256": "4" * 64,
            "output_sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        },
        "geometry_diagnostics": {
            "schema_version": "geometry_diagnostics/1",
            "passed": True,
            "checks": [],
        },
        "visual_preflight_status": {"passed": visual_passed},
    }
    if include_layout:
        manifest["layout_report"] = {"schema_version": "layout_report/1", "passed": True}
    return manifest


def _run(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "orchestrator.py", "--readiness-manifest", str(path), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_readiness_manifest_defaults_to_markdown_without_project(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest(tmp_path / "figure.png")), encoding="utf-8")

    result = _run(path)

    assert result.returncode == 0
    assert result.stdout.startswith("# Publication Readiness Report\n")
    assert "- Status: `needs_review`" in result.stdout
    assert "Attempt provenance" not in result.stdout
    assert result.stderr == ""


def test_readiness_manifest_legacy_adapter_does_not_invent_applied_policy(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest(tmp_path / "figure.png")), encoding="utf-8")

    result = _run(path, "--readiness-format", "json")

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["readiness_status"] == "needs_review"
    assert report["applied_policies"] == []
    assert not any(item["source"] == "policy_projection" for item in report["findings"])


def test_readiness_manifest_json_and_revision_exit_code(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest(tmp_path / "figure.png", visual_passed=False)), encoding="utf-8")

    result = _run(path, "--readiness-format", "json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["readiness_status"] == "blocked"
    assert report["project_id"] == "demo"
    assert report["figure_id"] == "Fig1"


def test_readiness_manifest_uses_exit_two_for_major_findings(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "figure.png")
    manifest["geometry_diagnostics"] = {
        "schema_version": "geometry_diagnostics/1",
        "passed": False,
        "checks": [{"name": "tick_label_crowding", "passed": False}],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = _run(path)

    assert result.returncode == 2
    assert "- Status: `needs_revision`" in result.stdout


def test_readiness_manifest_blocks_when_required_evidence_is_missing(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest(tmp_path / "figure.png", include_layout=False)), encoding="utf-8")

    result = _run(path)

    assert result.returncode == 1
    assert "REQUIRED_EVIDENCE_MISSING" in result.stdout


@pytest.mark.parametrize("conflict", [("--project", "demo"), ("--list-projects",), ("--check-all",)])
def test_readiness_manifest_rejects_other_operational_modes(tmp_path: Path, conflict: tuple[str, ...]) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest(tmp_path / "figure.png")), encoding="utf-8")

    result = _run(path, *conflict)

    assert result.returncode == 1
    assert "independent operational mode" in result.stdout
    assert result.stderr == ""


def test_readiness_manifest_reports_invalid_input_on_stdout(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{", encoding="utf-8")

    result = _run(path)

    assert result.returncode == 1
    assert result.stdout.startswith("Error: unable to evaluate readiness manifest:")
    assert result.stderr == ""


def test_readiness_format_requires_manifest() -> None:
    result = subprocess.run(
        [sys.executable, "orchestrator.py", "--readiness-format", "json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == "Error: --readiness-format requires --readiness-manifest.\n"
    assert result.stderr == ""
