from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from hub_core import data_contract_io


class _FakePandas:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict]] = []

    def read_csv(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return "frame"


def test_large_csv_uses_one_direct_parse_without_chunk_concat(tmp_path: Path) -> None:
    source = tmp_path / "large.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    pandas = _FakePandas()
    messages: list[str] = []

    with patch.object(data_contract_io, "CSV_LARGE_FILE_WARNING_THRESHOLD_BYTES", 1):
        result = data_contract_io.read_csv_safe(source, pandas, log_func=messages.append)

    assert result == "frame"
    assert len(pandas.calls) == 1
    assert pandas.calls[0][1] == {"encoding": "utf-8-sig"}
    assert "full dataframe materialization" in messages[0]
    assert "chunk-concat" in messages[0]
