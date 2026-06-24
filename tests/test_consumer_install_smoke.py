from pathlib import Path

import pytest

from scripts.consumer_install_smoke import consumer_smoke_commands, expected_wheel_name, resolve_wheel


def _write_pyproject(root: Path, version: str = "1.2.3") -> None:
    (root / "pyproject.toml").write_text(f'[project]\nname = "figops"\nversion = "{version}"\n')


def test_expected_wheel_name_uses_current_project_version(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "1.2.3")

    assert expected_wheel_name(tmp_path) == "figops-1.2.3-py3-none-any.whl"


def test_resolve_wheel_requires_built_current_version(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "1.2.3")
    (tmp_path / "dist").mkdir()

    with pytest.raises(FileNotFoundError, match="Run `uv build` first"):
        resolve_wheel(tmp_path)


def test_resolve_wheel_accepts_explicit_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / "custom.whl"
    wheel.write_text("wheel", encoding="utf-8")

    assert resolve_wheel(tmp_path, wheel) == wheel.resolve()


def test_consumer_smoke_commands_use_isolated_uv_with_console_scripts(tmp_path: Path) -> None:
    wheel = tmp_path / "figops-1.2.3-py3-none-any.whl"

    commands = consumer_smoke_commands(wheel, uv_bin="uv-test")

    assert commands == (
        ("uv-test", "run", "--isolated", "--with", str(wheel), "figops-mcp", "--smoke"),
        ("uv-test", "run", "--isolated", "--with", str(wheel), "figops", "--help"),
    )
