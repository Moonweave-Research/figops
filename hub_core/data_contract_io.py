import importlib.util
import logging
import os
import shutil
import tempfile
from pathlib import Path

from .adapters import select_adapters
from .logging import get_logger
from .project_paths import (
    ProjectInputSnapshot,
    open_verified_project_input,
    revalidate_project_input,
)

logger = get_logger(__name__)

CSV_CHUNK_THRESHOLD_BYTES = 256 * 1024 * 1024  # 256 MB
CSV_CHUNK_SIZE = 50_000  # rows per chunk
SUPPORTED_DATA_CONTRACT_SUFFIXES = {
    ".csv",
    ".tsv",
    ".txt",
    ".parquet",
    ".h5",
    ".hdf5",
    ".feather",
}
OPTIONAL_IO_DEPENDENCIES = {
    ".parquet": ("pyarrow", "pyarrow"),
    ".feather": ("pyarrow", "pyarrow"),
    ".h5": ("tables", "PyTables (tables)"),
    ".hdf5": ("tables", "PyTables (tables)"),
}


def _log(message: str) -> None:
    if "❌" in message:
        level = logging.ERROR
    elif "⚠️" in message or "🟠" in message:
        level = logging.WARNING
    else:
        level = logging.INFO
    logger.log(level, message)


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def read_csv_safe(csv_path, pd, log_func=None, **read_kwargs):
    """
    CSV를 안전하게 읽습니다.
    256 MB 미만: 전체 로드 (빠름).
    256 MB 이상: 청크 단위 로드 후 concat (메모리 효율).
    """
    if hasattr(csv_path, "fileno"):
        file_size = os.fstat(csv_path.fileno()).st_size
        csv_path.seek(0)
    else:
        file_size = os.path.getsize(csv_path)
    if file_size < CSV_CHUNK_THRESHOLD_BYTES:
        return pd.read_csv(csv_path, encoding="utf-8-sig", **read_kwargs)

    log = log_func or _log
    log(f"      ℹ️  Large file ({file_size // 1024 // 1024} MB) — using chunked read")
    chunks = pd.read_csv(
        csv_path,
        encoding="utf-8-sig",
        chunksize=CSV_CHUNK_SIZE,
        **read_kwargs,
    )
    return pd.concat(chunks, ignore_index=True)


def _read_hdf_path(data_path, pd, hdf_key: str):
    try:
        return pd.read_hdf(data_path, key=hdf_key)
    except KeyError:
        # Do NOT silently fall back to a different dataset: rendering the wrong
        # data with no signal is worse than failing. Report the available keys.
        import h5py

        with h5py.File(data_path, "r") as hf:
            available_keys = list(hf.keys())
        if not available_keys:
            raise KeyError("HDF5 file has no datasets.")
        available = ", ".join(f"/{key}" for key in available_keys)
        raise KeyError(
            f"HDF5 key '{hdf_key}' not found in {Path(data_path).name}. "
            f"Available keys: {available}. Set the correct key explicitly "
            "instead of relying on a fallback (the wrong dataset would render silently)."
        )


def _read_hdf_verified_stream(data_stream, pd, hdf_key: str):
    """Materialize an already-verified descriptor without reopening its source path."""

    with tempfile.TemporaryDirectory(prefix="figops_verified_hdf_") as temp_dir:
        os.chmod(temp_dir, 0o700)
        materialized = Path(temp_dir) / "input.h5"
        data_stream.seek(0)
        with materialized.open("xb") as destination:
            os.chmod(materialized, 0o600)
            shutil.copyfileobj(data_stream, destination, length=1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        try:
            return _read_hdf_path(materialized, pd, hdf_key)
        except Exception as exc:
            original = str(exc)
            sanitized = original
            for sensitive in (str(materialized), str(temp_dir)):
                sanitized = sanitized.replace(sensitive, "<verified-hdf-input>")
                sanitized = sanitized.replace(sensitive.replace("\\", "/"), "<verified-hdf-input>")
            if sanitized == original:
                raise
            try:
                safe_exception = type(exc)(sanitized)
            except Exception:
                safe_exception = RuntimeError(f"Failed to read verified HDF5 input: {sanitized}")
            raise safe_exception from None


def read_data_safe(data_path, pd, hdf_key: str = "/data", *, suffix: str | None = None):
    """
    포맷을 자동 감지하여 데이터를 읽습니다.
    - .csv / .tsv / .txt  → read_csv_safe() (청크 지원)
    - .parquet            → pd.read_parquet() (pyarrow 필요)
    - .h5 / .hdf5         → pd.read_hdf()    (tables 필요, key=hdf_key)
    - .feather            → pd.read_feather() (pyarrow 필요)
    그 외 확장자는 CSV로 fallback합니다.
    """
    if suffix is None:
        suffix = os.path.splitext(os.fspath(data_path))[1].lower()
    else:
        suffix = str(suffix).lower()

    if suffix in {".csv", ".tsv", ".txt"}:
        read_kwargs = {}
        if suffix == ".tsv":
            read_kwargs["sep"] = "\t"
        elif suffix == ".txt":
            read_kwargs["sep"] = None
            read_kwargs["engine"] = "python"
        return read_csv_safe(data_path, pd, **read_kwargs)

    if suffix == ".parquet":
        try:
            import pyarrow  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "pyarrow is required to read Parquet files. Install with: uv pip install 'figops[io]'"
            ) from exc
        if hasattr(data_path, "seek"):
            data_path.seek(0)
        return pd.read_parquet(data_path)

    if suffix in {".h5", ".hdf5"}:
        try:
            import tables  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "PyTables (tables) is required to read HDF5 files. Install with: uv pip install 'figops[io]'"
            ) from exc
        if hasattr(data_path, "read"):
            return _read_hdf_verified_stream(data_path, pd, hdf_key)
        return _read_hdf_path(data_path, pd, hdf_key)

    if suffix == ".feather":
        try:
            import pyarrow  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "pyarrow is required to read Feather files. Install with: uv pip install 'figops[io]'"
            ) from exc
        if hasattr(data_path, "seek"):
            data_path.seek(0)
        return pd.read_feather(data_path)

    raise ValueError(
        f"Unsupported file format '{suffix}'. "
        "Supported: .csv, .tsv, .txt, .parquet, .h5, .hdf5, .feather"
    )


def read_project_data_safe(
    project_root,
    declared_path,
    pd,
    *,
    expected_snapshot: ProjectInputSnapshot,
    hdf_key: str = "/data",
):
    """Revalidate a declared project input immediately before one bounded read."""

    purpose = "data_contract.csv_checks[].path"
    declared_suffix = Path(str(declared_path).replace("\\", "/")).suffix.lower()
    with open_verified_project_input(
        project_root,
        declared_path,
        expected_snapshot=expected_snapshot,
        purpose=purpose,
    ) as data_handle:
        result = read_data_safe(
            data_handle,
            pd,
            hdf_key=hdf_key,
            suffix=declared_suffix,
        )
    # If the boundary changed while the verified handle was being parsed, fail
    # closed even though no bytes from the replacement pathname were consumed.
    revalidate_project_input(
        project_root,
        declared_path,
        expected_snapshot=expected_snapshot,
        purpose=purpose,
    )
    return result


def get_data_contract_paths(config):
    contract = config.get("data_contract", {})
    checks = contract.get("csv_checks", []) if isinstance(contract, dict) else []
    paths = []
    for check in checks:
        if isinstance(check, dict):
            rel_path = check.get("path")
            if isinstance(rel_path, str) and rel_path.strip():
                paths.append(rel_path.strip())
    # Keep order while removing duplicates
    deduped = []
    seen = set()
    for p in paths:
        if p not in seen:
            deduped.append(p)
            seen.add(p)
    return deduped


def resolve_prefetcher(config: dict, prefetcher=None):
    return prefetcher if prefetcher is not None else select_adapters(config).prefetcher
