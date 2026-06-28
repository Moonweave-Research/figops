import importlib.util
import logging
import os
from pathlib import Path

from .adapters import select_adapters
from .logging import get_logger

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


def read_data_safe(data_path, pd, hdf_key: str = "/data"):
    """
    포맷을 자동 감지하여 데이터를 읽습니다.
    - .csv / .tsv / .txt  → read_csv_safe() (청크 지원)
    - .parquet            → pd.read_parquet() (pyarrow 필요)
    - .h5 / .hdf5         → pd.read_hdf()    (tables 필요, key=hdf_key)
    - .feather            → pd.read_feather() (pyarrow 필요)
    그 외 확장자는 CSV로 fallback합니다.
    """
    suffix = os.path.splitext(data_path)[1].lower()

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
        return pd.read_parquet(data_path)

    if suffix in {".h5", ".hdf5"}:
        try:
            import tables  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "PyTables (tables) is required to read HDF5 files. Install with: uv pip install 'figops[io]'"
            ) from exc
        try:
            return pd.read_hdf(data_path, key=hdf_key)
        except KeyError:
            # Do NOT silently fall back to a different dataset: rendering the wrong
            # data with no signal is worse than failing. Report the available keys.
            import h5py

            with h5py.File(data_path, "r") as hf:
                available_keys = list(hf.keys())
            if not available_keys:
                raise KeyError(f"HDF5 file has no datasets: {data_path}")
            available = ", ".join(f"/{key}" for key in available_keys)
            raise KeyError(
                f"HDF5 key '{hdf_key}' not found in {Path(data_path).name}. "
                f"Available keys: {available}. Set the correct key explicitly "
                "instead of relying on a fallback (the wrong dataset would render silently)."
            )

    if suffix == ".feather":
        try:
            import pyarrow  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "pyarrow is required to read Feather files. Install with: uv pip install 'figops[io]'"
            ) from exc
        return pd.read_feather(data_path)

    raise ValueError(
        f"Unsupported file format '{suffix}' for: {data_path}. "
        "Supported: .csv, .tsv, .txt, .parquet, .h5, .hdf5, .feather"
    )


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
