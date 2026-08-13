from __future__ import annotations

import gzip
import hashlib
import inspect
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest

import offchain.market_data_control as api
import offchain.market_data_control.core as core_module
import offchain.market_data_control.custody as custody
from offchain.market_data_control import (
    AUTONOMY_CONTRACT_HASH,
    MISSION_CONTRACT_HASH,
    AcquisitionReceipt,
    AvailabilityClass,
    Catalogue,
    ClockHealth,
    ControlPlaneError,
    ObservationVersion,
    canonical_hash,
    certify_release,
    inspect_recovery,
    load_contracts,
    publish_synthetic_release,
    resolve_release,
    strict_json_load,
    validate_revision_chains,
)
from offchain.market_data_control.core import (
    FORWARD_AVAILABILITY_POLICY_ID,
    INTERVAL_MS,
    NORMALIZER_ID,
    canonical_json,
    deep_thaw,
    read_bounded_regular_file,
    sha256_bytes,
    strict_gzip_body,
)


ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = "f9a8e35c85bf736eedc21eb6ae3df0f788386e8f"
AUTONOMY_HASH = "b9b1d48dd3f65ac492b287e9d5dcebe11f69063138698bf37432c11869a3da5b"
MISSION_HASH = "159a822f77e3c6bf6409e04b2c25a61c5c7232cf6e73ea160ffb6cbf167d5d4c"
AUTONOMY_PATH = ROOT / "contracts" / "DELTAGRID_AUTONOMY_CONSTITUTION_V1.json"
MISSION_PATH = ROOT / "contracts" / "DELTAGRID_TEMPORAL_MARKET_DATA_CONTROL_PLANE_V1.json"


def _gzip(body: bytes) -> bytes:
    return gzip.compress(body, mtime=0)


def _receipt(
    index: int = 0,
    *,
    body: bytes | None = None,
    requested_at: str | None = None,
    received_at: str | None = None,
    monotonic_duration_ms: int = 100,
    clock_health: ClockHealth = ClockHealth.HEALTHY,
    http_status: int = 200,
    attempt_number: int = 1,
    retry_budget_exhausted: bool = False,
    retry_after_seconds: int | None = None,
) -> tuple[AcquisitionReceipt, bytes]:
    payload = body if body is not None else canonical_json({"fixture": index}).encode()
    compressed = _gzip(payload)
    from datetime import datetime, timedelta, timezone
    base = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index + 1)
    requested = requested_at or base.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    received = received_at or (base + timedelta(milliseconds=100)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    receipt = AcquisitionReceipt(
        request_id=f"fixture-request-{index}",
        provider="BINANCE_PUBLIC",
        host="data-api.binance.vision",
        method="GET",
        endpoint_path="/api/v3/klines",
        request_params={"symbol": "BTCUSDT", "interval": "1h", "fixture": index},
        requested_at=requested,
        received_at=received,
        monotonic_duration_ms=monotonic_duration_ms,
        clock_health=clock_health,
        http_status=http_status,
        response_headers={},
        request_weight={},
        retry_after_seconds=retry_after_seconds,
        attempt_number=attempt_number,
        retry_budget_exhausted=retry_budget_exhausted,
        body_sha256=sha256_bytes(payload),
        compressed_object_sha256=sha256_bytes(compressed),
        collector_id="synthetic-fixture-collector-v1",
        repository_commit=BASE_COMMIT,
    )
    return receipt, compressed


def _bar_observation(
    receipt: AcquisitionReceipt,
    index: int = 0,
    *,
    revision_number: int = 0,
    supersedes_record_hash: str | None = None,
    source_time: str | None = None,
    available_at: str | None = None,
    first_observed_at: str | None = None,
    last_verified_at: str | None = None,
    availability_class: AvailabilityClass = AvailabilityClass.OBSERVED_LIVE,
    availability_policy_id: str = FORWARD_AVAILABILITY_POLICY_ID,
    clock_health: ClockHealth = ClockHealth.HEALTHY,
    payload_extra: dict | None = None,
) -> ObservationVersion:
    period_start_ms = 1767225600000 + index * INTERVAL_MS  # 2026-01-01T00:00:00Z
    event_ms = period_start_ms + INTERVAL_MS - 1
    from datetime import datetime, timezone

    event_time = datetime.fromtimestamp(event_ms / 1000, tz=timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    observed = receipt.received_at
    payload = {"period_start_ms": period_start_ms, "close": str(100 + index)}
    if payload_extra:
        payload.update(payload_extra)
    return ObservationVersion(
        logical_id=(
            f"BINANCE_PUBLIC/spot_ohlcv/BTCUSDT/1h/{period_start_ms}"
        ),
        provider="BINANCE_PUBLIC",
        stream="spot_ohlcv",
        symbol="BTCUSDT",
        interval="1h",
        event_time=event_time,
        source_time=source_time or event_time,
        available_at=available_at if available_at is not None else (
            None if availability_class is AvailabilityClass.UNKNOWN else observed
        ),
        availability_class=availability_class,
        availability_policy_id=availability_policy_id,
        first_observed_at=first_observed_at or observed,
        last_verified_at=last_verified_at or observed,
        revision_number=revision_number,
        supersedes_record_hash=supersedes_record_hash,
        source_response_hash=receipt.source_response_hash,
        receipt_hash=receipt.receipt_hash,
        normalizer_id=NORMALIZER_ID,
        normalized_payload=payload,
        clock_health=clock_health,
    )


def _catalogue(tmp_path: Path, name: str = "runtime") -> Catalogue:
    return Catalogue.initialize(
        tmp_path / name,
        repository_root=ROOT,
        acknowledgement="INITIALIZE_RUNTIME",
    )


def _publish_one(
    catalogue: Catalogue,
    index: int = 0,
    *,
    parent_release_id: str | None = None,
) -> dict:
    receipt, raw = _receipt(index)
    observation = _bar_observation(receipt, index)
    return dict(
        publish_synthetic_release(
            catalogue=catalogue,
            observations=(observation,),
            receipts=(receipt,),
            raw_objects={receipt.compressed_object_sha256: raw},
            repository_commit=BASE_COMMIT,
            parent_release_id=parent_release_id,
        )
    )


def _release_dir(catalogue: Catalogue, result: dict) -> Path:
    return catalogue.runtime_root / result["relative_path"]


def _contract_core_hash(path: Path) -> str:
    value = json.loads(path.read_text())
    value.pop("contract_hash_sha256")
    return canonical_hash(value)


def test_contract_hashes_authority_and_deep_immutability() -> None:
    autonomy, mission = load_contracts()
    assert AUTONOMY_CONTRACT_HASH == AUTONOMY_HASH == _contract_core_hash(AUTONOMY_PATH)
    assert MISSION_CONTRACT_HASH == MISSION_HASH == _contract_core_hash(MISSION_PATH)
    assert all(value is False for value in autonomy["current_authority"].values())
    assert autonomy["proposal_activation_separation"]["permanent_self_authorization_prohibition"] is True
    assert mission["authorization_state"]["market_data_custody"] is True
    for field in (
        "live_refresh",
        "real_data_research_resolution",
        "strategy_authority",
        "performance_authority",
        "model_or_ml_authority",
        "signal_authority",
        "paper_trading",
        "live_trading",
        "exchange_access",
        "credential_access",
        "order_placement",
        "portfolio_authority",
        "capital_deployment",
        "profitability_claim",
        "self_authorization",
    ):
        assert mission["authorization_state"][field] is False
    with pytest.raises(TypeError):
        mission["authorization_state"]["capital_deployment"] = True
    with pytest.raises((AttributeError, TypeError)):
        mission["source_scope"]["symbols"].append("XRPUSDT")




def test_contract_alignment_rejects_drift_in_operational_claims() -> None:
    autonomy, mission = load_contracts()

    changed_autonomy = deep_thaw(autonomy)
    changed_autonomy["current_authority"]["capital_deployment"] = True
    with pytest.raises(ControlPlaneError, match="CONSTITUTION_CODE_CURRENT_AUTHORITY_MISMATCH"):
        core_module._verify_autonomy_code_alignment(changed_autonomy)

    changed_runtime = deep_thaw(mission)
    changed_runtime["runtime"]["publication_lock_is_security_sandbox"] = True
    with pytest.raises(ControlPlaneError, match="CONTRACT_CODE_RUNTIME_MISMATCH"):
        core_module._verify_contract_code_alignment(changed_runtime)

    changed_certifier = deep_thaw(mission)
    changed_certifier["certification"]["public_certifier_published_release_only"] = False
    with pytest.raises(ControlPlaneError, match="CONTRACT_CODE_CERTIFICATION_MISMATCH"):
        core_module._verify_contract_code_alignment(changed_certifier)

    changed_legacy = deep_thaw(mission)
    changed_legacy["legacy_build"]["re_runs_exact_audit_before_publication"] = False
    with pytest.raises(ControlPlaneError, match="CONTRACT_CODE_LEGACY_BUILD_MISMATCH"):
        core_module._verify_contract_code_alignment(changed_legacy)


def test_bounded_regular_file_reader_enforces_cap_and_final_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"abcdef")
    assert read_bounded_regular_file(source, maximum_bytes=6) == b"abcdef"
    with pytest.raises(ControlPlaneError, match="FILE_SIZE_LIMIT"):
        read_bounded_regular_file(source, maximum_bytes=5)

    link = tmp_path / "link.bin"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ControlPlaneError, match="FILE_INPUT_INVALID"):
        read_bounded_regular_file(link, maximum_bytes=6)


def test_strict_json_rejects_duplicates_nonfinite_and_too_deep() -> None:
    with pytest.raises(ControlPlaneError, match="JSON_DUPLICATE_KEY"):
        strict_json_load('{"x":1,"x":2}')
    with pytest.raises(ControlPlaneError, match="JSON_NON_FINITE_NUMBER"):
        strict_json_load('{"x":NaN}')
    value = "0"
    for _ in range(70):
        value = "[" + value + "]"
    with pytest.raises(ControlPlaneError, match="JSON_NESTING_LIMIT"):
        strict_json_load(value)


def test_contract_tamper_is_rejected(tmp_path: Path) -> None:
    autonomy = tmp_path / "autonomy.json"
    mission = tmp_path / "mission.json"
    autonomy.write_bytes(AUTONOMY_PATH.read_bytes())
    changed = json.loads(MISSION_PATH.read_text())
    changed["authorization_state"]["capital_deployment"] = True
    mission.write_text(json.dumps(changed))
    with pytest.raises(ControlPlaneError, match="MISSION_CONTRACT_HASH_MISMATCH"):
        load_contracts(autonomy, mission)


def test_receipt_is_deeply_immutable_and_round_trips() -> None:
    params = {"symbol": "BTCUSDT", "nested": {"items": [1, 2]}}
    body = b"fixture"
    raw = _gzip(body)
    receipt = AcquisitionReceipt(
        request_id="deep-freeze",
        provider="BINANCE_PUBLIC",
        host="data-api.binance.vision",
        method="GET",
        endpoint_path="/api/v3/klines",
        request_params=params,
        requested_at="2026-01-01T00:00:00.000Z",
        received_at="2026-01-01T00:00:00.100Z",
        monotonic_duration_ms=100,
        clock_health=ClockHealth.HEALTHY,
        http_status=200,
        response_headers={},
        request_weight={},
        retry_after_seconds=None,
        attempt_number=1,
        retry_budget_exhausted=False,
        body_sha256=sha256_bytes(body),
        compressed_object_sha256=sha256_bytes(raw),
        collector_id="fixture",
        repository_commit=BASE_COMMIT,
    )
    original_hash = receipt.receipt_hash
    params["nested"]["items"].append(3)
    assert deep_thaw(receipt.request_params)["nested"]["items"] == [1, 2]
    exported = receipt.as_dict()
    exported["request_params"]["nested"]["items"].append(99)
    assert receipt.receipt_hash == original_hash
    assert AcquisitionReceipt.from_dict(receipt.as_dict()) == receipt


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"received_at": "2025-12-31T23:59:59.999Z"}, "RECEIPT_TIME_REVERSED"),
        ({"monotonic_duration_ms": True}, "INTEGER_INVALID"),
        ({"retry_budget_exhausted": "false"}, "BOOLEAN_INVALID"),
        ({"http_status": 429, "retry_after_seconds": 2, "attempt_number": 4, "retry_budget_exhausted": False}, "RETRY_EXHAUSTION_INCONSISTENT"),
    ],
)
def test_receipt_strict_semantics(overrides: dict, reason: str) -> None:
    with pytest.raises(ControlPlaneError, match=reason):
        _receipt(0, **overrides)


def test_receipt_healthy_clock_duration_must_be_consistent() -> None:
    with pytest.raises(ControlPlaneError, match="CLOCK_DURATION_INCONSISTENT"):
        _receipt(0, monotonic_duration_ms=9000)


def test_observation_causality_bar_completion_and_deep_immutability() -> None:
    receipt, _raw = _receipt(1)
    record = _bar_observation(receipt, 1, payload_extra={"nested": {"values": [1, 2]}})
    payload = record.as_dict()["normalized_payload"]
    payload["nested"]["values"].append(3)
    assert record.as_dict()["normalized_payload"]["nested"]["values"] == [1, 2]

    with pytest.raises(ControlPlaneError, match="AVAILABILITY_PRECEDES_EVENT"):
        _bar_observation(receipt, 1, available_at="2026-01-01T01:30:00.000Z")
    with pytest.raises(ControlPlaneError, match="SOURCE_TIME_PRECEDES_EVENT"):
        _bar_observation(receipt, 1, source_time="2026-01-01T01:30:00.000Z")
    with pytest.raises(ControlPlaneError, match="FIRST_OBSERVATION_PRECEDES_EVENT"):
        _bar_observation(receipt, 1, first_observed_at="2026-01-01T01:30:00.000Z")


def test_unknown_availability_is_structurally_honest() -> None:
    receipt, _ = _receipt(2)
    record = _bar_observation(
        receipt,
        2,
        availability_class=AvailabilityClass.UNKNOWN,
        availability_policy_id="deltagrid-mission99-legacy-unknown-v1",
        available_at=None,
        clock_health=ClockHealth.UNKNOWN,
    )
    assert record.available_at is None
    with pytest.raises(ControlPlaneError, match="UNKNOWN_AVAILABILITY_HAS_TIME"):
        _bar_observation(
            receipt,
            2,
            availability_class=AvailabilityClass.UNKNOWN,
            availability_policy_id="deltagrid-mission99-legacy-unknown-v1",
            available_at=receipt.received_at,
            clock_health=ClockHealth.UNKNOWN,
        )


def test_revision_chain_is_idempotent_and_rejects_conflicts_and_regressions() -> None:
    r0, _ = _receipt(3)
    first = _bar_observation(r0, 3)
    assert validate_revision_chains((first, first)) == (first,)

    r1, _ = _receipt(4)
    second = _bar_observation(
        r1,
        3,
        revision_number=1,
        supersedes_record_hash=first.record_hash,
        first_observed_at=r1.received_at,
        last_verified_at=r1.received_at,
    )
    assert len(validate_revision_chains((second, first))) == 2

    conflict = _bar_observation(
        r1,
        3,
        revision_number=0,
        payload_extra={"different": True},
    )
    with pytest.raises(ControlPlaneError, match="REVISION_FORK"):
        validate_revision_chains((first, conflict))

    r_old, _ = _receipt(
        99,
        requested_at="2026-01-01T03:59:59.999Z",
        received_at="2026-01-01T04:00:00.000Z",
        monotonic_duration_ms=1,
    )
    regressing = _bar_observation(
        r_old,
        3,
        revision_number=1,
        supersedes_record_hash=first.record_hash,
        first_observed_at="2026-01-01T04:00:00.000Z",
        last_verified_at="2026-01-01T04:00:00.000Z",
    )
    with pytest.raises(ControlPlaneError, match="REVISION_TIME_REGRESSION"):
        validate_revision_chains((first, regressing))


def test_strict_gzip_rejects_plain_truncated_trailing_and_expansion() -> None:
    with pytest.raises(ControlPlaneError, match="GZIP_INVALID"):
        strict_gzip_body(b"plain", maximum_decompressed_bytes=100)
    good = _gzip(b"abc")
    with pytest.raises(ControlPlaneError, match="GZIP_INVALID"):
        strict_gzip_body(good[:-2], maximum_decompressed_bytes=100)
    with pytest.raises(ControlPlaneError, match="GZIP_INVALID"):
        strict_gzip_body(good + b"trailing", maximum_decompressed_bytes=100)
    with pytest.raises(ControlPlaneError, match="GZIP_DECOMPRESSED_SIZE_LIMIT"):
        strict_gzip_body(_gzip(b"x" * 101), maximum_decompressed_bytes=100)


def test_runtime_init_modes_containment_and_symlinks(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    assert (catalogue.runtime_root.stat().st_mode & 0o777) == 0o700
    assert (catalogue.path.stat().st_mode & 0o777) == 0o600
    assert (catalogue.lock_path.stat().st_mode & 0o777) == 0o600
    with pytest.raises(ControlPlaneError, match="RUNTIME_ROOT_INSIDE_REPOSITORY"):
        Catalogue.initialize(
            ROOT / "offchain" / "data" / "mission99",
            acknowledgement="INITIALIZE_RUNTIME",
        )
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ControlPlaneError, match="SYMLINK_REJECTED"):
        Catalogue.initialize(link, acknowledgement="INITIALIZE_RUNTIME")
    with pytest.raises(ControlPlaneError, match="EXECUTION_ACKNOWLEDGEMENT_REQUIRED"):
        Catalogue.initialize(tmp_path / "missing-ack")


def test_publish_certify_resolve_and_identity_are_deterministic(tmp_path: Path) -> None:
    first_catalogue = _catalogue(tmp_path, "a")
    second_catalogue = _catalogue(tmp_path, "b")
    receipt, raw = _receipt(5)
    observation = _bar_observation(receipt, 5)

    def publish(catalogue: Catalogue, observations: tuple[ObservationVersion, ...]) -> dict:
        return dict(
            publish_synthetic_release(
                catalogue=catalogue,
                observations=observations,
                receipts=(receipt, receipt),
                raw_objects={receipt.compressed_object_sha256: raw},
                repository_commit=BASE_COMMIT,
            )
        )

    one = publish(first_catalogue, (observation, observation))
    two = publish(second_catalogue, (observation,))
    assert one["release_id"] == two["release_id"]
    certificate = certify_release(_release_dir(first_catalogue, one), runtime_root=first_catalogue.runtime_root)
    assert certificate.release_id == one["release_id"]
    resolution = resolve_release(
        first_catalogue,
        one["release_id"],
        "2026-01-01T10:00:00.000Z",
        "SYNTHETIC_TEST_ONLY",
    )
    assert resolution.selected_record_hashes == (observation.record_hash,)



def test_resolution_hash_canonicalizes_equivalent_decision_timestamps(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    release = _publish_one(catalogue, 47)
    first = resolve_release(
        catalogue, release["release_id"], "2026-01-03T00:00:00Z", "SYNTHETIC_TEST_ONLY"
    )
    second = resolve_release(
        catalogue, release["release_id"], "2026-01-03T00:00:00.000Z", "SYNTHETIC_TEST_ONLY"
    )
    assert first.decision_time == second.decision_time == "2026-01-03T00:00:00.000Z"
    assert first.resolution_hash == second.resolution_hash


def test_raw_object_linkage_and_conflict_fail_closed(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    receipt, raw = _receipt(6)
    observation = _bar_observation(receipt, 6)
    with pytest.raises(ControlPlaneError, match="RAW_OBJECT_HASH_MISMATCH"):
        publish_synthetic_release(
            catalogue=catalogue,
            observations=(observation,),
            receipts=(receipt,),
            raw_objects={receipt.compressed_object_sha256: _gzip(b"different")},
            repository_commit=BASE_COMMIT,
        )
    with pytest.raises(ControlPlaneError, match="RAW_OBJECT_BYTES_REQUIRED"):
        publish_synthetic_release(
            catalogue=catalogue,
            observations=(observation,),
            receipts=(receipt,),
            raw_objects={},
            repository_commit=BASE_COMMIT,
        )



def test_observation_cannot_derive_from_failed_http_receipt(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    receipt, raw = _receipt(46, http_status=429, retry_after_seconds=2)
    observation = _bar_observation(receipt, 46)
    with pytest.raises(ControlPlaneError, match="OBSERVATION_SOURCE_HTTP_UNSUCCESSFUL"):
        publish_synthetic_release(
            catalogue=catalogue,
            observations=(observation,),
            receipts=(receipt,),
            raw_objects={receipt.compressed_object_sha256: raw},
            repository_commit=BASE_COMMIT,
        )


def test_observation_must_bind_exact_receipt(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    receipt, raw = _receipt(7)
    other, _ = _receipt(8)
    record = _bar_observation(receipt, 7)
    tampered = ObservationVersion.from_dict({**record.as_dict(), "receipt_hash": other.receipt_hash, "record_hash": ""})
    with pytest.raises(ControlPlaneError, match="OBSERVATION_RECEIPT_MISSING"):
        publish_synthetic_release(
            catalogue=catalogue,
            observations=(tampered,),
            receipts=(receipt,),
            raw_objects={receipt.compressed_object_sha256: raw},
            repository_commit=BASE_COMMIT,
        )


def test_certifier_rejects_missing_certificate_and_extra_sqlite_object(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path, "missing-cert")
    release = _publish_one(catalogue, 9)
    directory = _release_dir(catalogue, release)
    (directory / "certificate.json").unlink()
    with pytest.raises(ControlPlaneError, match="CERTIFICATE_FILE_MISSING"):
        certify_release(directory, runtime_root=catalogue.runtime_root)

    catalogue2 = _catalogue(tmp_path, "extra-view")
    release2 = _publish_one(catalogue2, 10)
    database = _release_dir(catalogue2, release2) / "release.sqlite3"
    conn = sqlite3.connect(database)
    try:
        conn.execute("CREATE VIEW unexpected_view AS SELECT 1 AS x")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ControlPlaneError, match="RELEASE_SQLITE_SCHEMA_INVALID"):
        certify_release(_release_dir(catalogue2, release2), runtime_root=catalogue2.runtime_root)


def test_certifier_rejects_extra_column_and_manifest_tamper(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path, "extra-column")
    release = _publish_one(catalogue, 11)
    database = _release_dir(catalogue, release) / "release.sqlite3"
    conn = sqlite3.connect(database)
    try:
        conn.execute("ALTER TABLE warnings ADD COLUMN unexpected TEXT")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ControlPlaneError, match="RELEASE_SQLITE_SCHEMA_INVALID"):
        certify_release(_release_dir(catalogue, release), runtime_root=catalogue.runtime_root)

    catalogue2 = _catalogue(tmp_path, "manifest-tamper")
    release2 = _publish_one(catalogue2, 12)
    manifest = _release_dir(catalogue2, release2) / "manifest.json"
    data = json.loads(manifest.read_text())
    data["manifest_core"]["release_id"] = "m99-" + "0" * 64
    manifest.write_text(canonical_json(data) + "\n")
    os.chmod(manifest, 0o600)
    with pytest.raises(ControlPlaneError):
        certify_release(_release_dir(catalogue2, release2), runtime_root=catalogue2.runtime_root)


def test_full_snapshot_child_preserves_parent_and_resolves_both(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    parent = _publish_one(catalogue, 13)
    child = _publish_one(catalogue, 14, parent_release_id=parent["release_id"])
    resolution = resolve_release(
        catalogue,
        child["release_id"],
        "2026-01-01T19:00:00.000Z",
        "SYNTHETIC_TEST_ONLY",
    )
    assert len(resolution.selected_record_hashes) == 2
    parent_cert = certify_release(_release_dir(catalogue, parent), runtime_root=catalogue.runtime_root)
    child_cert = certify_release(_release_dir(catalogue, child), runtime_root=catalogue.runtime_root)
    assert parent_cert.row_count == 1
    assert child_cert.row_count == 2


def test_child_snapshot_cannot_drop_parent_evidence(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    parent = _publish_one(catalogue, 15)
    child = _publish_one(catalogue, 16, parent_release_id=parent["release_id"])
    database = _release_dir(catalogue, child) / "release.sqlite3"
    conn = sqlite3.connect(database)
    try:
        first_hash = conn.execute("SELECT record_hash FROM observations ORDER BY record_hash LIMIT 1").fetchone()[0]
        conn.execute("DELETE FROM observations WHERE record_hash = ?", (first_hash,))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ControlPlaneError):
        certify_release(_release_dir(catalogue, child), runtime_root=catalogue.runtime_root)


def test_catalogue_path_escape_and_wrong_directory_are_rejected(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    release = _publish_one(catalogue, 17)
    conn = sqlite3.connect(catalogue.path)
    try:
        conn.execute(
            "UPDATE releases SET relative_path = ? WHERE release_id = ?",
            ("../escape", release["release_id"]),
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ControlPlaneError, match="CATALOGUE_PATH_INVALID"):
        catalogue.release(release["release_id"])


def test_resolver_denies_real_and_protected_stage_tokens(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    release = _publish_one(catalogue, 18)
    for stage in ("VALIDATION", "HOLDOUT", "PAPER", "LIVE", "CAPITAL"):
        with pytest.raises(ControlPlaneError):
            resolve_release(
                catalogue,
                release["release_id"],
                "2026-01-02T00:00:00.000Z",
                stage,
            )


def test_failure_injection_never_catalogues_incomplete_release(tmp_path: Path) -> None:
    before_catalogue = (
        "contracts_and_catalogue",
        "normalize_inputs",
        "persist_raw_objects",
        "write_release_database",
        "write_manifest",
        "staged_verification",
        "write_certificate",
        "verify_staged_complete",
        "before_atomic_rename",
        "after_atomic_rename",
        "before_catalogue_commit",
    )
    for index, failpoint in enumerate(before_catalogue):
        catalogue = _catalogue(tmp_path, f"fail-{index}")
        receipt, raw = _receipt(index)
        observation = _bar_observation(receipt, index)
        with pytest.raises(ControlPlaneError, match="INJECTED_PUBLICATION_FAILURE"):
            custody._Publisher(catalogue, failpoint=failpoint).publish(
                observations=(observation,),
                receipts=(receipt,),
                raw_objects={receipt.compressed_object_sha256: raw},
                parent_release_id=None,
                repository_commit=BASE_COMMIT,
                synthetic_fixture=True,
                warnings=(),
                quarantine=(),
                legacy_proof_hash=None,
            )
        assert catalogue.list_releases() == ()
        states = [item["state"] for item in inspect_recovery(catalogue)]
        assert states


def test_after_catalogue_commit_failure_leaves_only_valid_catalogued_release(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    receipt, raw = _receipt(1)
    observation = _bar_observation(receipt, 1)
    with pytest.raises(ControlPlaneError, match="INJECTED_PUBLICATION_FAILURE"):
        custody._Publisher(catalogue, failpoint="after_catalogue_commit").publish(
            observations=(observation,),
            receipts=(receipt,),
            raw_objects={receipt.compressed_object_sha256: raw},
            parent_release_id=None,
            repository_commit=BASE_COMMIT,
            synthetic_fixture=True,
            warnings=(),
            quarantine=(),
            legacy_proof_hash=None,
        )
    rows = catalogue.list_releases()
    assert len(rows) == 1
    certify_release(
        catalogue.runtime_root / rows[0]["relative_path"],
        runtime_root=catalogue.runtime_root,
    )


def test_publication_lock_is_process_visible(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    ready = tmp_path / "ready"
    code = (
        "import fcntl,time,pathlib,sys; "
        "f=open(sys.argv[1],'r+b'); fcntl.flock(f,fcntl.LOCK_EX); "
        "pathlib.Path(sys.argv[2]).write_text('ready'); time.sleep(3.2)"
    )
    process = subprocess.Popen([sys.executable, "-c", code, str(catalogue.lock_path), str(ready)])
    try:
        deadline = time.monotonic() + 2
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        with pytest.raises(ControlPlaneError, match="PUBLICATION_LOCK_BUSY"):
            with catalogue.publication_lock():
                pass
    finally:
        process.terminate()
        process.wait(timeout=5)


def _race_program() -> str:
    return r'''
import gzip,sys
from offchain.market_data_control import AcquisitionReceipt,AvailabilityClass,Catalogue,ClockHealth,ObservationVersion,ControlPlaneError,publish_synthetic_release
from offchain.market_data_control.core import NORMALIZER_ID,FORWARD_AVAILABILITY_POLICY_ID,sha256_bytes
runtime=sys.argv[1]; idx=int(sys.argv[2]); base="f9a8e35c85bf736eedc21eb6ae3df0f788386e8f"
body=("race-%d"%idx).encode(); raw=gzip.compress(body,mtime=0)
hour=idx+1
requested=f"2026-01-01T{hour:02d}:00:00.000Z"; received=f"2026-01-01T{hour:02d}:00:00.100Z"
r=AcquisitionReceipt(request_id=f"race-{idx}",provider="BINANCE_PUBLIC",host="data-api.binance.vision",method="GET",endpoint_path="/api/v3/klines",request_params={"fixture":idx},requested_at=requested,received_at=received,monotonic_duration_ms=100,clock_health=ClockHealth.HEALTHY,http_status=200,response_headers={},request_weight={},retry_after_seconds=None,attempt_number=1,retry_budget_exhausted=False,body_sha256=sha256_bytes(body),compressed_object_sha256=sha256_bytes(raw),collector_id="race",repository_commit=base)
start=1767225600000+idx*3600000; event=start+3599999
from datetime import datetime,timezone
event_text=datetime.fromtimestamp(event/1000,tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")
o=ObservationVersion(logical_id=f"BINANCE_PUBLIC/spot_ohlcv/BTCUSDT/1h/{start}",provider="BINANCE_PUBLIC",stream="spot_ohlcv",symbol="BTCUSDT",interval="1h",event_time=event_text,source_time=event_text,available_at=received,availability_class=AvailabilityClass.OBSERVED_LIVE,availability_policy_id=FORWARD_AVAILABILITY_POLICY_ID,first_observed_at=received,last_verified_at=received,revision_number=0,supersedes_record_hash=None,source_response_hash=r.source_response_hash,receipt_hash=r.receipt_hash,normalizer_id=NORMALIZER_ID,normalized_payload={"period_start_ms":start,"close":str(idx)},clock_health=ClockHealth.HEALTHY)
try:
 c=Catalogue(runtime)
 publish_synthetic_release(catalogue=c,observations=(o,),receipts=(r,),raw_objects={r.compressed_object_sha256:raw},repository_commit=base)
 print("OK")
except ControlPlaneError as e:
 print(e.reason)
 sys.exit(2)
'''


def test_two_process_publishers_cannot_exceed_release_limit(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    for index in range(3):
        _publish_one(catalogue, index)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    first = subprocess.Popen(
        [sys.executable, "-c", _race_program(), str(catalogue.runtime_root), "3"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    second = subprocess.Popen(
        [sys.executable, "-c", _race_program(), str(catalogue.runtime_root), "4"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    out1, err1 = first.communicate(timeout=20)
    out2, err2 = second.communicate(timeout=20)
    outputs = {out1.strip(), out2.strip()}
    assert outputs == {"OK", "RELEASE_COUNT_LIMIT"}, (out1, err1, out2, err2)
    assert len(catalogue.list_releases()) == 4


def test_recovery_does_not_treat_valid_staging_objects_as_orphan(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    receipt, raw = _receipt(0)
    observation = _bar_observation(receipt, 0)
    with pytest.raises(ControlPlaneError):
        custody._Publisher(catalogue, failpoint="write_certificate").publish(
            observations=(observation,),
            receipts=(receipt,),
            raw_objects={receipt.compressed_object_sha256: raw},
            parent_release_id=None,
            repository_commit=BASE_COMMIT,
            synthetic_fixture=True,
            warnings=(),
            quarantine=(),
            legacy_proof_hash=None,
        )
    states = inspect_recovery(catalogue)
    assert any(item["state"] == "VALID_STAGING_PRECERTIFICATE" for item in states)
    object_path = f"objects/sha256/{receipt.compressed_object_sha256[:2]}/{receipt.compressed_object_sha256}.gz"
    assert not any(
        item["path"] == object_path and item["state"].startswith("ORPHANED_RAW")
        for item in states
    )



def test_observation_rejects_availability_before_source_and_unhealthy_live() -> None:
    receipt, _raw = _receipt(1)
    with pytest.raises(ControlPlaneError, match="AVAILABILITY_PRECEDES_SOURCE"):
        _bar_observation(
            receipt,
            1,
            source_time="2026-01-01T02:00:00.050Z",
            available_at="2026-01-01T02:00:00.000Z",
        )
    with pytest.raises(ControlPlaneError, match="CLOCK_HEALTH_UNTRUSTWORTHY"):
        _bar_observation(receipt, 1, clock_health=ClockHealth.UNKNOWN)


def test_publish_accepts_one_shot_receipt_iterable_without_consuming_it(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    receipt, raw = _receipt(40)
    observation = _bar_observation(receipt, 40)
    result = publish_synthetic_release(
        catalogue=catalogue,
        observations=(observation,),
        receipts=(item for item in (receipt,)),
        raw_objects={receipt.compressed_object_sha256: raw},
        repository_commit=BASE_COMMIT,
    )
    assert result["certified"] is True


def test_raw_object_decompressed_body_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    original, raw = _receipt(41)
    receipt = AcquisitionReceipt(
        request_id=original.request_id,
        provider=original.provider,
        host=original.host,
        method=original.method,
        endpoint_path=original.endpoint_path,
        request_params=original.as_dict()["request_params"],
        requested_at=original.requested_at,
        received_at=original.received_at,
        monotonic_duration_ms=original.monotonic_duration_ms,
        clock_health=original.clock_health,
        http_status=original.http_status,
        response_headers=original.as_dict()["response_headers"],
        request_weight=original.as_dict()["request_weight"],
        retry_after_seconds=original.retry_after_seconds,
        attempt_number=original.attempt_number,
        retry_budget_exhausted=original.retry_budget_exhausted,
        body_sha256="0" * 64,
        compressed_object_sha256=original.compressed_object_sha256,
        collector_id=original.collector_id,
        repository_commit=original.repository_commit,
    )
    observation = _bar_observation(receipt, 41)
    with pytest.raises(ControlPlaneError, match="RAW_BODY_HASH_MISMATCH"):
        publish_synthetic_release(
            catalogue=catalogue,
            observations=(observation,),
            receipts=(receipt,),
            raw_objects={receipt.compressed_object_sha256: raw},
            repository_commit=BASE_COMMIT,
        )


def test_sqlite_readonly_uri_handles_reserved_and_unicode_path_characters(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path, "runtime space # ? é")
    result = _publish_one(catalogue, 42)
    certificate = certify_release(
        _release_dir(catalogue, result), runtime_root=catalogue.runtime_root
    )
    assert certificate.release_id == result["release_id"]


def test_runtime_initialization_fails_closed_when_directory_fsync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_fsync(_path: Path) -> None:
        raise ControlPlaneError("DIRECTORY_FSYNC_FAILED")

    monkeypatch.setattr(custody, "_fsync_directory", fail_fsync)
    with pytest.raises(ControlPlaneError, match="DIRECTORY_FSYNC_FAILED"):
        Catalogue.initialize(
            tmp_path / "fsync-failure",
            repository_root=ROOT,
            acknowledgement="INITIALIZE_RUNTIME",
        )


def test_after_rename_before_catalogue_is_explicit_orphan(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    receipt, raw = _receipt(43)
    observation = _bar_observation(receipt, 43)
    with pytest.raises(ControlPlaneError, match="INJECTED_PUBLICATION_FAILURE"):
        custody._Publisher(catalogue, failpoint="after_atomic_rename").publish(
            observations=(observation,),
            receipts=(receipt,),
            raw_objects={receipt.compressed_object_sha256: raw},
            parent_release_id=None,
            repository_commit=BASE_COMMIT,
            synthetic_fixture=True,
            warnings=(),
            quarantine=(),
            legacy_proof_hash=None,
        )
    assert catalogue.list_releases() == ()
    states = inspect_recovery(catalogue)
    assert any(item["state"] == "ORPHANED_COMPLETE_RELEASE" for item in states)


def test_child_certification_requires_parent_to_remain_catalogued(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    parent = _publish_one(catalogue, 44)
    child = _publish_one(catalogue, 45, parent_release_id=parent["release_id"])
    conn = sqlite3.connect(catalogue.path)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM releases WHERE release_id = ?", (parent["release_id"],))
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ControlPlaneError, match="PARENT_RELEASE_NOT_CATALOGUED"):
        certify_release(
            _release_dir(catalogue, child), runtime_root=catalogue.runtime_root
        )


def test_cli_failure_output_is_reason_only(capsys: pytest.CaptureFixture[str]) -> None:
    from offchain.market_data_control.__main__ import main

    assert main(["resolve"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"reason": "CLI_INPUT_INVALID"}


def test_public_api_has_no_general_real_publisher_or_network_trading_surface() -> None:
    assert not hasattr(api, "ReleasePublisher")
    assert "_Publisher" not in api.__all__
    assert "_legacy_authorized" not in (ROOT / "offchain/market_data_control/custody.py").read_text()
    forbidden = ("network", "collect", "exchange", "credential", "order", "trade", "capital", "strategy", "performance")
    public = {name.lower() for name in api.__all__}
    assert not any(any(token in name for token in forbidden) for name in public)
    assert "build_legacy_release" in public
    signature = inspect.signature(api.build_legacy_release)
    assert "execution_acknowledgement" in signature.parameters


def test_rights_notice_and_registry_include_public_operating_files() -> None:
    license_text = (ROOT / "LICENSE").read_text()
    readme = (ROOT / "README.md").read_text()
    assert "Copyright © 2026 Tushar Rawat" in license_text
    assert "All rights reserved" in license_text
    assert "not open source" in license_text.lower()
    assert "tushar142004@gmail.com" in license_text
    assert "[LICENSE](LICENSE)" in readme
    registry = json.loads((ROOT / "docs/documentation-status.json").read_text())
    entries = {item["path"]: item for item in registry["documents"]}
    assert entries["LICENSE"]["classification"] == "CURRENT_PUBLIC"
    assert entries["AGENTS.md"]["classification"] == "CURRENT_INTERNAL"
    assert len(registry["documents"]) == 211


def test_cli_source_exposes_init_and_no_collection_command() -> None:
    text = (ROOT / "offchain/market_data_control/__main__.py").read_text()
    assert 'add_parser("init-runtime")' in text
    assert 'add_parser("build-legacy-release")' in text
    assert 'add_parser("certify-release")' in text
    assert 'add_parser("resolve")' in text
    assert 'add_parser("collect")' not in text
    assert 'add_parser("refresh")' not in text


def test_public_certifier_rejects_staging_directory(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    receipt, raw = _receipt(60)
    observation = _bar_observation(receipt, 60)
    with pytest.raises(ControlPlaneError, match="INJECTED_PUBLICATION_FAILURE"):
        custody._Publisher(catalogue, failpoint="verify_staged_complete").publish(
            observations=(observation,),
            receipts=(receipt,),
            raw_objects={receipt.compressed_object_sha256: raw},
            parent_release_id=None,
            repository_commit=BASE_COMMIT,
            synthetic_fixture=True,
            warnings=(),
            quarantine=(),
            legacy_proof_hash=None,
        )
    stages = tuple((catalogue.runtime_root / "staging").iterdir())
    assert len(stages) == 1
    assert (stages[0] / "certificate.json").is_file()
    with pytest.raises(ControlPlaneError, match="PUBLISHED_RELEASE_REQUIRED"):
        certify_release(stages[0], runtime_root=catalogue.runtime_root)


def test_publication_rejects_receipt_repository_identity_mismatch(tmp_path: Path) -> None:
    catalogue = _catalogue(tmp_path)
    original, raw = _receipt(61)
    receipt = AcquisitionReceipt(
        request_id=original.request_id,
        provider=original.provider,
        host=original.host,
        method=original.method,
        endpoint_path=original.endpoint_path,
        request_params=original.as_dict()["request_params"],
        requested_at=original.requested_at,
        received_at=original.received_at,
        monotonic_duration_ms=original.monotonic_duration_ms,
        clock_health=original.clock_health,
        http_status=original.http_status,
        response_headers=original.as_dict()["response_headers"],
        request_weight=original.as_dict()["request_weight"],
        retry_after_seconds=original.retry_after_seconds,
        attempt_number=original.attempt_number,
        retry_budget_exhausted=original.retry_budget_exhausted,
        body_sha256=original.body_sha256,
        compressed_object_sha256=original.compressed_object_sha256,
        collector_id=original.collector_id,
        repository_commit="0" * 40,
    )
    observation = _bar_observation(receipt, 61)
    with pytest.raises(ControlPlaneError, match="RECEIPT_REPOSITORY_IDENTITY_MISMATCH"):
        publish_synthetic_release(
            catalogue=catalogue,
            observations=(observation,),
            receipts=(receipt,),
            raw_objects={receipt.compressed_object_sha256: raw},
            repository_commit=BASE_COMMIT,
        )


def test_observation_rejects_unversioned_normalizer_identity() -> None:
    receipt, _raw = _receipt(62)
    base = _bar_observation(receipt, 62).as_dict()
    base["normalizer_id"] = "different-normalizer-v1"
    base["record_hash"] = ""
    with pytest.raises(ControlPlaneError, match="NORMALIZER_ID_UNSUPPORTED"):
        ObservationVersion.from_dict(base)
