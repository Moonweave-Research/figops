from hub_core import data_contract, data_contract_semantics
from hub_core import data_contract_semantic_units as units


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
