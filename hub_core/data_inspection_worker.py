"""Isolated CSV/TSV profiler used by :mod:`hub_core.data_inspection`.

The worker accepts one JSON request on stdin and writes one compact JSON result
on stdout. It never reports its private snapshot pathname or recommendations.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_SCAN_ROWS = 1_000_000
MAX_RETURNED_COLUMNS = 256
MAX_SAMPLE_ROWS = 20
MAX_CELL_CHARS = 512
MAX_UNIQUE_VALUES = 1024
MAX_CSV_FIELD_CHARS = 1024 * 1024
WORKER_RESPONSE_BYTES = 28 * 1024
MAX_JSON_SAFE_INTEGER = (1 << 53) - 1


def _truncation_flags() -> dict[str, bool]:
    return {
        "row_limit": False,
        "deadline": False,
        "columns": False,
        "cell_strings": False,
        "samples_for_response_size": False,
        "columns_for_response_size": False,
    }


def _trim(value: str) -> tuple[str, bool]:
    if len(value) <= MAX_CELL_CHARS:
        return value, False
    return value[:MAX_CELL_CHARS], True


def _scalar_kind(value: str) -> tuple[str, int | float | bool | None]:
    stripped = value.strip()
    if not stripped:
        return "null", None
    lowered = stripped.casefold()
    if lowered in {"true", "false"}:
        return "boolean", lowered == "true"
    try:
        integer = int(stripped, 10)
    except ValueError:
        pass
    else:
        return "integer", integer
    try:
        number = float(stripped)
    except ValueError:
        return "string", None
    return "number", number


@dataclass
class _Column:
    name: str
    name_truncated: bool
    null_count: int = 0
    nonfinite_count: int = 0
    value_truncated_count: int = 0
    kinds: set[str] = field(default_factory=set)
    minimum: float | int | None = None
    maximum: float | int | None = None
    unique: set[bytes] = field(default_factory=set)
    unique_truncated: bool = False
    range_unavailable_reason: str | None = None
    last_short_value: str | None = None

    def consume(self, raw: str) -> None:
        value, truncated = _trim(raw)
        if truncated:
            self.value_truncated_count += 1
        kind, parsed = _scalar_kind(raw)
        if kind == "null":
            self.null_count += 1
        else:
            self.kinds.add(kind)
            if not self.unique_truncated and (len(raw) > MAX_CELL_CHARS or raw != self.last_short_value):
                # Display truncation must never collapse cardinality. Retain a
                # fixed-size cryptographic identity of the complete decoded
                # field instead of its 512-character presentation prefix.
                self.unique.add(hashlib.sha256(raw.encode("utf-8")).digest())
                if len(self.unique) > MAX_UNIQUE_VALUES:
                    self.unique_truncated = True
                    # Keep a truthful lower bound without retaining the full set.
                    self.unique = set(tuple(self.unique)[:MAX_UNIQUE_VALUES])
            self.last_short_value = raw if len(raw) <= MAX_CELL_CHARS else None
        if kind == "integer" and isinstance(parsed, int) and not isinstance(parsed, bool):
            if abs(parsed) > MAX_JSON_SAFE_INTEGER:
                self.range_unavailable_reason = "INTEGER_OUTSIDE_SAFE_JSON_RANGE"
            elif self.range_unavailable_reason is None:
                self.minimum = parsed if self.minimum is None else min(self.minimum, parsed)
                self.maximum = parsed if self.maximum is None else max(self.maximum, parsed)
        elif kind == "number" and isinstance(parsed, float):
            if not math.isfinite(parsed):
                self.nonfinite_count += 1
            elif self.range_unavailable_reason is None:
                self.minimum = parsed if self.minimum is None else min(self.minimum, parsed)
                self.maximum = parsed if self.maximum is None else max(self.maximum, parsed)

    def dtype(self) -> str:
        if not self.kinds:
            return "null"
        if self.kinds <= {"integer"}:
            return "integer"
        if self.kinds <= {"integer", "number"}:
            return "number"
        if self.kinds <= {"boolean"}:
            return "boolean"
        return "string"

    def payload(self, rows: int) -> dict[str, Any]:
        dtype = self.dtype()
        result: dict[str, Any] = {
            "name": self.name,
            "dtype": dtype,
            "null_count": self.null_count,
            "null_fraction": round(self.null_count / rows, 8) if rows else 0.0,
            "unique_count": None if self.unique_truncated else len(self.unique),
            "unique_count_lower_bound": len(self.unique) if self.unique_truncated else None,
            "unique_count_truncated": self.unique_truncated,
        }
        if self.name_truncated:
            result["name_truncated"] = True
        if self.value_truncated_count:
            result["value_truncated_count"] = self.value_truncated_count
        if self.nonfinite_count:
            result["nonfinite_numeric_count"] = self.nonfinite_count
        if dtype in {"integer", "number"} and self.range_unavailable_reason:
            result["finite_range_unavailable_reason"] = self.range_unavailable_reason
        elif dtype in {"integer", "number"} and self.minimum is not None:
            result["finite_range"] = {"min": self.minimum, "max": self.maximum}
        return result


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "availability": {"state": "unavailable", "reason": reason},
        "scan": None,
        "columns": [],
        "sample_columns": [],
        "samples": [],
        "truncation": _truncation_flags(),
        "warnings": [],
    }


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    def encoded_size() -> int:
        return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    if encoded_size() <= WORKER_RESPONSE_BYTES:
        return payload
    samples = payload.get("samples")
    if isinstance(samples, list) and samples:
        samples.clear()
        payload["sample_columns"] = []
        payload.setdefault("truncation", _truncation_flags())["samples_for_response_size"] = True
    columns = payload.get("columns")
    if isinstance(columns, list):
        while columns and encoded_size() > WORKER_RESPONSE_BYTES:
            columns.pop()
        scan = payload.get("scan")
        if isinstance(scan, dict):
            scan["columns_returned"] = len(columns)
        payload.setdefault("truncation", _truncation_flags())["columns_for_response_size"] = True
    if encoded_size() > WORKER_RESPONSE_BYTES:
        return _unavailable("RESPONSE_BYTE_LIMIT")
    return payload


def inspect_stream(
    source,
    *,
    data_format: str,
    deadline: float,
    requested_columns: list[str] | None,
    include_samples: bool,
    sample_rows: int,
) -> dict[str, Any]:
    """Profile one already-frozen text stream without reopening a path."""

    if data_format not in {"csv", "tsv"}:
        return _unavailable("FORMAT_UNSUPPORTED")
    if time.monotonic() >= deadline:
        return _unavailable("INSPECTION_DEADLINE")
    if not 0 <= sample_rows <= MAX_SAMPLE_ROWS:
        return _unavailable("SAMPLE_ROW_LIMIT")
    if not include_samples:
        sample_rows = 0
    if requested_columns is not None and (
        not isinstance(requested_columns, list)
        or len(requested_columns) > MAX_RETURNED_COLUMNS
        or any(not isinstance(name, str) or not name or len(name) > MAX_CELL_CHARS for name in requested_columns)
    ):
        return _unavailable("COLUMN_FILTER_INVALID")

    delimiter = "," if data_format == "csv" else "\t"
    csv.field_size_limit(MAX_CSV_FIELD_CHARS)
    try:
        reader = csv.reader(source, delimiter=delimiter, strict=True)
        try:
            raw_header = next(reader)
        except StopIteration:
            return _unavailable("DATA_FILE_EMPTY")
        except (csv.Error, UnicodeError):
            return _unavailable("DELIMITED_PARSE_FAILED")
        if not raw_header:
            return _unavailable("HEADER_MISSING")

        header: list[tuple[str, bool]] = [_trim(name) for name in raw_header]
        selected_indices: list[int]
        missing: list[str] = []
        if requested_columns is None:
            selected_indices = list(range(min(len(header), MAX_RETURNED_COLUMNS)))
        else:
            selected_indices = []
            for requested in requested_columns:
                matches = [index for index, (name, _) in enumerate(header) if name == requested]
                if not matches:
                    missing.append(requested)
                else:
                    selected_indices.extend(matches)
            selected_indices = selected_indices[:MAX_RETURNED_COLUMNS]
        columns = [_Column(name=header[index][0], name_truncated=header[index][1]) for index in selected_indices]

        rows_scanned = 0
        row_limit_reached = False
        deadline_reached = False
        width_mismatch_count = 0
        samples: list[list[str]] = []
        while rows_scanned < MAX_SCAN_ROWS:
            if rows_scanned % 256 == 0 and time.monotonic() >= deadline:
                deadline_reached = True
                break
            try:
                row = next(reader)
            except StopIteration:
                break
            rows_scanned += 1
            if len(row) != len(header):
                width_mismatch_count += 1
            sample: list[str] = []
            for output_index, source_index in enumerate(selected_indices):
                raw = row[source_index] if source_index < len(row) else ""
                columns[output_index].consume(raw)
                if len(samples) < sample_rows:
                    sample.append(_trim(raw)[0])
            if len(samples) < sample_rows:
                samples.append(sample)
        if rows_scanned >= MAX_SCAN_ROWS:
            # Do not call next(reader) to probe for another record: parsing row
            # MAX_SCAN_ROWS + 1 would violate the hard scan contract. The exact
            # total is therefore intentionally unavailable at the ceiling.
            row_limit_reached = True
    except (csv.Error, UnicodeError):
        return _unavailable("DELIMITED_PARSE_FAILED")

    count_truncated = row_limit_reached or deadline_reached
    warnings: list[dict[str, Any]] = []
    if missing:
        warnings.append({"code": "COLUMNS_NOT_FOUND", "columns": missing[:MAX_RETURNED_COLUMNS]})
    if width_mismatch_count:
        warnings.append({"code": "ROW_WIDTH_MISMATCH", "count": width_mismatch_count})
    payload: dict[str, Any] = {
        "status": "available",
        "availability": {"state": "available", "reason": None},
        "scan": {
            "row_count": None if count_truncated else rows_scanned,
            "row_count_lower_bound": rows_scanned if count_truncated else None,
            "rows_scanned": rows_scanned,
            "columns_detected": len(header),
            "columns_returned": len(columns),
        },
        "columns": [column.payload(rows_scanned) for column in columns],
        "sample_columns": [column.name for column in columns] if samples else [],
        "samples": samples,
        "truncation": {
            **_truncation_flags(),
            "row_limit": row_limit_reached,
            "deadline": deadline_reached,
            "columns": len(header) > len(selected_indices) and requested_columns is None,
            "cell_strings": any(column.value_truncated_count for column in columns),
        },
        "warnings": warnings,
    }
    return _compact(payload)


def inspect_request(request: dict[str, Any]) -> dict[str, Any]:
    """Profile one private, already-verified uncompressed CSV/TSV snapshot."""

    try:
        snapshot = Path(request["snapshot_path"])
        data_format = str(request["format"])
        remaining_seconds = float(request["remaining_seconds"])
        requested_columns = request.get("columns")
        include_samples = bool(request.get("include_samples", False))
        sample_rows = int(request.get("sample_rows", 0))
    except (KeyError, TypeError, ValueError):
        return _unavailable("WORKER_REQUEST_INVALID")
    if remaining_seconds <= 0:
        return _unavailable("INSPECTION_DEADLINE")
    try:
        source = snapshot.open("r", encoding="utf-8-sig", errors="strict", newline="")
    except (OSError, UnicodeError):
        return _unavailable("SNAPSHOT_READ_FAILED")
    try:
        return inspect_stream(
            source,
            data_format=data_format,
            deadline=time.monotonic() + remaining_seconds,
            requested_columns=requested_columns,
            include_samples=include_samples,
            sample_rows=sample_rows,
        )
    finally:
        source.close()


def _frozen_format(suffix: str, head: bytes) -> tuple[str | None, str | None]:
    if (
        head.startswith(b"\x1f\x8b")
        or head.startswith(b"BZh")
        or head.startswith(b"\xfd7zXZ\x00")
        or head.startswith(b"PK\x03\x04")
        or head.startswith(b"7z\xbc\xaf\x27\x1c")
        or head.startswith(b"PAR1")
        or head.startswith(b"\x89HDF\r\n\x1a\n")
    ):
        return None, "COMPRESSED_OR_CONTAINER_UNAVAILABLE"
    if suffix == ".csv":
        return "csv", None
    if suffix == ".tsv":
        return "tsv", None
    if suffix in {".gz", ".zip", ".bz2", ".xz", ".parquet", ".xlsx", ".xls", ".h5", ".hdf5"}:
        return None, "COMPRESSED_OR_CONTAINER_UNAVAILABLE"
    return None, "FORMAT_UNSUPPORTED"


def _worker_unavailable(reason: str, *, name: str, data_format: str | None = None) -> dict[str, Any]:
    payload = _unavailable(reason)
    payload["schema_version"] = "figops.inspect-data.v1"
    payload["source"] = {"name": name[:MAX_CELL_CHARS], "format": data_format, "byte_size": None, "sha256": None}
    return payload


def inspect_allowed_data_request(request: dict[str, Any]) -> dict[str, Any]:
    """Contain, freeze, hash, and parse in this one hard-bounded worker."""

    from hub_core.allowed_data import (
        ABSOLUTE_INSPECT_MAX_BYTES,
        SNAPSHOT_CHUNK_BYTES,
        AllowedDataError,
        open_verified_allowed_data,
        safe_data_name,
    )

    try:
        raw_path = request["data_path"]
        allowed_roots = request["allowed_roots"]
        relative_base = request.get("relative_base")
        prefetch_mode = str(request["prefetch_mode"])
        max_bytes = int(request["max_bytes"])
        deadline = float(request["deadline"])
        columns = request.get("columns")
        include_samples = bool(request.get("include_samples", False))
        sample_rows = int(request.get("sample_rows", 0))
    except (KeyError, TypeError, ValueError):
        return _worker_unavailable("WORKER_REQUEST_INVALID", name="<data-file>")
    name = safe_data_name(raw_path)
    if prefetch_mode not in {"none", "noop", "gdrive"}:
        return _worker_unavailable("PREFETCH_ADAPTER_UNSUPPORTED", name=name)
    if not 0 < max_bytes <= ABSOLUTE_INSPECT_MAX_BYTES:
        return _worker_unavailable("INSPECTION_LIMIT_INVALID", name=name)
    try:
        with open_verified_allowed_data(
            raw_path,
            allowed_roots=allowed_roots,
            relative_base=relative_base,
            prefetch_mode=prefetch_mode,
            max_bytes=max_bytes,
            deadline=deadline,
        ) as verified:
            digest = hashlib.sha256()
            copied = 0
            with tempfile.TemporaryFile(mode="w+b") as frozen:
                while True:
                    if time.monotonic() >= deadline:
                        raise AllowedDataError("INSPECTION_DEADLINE", "Data inspection exceeded its deadline.")
                    chunk = verified.handle.read(SNAPSHOT_CHUNK_BYTES)
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > max_bytes:
                        raise AllowedDataError("DATA_SOURCE_BYTE_LIMIT", "Data file exceeds the inspection limit.")
                    digest.update(chunk)
                    frozen.write(chunk)
                if copied != verified.byte_size:
                    raise AllowedDataError("DATA_PATH_CHANGED", "Data file size changed while it was copied.")
                frozen.flush()
                frozen.seek(0)
                data_format, unavailable_reason = _frozen_format(verified.suffix, frozen.read(8))
                source_payload = {
                    "name": verified.display_name,
                    "format": data_format,
                    "byte_size": copied,
                    "sha256": digest.hexdigest(),
                }
                if unavailable_reason:
                    result = _worker_unavailable(
                        unavailable_reason,
                        name=verified.display_name,
                        data_format=data_format,
                    )
                    result["source"] = source_payload
                else:
                    frozen.seek(0)
                    text_source = io.TextIOWrapper(frozen, encoding="utf-8-sig", errors="strict", newline="")
                    try:
                        result = inspect_stream(
                            text_source,
                            data_format=data_format,
                            deadline=deadline,
                            requested_columns=columns,
                            include_samples=include_samples,
                            sample_rows=sample_rows,
                        )
                    finally:
                        text_source.detach()
                    result["schema_version"] = "figops.inspect-data.v1"
                    result["source"] = source_payload
                result["prefetch_calls"] = verified.prefetch_calls
        return result
    except AllowedDataError as exc:
        return _worker_unavailable(exc.code, name=name)
    except (OSError, UnicodeError):
        return _worker_unavailable("WORKER_IO_FAILURE", name=name)
    except Exception:
        return _worker_unavailable("WORKER_FAILURE", name=name)


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(64 * 1024)
        if len(raw) >= 64 * 1024:
            payload = _unavailable("WORKER_REQUEST_BYTE_LIMIT")
        else:
            request = json.loads(raw.decode("utf-8"))
            if not isinstance(request, dict):
                payload = _unavailable("WORKER_REQUEST_INVALID")
            elif request.get("operation") == "inspect_allowed_data":
                payload = inspect_allowed_data_request(request)
            else:
                payload = inspect_request(request)
    except Exception:
        # Do not leak private paths, parser internals, or tracebacks to MCP.
        payload = _unavailable("WORKER_FAILURE")
    sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
