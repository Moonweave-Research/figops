from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub_core.human_review_receipt import canonical_human_review_receipt_bytes
from hub_core.review_recording import (
    ReviewRecordExistsError,
    ReviewRecordingAuthorizationError,
    ReviewRecordingError,
    record_human_review_receipt,
)
from tests.human_review_receipt_helpers import receipt


def _record(tmp_path: Path, *, value: object, relative_path: str = "human/review.json", **kwargs: object):
    return record_human_review_receipt(
        value,
        evidence_root=tmp_path / "evidence",
        relative_path=relative_path,
        write_authorized=True,
        **kwargs,
    )


def test_records_exact_canonical_bytes_and_returns_runtime_independent_result(tmp_path: Path) -> None:
    review = receipt()
    result = _record(tmp_path, value=review)
    destination = tmp_path / "evidence" / result.relative_path

    assert destination.read_bytes() == canonical_human_review_receipt_bytes(review)
    assert result.record_relative_path == "human/review.json"
    assert result.receipt_id == review["receipt_id"]
    assert result.canonical_sha256 == review["integrity"]["canonical_sha256"]
    assert result.size_bytes == destination.stat().st_size
    assert str(tmp_path) not in repr(result)


def test_accepts_only_exact_canonical_receipt_bytes(tmp_path: Path) -> None:
    review = receipt()
    canonical = canonical_human_review_receipt_bytes(review)
    result = _record(tmp_path, value=canonical, relative_path="bytes.json")
    assert (tmp_path / "evidence" / result.relative_path).read_bytes() == canonical

    with pytest.raises(ReviewRecordingError, match="canonical"):
        _record(tmp_path / "noncanonical", value=b" " + canonical, relative_path="bytes.json")


def test_write_authorized_false_fails_before_validation_or_filesystem_touch(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    with pytest.raises(ReviewRecordingAuthorizationError, match="disabled"):
        record_human_review_receipt(
            object(),  # type: ignore[arg-type]
            evidence_root=root,
            relative_path="review.json",
            write_authorized=False,
        )
    assert not root.exists()


@pytest.mark.parametrize(
    "relative_path",
    ["/outside.json", "../outside.json", "nested/../../outside.json", r"nested\\review.json", "C:/outside.json"],
)
def test_absolute_and_traversal_destinations_are_rejected(tmp_path: Path, relative_path: str) -> None:
    with pytest.raises(ReviewRecordingError, match="canonical|relative"):
        _record(tmp_path, value=receipt(), relative_path=relative_path)
    assert not (tmp_path / "outside.json").exists()


def test_symlinked_evidence_root_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "evidence"
    try:
        root.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create directory symlinks")

    with pytest.raises(ReviewRecordingError, match="symlink|reparse"):
        _record(tmp_path, value=receipt())
    assert not (outside / "human" / "review.json").exists()


def test_symlinked_destination_parent_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create directory symlinks")

    with pytest.raises(ReviewRecordingError, match="symlink|reparse|unsafe"):
        _record(tmp_path, value=receipt(), relative_path="link/review.json")
    assert not (outside / "review.json").exists()


def test_existing_destination_is_never_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    destination = root / "review.json"
    destination.write_bytes(b"winner")

    with pytest.raises(ReviewRecordExistsError):
        _record(tmp_path, value=receipt(), relative_path="review.json")
    assert destination.read_bytes() == b"winner"


def test_no_clobber_race_preserves_competitor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hub_core.review_recording as recording

    def competing_move(source: Path, destination: Path) -> None:
        destination.write_bytes(b"competitor")
        raise FileExistsError(str(destination))

    monkeypatch.setattr(recording, "atomic_no_clobber_move", competing_move)
    with pytest.raises(ReviewRecordExistsError):
        _record(tmp_path, value=receipt(), relative_path="race.json")

    destination = tmp_path / "evidence" / "race.json"
    assert destination.read_bytes() == b"competitor"
    assert not list((tmp_path / "evidence").rglob("*.tmp"))


def test_malformed_receipt_never_creates_evidence_root(tmp_path: Path) -> None:
    malformed = receipt()
    malformed["integrity"] = {"canonical_sha256": "0" * 64}
    with pytest.raises(ReviewRecordingError, match="malformed"):
        _record(tmp_path, value=malformed)
    assert not (tmp_path / "evidence").exists()


def test_record_bytes_remain_after_runtime_tree_deletion(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    runtime_file = runtime / "manifest.json"
    runtime_file.write_text("runtime", encoding="utf-8")
    result = _record(tmp_path, value=receipt(), relative_path="review.json")
    runtime_file.unlink()
    runtime.rmdir()
    payload = json.loads((tmp_path / "evidence" / result.relative_path).read_bytes())
    assert payload["receipt_id"] == result.receipt_id
