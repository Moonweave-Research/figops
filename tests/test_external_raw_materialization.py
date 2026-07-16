from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from hub_core.external_raw import ExternalRawError, verify_external_raw_materialization


def _descriptor(payload: bytes, *, access_class: str | None = None) -> dict[str, str]:
    descriptor = {
        "id": "instrument-run-42",
        "path": "exports/run-42.csv",
        "allowed_root": "lab-exports",
        "version": "etag-42",
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    if access_class:
        descriptor["access_class"] = access_class
    return descriptor


def test_external_raw_post_prefetch_hash_mismatch_fails(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    runtime = tmp_path / "runtime"
    allowed.mkdir()
    runtime.mkdir()
    materialized = runtime / "materialized" / "run-42.csv"
    materialized.parent.mkdir()
    materialized.write_bytes(b"tampered-after-prefetch")

    with pytest.raises(ExternalRawError, match="do not match"):
        verify_external_raw_materialization(
            _descriptor(b"original-source"),
            materialized,
            runtime_root=runtime,
            allowed_roots={"lab-exports": allowed},
        )


def test_sensitive_external_raw_is_metadata_only_and_never_copied_to_results(tmp_path: Path) -> None:
    secret = b"patient_id,value\nP-SECRET,7\n"
    allowed = tmp_path / "allowed"
    runtime = tmp_path / "runtime"
    results = tmp_path / "project" / "results" / "publication"
    (allowed / "exports").mkdir(parents=True)
    runtime.mkdir()
    materialized = runtime / "materialized" / "run-42.csv"
    materialized.parent.mkdir()
    materialized.write_bytes(secret)

    verified = verify_external_raw_materialization(
        _descriptor(secret, access_class="restricted"),
        materialized,
        runtime_root=runtime,
        allowed_roots={"lab-exports": allowed},
    )
    metadata = verified.durable_metadata()

    assert metadata["content_included"] is False
    assert "locator" not in metadata
    assert "materialized_path" not in metadata
    assert "sample" not in metadata
    assert b"P-SECRET" not in repr(metadata).encode()
    assert not results.exists()


def test_external_raw_materialization_must_remain_under_runtime(tmp_path: Path) -> None:
    payload = b"x\n1\n"
    allowed = tmp_path / "allowed"
    runtime = tmp_path / "runtime"
    allowed.mkdir()
    runtime.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_bytes(payload)

    with pytest.raises(ExternalRawError, match="runtime root"):
        verify_external_raw_materialization(
            _descriptor(payload),
            outside,
            runtime_root=runtime,
            allowed_roots={"lab-exports": allowed},
        )
