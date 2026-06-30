import json
import os
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


def test_doctor_reports_missing_source_checkout_dependencies(monkeypatch, tmp_path):
    missing_modules = {"matplotlib", "pandas", "pytest", "yaml"}

    def fake_find_spec(name):
        if name in missing_modules:
            return None
        return object()

    monkeypatch.setattr("hub_core.doctor.importlib.util.find_spec", fake_find_spec)

    report = run_doctor(_config(tmp_path))
    checks = {check["name"]: check for check in report["checks"]}

    assert report["status"] == "error"
    assert report["ready"] is False
    assert checks["runtime_dependencies"]["status"] == "error"
    assert checks["runtime_dependencies"]["details"]["missing"] == ["matplotlib", "pandas", "yaml"]
    assert "python hub_uv.py sync" in checks["runtime_dependencies"]["hint"]
    assert checks["pytest"]["status"] == "warning"
    assert "source-checkout tests cannot run" in checks["pytest"]["summary"]
    assert "sync --group dev" in checks["pytest"]["hint"]


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
    assert {
        "python",
        "uv",
        "runtime_dependencies",
        "pytest",
        "pyarrow",
        "tables",
        "Rscript",
        "write_tools",
        "roots",
        "adapters",
    }.issubset(checks)


def test_doctor_json_reports_missing_deps_without_importing_heavy_mcp_modules(tmp_path):
    import_guard = tmp_path / "sitecustomize.py"
    import_guard.write_text(
        """
import builtins
import importlib.util

_blocked_imports = {
    "hub_core.mcp.schemas",
    "hub_core.mcp.server",
    "hub_core.mcp.resources",
    "hub_core.mcp.tools.render_support",
    "themes.journal_theme",
    "themes.style_packs",
    "themes.style_profiles",
}
_missing_specs = {"matplotlib", "pandas", "yaml"}
_real_import = builtins.__import__
_real_find_spec = importlib.util.find_spec


def _is_blocked(name):
    return any(name == blocked or name.startswith(blocked + ".") for blocked in _blocked_imports)


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if _is_blocked(name):
        raise ImportError(f"blocked heavy doctor import: {name}")
    return _real_import(name, globals, locals, fromlist, level)


def _guarded_find_spec(name, package=None):
    if name in _missing_specs:
        return None
    return _real_find_spec(name, package)


builtins.__import__ = _guarded_import
importlib.util.find_spec = _guarded_find_spec
""".lstrip(),
        encoding="utf-8",
    )
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(tmp_path), str(HUB_ROOT), env["PYTHONPATH"]] if env.get("PYTHONPATH") else [str(tmp_path), str(HUB_ROOT)]
    )

    completed = subprocess.run(
        [
            sys.executable,
            "figops_mcp_server.py",
            "--hub-path",
            str(HUB_ROOT),
            "--research-root",
            str(tmp_path),
            "--runtime-root",
            str(runtime_root),
            "doctor",
            "--json",
        ],
        cwd=HUB_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1, completed.stderr
    report = json.loads(completed.stdout)
    checks = {check["name"]: check for check in report["checks"]}
    assert report["status"] == "error"
    assert report["ready"] is False
    assert checks["runtime_dependencies"]["status"] == "error"
    assert checks["runtime_dependencies"]["details"]["missing"] == ["matplotlib", "pandas", "yaml"]
    assert "blocked heavy doctor import" not in completed.stderr


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
