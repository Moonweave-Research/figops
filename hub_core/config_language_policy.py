"""Language-policy normalization shared by config validation and orchestration."""


def normalize_lang(lang):
    if lang is None:
        return ""
    key = str(lang).strip().lower()
    if key == "py":
        return "python"
    return key


def get_language_policy(config, *, normalize_lang_func=normalize_lang):
    raw = config.get("language_policy", {})
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}

    analysis_lang = normalize_lang_func(raw.get("analysis_lang", "r")) or "r"
    plot_lang = normalize_lang_func(raw.get("plot_lang", "python")) or "python"
    allow_nonstandard = bool(raw.get("allow_nonstandard", False))
    return {
        "analysis_lang": analysis_lang,
        "plot_lang": plot_lang,
        "allow_nonstandard": allow_nonstandard,
    }
