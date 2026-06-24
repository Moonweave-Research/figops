import tarfile
import zipfile
from pathlib import Path

from scripts.package_metadata_smoke import inspect_package_metadata

PYPROJECT = """
[project]
name = "graph-making-hub"
version = "1.2.3"
authors = [{ name = "Choemun Yeong" }]
maintainers = [{ name = "Moonweave Research" }]
[project.scripts]
graphhub = "orchestrator:main"
graphhub-mcp = "graphhub_mcp_server:main"
"""

METADATA = """Metadata-Version: 2.4
Name: graph-making-hub
Version: 1.2.3
Author: Choemun Yeong
Maintainer: Moonweave Research
"""

ENTRY_POINTS = """[console_scripts]
graphhub = orchestrator:main
graphhub-mcp = graphhub_mcp_server:main
"""


def _write_pyproject(root: Path) -> None:
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")


def _write_wheel(path: Path, metadata: str = METADATA, entry_points: str = ENTRY_POINTS) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("graph_making_hub-1.2.3.dist-info/METADATA", metadata)
        archive.writestr("graph_making_hub-1.2.3.dist-info/entry_points.txt", entry_points)


def _write_sdist(path: Path, metadata: str = METADATA, entry_points: str = ENTRY_POINTS) -> None:
    pkg_info = path.parent / "PKG-INFO"
    entry_file = path.parent / "entry_points.txt"
    pkg_info.write_text(metadata, encoding="utf-8")
    entry_file.write_text(entry_points, encoding="utf-8")
    with tarfile.open(path, "w:gz") as archive:
        archive.add(pkg_info, arcname="graph_making_hub-1.2.3/PKG-INFO")
        archive.add(entry_file, arcname="graph_making_hub-1.2.3/graph_making_hub.egg-info/entry_points.txt")
    pkg_info.unlink()
    entry_file.unlink()


def test_package_metadata_smoke_accepts_matching_artifacts(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_wheel(dist / "graph_making_hub-1.2.3-py3-none-any.whl")
    _write_sdist(dist / "graph_making_hub-1.2.3.tar.gz")

    result = inspect_package_metadata(tmp_path)

    assert result["ok"]
    assert result["artifact_count"] == 2
    assert result["expected"]["authors"] == ["Choemun Yeong"]
    assert result["expected"]["console_scripts"]["graphhub-mcp"] == "graphhub_mcp_server:main"


def test_package_metadata_smoke_blocks_wrong_author(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_wheel(
        dist / "graph_making_hub-1.2.3-py3-none-any.whl",
        metadata=METADATA.replace("Author: Choemun Yeong", "Author: Someone Else"),
    )

    result = inspect_package_metadata(tmp_path)

    assert not result["ok"]
    assert any("Author" in blocker and "Choemun Yeong" in blocker for blocker in result["blockers"])


def test_package_metadata_smoke_blocks_missing_console_script(tmp_path: Path) -> None:
    _write_pyproject(tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_wheel(
        dist / "graph_making_hub-1.2.3-py3-none-any.whl",
        entry_points="[console_scripts]\ngraphhub = orchestrator:main\n",
    )

    result = inspect_package_metadata(tmp_path)

    assert not result["ok"]
    assert any("graphhub-mcp" in blocker for blocker in result["blockers"])
