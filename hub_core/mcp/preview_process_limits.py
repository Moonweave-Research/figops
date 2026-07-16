"""Platform-specific process containment for MCP preview workers."""

from __future__ import annotations

import subprocess
from typing import Final

PREVIEW_WORKER_MEMORY_BYTES: Final = 256 * 1024 * 1024


class WindowsJobLimiter:
    """Contain a suspended preview worker in a memory-capped Windows job."""

    memory_enforced = True

    def __init__(self, handle: int) -> None:
        self.handle = handle

    @classmethod
    def create(cls) -> WindowsJobLimiter:
        import ctypes
        from ctypes import wintypes

        class Basic(ctypes.Structure):
            _fields_ = [
                ("per_process_user_time_limit", ctypes.c_longlong),
                ("per_job_user_time_limit", ctypes.c_longlong),
                ("limit_flags", wintypes.DWORD),
                ("minimum_working_set_size", ctypes.c_size_t),
                ("maximum_working_set_size", ctypes.c_size_t),
                ("active_process_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority_class", wintypes.DWORD),
                ("scheduling_class", wintypes.DWORD),
            ]

        class Io(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_ulonglong)
                for name in (
                    "read_operation_count",
                    "write_operation_count",
                    "other_operation_count",
                    "read_transfer_count",
                    "write_transfer_count",
                    "other_transfer_count",
                )
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", Io),
                ("process_memory_limit", ctypes.c_size_t),
                ("job_memory_limit", ctypes.c_size_t),
                ("peak_process_memory_used", ctypes.c_size_t),
                ("peak_job_memory_used", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
        limits = Extended()
        limits.basic.limit_flags = 0x2000 | 0x100 | 0x200
        limits.process_memory_limit = PREVIEW_WORKER_MEMORY_BYTES
        limits.job_memory_limit = PREVIEW_WORKER_MEMORY_BYTES
        kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        )
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        ok = kernel32.SetInformationJobObject(
            wintypes.HANDLE(handle),
            9,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        )
        if not ok:
            kernel32.CloseHandle(wintypes.HANDLE(handle))
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
        return cls(int(handle))

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        if not kernel32.AssignProcessToJobObject(
            wintypes.HANDLE(self.handle),
            wintypes.HANDLE(int(process._handle)),
        ):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")

    @staticmethod
    def resume(process: subprocess.Popen[bytes]) -> None:
        import ctypes
        from ctypes import wintypes

        class ThreadEntry(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD),
                ("tpBasePri", ctypes.c_long),
                ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Thread32First.argtypes = (wintypes.HANDLE, ctypes.POINTER(ThreadEntry))
        kernel32.Thread32First.restype = wintypes.BOOL
        kernel32.Thread32Next.argtypes = (wintypes.HANDLE, ctypes.POINTER(ThreadEntry))
        kernel32.Thread32Next.restype = wintypes.BOOL
        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000004, 0)
        if snapshot == wintypes.HANDLE(-1).value:
            raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot")
        try:
            entry = ThreadEntry()
            entry.dwSize = ctypes.sizeof(entry)
            found = bool(kernel32.Thread32First(snapshot, ctypes.byref(entry)))
            while found and entry.th32OwnerProcessID != process.pid:
                found = bool(kernel32.Thread32Next(snapshot, ctypes.byref(entry)))
            if not found:
                raise OSError("Suspended worker thread was not found")
            kernel32.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel32.OpenThread.restype = wintypes.HANDLE
            thread = kernel32.OpenThread(0x0002, False, entry.th32ThreadID)
            if not thread:
                raise OSError(ctypes.get_last_error(), "OpenThread")
            try:
                kernel32.ResumeThread.argtypes = (wintypes.HANDLE,)
                kernel32.ResumeThread.restype = wintypes.DWORD
                if kernel32.ResumeThread(thread) == 0xFFFFFFFF:
                    raise OSError(ctypes.get_last_error(), "ResumeThread")
            finally:
                kernel32.CloseHandle(thread)
        finally:
            kernel32.CloseHandle(snapshot)

    def terminate(self, process: subprocess.Popen[bytes]) -> None:
        import ctypes
        from ctypes import wintypes

        ctypes.WinDLL("kernel32", use_last_error=True).TerminateJobObject(
            wintypes.HANDLE(self.handle),
            1,
        )
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass

    def close(self) -> None:
        if self.handle:
            import ctypes
            from ctypes import wintypes

            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(
                wintypes.HANDLE(self.handle)
            )
            self.handle = 0
