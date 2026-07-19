"""Style pack registry for productization and release-boundary checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from hub_core.config_style import ALLOWED_TARGET_FORMATS
from hub_core.config_style import INTERNAL_STYLE_TARGET_FORMAT as INTERNAL_STYLE_TARGET_FORMAT

PUBLIC_CORE = "public_core"
INTERNAL = "internal"
PRIVATE = "private"
ALLOWED_VISIBILITIES = {PUBLIC_CORE, INTERNAL, PRIVATE}
INTERNAL_RESISTANCE_PROFILE = "_".join(("resistance", "premium"))


@dataclass(frozen=True)
class StylePack:
    name: str
    visibility: str
    target_formats: tuple[str, ...]
    profiles: tuple[str, ...]
    release_note: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["target_formats"] = list(self.target_formats)
        payload["profiles"] = list(self.profiles)
        return payload


STYLE_PACKS: tuple[StylePack, ...] = (
    StylePack(
        name="journal_core",
        visibility=PUBLIC_CORE,
        target_formats=("acs", "cell", "default", "elsevier", "nature", "neutral", "rsc", "science", "wiley"),
        profiles=("baseline",),
        release_note="Generic journal and default formats suitable for a future public core.",
    ),
)


def list_style_packs() -> list[dict[str, object]]:
    return [pack.to_dict() for pack in STYLE_PACKS]


def private_or_internal_style_packs() -> list[dict[str, object]]:
    return [pack.to_dict() for pack in STYLE_PACKS if pack.visibility != PUBLIC_CORE]


def validate_style_pack_registry() -> list[str]:
    errors: list[str] = []
    seen_formats: set[str] = set()
    for pack in STYLE_PACKS:
        if pack.visibility not in ALLOWED_VISIBILITIES:
            errors.append(f"Style pack {pack.name} has invalid visibility {pack.visibility!r}.")
        for target_format in pack.target_formats:
            if target_format not in ALLOWED_TARGET_FORMATS:
                errors.append(f"Style pack {pack.name} references unknown target_format {target_format!r}.")
            if target_format in seen_formats:
                errors.append(f"target_format {target_format!r} appears in more than one style pack.")
            seen_formats.add(target_format)
    return errors
