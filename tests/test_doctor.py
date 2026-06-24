import json
import subprocess
import sys
from pathlib import Path

from hub_core.doctor import run_doctor
from hub_core.mcp import McpServerConfig

HUB_ROOT = Path(__file__).resolve().parent.parent


def _config(tmp_path: Path) -> McpServerConfig:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    return McpServerConfig(hub_path=HUB_ROOT, research_root=tmp_path, runtime_root=runtime_root)


def test_doctor_reports_missing_tools_with_actionable_hints(monkeypatch, tmp_path):
    monkeypatch.setattr("hub_core.doctor.shutil.which", lambda _name: None)

    report = run_doctor(_config(tmp_path))
    checks = {check["name"]: check for check in report["checks"]}

    assert report["status"] == "error"
    assert report["ready"] is False
    assert checks["uv"]["status"] == "error"
    assert "Install uv" in checks["uv"]["hint"]
    assert checks["Rscript"]["status"] == "warning"
    assert "Install R" in checks["Rscript"]["hint"]


def test_doctor_json_reports_structured_readiness(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "figops_mcp_server.py",
            "--hub-path",
            str(HUB_ROOT),
            "--research-root",
            str(tmp_path),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "doctor",
            "--json",
        ],
        cwd=HUB_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    checks = {check["name"]: check for check in report["checks"]}
    assert report["status"] in {"ok", "warning"}
    assert report["ready"] is True
    assert {"python", "uv", "pyarrow", "tables", "Rscript", "write_tools", "roots", "adapters"}.issubset(checks)


def test_doctor_reports_invalid_adapter_without_silent_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPH_HUB_PREFETCH_ADAPTER", "invalid")

    report = run_doctor(_config(tmp_path))
    checks = {check["name"]: check for check in report["checks"]}

    assert report["status"] == "error"
    assert report["ready"] is False
    assert checks["adapters"]["status"] == "error"
    assert "Unknown prefetch adapter" in checks["adapters"]["summary"]
    assert "GRAPH_HUB_PREFETCH_ADAPTER" in checks["adapters"]["hint"]


def test_doctor_roots_warn_when_runtime_root_is_missing(tmp_path):
    config = McpServerConfig(hub_path=HUB_ROOT, research_root=tmp_path, runtime_root=tmp_path / "missing-runtime")

    report = run_doctor(config)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["status"] in {"warning", "error"}
    assert checks["roots"]["status"] == "warning"
    assert "does not exist" in checks["roots"]["summary"]
    assert "runtime_root" in checks["roots"]["details"]["warnings"][0]
    assert "runtime_root" in checks["roots"]["hint"]


def test_doctor_roots_allow_missing_implicit_runtime_root(monkeypatch, tmp_path):
    preview_runtime_root = tmp_path / "preview-runtime"
    monkeypatch.setattr("hub_core.mcp.security.preview_runtime_root", lambda: str(preview_runtime_root))

    report = run_doctor(McpServerConfig(hub_path=HUB_ROOT, research_root=tmp_path))
    checks = {check["name"]: check for check in report["checks"]}

    assert checks["roots"]["status"] == "ok"
    assert checks["roots"]["details"]["runtime_root"] == str(preview_runtime_root.resolve())
    assert not preview_runtime_root.exists()


def test_doctor_roots_error_when_research_root_is_missing(tmp_path):
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    config = McpServerConfig(hub_path=HUB_ROOT, research_root=tmp_path / "missing-research", runtime_root=runtime_root)

    report = run_doctor(config)
    checks = {check["name"]: check for check in report["checks"]}

    assert report["status"] == "error"
    assert report["ready"] is False
    assert checks["roots"]["status"] == "error"
    assert "research_root" in checks["roots"]["details"]["errors"][0]


def test_doctor_write_tools_enabled_summary_disclaims_execution_verification(tmp_path):
    config = _config(tmp_path)
    config = McpServerConfig(
        hub_path=config.hub_path,
        research_root=config.research_root,
        runtime_root=config.runtime_root,
        write_tools_enabled=True,
    )

    report = run_doctor(config)
    checks = {check["name"]: check for check in report["checks"]}

    assert checks["write_tools"]["status"] == "ok"
    assert "not execution-verified" in checks["write_tools"]["summary"]
