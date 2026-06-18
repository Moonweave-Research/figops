"""
Data Regression Module: Numeric drift detection for CSV, Parquet, and TSV data artifacts.
Ensures scientific reproducibility through golden-dataset comparison.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

DEFAULT_ATOL = 1e-6
DEFAULT_RTOL = 1e-5
SUPPORTED_SUFFIXES = {".csv", ".tsv", ".parquet"}


@dataclass
class RegressionFailure:
    path: str
    reason: str
    diff_summary: str = ""


@dataclass
class RegressionResult:
    success: bool
    compared_files: list[str] = field(default_factory=list)
    frozen_files: list[str] = field(default_factory=list)
    failures: list[RegressionFailure] = field(default_factory=list)
    manifest_path: str = ""
    golden_dir: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["failures"] = [asdict(item) for item in self.failures]
        return payload


def freeze_golden_dataset(project_dir: str | Path, config: dict) -> RegressionResult:
    project_path = Path(project_dir).expanduser().resolve()
    golden_dir = project_path / "results" / "data" / "golden"
    golden_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries = []
    frozen_files: list[str] = []
    for target in _collect_golden_targets(project_path, config):
        relative = target.relative_to(project_path / "results" / "data")
        destination = golden_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, destination)
        frozen_files.append(str(relative).replace("\\", "/"))
        manifest_entries.append(
            {
                "path": str(relative).replace("\\", "/"),
                "sha256": _sha256(destination),
                "size_bytes": destination.stat().st_size,
            }
        )

    manifest_path = golden_dir / "golden_hash.json"
    manifest_path.write_text(
        json.dumps(
            {
                "files": manifest_entries,
                "count": len(manifest_entries),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return RegressionResult(
        success=True,
        frozen_files=frozen_files,
        manifest_path=str(manifest_path),
        golden_dir=str(golden_dir),
    )


def check_golden_regression(
    project_dir: str | Path,
    config: dict,
    *,
    default_atol: float = DEFAULT_ATOL,
) -> RegressionResult:
    project_path = Path(project_dir).expanduser().resolve()
    golden_dir = project_path / "results" / "data" / "golden"
    manifest_path = golden_dir / "golden_hash.json"
    if not golden_dir.exists() or not manifest_path.exists():
        return RegressionResult(
            success=False,
            failures=[
                RegressionFailure(
                    path="results/data/golden",
                    reason="Golden dataset not frozen yet.",
                )
            ],
            manifest_path=str(manifest_path),
            golden_dir=str(golden_dir),
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest.get("files", []):
        recorded_path = entry.get("path", "")
        recorded_hash = entry.get("sha256", "")
        baseline_path = golden_dir / recorded_path
        if not baseline_path.exists() or _sha256(baseline_path) != recorded_hash:
            return RegressionResult(
                success=False,
                failures=[
                    RegressionFailure(
                        path=recorded_path,
                        reason=f"Golden baseline integrity check failed: {recorded_path}",
                    )
                ],
                manifest_path=str(manifest_path),
                golden_dir=str(golden_dir),
            )

    failures: list[RegressionFailure] = []
    compared_files: list[str] = []
    for target_spec in _collect_golden_specs(project_path, config):
        relative = target_spec["path"]
        compared_files.append(relative)
        current_path = project_path / relative
        golden_path = golden_dir / Path(relative).relative_to("results/data")
        if not current_path.exists():
            failures.append(
                RegressionFailure(
                    path=relative,
                    reason="Current data file is missing.",
                )
            )
            continue
        if not golden_path.exists():
            failures.append(
                RegressionFailure(
                    path=relative,
                    reason="Golden baseline file is missing.",
                )
            )
            continue

        try:
            _compare_tables(current_path, golden_path, atol=target_spec["atol"], rtol=target_spec["rtol"])
        except AssertionError as exc:
            failures.append(
                RegressionFailure(
                    path=relative,
                    reason="Scientific drift detected.",
                    diff_summary=_build_diff_summary(
                        current_path,
                        golden_path,
                        str(exc),
                        atol=target_spec["atol"],
                        rtol=target_spec["rtol"],
                    ),
                )
            )
        except Exception as exc:
            failures.append(
                RegressionFailure(
                    path=relative,
                    reason=f"Regression comparison failed: {exc}",
                )
            )

    return RegressionResult(
        success=not failures,
        compared_files=compared_files,
        failures=failures,
        manifest_path=str(manifest_path),
        golden_dir=str(golden_dir),
    )


def _collect_golden_targets(project_path: Path, config: dict) -> list[Path]:
    specs = _collect_golden_specs(project_path, config)
    targets: list[Path] = []
    for spec in specs:
        path = project_path / spec["path"]
        if path.exists():
            targets.append(path)
    return targets


def _collect_golden_specs(project_path: Path, config: dict) -> list[dict]:
    configured = config.get("golden_metrics", [])
    specs: list[dict] = []
    if isinstance(configured, list) and configured:
        for item in configured:
            if not isinstance(item, dict):
                continue
            raw_path = str(item.get("path", "")).strip()
            if not raw_path:
                continue
            specs.append(
                {
                    "path": raw_path,
                    "atol": float(item.get("atol", DEFAULT_ATOL)),
                    "rtol": float(item.get("rtol", DEFAULT_RTOL)),
                }
            )
        return specs

    data_root = project_path / "results" / "data"
    if not data_root.exists():
        return []

    for path in sorted(data_root.rglob("*")):
        if not path.is_file():
            continue
        if "golden" in path.parts:
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        specs.append(
            {
                "path": str(path.relative_to(project_path)).replace("\\", "/"),
                "atol": DEFAULT_ATOL,
                "rtol": DEFAULT_RTOL,
            }
        )
    return specs


def _compare_tables(current_path: Path, golden_path: Path, *, atol: float, rtol: float) -> None:
    current = _load_table(current_path)
    golden = _load_table(golden_path)
    assert_frame_equal(
        current,
        golden,
        check_dtype=False,
        check_exact=False,
        atol=atol,
        rtol=rtol,
    )


def _load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported golden dataset type: {path.suffix}")


def _value_at_label(df: pd.DataFrame, row_label: object, col: str) -> object:
    value = df.loc[row_label, col]
    if isinstance(value, pd.Series):
        return value.iloc[0]
    return value


def _build_diff_summary(
    current_path: Path,
    golden_path: Path,
    assertion_message: str,
    *,
    atol: float,
    rtol: float = DEFAULT_RTOL,
) -> str:
    try:
        current = _load_table(current_path)
        golden = _load_table(golden_path)
    except Exception:
        return assertion_message.splitlines()[0]

    if list(current.columns) != list(golden.columns):
        return f"Column mismatch: current={list(current.columns)} golden={list(golden.columns)}"
    if len(current) != len(golden):
        return f"Row count mismatch: current={len(current)} golden={len(golden)}"

    for col in current.columns:
        if pd.api.types.is_numeric_dtype(current[col]) and pd.api.types.is_numeric_dtype(golden[col]):
            diff = (current[col] - golden[col]).abs()
            threshold = atol + rtol * golden[col].abs()
            exceed = diff > threshold
            if exceed.fillna(False).any():
                row = diff.where(exceed).fillna(0).idxmax()
                return (
                    f"First numeric drift at row={row}, column='{col}', "
                    f"current={_value_at_label(current, row, col)!r}, "
                    f"golden={_value_at_label(golden, row, col)!r}"
                )
            continue
        mismatch = current[col].astype(str) != golden[col].astype(str)
        if mismatch.any():
            row = mismatch.idxmax()
            return (
                f"First value drift at row={row}, column='{col}', "
                f"current={_value_at_label(current, row, col)!r}, "
                f"golden={_value_at_label(golden, row, col)!r}"
            )

    first_line = assertion_message.splitlines()[0] if assertion_message else "Unknown regression diff"
    return first_line


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
