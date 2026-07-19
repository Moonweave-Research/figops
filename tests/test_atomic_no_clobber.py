from __future__ import annotations

from pathlib import Path

import pytest

from hub_core.atomic_no_clobber import (
    ATOMIC_NO_CLOBBER_UNAVAILABLE,
    AtomicNoClobberUnavailable,
    atomic_no_clobber_move,
)


def test_atomic_move_consumes_source_name(tmp_path: Path) -> None:
    source = tmp_path / ".private-stage"
    destination = tmp_path / "result.csv"
    source.write_bytes(b"complete")

    atomic_no_clobber_move(source, destination)

    assert not source.exists()
    assert destination.read_bytes() == b"complete"


def test_atomic_move_preserves_race_winner(tmp_path: Path) -> None:
    source = tmp_path / ".private-stage"
    destination = tmp_path / "result.csv"
    source.write_bytes(b"ours")
    destination.write_bytes(b"theirs")

    with pytest.raises(FileExistsError):
        atomic_no_clobber_move(source, destination)

    assert source.read_bytes() == b"ours"
    assert destination.read_bytes() == b"theirs"


def test_unsupported_native_primitive_fails_before_publication(tmp_path: Path, monkeypatch) -> None:
    import hub_core.atomic_no_clobber as atomic

    source = tmp_path / ".private-stage"
    destination = tmp_path / "result.csv"
    source.write_bytes(b"ours")
    def unavailable(*_args):
        raise AtomicNoClobberUnavailable(f"{ATOMIC_NO_CLOBBER_UNAVAILABLE}: unavailable")

    if atomic.os.name == "nt":
        monkeypatch.setattr(atomic, "_windows_move", unavailable)
    elif atomic.sys.platform.startswith("linux"):
        monkeypatch.setattr(atomic, "_linux_move", unavailable)
    elif atomic.sys.platform == "darwin":
        monkeypatch.setattr(atomic, "_macos_move", unavailable)
    else:
        pytest.skip("host is already unsupported")

    with pytest.raises(AtomicNoClobberUnavailable, match=ATOMIC_NO_CLOBBER_UNAVAILABLE):
        atomic_no_clobber_move(source, destination)

    assert source.read_bytes() == b"ours"
    assert not destination.exists()
