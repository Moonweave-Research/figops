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
            "graphhub_mcp_server.py",
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
