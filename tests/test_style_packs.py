from hub_core.config_parser import ALLOWED_TARGET_FORMATS
from themes.style_packs import (
    PUBLIC_CORE,
    list_style_packs,
    private_or_internal_style_packs,
    validate_style_pack_registry,
)


def test_style_pack_registry_covers_allowed_target_formats() -> None:
    assert validate_style_pack_registry() == []


def test_style_pack_registry_is_public_core_only() -> None:
    packs = list_style_packs()

    assert private_or_internal_style_packs() == []
    assert {pack["visibility"] for pack in packs} == {PUBLIC_CORE}


def test_public_core_style_pack_exposes_all_runtime_formats() -> None:
    packs = list_style_packs()
    target_formats = {target_format for pack in packs for target_format in pack["target_formats"]}
    profiles = {profile for pack in packs for profile in pack["profiles"]}

    assert target_formats == ALLOWED_TARGET_FORMATS
    assert profiles == {"baseline"}
