from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

import hub_core.allowed_data as allowed_data
from hub_core.allowed_data import (
    ABSOLUTE_INSPECT_MAX_BYTES,
    DEFAULT_INSPECT_MAX_BYTES,
    AllowedDataError,
    open_verified_allowed_data,
    resolve_inspect_max_bytes,
    select_allowed_data_path,
)
from tests._symlink import symlink_or_skip


def test_relative_path_requires_explicit_allowed_base(tmp_path: Path) -> None:
    (tmp_path / "input.csv").write_text("x\n1\n", encoding="utf-8")
    with pytest.raises(AllowedDataError) as captured:
        select_allowed_data_path("input.csv", allowed_roots=[tmp_path])
    assert captured.value.code == "RELATIVE_DATA_PATH_WITHOUT_BASE"
    selected = select_allowed_data_path("input.csv", allowed_roots=[tmp_path], relative_base=tmp_path)
    assert selected.candidate == (tmp_path / "input.csv").resolve()


@pytest.mark.parametrize("declaration", ["../input.csv", "nested/../../input.csv", "nested\\..\\input.csv"])
def test_relative_traversal_is_rejected(tmp_path: Path, declaration: str) -> None:
    with pytest.raises(AllowedDataError) as captured:
        select_allowed_data_path(declaration, allowed_roots=[tmp_path], relative_base=tmp_path)
    assert captured.value.code == "DATA_PATH_TRAVERSAL"


def test_ntfs_stream_designator_is_rejected_portably(tmp_path: Path) -> None:
    with pytest.raises(AllowedDataError) as captured:
        select_allowed_data_path("input.csv:secret", allowed_roots=[tmp_path], relative_base=tmp_path)
    assert captured.value.code == "DATA_PATH_STREAM"


def test_absolute_escape_is_redacted(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "operator-secret" / "secret.csv"
    allowed.mkdir()
    outside.parent.mkdir()
    outside.write_text("OUTSIDE_SECRET", encoding="utf-8")
    with pytest.raises(AllowedDataError) as captured:
        select_allowed_data_path(outside, allowed_roots=[allowed])
    assert captured.value.code == "DATA_PATH_OUTSIDE_ALLOWED_ROOT"
    assert str(outside) not in str(captured.value)
    assert "operator-secret" not in str(captured.value)


def test_directory_is_not_a_regular_input(tmp_path: Path) -> None:
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(AllowedDataError) as captured:
        select_allowed_data_path(directory, allowed_roots=[tmp_path])
    assert captured.value.code == "DATA_PATH_NOT_REGULAR"


def test_internal_symlink_or_reparse_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.csv"
    target.write_text("x\n1\n", encoding="utf-8")
    link = tmp_path / "linked.csv"
    symlink_or_skip(link, target)
    with pytest.raises(AllowedDataError) as captured:
        select_allowed_data_path(link, allowed_roots=[tmp_path])
    assert captured.value.code == "DATA_PATH_REPARSE_POINT"


@pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-specific")
def test_windows_junction_component_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "input.csv").write_text("x\n1\n", encoding="utf-8")
    junction = tmp_path / "junction"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("Windows junction creation is unavailable")
    try:
        with pytest.raises(AllowedDataError) as captured:
            select_allowed_data_path(junction / "input.csv", allowed_roots=[tmp_path])
        assert captured.value.code == "DATA_PATH_REPARSE_POINT"
    finally:
        os.rmdir(junction)


def test_verified_descriptor_reports_prefetch_count_and_never_reopens_for_consumer(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_bytes(b"x\n1\n")
    with open_verified_allowed_data(
        source,
        allowed_roots=[tmp_path],
        relative_base=None,
        prefetch_mode="noop",
        max_bytes=1024,
        deadline=time.monotonic() + 10,
    ) as verified:
        assert verified.handle.read() == b"x\n1\n"
        assert verified.prefetch_calls == 1
        assert verified.byte_size == 4
        assert verified.display_name == "input.csv"


def test_prefetch_symlink_swap_fails_before_external_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "input.csv"
    source.write_bytes(b"SAFE_CONTENT")
    outside = tmp_path / "outside.csv"
    outside.write_bytes(b"OUTSIDE_SECRET")

    class SwappingPrefetcher:
        def ensure_local(self, _paths: list[str]) -> None:
            source.unlink()
            symlink_or_skip(source, outside)

    monkeypatch.setattr(allowed_data, "_prefetch_from_mode", lambda _mode: SwappingPrefetcher())
    with pytest.raises(AllowedDataError) as captured:
        with open_verified_allowed_data(
            source,
            allowed_roots=[allowed],
            relative_base=None,
            prefetch_mode="noop",
            max_bytes=1024,
            deadline=time.monotonic() + 10,
        ):
            pytest.fail("unsafe descriptor was yielded")
    assert captured.value.code == "DATA_PATH_CHANGED"


def test_post_open_toctou_swap_fails_before_descriptor_is_yielded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "input.csv"
    source.write_bytes(b"SAFE_CONTENT")
    outside = tmp_path / "outside.csv"
    outside.write_bytes(b"OUTSIDE_SECRET")
    original = allowed_data._revalidate
    calls = 0

    def swap_on_second(selection, expected):
        nonlocal calls
        calls += 1
        if calls == 2:
            try:
                source.unlink()
            except PermissionError as exc:
                raise AllowedDataError("DATA_PATH_CHANGED", "Data path swap was denied safely.") from exc
            symlink_or_skip(source, outside)
        return original(selection, expected)

    monkeypatch.setattr(allowed_data, "_revalidate", swap_on_second)
    with pytest.raises(AllowedDataError) as captured:
        with open_verified_allowed_data(
            source,
            allowed_roots=[tmp_path],
            relative_base=None,
            prefetch_mode="none",
            max_bytes=1024,
            deadline=time.monotonic() + 10,
        ):
            pytest.fail("descriptor must not be yielded after a path swap")
    assert captured.value.code == "DATA_PATH_CHANGED"


def test_source_byte_limit_is_checked_before_consumer_read(tmp_path: Path) -> None:
    source = tmp_path / "large.csv"
    source.write_bytes(b"x\n" + b"1\n" * 100)
    with pytest.raises(AllowedDataError) as captured:
        with open_verified_allowed_data(
            source,
            allowed_roots=[tmp_path],
            relative_base=None,
            prefetch_mode="none",
            max_bytes=16,
            deadline=time.monotonic() + 10,
        ):
            pass
    assert captured.value.code == "DATA_SOURCE_BYTE_LIMIT"


@pytest.mark.parametrize("value", ["bad", "0", "-1", str(ABSOLUTE_INSPECT_MAX_BYTES + 1)])
def test_invalid_inspect_limit_defaults_with_warning(value: str) -> None:
    warnings: list[str] = []
    assert resolve_inspect_max_bytes(value, warnings=warnings) == DEFAULT_INSPECT_MAX_BYTES
    assert warnings and "64 MiB default" in warnings[0]


def test_valid_inspect_limit_and_stream_chunk_ceiling() -> None:
    assert resolve_inspect_max_bytes(1024) == 1024
    assert resolve_inspect_max_bytes(ABSOLUTE_INSPECT_MAX_BYTES) == ABSOLUTE_INSPECT_MAX_BYTES
    assert allowed_data.SNAPSHOT_CHUNK_BYTES <= 1024 * 1024
