from hub_core import data_contract, data_contract_semantics
from hub_core import data_contract_semantic_units as units


def _append_check(checks, **payload):
    if checks is not None:
        checks.append(payload)


def _append_failed_check(checks, **payload):
    payload.setdefault("status", "failed")
    _append_check(checks, **payload)


def test_unit_signature_helpers_are_reexported_through_existing_modules():
    assert data_contract_semantics._parse_unit_signature is units.parse_unit_signature
    assert data_contract_semantics._format_unit_signature is units.format_unit_signature
    assert data_contract._parse_unit_signature is units.parse_unit_signature
    assert data_contract._format_unit_signature is units.format_unit_signature


def test_unit_signature_helpers_parse_and_format_compound_units():
    signature = units.parse_unit_signature("ohm*cm^2/cm")

    assert signature == {"ohm": 1, "cm": 1}
    assert units.format_unit_signature(signature) == "cm*ohm"


def test_unit_compatibility_helper_skips_when_pint_is_unavailable():
    messages = []

    result = units.check_unit_compatibility(
        "current",
        "mA",
        "A",
        pint_available=False,
        ureg=None,
        log_func=messages.append,
        dimensionality_error=Exception,
    )

    assert result == "skip"
    assert any("pint not installed" in message for message in messages)


def test_unit_coherence_validator_records_passed_calculation_check():
    checks = []

    errors, rows = units.check_unit_coherence_constraint(
        "resistivity",
        {
            "expected_unit": "ohm*cm",
            "terms": [
                {"column": "resistance", "unit": "ohm"},
                {"column": "area", "unit": "cm^2"},
                {"column": "thickness", "unit": "cm", "exponent": -1},
            ],
        },
        {"resistance": "resistance", "area": "area", "thickness": "thickness"},
        calculation_checks=checks,
        csv_rel_path="results/data/summary.csv",
        source_config_path="project_config.yaml",
        append_calculation_check=_append_check,
        append_failed_calculation_check=_append_failed_check,
    )

    assert errors == []
    assert rows == []
    assert checks[0]["name"] == "unit_coherence"
    assert checks[0]["status"] == "passed"


def test_axis_unit_validator_records_conversion_factor():
    checks = []

    errors, rows = units.check_axis_unit_constraint(
        "current",
        {"data_unit": "mA", "display_unit": "A"},
        calculation_checks=checks,
        csv_rel_path="results/data/axis.csv",
        source_config_path="project_config.yaml",
        unit_checker=lambda *_args: (0.001, "mA", "A"),
        append_calculation_check=_append_check,
        append_failed_calculation_check=_append_failed_check,
        json_safe_value=lambda value: value,
    )

    assert errors == []
    assert rows == []
    assert checks[0]["name"] == "axis_unit"
    assert checks[0]["violations"][0]["conversion_factor"] == 0.001
