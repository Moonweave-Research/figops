from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from hub_core.atomic_no_clobber import AtomicNoClobberUnavailable
from hub_core.durable_promotion import (
    DurablePromotionError,
    promote_result_with_receipt,
    promote_runtime_artifact,
    verify_promoted_result,
)
from hub_core.durable_receipt import (
    DurableReceipt,
    opaque_artifact_id,
    opaque_claim_id,
    opaque_receipt_id,
)


def _receipt(digest: str) -> DurableReceipt:
    artifact = {
        "artifact_id": opaque_artifact_id("result.source_data", "calc-1"),
        "role": "result.source_data",
        "sha256": digest,
    }
    return DurableReceipt(
        figops_version="0.20.0",
        run_id=opaque_receipt_id("run", "run-1"),
        timestamp="2026-07-16T00:00:00Z",
        git_sha256="1" * 64,
        config_sha256="2" * 64,
        script_sha256="3" * 64,
        environment_lock_sha256="4" * 64,
        durable_artifact=artifact,
        input_artifacts=[
            {
                "artifact_id": opaque_artifact_id("raw", "raw-1"),
                "role": "raw",
                "sha256": "5" * 64,
            }
        ],
        output_artifacts=[artifact],
        claim_ids=[opaque_claim_id("claim:figure-1:p-value")],
        manifest_id=opaque_receipt_id("manifest", "manifest-a1b2"),
        manifest_sha256="6" * 64,
    )


def test_result_promotion_stages_on_destination_filesystem(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "external-runtime"
    runtime.mkdir()
    source = runtime / "jobs" / "render.png"
    source.parent.mkdir()
    source.write_bytes(b"rendered-result")
    destination = tmp_path / "project" / "results" / "figures" / "figure.png"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    import hub_core.durable_promotion as promotion

    real_move = promotion.atomic_no_clobber_move
    move_calls: list[tuple[Path, Path]] = []

    def reject_cross_volume_move(source_path, destination_path):
        staged = Path(source_path)
        target = Path(destination_path)
        move_calls.append((staged, target))
        if staged.parent.resolve() != target.parent.resolve():
            raise OSError("simulated EXDEV")
        real_move(staged, target)

    monkeypatch.setattr(promotion, "atomic_no_clobber_move", reject_cross_volume_move)
    promoted = promote_runtime_artifact(
        source,
        destination,
        runtime_root=runtime,
        expected_sha256=digest,
    )

    assert promoted.path == destination
    assert destination.read_bytes() == b"rendered-result"
    assert move_calls and move_calls[0][0].parent == destination.parent
    assert move_calls[0][0] != source


def test_promotion_race_never_clobbers_competing_destination(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"producer-owned")
    destination = tmp_path / "project" / "results" / "result.csv"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    import hub_core.durable_promotion as promotion

    real_move = promotion.atomic_no_clobber_move

    def create_competitor_before_publish(stage, target):
        Path(target).write_bytes(b"competitor-owned")
        real_move(stage, target)

    monkeypatch.setattr(promotion, "atomic_no_clobber_move", create_competitor_before_publish)
    with pytest.raises(DurablePromotionError, match="already exists"):
        promote_runtime_artifact(source, destination, runtime_root=runtime, expected_sha256=digest)

    assert destination.read_bytes() == b"competitor-owned"
    assert not list(destination.parent.glob(".result.csv.figops-stage-*"))


def test_promotion_unsupported_atomic_move_has_no_overwrite_fallback(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"producer-owned")
    destination = tmp_path / "project" / "results" / "result.csv"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    import hub_core.durable_promotion as promotion

    def unavailable(*_args):
        raise AtomicNoClobberUnavailable("unsupported")

    monkeypatch.setattr(promotion, "atomic_no_clobber_move", unavailable)
    with pytest.raises(DurablePromotionError, match="FIGOPS_ATOMIC_NO_CLOBBER_UNAVAILABLE"):
        promote_runtime_artifact(source, destination, runtime_root=runtime, expected_sha256=digest)

    assert not destination.exists()
    assert source.read_bytes() == b"producer-owned"
    assert not list(destination.parent.glob(".result.csv.figops-stage-*"))


def test_posix_prepublication_failure_directly_discards_owned_stage(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"producer-owned")
    destination = tmp_path / "project" / "results" / "result.csv"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    import hub_core.durable_promotion as promotion

    monkeypatch.setattr(
        promotion,
        "atomic_no_clobber_move",
        lambda *_args: (_ for _ in ()).throw(AtomicNoClobberUnavailable("darwin unavailable")),
    )
    monkeypatch.setattr(promotion, "delete_file_by_identity", lambda *_args, **_kwargs: False)

    with pytest.raises(DurablePromotionError, match="FIGOPS_ATOMIC_NO_CLOBBER_UNAVAILABLE"):
        promote_runtime_artifact(source, destination, runtime_root=runtime, expected_sha256=digest)

    assert not destination.exists()
    assert not list(destination.parent.glob(".result.csv.figops-stage-*"))


def test_permanent_stage_unlink_denial_cannot_leave_a_private_alias(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"producer-owned")
    destination = tmp_path / "project" / "results" / "result.csv"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    real_unlink = Path.unlink
    def deny_private_stage_unlink(path: Path, *args, **kwargs):
        if ".figops-stage-" in path.name:
            raise PermissionError("permanent retained-private-stage denial")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny_private_stage_unlink)
    promote_runtime_artifact(source, destination, runtime_root=runtime, expected_sha256=digest)

    assert destination.read_bytes() == b"producer-owned"
    assert not list(destination.parent.glob(".result.csv.figops-stage-*"))


def test_promotion_rejects_prepublication_private_hardlink_alias(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"producer-owned")
    destination = tmp_path / "project" / "results" / "result.csv"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    import hub_core.durable_promotion as promotion

    real_move = promotion.atomic_no_clobber_move
    alias = destination.parent / "attacker-alias.tmp"

    def add_alias_then_move(stage, target):
        os.link(stage, alias, follow_symlinks=False)
        real_move(stage, target)

    monkeypatch.setattr(promotion, "atomic_no_clobber_move", add_alias_then_move)
    with pytest.raises(DurablePromotionError, match="retained an alias"):
        promote_runtime_artifact(source, destination, runtime_root=runtime, expected_sha256=digest)

    assert not destination.exists()
    assert alias.read_bytes() == b"producer-owned"
    assert not list(destination.parent.glob(".result.csv.figops-stage-*"))


def test_posix_postpublication_verifier_failure_preserves_destination_for_manual_review(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"producer-owned")
    destination = tmp_path / "project" / "results" / "result.csv"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    import hub_core.durable_promotion as promotion

    real_move = promotion.atomic_no_clobber_move
    alias = destination.parent / "attacker-alias.tmp"

    def add_alias_then_move(stage, target):
        os.link(stage, alias, follow_symlinks=False)
        real_move(stage, target)

    monkeypatch.setattr(promotion, "atomic_no_clobber_move", add_alias_then_move)
    monkeypatch.setattr(promotion, "delete_file_by_identity", lambda *_args, **_kwargs: False)

    with pytest.raises(DurablePromotionError, match="FIGOPS_DURABLE_MANUAL_CLEANUP_REQUIRED"):
        promote_runtime_artifact(source, destination, runtime_root=runtime, expected_sha256=digest)

    assert destination.read_bytes() == b"producer-owned"
    assert alias.read_bytes() == b"producer-owned"
    assert not list(destination.parent.glob(".result.csv.figops-stage-*"))


def test_receipt_race_rolls_back_only_our_artifact(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"producer-owned")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    result = tmp_path / "project" / "results" / "result.csv"
    receipt_path = tmp_path / "project" / "results" / "result.receipt.json"

    import hub_core.durable_promotion as promotion

    real_move = promotion.atomic_no_clobber_move
    calls = 0

    def race_on_receipt(stage, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            Path(target).write_bytes(b"competitor-receipt")
        real_move(stage, target)

    monkeypatch.setattr(promotion, "atomic_no_clobber_move", race_on_receipt)
    expected_error = "already exists" if os.name == "nt" else "FIGOPS_DURABLE_MANUAL_CLEANUP_REQUIRED"
    with pytest.raises(DurablePromotionError, match=expected_error):
        promote_result_with_receipt(source, result, _receipt(digest), receipt_path, runtime_root=runtime)

    assert result.exists() is (os.name != "nt")
    assert receipt_path.read_bytes() == b"competitor-receipt"


def test_posix_receipt_race_keeps_published_artifact_and_discards_receipt_stage(
    tmp_path: Path, monkeypatch
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"producer-owned")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    result = tmp_path / "project" / "results" / "result.csv"
    receipt_path = tmp_path / "project" / "results" / "result.receipt.json"

    import hub_core.durable_promotion as promotion

    real_move = promotion.atomic_no_clobber_move
    calls = 0

    def race_on_receipt(stage, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            Path(target).write_bytes(b"competitor-receipt")
        real_move(stage, target)

    monkeypatch.setattr(promotion, "atomic_no_clobber_move", race_on_receipt)
    monkeypatch.setattr(promotion, "delete_file_by_identity", lambda *_args, **_kwargs: False)

    with pytest.raises(DurablePromotionError, match="FIGOPS_DURABLE_MANUAL_CLEANUP_REQUIRED"):
        promote_result_with_receipt(source, result, _receipt(digest), receipt_path, runtime_root=runtime)

    assert result.read_bytes() == b"producer-owned"
    assert receipt_path.read_bytes() == b"competitor-receipt"
    assert not list(result.parent.glob(".*.figops-stage-*"))


def test_receipt_failure_never_deletes_replacement_artifact(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"producer-owned")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    result = tmp_path / "project" / "results" / "result.csv"
    receipt_path = tmp_path / "project" / "results" / "result.receipt.json"

    import hub_core.durable_promotion as promotion

    real_move = promotion.atomic_no_clobber_move
    calls = 0

    def replace_artifact_then_race_receipt(stage, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            result.unlink()
            result.write_bytes(b"competitor-artifact")
            Path(target).write_bytes(b"competitor-receipt")
        real_move(stage, target)

    monkeypatch.setattr(promotion, "atomic_no_clobber_move", replace_artifact_then_race_receipt)
    with pytest.raises(DurablePromotionError, match="FIGOPS_DURABLE_MANUAL_CLEANUP_REQUIRED"):
        promote_result_with_receipt(source, result, _receipt(digest), receipt_path, runtime_root=runtime)

    assert result.read_bytes() == b"competitor-artifact"
    assert receipt_path.read_bytes() == b"competitor-receipt"


def test_artifact_rollback_hash_then_inode_swap_preserves_competitor(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"producer-owned")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    result = tmp_path / "project" / "results" / "result.csv"
    receipt_path = tmp_path / "project" / "results" / "result.receipt.json"

    import hub_core.durable_promotion as promotion

    real_move = promotion.atomic_no_clobber_move
    real_hash = promotion.file_sha256
    artifact_hash_calls = 0

    def race_receipt(stage, target):
        if Path(target) == receipt_path:
            receipt_path.write_bytes(b"competitor-receipt")
        real_move(stage, target)

    def swap_after_artifact_hash(path):
        nonlocal artifact_hash_calls
        observed = real_hash(path)
        if Path(path) == result:
            artifact_hash_calls += 1
            if artifact_hash_calls == 3:
                result.unlink()
                result.write_bytes(b"competitor-artifact-after-hash")
        return observed

    monkeypatch.setattr(promotion, "atomic_no_clobber_move", race_receipt)
    monkeypatch.setattr(promotion, "file_sha256", swap_after_artifact_hash)
    with pytest.raises(DurablePromotionError, match="FIGOPS_DURABLE_MANUAL_CLEANUP_REQUIRED"):
        promote_result_with_receipt(source, result, _receipt(digest), receipt_path, runtime_root=runtime)

    assert artifact_hash_calls >= 3
    assert result.read_bytes() == b"competitor-artifact-after-hash"
    assert receipt_path.read_bytes() == b"competitor-receipt"


def test_receipt_rollback_hash_then_inode_swap_preserves_competitor(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"producer-owned")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    result = tmp_path / "project" / "results" / "result.csv"
    receipt_path = tmp_path / "project" / "results" / "result.receipt.json"

    import hub_core.durable_promotion as promotion

    real_hash = promotion.file_sha256
    artifact_hash_calls = 0
    receipt_hash_calls = 0

    def force_failure_then_swap_receipt_after_cleanup_hash(path):
        nonlocal artifact_hash_calls, receipt_hash_calls
        target = Path(path)
        observed = real_hash(path)
        if target == result:
            artifact_hash_calls += 1
            if artifact_hash_calls == 3:
                return "0" * 64
        elif target == receipt_path:
            receipt_hash_calls += 1
            if receipt_hash_calls == 3:
                receipt_path.unlink()
                receipt_path.write_bytes(b"competitor-receipt-after-hash")
        return observed

    monkeypatch.setattr(promotion, "file_sha256", force_failure_then_swap_receipt_after_cleanup_hash)
    with pytest.raises(DurablePromotionError, match="FIGOPS_DURABLE_MANUAL_CLEANUP_REQUIRED"):
        promote_result_with_receipt(source, result, _receipt(digest), receipt_path, runtime_root=runtime)

    assert receipt_hash_calls >= 3
    assert receipt_path.read_bytes() == b"competitor-receipt-after-hash"
    if os.name == "nt":
        assert not result.exists()


def test_receipt_and_result_verify_after_runtime_tree_deletion(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "jobs" / "calculation.json"
    source.parent.mkdir()
    source.write_bytes(b'{"estimate":1.25}')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    result = tmp_path / "project" / "results" / "source_data" / "calculation.json"
    receipt_path = tmp_path / "project" / "results" / "evidence" / "calculation.receipt.json"

    promote_result_with_receipt(
        source,
        result,
        _receipt(digest),
        receipt_path,
        runtime_root=runtime,
    )
    shutil.rmtree(runtime)

    verified = verify_promoted_result(
        result,
        receipt_path,
        durable_root=tmp_path / "project" / "results",
        forbidden_roots=(runtime,),
    )
    assert verified.durable_artifact["sha256"] == digest
    assert str(runtime).encode() not in receipt_path.read_bytes()


def test_promoted_result_tamper_fails_closed(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"x\n1\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    result = tmp_path / "project" / "results" / "source_data" / "result.csv"
    receipt_path = tmp_path / "project" / "results" / "evidence" / "result.receipt.json"
    promote_result_with_receipt(source, result, _receipt(digest), receipt_path, runtime_root=runtime)

    result.write_bytes(b"x\n999\n")

    with pytest.raises(DurablePromotionError, match="hash"):
        verify_promoted_result(
            result,
            receipt_path,
            durable_root=tmp_path / "project" / "results",
            forbidden_roots=(runtime,),
        )


def test_promotion_rejects_producer_hash_mismatch(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "result.csv"
    source.write_bytes(b"x\n1\n")

    with pytest.raises(DurablePromotionError, match="producer declaration"):
        promote_runtime_artifact(
            source,
            tmp_path / "project" / "results" / "result.csv",
            runtime_root=runtime,
            expected_sha256="0" * 64,
        )


def _promoted_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    runtime = tmp_path / "runtime"
    runtime.mkdir(parents=True)
    source = runtime / "result.csv"
    source.write_bytes(b"x\n1\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    durable_root = tmp_path / "project" / "results"
    result = durable_root / "source_data" / "result.csv"
    receipt_path = durable_root / "evidence" / "result.receipt.json"
    promote_result_with_receipt(source, result, _receipt(digest), receipt_path, runtime_root=runtime)
    return runtime, durable_root, result, receipt_path


@pytest.mark.parametrize("target_name", ["artifact", "receipt"])
def test_verify_rejects_symlink_even_when_target_bytes_are_valid(
    tmp_path: Path, target_name: str
) -> None:
    runtime, durable_root, artifact, receipt = _promoted_fixture(tmp_path)
    selected = artifact if target_name == "artifact" else receipt
    external = tmp_path / f"external-{selected.name}"
    external.write_bytes(selected.read_bytes())
    selected.unlink()
    try:
        selected.symlink_to(external)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(DurablePromotionError, match="FIGOPS_DURABLE_VERIFY_BOUNDARY"):
        verify_promoted_result(
            artifact,
            receipt,
            durable_root=durable_root,
            forbidden_roots=(runtime,),
        )


def test_verify_rejects_forbidden_runtime_overlap(tmp_path: Path) -> None:
    runtime, durable_root, artifact, receipt = _promoted_fixture(tmp_path)

    with pytest.raises(DurablePromotionError, match="FIGOPS_DURABLE_VERIFY_BOUNDARY"):
        verify_promoted_result(
            artifact,
            receipt,
            durable_root=durable_root,
            forbidden_roots=(tmp_path / "project", runtime),
        )


def test_verify_detects_file_swap_between_snapshot_and_open(tmp_path: Path, monkeypatch) -> None:
    runtime, durable_root, artifact, receipt = _promoted_fixture(tmp_path)
    replacement = tmp_path / "replacement.csv"
    replacement.write_bytes(artifact.read_bytes())

    import hub_core.durable_promotion as promotion

    real_open = promotion.os.open
    swapped = False

    def swap_before_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if Path(path) == artifact.resolve() and not swapped:
            swapped = True
            artifact.unlink()
            replacement.replace(artifact)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(promotion.os, "open", swap_before_open)
    with pytest.raises(DurablePromotionError, match="FIGOPS_DURABLE_VERIFY_CHANGED"):
        verify_promoted_result(
            artifact,
            receipt,
            durable_root=durable_root,
            forbidden_roots=(runtime,),
        )


@pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-specific")
def test_verify_rejects_durable_root_junction_to_valid_external_bytes(tmp_path: Path) -> None:
    runtime, real_root, artifact, receipt = _promoted_fixture(tmp_path / "real")
    junction = tmp_path / "declared-results"
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(real_root)],
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.skip("directory junction creation is unavailable")
    try:
        with pytest.raises(DurablePromotionError, match="FIGOPS_DURABLE_VERIFY_BOUNDARY"):
            verify_promoted_result(
                junction / artifact.relative_to(real_root),
                junction / receipt.relative_to(real_root),
                durable_root=junction,
                forbidden_roots=(runtime,),
            )
    finally:
        subprocess.run(["cmd", "/c", "rmdir", str(junction)], check=False, capture_output=True)
