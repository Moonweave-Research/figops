from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from importlib.resources import files
from typing import Final, TypedDict


class AuthenticStyleLanguageMetadata(TypedDict):
    matrix_source: str
    matrix_track: str
    rationale_category: str
    official_claim: bool
    rationale: str
    source_note: str
    claim_boundary: str
    observed_visual_language: list[str]


StyleLanguageMetadataValue = str | bool | Sequence[str]
MATRIX_RESOURCE_PATH: Final = "data/journal_visual_language_matrix.json"
AUTHENTIC_STYLE_LANGUAGE_MATRIX_SOURCE: Final = f"package:themes/{MATRIX_RESOURCE_PATH}"
PUBLIC_JOURNAL_TRACKS: Final = ("nature", "science", "acs", "rsc", "elsevier", "wiley", "cell")
RATIONALES: Final[Mapping[str, str]] = {
    "nature": (
        "Metadata-only Nature visual-language hint: sparse labelled graphs, no decorative effects, "
        "and accessibility-conscious encodings, without changing render tokens."
    ),
    "science": (
        "Metadata-only Science visual-language hint: compact, high-density figures driven by the "
        "57 mm single-column width and existing compact density tokens."
    ),
    "acs": (
        "Metadata-only ACS visual-language hint: chemistry-oriented accessible graphics with clear "
        "sans-serif lettering and non-color-only encodings."
    ),
    "rsc": (
        "Metadata-only RSC visual-language hint: chemistry-publishing legibility, scale-bar awareness, "
        "and the existing higher text floor."
    ),
    "elsevier": (
        "Metadata-only Elsevier visual-language hint: broad uniform artwork and readable normal text "
        "using the existing wider 90 mm track anchors."
    ),
    "wiley": (
        "Metadata-only Wiley visual-language hint: quality-first figure handling and readable words "
        "and symbols within broad Wiley width guidance."
    ),
    "cell": (
        "Metadata-only Cell visual-language hint: biomedical canvas with existing 85/114/174 mm slots "
        "and moderate line/marker scale."
    ),
}
CLAIM_BOUNDARY: Final = "Non-official FigOps interpretation; not a latest publisher-compliance claim."


@dataclass(frozen=True, slots=True)
class AuthenticStyleLanguageMetadataError(RuntimeError):
    target_format: str

    def __str__(self) -> str:
        return f"Malformed authentic style-language metadata for {self.target_format}"


@dataclass(frozen=True, slots=True)
class AuthenticStyleLanguageMatrixMissingError(RuntimeError):
    source: str

    def __str__(self) -> str:
        return f"Missing authentic style-language matrix: {self.source}"


@dataclass(frozen=True, slots=True)
class AuthenticStyleLanguageMatrixCorruptError(RuntimeError):
    source: str
    detail: str

    def __str__(self) -> str:
        return f"Corrupt authentic style-language matrix: {self.source} ({self.detail})"


def get_authentic_style_language_metadata(target_format: str) -> AuthenticStyleLanguageMetadata:
    target_key = target_format.strip().lower()
    metadata: AuthenticStyleLanguageMetadata = {
        "matrix_source": AUTHENTIC_STYLE_LANGUAGE_MATRIX_SOURCE,
        "matrix_track": target_key,
        "rationale_category": "observed_visual_language",
        "official_claim": False,
        "rationale": RATIONALES.get(target_key, ""),
        "source_note": f"Derived from public_tracks.{target_key}.observed_visual_language in the 2026-07-04 matrix.",
        "claim_boundary": CLAIM_BOUNDARY,
        "observed_visual_language": _observed_visual_language(target_key),
    }
    if not validate_authentic_style_language_metadata(metadata):
        raise AuthenticStyleLanguageMetadataError(target_key)
    return deepcopy(metadata)


def validate_authentic_style_language_metadata(metadata: Mapping[str, StyleLanguageMetadataValue]) -> bool:
    observed_visual_language = metadata.get("observed_visual_language")
    return (
        metadata.get("matrix_source") == AUTHENTIC_STYLE_LANGUAGE_MATRIX_SOURCE
        and metadata.get("matrix_track") in PUBLIC_JOURNAL_TRACKS
        and metadata.get("rationale_category") == "observed_visual_language"
        and metadata.get("official_claim") is False
        and bool(metadata.get("rationale"))
        and bool(metadata.get("source_note"))
        and bool(metadata.get("claim_boundary"))
        and isinstance(observed_visual_language, Sequence)
        and not isinstance(observed_visual_language, str)
        and all(isinstance(item, str) and bool(item) for item in observed_visual_language)
    )


def _observed_visual_language(target_format: str) -> list[str]:
    resource = files("themes").joinpath(MATRIX_RESOURCE_PATH)
    try:
        matrix_text = resource.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AuthenticStyleLanguageMatrixMissingError(AUTHENTIC_STYLE_LANGUAGE_MATRIX_SOURCE) from exc
    except UnicodeDecodeError as exc:
        raise AuthenticStyleLanguageMatrixCorruptError(
            AUTHENTIC_STYLE_LANGUAGE_MATRIX_SOURCE,
            "resource is not valid UTF-8",
        ) from exc

    try:
        matrix = json.loads(matrix_text)
        observed_items = matrix["public_tracks"][target_format]["observed_visual_language"]
        observed_visual_language = [item["item"] for item in observed_items]
    except json.JSONDecodeError as exc:
        raise AuthenticStyleLanguageMatrixCorruptError(
            AUTHENTIC_STYLE_LANGUAGE_MATRIX_SOURCE,
            f"invalid JSON at line {exc.lineno} column {exc.colno}",
        ) from exc
    except (KeyError, TypeError) as exc:
        raise AuthenticStyleLanguageMatrixCorruptError(
            AUTHENTIC_STYLE_LANGUAGE_MATRIX_SOURCE,
            "missing expected public track metadata",
        ) from exc

    if not all(isinstance(item, str) and bool(item) for item in observed_visual_language):
        raise AuthenticStyleLanguageMatrixCorruptError(
            AUTHENTIC_STYLE_LANGUAGE_MATRIX_SOURCE,
            "observed visual-language items must be non-empty strings",
        )
    return observed_visual_language
