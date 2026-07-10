"""
[Graph_making_hub]/orchestrator.py
==================================
🚀 연구 프로젝트 통합 실행기 (Research Project Orchestrator)

[역할 / Role]
- 개별 연구 프로젝트의 `project_config.yaml`을 읽어 분석/플롯 파이프라인 자동화
- 프로젝트 간 격리된 환경에서도 표준 인터페이스(CSV)를 통해 시각화 연결
- 테마나 템플릿 변경 시 전체 프로젝트의 그래프 일괄 재생성 기능

[출처 / Source]
  Refactored for Research Central Architecture (Modularized)
  Migration date: 2026-03-05
"""

import argparse
import hashlib
import os
import shlex
import sys
from datetime import datetime, timezone

from hub_core import (
    BUILD_STATE_SCHEMA_VERSION,
    build_attempt_provenance,
    check_golden_regression,
    dump_exception_failure,
    dump_pipeline_failure,
    embed_figures_fingerprint,
    freeze_golden_dataset,
    get_discoverable_projects,
    get_hub_path,
    get_research_root,
    list_projects,
    load_build_state,
    load_config,
    master_execution_error,
    parse_comparison_config,
    parse_sweep_config,
    print_provenance,
    project_role,
    project_status,
    prompt_numeric_selection,
    required_r_runners,
    rerun_in_docker,
    run_analysis,
    run_check_all,
    run_comparison,
    run_diagrams,
    run_plots,
    run_preflight_check,
    run_sweep,
    save_build_state,
    scaffold_project,
    scaffold_wizard,
    ui_panel,
    ui_print,
    validate_data_contract,
    validate_data_contract_preflight,
    validate_environment_locks,
    write_execution_log,
)
from hub_core.adapters import select_adapters
from hub_core.attempt_provenance import render_attempt_provenance, update_attempt_provenance
from hub_core.cache_manager import collect_signatures
from hub_core.config_parser import find_config_path
from hub_core.logging import configure_logging, get_logger
from hub_core.redaction import redact_text
from hub_core.research_ops_enforcement import validate_research_ops_contract

logger = get_logger(__name__)
INTERNAL_STYLE_TARGET_FORMAT = "_".join(("nature", "surfur"))


def _refresh_visual_output_signatures(project_dir: str, config: dict, build_state: dict) -> None:
    sections = (
        ("figures", "figures", "Fig"),
        ("diagrams", "diagrams", "Diagram"),
    )
    for section_name, step_kind, default_prefix in sections:
        bucket = build_state.get(step_kind)
        if not isinstance(bucket, dict):
            continue
        for index, artifact in enumerate(config.get(section_name, []), 1):
            artifact_id = artifact.get("id", f"{default_prefix}{index}")
            script = artifact.get("script", "").split("::")[0]
            output = artifact.get("output", "output.pdf")
            step_key = f"{artifact_id}:{script}->{output}"
            step_state = bucket.get(step_key)
            if not isinstance(step_state, dict):
                continue
            step_state["outputs"] = collect_signatures(project_dir, [output])


def _apply_cli_preset(config: dict, preset_name: str) -> None:
    from hub_core.config_parser import ALLOWED_TARGET_FORMATS

    presets = config.get("presets") or {}
    preset_key = preset_name.lower()
    matching_name = next((k for k in presets if k.lower() == preset_key), None)
    if matching_name and isinstance(presets[matching_name], dict):
        visual = config.setdefault("visual_style", {})
        allowed_keys = {"target_format", "font_scale", "profile", "output_format", "colormap"}
        for key, val in presets[matching_name].items():
            if key in allowed_keys:
                visual[key] = val
        logger.info("   --preset '%s' applied: %s", preset_name, presets[matching_name])
    elif preset_key in ALLOWED_TARGET_FORMATS:
        config.setdefault("visual_style", {})["target_format"] = preset_key
        logger.info("   --preset → target_format='%s'", preset_key)
    else:
        logger.warning(
            "⚠️  Warning: --preset '%s' not found in presets: section "
            "and not a known target_format. Ignored.",
            preset_name,
        )


def _selector_kind(args: argparse.Namespace) -> str:
    if args.check_all:
        return "check_all"
    if args.project:
        return "project"
    if args.init or args.wizard:
        return "scaffold"
    if args.list_projects or args.status:
        return "list"
    return "interactive"


def _emit_attempt_provenance(attempt: dict[str, object]) -> None:
    ui_print(render_attempt_provenance(attempt))


def _persist_project_failure(
    *,
    project_path: str,
    hub_path: str,
    config: dict | None,
    config_path: str | None,
    config_hash: str | None,
    args: argparse.Namespace,
    start_time: datetime,
    failure_stage: str,
    message: str,
    raw_request: str,
    engine_target: str,
    job_id: str,
    attempt_provenance: dict[str, object],
) -> str | None:
    """Persist a sanitized failure for a project that has already been resolved."""
    safe_message = redact_text(message)
    _emit_attempt_provenance(attempt_provenance)
    context = {
        "step": args.step,
        "raw_request": raw_request,
        "engine_target": engine_target,
        "job_id": job_id,
        "failure_stage": failure_stage,
        "attempt_provenance": attempt_provenance,
    }
    failure_dump_path = dump_pipeline_failure(project_path, message=safe_message, context=context)
    try:
        write_execution_log(
            project_path,
            hub_path,
            config,
            config_path,
            config_hash,
            args=args,
            start_time=start_time,
            end_time=datetime.now(timezone.utc),
            success=False,
            failure_stage=failure_stage,
            message=safe_message,
            raw_request=raw_request,
            engine_target=engine_target,
            attempt_provenance=attempt_provenance,
        )
    except RuntimeError:
        logger.warning("⚠️  Execution history was not persisted after early pipeline failure.")
    return failure_dump_path


def main():
    inferred_hub_path = get_hub_path()
    inferred_root_dir = get_research_root()

    parser = argparse.ArgumentParser(
        description="Research Central Orchestrator (RC-Arch)",
        epilog=(
            "Quick start:\n"
            "  python orchestrator.py\n"
            '  python orchestrator.py --project "01_Ionoelastomer" --step plot\n'
            '  python orchestrator.py --project "01_Ionoelastomer" --step diagrams\n'
            '  python orchestrator.py --init --project "새_프로젝트_폴더"'
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--project", "-p", type=str, help="Project directory path (relative or absolute)")
    parser.add_argument(
        "--step",
        "-s",
        type=str,
        choices=["analysis", "plot", "diagrams", "assembly", "all"],
        default="all",
        help="Choose pipeline step: analysis, plot, diagrams, assembly, or all (default)",
    )
    parser.add_argument("--force", action="store_true", help="Force rerun all steps and bypass smart build cache")
    parser.add_argument("--strict-lock", action="store_true", help="Fail-fast when environment lockfiles are missing")
    parser.add_argument("--list-projects", "-l", action="store_true", help="List configured projects")
    parser.add_argument(
        "--list-root-only", action="store_true", help="With --list-projects, show only immediate root folders"
    )
    parser.add_argument("--status", action="store_true", help="Alias for --list-projects with enhanced status table")
    parser.add_argument(
        "--scan-depth", type=int, default=4, help="Max depth for recursive --list-projects scan (default: 4)"
    )
    parser.add_argument(
        "--init", action="store_true", help="Initialize a new project scaffold at --project path (or launch wizard)"
    )
    parser.add_argument(
        "--wizard", action="store_true", help="Launch interactive scaffolding wizard (can be used with --init)"
    )
    parser.add_argument(
        "--check-all", action="store_true", help="Run all discoverable projects and write a regression report"
    )
    parser.add_argument(
        "--reformat-journal",
        type=str,
        default=None,
        help="Re-render all figures for a different target journal (e.g., science, acs)",
    )
    parser.add_argument(
        "--freeze-golden", action="store_true", help="Freeze current results/data artifacts into results/data/golden"
    )
    parser.add_argument(
        "--check-regression",
        action="store_true",
        help="Compare current results/data artifacts against frozen golden data",
    )
    parser.add_argument(
        "--regression-baseline",
        choices=["ignore", "check", "update"],
        default="ignore",
        help=(
            "For --check-all, ignore baselines, check current figures against stored "
            "baselines, or update baseline snapshots"
        ),
    )
    parser.add_argument("--docker", action="store_true", help="Rerun this orchestrator command inside Docker")
    parser.add_argument("--docker-build", action="store_true", help="Build the Docker image before --docker execution")
    parser.add_argument(
        "--docker-image", type=str, default="figops:latest", help="Docker image tag for --docker mode"
    )
    parser.add_argument(
        "--read-fingerprint",
        type=str,
        metavar="FILE",
        help="Read and display the Digital Fingerprint from a figure file (.png, .pdf, .svg)",
    )
    parser.add_argument(
        "--inject-fingerprint",
        action="store_true",
        help="Inject Digital Fingerprint into existing figures (no pipeline rerun)",
    )
    parser.add_argument(
        "--sweep", action="store_true", help="Run parameter sweep defined in project_config.yaml sweep: section"
    )
    parser.add_argument(
        "--comparison",
        action="store_true",
        help="Run comparison mode defined in project_config.yaml comparison: section",
    )
    parser.add_argument(
        "--preset",
        type=str,
        default=None,
        metavar="NAME",
        help=(
            "Override visual_style for this run without editing project_config.yaml.\n"
            "Accepts a named preset from the config's presets: section, or a target_format\n"
            f"(nature, {INTERNAL_STYLE_TARGET_FORMAT}, science, ppt, acs, rsc, elsevier, wiley, cell, default)."
        ),
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging on stderr")

    args = parser.parse_args()
    configure_logging(verbose=args.verbose)

    root_dir = inferred_root_dir
    hub_path = inferred_hub_path
    attempt_provenance = build_attempt_provenance(
        surface="cli",
        step=args.step,
        selector_kind=_selector_kind(args),
        hub_path=hub_path,
    )
    _emit_attempt_provenance(attempt_provenance)

    if args.list_projects or args.status:
        list_projects(root_dir, recursive=not args.list_root_only, max_depth=args.scan_depth)
        return 0

    start_time = datetime.now(timezone.utc)
    end_time = start_time
    success = False
    failure_stage = ""
    status_message = ""
    config = None
    config_path = None
    config_hash = None
    lock_info = None
    build_state_path = None
    failure_dump_path = None
    adapters = None

    if args.docker and os.environ.get("RESEARCH_HUB_IN_DOCKER") != "1":
        try:
            return rerun_in_docker(
                hub_path=hub_path,
                root_dir=root_dir,
                argv=sys.argv[1:],
                image=args.docker_image,
                build=args.docker_build,
            )
        except RuntimeError as exc:
            ui_print(f"❌ {exc}")
            return 1

    if args.read_fingerprint:
        from hub_core.provenance import read_provenance_fingerprint

        fp = read_provenance_fingerprint(args.read_fingerprint)
        if fp:
            ui_print(f"\n🏷️  [Digital Fingerprint: {os.path.basename(args.read_fingerprint)}]")
            for k, v in fp.items():
                ui_print(f"   - {k}: {v}")
            return 0
        else:
            ui_print(f"\n❌ Error: No Digital Fingerprint found in {args.read_fingerprint}")
            return 1

    if args.inject_fingerprint:
        if not args.project:
            ui_print("❌ Error: --inject-fingerprint requires --project.")
            return 1
        project_path = args.project
        if not os.path.isabs(project_path):
            project_path = os.path.join(root_dir, project_path)
        project_path = os.path.abspath(project_path)
        raw_request = shlex.join(["python", "orchestrator.py", *sys.argv[1:]])
        engine_target = "hub_pipeline"
        job_id = os.path.basename(project_path.rstrip(os.sep)) or "hub_project"

        if not os.path.isdir(project_path):
            update_attempt_provenance(attempt_provenance, config_path=None, config_status="missing")
            _emit_attempt_provenance(attempt_provenance)
            ui_print(f"❌ Error: Project directory not found: {project_path}")
            return 1

        candidate_config_path = find_config_path(project_path)
        config, config_path, config_hash = load_config(project_path)
        if not config:
            update_attempt_provenance(attempt_provenance, config_path=candidate_config_path)
            if attempt_provenance["config_status"] == "valid":
                update_attempt_provenance(
                    attempt_provenance,
                    config_path=candidate_config_path,
                    config_status="invalid",
                )
            _persist_project_failure(
                project_path=project_path,
                hub_path=hub_path,
                config=None,
                config_path=candidate_config_path,
                config_hash=None,
                args=args,
                start_time=start_time,
                failure_stage="CONFIG",
                message="Project configuration could not be loaded for fingerprint injection.",
                raw_request=raw_request,
                engine_target=engine_target,
                job_id=job_id,
                attempt_provenance=attempt_provenance,
            )
            return 1
        update_attempt_provenance(attempt_provenance, config_path=config_path, config_status="valid")
        _emit_attempt_provenance(attempt_provenance)

        from hub_core.provenance import (
            _build_environment_hash,
            _readable_git_commit,
            _readable_tool_version,
        )

        python_version = sys.version.split()[0]
        r_exec = config.get("execution", {}).get("rscript") or "Rscript"
        r_version = _readable_tool_version(r_exec)
        env_hash = _build_environment_hash(None, python_version, r_version, config)
        git_commit = _readable_git_commit(hub_path)
        from hub_core.provenance import reproducible_timestamp

        try:
            ts = reproducible_timestamp()
        except ValueError as exc:
            ui_print(f"❌ {exc}")
            return 1

        n = embed_figures_fingerprint(
            project_dir=project_path,
            config=config,
            config_hash=config_hash,
            environment_hash=env_hash,
            git_commit=git_commit,
            timestamp=ts,
        )
        return 0 if n >= 0 else 1

    if args.init or args.wizard:
        # If --wizard is present or --init is used without --project, launch wizard
        if args.wizard or (args.init and not args.project):
            scaffold_wizard(hub_path)
            return 0

        # Original --init logic with --project
        init_target = args.project
        if not os.path.isabs(init_target):
            init_target = os.path.join(root_dir, init_target)

        try:
            scaffold_info = scaffold_project(init_target, hub_path)
        except RuntimeError as exc:
            ui_print(f"❌ {exc}")
            return 1

        ui_panel(
            f"[bold]Project Scaffold Initialized[/bold]\n"
            f"   - name: {scaffold_info['project_name']}\n"
            f"   - dir: {scaffold_info['project_dir']}",
            title="Success",
            style="green",
        )
        return 0

    if args.check_all:
        try:
            report_path, report = run_check_all(
                hub_path=os.path.abspath(os.path.dirname(__file__)),
                root_dir=root_dir,
                step=args.step,
                force=args.force,
                strict_lock=args.strict_lock,
                scan_depth=args.scan_depth,
                regression_baseline=args.regression_baseline,
            )
        except RuntimeError as exc:
            logger.error("❌ %s", exc)
            return 1

        logger.info("\n🧪 [Check-All Summary]")
        logger.info("   - report_path: %s", report_path)
        logger.info("   - discovered_configs: %s", report.get("discovered_count", report["project_count"]))
        logger.info("   - project_count: %s", report["project_count"])
        logger.info("   - invalid_configs: %s", report.get("invalid_count", 0))
        logger.info("   - passed: %s", report["passed_count"])
        logger.info("   - failed: %s", report["failed_count"])
        if args.regression_baseline != "ignore":
            baseline = report.get("baseline_summary", {})
            logger.info("   - baseline_mode: %s", baseline.get("mode"))
            logger.info("   - matched: %s", baseline.get("matched_count", 0))
            logger.info("   - mismatched: %s", baseline.get("mismatch_count", 0))
            logger.info("   - missing_baseline: %s", baseline.get("missing_baseline_count", 0))
            logger.info("   - updated: %s", baseline.get("updated_count", 0))
        return 0 if report.get("success") else 1

    if not args.project:
        # --- Interactive Mode 발동 ---
        projects = get_discoverable_projects(root_dir, max_depth=args.scan_depth)
        if not projects:
            logger.error("❌ No configured projects found in the research directory.")
            logger.error("   ├─ Try: python orchestrator.py --list-projects")
            logger.error('   └─ Or create one: python orchestrator.py --init --project "새_프로젝트_폴더"')
            return 1

        # 선택 목록 구성 (이름 + 경로)
        display_options = [f"{p['name']} ({p['path']})" for p in projects]
        selected_idx = prompt_numeric_selection(display_options, header="Available Research Projects")

        # 선택된 프로젝트 경로 할당
        args.project = projects[selected_idx]["path"]
        logger.info("🚀 Selected Project: %s", projects[selected_idx]["name"])
        # -----------------------------

    # 프로젝트 경로 정규화 (이름만 입력 시 루트에서 찾기)
    project_path = args.project
    if not os.path.exists(project_path):
        project_path = os.path.join(root_dir, args.project)
    project_path = os.path.abspath(project_path)

    if not os.path.isdir(project_path):
        logger.error("❌ Error: Project directory not found: %s", project_path)
        logger.error("   ├─ Check the path spelling or run `python orchestrator.py --list-projects`.")
        logger.error("   └─ Relative names are resolved from the research root folder.")
        return 1

    raw_request = shlex.join(["python", "orchestrator.py", *sys.argv[1:]])
    engine_target = "hub_pipeline"
    job_id = os.path.basename(project_path.rstrip(os.sep)) or "hub_project"

    try:
        # 설정 로드 및 실행
        candidate_config_path = find_config_path(project_path)
        config, config_path, config_hash = load_config(project_path)
        if not config:
            update_attempt_provenance(attempt_provenance, config_path=candidate_config_path)
            if attempt_provenance["config_status"] == "valid":
                update_attempt_provenance(
                    attempt_provenance,
                    config_path=candidate_config_path,
                    config_status="invalid",
                )
            failure_stage = "CONFIG"
            status_message = "Project configuration could not be loaded."
            failure_dump_path = _persist_project_failure(
                project_path=project_path,
                hub_path=hub_path,
                config=None,
                config_path=candidate_config_path,
                config_hash=None,
                args=args,
                start_time=start_time,
                failure_stage=failure_stage,
                message=status_message,
                raw_request=raw_request,
                engine_target=engine_target,
                job_id=job_id,
                attempt_provenance=attempt_provenance,
            )
            return 1
        update_attempt_provenance(attempt_provenance, config_path=config_path, config_status="valid")
        _emit_attempt_provenance(attempt_provenance)
        if project_role(config) == "master":
            failure_stage = "CONFIG"
            status_message = master_execution_error(config)
            failure_dump_path = _persist_project_failure(
                project_path=project_path,
                hub_path=hub_path,
                config=config,
                config_path=config_path,
                config_hash=config_hash,
                args=args,
                start_time=start_time,
                failure_stage=failure_stage,
                message=status_message,
                raw_request=raw_request,
                engine_target=engine_target,
                job_id=job_id,
                attempt_provenance=attempt_provenance,
            )
            logger.error("❌ Error: %s", redact_text(status_message))
            return 1
        if project_status(config) == "legacy":
            failure_stage = "CONFIG"
            status_message = "project is marked legacy; rendering is disabled for retired projects."
            failure_dump_path = _persist_project_failure(
                project_path=project_path,
                hub_path=hub_path,
                config=config,
                config_path=config_path,
                config_hash=config_hash,
                args=args,
                start_time=start_time,
                failure_stage=failure_stage,
                message=status_message,
                raw_request=raw_request,
                engine_target=engine_target,
                job_id=job_id,
                attempt_provenance=attempt_provenance,
            )
            logger.error("❌ Error: %s", status_message)
            return 1
        research_ops = validate_research_ops_contract(project_path, config)
        if research_ops["errors"]:
            for message in research_ops["errors"]:
                logger.error("❌ Error: %s", redact_text(message))
            failure_stage = "CONFIG"
            status_message = "; ".join(research_ops["errors"])
            failure_dump_path = _persist_project_failure(
                project_path=project_path,
                hub_path=hub_path,
                config=config,
                config_path=config_path,
                config_hash=config_hash,
                args=args,
                start_time=start_time,
                failure_stage=failure_stage,
                message=status_message,
                raw_request=raw_request,
                engine_target=engine_target,
                job_id=job_id,
                attempt_provenance=attempt_provenance,
            )
            return 1
        for message in research_ops["warnings"]:
            logger.warning("⚠️  Warning: %s", message)

        if args.preset:
            _apply_cli_preset(config, args.preset)
            config_hash = hashlib.sha256(f"{config_hash}:preset={args.preset}".encode()).hexdigest()

        rscript_commands = required_r_runners(config, args.step)
        if not run_preflight_check(exit_on_failure=False, rscript_commands=rscript_commands):
            end_time = datetime.now(timezone.utc)
            failure_stage = "VALIDATE"
            status_message = "Runtime preflight failed for selected pipeline steps."
            failure_dump_path = dump_pipeline_failure(
                project_path,
                message=status_message,
                context={
                    "step": args.step,
                    "raw_request": raw_request,
                    "engine_target": engine_target,
                    "job_id": job_id,
                    "failure_stage": failure_stage,
                    "attempt_provenance": attempt_provenance,
                },
            )
            try:
                write_execution_log(
                    project_path,
                    hub_path,
                    config,
                    config_path,
                    config_hash,
                    args=args,
                    start_time=start_time,
                    end_time=end_time,
                    success=False,
                    failure_stage=failure_stage,
                    message=status_message,
                    raw_request=raw_request,
                    engine_target=engine_target,
                    attempt_provenance=attempt_provenance,
                )
            except RuntimeError:
                logger.warning("⚠️  Execution history was not persisted after preflight failure.")
            logger.error("❌ %s", status_message)
            logger.error("   └─ Failure snapshot: %s", failure_dump_path)
            return 1

        adapters = select_adapters(config)

        lock_info = validate_environment_locks(
            project_dir=project_path,
            hub_path=hub_path,
            config=config,
            strict_cli=args.strict_lock,
        )
        if not lock_info.get("ok"):
            end_time = datetime.now(timezone.utc)
            failure_stage = "VALIDATE"
            status_message = "Environment lock validation failed."
            try:
                write_execution_log(
                    project_path,
                    hub_path,
                    config,
                    config_path,
                    config_hash,
                    args=args,
                    lock_info=lock_info,
                    build_state_path=build_state_path,
                    start_time=start_time,
                    end_time=end_time,
                    success=False,
                    failure_stage=failure_stage,
                    message=status_message,
                    raw_request=raw_request,
                    engine_target=engine_target,
                    attempt_provenance=attempt_provenance,
                )
            except RuntimeError:
                return 1
            return 1

        build_state, build_state_path = load_build_state(project_path)
        print_provenance(
            project_path,
            config_path,
            config_hash,
            config,
            lock_info=lock_info,
            build_state_path=build_state_path,
        )

        # --- Batch journal reformat shortcut ---
        if args.reformat_journal:
            from hub_core.batch_reformat import batch_reformat_figures

            result = batch_reformat_figures(
                project_path,
                args.reformat_journal,
                config,
                hub_path,
                force=True,
            )
            if result.success:
                logger.info(
                    "\n   Batch reformat -> %s: %s figures in %ss",
                    result.target_journal,
                    result.figures_regenerated,
                    result.elapsed_seconds,
                )
                for p in result.output_paths:
                    logger.info("   - %s", p)
            else:
                logger.error("\n   Batch reformat failed: %s", result.error)
            return 0 if result.success else 1

        logger.info("\n🧠 [Smart Build]")
        if args.force:
            logger.info("   - mode: force (all steps rerun)")
        elif build_state.get("config_hash") and build_state.get("config_hash") != config_hash:
            logger.info("   - cache invalidated: project_config.yaml changed since last run")
        else:
            logger.info("   - mode: incremental (mtime+size signature cache)")
        logger.info("   - state_file: %s", build_state_path)

        start_time = datetime.now(timezone.utc)
        logger.info("\n%s\n📡 RC-Arch Pipeline Start: %s\n%s", "=" * 60, config["project"]["name"], "=" * 60)

        # --- Mutual exclusion: sweep + comparison cannot both be active ---
        sweep_cfg = config.get("sweep")
        comparison_cfg = config.get("comparison")
        sweep_active = bool(args.sweep or (sweep_cfg and sweep_cfg.get("enabled", False)))
        comparison_active = bool(args.comparison or (comparison_cfg and comparison_cfg.get("enabled", False)))

        if sweep_active and comparison_active:
            logger.error("❌ sweep and comparison cannot both be active at the same time.")
            logger.error("   Set only one of sweep.enabled or comparison.enabled to true.")
            success = False
            failure_stage = "CONFIG"
            status_message = "sweep and comparison cannot both be active."
        # --- Parameter Sweep ---
        elif sweep_active:
            if not sweep_cfg:
                logger.error("❌ --sweep flag used but no 'sweep:' section found in project_config.yaml.")
                success = False
                failure_stage = "CONFIG"
                status_message = "Sweep requested but no sweep configuration was found."
            else:
                sweep_failure = {}
                parsed_sweep = parse_sweep_config(sweep_cfg)
                sweep_label = "enabled in config" if sweep_cfg.get("enabled") else "forced via --sweep"
                logger.info("   - sweep: %s, %s run(s)", sweep_label, len(parsed_sweep["runs"]))
                success = run_sweep(
                    project_dir=project_path,
                    config=config,
                    build_state=build_state,
                    build_state_path=build_state_path,
                    config_hash=config_hash,
                    sweep_cfg=sweep_cfg,
                    step=args.step,
                    force=args.force,
                    failure_context=sweep_failure,
                    prefetcher=adapters.prefetcher,
                    athena=adapters.athena,
                )
                if not success:
                    failure_stage = sweep_failure.get("stage", "EXECUTE")
                    status_message = sweep_failure.get("message", "Sweep execution failed.")
        # --- Comparison Mode ---
        elif comparison_active:
            if not comparison_cfg:
                logger.error("❌ --comparison flag used but no 'comparison:' section found in project_config.yaml.")
                success = False
                failure_stage = "CONFIG"
                status_message = "Comparison requested but no comparison configuration was found."
            else:
                comparison_failure = {}
                parsed_comparison = parse_comparison_config(comparison_cfg)
                comparison_label = "enabled in config" if comparison_cfg.get("enabled") else "forced via --comparison"
                logger.info(
                    "   - comparison: %s, %s condition(s)",
                    comparison_label,
                    len(parsed_comparison["conditions"]),
                )
                success = run_comparison(
                    project_dir=project_path,
                    config=config,
                    build_state=build_state,
                    build_state_path=build_state_path,
                    config_hash=config_hash,
                    comparison_cfg=comparison_cfg,
                    step=args.step,
                    force=args.force,
                    failure_context=comparison_failure,
                    prefetcher=adapters.prefetcher,
                    athena=adapters.athena,
                )
                if not success:
                    failure_stage = comparison_failure.get("stage", "EXECUTE")
                    status_message = comparison_failure.get("message", "Comparison execution failed.")
        else:
            success = True
            if args.step in ["plot", "all"]:
                success = validate_data_contract_preflight(
                    project_path,
                    config,
                    require_existing=args.step == "plot",
                    prefetcher=adapters.prefetcher,
                )
                if not success:
                    failure_stage = "VALIDATE"
                    status_message = "Data contract preflight failed."

            if success and args.step in ["analysis", "all"]:
                success = run_analysis(
                    project_path,
                    config,
                    build_state=build_state,
                    build_state_path=build_state_path,
                    config_hash=config_hash,
                    force=args.force,
                    prefetcher=adapters.prefetcher,
                    athena=adapters.athena,
                )
                if not success:
                    failure_stage = "EXECUTE"
                    status_message = "Analysis step failed."

            if success and args.step in ["analysis", "all"] and args.check_regression:
                regression_result = check_golden_regression(project_path, config)
                logger.info("\n🧪 [Golden Regression Check]")
                logger.info("   - manifest: %s", regression_result.manifest_path)
                logger.info("   - compared: %s", len(regression_result.compared_files))
                if regression_result.success:
                    logger.info("   - status: matched")
                else:
                    logger.error("   - status: failed")
                    for failure in regression_result.failures[:5]:
                        logger.error("   - %s: %s", failure.path, failure.reason)
                        if failure.diff_summary:
                            logger.error("     diff: %s", failure.diff_summary)
                    success = False
                    failure_stage = "VALIDATE"
                    status_message = "Golden regression check failed."

            if success and args.step in ["plot", "all"]:
                success = validate_data_contract(project_path, config, prefetcher=adapters.prefetcher)
                if not success:
                    failure_stage = "VALIDATE"
                    status_message = "Data contract validation failed."

            if success and args.step in ["plot", "all"]:
                success = run_plots(
                    project_path,
                    config,
                    build_state=build_state,
                    build_state_path=build_state_path,
                    config_hash=config_hash,
                    force=args.force,
                    prefetcher=adapters.prefetcher,
                    athena=adapters.athena,
                )
                if not success:
                    failure_stage = "EXECUTE"
                    status_message = "Plotting step failed."

            if success and args.step in ["plot", "all"]:
                adapters.athena.run_health_hook(root_dir, hub_path)

            if success and args.step in ["diagrams", "all"]:
                success = run_diagrams(
                    project_path,
                    config,
                    build_state=build_state,
                    build_state_path=build_state_path,
                    config_hash=config_hash,
                    force=args.force,
                    prefetcher=adapters.prefetcher,
                    athena=adapters.athena,
                )
                if not success:
                    failure_stage = "EXECUTE"
                    status_message = "Diagram step failed."

            if success and args.step in ["assembly", "all"]:
                from hub_core.process_runner import run_assemblies

                success = run_assemblies(
                    project_path,
                    config,
                    force=args.force,
                )
                if not success:
                    failure_stage = "EXECUTE"
                    status_message = "Assembly step failed."

        if success and args.freeze_golden:
            freeze_result = freeze_golden_dataset(project_path, config)
            logger.info("\n📦 [Golden Dataset Frozen]")
            logger.info("   - golden_dir: %s", freeze_result.golden_dir)
            logger.info("   - file_count: %s", len(freeze_result.frozen_files))
            logger.info("   - manifest: %s", freeze_result.manifest_path)

        if success:
            build_state["version"] = BUILD_STATE_SCHEMA_VERSION
            build_state["config_hash"] = config_hash
            save_build_state(build_state_path, build_state)

            # --- Digital Fingerprint: 생성된 모든 figure에 프로방스 지문 임베딩 ---
            try:
                python_version = sys.version.split()[0]
                from hub_core.provenance import (
                    _build_environment_hash,
                    _readable_git_commit,
                    _readable_tool_version,
                )

                r_exec = config.get("execution", {}).get("rscript") or "Rscript"
                r_version = _readable_tool_version(r_exec)
                env_hash = _build_environment_hash(lock_info, python_version, r_version, config)
                git_commit = _readable_git_commit(hub_path)
                from hub_core.provenance import reproducible_timestamp

                embed_figures_fingerprint(
                    project_dir=project_path,
                    config=config,
                    config_hash=config_hash,
                    environment_hash=env_hash,
                    git_commit=git_commit,
                    timestamp=reproducible_timestamp(),
                )
                _refresh_visual_output_signatures(project_path, config, build_state)
                save_build_state(build_state_path, build_state)
            except Exception as _fp_exc:
                logger.warning("\n⚠️  Digital Fingerprint 임베딩 실패 (결과에는 영향 없음): %s", _fp_exc)
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Pipeline interrupted by user (Ctrl+C). Exiting.")
        return 130
    except Exception as exc:
        end_time = datetime.now(timezone.utc)
        failure_stage = failure_stage or "EXECUTE"
        status_message = f"{type(exc).__name__}: {exc}"
        failure_dump_path = dump_exception_failure(
            project_path,
            exc,
            context={
                "step": args.step,
                "force": args.force,
                "check_regression": args.check_regression,
                "freeze_golden": args.freeze_golden,
                "raw_request": raw_request,
                "engine_target": engine_target,
                "job_id": job_id,
                "failure_stage": failure_stage,
                "attempt_provenance": attempt_provenance,
            },
        )
        logger.error("\n❌ Unexpected orchestrator exception: %s: %s", type(exc).__name__, exc)
        logger.error("   - failure_dump: %s", failure_dump_path)
        logger.error("   - hint: /heal %s", os.path.relpath(project_path, root_dir))
        success = False

    end_time = datetime.now(timezone.utc)
    logging_failed = False
    try:
        write_execution_log(
            project_path,
            hub_path,
            config,
            config_path,
            config_hash,
            args=args,
            lock_info=lock_info,
            build_state_path=build_state_path,
            start_time=start_time,
            end_time=end_time,
            success=success,
            failure_stage="" if success else (failure_stage or "EXECUTE"),
            message=status_message,
            raw_request=raw_request,
            engine_target=engine_target,
            attempt_provenance=attempt_provenance,
        )
    except RuntimeError:
        logging_failed = True

    duration = end_time - start_time

    if success and project_path and adapters is not None:
        adapters.athena.run_draft_bridge(project_path, hub_path)

    logger.info("\n%s", "=" * 60)
    if success:
        logger.info("✅ Pipeline Successfully Finished. (Time: %.1fs)", duration.total_seconds())
    else:
        if project_path and failure_dump_path is None:
            failure_dump_path = dump_pipeline_failure(
                project_path,
                message=status_message or "One or more pipeline steps failed.",
                context={
                    "step": args.step,
                    "force": args.force,
                    "check_regression": args.check_regression,
                    "freeze_golden": args.freeze_golden,
                    "raw_request": raw_request,
                    "engine_target": engine_target,
                    "job_id": job_id,
                    "failure_stage": failure_stage or "EXECUTE",
                    "attempt_provenance": attempt_provenance,
                },
            )
        logger.error("❌ Pipeline Failed midway. Check errors above.")
        logger.error("   └─ Fix the first failing step above, then rerun the same command.")
        if failure_dump_path:
            logger.error("   └─ Failure snapshot: %s", failure_dump_path)
            logger.error("   └─ Auto-heal hint: /heal %s", os.path.relpath(project_path, root_dir))
    if logging_failed:
        logger.warning("⚠️  Execution history was not persisted to the primary hub_logs path.")
    logger.info("%s", "=" * 60)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
