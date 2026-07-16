from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import hub_core.data_inspection as inspection
import hub_core.data_inspection_worker as worker
from hub_core.data_inspection import (
    MAX_CELL_CHARS,
    MAX_INSPECTION_RESPONSE_BYTES,
    MAX_SAMPLE_ROWS,
    inspect_allowed_data,
    inspect_data,
)
from tests._symlink import symlink_or_skip


def _inspect(path: Path, **kwargs):
    return inspect_allowed_data(path, allowed_roots=[path.parent], prefetch_mode="noop", **kwargs)


def _legacy_snapshot(path: Path, *, deadline: float | None = None):
    return SimpleNamespace(
        snapshot_path=path,
        display_name=path.name,
        suffix=path.suffix,
        byte_size=path.stat().st_size,
        sha256="0" * 64,
        deadline=time.monotonic() + 10 if deadline is None else deadline,
    )


def test_lower_inspection_modules_do_not_import_mcp_layer() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in ("hub_core/data_inspection.py", "hub_core/data_inspection_worker.py"):
        source = (root / relative).read_text(encoding="utf-8")
        assert "hub_core.mcp" not in source


def test_csv_profile_returns_facts_hash_and_no_default_samples_or_recommendation(tmp_path: Path) -> None:
    source = tmp_path / "facts.csv"
    source.write_text("group,value,flag\nA,1,true\nB,2.5,false\nA,,true\n", encoding="utf-8")

    result = _inspect(source)

    assert result["status"] == "available"
    assert result["source"]["format"] == "csv"
    assert result["prefetch_calls"] == 1
    assert len(result["source"]["sha256"]) == 64
    assert result["scan"] == {
        "row_count": 3,
        "row_count_lower_bound": None,
        "rows_scanned": 3,
        "columns_detected": 3,
        "columns_returned": 3,
    }
    assert result["samples"] == []
    assert result["sample_columns"] == []
    assert result["limits"]["worker_memory_bytes"] == 256 * 1024 * 1024
    assert result["limits"]["worker_memory_enforced"] is True
    by_name = {column["name"]: column for column in result["columns"]}
    assert by_name["group"]["dtype"] == "string"
    assert by_name["group"]["unique_count"] == 2
    assert by_name["value"]["dtype"] == "number"
    assert by_name["value"]["null_count"] == 1
    assert by_name["value"]["finite_range"] == {"min": 1, "max": 2.5}
    assert by_name["flag"]["dtype"] == "boolean"
    assert "recommend" not in json.dumps(result).lower()


def test_tsv_column_filter_and_explicit_samples_are_bounded(tmp_path: Path) -> None:
    source = tmp_path / "facts.tsv"
    long_value = "z" * (MAX_CELL_CHARS + 100)
    source.write_text(f"a\tb\tc\n1\t{long_value}\t3\n4\ty\t6\n", encoding="utf-8")

    result = _inspect(source, columns=["b", "missing"], include_samples=True, sample_rows=2)

    assert result["status"] == "available"
    assert result["source"]["format"] == "tsv"
    assert result["sample_columns"] == ["b"]
    assert len(result["samples"]) == 2
    assert len(result["samples"][0][0]) == MAX_CELL_CHARS
    assert result["columns"][0]["value_truncated_count"] == 1
    assert result["warnings"] == [{"code": "COLUMNS_NOT_FOUND", "columns": ["missing"]}]


def test_sample_validation_preserves_default_off(tmp_path: Path) -> None:
    source = tmp_path / "facts.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    disabled = _inspect(source, sample_rows=1)
    excessive = _inspect(source, include_samples=True, sample_rows=MAX_SAMPLE_ROWS + 1)
    assert disabled["availability"]["reason"] == "SAMPLES_NOT_ENABLED"
    assert excessive["availability"]["reason"] == "SAMPLE_ROW_LIMIT"


def test_nonfinite_values_are_counted_but_finite_range_stays_finite(tmp_path: Path) -> None:
    source = tmp_path / "numeric.csv"
    source.write_text("x\n-inf\n1\n2\ninf\nnan\n", encoding="utf-8")

    result = _inspect(source)

    column = result["columns"][0]
    assert column["dtype"] == "number"
    assert column["nonfinite_numeric_count"] == 3
    assert column["finite_range"] == {"min": 1, "max": 2}
    assert all(math.isfinite(value) for value in column["finite_range"].values())


def test_extreme_integer_has_typed_unavailable_range_instead_of_worker_failure(tmp_path: Path) -> None:
    source = tmp_path / "extreme.csv"
    source.write_text("x\n" + ("9" * 400) + "\n", encoding="utf-8")

    result = _inspect(source)

    assert result["status"] == "available"
    assert result["columns"][0]["dtype"] == "integer"
    assert result["columns"][0]["finite_range_unavailable_reason"] == "INTEGER_OUTSIDE_SAFE_JSON_RANGE"
    assert "finite_range" not in result["columns"][0]


def test_cardinality_is_bounded_and_reported_as_lower_bound(tmp_path: Path) -> None:
    source = tmp_path / "unique.csv"
    source.write_text("x\n" + "\n".join(f"v{i}" for i in range(worker.MAX_UNIQUE_VALUES + 5)) + "\n", encoding="utf-8")

    result = _inspect(source)

    column = result["columns"][0]
    assert column["unique_count"] is None
    assert column["unique_count_lower_bound"] == worker.MAX_UNIQUE_VALUES
    assert column["unique_count_truncated"] is True


def test_cardinality_uses_full_value_not_display_prefix(tmp_path: Path) -> None:
    source = tmp_path / "long-values.csv"
    shared = "x" * (MAX_CELL_CHARS + 50)
    source.write_text(f"value\n{shared}A\n{shared}B\n", encoding="utf-8")

    result = _inspect(source, include_samples=True, sample_rows=2)

    assert result["columns"][0]["unique_count"] == 2
    assert result["samples"][0][0] == result["samples"][1][0]
    assert len(result["samples"][0][0]) == MAX_CELL_CHARS


@pytest.mark.parametrize(
    "body",
    [
        'a,b\n1,"unterminated\n',
        'a,b\n1,"quoted"junk\n',
    ],
)
def test_malformed_csv_quoting_is_typed_unavailable(tmp_path: Path, body: str) -> None:
    source = tmp_path / "malformed.csv"
    source.write_text(body, encoding="utf-8")

    result = _inspect(source)

    assert result["status"] == "unavailable"
    assert result["availability"]["reason"] == "DELIMITED_PARSE_FAILED"


@pytest.mark.parametrize("suffix", [".gz", ".zip", ".parquet", ".xlsx", ".h5"])
def test_compressed_and_container_formats_are_typed_unavailable(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / f"data{suffix}"
    source.write_bytes(b"not expanded")

    result = _inspect(source)

    assert result["status"] == "unavailable"
    assert result["availability"]["reason"] == "COMPRESSED_OR_CONTAINER_UNAVAILABLE"


def test_compressed_magic_renamed_to_csv_is_not_expanded(tmp_path: Path) -> None:
    source = tmp_path / "renamed.csv"
    source.write_bytes(b"\x1f\x8b" + b"compressed secret")

    result = _inspect(source)

    assert result["status"] == "unavailable"
    assert result["availability"]["reason"] == "COMPRESSED_OR_CONTAINER_UNAVAILABLE"


def test_other_uncompressed_format_is_typed_unavailable(tmp_path: Path) -> None:
    source = tmp_path / "data.json"
    source.write_text('{"x": 1}', encoding="utf-8")

    result = _inspect(source)

    assert result["status"] == "unavailable"
    assert result["availability"]["reason"] == "FORMAT_UNSUPPORTED"


def test_worker_materialization_failure_is_typed_and_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "facts.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    monkeypatch.setattr(
        worker.tempfile,
        "TemporaryFile",
        lambda **_kwargs: (_ for _ in ()).throw(OSError(f"private temp at {tmp_path / 'secret-temp'}")),
    )
    result = worker.inspect_allowed_data_request(
        {
            "data_path": str(source),
            "allowed_roots": [str(tmp_path)],
            "relative_base": None,
            "prefetch_mode": "noop",
            "max_bytes": 1024,
            "deadline": time.monotonic() + 10,
            "columns": None,
            "include_samples": False,
            "sample_rows": 0,
        }
    )
    encoded = json.dumps(result, ensure_ascii=False)
    assert result["availability"]["reason"] == "WORKER_IO_FAILURE"
    assert str(tmp_path) not in encoded
    assert "secret-temp" not in encoded


def test_public_one_shot_rejects_absolute_escape_and_redacts_path(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "operator-secret" / "secret.csv"
    allowed.mkdir()
    outside.parent.mkdir()
    outside.write_text("x\nOUTSIDE_SECRET\n", encoding="utf-8")

    result = inspect_allowed_data(outside, allowed_roots=[allowed], prefetch_mode="noop")
    encoded = json.dumps(result, ensure_ascii=False)

    assert result["status"] == "unavailable"
    assert result["availability"]["reason"] == "DATA_PATH_OUTSIDE_ALLOWED_ROOT"
    assert str(outside) not in encoded
    assert "operator-secret" not in encoded
    assert "OUTSIDE_SECRET" not in encoded


def test_public_one_shot_rejects_relative_traversal(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.csv"
    outside.write_text("x\n1\n", encoding="utf-8")

    result = inspect_allowed_data(
        "../outside.csv",
        allowed_roots=[tmp_path],
        relative_base=tmp_path,
        prefetch_mode="noop",
    )

    assert result["availability"]["reason"] == "DATA_PATH_TRAVERSAL"


def test_public_one_shot_rejects_symlink_or_reparse_component(tmp_path: Path) -> None:
    target = tmp_path / "target.csv"
    target.write_text("x\n1\n", encoding="utf-8")
    link = tmp_path / "linked.csv"
    symlink_or_skip(link, target)

    result = inspect_allowed_data(link, allowed_roots=[tmp_path], prefetch_mode="noop")

    assert result["availability"]["reason"] == "DATA_PATH_REPARSE_POINT"


@pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-specific")
def test_public_one_shot_rejects_windows_junction(tmp_path: Path) -> None:
    target = tmp_path / "target-directory"
    target.mkdir()
    (target / "facts.csv").write_text("x\n1\n", encoding="utf-8")
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
        result = inspect_allowed_data(junction / "facts.csv", allowed_roots=[tmp_path], prefetch_mode="noop")
        assert result["availability"]["reason"] == "DATA_PATH_REPARSE_POINT"
    finally:
        os.rmdir(junction)


def test_public_one_shot_enforces_source_byte_cap(tmp_path: Path) -> None:
    source = tmp_path / "large.csv"
    source.write_bytes(b"x\n" + b"1\n" * 100)

    result = inspect_allowed_data(source, allowed_roots=[tmp_path], prefetch_mode="noop", max_bytes=16)

    assert result["availability"]["reason"] == "DATA_SOURCE_BYTE_LIMIT"


def test_public_timeout_terminates_contained_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "facts.csv"
    source.write_text("x\n1\n", encoding="utf-8")

    class Process:
        returncode = None

        @staticmethod
        def communicate(*, input, timeout):
            del input
            raise subprocess.TimeoutExpired("worker", timeout)

    class Limiter:
        terminated = False
        closed = False

        def terminate(self, process):
            assert isinstance(process, Process)
            self.terminated = True

        def close(self):
            self.closed = True

    limiter = Limiter()
    monkeypatch.setattr(inspection, "_start_worker", lambda: (Process(), limiter))

    result = inspect_allowed_data(source, allowed_roots=[tmp_path], prefetch_mode="noop")

    assert result["availability"]["reason"] == "INSPECTION_DEADLINE"
    assert limiter.terminated and limiter.closed


def test_public_timeout_reports_unreaped_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "facts.csv"
    source.write_text("x\n1\n", encoding="utf-8")

    class Process:
        returncode = None

        @staticmethod
        def communicate(*, input, timeout):
            del input
            raise subprocess.TimeoutExpired("worker", timeout)

    class Limiter:
        @staticmethod
        def terminate(_process):
            raise RuntimeError("unreaped")

        @staticmethod
        def close():
            return None

    monkeypatch.setattr(inspection, "_start_worker", lambda: (Process(), Limiter()))
    result = inspect_allowed_data(source, allowed_roots=[tmp_path], prefetch_mode="noop")
    assert result["availability"]["reason"] == "WORKER_TERMINATION_FAILED"


def test_one_shot_is_portable_from_python_c_without_importable_main(tmp_path: Path) -> None:
    source = tmp_path / "portable.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    script = (
        "from hub_core.data_inspection import inspect_allowed_data; "
        f"r=inspect_allowed_data({str(source)!r}, allowed_roots=[{str(tmp_path)!r}], prefetch_mode='noop'); "
        "print(r['status'])"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "available"


def test_one_shot_is_portable_from_python_stdin(tmp_path: Path) -> None:
    source = tmp_path / "portable-stdin.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    script = (
        "from hub_core.data_inspection import inspect_allowed_data\n"
        f"r=inspect_allowed_data({str(source)!r}, allowed_roots=[{str(tmp_path)!r}], prefetch_mode='noop')\n"
        "print(r['status'])\n"
    )

    completed = subprocess.run(
        [sys.executable, "-"],
        input=script.encode("utf-8"),
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        check=False,
        timeout=15,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert completed.stdout.decode("utf-8").strip() == "available"


def test_worker_row_cap_returns_truthful_lower_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "rows.csv"
    source.write_text("x\n1\n2\n3\n4\n", encoding="utf-8")
    monkeypatch.setattr(worker, "MAX_SCAN_ROWS", 3)

    result = worker.inspect_request(
        {
            "snapshot_path": str(source),
            "format": "csv",
            "remaining_seconds": 10,
            "columns": None,
            "include_samples": False,
            "sample_rows": 0,
        }
    )

    assert result["scan"]["row_count"] is None
    assert result["scan"]["row_count_lower_bound"] == 3
    assert result["scan"]["rows_scanned"] == 3
    assert result["truncation"]["row_limit"] is True


def test_worker_does_not_parse_record_after_row_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "bounded.csv"
    # Row four is malformed and would fail strict parsing if the parser were
    # advanced once more merely to probe for EOF.
    source.write_text('x\n1\n2\n3\n"unterminated\n', encoding="utf-8")
    monkeypatch.setattr(worker, "MAX_SCAN_ROWS", 3)

    result = worker.inspect_request(
        {
            "snapshot_path": str(source),
            "format": "csv",
            "remaining_seconds": 10,
            "columns": None,
            "include_samples": False,
            "sample_rows": 0,
        }
    )

    assert result["status"] == "available"
    assert result["scan"]["rows_scanned"] == 3
    assert result["truncation"]["row_limit"] is True


def test_public_worker_enforces_million_row_cap(tmp_path: Path) -> None:
    source = tmp_path / "million.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        handle.write("x\n")
        handle.write("1\n" * 1_000_001)

    result = _inspect(source)

    assert result["status"] == "available"
    assert result["scan"]["row_count"] is None
    assert result["scan"]["row_count_lower_bound"] == 1_000_000
    assert result["scan"]["rows_scanned"] == 1_000_000
    assert result["truncation"]["row_limit"] is True


def test_expired_shared_deadline_does_not_start_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "facts.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    expired = _legacy_snapshot(source, deadline=time.monotonic() - 1)
    monkeypatch.setattr(
        "hub_core.data_inspection._start_worker",
        lambda: pytest.fail("worker must not start after shared deadline"),
    )
    result = inspect_data(expired)

    assert result["status"] == "unavailable"
    assert result["availability"]["reason"] == "INSPECTION_DEADLINE"


def test_spawn_latency_is_charged_to_shared_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "facts.csv"
    source.write_text("x\n1\n", encoding="utf-8")

    class Process:
        returncode = 0
        captured_timeout = None
        captured_request = None

        def communicate(self, *, input, timeout):
            self.captured_timeout = timeout
            self.captured_request = json.loads(input)
            payload = {
                "status": "available",
                "availability": {"state": "available", "reason": None},
                "scan": {"row_count": 0, "rows_scanned": 0, "columns_detected": 0, "columns_returned": 0},
                "columns": [],
                "sample_columns": [],
                "samples": [],
                "truncation": {},
                "warnings": [],
            }
            return json.dumps(payload).encode(), b""

    class Limiter:
        def terminate(self, process):
            pytest.fail(f"unexpected termination: {process}")

        def close(self):
            return None

    process = Process()
    ticks = iter([90.0, 97.0, 98.0])
    artificial = _legacy_snapshot(source, deadline=100.0)
    monkeypatch.setattr(inspection.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(inspection, "_start_worker", lambda: (process, Limiter()))
    result = inspect_data(artificial)

    assert result["status"] == "available"
    assert process.captured_request["remaining_seconds"] == 3.0
    assert process.captured_timeout == 2.0


def test_memory_limiter_unavailable_fails_before_unbounded_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "facts.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    monkeypatch.setattr(
        inspection,
        "_start_worker",
        lambda: (_ for _ in ()).throw(inspection._WorkerLimitUnavailable()),
    )
    result = inspect_data(_legacy_snapshot(source))

    assert result["status"] == "unavailable"
    assert result["availability"]["reason"] == "WORKER_MEMORY_LIMIT_UNAVAILABLE"
    assert result["limits"]["worker_memory_enforced"] is False


def test_darwin_inspection_continues_with_non_memory_limits_and_reports_limitation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "facts.csv"
    source.write_text("x\n1\n", encoding="utf-8")

    class Process:
        returncode = 0

        @staticmethod
        def communicate(*, input, timeout):
            del input, timeout
            payload = {
                "status": "available",
                "availability": {"state": "available", "reason": None},
                "scan": {"row_count": 1},
                "columns": [],
                "samples": [],
                "truncation": {},
                "warnings": [],
            }
            return json.dumps(payload).encode(), b""

    limiter = inspection._PosixProcessGroupLimiter(memory_enforced=False)
    monkeypatch.setattr(inspection, "_start_worker", lambda: (Process(), limiter))

    result = inspect_data(_legacy_snapshot(source))

    assert result["status"] == "available"
    assert result["limits"]["worker_memory_enforced"] is False
    assert "unavailable on this host" in result["limits"]["worker_memory_limitation"]


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object failure path is Windows-specific")
def test_windows_job_creation_failure_never_spawns_unbounded_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    popen = pytest.fail
    monkeypatch.setattr(inspection._WindowsJobLimiter, "create", lambda: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(inspection.subprocess, "Popen", popen)

    with pytest.raises(inspection._WorkerLimitUnavailable):
        inspection._start_worker()


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object failure path is Windows-specific")
def test_windows_job_assignment_failure_kills_worker_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        pid = 123
        returncode = None
        killed = False
        waited = False

        def poll(self):
            return None

        def kill(self):
            self.killed = True

        def wait(self):
            self.waited = True

    class Limiter:
        closed = False

        def assign(self, _process):
            raise OSError("assignment failed")

        def close(self):
            self.closed = True

    process = Process()
    limiter = Limiter()
    calls = 0

    def popen(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return process

    monkeypatch.setattr(inspection._WindowsJobLimiter, "create", lambda: limiter)
    monkeypatch.setattr(inspection.subprocess, "Popen", popen)
    with pytest.raises(inspection._WorkerLimitUnavailable):
        inspection._start_worker()

    assert calls == 1
    assert process.killed and process.waited
    assert limiter.closed


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups are unavailable on Windows")
def test_posix_timeout_limiter_kills_entire_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    class Process:
        pid = 4242

        @staticmethod
        def poll():
            return None

        @staticmethod
        def wait(timeout):
            assert timeout == 0.75

        @staticmethod
        def kill():
            pytest.fail("single-process fallback must not run when killpg succeeds")

    killpg = []
    monkeypatch.setattr(inspection.os, "killpg", lambda pid, sig: killpg.append((pid, sig)))
    inspection._PosixProcessGroupLimiter().terminate(Process())
    assert killpg == [(4242, inspection.signal.SIGKILL)]


def test_response_is_compact_under_worst_case_headers_and_samples(tmp_path: Path) -> None:
    source = tmp_path / "wide.csv"
    header = [f"column_{index}_" + ("h" * 120) for index in range(256)]
    row = ["v" * 600 for _ in header]
    source.write_text(",".join(header) + "\n" + ",".join(row) + "\n", encoding="utf-8")

    result = _inspect(source, include_samples=True, sample_rows=1)
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    assert len(encoded) <= MAX_INSPECTION_RESPONSE_BYTES
    assert result["truncation"]["columns_for_response_size"] is True
    assert result["scan"]["columns_returned"] < 256


def test_worker_failure_is_path_redacted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "operator-secret.csv"
    source.write_text("x\n1\n", encoding="utf-8")

    class FailedProcess:
        returncode = 1

        @staticmethod
        def communicate(*, input, timeout):
            del input, timeout
            return str(source).encode(), b""

    class Limiter:
        @staticmethod
        def close():
            return None

    monkeypatch.setattr("hub_core.data_inspection._start_worker", lambda: (FailedProcess(), Limiter()))
    result = inspect_data(_legacy_snapshot(source))

    encoded = json.dumps(result, ensure_ascii=False)
    assert result["availability"]["reason"] == "WORKER_FAILURE"
    assert str(tmp_path) not in encoded
    assert result["limits"]["worker_memory_enforced"] is True
