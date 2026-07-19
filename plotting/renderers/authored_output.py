from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from plotting.utils import label_transformation_evidence


def write_authored_output_evidence(points: list[dict], spec: Any) -> None:
    """Persist exact display mappings when the render orchestrator requests it."""
    sidecar = str(os.environ.get("AUTHORED_OUTPUT_EVIDENCE_OUT") or "").strip()
    if not sidecar:
        return
    values: list[object] = []
    for point in points:
        values.append(point.get("x", ""))
        for label_field in ("label", "series", "facet"):
            if point.get(label_field) not in (None, ""):
                values.append(point[label_field])
    evidence = label_transformation_evidence(
        values,
        label_map=spec.label_map,
        label_transform=spec.label_transform,
        compress_labels=spec.compress_labels,
    )
    claim_candidates = []
    for index, annotation in enumerate(spec.annotations or ()):
        if not isinstance(annotation, dict) or annotation.get("annotation_kind") != "literal":
            continue
        text = str(annotation.get("text") or "")
        ledger_text = text[:512]
        claim_candidates.append(
            {
                "source": "annotation",
                "annotation_index": index,
                "text": ledger_text,
                "text_truncated": len(text) > len(ledger_text),
                "status": "unverified_literal",
                "manual_review_required": True,
            }
        )
    evidence["claim_candidates"] = claim_candidates
    sidecar_path = Path(sidecar)
    if sidecar_path.is_file():
        prior = json.loads(sidecar_path.read_text(encoding="utf-8"))
        mappings = [*prior.get("mappings", []), *evidence.get("mappings", [])]
        unique_mappings = {
            (item["original"], item["display"], item["transform"]): item for item in mappings
        }
        evidence["mappings"] = list(unique_mappings.values())
        by_display: dict[str, list[str]] = {}
        for item in evidence["mappings"]:
            by_display.setdefault(item["display"], []).append(item["original"])
        evidence["collisions"] = [
            {"display": display, "originals": sorted(set(originals))}
            for display, originals in sorted(by_display.items())
            if len(set(originals)) > 1
        ]
        ledger = [*prior.get("mutation_ledger", []), *evidence.get("mutation_ledger", [])]
        evidence["mutation_ledger"] = list(
            {item["mutation_id"]: item for item in ledger}.values()
        )
        evidence["mode"] = "mixed" if prior.get("mode") != evidence.get("mode") else evidence["mode"]
        evidence["claim_candidates"] = [
            *prior.get("claim_candidates", []),
            *evidence.get("claim_candidates", []),
        ]
    sidecar_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")


def verify_spec_calculation_evidence(spec: Any) -> None:
    """Require orchestration-bound evidence; render code never reopens caller paths."""
    if not spec.significance_markers:
        return
    for index, marker in enumerate(spec.significance_markers):
        if not isinstance(marker, dict):
            raise ValueError(f"significance_markers[{index}] must be an object")
        missing = [key for key in ("x1", "x2", "y") if key not in marker]
        if missing:
            raise ValueError(
                f"significance_markers[{index}] missing required field(s): {', '.join(missing)}"
            )
    records = getattr(spec, "calculation_evidence", ())
    if not isinstance(records, (list, tuple)) or not records:
        raise ValueError(
            "significance_markers require trusted, preverified contained calculation evidence from the orchestrator"
        )
