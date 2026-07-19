from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from hub_core.external_raw import ExternalRawError
from hub_core.external_raw_execution import (
    bind_launcher_allowed_roots,
    external_raw_signatures,
    materialize_external_raw_inputs,
)
from hub_core.mcp import FigOpsMCPServer
from hub_core.process_runner import run_analysis
from hub_core.provenance import hash_input_files


class RecordingPrefetcher:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def ensure_local(self, paths: list[str]) -> None:
        self.paths.extend(paths)


def _config(digest: str, *, access_class: str | None = None) -> dict:
    descriptor = {
        "id": "instrument-export",
        "path": "run.csv",
        "allowed_root": "lab-exports",
        "version": "etag-42",
        "sha256": digest,
    }
    if access_class:
        descriptor["access_class"] = access_class
    return {
        "project": {"name": "external-raw-integration"},
        "environment": {},
        "execution": {"python": sys.executable},
        "language_policy": {"allow_nonstandard": True},
        "external_raw": [descriptor],
        "pipeline": {
            "analysis": [
                {
                    "script": "analysis.py",
                    "lang": "python",
                    "inputs": ["external_raw:instrument-export"],
                    "outputs": [],
                    "cache": False,
                }
            ]
        },
        "data_contract": {},
    }


def test_materialization_uses_launcher_authority_and_disposable_runtime(tmp_path: Path) -> None:
    project = tmp_path / "project"
    allowed = tmp_path / "lab-exports"
    runtime = tmp_path / "runtime"
    project.mkdir()
    allowed.mkdir()
    runtime.mkdir()
    source = allowed / "run.csv"
    source.write_bytes(b"x,y\n1,2\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    prefetcher = RecordingPrefetcher()

    resolved = materialize_external_raw_inputs(
        project_root=project,
        config=_config(digest, access_class="restricted"),
        declarations=["external_raw:instrument-export"],
        prefetcher=prefetcher,
        allowed_roots={"lab-exports": allowed},
        runtime_root=runtime,
    )

    assert prefetcher.paths == [str(source.resolve())]
    assert len(resolved) == 1
    assert resolved[0].path.read_bytes() == source.read_bytes()
    assert resolved[0].path.is_relative_to(runtime)
    assert not resolved[0].path.is_relative_to(project)
    assert "locator" not in resolved[0].provenance_metadata()
    assert resolved[0].provenance_metadata()["content_included"] is False


def test_process_runner_resolves_external_reference_before_windows_path_handling(tmp_path: Path) -> None:
    project = tmp_path / "project"
    allowed = tmp_path / "lab-exports"
    runtime = tmp_path / "runtime"
    project.mkdir()
    allowed.mkdir()
    runtime.mkdir()
    (project / "analysis.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    source = allowed / "run.csv"
    source.write_bytes(b"x,y\n1,2\n")
    config = _config(hashlib.sha256(source.read_bytes()).hexdigest())
    prefetcher = RecordingPrefetcher()

    with (
        patch.dict(os.environ, {"RESEARCH_HUB_RUNTIME_ROOT": str(runtime)}),
        patch("hub_core.process_runner.run_command", return_value=True) as run_command,
    ):
        result = run_analysis(
            str(project),
            config,
            {},
            str(runtime / "state.json"),
            "config-hash",
            prefetcher=prefetcher,
            external_raw_allowed_roots={"lab-exports": allowed},
        )

    assert result is True
    inputs = run_command.call_args.kwargs["additional_env"]["GRAPH_HUB_INPUTS"].split(os.pathsep)
    assert len(inputs) == 1
    materialized = Path(inputs[0])
    assert materialized.is_relative_to(runtime)
    assert materialized != source
    assert materialized.read_bytes() == source.read_bytes()


def test_hash_mismatch_fails_before_producer_execution(tmp_path: Path) -> None:
    project = tmp_path / "project"
    allowed = tmp_path / "lab-exports"
    runtime = tmp_path / "runtime"
    project.mkdir()
    allowed.mkdir()
    runtime.mkdir()
    (project / "analysis.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    (allowed / "run.csv").write_bytes(b"changed\n")
    prefetcher = RecordingPrefetcher()

    with (
        patch.dict(os.environ, {"RESEARCH_HUB_RUNTIME_ROOT": str(runtime)}),
        patch("hub_core.process_runner.run_command", return_value=True) as run_command,
    ):
        result = run_analysis(
            str(project),
            _config("0" * 64),
            {},
            str(runtime / "state.json"),
            "config-hash",
            prefetcher=prefetcher,
            external_raw_allowed_roots={"lab-exports": allowed},
        )

    assert result is False
    run_command.assert_not_called()


def test_missing_launcher_authority_is_not_inferred_from_project_descriptor(tmp_path: Path) -> None:
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    project.mkdir()
    runtime.mkdir()
    source = tmp_path / "lab-exports" / "run.csv"
    source.parent.mkdir()
    source.write_bytes(b"x\n1\n")
    config = _config(hashlib.sha256(source.read_bytes()).hexdigest())

    try:
        materialize_external_raw_inputs(
            project_root=project,
            config=config,
            declarations=["external_raw:instrument-export"],
            prefetcher=RecordingPrefetcher(),
            allowed_roots=None,
            runtime_root=runtime,
        )
    except ExternalRawError as exc:
        assert "not launcher-approved" in str(exc)
    else:
        raise AssertionError("project descriptor unexpectedly granted its own filesystem authority")


def test_cache_and_provenance_bind_opaque_source_identity_without_content(tmp_path: Path) -> None:
    digest = "a" * 64
    config = _config(digest, access_class="restricted")
    signatures = external_raw_signatures(config, ["external_raw:instrument-export"])

    assert signatures == [
        {
            "declaration": "external_raw:instrument-export",
            "artifact_id": "instrument-export",
            "allowed_root": "lab-exports",
            "version": "etag-42",
            "sha256": digest,
            "locator_kind": "path",
            "locator_identity_sha256": hashlib.sha256(b"path\0run.csv").hexdigest(),
            "access_class": "restricted",
            "content_included": False,
        }
    ]
    assert hash_input_files(
        tmp_path,
        ["external_raw:instrument-export"],
        config=config,
    ) == {"external_raw:instrument-export": digest[:12]}


def test_launcher_sequence_root_ids_are_unique_directory_names(tmp_path: Path) -> None:
    first = tmp_path / "a" / "lab-exports"
    second = tmp_path / "b" / "lab-exports"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    try:
        bind_launcher_allowed_roots([first, second])
    except ExternalRawError as exc:
        assert "ambiguous" in str(exc)
    else:
        raise AssertionError("duplicate launcher root identifiers were accepted")


def test_uri_requires_an_explicit_materialization_adapter(tmp_path: Path) -> None:
    project = tmp_path / "project"
    runtime = tmp_path / "runtime"
    allowed = tmp_path / "lab-exports"
    project.mkdir()
    runtime.mkdir()
    allowed.mkdir()
    config = _config("a" * 64)
    descriptor = config["external_raw"][0]
    descriptor.pop("path")
    descriptor["uri"] = "gdrive://lab/exports/run.csv"

    try:
        materialize_external_raw_inputs(
            project_root=project,
            config=config,
            declarations=["external_raw:instrument-export"],
            prefetcher=RecordingPrefetcher(),
            allowed_roots={"lab-exports": allowed},
            runtime_root=runtime,
        )
    except ExternalRawError as exc:
        assert "requires an enabled materialization adapter" in str(exc)
    else:
        raise AssertionError("URI input executed without a capable adapter")


def _external_inspection_server(
    tmp_path: Path,
    *,
    descriptor_sha256: str,
) -> tuple[FigOpsMCPServer, Path, Path]:
    research = tmp_path / "research"
    project = research / "project"
    public_root = tmp_path / "public-root"
    secret_root = tmp_path / "secret-root"
    runtime = tmp_path / "runtime"
    project.mkdir(parents=True)
    public_root.mkdir()
    secret_root.mkdir()
    public_file = public_root / "shared.csv"
    secret_file = secret_root / "shared.csv"
    public_file.write_text("label,value\nPUBLIC,1\n", encoding="utf-8")
    secret_file.write_text("label,value\nTOP_SECRET,999\n", encoding="utf-8")
    (project / "raw").mkdir()
    (project / "raw" / "local.csv").write_text("x\n1\n", encoding="utf-8")
    (project / "project_config.yaml").write_text(
        "project:\n  name: External inspection\n"
        "data_contract:\n  csv_checks:\n    - path: raw/local.csv\n"
        "external_raw:\n"
        "  - id: public-sample\n"
        "    path: shared.csv\n"
        "    allowed_root: public-root\n"
        "    version: v1\n"
        f"    sha256: {descriptor_sha256}\n"
        "    access_class: public\n",
        encoding="utf-8",
    )
    server = FigOpsMCPServer(
        config={
            "research_root": research,
            "runtime_root": runtime,
            "allowed_data_roots": (public_root, secret_root),
            "write_tools_enabled": False,
            "surface_profile": "v2",
        }
    )
    return server, public_file, secret_file


def _structured_call(server: FigOpsMCPServer, arguments: dict) -> dict:
    response = server.call_tool("figops.inspect_data", arguments)
    assert json.loads(response["content"][0]["text"]) == response["structuredContent"]
    return response["structuredContent"]


def test_inspect_data_binds_descriptor_to_exact_allowed_root_and_sha(tmp_path: Path) -> None:
    public_bytes = b"label,value\r\nPUBLIC,1\r\n" if os.name == "nt" else b"label,value\nPUBLIC,1\n"
    server, public_file, secret_file = _external_inspection_server(
        tmp_path,
        descriptor_sha256=hashlib.sha256(public_bytes).hexdigest(),
    )

    attack = _structured_call(
        server,
        {
            "data_path": str(secret_file),
            "external_raw_id": "public-sample",
            "include_samples": True,
            "sample_rows": 1,
        },
    )
    legitimate = _structured_call(
        server,
        {
            "data_path": str(public_file),
            "external_raw_id": "public-sample",
            "include_samples": True,
            "sample_rows": 1,
        },
    )

    assert "access_policy" in attack, attack
    assert attack["access_policy"]["mode"] == "metadata_only"
    assert attack["samples"] == []
    assert "TOP_SECRET" not in json.dumps(attack)
    assert legitimate["status_code"] == "INSPECTION_VALUES_AVAILABLE"
    assert legitimate["access_policy"]["materialized_sha256_verified"] is True
    assert legitimate["samples"] == [["PUBLIC", "1"]]


def test_invalid_external_descriptor_never_grants_sample_authority(tmp_path: Path) -> None:
    server, public_file, _ = _external_inspection_server(
        tmp_path,
        descriptor_sha256="not-a-sha256",
    )

    result = _structured_call(
        server,
        {
            "data_path": str(public_file),
            "external_raw_id": "public-sample",
            "include_samples": True,
            "sample_rows": 1,
        },
    )

    assert "access_policy" in result, result
    assert result["access_policy"]["mode"] == "metadata_only"
    assert result["samples"] == []
    assert "PUBLIC" not in json.dumps(result)


def test_mcp_project_render_consumes_verified_external_raw_from_runtime(tmp_path: Path) -> None:
    research = tmp_path / "research"
    project = research / "project"
    allowed = tmp_path / "lab-exports"
    runtime = tmp_path / "runtime"
    (project / "hub_scripts").mkdir(parents=True)
    (project / "results" / "data").mkdir(parents=True)
    (project / "results" / "data" / "local.csv").write_text("x,y\n0,1\n", encoding="utf-8")
    allowed.mkdir()
    source = allowed / "run.csv"
    source.write_bytes(b"x,y\n1,2\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (project / "hub_scripts" / "plot.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "from PIL import Image\n"
        "inputs = [Path(p) for p in os.environ['GRAPH_HUB_INPUTS'].split(os.pathsep)]\n"
        "external = next(p for p in inputs if p.name.startswith('instrument-export-'))\n"
        "assert external.read_bytes() == b'x,y\\n1,2\\n'\n"
        "assert not str(external).startswith(os.environ['PROJECT_ROOT'])\n"
        "Path('results/figures').mkdir(parents=True, exist_ok=True)\n"
        "Image.new('RGB', (64, 48), 'navy').save('results/figures/Fig1.png')\n",
        encoding="utf-8",
    )
    (project / "project_config.yaml").write_text(
        "project:\n  name: MCP external render\n"
        "visual_style:\n  target_format: nature\n  profile: baseline\n"
        "sample_registry:\n  - sample_id: S1\n"
        "experimental_conditions:\n  conditions:\n    - id: condition_a\n"
        "data_contract:\n  csv_checks:\n    - path: results/data/local.csv\n"
        "external_raw:\n"
        "  - id: instrument-export\n"
        "    path: run.csv\n"
        "    allowed_root: lab-exports\n"
        "    version: v1\n"
        f"    sha256: {digest}\n"
        "    access_class: restricted\n"
        "figures:\n"
        "  - id: Fig1\n"
        "    script: hub_scripts/plot.py\n"
        "    inputs: [external_raw:instrument-export]\n"
        "    output: results/figures/Fig1.png\n"
        "    claim: External input render fixture.\n"
        "    samples: [S1]\n"
        "    conditions: [condition_a]\n",
        encoding="utf-8",
    )
    server = FigOpsMCPServer(
        config={
            "research_root": research,
            "runtime_root": runtime,
            "allowed_data_roots": (allowed,),
            "write_tools_enabled": True,
            "surface_profile": "compatibility",
        }
    )

    response = server.call_tool(
        "figops.render_project_figure",
        {"project_path": str(project), "figure_id": "Fig1", "job_id": "external-e2e"},
    )["structuredContent"]

    assert response["status"] in {"ok", "warning"}, response.get("errors") or response
    materialized = list((runtime / "external_raw").rglob("instrument-export-*.csv"))
    assert len(materialized) == 1
    assert materialized[0].read_bytes() == source.read_bytes()
    assert not list(project.rglob("instrument-export-*.csv"))


def test_cli_external_raw_root_grant_reaches_actual_producer(tmp_path: Path) -> None:
    research = tmp_path / "research"
    project = research / "project"
    allowed = tmp_path / "lab-exports"
    runtime = tmp_path / "runtime"
    (project / "hub_scripts" / "analysis").mkdir(parents=True)
    allowed.mkdir()
    source = allowed / "run.csv"
    source.write_bytes(b"x,y\n1,2\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (project / "hub_scripts" / "analysis" / "analyze.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "input_path = Path(os.environ['GRAPH_HUB_INPUTS'])\n"
        "assert input_path.read_bytes() == b'x,y\\n1,2\\n'\n"
        "out = Path('results/data/source/verified.txt')\n"
        "out.parent.mkdir(parents=True, exist_ok=True)\n"
        "out.write_text('verified', encoding='utf-8')\n",
        encoding="utf-8",
    )
    (project / "project_config.yaml").write_text(
        "project:\n  name: CLI external analysis\n"
        "environment: {}\n"
        f"execution:\n  python: '{sys.executable.replace(chr(92), '/')}'\n"
        "language_policy:\n  allow_nonstandard: true\n"
        "external_raw:\n"
        "  - id: instrument-export\n"
        "    path: run.csv\n"
        "    allowed_root: lab-exports\n"
        "    version: v1\n"
        f"    sha256: {digest}\n"
        "pipeline:\n  analysis:\n"
        "    - script: hub_scripts/analysis/analyze.py\n"
        "      lang: python\n"
        "      inputs: [external_raw:instrument-export]\n"
        "      outputs: [results/data/source/verified.txt]\n"
        "      cache: false\n"
        "data_contract: {}\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PROJECT_ROOT"] = str(research)
    env["RESEARCH_HUB_RUNTIME_ROOT"] = str(runtime)
    completed = subprocess.run(
        [
            sys.executable,
            "orchestrator.py",
            "--project",
            str(project),
            "--step",
            "analysis",
            "--force",
            "--external-raw-root",
            f"lab-exports={allowed}",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (project / "results" / "data" / "source" / "verified.txt").read_text(
        encoding="utf-8"
    ) == "verified"
    assert list((runtime / "external_raw").rglob("instrument-export-*.csv"))
