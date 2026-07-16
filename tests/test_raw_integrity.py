import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from hub_core.config_parser import validate_config
from hub_core.mcp import GraphHubMCPServer


def _config(mode: str | None = "warn") -> dict:
    raw_integrity = {
        "manifest": "raw/.raw_manifest.json",
        "paths": ["raw/"],
    }
    if mode is not None:
        raw_integrity["mode"] = mode
    return {
        "project": {"name": "Raw Integrity Demo"},
        "visual_style": {"target_format": "nature"},
        "data_contract": {"raw_integrity": raw_integrity, "require_figure_traceability": False},
        "figures": [
            {
                "id": "fig1",
                "script": "plot.py",
                "inputs": ["raw/"],
                "output": "results/fig1.png",
            }
        ],
    }


def _write_raw(project_dir: Path, rel_path: str, contents: str) -> Path:
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def _write_config(project_dir: Path, config: dict) -> None:
    (project_dir / "project_config.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


class RawIntegritySealVerifyTest(unittest.TestCase):
    def test_seal_then_verify_unchanged_raw_is_ok(self):
        from hub_core.raw_integrity import seal_raw_integrity, verify_raw_integrity

        with tempfile.TemporaryDirectory(prefix="graphhub_raw_integrity_") as tmpdir:
            project_dir = Path(tmpdir)
            config = _config()
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,2\n")

            seal_result = seal_raw_integrity(project_dir, config)
            verify_result = verify_raw_integrity(project_dir, config)

        self.assertTrue(seal_result["ok"])
        self.assertTrue(verify_result["ok"])
        self.assertEqual(verify_result["modified"], [])
        self.assertEqual(verify_result["added"], [])
        self.assertEqual(verify_result["removed"], [])

    def test_modified_raw_file_is_detected_and_strict_validation_fails(self):
        from hub_core.raw_integrity import seal_raw_integrity, verify_raw_integrity

        with tempfile.TemporaryDirectory(prefix="graphhub_raw_integrity_") as tmpdir:
            project_dir = Path(tmpdir)
            config = _config(mode="strict")
            _write_config(project_dir, config)
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,2\n")
            seal_raw_integrity(project_dir, config)
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,99\n")
            server = GraphHubMCPServer(research_root=project_dir.parent)

            verify_result = verify_raw_integrity(project_dir, config)
            validated = server.call_tool(
                "figops.validate_project",
                {"project_path": project_dir.name},
            )["structuredContent"]

        self.assertFalse(verify_result["ok"])
        self.assertEqual(verify_result["modified"], ["raw/data.csv"])
        self.assertFalse(validated["valid"])
        self.assertTrue(any("raw_integrity drift" in error for error in validated["config_errors"]))

    def test_added_raw_file_is_detected_and_warn_validation_stays_valid(self):
        from hub_core.raw_integrity import seal_raw_integrity, verify_raw_integrity

        with tempfile.TemporaryDirectory(prefix="graphhub_raw_integrity_") as tmpdir:
            project_dir = Path(tmpdir)
            config = _config(mode="warn")
            _write_config(project_dir, config)
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,2\n")
            seal_raw_integrity(project_dir, config)
            _write_raw(project_dir, "raw/new.csv", "x,y\n3,4\n")
            server = GraphHubMCPServer(research_root=project_dir.parent)

            verify_result = verify_raw_integrity(project_dir, config)
            validated = server.call_tool(
                "figops.validate_project",
                {"project_path": project_dir.name},
            )["structuredContent"]

        self.assertFalse(verify_result["ok"])
        self.assertEqual(verify_result["added"], ["raw/new.csv"])
        self.assertTrue(validated["valid"])
        self.assertTrue(any("raw_integrity drift" in warning for warning in validated["warnings"]))

    def test_drift_fails_validation_by_default_for_module_when_mode_absent(self):
        from hub_core.raw_integrity import seal_raw_integrity

        with tempfile.TemporaryDirectory(prefix="graphhub_raw_integrity_") as tmpdir:
            project_dir = Path(tmpdir)
            config = _config(mode=None)
            _write_config(project_dir, config)
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,2\n")
            seal_raw_integrity(project_dir, config)
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,99\n")
            server = GraphHubMCPServer(research_root=project_dir.parent)

            validated = server.call_tool(
                "figops.validate_project",
                {"project_path": project_dir.name},
            )["structuredContent"]

        self.assertFalse(validated["valid"])
        self.assertTrue(any("raw_integrity drift" in error for error in validated["config_errors"]))

    def test_explicit_warn_opt_out_keeps_module_raw_drift_advisory(self):
        from hub_core.raw_integrity import seal_raw_integrity

        with tempfile.TemporaryDirectory(prefix="graphhub_raw_integrity_") as tmpdir:
            project_dir = Path(tmpdir)
            config = _config(mode="warn")
            _write_config(project_dir, config)
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,2\n")
            seal_raw_integrity(project_dir, config)
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,99\n")
            server = GraphHubMCPServer(research_root=project_dir.parent)

            validated = server.call_tool(
                "figops.validate_project",
                {"project_path": project_dir.name},
            )["structuredContent"]

        self.assertTrue(validated["valid"])
        self.assertTrue(any("raw_integrity drift" in warning for warning in validated["warnings"]))

    def test_unsealed_raw_integrity_fails_module_default_strict_mode(self):
        with tempfile.TemporaryDirectory(prefix="graphhub_raw_integrity_") as tmpdir:
            project_dir = Path(tmpdir)
            config = _config(mode=None)
            _write_config(project_dir, config)
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,2\n")
            server = GraphHubMCPServer(research_root=project_dir.parent)

            validated = server.call_tool(
                "figops.validate_project",
                {"project_path": project_dir.name},
            )["structuredContent"]

        self.assertFalse(validated["valid"])
        self.assertTrue(any("requires a valid seal" in error for error in validated["config_errors"]))
        self.assertFalse(validated["raw_integrity_status"]["sealed"])

    def test_master_raw_drift_is_not_enforced_by_module_default(self):
        from hub_core.raw_integrity import seal_raw_integrity

        with tempfile.TemporaryDirectory(prefix="graphhub_raw_integrity_") as tmpdir:
            project_dir = Path(tmpdir)
            config = _config(mode=None)
            config["project"]["role"] = "master"
            config["figures"] = []
            config["modules"] = ["modules/experiment_a"]
            _write_config(project_dir, config)
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,2\n")
            seal_raw_integrity(project_dir, config)
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,99\n")
            server = GraphHubMCPServer(research_root=project_dir.parent)

            validated = server.call_tool(
                "figops.validate_project",
                {"project_path": project_dir.name},
            )["structuredContent"]

        self.assertTrue(validated["valid"])
        self.assertFalse(any("raw_integrity drift" in error for error in validated["config_errors"]))

    def test_removed_raw_file_is_detected(self):
        from hub_core.raw_integrity import seal_raw_integrity, verify_raw_integrity

        with tempfile.TemporaryDirectory(prefix="graphhub_raw_integrity_") as tmpdir:
            project_dir = Path(tmpdir)
            config = _config()
            raw_path = _write_raw(project_dir, "raw/data.csv", "x,y\n1,2\n")
            seal_raw_integrity(project_dir, config)
            raw_path.unlink()

            verify_result = verify_raw_integrity(project_dir, config)

        self.assertFalse(verify_result["ok"])
        self.assertEqual(verify_result["removed"], ["raw/data.csv"])

    def test_seal_verify_round_trip_is_stable(self):
        from hub_core.raw_integrity import seal_raw_integrity, verify_raw_integrity

        with tempfile.TemporaryDirectory(prefix="graphhub_raw_integrity_") as tmpdir:
            project_dir = Path(tmpdir)
            config = _config()
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,2\n")

            first = seal_raw_integrity(project_dir, config)
            second = seal_raw_integrity(project_dir, config)
            verify_result = verify_raw_integrity(project_dir, config)

        self.assertEqual(first["files"], second["files"])
        self.assertTrue(verify_result["ok"])


class RawIntegrityConfigValidationTest(unittest.TestCase):
    def test_config_without_raw_integrity_is_unchanged(self):
        config = {
            "project": {"name": "No Raw Integrity Demo"},
            "visual_style": {"target_format": "nature"},
        }

        self.assertEqual(validate_config(config), [])

    def test_invalid_mode_and_traversal_paths_fail_validation(self):
        config = _config(mode="enforce")
        config["data_contract"]["raw_integrity"]["manifest"] = "../raw_manifest.json"
        config["data_contract"]["raw_integrity"]["paths"] = ["/tmp/raw", "../raw"]

        errors = validate_config(config)

        combined = " ".join(errors)
        self.assertIn("data_contract.raw_integrity.mode", combined)
        self.assertIn("manifest", combined)
        self.assertIn("paths[1]", combined)
        self.assertIn("paths[2]", combined)


class RawIntegrityMCPInspectTest(unittest.TestCase):
    def test_inspect_project_surfaces_raw_integrity_status(self):
        from hub_core.raw_integrity import seal_raw_integrity

        with tempfile.TemporaryDirectory(prefix="graphhub_raw_integrity_") as tmpdir:
            root = Path(tmpdir)
            project_dir = root / "module"
            project_dir.mkdir()
            _write_raw(project_dir, "raw/data.csv", "x,y\n1,2\n")
            config_path = project_dir / "project_config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "project:",
                        "  name: Raw Integrity Inspect Demo",
                        "data_contract:",
                        "  raw_integrity:",
                        "    manifest: raw/.raw_manifest.json",
                        "    mode: warn",
                        "    paths: [raw/]",
                        "visual_style:",
                        "  target_format: nature",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            seal_raw_integrity(project_dir, _config(mode="warn"))
            server = GraphHubMCPServer(research_root=root)

            result = server.call_tool(
                "figops.inspect_project",
                {"project_path": "module"},
            )["structuredContent"]

        status = result["raw_integrity_status"]
        self.assertTrue(status["configured"])
        self.assertTrue(status["sealed"])
        self.assertTrue(status["ok"])
        self.assertEqual(status["modified"], [])


def _write_manifest(project_dir: Path, files: dict[str, str]) -> None:
    manifest = project_dir / "raw" / ".raw_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "_metadata": {"sealed_at": "2026-07-15T00:00:00+00:00", "algorithm": "sha256"},
                **files,
            }
        ),
        encoding="utf-8",
    )


def test_strict_graph_rejects_vacuous_seal_unless_no_raw_inputs(tmp_path: Path) -> None:
    from hub_core.raw_integrity import verify_raw_integrity

    raw_config = _config(mode="strict")
    _write_raw(tmp_path, "raw/data.csv", "x,y\n1,2\n")
    _write_manifest(tmp_path, {})

    rejected = verify_raw_integrity(tmp_path, raw_config)

    assert rejected["ok"] is False
    assert any("at least one valid local raw manifest entry" in error for error in rejected["errors"])

    synthetic_config = _config(mode="strict")
    synthetic_config["data_contract"]["raw_integrity"]["paths"] = []
    synthetic_config["data_contract"]["raw_integrity"]["no_raw_inputs"] = {
        "type": "no_raw_inputs",
        "reason": "The producer generates a deterministic calibration grid.",
    }
    synthetic_config["figures"][0]["inputs"] = []
    (tmp_path / "raw" / ".raw_manifest.json").unlink()

    accepted = verify_raw_integrity(tmp_path, synthetic_config)

    assert accepted["ok"] is True
    assert accepted["sealed"] is False
    assert accepted["no_raw_inputs"] is True

    for malformed in ([], {"type": "no_raw_inputs", "reason": ""}):
        invalid_config = _config(mode="strict")
        invalid_config["data_contract"]["raw_integrity"]["paths"] = []
        invalid_config["data_contract"]["raw_integrity"]["no_raw_inputs"] = malformed
        invalid_config["figures"][0]["inputs"] = []
        invalid = verify_raw_integrity(tmp_path, invalid_config)
        assert invalid["ok"] is False
        assert any("no_raw_inputs" in error for error in invalid["errors"])


def test_strict_raw_integrity_rejects_missing_configured_path(tmp_path: Path) -> None:
    from hub_core.raw_integrity import verify_raw_integrity

    result = verify_raw_integrity(tmp_path, _config(mode="strict"))

    assert result["ok"] is False
    assert any("configured path does not exist" in error for error in result["errors"])


def test_strict_raw_integrity_rejects_bad_digest_and_noncanonical_member(tmp_path: Path) -> None:
    from hub_core.raw_integrity import verify_raw_integrity

    _write_raw(tmp_path, "raw/data.csv", "x,y\n1,2\n")
    _write_manifest(tmp_path, {"raw\\data.csv": "A" * 64, "raw/data.csv": "A" * 64})

    result = verify_raw_integrity(tmp_path, _config(mode="strict"))

    assert result["ok"] is False
    assert any("canonical" in error for error in result["errors"])
    assert any("64 lowercase hex" in error for error in result["errors"])


def test_strict_raw_integrity_rejects_duplicate_manifest_members(tmp_path: Path) -> None:
    from hub_core.raw_integrity import verify_raw_integrity

    raw = _write_raw(tmp_path, "raw/data.csv", "x,y\n1,2\n")
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    manifest = tmp_path / "raw" / ".raw_manifest.json"
    manifest.write_text(
        '{"_metadata":{"sealed_at":"2026-07-15T00:00:00+00:00","algorithm":"sha256"},'
        f'"raw/data.csv":"{digest}","raw/data.csv":"{digest}"}}',
        encoding="utf-8",
    )

    result = verify_raw_integrity(tmp_path, _config(mode="strict"))

    assert result["ok"] is False
    assert any("duplicate JSON object key" in error for error in result["errors"])


def test_strict_manifest_membership_is_derived_from_declared_graph(tmp_path: Path) -> None:
    from hub_core.raw_integrity import seal_raw_integrity, verify_raw_integrity

    used = _write_raw(tmp_path, "raw/used.csv", "x,y\n1,2\n")
    _write_raw(tmp_path, "raw/not-a-dependency.csv", "x,y\n3,4\n")
    config = _config(mode="strict")
    config["figures"][0]["inputs"] = ["raw/used.csv"]

    sealed = seal_raw_integrity(tmp_path, config)
    verified = verify_raw_integrity(tmp_path, config)

    assert sealed["files"] == {"raw/used.csv": hashlib.sha256(used.read_bytes()).hexdigest()}
    assert verified["ok"] is True
    assert verified["dependency_graph"]["raw_members"] == ["raw/used.csv"]


def test_external_raw_requires_allowed_root_version_and_sha() -> None:
    from hub_core.external_raw import ExternalRawError, validate_external_raw_descriptors

    valid = {
        "id": "instrument-export-2026-07-15",
        "uri": "gdrive://lab/exports/run-042.csv",
        "allowed_root": "lab-exports",
        "version": "etag-042",
        "sha256": "a" * 64,
    }
    descriptor = validate_external_raw_descriptors([valid])[0]
    assert descriptor.id == valid["id"]
    assert descriptor.sha256 == valid["sha256"]

    for missing in ("allowed_root", "version", "sha256"):
        malformed = dict(valid)
        malformed.pop(missing)
        with unittest.TestCase().assertRaises(ExternalRawError):
            validate_external_raw_descriptors([malformed])
