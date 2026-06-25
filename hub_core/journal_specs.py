"""Machine-readable journal style and preflight provenance registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Provenance = Literal[
    "official_required",
    "official_recommended",
    "publisher_rule_of_thumb",
    "graphhub_assumption",
    "internal_policy",
    "internal_project_style",
]
Enforcement = Literal["error", "warning", "advisory"]

OFFICIAL_REQUIRED: Provenance = "official_required"
OFFICIAL_RECOMMENDED: Provenance = "official_recommended"
PUBLISHER_RULE_OF_THUMB: Provenance = "publisher_rule_of_thumb"
GRAPHHUB_ASSUMPTION: Provenance = "graphhub_assumption"
INTERNAL_POLICY: Provenance = "internal_policy"
INTERNAL_PROJECT_STYLE: Provenance = "internal_project_style"

ERROR: Enforcement = "error"
WARNING: Enforcement = "warning"
ADVISORY: Enforcement = "advisory"


@dataclass(frozen=True)
class JournalToken:
    key: str
    value: object
    provenance: Provenance
    source_url: str | None
    source_note: str
    enforcement: Enforcement


@dataclass(frozen=True)
class JournalPreflightSpec:
    target_format: str
    max_width_mm: JournalToken
    min_dpi: JournalToken
    formats: JournalToken


NATURE_SOURCE = "https://www.nature.com/nature/for-authors/final-submission"
NATURE_ARTWORK_SOURCE = "https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/"
SCIENCE_SOURCE = "https://www.science.org/content/page/instructions-preparing-initial-manuscript"
ACS_SOURCE = "https://pubs.acs.org/page/4authors/submission/graphics_prep.html"
RSC_SOURCE = "https://www.rsc.org/journals-books-databases/author-and-reviewer-hub/authors-information/preparing-your-article/"
ELSEVIER_SOURCE = "https://www.elsevier.com/about/policies-and-standards/author/artwork-and-media-instructions/artwork-sizing"
WILEY_SOURCE = "https://authors.wiley.com/author-resources/Journal-Authors/Prepare/manuscript-preparation-guidelines.html/figure-preparation.html"
CELL_SOURCE = "https://www.cell.com/information-for-authors/figure-guidelines"
INTERNAL_STYLE_TARGET_FORMAT = "_".join(("nature", "surfur"))


def _token(
    key: str,
    value: object,
    provenance: Provenance,
    source_url: str | None,
    source_note: str,
    enforcement: Enforcement,
) -> JournalToken:
    return JournalToken(
        key=key,
        value=value,
        provenance=provenance,
        source_url=source_url,
        source_note=source_note,
        enforcement=enforcement,
    )


def _preflight_spec(
    target_format: str,
    *,
    max_width_mm: float,
    max_width_provenance: Provenance,
    max_width_source: str | None,
    max_width_note: str,
    min_dpi: int,
    min_dpi_provenance: Provenance,
    min_dpi_source: str | None,
    min_dpi_note: str,
    formats: set[str],
    formats_provenance: Provenance,
    formats_source: str | None,
    formats_note: str,
) -> JournalPreflightSpec:
    return JournalPreflightSpec(
        target_format=target_format,
        max_width_mm=_token(
            "max_width_mm", max_width_mm, max_width_provenance, max_width_source, max_width_note, ERROR
        ),
        min_dpi=_token("min_dpi", min_dpi, min_dpi_provenance, min_dpi_source, min_dpi_note, ERROR),
        formats=_token("formats", frozenset(formats), formats_provenance, formats_source, formats_note, ERROR),
    )


JOURNAL_PREFLIGHT_SPECS: dict[str, JournalPreflightSpec] = {
    "nature": _preflight_spec(
        "nature",
        max_width_mm=183,
        max_width_provenance=OFFICIAL_REQUIRED,
        max_width_source=NATURE_SOURCE,
        max_width_note="Nature maximum final artwork width used by the legacy preflight gate.",
        min_dpi=600,
        min_dpi_provenance=OFFICIAL_RECOMMENDED,
        min_dpi_source=NATURE_ARTWORK_SOURCE,
        min_dpi_note="Raster figure resolution floor used for submission-safe output.",
        formats={"pdf", "png", "tiff", "eps"},
        formats_provenance=OFFICIAL_RECOMMENDED,
        formats_source=NATURE_ARTWORK_SOURCE,
        formats_note="Submission-safe figure formats accepted by this preflight track.",
    ),
    INTERNAL_STYLE_TARGET_FORMAT: _preflight_spec(
        INTERNAL_STYLE_TARGET_FORMAT,
        max_width_mm=183,
        max_width_provenance=INTERNAL_PROJECT_STYLE,
        max_width_source=None,
        max_width_note="Internal Nature-derived sulfur preset; not a separate journal standard.",
        min_dpi=600,
        min_dpi_provenance=INTERNAL_PROJECT_STYLE,
        min_dpi_source=None,
        min_dpi_note="Internal preset inherits Nature-like raster safety checks.",
        formats={"pdf", "png", "tiff", "eps"},
        formats_provenance=INTERNAL_PROJECT_STYLE,
        formats_source=None,
        formats_note="Internal preset inherits Nature-like format checks; not a separate journal standard.",
    ),
    "science": _preflight_spec(
        "science",
        max_width_mm=170,
        max_width_provenance=GRAPHHUB_ASSUMPTION,
        max_width_source=SCIENCE_SOURCE,
        max_width_note="Legacy conservative cap; style tokens separately encode Science width slots.",
        min_dpi=600,
        min_dpi_provenance=OFFICIAL_RECOMMENDED,
        min_dpi_source=SCIENCE_SOURCE,
        min_dpi_note="Raster resolution floor used for line-art-safe output.",
        formats={"pdf", "png", "tiff", "eps"},
        formats_provenance=OFFICIAL_RECOMMENDED,
        formats_source=SCIENCE_SOURCE,
        formats_note="Submission-safe vector/raster formats used by this preflight track.",
    ),
    "acs": _preflight_spec(
        "acs",
        max_width_mm=171,
        max_width_provenance=GRAPHHUB_ASSUMPTION,
        max_width_source=ACS_SOURCE,
        max_width_note="Legacy conservative cap; ACS double-column width is tracked in style tokens.",
        min_dpi=600,
        min_dpi_provenance=OFFICIAL_RECOMMENDED,
        min_dpi_source=ACS_SOURCE,
        min_dpi_note="Raster resolution floor used for line-art-safe output.",
        formats={"tiff", "pdf", "png"},
        formats_provenance=INTERNAL_POLICY,
        formats_source=ACS_SOURCE,
        formats_note="Preflight-approved subset of ACS-compatible formats.",
    ),
    "rsc": _preflight_spec(
        "rsc",
        max_width_mm=176,
        max_width_provenance=GRAPHHUB_ASSUMPTION,
        max_width_source=RSC_SOURCE,
        max_width_note="Legacy conservative cap retained for compatibility.",
        min_dpi=600,
        min_dpi_provenance=OFFICIAL_RECOMMENDED,
        min_dpi_source=RSC_SOURCE,
        min_dpi_note="Raster resolution floor used for line-art-safe output.",
        formats={"tiff", "pdf", "png"},
        formats_provenance=INTERNAL_POLICY,
        formats_source=RSC_SOURCE,
        formats_note="Preflight-approved subset of RSC-compatible formats.",
    ),
    "elsevier": _preflight_spec(
        "elsevier",
        max_width_mm=190,
        max_width_provenance=PUBLISHER_RULE_OF_THUMB,
        max_width_source=ELSEVIER_SOURCE,
        max_width_note="Elsevier-style double/full-width cap used for preflight.",
        min_dpi=300,
        min_dpi_provenance=OFFICIAL_RECOMMENDED,
        min_dpi_source=ELSEVIER_SOURCE,
        min_dpi_note="Raster resolution floor used by this preflight track.",
        formats={"tiff", "pdf", "png", "eps"},
        formats_provenance=OFFICIAL_RECOMMENDED,
        formats_source=ELSEVIER_SOURCE,
        formats_note="Submission-safe vector/raster formats used by this preflight track.",
    ),
    "wiley": _preflight_spec(
        "wiley",
        max_width_mm=180,
        max_width_provenance=OFFICIAL_RECOMMENDED,
        max_width_source=WILEY_SOURCE,
        max_width_note="Wiley figure preparation guidance uses an 80-180 mm width range.",
        min_dpi=300,
        min_dpi_provenance=OFFICIAL_RECOMMENDED,
        min_dpi_source=WILEY_SOURCE,
        min_dpi_note="Wiley figure preparation guidance uses 300-600 dpi.",
        formats={"tiff", "pdf", "png", "eps", "jpg"},
        formats_provenance=OFFICIAL_RECOMMENDED,
        formats_source=WILEY_SOURCE,
        formats_note="Common Wiley-compatible figure formats accepted by this preflight track.",
    ),
    "cell": _preflight_spec(
        "cell",
        max_width_mm=174,
        max_width_provenance=OFFICIAL_RECOMMENDED,
        max_width_source=CELL_SOURCE,
        max_width_note="Cell Press double/full-width cap encoded by the style track.",
        min_dpi=300,
        min_dpi_provenance=OFFICIAL_RECOMMENDED,
        min_dpi_source=CELL_SOURCE,
        min_dpi_note="Raster resolution floor used by this preflight track.",
        formats={"tiff", "pdf", "png", "eps", "jpg"},
        formats_provenance=OFFICIAL_RECOMMENDED,
        formats_source=CELL_SOURCE,
        formats_note="Common Cell Press-compatible figure formats accepted by this preflight track.",
    ),
}

PREFLIGHT_POLICY_TOKENS: dict[str, JournalToken] = {
    "font_settings": _token(
        "font_settings",
        "embedded_non_type3_fonts",
        INTERNAL_POLICY,
        None,
        "Graph Hub checks PDF artifacts for Type3 fonts because they are fragile in publication workflows.",
        ERROR,
    ),
    "vector_file_size": _token(
        "vector_file_size",
        50 * 1024 * 1024,
        INTERNAL_POLICY,
        None,
        "Graph Hub vector artifact size guardrail for submission and MCP transport safety.",
        ERROR,
    ),
    "raster_file_size": _token(
        "raster_file_size",
        "expected_compressed_bound",
        GRAPHHUB_ASSUMPTION,
        None,
        "Graph Hub heuristic warning for unusually large raster artifacts; dense images may be legitimate.",
        ADVISORY,
    ),
    "color_mode": _token(
        "color_mode",
        "rgb_not_cmyk",
        INTERNAL_POLICY,
        None,
        "Graph Hub treats CMYK rasters as unsafe for most automated submission workflows.",
        ERROR,
    ),
}


def get_preflight_spec(target_format: str) -> JournalPreflightSpec:
    key = str(target_format or "nature").strip().lower()
    try:
        return JOURNAL_PREFLIGHT_SPECS[key]
    except KeyError as exc:
        supported = ", ".join(sorted(JOURNAL_PREFLIGHT_SPECS))
        raise ValueError(f"Unknown journal '{target_format}'. Supported: {supported}") from exc


def token_to_dict(token: JournalToken) -> dict[str, object]:
    value = sorted(token.value) if isinstance(token.value, frozenset) else token.value
    return {
        "key": token.key,
        "value": value,
        "provenance": token.provenance,
        "source_url": token.source_url,
        "source_note": token.source_note,
        "enforcement": token.enforcement,
    }


def list_preflight_tokens(target_format: str) -> list[dict[str, object]]:
    spec = get_preflight_spec(target_format)
    return [
        token_to_dict(spec.max_width_mm),
        token_to_dict(spec.min_dpi),
        token_to_dict(spec.formats),
        *(token_to_dict(token) for token in PREFLIGHT_POLICY_TOKENS.values()),
    ]


def list_supported_preflight_targets() -> list[str]:
    return sorted(JOURNAL_PREFLIGHT_SPECS)
