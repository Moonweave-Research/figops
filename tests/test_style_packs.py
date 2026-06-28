from themes.style_packs import (
    INTERNAL_RESISTANCE_PROFILE,
    INTERNAL_STYLE_TARGET_FORMAT,
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

    assert by_format[INTERNAL_STYLE_TARGET_FORMAT]["visibility"] != PUBLIC_CORE


def test_internal_profile_is_not_public_core() -> None:
    internal_packs = private_or_internal_style_packs()

    assert any(INTERNAL_RESISTANCE_PROFILE in pack["profiles"] for pack in internal_packs)
