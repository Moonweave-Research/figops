import pandas as pd

from hub_core import data_contract, data_contract_semantics
from hub_core import data_contract_semantic_ordering as ordering


def test_monotonic_helper_is_reexported_through_existing_modules():
    assert data_contract_semantics._check_monotonic_constraint is ordering.check_monotonic_constraint
    assert data_contract._check_monotonic_constraint is ordering.check_monotonic_constraint


def test_monotonic_helper_reports_equal_value_for_strict_increase():
    series = pd.Series([0, 1, 1], index=["r0", "r1", "r2"])

    error, rows = ordering.check_monotonic_constraint(series, "time", "increasing", 10)

    assert "1 monotonic violation" in error
    assert rows == [
        {
            "row": "r2",
            "column": "time",
            "value": "1",
            "expected": "monotonic increasing; previous value 1",
            "violation_type": "monotonic_violation",
        }
    ]


def test_grouped_monotonic_wrapper_uses_existing_compatibility_helpers():
    df = pd.DataFrame({"sample": ["A", "A", "B", "B"], "time": [0, 1, 2, 1]})
    checks = []

    errors, rows = data_contract_semantics._check_monotonic_within_group_constraint(
        df,
        df["time"],
        "time",
        {"group_by": ["sample"], "mode": "increasing"},
        {"sample": "sample", "time": "time"},
        10,
        calculation_checks=checks,
        csv_rel_path="results/data/summary.csv",
        source_config_path="project_config.yaml",
    )

    assert errors == ["Column 'time': 1 group(s) failed monotonic_within_group=increasing"]
    assert rows[0]["violation_type"] == "monotonic_within_group"
    assert checks[0]["name"] == "monotonic_within_group"
    assert checks[0]["violations"][0]["group"] == {"sample": "B"}
