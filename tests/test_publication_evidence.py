from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub_core.publication_evidence import (
    MAX_READINESS_MANIFEST_BYTES,
    load_readiness_manifest,
    readiness_evidence_from_manifest,
)

SHA_A = "A" * 64
SHA_B = "b" * 64


def test_normalizes_allowlisted_manifest_without_paths() -> None:
    evidence = readiness_evidence_from_manifest(
        {
            "project_id": "project-1",
            "selected_figure": {"id": "Fig2b", "output": "results/Fig2b.png"},
            "job_root": "C:/private/runtime/job",
            "geometry_diagnostics": {
                "passed": True,
                "report_path": "C:/private/geometry.json",
                "checks": [{"id": "legend", "passed": True}],
            },
            "visual_preflight_status": {"passed": True},
            "layout_report": {"render_errors": []},
            "calculation_checks": [{"name": "range", "status": "passed"}],
            "baseline_comparison": {"status": "match"},
            "artifact_status": "created",
            "failure_stage": "",
            "style_summary": {"target_format": "nature", "profile": "baseline"},
            "provenance": {
                "config_sha256": SHA_A,
                "invalid_sha256": "short",
                "source_path": "C:/private/data.csv",
                "lock_status": {"python_lock": {"sha256": SHA_B, "exists": True}},
            },
            "secret": "not exported",
        }
    )

    assert evidence["schema_version"] == "publication_evidence/1"
    assert evidence["project_id"] == "project-1"
    assert evidence["figure_id"] == "Fig2b"
    assert evidence["geometry_diagnostics"] == {
        "passed": True,
        "checks": [{"id": "legend", "passed": True}],
    }
    assert evidence["provenance"] == {
        "config_sha256": SHA_A.lower(),
        "lock_status": {"python_lock": {"sha256": SHA_B}},
    }
    serialized = json.dumps(evidence)
    assert "C:/" not in serialized
    assert "job_root" not in evidence
    assert "secret" not in evidence


def test_direct_figure_id_takes_precedence() -> None:
    evidence = readiness_evidence_from_manifest(
        {"figure_id": "Fig1", "selected_figure": {"id": "Fig2"}}
    )
    assert evidence["figure_id"] == "Fig1"


def test_redacts_secrets_without_hiding_style_tokens() -> None:
    evidence = readiness_evidence_from_manifest(
        {
            "geometry_diagnostics": {
                "findings": [
                    {
                        "message": "password=hunter2 Bearer live-token",
                        "token": "nested-token",
                        "detail": "https://alice:password@example.test/report",
                    }
                ]
            },
            "layout_report": {
                "message": "authorization: Basic dXNlcjpwYXNz api_key=raw-key"
            },
            "style_summary": {
                "target_format": "nature",
                "font_tokens": {"title": 8.0, "axis_label": 7.0},
                "line_token": "baseline",
            },
        }
    )

    serialized = json.dumps(evidence, sort_keys=True)
    for secret in ("hunter2", "live-token", "nested-token", "alice", "password@example", "raw-key"):
        assert secret not in serialized
    assert "[REDACTED]" in serialized
    assert evidence["style_summary"]["font_tokens"] == {"title": 8.0, "axis_label": 7.0}
    assert evidence["style_summary"]["line_token"] == "baseline"


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_direct_mapping_rejects_nonfinite_numbers(number: float) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        readiness_evidence_from_manifest({"layout_report": {"ratio": number}})


@pytest.mark.parametrize(
    "manifest",
    [
        {"style_summary": {"font": Path("font.ttf")}},
        {"provenance": []},
    ],
)
def test_rejects_unsupported_or_path_bearing_evidence(manifest: dict) -> None:
    with pytest.raises((TypeError, ValueError)):
        readiness_evidence_from_manifest(manifest)


def test_sanitizes_embedded_absolute_paths_without_rejecting_diagnostics() -> None:
    evidence = readiness_evidence_from_manifest(
        {
            "layout_report": {
                "posix": "failed at /home/alice/private/Fig.png during render",
                "windows": r"failed at C:\Users\Alice\private\Fig.png during render",
                "unc": r"failed at \\server\private\share\Fig.png during render",
                "mixed": r"compare /tmp/a.png with C:\private\b.png and \\host\share\c.png",
            }
        }
    )

    report = evidence["layout_report"]
    assert report["posix"] == "failed at [PATH] during render"
    assert report["windows"] == "failed at [PATH] during render"
    assert report["unc"] == "failed at [PATH] during render"
    assert report["mixed"] == "compare [PATH] with [PATH] and [PATH]"
    serialized = json.dumps(evidence)
    for absolute_fragment in ("/home/", "/tmp/", "C:\\\\", "C:/", "\\\\\\\\server", "\\\\\\\\host"):
        assert absolute_fragment not in serialized


def test_normalizes_unambiguous_relative_backslash_paths() -> None:
    windows = readiness_evidence_from_manifest(
        {"layout_report": {"artifact": r"results\Fig.png", "message": r"press \n to continue"}}
    )
    posix = readiness_evidence_from_manifest(
        {"layout_report": {"artifact": "results/Fig.png", "message": r"press \n to continue"}}
    )

    assert windows == posix
    assert windows["layout_report"]["artifact"] == "results/Fig.png"
    assert windows["layout_report"]["message"] == r"press \n to continue"


def test_load_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text('{"artifact_status":"ok","artifact_status":"failed"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_readiness_manifest(path)


@pytest.mark.parametrize("payload", [b"[]", b"null", b'"text"'])
def test_load_rejects_non_object_json(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="JSON object"):
        load_readiness_manifest(path)


def test_load_rejects_non_utf8_json(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(b'{"name":"\xff"}')
    with pytest.raises(ValueError, match="UTF-8"):
        load_readiness_manifest(path)


def test_load_rejects_non_standard_numeric_constants(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text('{"layout_report":{"ratio":NaN}}', encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported JSON constant"):
        load_readiness_manifest(path)


def test_load_rejects_oversized_file(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    with path.open("wb") as stream:
        stream.truncate(MAX_READINESS_MANIFEST_BYTES + 1)
    with pytest.raises(ValueError, match="maximum size"):
        load_readiness_manifest(path)


def test_loads_valid_manifest(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"artifact_status": "created", "provenance": {"output_sha256": SHA_B}}),
        encoding="utf-8",
    )
    evidence = load_readiness_manifest(path)
    assert evidence == {
        "schema_version": "publication_evidence/1",
        "artifact_status": "created",
        "provenance": {"output_sha256": SHA_B},
        "provenance_coverage": {
            "status": "incomplete",
            "hashes": {"output_sha256": SHA_B},
            "missing": ["input_sha256", "config_sha256", "script_sha256", "environment_sha256"],
        },
        "artifact_integrity": {
            "schema_version": "artifact_integrity/1",
            "status": "failed",
            "entries": [],
            "errors": [
                {"code": "ARTIFACT_DECLARATION_INVALID", "message": "manifest figures must be a list"}
            ],
        },
    }
