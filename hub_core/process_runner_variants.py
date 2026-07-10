"""Sweep and comparison orchestration kept separate from the base pipeline runner.

The public compatibility facade remains :mod:`hub_core.process_runner`.  This
module receives its collaborators explicitly so that the facade keeps existing
monkeypatch and public-import contracts while this variation-specific control
flow can evolve independently.
"""

from __future__ import annotations

import copy
import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass


@dataclass(frozen=True)
class VariantDependencies:
    """Collaborators supplied by the ``process_runner`` compatibility facade."""

    log: Callable[[str], None]
    set_failure_context: Callable[[dict | None, str, str], None]
    parse_sweep_config: Callable[[dict], dict]
    parse_comparison_config: Callable[[dict], dict]
    validate_data_contract: Callable[..., bool]
    validate_data_contract_preflight: Callable[..., bool]
    resolve_contained_project_path: Callable[[str, str], str]
    execution_security_error: type[Exception]
    join_config_path: Callable[[str, str], str]
    env_overlay: Callable[[dict[str, str]], AbstractContextManager[None]]
    run_analysis: Callable[..., bool]
    run_plots: Callable[..., bool]
    run_diagrams: Callable[..., bool]


def run_sweep(
    project_dir: str,
    config: dict,
    build_state: dict,
    build_state_path: str,
    config_hash: str,
    sweep_cfg: dict,
    *,
    dependencies: VariantDependencies,
    step: str = "all",
    force: bool = False,
    failure_context: dict | None = None,
    prefetcher=None,
    athena=None,
) -> bool:
    """Run each parsed sweep variant through the supplied pipeline functions."""

    parsed = dependencies.parse_sweep_config(sweep_cfg)
    runs = parsed["runs"]
    output_dir_pattern = parsed["output_dir_pattern"]

    if not runs:
        dependencies.log("   ⚠️  Sweep enabled but no parameter runs resolved. Check sweep.values or sweep.grid.")
        dependencies.set_failure_context(
            failure_context,
            "CONFIG",
            "Sweep enabled but no parameter runs were resolved.",
        )
        return False

    total = len(runs)
    dependencies.log(f"\n🔁 [Sweep Mode] {total} run(s) scheduled")

    all_success = True
    for idx, env_overrides in enumerate(runs, 1):
        label_parts = ", ".join(f"{key}={value}" for key, value in env_overrides.items())
        dependencies.log(f"\n{'─' * 60}")
        dependencies.log(f"   Sweep run {idx}/{total}: {label_parts}")

        output_dir = output_dir_pattern
        for param_name, param_value in env_overrides.items():
            output_dir = output_dir.replace(f"{{{param_name}}}", param_value)
        if "{parameter}" in output_dir or "{value}" in output_dir:
            if len(env_overrides) == 1:
                param_name, param_value = next(iter(env_overrides.items()))
                output_dir = output_dir.replace("{parameter}", param_name).replace("{value}", param_value)
            else:
                joined_names = "_".join(env_overrides.keys())
                joined_pairs = "_".join(f"{name}_{value}" for name, value in env_overrides.items())
                output_dir = output_dir.replace("{parameter}", joined_names).replace("{value}", joined_pairs)
        try:
            sweep_output_dir = dependencies.resolve_contained_project_path(project_dir, output_dir)
        except dependencies.execution_security_error as exc:
            dependencies.log(f"      ❌ Sweep output directory rejected: {exc}")
            dependencies.set_failure_context(failure_context, "CONFIG", f"Sweep output directory rejected: {exc}")
            return False
        os.makedirs(sweep_output_dir, exist_ok=True)

        run_config = copy.deepcopy(config)
        for analysis_step in run_config.get("pipeline", {}).get("analysis", []):
            analysis_step["_cache_env_overrides"] = dict(env_overrides)
        for section in ("figures", "diagrams"):
            for artifact in run_config.get(section, []):
                original_output = artifact.get("output", "")
                artifact["output"] = dependencies.join_config_path(output_dir, os.path.basename(original_output))

        run_success = True
        if step in ("plot", "all"):
            run_success = dependencies.validate_data_contract_preflight(
                project_dir,
                run_config,
                require_existing=step == "plot",
                prefetcher=prefetcher,
            )
            if not run_success:
                dependencies.set_failure_context(
                    failure_context,
                    "VALIDATE",
                    f"Sweep preflight failed for run {idx}/{total} ({label_parts}).",
                )

        sweep_env = {f"SWEEP_{key}": value for key, value in env_overrides.items()}
        sweep_env.update(env_overrides)

        with dependencies.env_overlay(sweep_env):
            if run_success and step in ("analysis", "all"):
                run_success = dependencies.run_analysis(
                    project_dir,
                    run_config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=force,
                    prefetcher=prefetcher,
                    athena=athena,
                )
                if not run_success:
                    dependencies.set_failure_context(
                        failure_context,
                        "EXECUTE",
                        f"Sweep analysis failed for run {idx}/{total} ({label_parts}).",
                    )
            if run_success and step in ("plot", "all"):
                run_success = dependencies.validate_data_contract(project_dir, run_config, prefetcher=prefetcher)
                if not run_success:
                    dependencies.set_failure_context(
                        failure_context,
                        "VALIDATE",
                        f"Sweep data contract validation failed for run {idx}/{total} ({label_parts}).",
                    )
            if run_success and step in ("plot", "all"):
                run_success = dependencies.run_plots(
                    project_dir,
                    run_config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=force,
                    prefetcher=prefetcher,
                    athena=athena,
                )
                if not run_success:
                    dependencies.set_failure_context(
                        failure_context,
                        "EXECUTE",
                        f"Sweep plotting failed for run {idx}/{total} ({label_parts}).",
                    )
            if run_success and step in ("diagrams", "all"):
                run_success = dependencies.run_diagrams(
                    project_dir,
                    run_config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=force,
                    prefetcher=prefetcher,
                    athena=athena,
                )
                if not run_success:
                    dependencies.set_failure_context(
                        failure_context,
                        "EXECUTE",
                        f"Sweep diagram generation failed for run {idx}/{total} ({label_parts}).",
                    )

        status = "✅" if run_success else "❌"
        dependencies.log(f"   {status} Sweep run {idx}/{total} ({label_parts}): {'OK' if run_success else 'FAILED'}")
        dependencies.log(f"      output_dir: {sweep_output_dir}")

        if not run_success:
            all_success = False

    dependencies.log(f"\n{'=' * 60}")
    if all_success:
        dependencies.log(f"✅ Sweep completed: {total}/{total} runs passed.")
    else:
        dependencies.log("❌ Sweep finished with failures. Check output above.")
    return all_success


def run_comparison(
    project_dir: str,
    config: dict,
    build_state: dict,
    build_state_path: str,
    config_hash: str,
    comparison_cfg: dict,
    *,
    dependencies: VariantDependencies,
    step: str = "all",
    force: bool = False,
    failure_context: dict | None = None,
    prefetcher=None,
    athena=None,
) -> bool:
    """Run each parsed comparison condition through the supplied pipeline functions."""

    parsed = dependencies.parse_comparison_config(comparison_cfg)
    conditions = parsed["conditions"]
    overlay_output = parsed["overlay_output"]

    if not conditions:
        dependencies.log("   ⚠️  Comparison enabled but no conditions defined. Check comparison.conditions.")
        dependencies.set_failure_context(
            failure_context,
            "CONFIG",
            "Comparison enabled but no conditions were resolved.",
        )
        return False

    total = len(conditions)
    dependencies.log(f"\n🔀 [Comparison Mode] {total} condition(s) scheduled")
    if overlay_output:
        dependencies.log(f"   overlay_output: {overlay_output}")

    all_success = True
    for idx, condition in enumerate(conditions, 1):
        label = condition["label"]
        env_overrides = condition["env"]
        data_override = condition.get("data_override")

        dependencies.log(f"\n{'─' * 60}")
        dependencies.log(f"   Condition {idx}/{total}: {label}")

        run_config = copy.deepcopy(config)
        safe_label = label.replace(" ", "_").replace("/", "_").replace("%", "pct")
        condition_output_dir = f"results/figures/comparison_{safe_label}"
        absolute_condition_dir = os.path.join(project_dir, condition_output_dir)
        os.makedirs(absolute_condition_dir, exist_ok=True)

        for section in ("figures", "diagrams"):
            for artifact in run_config.get(section, []):
                original_output = artifact.get("output", "")
                artifact["output"] = dependencies.join_config_path(
                    condition_output_dir,
                    os.path.basename(original_output),
                )

        if data_override:
            for analysis_step in run_config.get("pipeline", {}).get("analysis", []):
                analysis_step["inputs"] = [data_override]

        run_success = True
        if step in ("plot", "all"):
            run_success = dependencies.validate_data_contract_preflight(
                project_dir,
                run_config,
                require_existing=step == "plot",
                prefetcher=prefetcher,
            )
            if not run_success:
                dependencies.set_failure_context(
                    failure_context,
                    "VALIDATE",
                    f"Comparison preflight failed for condition {idx}/{total} ({label}).",
                )

        condition_env = {f"COMPARISON_{key}": value for key, value in env_overrides.items()}
        condition_env.update(env_overrides)
        condition_env["COMPARISON_LABEL"] = label

        with dependencies.env_overlay(condition_env):
            if run_success and step in ("analysis", "all"):
                run_success = dependencies.run_analysis(
                    project_dir,
                    run_config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=force,
                    prefetcher=prefetcher,
                    athena=athena,
                )
                if not run_success:
                    dependencies.set_failure_context(
                        failure_context,
                        "EXECUTE",
                        f"Comparison analysis failed for condition {idx}/{total} ({label}).",
                    )
            if run_success and step in ("plot", "all"):
                run_success = dependencies.validate_data_contract(project_dir, run_config, prefetcher=prefetcher)
                if not run_success:
                    dependencies.set_failure_context(
                        failure_context,
                        "VALIDATE",
                        f"Comparison data contract validation failed for condition {idx}/{total} ({label}).",
                    )
            if run_success and step in ("plot", "all"):
                run_success = dependencies.run_plots(
                    project_dir,
                    run_config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=force,
                    prefetcher=prefetcher,
                    athena=athena,
                )
                if not run_success:
                    dependencies.set_failure_context(
                        failure_context,
                        "EXECUTE",
                        f"Comparison plotting failed for condition {idx}/{total} ({label}).",
                    )
            if run_success and step in ("diagrams", "all"):
                run_success = dependencies.run_diagrams(
                    project_dir,
                    run_config,
                    build_state,
                    build_state_path,
                    config_hash,
                    force=force,
                    prefetcher=prefetcher,
                    athena=athena,
                )
                if not run_success:
                    dependencies.set_failure_context(
                        failure_context,
                        "EXECUTE",
                        f"Comparison diagram generation failed for condition {idx}/{total} ({label}).",
                    )

        status = "✅" if run_success else "❌"
        dependencies.log(f"   {status} Condition {idx}/{total} ({label}): {'OK' if run_success else 'FAILED'}")
        dependencies.log(f"      output_dir: {absolute_condition_dir}")

        if not run_success:
            all_success = False

    dependencies.log(f"\n{'=' * 60}")
    if all_success:
        dependencies.log(f"✅ Comparison completed: {total}/{total} conditions passed.")
        if overlay_output:
            dependencies.log(f"   overlay_output target: {os.path.join(project_dir, overlay_output)}")
            dependencies.log(
                "   (overlay assembly is delegated to the project's plot script via COMPARISON_LABEL env vars)"
            )
    else:
        dependencies.log("❌ Comparison finished with failures. Check output above.")
    return all_success
