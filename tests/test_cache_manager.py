import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hub_core.cache_manager import (
    CACHE_STRATEGY_MTIME,
    _empty_build_state,
    cache_strategy_from_config,
    file_signature,
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


def test_default_signature_detects_same_size_content_change_with_preserved_mtime(tmp_path: Path):
    source = tmp_path / "input.csv"
    source.write_bytes(b"alpha")
    original_stat = source.stat()

    before = file_signature(source, tmp_path)
    source.write_bytes(b"bravo")
    os.utime(source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    after = file_signature(source, tmp_path)

    assert "content_hash" in before
    assert "mtime_ns" not in before
    assert before["size"] == after["size"]
    assert before["content_hash"] != after["content_hash"]


def test_mtime_strategy_remains_explicit_opt_in(tmp_path: Path):
    source = tmp_path / "immutable.csv"
    source.write_text("x\n1\n", encoding="utf-8")

    signature = file_signature(source, tmp_path, cache_strategy=CACHE_STRATEGY_MTIME)

    assert "mtime_ns" in signature
    assert "content_hash" not in signature


def test_cache_strategy_from_config_defaults_to_content_hash_and_validates_opt_out():
    assert cache_strategy_from_config({}) == "content_hash"
    assert cache_strategy_from_config({"execution": {"cache_strategy": "MTIME"}}) == "mtime"

    with pytest.raises(ValueError, match="cache_strategy"):
        cache_strategy_from_config({"execution": {"cache_strategy": "fast"}})
