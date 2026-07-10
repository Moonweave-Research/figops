from __future__ import annotations

import hashlib
import json
import sys
from types import SimpleNamespace

import pytest

import orchestrator
from hub_core.mcp import McpServerConfig


def test_init_scaffold_runs_before_runtime_preflight(monkeypatch, tmp_path):
    project_dir = tmp_path / "smoke_project"

    monkeypatch.setattr(orchestrator, "get_hub_path", lambda: str(tmp_path / "hub"))
    monkeypatch.setattr(orchestrator, "get_research_root", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "configure_logging", lambda verbose=False: None)
    monkeypatch.setattr(orchestrator, "ui_panel", lambda *args, **kwargs: None)

    def fail_preflight(*args, **kwargs):
        raise AssertionError("runtime preflight should not run for --init")

    monkeypatch.setattr(orchestrator, "run_preflight_check", fail_preflight)
    monkeypatch.setattr(
        orchestrator,
        "scaffold_project",
        lambda target, hub_path: {"project_name": "smoke_project", "project_dir": str(project_dir)},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["orchestrator.py", "--init", "--project", str(project_dir)],
    )

    assert orchestrator.main() == 0


def test_missing_project_reports_path_error_before_runtime_preflight(monkeypatch, tmp_path):
    # Given: a project selector that cannot resolve to a directory.
    monkeypatch.setattr(orchestrator, "get_hub_path", lambda: str(tmp_path / "hub"))
    monkeypatch.setattr(orchestrator, "get_research_root", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "configure_logging", lambda verbose=False: None)
    monkeypatch.setattr(
        orchestrator,
        "run_preflight_check",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("preflight must follow path validation")),
    )
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--project", "missing-project", "--step", "plot"])

    # When: running the missing-project invocation.
    result = orchestrator.main()

    # Then: the path diagnostic wins instead of an unrelated R check.
    assert result == 1


def test_orchestrator_does_not_leak_inferred_roots_into_later_mcp_defaults(monkeypatch, tmp_path):
    # Given: no operator-provided root environment and an orchestration call with temporary inferred roots.
    monkeypatch.delenv("RESEARCH_HUB_PATH", raising=False)
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    monkeypatch.setattr(orchestrator, "get_hub_path", lambda: str(tmp_path / "dead-hub"))
    monkeypatch.setattr(orchestrator, "get_research_root", lambda: str(tmp_path / "dead-root"))
    monkeypatch.setattr(orchestrator, "configure_logging", lambda verbose=False: None)
    monkeypatch.setattr(orchestrator, "list_projects", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--list-projects"])

    # When: the orchestrator returns and MCP resolves its own default configuration.
    result = orchestrator.main()
    mcp_config = McpServerConfig.from_env()

    # Then: the transient inferred roots did not become global MCP policy.
    assert result == 0
    assert mcp_config.hub_path is None
    assert mcp_config.research_root is None


def test_readable_invalid_yaml_persists_invalid_attempt_provenance(monkeypatch, tmp_path):
    # Given: a project config that exists and is readable but is syntactically invalid.
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    config_path = project_dir / "project_config.yaml"
    raw_config = "project: [unterminated\n"
    config_path.write_text(raw_config, encoding="utf-8")
    written: dict[str, object] = {}
    monkeypatch.setattr(orchestrator, "get_hub_path", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "get_research_root", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "configure_logging", lambda verbose=False: None)
    monkeypatch.setattr(
        orchestrator,
        "run_preflight_check",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("invalid YAML must precede runtime preflight")),
    )
    monkeypatch.setattr(
        orchestrator,
        "dump_pipeline_failure",
        lambda *_args, **_kwargs: str(project_dir / "failure.json"),
    )
    monkeypatch.setattr(
        orchestrator,
        "write_execution_log",
        lambda *_args, **kwargs: (written.update(kwargs), (str(project_dir / "execution.jsonl"), {}))[1],
    )
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--project", str(project_dir), "--step", "plot"])

    # When: parsing the invalid project config.
    result = orchestrator.main()

    # Then: the persisted attempt identifies invalid-but-readable configuration.
    attempt = written["attempt_provenance"]
    assert result == 1
    assert attempt["config_status"] == "invalid"
    assert attempt["raw_config_sha256"] == hashlib.sha256(config_path.read_bytes()).hexdigest()
    assert "raw_config_sha256" not in attempt["unavailable_fields"]


@pytest.mark.parametrize("failure_kind", ("master", "legacy", "research_ops"))
def test_resolved_project_early_failures_persist_attempt_provenance(monkeypatch, tmp_path, failure_kind):
    # Given: a validly resolved project that fails an early policy gate.
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    config_path = project_dir / "project_config.yaml"
    config_path.write_text("project: {name: demo}\n", encoding="utf-8")
    config = {"project": {"name": "demo"}}
    written: dict[str, object] = {}
    dumped: dict[str, object] = {}
    monkeypatch.setattr(orchestrator, "get_hub_path", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "get_research_root", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "configure_logging", lambda verbose=False: None)
    monkeypatch.setattr(orchestrator, "load_config", lambda _path: (config, str(config_path), "config-hash"))
    monkeypatch.setattr(orchestrator, "project_role", lambda _config: "module")
    monkeypatch.setattr(orchestrator, "project_status", lambda _config: "active")
    monkeypatch.setattr(orchestrator, "master_execution_error", lambda _config: "master disabled")
    monkeypatch.setattr(orchestrator, "validate_research_ops_contract", lambda *_args: {"errors": [], "warnings": []})
    match failure_kind:
        case "master":
            monkeypatch.setattr(orchestrator, "project_role", lambda _config: "master")
        case "legacy":
            monkeypatch.setattr(orchestrator, "project_status", lambda _config: "legacy")
        case "research_ops":
            monkeypatch.setattr(
                orchestrator,
                "validate_research_ops_contract",
                lambda *_args: {"errors": ["research contract failure"], "warnings": []},
            )
    monkeypatch.setattr(
        orchestrator,
        "run_preflight_check",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("early gate must precede preflight")),
    )
    monkeypatch.setattr(
        orchestrator,
        "dump_pipeline_failure",
        lambda *_args, **kwargs: (dumped.update(kwargs), str(project_dir / "failure.json"))[1],
    )
    monkeypatch.setattr(
        orchestrator,
        "write_execution_log",
        lambda *_args, **kwargs: (written.update(kwargs), (str(project_dir / "execution.jsonl"), {}))[1],
    )
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--project", str(project_dir), "--step", "plot"])

    # When: the resolved project hits the policy gate.
    result = orchestrator.main()

    # Then: both persistence surfaces carry one valid-config attempt record.
    assert result == 1
    assert written["attempt_provenance"] == dumped["context"]["attempt_provenance"]
    assert written["attempt_provenance"]["config_status"] == "valid"
    assert written["failure_stage"] == "CONFIG"


@pytest.mark.parametrize(
    ("config_kind", "expected_status"),
    (("invalid", "invalid"), ("missing", "missing")),
)
def test_inject_fingerprint_resolved_config_failures_persist_attempt(
    monkeypatch,
    tmp_path,
    config_kind,
    expected_status,
):
    # Given: an injection target that resolves to a project with an invalid or missing config.
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    if config_kind == "invalid":
        (project_dir / "project_config.yaml").write_text("project: [unterminated\n", encoding="utf-8")
    written: dict[str, object] = {}
    monkeypatch.setattr(orchestrator, "get_hub_path", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "get_research_root", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "configure_logging", lambda verbose=False: None)
    monkeypatch.setattr(
        orchestrator,
        "dump_pipeline_failure",
        lambda *_args, **_kwargs: str(project_dir / "failure.json"),
    )
    monkeypatch.setattr(
        orchestrator,
        "write_execution_log",
        lambda *_args, **kwargs: (written.update(kwargs), (str(project_dir / "execution.jsonl"), {}))[1],
    )
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--inject-fingerprint", "--project", str(project_dir)])

    # When: the injection command cannot load its resolved project config.
    result = orchestrator.main()

    # Then: the failure is persisted with an explicit config contract.
    assert result == 1
    assert written["attempt_provenance"]["config_status"] == expected_status
    if config_kind == "missing":
        assert "raw_config_sha256" in written["attempt_provenance"]["unavailable_fields"]
    else:
        assert written["attempt_provenance"]["raw_config_sha256"]


def test_successful_project_run_emits_final_configured_attempt_provenance(monkeypatch, tmp_path):
    # Given: a successful resolved project run with a readable configuration file.
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    config_path = project_dir / "project_config.yaml"
    config_path.write_text("project: {name: demo}\n", encoding="utf-8")
    config = {"project": {"name": "demo"}, "pipeline": {"analysis": []}}
    adapters = SimpleNamespace(
        prefetcher=SimpleNamespace(),
        athena=SimpleNamespace(run_health_hook=lambda *_args: None, run_draft_bridge=lambda *_args: None),
    )
    emitted: list[str] = []
    monkeypatch.setattr(orchestrator, "get_hub_path", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "get_research_root", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "configure_logging", lambda verbose=False: None)
    monkeypatch.setattr(orchestrator, "ui_print", lambda message, **_kwargs: emitted.append(str(message)))
    monkeypatch.setattr(orchestrator, "load_config", lambda _path: (config, str(config_path), "config-hash"))
    monkeypatch.setattr(orchestrator, "project_role", lambda _config: "module")
    monkeypatch.setattr(orchestrator, "project_status", lambda _config: "active")
    monkeypatch.setattr(orchestrator, "validate_research_ops_contract", lambda *_args: {"errors": [], "warnings": []})
    monkeypatch.setattr(orchestrator, "run_preflight_check", lambda **_kwargs: True)
    monkeypatch.setattr(orchestrator, "select_adapters", lambda _config: adapters)
    monkeypatch.setattr(
        orchestrator,
        "validate_environment_locks",
        lambda **_kwargs: {"ok": True, "strict": False, "python_lock": {}, "r_lock": {}},
    )
    monkeypatch.setattr(orchestrator, "load_build_state", lambda _path: ({}, str(project_dir / ".build_state.json")))
    monkeypatch.setattr(orchestrator, "print_provenance", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(orchestrator, "validate_data_contract_preflight", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(orchestrator, "validate_data_contract", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(orchestrator, "run_plots", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(orchestrator, "save_build_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(orchestrator, "embed_figures_fingerprint", lambda **_kwargs: 0)
    monkeypatch.setattr(orchestrator, "write_execution_log", lambda *_args, **_kwargs: ("execution.jsonl", {}))
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--project", str(project_dir), "--step", "plot"])

    # When: completing the normal plot pipeline.
    result = orchestrator.main()

    # Then: the final emitted attempt has the readable config contract and original identity.
    attempts = [json.loads(item) for item in emitted if item.startswith("{")]
    assert result == 0
    assert attempts[-1]["config_status"] == "valid"
    assert attempts[-1]["raw_config_sha256"] == hashlib.sha256(config_path.read_bytes()).hexdigest()
    assert attempts[0]["attempt_id"] == attempts[-1]["attempt_id"]


def test_failed_all_step_preflight_does_not_start_analysis(monkeypatch, tmp_path):
    # Given: a selected project whose runtime preflight cannot pass.
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    config_path = project_dir / "project_config.yaml"
    config_path.write_text("project: {name: demo}\n", encoding="utf-8")
    config = {
        "project": {"name": "demo"},
        "pipeline": {"analysis": [{"script": "analysis.R", "lang": "r"}]},
    }
    written: dict[str, object] = {}
    monkeypatch.setattr(orchestrator, "get_hub_path", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "get_research_root", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "configure_logging", lambda verbose=False: None)
    monkeypatch.setattr(orchestrator, "load_config", lambda _path: (config, str(config_path), "config-hash"))
    monkeypatch.setattr(orchestrator, "validate_research_ops_contract", lambda *_args: {"errors": [], "warnings": []})
    monkeypatch.setattr(orchestrator, "run_preflight_check", lambda **_kwargs: False)
    monkeypatch.setattr(
        orchestrator,
        "run_analysis",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("analysis must not run after preflight failure")
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "dump_pipeline_failure",
        lambda *_args, **_kwargs: str(project_dir / "failure.json"),
    )
    monkeypatch.setattr(
        orchestrator,
        "write_execution_log",
        lambda *_args, **kwargs: (written.update(kwargs), (str(project_dir / "execution.jsonl"), {}))[1],
    )
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--project", str(project_dir), "--step", "all"])

    # When: the all-step pipeline reaches its selective preflight.
    result = orchestrator.main()

    # Then: it returns the preflight failure and persists the one attempt record.
    assert result == 1
    assert written["failure_stage"] == "VALIDATE"
    assert written["attempt_provenance"]["surface"] == "cli"


def test_failed_data_preflight_does_not_start_all_step_analysis(monkeypatch, tmp_path):
    # Given: runtime preflight passes but the data contract preflight fails.
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    config_path = project_dir / "project_config.yaml"
    config_path.write_text("project: {name: demo}\n", encoding="utf-8")
    config = {"project": {"name": "demo"}, "pipeline": {"analysis": []}}
    adapters = SimpleNamespace(
        prefetcher=SimpleNamespace(),
        athena=SimpleNamespace(run_health_hook=lambda *_args: None, run_draft_bridge=lambda *_args: None),
    )
    monkeypatch.setattr(orchestrator, "get_hub_path", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "get_research_root", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "configure_logging", lambda verbose=False: None)
    monkeypatch.setattr(orchestrator, "load_config", lambda _path: (config, str(config_path), "config-hash"))
    monkeypatch.setattr(orchestrator, "validate_research_ops_contract", lambda *_args: {"errors": [], "warnings": []})
    monkeypatch.setattr(orchestrator, "run_preflight_check", lambda **_kwargs: True)
    monkeypatch.setattr(orchestrator, "select_adapters", lambda _config: adapters)
    monkeypatch.setattr(
        orchestrator,
        "validate_environment_locks",
        lambda **_kwargs: {"ok": True, "strict": False, "python_lock": {}, "r_lock": {}},
    )
    monkeypatch.setattr(orchestrator, "load_build_state", lambda _path: ({}, str(project_dir / ".build_state.json")))
    monkeypatch.setattr(orchestrator, "print_provenance", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(orchestrator, "validate_data_contract_preflight", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        orchestrator,
        "run_analysis",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("analysis must not overwrite data failure")),
    )
    monkeypatch.setattr(
        orchestrator,
        "dump_pipeline_failure",
        lambda *_args, **_kwargs: str(project_dir / "failure.json"),
    )
    monkeypatch.setattr(
        orchestrator,
        "write_execution_log",
        lambda *_args, **_kwargs: (str(project_dir / "execution.jsonl"), {}),
    )
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--project", str(project_dir), "--step", "all"])

    # When: executing every requested pipeline stage.
    result = orchestrator.main()

    # Then: the validation failure is terminal before analysis can mutate state.
    assert result == 1


def test_inject_fingerprint_uses_reproducible_timestamp(monkeypatch, tmp_path):
    # Given: a standalone fingerprint injection with a deterministic timestamp source.
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    config_path = project_dir / "project_config.yaml"
    config_path.write_text("project: {name: demo}\n", encoding="utf-8")
    config = {"project": {"name": "demo"}, "execution": {}}
    captured: dict[str, object] = {}
    emitted: list[str] = []
    monkeypatch.setattr(orchestrator, "get_hub_path", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "get_research_root", lambda: str(tmp_path))
    monkeypatch.setattr(orchestrator, "configure_logging", lambda verbose=False: None)
    monkeypatch.setattr(orchestrator, "ui_print", lambda message, **_kwargs: emitted.append(str(message)))
    monkeypatch.setattr(orchestrator, "load_config", lambda _path: (config, str(config_path), "config-hash"))
    monkeypatch.setattr(orchestrator, "embed_figures_fingerprint", lambda **kwargs: captured.update(kwargs) or 0)
    monkeypatch.setattr("hub_core.provenance.reproducible_timestamp", lambda: "1970-01-01T00:00:01+00:00")
    monkeypatch.setattr(sys, "argv", ["orchestrator.py", "--inject-fingerprint", "--project", str(project_dir)])

    # When: injecting the fingerprint.
    result = orchestrator.main()

    # Then: no wall-clock timestamp reaches the embedded metadata.
    assert result == 0
    assert captured["timestamp"] == "1970-01-01T00:00:01+00:00"
    attempts = [json.loads(item) for item in emitted if item.startswith("{")]
    assert attempts[-1]["config_status"] == "valid"
    assert attempts[-1]["raw_config_sha256"] == hashlib.sha256(config_path.read_bytes()).hexdigest()
