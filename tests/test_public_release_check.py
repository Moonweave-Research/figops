from pathlib import Path

from scripts.check_public_release import run_release_check


def test_public_release_check_blocks_all_rights_reserved_license(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("All rights reserved.\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("No open source license has been granted.\n", encoding="utf-8")

    result = run_release_check(tmp_path, check_style_registry=False)

    assert not result.ok
    assert any("all-rights-reserved" in blocker for blocker in result.blockers)
    assert any("no open source license" in blocker for blocker in result.blockers)


def test_public_release_check_blocks_private_markers(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    doc = tmp_path / "README.md"
    doc.write_text("Gold project: 02_Surfur_Polymer/저항 측정/PI_control\n", encoding="utf-8")

    result = run_release_check(tmp_path, check_style_registry=False)

    assert not result.ok
    assert any("02_Surfur_Polymer" in blocker for blocker in result.blockers)


def test_public_release_check_blocks_internal_style_packs(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Open source release candidate.\n", encoding="utf-8")

    result = run_release_check(tmp_path)

    assert not result.ok
    assert any("Internal/private style packs" in blocker for blocker in result.blockers)


def test_public_release_check_does_not_block_on_its_own_denylist_terms(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "check_public_release.py"
    test_file = tmp_path / "tests" / "test_public_release_check.py"
    script.parent.mkdir()
    test_file.parent.mkdir()
    script.write_text('PRIVATE_MARKERS = ("02_Surfur_Polymer", "nature_surfur")\n', encoding="utf-8")
    test_file.write_text('sample = "02_Surfur_Polymer"\n', encoding="utf-8")
    (tmp_path / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Open source release candidate.\n", encoding="utf-8")

    result = run_release_check(tmp_path, check_style_registry=False)

    assert result.ok
