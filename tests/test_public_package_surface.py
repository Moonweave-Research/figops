import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from scripts.check_public_release import PRIVATE_MARKERS
from scripts.public_package_surface import blocked_path_reason, inspect_public_package_surface


def _sample_private_marker() -> str:
    return next(marker for marker in PRIVATE_MARKERS if "_" in marker)


def _write_tar_gz(path: Path, files: dict[str, str]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, text in files.items():
            source = path.parent / name.replace("/", "_")
            source.write_text(text, encoding="utf-8")
            archive.add(source, arcname=name)
            source.unlink()


def _write_wheel(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)


def test_public_package_surface_blocks_tests_in_sdist(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_tar_gz(
        dist / "figops-0.16.6.tar.gz",
        {
            "figops-0.16.6/pyproject.toml": "[project]\nname='x'\n",
            "figops-0.16.6/tests/test_private.py": "def test_x(): pass\n",
        },
    )

    result = inspect_public_package_surface(tmp_path)

    assert not result["ok"]
    assert any("tests/test_private.py" in blocker for blocker in result["blockers"])


def test_public_package_surface_blocks_private_marker_in_wheel(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    marker = _sample_private_marker()
    _write_wheel(
        dist / "figops-0.16.6-py3-none-any.whl",
        {"themes/journal_theme.py": f"STYLE = {marker!r}\n"},
    )

    result = inspect_public_package_surface(tmp_path)

    assert not result["ok"]
    assert any(marker in blocker for blocker in result["blockers"])


def test_public_package_surface_accepts_synthetic_minimal_artifacts(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_wheel(dist / "figops-0.16.6-py3-none-any.whl", {"hub_core/__init__.py": ""})
    _write_tar_gz(
        dist / "figops-0.16.6.tar.gz",
        {"figops-0.16.6/pyproject.toml": "[project]\nname='figops'\n"},
    )

    result = inspect_public_package_surface(tmp_path)

    assert result["ok"]
    assert result["artifact_count"] == 2


def test_public_package_surface_blocks_private_marker_in_packaged_r_file(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    marker = _sample_private_marker()
    _write_wheel(
        dist / "figops-0.16.6-py3-none-any.whl",
        {"themes/journal_theme.R": f"note <- {marker!r}\n"},
    )

    result = inspect_public_package_surface(tmp_path)

    assert not result["ok"]
    assert any("journal_theme.R" in blocker and marker in blocker for blocker in result["blockers"])


def test_public_package_surface_allows_packaged_scaffold_template(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_wheel(
        dist / "figops-0.16.6-py3-none-any.whl",
        {"hub_core/templates/project_config_template.yaml": "project:\n  name: Example\n"},
    )

    result = inspect_public_package_surface(tmp_path)

    assert result["ok"]


def test_blocked_path_reason_matches_private_publication_surfaces():
    assert blocked_path_reason("figops-0.16.6/tests/test_private.py") == "*/tests/*"
    assert blocked_path_reason("figops-0.16.6/docs/internal/protocols/01.md") == "*/docs/internal/protocols/*"
    assert blocked_path_reason("figops-0.16.6/project_config_template.yaml") == "figops-*/project_config_template.yaml"
    assert blocked_path_reason("figops-0.16.6/hub_core/templates/project_config_template.yaml") is None


def test_installed_ai_native_surface_budget(tmp_path: Path) -> None:
    """Exercise the packaged modules from an isolated, wheel-shaped archive."""
    wheel = tmp_path / "figops-0.20.0-py3-none-any.whl"
    hub_root = Path(__file__).resolve().parents[1]
    with zipfile.ZipFile(wheel, "w") as archive:
        for package in ("hub_core", "plotting", "themes"):
            for source in (hub_root / package).rglob("*"):
                if source.is_file() and source.suffix in {".py", ".yaml", ".json", ".R"}:
                    archive.write(source, source.relative_to(hub_root).as_posix())

    script = """
import json, sys
sys.path.insert(0, sys.argv[1])
from hub_core.mcp.schemas import list_tool_definitions
from hub_core.mcp.server import FigOpsMCPServer
from hub_core.mcp.surface_profiles import COMPATIBILITY_CANONICAL_NAMES, V2_TOOL_NAMES
from hub_core.mcp.transport import _handle_json_rpc
names = [item['name'] for item in list_tool_definitions(profile='v2', write_tools_enabled=True)]
compatibility_only = (set(COMPATIBILITY_CANONICAL_NAMES) - set(V2_TOOL_NAMES)) | {
    name.replace('figops.', 'graphhub.', 1) for name in COMPATIBILITY_CANONICAL_NAMES
}
assert names == list(V2_TOOL_NAMES)
assert len(names) <= 8
assert set(names).isdisjoint(compatibility_only)
server = FigOpsMCPServer(
    surface_profile='v2',
    write_tools_enabled=True,
    research_root=sys.argv[2],
    runtime_root=sys.argv[3],
)
assert list(server._handlers) == names
assert [item['name'] for item in server.callable_tool_definitions()] == names
for guessed in ('figops.list_projects', 'figops.render_csv_graph', 'graphhub.health'):
    try:
        server.call_tool(guessed, {})
    except ValueError as exc:
        assert 'Unknown FigOps MCP tool' in str(exc)
    else:
        raise AssertionError(f'hidden compatibility tool was callable: {guessed}')
    response = _handle_json_rpc(server, {
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
        'params': {'name': guessed, 'arguments': {}},
    })
    assert response['error']['code'] == -32602
print(json.dumps(names))
"""
    completed = subprocess.run(
        [sys.executable, "-I", "-c", script, str(wheel), str(tmp_path), str(tmp_path / "runtime")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert len(json.loads(completed.stdout)) <= 8
