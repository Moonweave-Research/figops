import sys
from pathlib import Path

from scripts import guarded_pypi_upload
from scripts.check_public_release import ReleaseCheckResult


def test_guarded_upload_blocks_private_license(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("All rights reserved.\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("No open source license has been granted.\n", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "graph_making_hub-0.16.4-py3-none-any.whl").write_text("placeholder", encoding="utf-8")

    blockers = guarded_pypi_upload.upload_blockers(tmp_path)

    assert any("all-rights-reserved" in blocker for blocker in blockers)
    assert any("no open source license" in blocker for blocker in blockers)


def test_guarded_upload_requires_distribution_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        guarded_pypi_upload,
        "run_release_check",
        lambda _root: ReleaseCheckResult(blockers=(), warnings=()),
    )

    blockers = guarded_pypi_upload.upload_blockers(tmp_path)

    assert blockers == ("No distribution files found for glob: dist/*",)


def test_guarded_upload_command_defaults_to_testpypi_repository(tmp_path: Path) -> None:
    wheel = tmp_path / "dist" / "graph_making_hub-0.16.4-py3-none-any.whl"
    wheel.parent.mkdir()
    wheel.write_text("placeholder", encoding="utf-8")

    command = guarded_pypi_upload.build_upload_command("testpypi", [wheel])

    assert command == [sys.executable, "-m", "twine", "upload", "--repository", "testpypi", str(wheel)]


def test_guarded_upload_command_uses_default_pypi_target_without_repository_alias(tmp_path: Path) -> None:
    sdist = tmp_path / "dist" / "graph_making_hub-0.16.4.tar.gz"
    sdist.parent.mkdir()
    sdist.write_text("placeholder", encoding="utf-8")

    command = guarded_pypi_upload.build_upload_command("pypi", [sdist])

    assert command == [sys.executable, "-m", "twine", "upload", str(sdist)]
