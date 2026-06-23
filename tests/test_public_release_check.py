import subprocess
import unicodedata
from pathlib import Path

from PIL import Image

from hub_core.provenance import embed_provenance_fingerprint
from scripts import check_public_release
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


def test_public_release_check_blocks_internal_style_packs(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Open source release candidate.\n", encoding="utf-8")
    monkeypatch.setattr(check_public_release, "validate_style_pack_registry", lambda: [])
    monkeypatch.setattr(
        check_public_release,
        "private_or_internal_style_packs",
        lambda: [{"name": "internal_fixture"}],
    )

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


def test_public_release_check_ignores_gitignored_local_outputs(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Open source release candidate.\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("**/results/\n/*.log\n", encoding="utf-8")
    output = tmp_path / "results" / "scratch.txt"
    output.parent.mkdir()
    output.write_text("PI_control local scratch output\n", encoding="utf-8")
    (tmp_path / "local.log").write_text("PI_control local log\n", encoding="utf-8")
    nested_output = tmp_path / "nested" / "results" / "scratch.txt"
    nested_output.parent.mkdir(parents=True)
    nested_output.write_text("PI_control nested local scratch output\n", encoding="utf-8")

    result = run_release_check(tmp_path, check_style_registry=False)

    assert result.ok


def test_public_release_check_uses_git_exclude_standard_when_available(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Open source release candidate.\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("results/\n", encoding="utf-8")
    output = tmp_path / "results" / "scratch.txt"
    output.parent.mkdir()
    output.write_text("PI_control local scratch output\n", encoding="utf-8")

    result = run_release_check(tmp_path, check_style_registry=False)

    assert result.ok


def test_public_release_check_scans_svg_text_for_private_markers(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Open source release candidate.\n", encoding="utf-8")
    (tmp_path / "figure.svg").write_text("<svg><text>PI_control</text></svg>\n", encoding="utf-8")

    result = run_release_check(tmp_path, check_style_registry=False)

    assert not result.ok
    assert any("figure.svg" in blocker for blocker in result.blockers)


def test_public_release_check_normalizes_nfd_korean_markers(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Open source release candidate.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(unicodedata.normalize("NFD", "저항 측정"), encoding="utf-8")

    result = run_release_check(tmp_path, check_style_registry=False)

    assert not result.ok
    assert any("저항 측정" in blocker for blocker in result.blockers)


def test_public_release_check_blocks_undecodable_text_files(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Open source release candidate.\n", encoding="utf-8")
    (tmp_path / "README.md").write_bytes(b"public intro\n\xffPI_control\n")

    result = run_release_check(tmp_path, check_style_registry=False)

    assert not result.ok
    assert any("Unable to decode UTF-8 text file: README.md" in blocker for blocker in result.blockers)


def test_public_release_check_scans_png_provenance_fingerprint_for_private_markers(tmp_path: Path) -> None:
    (tmp_path / "LICENSE").write_text("Apache-2.0\n", encoding="utf-8")
    (tmp_path / "NOTICE").write_text("Open source release candidate.\n", encoding="utf-8")
    figure = tmp_path / "figure.png"
    Image.new("RGB", (1, 1), "white").save(figure)
    embedded = embed_provenance_fingerprint(
        str(figure),
        {
            "project": "PI_control",
            "config": "abc",
            "env": "def",
            "git": "ghi",
            "timestamp": "2026-06-19T00:00:00Z",
        },
    )
    assert embedded

    result = run_release_check(tmp_path, check_style_registry=False)

    assert not result.ok
    assert any("figure.png" in blocker and "PI_control" in blocker for blocker in result.blockers)
