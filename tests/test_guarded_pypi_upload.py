import json
import sys
from pathlib import Path

from scripts import guarded_pypi_upload


def _write_upload_policy(root: Path, *, allowed: bool = True, license_decision_required: bool = False) -> None:
    policy_dir = root / "docs" / "packaging"
    policy_dir.mkdir(parents=True)
    (policy_dir / "public-core-inventory.json").write_text(
        json.dumps(
            {
                "distribution_policy": {
                    "current_status": "public_package_approved" if allowed else "private_internal",
                    "public_pypi_allowed": allowed,
                    "license_decision_required": license_decision_required,
                }
            }
        ),
        encoding="utf-8",
    )


def test_guarded_upload_blocks_private_license(tmp_path: Path, monkeypatch) -> None:
    _write_upload_policy(tmp_path)
    (tmp_path / "LICENSE").write_text("All rights reserved.\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("No open source license has been granted.\n", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "figops-0.16.4-py3-none-any.whl").write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(
        guarded_pypi_upload,
        "inspect_public_package_surface",
        lambda _root, _dist_glob: {"ok": True, "blockers": []},
    )

    blockers = guarded_pypi_upload.upload_blockers(tmp_path)

    assert any("all-rights-reserved" in blocker for blocker in blockers)
    assert any("no open source license" in blocker for blocker in blockers)


def test_guarded_upload_requires_distribution_files(tmp_path: Path) -> None:
    _write_upload_policy(tmp_path)
    (tmp_path / "LICENSE").write_text("Apache License\nVersion 2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Open source release candidate.\n", encoding="utf-8")

    blockers = guarded_pypi_upload.upload_blockers(tmp_path)

    assert blockers == ("No distribution files found for glob: dist/*",)


def test_guarded_upload_blocks_when_distribution_policy_has_not_approved_pypi(tmp_path: Path, monkeypatch) -> None:
    _write_upload_policy(tmp_path, allowed=False, license_decision_required=True)
    (tmp_path / "LICENSE").write_text("Apache License\nVersion 2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Open source release candidate.\n", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "figops-0.16.4-py3-none-any.whl").write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(
        guarded_pypi_upload,
        "inspect_public_package_surface",
        lambda _root, _dist_glob: {"ok": True, "blockers": []},
    )

    blockers = guarded_pypi_upload.upload_blockers(tmp_path)

    assert any("has not approved" in blocker for blocker in blockers)
    assert any("license decision" in blocker for blocker in blockers)


def test_guarded_upload_blocks_package_surface_findings(tmp_path: Path, monkeypatch) -> None:
    _write_upload_policy(tmp_path)
    (tmp_path / "LICENSE").write_text("Apache License\nVersion 2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Open source release candidate.\n", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "figops-0.16.4-py3-none-any.whl"
    wheel.write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(
        guarded_pypi_upload,
        "inspect_public_package_surface",
        lambda _root, _dist_glob: {"ok": False, "blockers": ["private marker found"]},
    )

    blockers = guarded_pypi_upload.upload_blockers(tmp_path)

    assert "private marker found" in blockers


def test_guarded_upload_command_defaults_to_testpypi_repository(tmp_path: Path) -> None:
    wheel = tmp_path / "dist" / "figops-0.16.4-py3-none-any.whl"
    wheel.parent.mkdir()
    wheel.write_text("placeholder", encoding="utf-8")

    command = guarded_pypi_upload.build_upload_command("testpypi", [wheel])

    assert command == [sys.executable, "-m", "twine", "upload", "--repository", "testpypi", str(wheel)]


def test_guarded_upload_command_uses_default_pypi_target_without_repository_alias(tmp_path: Path) -> None:
    sdist = tmp_path / "dist" / "figops-0.16.4.tar.gz"
    sdist.parent.mkdir()
    sdist.write_text("placeholder", encoding="utf-8")

    command = guarded_pypi_upload.build_upload_command("pypi", [sdist])

    assert command == [sys.executable, "-m", "twine", "upload", str(sdist)]
