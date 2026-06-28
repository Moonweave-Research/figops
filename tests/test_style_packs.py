from themes.style_packs import (
    INTERNAL_RESISTANCE_PROFILE,
    INTERNAL_STYLE_TARGET_FORMAT,
    list_style_packs,
    private_or_internal_style_packs,
    validate_style_pack_registry,
)


def test_style_pack_registry_covers_allowed_target_formats() -> None:
    assert validate_style_pack_registry() == []


def test_private_project_derived_styles_are_split_from_public_registry() -> None:
    packs = list_style_packs()
    by_format = {target_format: pack for pack in packs for target_format in pack["target_formats"]}

    assert INTERNAL_STYLE_TARGET_FORMAT not in by_format


def test_internal_profile_is_split_from_public_registry() -> None:
    internal_packs = private_or_internal_style_packs()

    assert internal_packs == []
    assert INTERNAL_RESISTANCE_PROFILE
