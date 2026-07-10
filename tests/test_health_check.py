from __future__ import annotations

from hub_core.health_check import required_r_runners, run_preflight_check


def test_required_r_runners_skips_r_for_python_plot_only_pipeline() -> None:
    # Given: a plot-only project whose selected figure is Python.
    config = {
        "execution": {"rscript": "configured-rscript"},
        "figures": [{"script": "plot.py", "lang": "python"}],
        "pipeline": {"analysis": [{"script": "analyze.R", "lang": "r"}]},
    }

    # When: determining R requirements for the plot step.
    runners = required_r_runners(config, "plot")

    # Then: no R executable is required.
    assert runners == ()


def test_required_r_runners_uses_configured_analysis_runner_once() -> None:
    # Given: multiple selected R analysis scripts with one configured runner.
    config = {
        "execution": {"rscript": "configured-rscript"},
        "pipeline": {
            "analysis": [
                {"script": "first.R", "lang": "r"},
                {"script": "second.R", "lang": "r"},
                {"domain_helper": "materials_polymer.signal_smooth_baseline"},
            ]
        },
    }

    # When: determining R requirements for analysis.
    runners = required_r_runners(config, "analysis")

    # Then: the configured runner is checked exactly once and helpers are excluded.
    assert runners == ("configured-rscript",)


def test_run_preflight_check_skips_r_when_no_selected_runner(monkeypatch) -> None:
    # Given: Python and environment checks pass, and an empty R runner selection.
    monkeypatch.setattr("hub_core.health_check.check_python", lambda: (True, "Python OK"))
    monkeypatch.setattr("hub_core.health_check.check_env_vars", lambda: (True, "Environment OK", False))
    monkeypatch.setattr(
        "hub_core.health_check.check_r",
        lambda _runner: (_ for _ in ()).throw(AssertionError("R must not be checked")),
    )

    # When: the selective preflight runs.
    result = run_preflight_check(exit_on_failure=False, rscript_commands=())

    # Then: it succeeds without invoking the R probe.
    assert result is True
