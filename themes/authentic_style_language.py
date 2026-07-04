from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict

from themes.style_profiles import get_render_style_tokens


type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class AuthenticStyleLanguageMetadata(TypedDict):
    matrix_source: str
    matrix_track: str
    rationale_category: str
    official_claim: bool
    rationale: str
    source_note: str
    claim_boundary: str
    observed_visual_language: list[str]


class AuthenticStyleCandidateDelta(TypedDict):
    token: str
    current_value: JsonValue
    candidate_value: JsonValue
    delta_kind: str
    rationale_category: str
    source_note: str
    claim_boundary: str
    apply_by_default: bool


class AuthenticStyleCandidateDeltas(TypedDict):
    schema_version: str
    target_format: str
    candidate_deltas: list[AuthenticStyleCandidateDelta]
    descriptive_observations: list[str]
    official_claim: bool


class CandidateDeltaSpec(TypedDict):
    token: str
    candidate_value: JsonValue
    delta_kind: str
    rationale_category: str
    source_note: str


StyleLanguageMetadataValue = str | bool | Sequence[str]
MATRIX_SOURCE_PATH: Final = (
    Path(__file__).resolve().parent.parent / "docs" / "specs" / "2026-07-04-journal-visual-language-matrix.json"
)
AUTHENTIC_STYLE_LANGUAGE_MATRIX_SOURCE: Final = MATRIX_SOURCE_PATH.as_posix()
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
CANDIDATE_CLAIM_BOUNDARY: Final = (
    "Candidate visual-language delta only; not applied by default and not an official publisher-compliance claim."
)
CANDIDATE_DELTA_SPECS: Final[Mapping[str, tuple[CandidateDeltaSpec, ...]]] = {
    "nature": (
        {
            "token": "main_line_width",
            "candidate_value": 1.05,
            "delta_kind": "decrease_pt",
            "rationale_category": "observed_visual_language",
            "source_note": "2026-07-04 candidate from Nature sparse graph treatment observation; measured against current FigOps token only.",
        },
        {
            "token": "violin_width",
            "candidate_value": 0.5,
            "delta_kind": "decrease_fraction",
            "rationale_category": "heuristic_publication_convention",
            "source_note": "2026-07-04 candidate for less dominant distribution marks; heuristic, not a publisher rule.",
        },
    ),
    "science": (
        {
            "token": "main_marker_size",
            "candidate_value": 2.8,
            "delta_kind": "decrease_pt",
            "rationale_category": "observed_visual_language",
            "source_note": "2026-07-04 candidate from compact 57 mm Science canvas observation; measured against current FigOps token only.",
        },
        {
            "token": "error_cap_size",
            "candidate_value": 1.6,
            "delta_kind": "decrease_pt",
            "rationale_category": "heuristic_publication_convention",
            "source_note": "2026-07-04 candidate for dense small-column error bars; heuristic, not a publisher rule.",
        },
    ),
    "acs": (
        {
            "token": "main_marker_edge_width",
            "candidate_value": 0.6,
            "delta_kind": "increase_pt",
            "rationale_category": "heuristic_publication_convention",
            "source_note": "2026-07-04 candidate for clearer non-color-only symbol boundaries in chemistry-style plots.",
        },
    ),
    "rsc": (),
    "elsevier": (
        {
            "token": "main_marker_size",
            "candidate_value": 3.8,
            "delta_kind": "increase_pt",
            "rationale_category": "observed_visual_language",
            "source_note": "2026-07-04 candidate from broad 90 mm Elsevier canvas observation; measured against current FigOps token only.",
        },
    ),
    "wiley": (),
    "cell": (
        {
            "token": "timeseries_line_width",
            "candidate_value": 0.9,
            "delta_kind": "increase_pt",
            "rationale_category": "heuristic_publication_convention",
            "source_note": "2026-07-04 candidate for biomedical time-series readability; heuristic, not a publisher rule.",
        },
    ),
}


@dataclass(frozen=True, slots=True)
class AuthenticStyleLanguageMetadataError(RuntimeError):
    target_format: str

    def __str__(self) -> str:
        return f"Malformed authentic style-language metadata for {self.target_format}"


def get_authentic_style_language_metadata(target_format: str) -> AuthenticStyleLanguageMetadata:
    target_key = target_format.strip().lower()
    _require_public_track(target_key)
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


def get_authentic_style_candidate_deltas(target_format: str) -> AuthenticStyleCandidateDeltas:
    target_key = target_format.strip().lower()
    _require_public_track(target_key)
    tokens, _metadata = get_render_style_tokens(target_key, "baseline")
    candidate_deltas = [
        _candidate_delta(spec, tokens)
        for spec in CANDIDATE_DELTA_SPECS[target_key]
    ]
    return {
        "schema_version": "authentic_style_candidate_deltas/1",
        "target_format": target_key,
        "candidate_deltas": candidate_deltas,
        "descriptive_observations": _observed_visual_language(target_key),
        "official_claim": False,
    }


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


def _candidate_delta(spec: CandidateDeltaSpec, tokens: Mapping[str, JsonValue]) -> AuthenticStyleCandidateDelta:
    token = spec["token"]
    return {
        "token": token,
        "current_value": tokens[token],
        "candidate_value": spec["candidate_value"],
        "delta_kind": spec["delta_kind"],
        "rationale_category": spec["rationale_category"],
        "source_note": spec["source_note"],
        "claim_boundary": CANDIDATE_CLAIM_BOUNDARY,
        "apply_by_default": False,
    }


def _require_public_track(target_format: str) -> None:
    if target_format not in PUBLIC_JOURNAL_TRACKS:
        raise AuthenticStyleLanguageMetadataError(target_format)


def _observed_visual_language(target_format: str) -> list[str]:
    matrix = json.loads(MATRIX_SOURCE_PATH.read_text(encoding="utf-8"))
    tracks = matrix["public_tracks"]
    track = tracks[target_format]
    observed_items = track["observed_visual_language"]
    return [item["item"] for item in observed_items]
