"""Bounded, fact-only inspection of an already-verified data snapshot."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Protocol, Sequence

from hub_core.allowed_data import (
    ABSOLUTE_INSPECT_MAX_BYTES,
    DEFAULT_INSPECT_MAX_BYTES,
    INSPECT_WORK_CUTOFF_SECONDS,
)

MAX_SCAN_ROWS = 1_000_000
MAX_RETURNED_COLUMNS = 256
MAX_SAMPLE_ROWS = 20
MAX_CELL_CHARS = 512
MAX_INSPECTION_RESPONSE_BYTES = 32 * 1024
INSPECTION_WORKER_MEMORY_BYTES = 256 * 1024 * 1024
DEFAULT_INSPECT_SOURCE_BYTES = DEFAULT_INSPECT_MAX_BYTES
ABSOLUTE_INSPECT_SOURCE_BYTES = ABSOLUTE_INSPECT_MAX_BYTES
INSPECTION_WORK_CUTOFF_SECONDS = INSPECT_WORK_CUTOFF_SECONDS

_CONTAINER_SUFFIXES = {
    ".7z",
    ".bz2",
    ".feather",
    ".gz",
    ".h5",
    ".hdf5",
    ".parquet",
    ".rar",
    ".tar",
    ".xls",
    ".xlsx",
    ".xz",
    ".zip",
}


class InspectionSnapshot(Protocol):
    snapshot_path: Path
    display_name: str
    suffix: str
    byte_size: int
    sha256: str
    deadline: float


class _WorkerLimitUnavailable(RuntimeError):
    pass


def _unavailable(reason: str, *, source: dict[str, Any], memory_enforced: bool | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "figops.inspect-data.v1",
        "status": "unavailable",
        "availability": {"state": "unavailable", "reason": reason},
        "source": source,
        "scan": None,
        "columns": [],
        "samples": [],
        "truncation": {},
        "warnings": [],
        "limits": _limits(memory_enforced),
    }
    return result


def _limits(memory_enforced: bool | None) -> dict[str, Any]:
    limitation = None
    if memory_enforced is False:
        limitation = "Hard worker memory enforcement was unavailable on this host; fixed parser bounds still apply."
    return {
        "scan_rows": MAX_SCAN_ROWS,
        "returned_columns": MAX_RETURNED_COLUMNS,
        "sample_rows": MAX_SAMPLE_ROWS,
        "cell_chars": MAX_CELL_CHARS,
        "response_bytes": MAX_INSPECTION_RESPONSE_BYTES,
        "worker_memory_bytes": INSPECTION_WORKER_MEMORY_BYTES,
        "worker_memory_enforced": memory_enforced,
        "worker_memory_limitation": limitation,
    }


def _source(snapshot: InspectionSnapshot, data_format: str | None) -> dict[str, Any]:
    return {
        "name": str(snapshot.display_name)[:MAX_CELL_CHARS],
        "format": data_format,
        "byte_size": int(snapshot.byte_size),
        "sha256": str(snapshot.sha256),
    }


def _detect_format(snapshot: InspectionSnapshot) -> tuple[str | None, str | None]:
    suffix = str(snapshot.suffix).lower()
    if suffix in _CONTAINER_SUFFIXES:
        return None, "COMPRESSED_OR_CONTAINER_UNAVAILABLE"
    if suffix == ".csv":
        selected = "csv"
    elif suffix == ".tsv":
        selected = "tsv"
    else:
        return None, "FORMAT_UNSUPPORTED"
    try:
        with Path(snapshot.snapshot_path).open("rb") as handle:
            head = handle.read(8)
    except OSError:
        return None, "SNAPSHOT_READ_FAILED"
    compressed_or_container = (
        head.startswith(b"\x1f\x8b")
        or head.startswith(b"BZh")
        or head.startswith(b"\xfd7zXZ\x00")
        or head.startswith(b"PK\x03\x04")
        or head.startswith(b"7z\xbc\xaf\x27\x1c")
        or head.startswith(b"PAR1")
        or head.startswith(b"\x89HDF\r\n\x1a\n")
    )
    if compressed_or_container:
        return None, "COMPRESSED_OR_CONTAINER_UNAVAILABLE"
    return selected, None


class _Limiter:
    enforced = True

    def terminate(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=0.75)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("inspection worker could not be reaped") from exc
        if process.poll() is None:
            raise RuntimeError("inspection worker could not be reaped")

    def close(self) -> None:
        return None


class _PosixProcessGroupLimiter(_Limiter):
    def terminate(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                process.kill()
        try:
            process.wait(timeout=0.75)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("inspection process group could not be reaped") from exc
        if process.poll() is None:
            raise RuntimeError("inspection process group could not be reaped")


class _WindowsJobLimiter(_Limiter):
    def __init__(self, handle: int) -> None:
        self.handle = handle

    @classmethod
    def create(cls) -> _WindowsJobLimiter:
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
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
        limits = Extended()
        # KILL_ON_JOB_CLOSE | PROCESS_MEMORY | JOB_MEMORY.
        limits.basic.limit_flags = 0x2000 | 0x100 | 0x200
        limits.process_memory_limit = INSPECTION_WORKER_MEMORY_BYTES
        limits.job_memory_limit = INSPECTION_WORKER_MEMORY_BYTES
        if not kernel32.SetInformationJobObject(
            wintypes.HANDLE(handle), 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            kernel32.CloseHandle(wintypes.HANDLE(handle))
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
        return cls(int(handle))

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        if not kernel32.AssignProcessToJobObject(wintypes.HANDLE(self.handle), wintypes.HANDLE(int(process._handle))):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")

    def terminate(self, process: subprocess.Popen[bytes]) -> None:
        import ctypes
        from ctypes import wintypes

        ctypes.WinDLL("kernel32", use_last_error=True).TerminateJobObject(wintypes.HANDLE(self.handle), 1)
        try:
            process.wait(timeout=0.75)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("Windows inspection job could not be reaped") from exc
        if process.poll() is None:
            raise RuntimeError("Windows inspection job could not be reaped")

    def close(self) -> None:
        if self.handle:
            import ctypes
            from ctypes import wintypes

            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(wintypes.HANDLE(self.handle))
            self.handle = 0


def _process_options() -> dict[str, Any]:
    return {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "cwd": str(Path(__file__).resolve().parents[1]),
    }


def _start_worker(module: str = "hub_core.data_inspection_worker") -> tuple[subprocess.Popen[bytes], _Limiter | None]:
    command = [sys.executable, "-m", module]
    options = _process_options()
    if os.name == "nt":
        try:
            limiter = _WindowsJobLimiter.create()
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            process = subprocess.Popen(command, **options)
            limiter.assign(process)
            return process, limiter
        except (OSError, ValueError):
            if "process" in locals() and process.poll() is None:
                process.kill()
                process.wait()
            if "limiter" in locals():
                limiter.close()
            raise _WorkerLimitUnavailable("hard worker memory containment is unavailable") from None
    try:
        import resource

        def limit_memory() -> None:
            resource.setrlimit(
                resource.RLIMIT_AS,
                (INSPECTION_WORKER_MEMORY_BYTES, INSPECTION_WORKER_MEMORY_BYTES),
            )

        options["start_new_session"] = True
        options["preexec_fn"] = limit_memory
        limiter = _PosixProcessGroupLimiter()
    except (ImportError, AttributeError):
        raise _WorkerLimitUnavailable("hard worker memory containment is unavailable") from None
    return subprocess.Popen(command, **options), limiter


def _validate_columns(columns: Sequence[str] | None) -> list[str] | None:
    if columns is None:
        return None
    if isinstance(columns, (str, bytes)) or len(columns) > MAX_RETURNED_COLUMNS:
        raise ValueError(f"columns must be a sequence of at most {MAX_RETURNED_COLUMNS} names.")
    result = []
    for name in columns:
        if not isinstance(name, str) or not name or len(name) > MAX_CELL_CHARS:
            raise ValueError(f"column names must be non-empty strings of at most {MAX_CELL_CHARS} characters.")
        result.append(name)
    return result


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    def size() -> int:
        return len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    if size() <= MAX_INSPECTION_RESPONSE_BYTES:
        return result
    samples = result.get("samples")
    truncation = result.setdefault("truncation", {})
    if isinstance(samples, list) and samples:
        samples.clear()
        result["sample_columns"] = []
        truncation["samples_for_response_size"] = True
    columns = result.get("columns")
    if isinstance(columns, list):
        while columns and size() > MAX_INSPECTION_RESPONSE_BYTES:
            columns.pop()
        scan = result.get("scan")
        if isinstance(scan, dict):
            scan["columns_returned"] = len(columns)
        truncation["columns_for_response_size"] = True
    if size() > MAX_INSPECTION_RESPONSE_BYTES:
        return _unavailable("RESPONSE_BYTE_LIMIT", source=result.get("source", {}))
    return result


def inspect_data(
    snapshot: InspectionSnapshot,
    *,
    columns: Sequence[str] | None = None,
    include_samples: bool = False,
    sample_rows: int = 0,
) -> dict[str, Any]:
    """Inspect a private snapshot with fixed row/memory/time/response bounds.

    This compatibility service accepts an already-frozen private snapshot and
    no arbitrary parser options. MCP production callers use
    :func:`inspect_allowed_data` so boundary, freeze, hash, and parse share one
    contained worker and one hard deadline.
    """

    selected_columns = _validate_columns(columns)
    if not isinstance(include_samples, bool):
        raise ValueError("include_samples must be a boolean.")
    if not isinstance(sample_rows, int) or not 0 <= sample_rows <= MAX_SAMPLE_ROWS:
        raise ValueError(f"sample_rows must be an integer from 0 through {MAX_SAMPLE_ROWS}.")
    if not include_samples and sample_rows:
        raise ValueError("sample_rows requires include_samples=true.")

    data_format, unavailable_reason = _detect_format(snapshot)
    source = _source(snapshot, data_format)
    if unavailable_reason:
        return _unavailable(unavailable_reason, source=source)
    remaining = float(snapshot.deadline) - time.monotonic()
    if remaining <= 0:
        return _unavailable("INSPECTION_DEADLINE", source=source)

    request: dict[str, Any] = {
        "snapshot_path": str(Path(snapshot.snapshot_path)),
        "format": data_format,
        "columns": selected_columns,
        "include_samples": include_samples,
        "sample_rows": sample_rows,
    }
    try:
        process, limiter = _start_worker()
    except _WorkerLimitUnavailable:
        return _unavailable("WORKER_MEMORY_LIMIT_UNAVAILABLE", source=source, memory_enforced=False)
    memory_enforced = limiter is not None
    # Spawning is part of the single snapshot+inspection deadline. Recompute
    # the remaining budget only after the contained worker exists.
    remaining = float(snapshot.deadline) - time.monotonic()
    if remaining <= 0:
        limiter.terminate(process)
        limiter.close()
        return _unavailable("INSPECTION_DEADLINE", source=source, memory_enforced=memory_enforced)
    request["remaining_seconds"] = remaining
    encoded_request = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    remaining = float(snapshot.deadline) - time.monotonic()
    if remaining <= 0:
        limiter.terminate(process)
        limiter.close()
        return _unavailable("INSPECTION_DEADLINE", source=source, memory_enforced=memory_enforced)
    try:
        output, _ = process.communicate(input=encoded_request, timeout=max(0.01, remaining))
    except subprocess.TimeoutExpired:
        if limiter is not None:
            limiter.terminate(process)
        else:
            process.kill()
            process.wait()
        return _unavailable("INSPECTION_DEADLINE", source=source, memory_enforced=memory_enforced)
    finally:
        if limiter is not None:
            limiter.close()
    if process.returncode != 0 or len(output) > MAX_INSPECTION_RESPONSE_BYTES:
        return _unavailable("WORKER_FAILURE", source=source, memory_enforced=memory_enforced)
    try:
        worker = json.loads(output.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return _unavailable("WORKER_FAILURE", source=source, memory_enforced=memory_enforced)
    if not isinstance(worker, dict) or str(snapshot.snapshot_path) in json.dumps(worker, ensure_ascii=False):
        return _unavailable("WORKER_FAILURE", source=source, memory_enforced=memory_enforced)
    result = {
        "schema_version": "figops.inspect-data.v1",
        **worker,
        "source": source,
        "limits": _limits(memory_enforced),
    }
    return _compact_result(result)


def _request_source(data_path: Any) -> dict[str, Any]:
    try:
        name = Path(os.fspath(data_path)).name[:MAX_CELL_CHARS] or "<data-file>"
    except (TypeError, ValueError):
        name = "<data-file>"
    return {"name": name, "format": None, "byte_size": None, "sha256": None}


def _request_unavailable(reason: str, *, source: dict[str, Any], memory_enforced: bool | None) -> dict[str, Any]:
    return _unavailable(reason, source=source, memory_enforced=memory_enforced)


def inspect_allowed_data(
    data_path: str | os.PathLike[str],
    *,
    allowed_roots: Sequence[str | os.PathLike[str]],
    relative_base: str | os.PathLike[str] | None = None,
    prefetch_mode: str = "noop",
    max_bytes: int = DEFAULT_INSPECT_SOURCE_BYTES,
    columns: Sequence[str] | None = None,
    include_samples: bool = False,
    sample_rows: int = 0,
) -> dict[str, Any]:
    """Run boundary, freeze/hash, and parse in one hard-bounded worker."""

    source = _request_source(data_path)
    if prefetch_mode not in {"none", "noop", "gdrive"}:
        return _request_unavailable("PREFETCH_ADAPTER_UNSUPPORTED", source=source, memory_enforced=None)
    if not isinstance(max_bytes, int) or not 0 < max_bytes <= ABSOLUTE_INSPECT_SOURCE_BYTES:
        return _request_unavailable("INSPECTION_LIMIT_INVALID", source=source, memory_enforced=None)
    try:
        raw_path = os.fspath(data_path)
        root_values = [os.fspath(root) for root in allowed_roots]
        base_value = os.fspath(relative_base) if relative_base is not None else None
        selected_columns = _validate_columns(columns)
    except (TypeError, ValueError):
        return _request_unavailable("WORKER_REQUEST_INVALID", source=source, memory_enforced=None)
    if (
        not isinstance(raw_path, str)
        or any(not isinstance(root, str) for root in root_values)
        or (base_value is not None and not isinstance(base_value, str))
    ):
        return _request_unavailable("WORKER_REQUEST_INVALID", source=source, memory_enforced=None)
    if not root_values:
        return _request_unavailable("NO_ALLOWED_DATA_ROOTS", source=source, memory_enforced=None)
    if (
        not isinstance(include_samples, bool)
        or not isinstance(sample_rows, int)
        or not 0 <= sample_rows <= MAX_SAMPLE_ROWS
    ):
        return _request_unavailable("SAMPLE_ROW_LIMIT", source=source, memory_enforced=None)
    if not include_samples and sample_rows:
        return _request_unavailable("SAMPLES_NOT_ENABLED", source=source, memory_enforced=None)

    deadline = time.monotonic() + INSPECTION_WORK_CUTOFF_SECONDS
    request = {
        "operation": "inspect_allowed_data",
        "data_path": raw_path,
        "allowed_roots": root_values,
        "relative_base": base_value,
        "prefetch_mode": prefetch_mode,
        "max_bytes": max_bytes,
        "deadline": deadline,
        "columns": selected_columns,
        "include_samples": include_samples,
        "sample_rows": sample_rows,
    }
    try:
        process, limiter = _start_worker()
    except _WorkerLimitUnavailable:
        return _request_unavailable("WORKER_MEMORY_LIMIT_UNAVAILABLE", source=source, memory_enforced=False)
    except (OSError, ValueError):
        return _request_unavailable("WORKER_START_FAILED", source=source, memory_enforced=False)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        try:
            limiter.terminate(process)
            reason = "INSPECTION_DEADLINE"
        except RuntimeError:
            reason = "WORKER_TERMINATION_FAILED"
        finally:
            limiter.close()
        return _request_unavailable(reason, source=source, memory_enforced=True)
    encoded = json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        try:
            limiter.terminate(process)
            reason = "INSPECTION_DEADLINE"
        except RuntimeError:
            reason = "WORKER_TERMINATION_FAILED"
        finally:
            limiter.close()
        return _request_unavailable(reason, source=source, memory_enforced=True)
    try:
        output, _ = process.communicate(input=encoded, timeout=remaining)
    except subprocess.TimeoutExpired:
        try:
            limiter.terminate(process)
            reason = "INSPECTION_DEADLINE"
        except RuntimeError:
            reason = "WORKER_TERMINATION_FAILED"
        return _request_unavailable(reason, source=source, memory_enforced=True)
    except OSError:
        try:
            limiter.terminate(process)
            reason = "WORKER_FAILURE"
        except RuntimeError:
            reason = "WORKER_TERMINATION_FAILED"
        return _request_unavailable(reason, source=source, memory_enforced=True)
    finally:
        limiter.close()
    if process.returncode != 0 or len(output) > MAX_INSPECTION_RESPONSE_BYTES:
        return _request_unavailable("WORKER_FAILURE", source=source, memory_enforced=True)
    try:
        result = json.loads(output.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return _request_unavailable("WORKER_FAILURE", source=source, memory_enforced=True)
    if not isinstance(result, dict):
        return _request_unavailable("WORKER_FAILURE", source=source, memory_enforced=True)
    serialized = json.dumps(result, ensure_ascii=False)
    sensitive = [raw_path, *root_values]
    if any(value and Path(value).is_absolute() and value in serialized for value in sensitive):
        return _request_unavailable("WORKER_FAILURE", source=source, memory_enforced=True)
    result["limits"] = _limits(True)
    return _compact_result(result)


__all__ = [
    "INSPECTION_WORKER_MEMORY_BYTES",
    "ABSOLUTE_INSPECT_SOURCE_BYTES",
    "DEFAULT_INSPECT_SOURCE_BYTES",
    "INSPECTION_WORK_CUTOFF_SECONDS",
    "MAX_CELL_CHARS",
    "MAX_INSPECTION_RESPONSE_BYTES",
    "MAX_RETURNED_COLUMNS",
    "MAX_SAMPLE_ROWS",
    "MAX_SCAN_ROWS",
    "inspect_data",
    "inspect_allowed_data",
]
