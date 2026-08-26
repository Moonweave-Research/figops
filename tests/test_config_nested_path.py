from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

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


def test_load_config_preserves_discovered_lexical_path_at_verified_read_boundary(
    tmp_path: Path,
) -> None:
    lexical_project = (tmp_path / "alias-project").absolute()
    lexical_project.mkdir()
    lexical_config = lexical_project / "scripts" / "project_config.yaml"
    prefetcher = MagicMock()

    with (
        patch(
            "hub_core.config_parser.find_config_path",
            return_value=str(lexical_config),
        ),
        patch("hub_core.config_parser.select_prefetcher", return_value=prefetcher),
        patch(
            "hub_core.config_parser.read_verified_project_config",
            return_value="project:\n  name: alias\n",
        ) as reader,
    ):
        config, loaded_path, config_hash = load_config(lexical_project)

    assert config is not None
    assert config["project"]["name"] == "alias"
    assert loaded_path == str(lexical_config)
    assert config_hash
    reader.assert_called_once_with(
        lexical_project,
        str(lexical_config),
        prefetcher=prefetcher,
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


def test_load_config_uses_selected_prefetcher_at_verified_read_boundary(tmp_path: Path) -> None:
    project = tmp_path / "project"
    config_path = project / "project_config.yaml"
    _write_minimal_config(config_path, "prefetched")
    prefetcher = MagicMock()

    with patch("hub_core.config_parser.select_prefetcher", return_value=prefetcher):
        config, _loaded_path, _config_hash = load_config(project)

    assert config is not None
    prefetcher.ensure_local.assert_called_once_with([str(config_path)])


def test_load_config_rejects_hardlinked_config(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = tmp_path / "source.yaml"
    _write_minimal_config(source, "hardlinked")
    config_path = project / "project_config.yaml"
    try:
        os.link(source, config_path)
    except OSError as exc:
        pytest.skip(f"hardlinks unavailable: {exc}")

    assert load_config(project) == (None, None, None)


def test_load_config_rejects_invalid_cache_strategy(tmp_path: Path) -> None:
    project = tmp_path / "project"
    config_path = project / "project_config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "project:\n  name: invalid-cache\nexecution:\n  cache_strategy: fast\n",
        encoding="utf-8",
    )

    assert load_config(project) == (None, None, None)
