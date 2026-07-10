from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import IO, Final

TERMINATION_GRACE_SECONDS: Final[float] = 1.0
STDOUT_READ_CHUNK_CHARS: Final[int] = 8 * 1024
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: Final[int] = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: Final[int] = 0x00002000


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int | None
    timed_out: bool
    failure: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out and self.failure is None


class _WindowsProcessJob:
    """Contains a launched Windows process tree until the supervisor releases it."""

    def __init__(self, handle: int) -> None:
        self._handle: int | None = handle

    @classmethod
    def create(cls) -> _WindowsProcessJob:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        return cls(int(handle))

    def assign(self, process: subprocess.Popen[str]) -> None:
        import ctypes
        from ctypes import wintypes

        handle = self._require_open_handle()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        if not kernel32.AssignProcessToJobObject(wintypes.HANDLE(handle), wintypes.HANDLE(int(process._handle))):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")

    def kill_on_close(self) -> None:
        import ctypes
        from ctypes import wintypes

        class _BasicLimitInformation(ctypes.Structure):
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

        class _IoCounters(ctypes.Structure):
            _fields_ = [
                ("read_operation_count", ctypes.c_ulonglong),
                ("write_operation_count", ctypes.c_ulonglong),
                ("other_operation_count", ctypes.c_ulonglong),
                ("read_transfer_count", ctypes.c_ulonglong),
                ("write_transfer_count", ctypes.c_ulonglong),
                ("other_transfer_count", ctypes.c_ulonglong),
            ]

        class _ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("basic_limit_information", _BasicLimitInformation),
                ("io_info", _IoCounters),
                ("process_memory_limit", ctypes.c_size_t),
                ("job_memory_limit", ctypes.c_size_t),
                ("peak_process_memory_used", ctypes.c_size_t),
                ("peak_job_memory_used", ctypes.c_size_t),
            ]

        handle = self._require_open_handle()
        limits = _ExtendedLimitInformation()
        limits.basic_limit_information.limit_flags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        )
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        if not kernel32.SetInformationJobObject(
            wintypes.HANDLE(handle),
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")

    def close(self) -> None:
        if self._handle is None:
            return

        import ctypes
        from ctypes import wintypes

        handle = self._handle
        self._handle = None
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        if not kernel32.CloseHandle(wintypes.HANDLE(handle)):
            raise OSError(ctypes.get_last_error(), "CloseHandle failed")

    def _require_open_handle(self) -> int:
        if self._handle is None:
            raise RuntimeError("Windows Job Object handle is closed")
        return self._handle


def _drain_stdout(stream: IO[str], on_output: Callable[[str], None], failures: list[str]) -> None:
    try:
        read = getattr(stream, "read", None)
        if not callable(read):
            for line in stream:
                on_output(line)
            return

        buffered = ""
        while chunk := read(STDOUT_READ_CHUNK_CHARS):
            buffered += chunk
            while "\n" in buffered:
                line, buffered = buffered.split("\n", 1)
                on_output(f"{line}\n")
            if len(buffered) >= STDOUT_READ_CHUNK_CHARS:
                on_output(buffered)
                buffered = ""
        if buffered:
            on_output(buffered)
    except (OSError, ValueError) as exc:
        failures.append(f"stdout drain failed: {exc}")


def _posix_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_posix_tree(process: subprocess.Popen[str]) -> str | None:
    process_group_id = process.pid
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        if process.poll() is None:
            return "process group disappeared before the child was reaped"
    except OSError as exc:
        return f"SIGTERM process-group termination failed: {exc}"

    grace_deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
    while _posix_group_exists(process_group_id) and time.monotonic() < grace_deadline:
        time.sleep(0.01)
    if _posix_group_exists(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as exc:
            return f"SIGKILL process-group termination failed: {exc}"
    try:
        process.wait(timeout=TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        return "timed out while reaping the terminated process group"
    return None


def _terminate_windows_tree(
    process: subprocess.Popen[str],
    process_job: _WindowsProcessJob | None = None,
) -> str | None:
    if process_job is not None:
        try:
            process_job.kill_on_close()
            process_job.close()
            process.wait(timeout=TERMINATION_GRACE_SECONDS)
            return None
        except (OSError, subprocess.TimeoutExpired) as exc:
            close_failure: str | None = None
            try:
                process_job.close()
            except OSError as close_exc:
                close_failure = str(close_exc)
            fallback_failure = _terminate_windows_tree(process)
            fallback_detail = f"; fallback failed: {fallback_failure}" if fallback_failure else ""
            close_detail = f"; close failed: {close_failure}" if close_failure else ""
            return f"Windows Job Object termination failed: {exc}{close_detail}{fallback_detail}"

    taskkill_failure: str | None = None
    try:
        completed = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
            timeout=TERMINATION_GRACE_SECONDS,
        )
        if completed.returncode != 0:
            taskkill_failure = completed.stderr.strip() or f"taskkill returned {completed.returncode}"
    except (OSError, subprocess.SubprocessError) as exc:
        taskkill_failure = f"taskkill failed: {exc}"

    if process.poll() is None:
        try:
            process.kill()
        except OSError as exc:
            return f"{taskkill_failure or 'taskkill did not stop child'}; process.kill failed: {exc}"
    try:
        process.wait(timeout=TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        return f"{taskkill_failure or 'tree termination incomplete'}; child reap timed out"
    return taskkill_failure


def _terminate_process_tree(process: subprocess.Popen[str]) -> str | None:
    if os.name == "nt":
        return _terminate_windows_tree(process)
    return _terminate_posix_tree(process)


def supervise_process(
    command: Sequence[str],
    *,
    cwd: str,
    env: Mapping[str, str],
    timeout_seconds: float,
    on_output: Callable[[str], None],
    popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
) -> ProcessResult:
    platform_options: dict[str, bool | int]
    if os.name == "nt":
        platform_options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        platform_options = {"start_new_session": True}

    process_job = _WindowsProcessJob.create() if os.name == "nt" else None
    process: subprocess.Popen[str] | None = None
    try:
        process = popen_factory(
            list(command),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=dict(env),
            **platform_options,
        )
        if process_job is not None:
            if hasattr(process, "_handle"):
                process_job.assign(process)
            else:
                process_job.close()
                process_job = None
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        if process is not None:
            termination_failure = _terminate_process_tree(process)
            try:
                process.wait(timeout=TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                termination_failure = termination_failure or "child reap timed out after containment setup failed"
        if process_job is not None:
            try:
                process_job.close()
            except OSError as close_exc:
                termination_failure = termination_failure or f"Windows Job Object close failed: {close_exc}"
        if process is None:
            raise
        detail = f"; cleanup failed: {termination_failure}" if termination_failure else ""
        return ProcessResult(
            returncode=process.returncode,
            timed_out=False,
            failure=f"process containment setup failed: {exc}{detail}",
        )

    if process.stdout is None:
        process.kill()
        process.wait(timeout=TERMINATION_GRACE_SECONDS)
        if process_job is not None:
            process_job.close()
        return ProcessResult(returncode=process.returncode, timed_out=False, failure="stdout pipe was not created")

    drain_failures: list[str] = []
    drain_thread = threading.Thread(
        target=_drain_stdout,
        args=(process.stdout, on_output, drain_failures),
        name=f"figops-stdout-{getattr(process, 'pid', 'child')}",
        daemon=True,
    )
    drain_thread.start()
    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    termination_failure: str | None = None
    try:
        process.wait(timeout=max(0.0, deadline - time.monotonic()))
        drain_thread.join(max(0.0, deadline - time.monotonic()))
        if drain_thread.is_alive():
            timed_out = True
            termination_failure = (
                _terminate_windows_tree(process, process_job)
                if process_job is not None
                else _terminate_process_tree(process)
            )
    except subprocess.TimeoutExpired:
        timed_out = True
        termination_failure = (
            _terminate_windows_tree(process, process_job)
            if process_job is not None
            else _terminate_process_tree(process)
        )

    drain_thread.join(TERMINATION_GRACE_SECONDS)
    if drain_thread.is_alive():
        try:
            process.stdout.close()
        except OSError as exc:
            termination_failure = termination_failure or f"stdout close failed: {exc}"
        drain_thread.join(TERMINATION_GRACE_SECONDS)
    if drain_thread.is_alive():
        termination_failure = termination_failure or "stdout drain thread did not terminate"
    if drain_failures and not timed_out:
        termination_failure = termination_failure or "; ".join(drain_failures)

    if process_job is not None:
        try:
            process_job.close()
        except OSError as exc:
            termination_failure = termination_failure or f"Windows Job Object close failed: {exc}"

    return ProcessResult(
        returncode=process.returncode,
        timed_out=timed_out,
        failure=termination_failure,
    )
