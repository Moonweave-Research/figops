"""Multi-channel encoding profiles for publication figures."""

MARKER_CYCLE: list[str] = ["o", "s", "^", "D", "v", "<", ">", "p"]
HATCH_CYCLE: list[str] = ["//", "\\\\", "||", "--", "++", "xx", "oo", "**"]
LINESTYLE_CYCLE: list[str] = ["-", "--", "-.", ":"]

_ALIASES: dict[str, str] = {
    "premium": "resistance_premium",
    "resistance": "resistance_premium",
}

_PROFILES: dict[str, dict] = {
    "baseline": {
        "main_marker_size": 4.0,
        "main_linewidth": 1.0,
        "error_capsize": 3.0,
    },
    "resistance_premium": {
        "main_marker_size": 5.0,
        "main_linewidth": 1.5,
        "error_capsize": 4.0,
    },
}


def get_series_style(index: int) -> dict[str, str]:
    return {
        "marker": MARKER_CYCLE[index % len(MARKER_CYCLE)],
        "linestyle": LINESTYLE_CYCLE[index % len(LINESTYLE_CYCLE)],
        "hatch": HATCH_CYCLE[index % len(HATCH_CYCLE)],
    }


def resolve_profile_name(profile_name: str | None = None) -> str:
    if profile_name is None:
        return "baseline"
    resolved = _ALIASES.get(profile_name, profile_name)
    return resolved if resolved in _PROFILES else "baseline"


def list_profiles() -> list[str]:
    return list(_PROFILES.keys())


def get_profile_tokens(profile_name: str | None = None) -> tuple[dict, str]:
    key = resolve_profile_name(profile_name)
    return dict(_PROFILES[key]), key


def get_profile_rc_overrides(profile_name: str | None = None) -> tuple[dict, str]:
    key = resolve_profile_name(profile_name)
    return {}, key
