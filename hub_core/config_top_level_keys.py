"""Top-level config-key typo detection helpers."""

from __future__ import annotations

KNOWN_TOP_LEVEL_CONFIG_KEYS = {
    "assemblies",
    "canonical_docs",
    "comparison",
    "data_contract",
    "diagrams",
    "environment",
    "execution",
    "external_raw",
    "experimental_conditions",
    "figures",
    "folder_roles",
    "golden_metrics",
    "language_policy",
    "modules",
    "pipeline",
    "presets",
    "project",
    "raw_integrity",
    "regression",
    "sample_registry",
    "schema_version",
    "structure",
    "sweep",
    "visual_style",
}


def top_level_key_fingerprint(key: str) -> str:
    return "".join(ch.lower() for ch in key if ch.isalnum())


def levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, 1):
        current = [left_index]
        for right_index, right_char in enumerate(right, 1):
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def top_level_key_suggestion(raw_key: object) -> str | None:
    if not isinstance(raw_key, str) or raw_key in KNOWN_TOP_LEVEL_CONFIG_KEYS:
        return None

    fingerprint = top_level_key_fingerprint(raw_key)
    for known_key in sorted(KNOWN_TOP_LEVEL_CONFIG_KEYS):
        if fingerprint == top_level_key_fingerprint(known_key):
            return known_key

    candidates = []
    raw_lower = raw_key.lower()
    for known_key in KNOWN_TOP_LEVEL_CONFIG_KEYS:
        distance = levenshtein_distance(raw_lower, known_key.lower())
        if distance <= 2:
            candidates.append((distance, known_key))
    if not candidates:
        return None
    return sorted(candidates)[0][1]


def validate_top_level_key_near_misses(errors: list[str], config: dict) -> None:
    for key in config:
        suggestion = top_level_key_suggestion(key)
        if suggestion is not None:
            errors.append(f"Unknown top-level key '{key}' — did you mean '{suggestion}'?")
