import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hub_core.cache_manager import (
    _empty_build_state,
    is_step_stale,
    record_step_state,
)


def _make_output(path: str, exists: bool = True) -> dict:
    sig = {"path": path, "exists": exists, "size": 100, "mtime_ns": 1234567890}
    if not exists:
        sig.pop("size")
        sig.pop("mtime_ns")
    return sig


def test_stale_no_prior_record():
    state = _empty_build_state()
    output_sigs = [_make_output("out/fig1.png")]
    stale, reason = is_step_stale("figures", "fig1", "sig_abc", output_sigs, state, "hash1")
    assert stale is True
    assert reason == "no previous build record"


def test_fresh_identical_signature():
    state = _empty_build_state()
    output_sigs = [_make_output("out/fig1.png")]
    record_step_state(state, "figures", "fig1", "sig_abc", output_sigs, "hash1")
    stale, reason = is_step_stale("figures", "fig1", "sig_abc", output_sigs, state, "hash1")
    assert stale is False
    assert reason == "unchanged"


def test_stale_script_signature_changed():
    state = _empty_build_state()
    output_sigs = [_make_output("out/fig1.png")]
    record_step_state(state, "figures", "fig1", "sig_old", output_sigs, "hash1")
    stale, reason = is_step_stale("figures", "fig1", "sig_new", output_sigs, state, "hash1")
    assert stale is True
    assert reason == "script/input signature changed"


def test_stale_output_missing():
    state = _empty_build_state()
    output_sigs_recorded = [_make_output("out/fig1.png", exists=True)]
    record_step_state(state, "figures", "fig1", "sig_abc", output_sigs_recorded, "hash1")
    output_sigs_current = [_make_output("out/fig1.png", exists=False)]
    stale, reason = is_step_stale("figures", "fig1", "sig_abc", output_sigs_current, state, "hash1")
    assert stale is True
    assert reason.startswith("missing outputs:")
    assert "out/fig1.png" in reason


def test_stale_config_hash_changed():
    state = _empty_build_state()
    output_sigs = [_make_output("out/fig1.png")]
    record_step_state(state, "figures", "fig1", "sig_abc", output_sigs, "abc123")
    stale, reason = is_step_stale("figures", "fig1", "sig_abc", output_sigs, state, "xyz999")
    assert stale is True
    assert reason == "project_config.yaml modified"


def test_stale_force_flag():
    state = _empty_build_state()
    output_sigs = [_make_output("out/fig1.png")]
    record_step_state(state, "figures", "fig1", "sig_abc", output_sigs, "hash1")
    stale, reason = is_step_stale("figures", "fig1", "sig_abc", output_sigs, state, "hash1", force=True)
    assert stale is True
    assert reason == "forced by --force"


def test_stale_one_of_multiple_outputs_missing():
    state = _empty_build_state()
    output_sigs_recorded = [_make_output("out/fig1.png"), _make_output("out/fig2.pdf")]
    record_step_state(state, "figures", "multi", "sig_abc", output_sigs_recorded, "hash1")
    output_sigs_current = [_make_output("out/fig1.png"), _make_output("out/fig2.pdf", exists=False)]
    stale, reason = is_step_stale("figures", "multi", "sig_abc", output_sigs_current, state, "hash1")
    assert stale is True
    assert "out/fig2.pdf" in reason
