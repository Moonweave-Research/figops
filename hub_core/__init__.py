"""
hub_core package

This package contains the modularized logic for the Graph_making_hub orchestrator.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "BUILD_STATE_SCHEMA_VERSION": ("hub_core.cache_manager", "BUILD_STATE_SCHEMA_VERSION"),
    "append_execution_log": ("hub_core.execution_log", "append_execution_log"),
    "build_attempt_provenance": ("hub_core.attempt_provenance", "build_attempt_provenance"),
    "build_execution_log_record": ("hub_core.execution_log", "build_execution_log_record"),
    "check_golden_regression": ("hub_core.data_regression", "check_golden_regression"),
    "dump_exception_failure": ("hub_core.error_dumper", "dump_exception_failure"),
    "dump_pipeline_failure": ("hub_core.error_dumper", "dump_pipeline_failure"),
    "embed_figures_fingerprint": ("hub_core.provenance", "embed_figures_fingerprint"),
    "freeze_golden_dataset": ("hub_core.data_regression", "freeze_golden_dataset"),
    "get_discoverable_projects": ("hub_core.config_parser", "get_discoverable_projects"),
    "get_hub_path": ("hub_core.utils", "get_hub_path"),
    "get_research_root": ("hub_core.utils", "get_research_root"),
    "list_projects": ("hub_core.config_parser", "list_projects"),
    "load_build_state": ("hub_core.cache_manager", "load_build_state"),
    "load_config": ("hub_core.config_parser", "load_config"),
    "master_execution_error": ("hub_core.config_parser", "master_execution_error"),
    "parse_comparison_config": ("hub_core.config_parser", "parse_comparison_config"),
    "parse_sweep_config": ("hub_core.config_parser", "parse_sweep_config"),
    "print_provenance": ("hub_core.provenance", "print_provenance"),
    "project_role": ("hub_core.config_parser", "project_role"),
    "project_status": ("hub_core.config_parser", "project_status"),
    "prompt_numeric_selection": ("hub_core.utils", "prompt_numeric_selection"),
    "rerun_in_docker": ("hub_core.docker_runner", "rerun_in_docker"),
    "run_analysis": ("hub_core.process_runner", "run_analysis"),
    "run_check_all": ("hub_core.visual_regression", "run_check_all"),
    "run_comparison": ("hub_core.process_runner", "run_comparison"),
    "run_diagrams": ("hub_core.process_runner", "run_diagrams"),
    "run_plots": ("hub_core.process_runner", "run_plots"),
    "run_preflight_check": ("hub_core.health_check", "run_preflight_check"),
    "required_r_runners": ("hub_core.health_check", "required_r_runners"),
    "run_sweep": ("hub_core.process_runner", "run_sweep"),
    "save_build_state": ("hub_core.cache_manager", "save_build_state"),
    "scaffold_project": ("hub_core.scaffold", "scaffold_project"),
    "scaffold_wizard": ("hub_core.scaffold", "scaffold_wizard"),
    "scan_csv_export_anomalies": ("hub_core.utils", "scan_csv_export_anomalies"),
    "ui_confirm": ("hub_core.ui_utils", "ui_confirm"),
    "ui_panel": ("hub_core.ui_utils", "ui_panel"),
    "ui_print": ("hub_core.ui_utils", "ui_print"),
    "ui_prompt": ("hub_core.ui_utils", "ui_prompt"),
    "ui_table": ("hub_core.ui_utils", "ui_table"),
    "validate_data_contract": ("hub_core.data_contract", "validate_data_contract"),
    "validate_data_contract_preflight": ("hub_core.data_contract", "validate_data_contract_preflight"),
    "validate_environment_locks": ("hub_core.provenance", "validate_environment_locks"),
    "validate_figure_preflight": ("hub_core.figure_preflight", "validate_figure_preflight"),
    "write_check_all_report": ("hub_core.visual_regression", "write_check_all_report"),
    "write_execution_log": ("hub_core.execution_log", "write_execution_log"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module 'hub_core' has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY_EXPORTS})

__all__ = [
    "BUILD_STATE_SCHEMA_VERSION",
    "append_execution_log",
    "build_attempt_provenance",
    "build_execution_log_record",
    "check_golden_regression",
    "dump_exception_failure",
    "dump_pipeline_failure",
    "embed_figures_fingerprint",
    "freeze_golden_dataset",
    "get_discoverable_projects",
    "get_hub_path",
    "get_research_root",
    "list_projects",
    "load_build_state",
    "load_config",
    "master_execution_error",
    "parse_comparison_config",
    "parse_sweep_config",
    "print_provenance",
    "project_role",
    "project_status",
    "prompt_numeric_selection",
    "rerun_in_docker",
    "run_analysis",
    "run_check_all",
    "run_comparison",
    "run_diagrams",
    "run_plots",
    "run_preflight_check",
    "required_r_runners",
    "run_sweep",
    "save_build_state",
    "scaffold_project",
    "scaffold_wizard",
    "scan_csv_export_anomalies",
    "ui_confirm",
    "ui_panel",
    "ui_print",
    "ui_prompt",
    "ui_table",
    "validate_data_contract",
    "validate_data_contract_preflight",
    "validate_environment_locks",
    "validate_figure_preflight",
    "write_check_all_report",
    "write_execution_log",
]
