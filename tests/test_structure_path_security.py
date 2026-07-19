from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from hub_core.structure_path_security import delete_file_by_identity


@pytest.mark.skipif(os.name == "nt", reason="POSIX fail-closed contract")
def test_posix_identity_delete_never_renames_or_unlinks_a_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = tmp_path / "result.csv"
    payload = b"transaction-owned"
    published.write_bytes(payload)
    metadata = published.stat(follow_symlinks=False)
    identity = (metadata.st_dev, metadata.st_ino)
    digest = hashlib.sha256(payload).hexdigest()

    def forbidden_move(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("post-publication POSIX cleanup must not rename by pathname")

    def forbidden_unlink(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("post-publication POSIX cleanup must not unlink by pathname")

    monkeypatch.setattr("hub_core.atomic_no_clobber.atomic_no_clobber_move", forbidden_move)
    monkeypatch.setattr(Path, "unlink", forbidden_unlink)

    assert delete_file_by_identity(published, identity, digest) is False
    assert published.read_bytes() == payload
    current = published.stat(follow_symlinks=False)
    assert (current.st_dev, current.st_ino) == identity


@pytest.mark.skipif(os.name == "nt", reason="POSIX fail-closed contract")
def test_posix_identity_delete_preserves_competitor_bytes(tmp_path: Path) -> None:
    published = tmp_path / "result.csv"
    published.write_bytes(b"transaction-owned")
    original = published.stat(follow_symlinks=False)
    expected = (original.st_dev, original.st_ino)
    published.unlink()
    competitor = b"competitor-owned"
    published.write_bytes(competitor)

    assert delete_file_by_identity(
        published,
        expected,
        hashlib.sha256(b"transaction-owned").hexdigest(),
    ) is False
    assert published.read_bytes() == competitor
