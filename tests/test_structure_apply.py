from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from hub_core.atomic_no_clobber import AtomicNoClobberUnavailable
from hub_core.structure_apply import apply_structure_plan
from hub_core.structure_plan import build_structure_plan, confirmation_token


def _plan(root: Path) -> dict:
    return build_structure_plan(
        root,
        [{"source": "legacy/input.csv", "destination": "raw/input.csv", "role": "raw"}],
    )


def test_copy_apply_requires_matching_token_and_preserves_original(tmp_path: Path) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"a,b\n1,2\n")
    plan = _plan(tmp_path)

    with pytest.raises(PermissionError):
        apply_structure_plan(plan, confirmation_token="wrong")
    result = apply_structure_plan(plan, confirmation_token=confirmation_token(plan))

    assert result["originals_preserved"] is True
    assert source.read_bytes() == b"a,b\n1,2\n"
    assert (tmp_path / "raw" / "input.csv").read_bytes() == source.read_bytes()


def test_apply_rejects_stale_source_collision_and_unresolved_reference(tmp_path: Path) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"original")
    stale = _plan(tmp_path)
    source.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="changed after review"):
        apply_structure_plan(stale, confirmation_token=confirmation_token(stale))

    source.write_bytes(b"original")
    collision = _plan(tmp_path)
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "input.csv").write_bytes(b"user-owned")
    with pytest.raises(FileExistsError):
        apply_structure_plan(collision, confirmation_token=confirmation_token(collision))

    (tmp_path / "raw" / "input.csv").unlink()
    unresolved = build_structure_plan(
        tmp_path,
        [{"source": "legacy/input.csv", "destination": "raw/input.csv", "role": "raw"}],
        hardcoded_unresolved_references=["scripts/analyze.py: raw path"],
    )
    with pytest.raises(RuntimeError, match="hard-coded"):
        apply_structure_plan(unresolved, confirmation_token=confirmation_token(unresolved))


def test_apply_race_never_clobbers_competing_destination(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"planned-source")
    plan = _plan(tmp_path)

    import hub_core.structure_apply as structure_apply

    real_move = structure_apply.atomic_no_clobber_move

    def create_competitor_before_publish(stage, destination):
        Path(destination).write_bytes(b"competitor-owned")
        real_move(stage, destination)

    monkeypatch.setattr(structure_apply, "atomic_no_clobber_move", create_competitor_before_publish)
    with pytest.raises(FileExistsError, match="appeared during apply"):
        apply_structure_plan(plan, confirmation_token=confirmation_token(plan))

    assert (tmp_path / "raw" / "input.csv").read_bytes() == b"competitor-owned"
    assert source.read_bytes() == b"planned-source"
    assert not list((tmp_path / "raw").glob(".input.csv.figops-*.tmp"))


def test_apply_unsupported_atomic_move_has_no_overwrite_fallback(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"planned-source")
    plan = _plan(tmp_path)

    import hub_core.structure_apply as structure_apply

    def unavailable(*_args):
        raise AtomicNoClobberUnavailable("unsupported")

    monkeypatch.setattr(structure_apply, "atomic_no_clobber_move", unavailable)
    with pytest.raises(RuntimeError, match="FIGOPS_ATOMIC_NO_CLOBBER_UNAVAILABLE"):
        apply_structure_plan(plan, confirmation_token=confirmation_token(plan))

    assert not (tmp_path / "raw" / "input.csv").exists()
    assert source.read_bytes() == b"planned-source"
    assert not list((tmp_path / "raw").glob(".input.csv.figops-*.tmp"))


def test_posix_prepublication_failure_discards_owned_structure_stage(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"planned-source")
    plan = _plan(tmp_path)

    import hub_core.structure_apply as structure_apply

    def unavailable(*_args):
        raise AtomicNoClobberUnavailable("darwin unavailable")

    monkeypatch.setattr(structure_apply, "atomic_no_clobber_move", unavailable)
    monkeypatch.setattr(structure_apply, "delete_file_by_identity", lambda *_args, **_kwargs: False)

    with pytest.raises(RuntimeError, match="FIGOPS_ATOMIC_NO_CLOBBER_UNAVAILABLE"):
        apply_structure_plan(plan, confirmation_token=confirmation_token(plan))

    assert not (tmp_path / "raw" / "input.csv").exists()
    assert not list((tmp_path / "raw").glob(".input.csv.figops-*.tmp"))


def test_posix_post_apply_failure_preserves_published_copy_for_manual_review(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"planned-source")
    plan = _plan(tmp_path)
    destination = tmp_path / "raw" / "input.csv"

    import hub_core.structure_apply as structure_apply

    monkeypatch.setattr(structure_apply, "delete_file_by_identity", lambda *_args, **_kwargs: False)

    with pytest.raises(RuntimeError, match="FIGOPS_STRUCTURE_MANUAL_CLEANUP_REQUIRED"):
        apply_structure_plan(
            plan,
            confirmation_token=confirmation_token(plan),
            post_apply_verifier=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("verification failed")
            ),
        )

    assert destination.read_bytes() == b"planned-source"
    assert source.read_bytes() == b"planned-source"


def test_rollback_never_deletes_replacement_destination(tmp_path: Path) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"planned-source")
    plan = _plan(tmp_path)
    destination = tmp_path / "raw" / "input.csv"

    def replace_then_reject(_root: Path, _plan: dict) -> dict:
        destination.unlink()
        destination.write_bytes(b"competitor-owned")
        raise RuntimeError("verification failed")

    with pytest.raises(RuntimeError, match="FIGOPS_STRUCTURE_MANUAL_CLEANUP_REQUIRED"):
        apply_structure_plan(
            plan,
            confirmation_token=confirmation_token(plan),
            post_apply_verifier=replace_then_reject,
        )

    assert destination.read_bytes() == b"competitor-owned"
    assert source.read_bytes() == b"planned-source"


def test_structure_rollback_hash_then_inode_swap_preserves_competitor(tmp_path: Path, monkeypatch) -> None:
    import hub_core.structure_apply as structure_apply

    destination = tmp_path / "raw" / "input.csv"
    destination.parent.mkdir()
    destination.write_bytes(b"transaction-owned")
    expected_hash = structure_apply._sha256(destination)
    identity = structure_apply._file_identity(destination)
    real_hash = structure_apply._sha256
    swapped = False

    def swap_after_hash(path: Path) -> str:
        nonlocal swapped
        observed = real_hash(path)
        if Path(path) == destination and not swapped:
            swapped = True
            destination.unlink()
            destination.write_bytes(b"competitor-after-hash")
        return observed

    monkeypatch.setattr(structure_apply, "_sha256", swap_after_hash)
    structure_apply._remove_if_owned(destination, expected_hash, identity)

    assert swapped is True
    assert destination.read_bytes() == b"competitor-after-hash"


def test_typed_config_cas_receipt_and_verifier_failure_rollback(tmp_path: Path) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"original")
    config = tmp_path / "project_config.yaml"
    original_config = b"structure:\n  roots:\n    raw: legacy\n"
    config.write_bytes(original_config)
    plan = build_structure_plan(
        tmp_path,
        [{"source": "legacy/input.csv", "destination": "raw/input.csv", "role": "raw"}],
        config_diff=[{"path": ["structure", "roots", "raw"], "before": "legacy", "after": "raw"}],
    )

    def reject(_root: Path, _plan: dict) -> dict:
        assert "raw: raw" in config.read_text(encoding="utf-8")
        raise RuntimeError("verification failed")

    expected_error = "verification failed" if os.name == "nt" else "FIGOPS_STRUCTURE_MANUAL_CLEANUP_REQUIRED"
    with pytest.raises(RuntimeError, match=expected_error):
        apply_structure_plan(plan, confirmation_token=confirmation_token(plan), post_apply_verifier=reject)
    assert config.read_bytes() == original_config
    assert source.read_bytes() == b"original"
    if os.name == "nt":
        assert not (tmp_path / "raw" / "input.csv").exists()
        assert not list(tmp_path.glob("*.bak"))
    else:
        assert (tmp_path / "raw" / "input.csv").read_bytes() == b"original"
        (tmp_path / "raw" / "input.csv").unlink()
        for private_path in tmp_path.glob(".project_config.yaml.figops-*"):
            private_path.unlink()

    result = apply_structure_plan(
        plan,
        confirmation_token=confirmation_token(plan),
        post_apply_verifier=lambda _root, _plan: {"status": "passed"},
    )
    receipt = result["provenance_receipt"]
    assert receipt["copies"][0]["role"] == "raw"
    assert receipt["verification"] == {"status": "passed"}
    assert receipt["config"]["before_sha256"] != receipt["config"]["after_sha256"]


def test_apply_rejects_same_bytes_source_identity_swap(tmp_path: Path) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"same-bytes")
    plan = _plan(tmp_path)
    external = tmp_path / "external.csv"
    external.write_bytes(b"same-bytes")
    source.unlink()
    os.link(external, source)

    with pytest.raises(RuntimeError, match="source identity changed"):
        apply_structure_plan(plan, confirmation_token=confirmation_token(plan))

    assert not (tmp_path / "raw" / "input.csv").exists()
    assert external.read_bytes() == b"same-bytes"


def test_apply_binds_role_to_declared_custom_root(tmp_path: Path) -> None:
    from hub_core.structure_contract_types import CURRENT_CONTRACT, DEFAULT_V11_ROOTS

    roots = dict(DEFAULT_V11_ROOTS)
    roots["raw"] = "inputs/original"
    config = tmp_path / "project_config.yaml"
    config.write_text(
        yaml.safe_dump({"structure": {"contract": CURRENT_CONTRACT, "roots": roots}}, sort_keys=False),
        encoding="utf-8",
    )
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"planned")
    plan = build_structure_plan(
        tmp_path,
        [{"source": "legacy/input.csv", "destination": "raw/input.csv", "role": "raw"}],
    )

    with pytest.raises(ValueError, match="resolved 'raw' role root"):
        apply_structure_plan(plan, confirmation_token=confirmation_token(plan))

    assert not (tmp_path / "raw" / "input.csv").exists()


def test_config_compare_and_swap_preserves_racing_writer(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"original")
    config = tmp_path / "project_config.yaml"
    config.write_text("structure:\n  roots:\n    raw: legacy\n", encoding="utf-8")
    plan = build_structure_plan(
        tmp_path,
        [{"source": "legacy/input.csv", "destination": "raw/input.csv", "role": "raw"}],
        config_diff=[{"path": ["structure", "roots", "raw"], "before": "legacy", "after": "raw"}],
    )
    competitor = b"project: {name: competitor-owned}\n"

    import hub_core.structure_apply as structure_apply

    real_move = structure_apply.atomic_no_clobber_move
    injected = False

    def inject_before_cas(source_path, destination_path):
        nonlocal injected
        if Path(source_path) == config and str(destination_path).endswith(".cas") and not injected:
            injected = True
            config.write_bytes(competitor)
        return real_move(source_path, destination_path)

    monkeypatch.setattr(structure_apply, "atomic_no_clobber_move", inject_before_cas)
    expected_error = (
        "changed at compare-and-swap"
        if os.name == "nt"
        else "FIGOPS_STRUCTURE_MANUAL_CLEANUP_REQUIRED"
    )
    with pytest.raises(RuntimeError, match=expected_error):
        apply_structure_plan(plan, confirmation_token=confirmation_token(plan))

    assert config.read_bytes() == competitor
    assert (tmp_path / "raw" / "input.csv").exists() is (os.name != "nt")


def test_permanent_stage_unlink_denial_cannot_leave_a_private_alias(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"planned-source")
    plan = _plan(tmp_path)

    real_unlink = Path.unlink

    def refuse_private_stage(path: Path, *args, **kwargs):
        if path.name.endswith(".tmp") and ".figops-" in path.name:
            raise PermissionError("permanent private-stage deletion denial")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", refuse_private_stage)
    apply_structure_plan(plan, confirmation_token=confirmation_token(plan))

    assert (tmp_path / "raw" / "input.csv").read_bytes() == b"planned-source"
    assert source.read_bytes() == b"planned-source"
    assert not list((tmp_path / "raw").glob(".input.csv.figops-*.tmp"))


@pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-specific")
def test_apply_rejects_source_parent_replaced_by_windows_junction(tmp_path: Path) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"planned-source")
    plan = _plan(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    (external / "input.csv").write_bytes(b"planned-source")
    source.unlink()
    source.parent.rmdir()
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(source.parent), str(external)],
        capture_output=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip("Windows junction creation is unavailable")
    try:
        with pytest.raises(RuntimeError, match="unsafe directory|reparse point"):
            apply_structure_plan(plan, confirmation_token=confirmation_token(plan))
        assert not (tmp_path / "raw" / "input.csv").exists()
        assert (external / "input.csv").read_bytes() == b"planned-source"
    finally:
        subprocess.run(["cmd", "/c", "rmdir", str(source.parent)], check=False)


@pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-specific")
def test_apply_rechecks_destination_parent_at_write_time(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"planned-source")
    plan = _plan(tmp_path)
    external = tmp_path / "external-destination"
    external.mkdir()

    import hub_core.structure_apply as structure_apply

    real_stage_copy = structure_apply._stage_copy
    replaced = False

    def replace_parent_before_write(*args, **kwargs):
        nonlocal replaced
        if not replaced:
            replaced = True
            raw = tmp_path / "raw"
            raw.rmdir()
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(raw), str(external)],
                capture_output=True,
                check=False,
            )
            if created.returncode != 0:
                pytest.skip("Windows junction creation is unavailable")
        return real_stage_copy(*args, **kwargs)

    monkeypatch.setattr(structure_apply, "_stage_copy", replace_parent_before_write)
    try:
        with pytest.raises(PermissionError):
            apply_structure_plan(plan, confirmation_token=confirmation_token(plan))
        assert list(external.iterdir()) == []
    finally:
        raw = tmp_path / "raw"
        if raw.is_junction():
            subprocess.run(["cmd", "/c", "rmdir", str(raw)], check=False)


@pytest.mark.skipif(os.name != "nt", reason="directory junctions are Windows-specific")
def test_publish_detects_parent_swap_inside_atomic_move(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"planned-source")
    plan = _plan(tmp_path)
    external = tmp_path / "external-publish"
    external.mkdir()
    held = tmp_path / "held-raw"

    import hub_core.structure_apply as structure_apply

    real_move = structure_apply.atomic_no_clobber_move
    injected = False

    def swap_parent_during_move(stage, destination):
        nonlocal injected
        if not injected and Path(destination).name == "input.csv":
            injected = True
            raw = Path(stage).parent
            raw.rename(held)
            created = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(raw), str(external)],
                capture_output=True,
                check=False,
            )
            if created.returncode != 0:
                held.rename(raw)
                pytest.skip("Windows junction creation is unavailable")
            (external / Path(stage).name).write_bytes(b"attacker-stage")
        return real_move(stage, destination)

    monkeypatch.setattr(structure_apply, "atomic_no_clobber_move", swap_parent_during_move)
    try:
        with pytest.raises((PermissionError, RuntimeError)):
            apply_structure_plan(plan, confirmation_token=confirmation_token(plan))
        assert not (external / "input.csv").exists()
        assert list(external.iterdir()) == []
    finally:
        raw = tmp_path / "raw"
        if raw.is_junction():
            subprocess.run(["cmd", "/c", "rmdir", str(raw)], check=False)
        if held.exists() and not raw.exists():
            held.rename(raw)


def test_config_open_handle_mutation_is_preserved_and_aborts_commit(tmp_path: Path) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"original")
    config = tmp_path / "project_config.yaml"
    original = b"structure:\n  roots:\n    raw: legacy\n"
    config.write_bytes(original)
    plan = build_structure_plan(
        tmp_path,
        [{"source": "legacy/input.csv", "destination": "raw/input.csv", "role": "raw"}],
        config_diff=[{"path": ["structure", "roots", "raw"], "before": "legacy", "after": "raw"}],
    )
    competitor = b"project: {name: open-handle-writer}\n"

    with config.open("r+b") as held_config:

        def mutate_original_inode(_root: Path, _plan: dict) -> dict:
            held_config.seek(0)
            held_config.write(competitor)
            held_config.truncate()
            held_config.flush()
            os.fsync(held_config.fileno())
            return {"status": "passed"}

        expected_error = "open handle" if os.name == "nt" else "FIGOPS_STRUCTURE_MANUAL_CLEANUP_REQUIRED"
        with pytest.raises(RuntimeError, match=expected_error):
            apply_structure_plan(
                plan,
                confirmation_token=confirmation_token(plan),
                post_apply_verifier=mutate_original_inode,
            )

    # Windows denies the CAS rename while a non-delete-sharing handle is open,
    # so the transaction fails before invoking the verifier. POSIX permits the
    # rename and detects the held-inode mutation at finalization instead.
    assert config.read_bytes() == (original if os.name == "nt" else competitor)
    assert (tmp_path / "raw" / "input.csv").exists() is (os.name != "nt")


def test_publish_rejects_private_hardlink_alias(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "legacy" / "input.csv"
    source.parent.mkdir()
    source.write_bytes(b"planned-source")
    plan = _plan(tmp_path)

    import hub_core.structure_apply as structure_apply

    real_move = structure_apply.atomic_no_clobber_move
    alias = tmp_path / "raw" / "attacker-alias.tmp"
    injected = False

    def add_alias(stage, destination):
        nonlocal injected
        if not injected and Path(destination).name == "input.csv":
            injected = True
            os.link(stage, alias, follow_symlinks=False)
        real_move(stage, destination)

    monkeypatch.setattr(structure_apply, "atomic_no_clobber_move", add_alias)
    with pytest.raises(RuntimeError, match="retained an alias"):
        apply_structure_plan(plan, confirmation_token=confirmation_token(plan))

    assert (tmp_path / "raw" / "input.csv").exists() is (os.name != "nt")
    assert alias.read_bytes() == b"planned-source"
