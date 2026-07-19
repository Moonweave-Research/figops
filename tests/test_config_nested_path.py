from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hub_core.config_parser import load_config


def _write_minimal_config(path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"project:\n  name: {name}\n", encoding="utf-8")


def test_load_config_preserves_nested_legacy_config_path(tmp_path: Path) -> None:
    project = tmp_path / "project"
    config_path = project / "scripts" / "project_config.yaml"
    _write_minimal_config(config_path, "nested")

    config, loaded_path, config_hash = load_config(project)

    assert config is not None
    assert config["project"]["name"] == "nested"
    assert loaded_path == str(config_path.absolute())
    assert config_hash


def test_load_config_still_preserves_root_config_path(tmp_path: Path) -> None:
    project = tmp_path / "project"
    config_path = project / "project_config.yaml"
    _write_minimal_config(config_path, "root")

    config, loaded_path, config_hash = load_config(project)

    assert config is not None
    assert config["project"]["name"] == "root"
    assert loaded_path == str(config_path.absolute())
    assert config_hash


def test_load_config_revalidates_nested_path_relative_to_lexical_alias_root(
    tmp_path: Path,
) -> None:
    lexical_project = (tmp_path / "alias-project").absolute()
    lexical_project.mkdir()
    canonical_config = tmp_path / "canonical-project" / "scripts" / "project_config.yaml"
    _write_minimal_config(canonical_config, "alias")
    lexical_config = lexical_project / "scripts" / "project_config.yaml"

    with (
        patch(
            "hub_core.config_parser.find_config_path",
            return_value=str(lexical_config),
        ),
        patch(
            "hub_core.config_path_discovery.resolve_project_input",
            return_value=canonical_config,
        ) as resolver,
    ):
        config, loaded_path, config_hash = load_config(lexical_project)

    assert config is not None
    assert config["project"]["name"] == "alias"
    assert loaded_path == str(lexical_config)
    assert config_hash
    resolver.assert_called_once_with(
        lexical_project,
        "scripts/project_config.yaml",
        purpose="project config",
    )


def test_load_config_rejects_nested_config_symlink_escape(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    config_path = outside / "project_config.yaml"
    _write_minimal_config(config_path, "outside")
    scripts = project / "scripts"
    try:
        scripts.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")

    assert load_config(project) == (None, None, None)
