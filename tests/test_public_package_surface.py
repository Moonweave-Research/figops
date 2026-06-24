import tarfile
import zipfile
from pathlib import Path

from scripts.public_package_surface import blocked_path_reason, inspect_public_package_surface


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
    _write_wheel(
        dist / "figops-0.16.6-py3-none-any.whl",
        {"themes/journal_theme.py": "STYLE = 'nature_surfur'\n"},
    )

    result = inspect_public_package_surface(tmp_path)

    assert not result["ok"]
    assert any("nature_surfur" in blocker for blocker in result["blockers"])


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
    _write_wheel(
        dist / "figops-0.16.6-py3-none-any.whl",
        {"themes/journal_theme.R": "note <- 'nature_surfur'\n"},
    )

    result = inspect_public_package_surface(tmp_path)

    assert not result["ok"]
    assert any("journal_theme.R" in blocker and "nature_surfur" in blocker for blocker in result["blockers"])


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
    assert blocked_path_reason("figops-0.16.6/docs/hks/01.md") == "*/docs/hks/*"
    assert blocked_path_reason("figops-0.16.6/project_config_template.yaml") == "figops-*/project_config_template.yaml"
    assert blocked_path_reason("figops-0.16.6/hub_core/templates/project_config_template.yaml") is None
