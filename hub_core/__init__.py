"""
hub_core package

This package contains the modularized logic for the Graph_making_hub orchestrator.
"""

from .cache_manager import BUILD_STATE_SCHEMA_VERSION, load_build_state, save_build_state
from .config_parser import (
    get_discoverable_projects,
    list_projects,
    load_config,
    parse_comparison_config,
    parse_sweep_config,
)
from .data_contract import validate_data_contract, validate_data_contract_preflight
from .data_regression import check_golden_regression, freeze_golden_dataset
from .docker_runner import rerun_in_docker
from .error_dumper import dump_exception_failure, dump_pipeline_failure
from .execution_log import append_execution_log, build_execution_log_record, write_execution_log
from .figure_preflight import validate_figure_preflight
from .health_check import run_preflight_check
from .process_runner import run_analysis, run_comparison, run_diagrams, run_plots, run_sweep
from .provenance import (
    collect_dvc_provenance,
    embed_figures_fingerprint,
    print_provenance,
    validate_environment_locks,
)
from .scaffold import scaffold_project, scaffold_wizard
from .ui_utils import ui_confirm, ui_panel, ui_print, ui_prompt, ui_table
from .utils import (
    ensure_local_files,
    get_hub_path,
    get_research_root,
    prompt_numeric_selection,
    scan_csv_export_anomalies,
)
from .visual_regression import run_check_all, write_check_all_report
