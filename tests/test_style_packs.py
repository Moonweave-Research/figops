from themes.style_packs import (
    PUBLIC_CORE,
    list_style_packs,
    private_or_internal_style_packs,
    validate_style_pack_registry,
)


def test_style_pack_registry_covers_allowed_target_formats() -> None:
    assert validate_style_pack_registry() == []


def test_private_project_derived_styles_are_not_public_core() -> None:
    packs = list_style_packs()
    by_format = {target_format: pack for pack in packs for target_format in pack["target_formats"]}

    assert by_format["nature_surfur"]["visibility"] != PUBLIC_CORE


def test_resistance_premium_profile_is_internal() -> None:
    internal_packs = private_or_internal_style_packs()

    assert any("resistance_premium" in pack["profiles"] for pack in internal_packs)
