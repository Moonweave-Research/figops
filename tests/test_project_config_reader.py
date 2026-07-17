from __future__ import annotations

import sys
from pathlib import Path

import pytest

from hub_core.project_config_reader import ProjectConfigReadError, read_verified_project_config


def _write_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("project:\n  name: boundary-test\n", encoding="utf-8")


def _symlink_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")


def test_absolute_config_accepts_alias_of_project_root_without_losing_declaration(
    tmp_path: Path,
) -> None:
    canonical_parent = tmp_path / "canonical"
    project = canonical_parent / "project"
    config = project / "scripts" / "project_config.yaml"
    _write_config(config)
    alias_parent = tmp_path / "alias"
    _symlink_or_skip(alias_parent, canonical_parent, directory=True)

    payload = read_verified_project_config(project.resolve(), alias_parent / "project" / "scripts" / config.name)

    assert "boundary-test" in payload


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS fixed /var alias contract")
def test_absolute_config_accepts_macos_var_alias(tmp_path: Path) -> None:
    project = tmp_path / "project"
    config = project / "project_config.yaml"
    _write_config(config)
    canonical = config.resolve(strict=True)
    if not canonical.as_posix().startswith("/private/var/"):
        pytest.skip("temporary directory is not below the macOS /var alias")
    lexical = Path("/var") / canonical.relative_to("/private/var")

    payload = read_verified_project_config(project.resolve(), lexical)

    assert "boundary-test" in payload


def test_absolute_config_rejects_external_symlink_target(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external.yaml"
    _write_config(external)
    config = project / "project_config.yaml"
    _symlink_or_skip(config, external)

    with pytest.raises(ProjectConfigReadError, match="stay inside the project root"):
        read_verified_project_config(project.resolve(), config.absolute())


def test_absolute_config_rejects_internal_nested_symlink_component(tmp_path: Path) -> None:
    project = tmp_path / "project"
    real_scripts = project / "real-scripts"
    config = real_scripts / "project_config.yaml"
    _write_config(config)
    scripts_alias = project / "scripts"
    _symlink_or_skip(scripts_alias, real_scripts, directory=True)

    with pytest.raises(ProjectConfigReadError, match="must not traverse a symlink"):
        read_verified_project_config(project.resolve(), scripts_alias / config.name)
