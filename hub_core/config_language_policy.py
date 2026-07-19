"""Language-policy normalization shared by config validation and orchestration."""

from __future__ import annotations

from collections.abc import Mapping

_CURRENT_STRUCTURE_CONTRACT = "figops-project-v1.1"
ALLOWED_LANGUAGE_POLICY_MODES = frozenset({"advisory", "enforce"})


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

    structure = config.get("structure", {}) if isinstance(config, Mapping) else {}
    current_contract = (
        isinstance(structure, Mapping) and structure.get("contract") == _CURRENT_STRUCTURE_CONTRACT
    )
    default_mode = "advisory" if current_contract else "enforce"
    mode = str(raw.get("mode", default_mode)).strip().lower() or default_mode
    default_analysis = "auto" if current_contract else "r"
    default_plot = "auto" if current_contract else "python"
    analysis_lang = normalize_lang_func(raw.get("analysis_lang", default_analysis)) or default_analysis
    plot_lang = normalize_lang_func(raw.get("plot_lang", default_plot)) or default_plot
    if "allow_nonstandard" in raw:
        allow_nonstandard = bool(raw.get("allow_nonstandard"))
    else:
        allow_nonstandard = mode == "advisory"
    return {
        "analysis_lang": analysis_lang,
        "plot_lang": plot_lang,
        "allow_nonstandard": allow_nonstandard,
        "mode": mode,
        "compatibility": not current_contract,
    }
