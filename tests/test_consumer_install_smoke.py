from pathlib import Path

import pytest

from scripts.consumer_install_smoke import consumer_smoke_commands, expected_wheel_name, resolve_wheel

AUTHENTIC_STYLE_METADATA_SMOKE = (
    "import json; "
    "from themes.authentic_style_language import get_authentic_style_language_metadata; "
    "metadata = get_authentic_style_language_metadata('nature'); "
    "assert metadata['matrix_source'] == 'package:themes/data/journal_visual_language_matrix.json'; "
    "print(json.dumps(metadata, sort_keys=True))"
)


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

    commands = consumer_smoke_commands(wheel, uv_bin="uv-test", scaffold_project="/tmp/smoke_project")

    assert commands == (
        (
            "uv-test",
            "run",
            "--isolated",
            "--with",
            str(wheel),
            "python",
            "-c",
            AUTHENTIC_STYLE_METADATA_SMOKE,
        ),
        ("uv-test", "run", "--isolated", "--with", str(wheel), "figops-mcp", "--smoke"),
        ("uv-test", "run", "--isolated", "--with", str(wheel), "figops", "--help"),
        ("uv-test", "run", "--isolated", "--with", str(wheel), "figops", "--init", "--project", "/tmp/smoke_project"),
    )
