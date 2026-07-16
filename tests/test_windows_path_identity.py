from __future__ import annotations

import ctypes
import os
from pathlib import Path

import pytest

import hub_core.path_identity as path_identity
from hub_core.path_identity import final_regular_file_path, normalize_windows_final_path


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (r"\\?\C:\Research\data.csv", r"C:\Research\data.csv"),
        (r"\\?\UNC\server\share\data.csv", r"\\server\share\data.csv"),
        (r"C:\Research\data.csv", r"C:\Research\data.csv"),
    ],
)
def test_normalize_windows_final_path_removes_only_win32_namespace_prefix(
    raw: str,
    expected: str,
) -> None:
    assert normalize_windows_final_path(raw) == expected


def test_final_regular_file_path_uses_import_time_native_platform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "data.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    monkeypatch.setattr(os, "name", "posix" if path_identity._NATIVE_OS_NAME == "nt" else "nt")

    if path_identity._NATIVE_OS_NAME == "nt":
        sentinel = source.resolve()
        monkeypatch.setattr(path_identity, "_windows_final_regular_file_path", lambda _path: sentinel)
        assert final_regular_file_path(source) == sentinel
    else:
        def unexpected_windows_call(_path: object) -> Path:
            raise AssertionError("mocked os.name must not activate Windows path handling")

        monkeypatch.setattr(path_identity, "_windows_final_regular_file_path", unexpected_windows_call)
        assert final_regular_file_path(source) == source.resolve()


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows handle APIs")
def test_windows_final_path_closes_full_width_handle_when_descriptor_adoption_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import msvcrt

    native_handle = 0x12345678ABCDEF
    closed_handles: list[int] = []

    def create_file(*_args: object) -> int:
        return native_handle

    def get_final_path(*_args: object) -> int:
        raise AssertionError("final-path lookup must not run after descriptor adoption fails")

    def close_handle(handle: int) -> int:
        closed_handles.append(handle)
        return 1

    class FakeKernel32:
        CreateFileW = staticmethod(create_file)
        GetFinalPathNameByHandleW = staticmethod(get_final_path)
        CloseHandle = staticmethod(close_handle)

    fake_kernel32 = FakeKernel32()
    monkeypatch.setattr(ctypes, "WinDLL", lambda *_args, **_kwargs: fake_kernel32)

    def fail_descriptor_adoption(_handle: int, _flags: int) -> int:
        raise OSError("forced open_osfhandle failure")

    monkeypatch.setattr(msvcrt, "open_osfhandle", fail_descriptor_adoption)

    with pytest.raises(OSError, match="forced open_osfhandle failure"):
        path_identity._windows_final_regular_file_path(tmp_path / "data.csv")

    assert fake_kernel32.CloseHandle.argtypes == [ctypes.c_void_p]
    assert fake_kernel32.CloseHandle.restype is ctypes.c_int
    assert closed_handles == [native_handle]
