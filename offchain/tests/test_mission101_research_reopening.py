from __future__ import annotations

from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import threading
import zipfile

import pytest

from offchain.market_data_acquisition import backup, journal, service
from offchain.research.admission import AdmissionError, TrialLedger
from offchain.research.reopening import (
    ACK_BUILD_RELEASE,
    ACK_INITIALIZE_AUTHORITY,
    ACK_ISSUE_PERMIT,
    ACK_REVOKE_PERMIT,
    ACK_REGISTER_BUDGET,
    ACK_WRITE_DESCRIPTOR,
    DevelopmentAdmissionService,
    ReopeningError,
    build_admission_request,
    build_development_dataset_descriptor,
    build_forward_release,
    certify_forward_release,
    initialize_authority_runtime,
    inspect_authority_runtime,
    inspect_source_backup,
    issue_development_permit,
    load_certified_release_metadata,
    open_development_trial_ledger,
    register_development_budget,
    revoke_development_permit,
    verify_development_dataset_descriptor,
    verify_development_permit,
    write_development_dataset_descriptor,
)
from offchain.research.reopening import authority as authority_module
from offchain.research.reopening import bridge as bridge_module
from offchain.research.reopening import __main__ as cli_module
from offchain.research.reopening import core as core_module
from offchain.research.reopening import dataset as dataset_module
from offchain.research.reopening.core import (
    AUTONOMY_V3_HASH,
    MISSION101_HASH,
    MISSION101_ID,
    canonical_hash,
    canonical_json,
)
from offchain.tests.test_forward_market_data_acquisition import FakeOpener


ROOT = Path(__file__).resolve().parents[2]
M100_COMPATIBLE_COMMIT = "3d5fff9043ee4686e75b95c5b28c44e6e2928313"


def _repository_observer(
    *, head: str = M100_COMPATIBLE_COMMIT, clean: bool = True, root: Path = ROOT
):
    return lambda: {"repository_root": str(root), "head": head, "clean": clean}


def _contract(path: str) -> dict:
    return json.loads((ROOT / "contracts" / path).read_text(encoding="utf-8"))


def _contract_hash(value: dict) -> str:
    core = dict(value)
    core.pop("contract_hash_sha256")
    return canonical_hash(core)


@pytest.fixture(scope="module")
def source_backup(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("m101-source").resolve()
    runtime = root / "runtime"
    old_journal_identity = journal.repository_identity
    old_service_identity = service.repository_identity
    journal.repository_identity = lambda repository_root=None: M100_COMPATIBLE_COMMIT
    service.repository_identity = lambda repository_root=None: M100_COMPATIBLE_COMMIT
    try:
        journal.initialize_runtime(runtime)
        with pytest.raises(Exception):
            service._capture_once_with_transport(
                runtime,
                acknowledgement=service.ACK_CAPTURE,
                opener=FakeOpener(fail_path="/fapi/v1/markPriceKlines"),
            )
        result = service._capture_once_with_transport(
            runtime,
            acknowledgement=service.ACK_CAPTURE,
            opener=FakeOpener(),
        )
        assert result.status == "COMPLETE"
        revised = service._capture_once_with_transport(
            runtime,
            acknowledgement=service.ACK_CAPTURE,
            opener=FakeOpener(correction=True),
        )
        assert revised.status == "COMPLETE"
        destination = root / "source.zip"
        backup.export_backup(runtime, destination, acknowledgement=backup.ACK_BACKUP)
        return destination
    finally:
        journal.repository_identity = old_journal_identity
        service.repository_identity = old_service_identity


def _utc_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@pytest.fixture
def chain(tmp_path: Path, source_backup: Path) -> dict:
    temp = tmp_path.resolve()
    custody_root = temp / "custody"
    custody_root.mkdir(mode=0o700)
    release = build_forward_release(source_backup, custody_root, acknowledgement=ACK_BUILD_RELEASE)
    release_directory = custody_root / "releases" / release["release_id"]
    _certificate, core = load_certified_release_metadata(release_directory, runtime_root=custody_root)
    records = [item for item in core["custody_records"] if item["stream"] == "spot_ohlcv" and item["symbol"] == "BTCUSDT"]
    descriptor = build_development_dataset_descriptor(
        release_directory,
        runtime_root=custody_root,
        provider="BINANCE_PUBLIC",
        symbols=["BTCUSDT"],
        streams=["spot_ohlcv"],
        temporal_start=_utc_ms(min(item["event_time_ms"] for item in records)),
        temporal_end_as_of=_utc_ms(max(item["event_time_ms"] for item in records)),
        causal_availability_cutoff=max(item["available_at"] for item in records),
        provenance_reference="synthetic:mission101-acceptance",
    )
    authority_root = temp / "authority"
    initialize_authority_runtime(authority_root, acknowledgement=ACK_INITIALIZE_AUTHORITY)
    now = datetime.now(timezone.utc)
    issued_at = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    as_of = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    expires_at = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    permit = issue_development_permit(
        authority_root,
        descriptor=descriptor,
        release_directory=release_directory,
        custody_runtime_root=custody_root,
        experiment_family="M101_METADATA_ONLY_FAMILY",
        fixed_trial_budget=2,
        expires_at=expires_at,
        acknowledgement=ACK_ISSUE_PERMIT,
        repository_observer=_repository_observer(),
        time_provider=lambda: issued_at,
    )
    ledger_path = temp / "trial-ledger" / "trials.sqlite3"
    register_development_budget(
        ledger_path,
        budget_id="m101-budget",
        experiment_family="M101_METADATA_ONLY_FAMILY",
        total_trial_budget=2,
        created_at=issued_at,
        acknowledgement=ACK_REGISTER_BUDGET,
    )
    ledger = open_development_trial_ledger(ledger_path)
    request = build_admission_request(
        request_id="m101-request-1",
        repository_commit=M100_COMPATIBLE_COMMIT,
        repository_clean=True,
        budget_id="m101-budget",
        declared_trial_number=1,
        dataset_id=descriptor["dataset_id"],
        dataset_descriptor_hash=descriptor["canonical_descriptor_hash"],
        data_class="REAL_MARKET_DEVELOPMENT",
        split_identity="REAL_MARKET_DEVELOPMENT",
        permit_id=permit["permit_id"],
        permit_hash=permit["canonical_permit_hash"],
        experiment_family="M101_METADATA_ONLY_FAMILY",
        authorization_stage="MISSION_101_DEVELOPMENT_ADMISSION",
        initiated_by="OPERATOR",
        created_at=as_of,
    )
    admission = DevelopmentAdmissionService(
        descriptor=descriptor,
        release_directory=str(release_directory),
        custody_runtime_root=str(custody_root),
        authority_root=str(authority_root),
        trial_ledger=ledger,
        time_provider=lambda: as_of,
        repository_observer=_repository_observer(),
    )
    return locals()


def _private_ledger(
    chain: dict, name: str, budget_id: str, total: int
) -> TrialLedger:
    path = chain["temp"] / name / "trials.sqlite3"
    register_development_budget(
        path,
        budget_id=budget_id,
        experiment_family="M101_METADATA_ONLY_FAMILY",
        total_trial_budget=total,
        created_at=chain["issued_at"],
        acknowledgement=ACK_REGISTER_BUDGET,
    )
    return open_development_trial_ledger(path)


def _permit_with_budget(chain: dict, fixed_trial_budget: int) -> dict:
    return issue_development_permit(
        chain["authority_root"],
        descriptor=chain["descriptor"],
        release_directory=chain["release_directory"],
        custody_runtime_root=chain["custody_root"],
        experiment_family="M101_METADATA_ONLY_FAMILY",
        fixed_trial_budget=fixed_trial_budget,
        expires_at=chain["expires_at"],
        acknowledgement=ACK_ISSUE_PERMIT,
        repository_observer=_repository_observer(),
        time_provider=lambda: chain["issued_at"],
    )


def _request_for(
    chain: dict,
    permit: dict,
    *,
    request_id: str,
    budget_id: str,
    created_at: str | None = None,
) -> dict:
    return build_admission_request(
        request_id=request_id,
        repository_commit=M100_COMPATIBLE_COMMIT,
        repository_clean=True,
        budget_id=budget_id,
        declared_trial_number=1,
        dataset_id=chain["descriptor"]["dataset_id"],
        dataset_descriptor_hash=chain["descriptor"]["canonical_descriptor_hash"],
        data_class="REAL_MARKET_DEVELOPMENT",
        split_identity="REAL_MARKET_DEVELOPMENT",
        permit_id=permit["permit_id"],
        permit_hash=permit["canonical_permit_hash"],
        experiment_family="M101_METADATA_ONLY_FAMILY",
        authorization_stage="MISSION_101_DEVELOPMENT_ADMISSION",
        initiated_by="OPERATOR",
        created_at=created_at or chain["as_of"],
    )


def _admission_service(
    chain: dict, ledger: TrialLedger, *, decision_time: str | None = None
) -> DevelopmentAdmissionService:
    return DevelopmentAdmissionService(
        descriptor=chain["descriptor"],
        release_directory=str(chain["release_directory"]),
        custody_runtime_root=str(chain["custody_root"]),
        authority_root=str(chain["authority_root"]),
        trial_ledger=ledger,
        time_provider=lambda: decision_time or chain["as_of"],
        repository_observer=_repository_observer(),
    )


def _rewrite_member(source: Path, destination: Path, member_name: str, transform) -> Path:
    with zipfile.ZipFile(source, "r") as archive:
        members = {item.filename: archive.read(item) for item in archive.infolist()}
    members[member_name] = transform(members[member_name])
    manifest = json.loads(members["manifest.json"])
    if member_name != "manifest.json":
        entry = next(item for item in manifest["files"] if item["path"] == member_name)
        entry["size"] = len(members[member_name])
        entry["sha256"] = hashlib.sha256(members[member_name]).hexdigest()
        core = dict(manifest)
        core.pop("manifest_hash")
        manifest["manifest_hash"] = canonical_hash(core)
        members["manifest.json"] = (canonical_json(manifest) + "\n").encode()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    return destination


def _mutate_sqlite_backup(source: Path, destination: Path, tmp_path: Path, statement: str) -> Path:
    with zipfile.ZipFile(source, "r") as archive:
        database = tmp_path / "mutated.sqlite3"
        database.write_bytes(archive.read("acquisition.sqlite3"))
    conn = sqlite3.connect(database)
    try:
        conn.execute(statement)
        conn.commit()
    finally:
        conn.close()
    return _rewrite_member(source, destination, "acquisition.sqlite3", lambda _raw: database.read_bytes())


def _rehash_mapping(value: dict, hash_field: str) -> dict:
    core = dict(value)
    core.pop(hash_field)
    value[hash_field] = canonical_hash(core)
    return value


def test_contract_v3_lineage_hash_and_narrow_authority() -> None:
    v1 = _contract("DELTAGRID_AUTONOMY_CONSTITUTION_V1.json")
    v2 = _contract("DELTAGRID_AUTONOMY_CONSTITUTION_V2.json")
    v3 = _contract("DELTAGRID_AUTONOMY_CONSTITUTION_V3.json")
    mission = _contract("DELTAGRID_RESEARCH_REOPENING_GOVERNANCE_V1.json")
    assert _contract_hash(v1) == v1["contract_hash_sha256"] == "b9b1d48dd3f65ac492b287e9d5dcebe11f69063138698bf37432c11869a3da5b"
    assert _contract_hash(v2) == v2["contract_hash_sha256"] == "a9d830e14ad1d93efbfd7529e9ee937926d577aeb63792acf900fbc80d968664"
    assert _contract_hash(v3) == v3["contract_hash_sha256"] == AUTONOMY_V3_HASH
    assert v3["parent_constitution_hash_sha256"] == v2["contract_hash_sha256"]
    assert _contract_hash(mission) == mission["contract_hash_sha256"] == MISSION101_HASH
    authority = mission["authority"]
    assert all(authority[key] for key in ("forward_custody_bridge", "development_dataset_descriptor", "development_permit_machinery", "development_admission_machinery"))
    assert not any(authority[key] for key in ("result_bearing_research_execution", "validation", "holdout", "model_or_ml", "signals", "paper", "live", "exchange_access", "credential_access", "orders", "capital", "self_authorization"))


def test_valid_backup_is_independently_verified_and_preserves_provenance(source_backup: Path) -> None:
    evidence = inspect_source_backup(source_backup)
    facts = evidence["source_facts"]
    assert evidence["admissible_observation_count"] > 0
    assert evidence["failed_batch_count"] == 1
    assert facts["source_mission100_contract_hash"] == "42f1ebe86264268763978d6969c2a605924805433a041647f2625dfd297e16e3"
    assert facts["source_attests_mission100_remediation_contract_hash"] is False
    assert facts["code_commits"] == [M100_COMPATIBLE_COMMIT]
    assert facts["receipt_hashes"] and facts["response_hashes"] and facts["source_record_hashes"]
    assert all(item["source_m100_record_hash"] != item["custody_record_hash"] for item in evidence["custody_records"])
    assert all(item["available_at"] == item["first_observed_at"] for item in evidence["custody_records"])
    assert all(item["clock_health"] == "HEALTHY" and item["availability_class"] == "OBSERVED_LIVE" for item in evidence["custody_records"])


@pytest.mark.parametrize("raw", [b"not-a-zip", b"PK\x03\x04truncated"])
def test_malformed_zip_rejected(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "bad.zip"
    path.write_bytes(raw)
    with pytest.raises(ReopeningError):
        inspect_source_backup(path.resolve())


def test_duplicate_traversal_and_unexpected_members_rejected(tmp_path: Path, source_backup: Path) -> None:
    with zipfile.ZipFile(source_backup, "r") as source:
        values = [(item.filename, source.read(item)) for item in source.infolist()]
    duplicate = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(duplicate, "w") as archive:
        for name, raw in values:
            archive.writestr(name, raw)
        archive.writestr(values[0][0], values[0][1])
    with pytest.raises(ReopeningError, match="BACKUP_DUPLICATE_MEMBER"):
        inspect_source_backup(duplicate.resolve())
    for name in ("../escape", "unexpected.bin", "/absolute"):
        path = tmp_path / (name.replace("/", "_") + ".zip")
        with zipfile.ZipFile(path, "w") as archive:
            for existing, raw in values:
                archive.writestr(existing, raw)
            archive.writestr(name, b"x")
        with pytest.raises(ReopeningError):
            inspect_source_backup(path.resolve())


def test_source_must_be_bounded_regular_backup_not_runtime_or_symlink(tmp_path: Path, source_backup: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ReopeningError, match="BACKUP_INPUT_INVALID"):
        inspect_source_backup(source_backup.parent)
    link = tmp_path / "source-link.zip"
    link.symlink_to(source_backup)
    with pytest.raises(ReopeningError, match="BACKUP_INPUT_SYMLINK"):
        inspect_source_backup(link.absolute())
    monkeypatch.setattr(bridge_module, "MAX_ARCHIVE_BYTES", 1)
    with pytest.raises(ReopeningError, match="BACKUP_ARCHIVE_SIZE_LIMIT"):
        inspect_source_backup(source_backup)


def test_manifest_hash_size_and_file_hash_mismatches_rejected(tmp_path: Path, source_backup: Path) -> None:
    manifest_bad = _rewrite_member(source_backup, tmp_path / "manifest.zip", "manifest.json", lambda raw: raw.replace(b'"schema_version":"1.0"', b'"schema_version":"9.0"'))
    with pytest.raises(ReopeningError):
        inspect_source_backup(manifest_bad.resolve())
    with zipfile.ZipFile(source_backup, "r") as archive:
        members = {item.filename: archive.read(item) for item in archive.infolist()}
    manifest = json.loads(members["manifest.json"])
    manifest["files"][0]["size"] += 1
    core = dict(manifest); core.pop("manifest_hash"); manifest["manifest_hash"] = canonical_hash(core)
    members["manifest.json"] = (canonical_json(manifest) + "\n").encode()
    path = tmp_path / "size.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, raw in members.items(): archive.writestr(name, raw)
    with pytest.raises(ReopeningError, match="BACKUP_FILE_SIZE_MISMATCH"):
        inspect_source_backup(path.resolve())


def test_malformed_and_wrong_schema_sqlite_rejected(tmp_path: Path, source_backup: Path) -> None:
    malformed = _rewrite_member(source_backup, tmp_path / "malformed.zip", "acquisition.sqlite3", lambda _raw: b"not sqlite")
    with pytest.raises(ReopeningError):
        inspect_source_backup(malformed.resolve())
    extra_view = _mutate_sqlite_backup(source_backup, tmp_path / "schema.zip", tmp_path, "CREATE VIEW unexpected_view AS SELECT 1")
    with pytest.raises(ReopeningError):
        inspect_source_backup(extra_view.resolve())


def test_running_batch_and_incompatible_code_lineage_fail_closed(tmp_path: Path, source_backup: Path) -> None:
    running = _mutate_sqlite_backup(source_backup, tmp_path / "running.zip", tmp_path, "UPDATE capture_batches SET status='RUNNING' WHERE status='COMPLETE'")
    with pytest.raises(ReopeningError, match="INCOMPLETE_CAPTURE_BATCH_PRESENT"):
        inspect_source_backup(running.resolve())
    incompatible = _mutate_sqlite_backup(source_backup, tmp_path / "commit.zip", tmp_path, "UPDATE capture_batches SET code_commit='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'")
    with pytest.raises(ReopeningError, match="SOURCE_CODE_LINEAGE_INCOMPATIBLE"):
        inspect_source_backup(incompatible.resolve())


def test_reviewed_48fc_documentation_only_descendant_is_source_compatible(
    tmp_path: Path, source_backup: Path
) -> None:
    reviewed_commit = "48fc8bfd69792dbef00145e9f76c7e13a064d918"
    reviewed = _mutate_sqlite_backup(
        source_backup,
        tmp_path / "reviewed-48fc.zip",
        tmp_path,
        f"UPDATE capture_batches SET code_commit='{reviewed_commit}'",
    )
    evidence = inspect_source_backup(reviewed)
    assert evidence["source_facts"]["code_commits"] == [reviewed_commit]
    assert evidence["compatibility_review"]["verdict"] == "PASS"
    assert evidence["source_facts"]["source_attests_mission100_remediation_contract_hash"] is False
    policy = _contract("DELTAGRID_RESEARCH_REOPENING_GOVERNANCE_V1.json")[
        "source_code_compatibility_policy"
    ]
    assert reviewed_commit in policy["allowed_code_commits"]
    assert policy["reviewed_relationships"][reviewed_commit].startswith(
        "DOCUMENTATION_ONLY_DESCENDANT"
    )


@pytest.mark.parametrize("statement", [
    "UPDATE observations SET supersedes_record_hash='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' WHERE revision_number>1",
    "UPDATE observations SET available_at='1970-01-01T00:00:00.000Z'",
    "UPDATE receipts SET clock_status='DEGRADED' WHERE clock_status='HEALTHY'",
    "UPDATE observations SET response_hash='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'",
])
def test_temporal_revision_and_identity_tampering_rejected(tmp_path: Path, source_backup: Path, statement: str) -> None:
    path = _mutate_sqlite_backup(source_backup, tmp_path / (hashlib.sha256(statement.encode()).hexdigest() + ".zip"), tmp_path, statement)
    with pytest.raises(ReopeningError):
        inspect_source_backup(path.resolve())


def test_tampered_raw_object_and_body_fail_closed(tmp_path: Path, source_backup: Path) -> None:
    with zipfile.ZipFile(source_backup, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))
    object_name = next(item["path"] for item in manifest["files"] if item["path"].endswith(".gz"))
    tampered = _rewrite_member(source_backup, tmp_path / "raw.zip", object_name, lambda raw: raw[:-1] + bytes([raw[-1] ^ 1]))
    with pytest.raises(ReopeningError):
        inspect_source_backup(tampered.resolve())


def test_release_certification_reloads_bytes_and_is_metadata_safe(chain: dict) -> None:
    release = chain["release"]
    result = certify_forward_release(chain["release_directory"], runtime_root=chain["custody_root"])
    assert result == release
    text = (chain["release_directory"] / "release.json").read_text()
    assert "payload_json" not in text
    assert "normalized_payload" not in text
    assert result["metadata_safe"] is True


def test_release_and_certificate_identities_are_deterministic(tmp_path: Path, source_backup: Path, chain: dict) -> None:
    other = tmp_path.resolve() / "other-custody"
    other.mkdir(mode=0o700)
    second = build_forward_release(source_backup, other, acknowledgement=ACK_BUILD_RELEASE)
    assert second == chain["release"]


def test_certifier_cannot_repair_tampered_or_missing_certificate(chain: dict) -> None:
    certificate = chain["release_directory"] / "certificate.json"
    raw = certificate.read_bytes()
    certificate.write_bytes(b"{}\n")
    with pytest.raises(ReopeningError, match="CERTIFICATE_RECONSTRUCTION_MISMATCH"):
        certify_forward_release(chain["release_directory"], runtime_root=chain["custody_root"])
    certificate.write_bytes(raw)
    release_file = chain["release_directory"] / "release.json"
    release_raw = release_file.read_bytes()
    release_file.write_bytes(release_raw.replace(b"M100_FORWARD_OBSERVED", b"M99_SYNTHETIC_TEST_ONLY"))
    with pytest.raises(ReopeningError):
        certify_forward_release(chain["release_directory"], runtime_root=chain["custody_root"])


def test_dataset_descriptor_exact_release_and_record_binding(chain: dict) -> None:
    descriptor = verify_development_dataset_descriptor(
        chain["descriptor"],
        release_directory=chain["release_directory"],
        runtime_root=chain["custody_root"],
    )
    assert descriptor["data_class"] == descriptor["split_identity"] == "REAL_MARKET_DEVELOPMENT"
    assert descriptor["selected_record_count"] == len(descriptor["selected_custody_record_hashes"])
    assert descriptor["selection_specification"]["later_release_expansion"] is False
    changed = dict(descriptor)
    changed["selected_custody_record_hashes"] = [
        next(
            item["custody_record_hash"]
            for item in chain["records"]
            if item["custody_record_hash"] not in descriptor["selected_custody_record_hashes"]
        )
    ]
    changed["selected_record_count"] = len(changed["selected_custody_record_hashes"])
    changed["selected_record_set_hash"] = canonical_hash(changed["selected_custody_record_hashes"])
    core = dict(changed); core.pop("dataset_id"); core.pop("canonical_descriptor_hash")
    digest = canonical_hash(core); changed["canonical_descriptor_hash"] = digest; changed["dataset_id"] = f"m101-dataset-{digest}"
    with pytest.raises(ReopeningError, match="RECONSTRUCTION_MISMATCH"):
        verify_development_dataset_descriptor(changed, release_directory=chain["release_directory"], runtime_root=chain["custody_root"])


@pytest.mark.parametrize("field,value,reason", [
    ("allowed_symbols", ["*"], "DATASET_WILDCARD_OR_EMPTY_SCOPE"),
    ("data_class", "REAL_MARKET_VALIDATION", "DATASET_CLASS_UNAUTHORIZED"),
    ("split_identity", "REAL_MARKET_HOLDOUT", "DATASET_CLASS_UNAUTHORIZED"),
])
def test_descriptor_rejects_wildcard_validation_and_holdout(chain: dict, field: str, value, reason: str) -> None:
    changed = dict(chain["descriptor"])
    changed[field] = value
    core = dict(changed); core.pop("dataset_id"); core.pop("canonical_descriptor_hash")
    digest = canonical_hash(core); changed["canonical_descriptor_hash"] = digest; changed["dataset_id"] = f"m101-dataset-{digest}"
    with pytest.raises(ReopeningError, match=reason):
        verify_development_dataset_descriptor(changed)


def test_dataset_selects_latest_revision_causally_available_at_cutoff(chain: dict) -> None:
    revisions = sorted(chain["records"], key=lambda item: item["revision_number"])
    assert [item["revision_number"] for item in revisions] == [1, 2]
    early = build_development_dataset_descriptor(
        chain["release_directory"],
        runtime_root=chain["custody_root"],
        provider="BINANCE_PUBLIC",
        symbols=["BTCUSDT"],
        streams=["spot_ohlcv"],
        temporal_start=_utc_ms(revisions[0]["event_time_ms"]),
        temporal_end_as_of=_utc_ms(revisions[0]["event_time_ms"]),
        causal_availability_cutoff=revisions[0]["available_at"],
        provenance_reference="synthetic:early-causal-cutoff",
    )
    assert early["selected_custody_record_hashes"] == [revisions[0]["custody_record_hash"]]
    assert chain["descriptor"]["selected_custody_record_hashes"] == [
        revisions[1]["custody_record_hash"]
    ]
    assert chain["descriptor"]["selection_specification"][
        "single_latest_revision_per_logical_observation"
    ] is True


def test_three_eligible_revisions_select_one_chain_head_deterministically(chain: dict) -> None:
    revisions = sorted(chain["records"], key=lambda item: item["revision_number"])
    third = dict(revisions[-1])
    third["revision_number"] = 3
    third["supersedes_custody_record_hash"] = revisions[-1]["custody_record_hash"]
    third["custody_record_hash"] = "f" * 64
    records = [*revisions, third]
    start = datetime.fromtimestamp(revisions[0]["event_time_ms"] / 1000, tz=timezone.utc)
    cutoff = datetime.fromisoformat(third["available_at"].replace("Z", "+00:00"))
    arguments = {
        "provider": "BINANCE_PUBLIC",
        "symbols": ["BTCUSDT"],
        "streams": ["spot_ohlcv"],
        "stream_intervals": {"spot_ohlcv": "1h"},
        "start": start,
        "end": start,
        "cutoff": cutoff,
    }
    first = dataset_module._latest_causally_available_records(records, **arguments)
    second = dataset_module._latest_causally_available_records(list(reversed(records)), **arguments)
    assert first == second == ["f" * 64]
    selected_records = [item for item in records if item["custody_record_hash"] in first]
    assert len({item["custody_logical_id"] for item in selected_records}) == len(first)
    assert build_development_dataset_descriptor(
        chain["release_directory"],
        runtime_root=chain["custody_root"],
        provider="BINANCE_PUBLIC",
        symbols=["BTCUSDT"],
        streams=["spot_ohlcv"],
        temporal_start=_utc_ms(revisions[0]["event_time_ms"]),
        temporal_end_as_of=_utc_ms(revisions[0]["event_time_ms"]),
        causal_availability_cutoff=revisions[-1]["available_at"],
        provenance_reference="synthetic:mission101-acceptance",
    )["canonical_descriptor_hash"] == chain["descriptor"]["canonical_descriptor_hash"]


@pytest.mark.parametrize(
    "streams",
    [
        ["perpetual_ohlcv", "funding_rates"],
        ["spot_ohlcv", "perpetual_ohlcv", "mark_price_ohlcv", "funding_rates"],
    ],
)
def test_mixed_bar_and_funding_datasets_are_exact_and_deterministic(
    chain: dict, streams: list[str]
) -> None:
    records = [
        item
        for item in chain["core"]["custody_records"]
        if item["symbol"] == "BTCUSDT" and item["stream"] in streams
    ]
    arguments = {
        "runtime_root": chain["custody_root"],
        "provider": "BINANCE_PUBLIC",
        "symbols": ["BTCUSDT"],
        "streams": streams,
        "temporal_start": _utc_ms(min(item["event_time_ms"] for item in records)),
        "temporal_end_as_of": _utc_ms(max(item["event_time_ms"] for item in records)),
        "causal_availability_cutoff": max(item["available_at"] for item in records),
        "provenance_reference": "synthetic:mixed-streams",
    }
    first = build_development_dataset_descriptor(chain["release_directory"], **arguments)
    second = build_development_dataset_descriptor(chain["release_directory"], **arguments)
    assert first == second
    assert first["stream_intervals"] == {
        stream: (None if stream == "funding_rates" else "1h")
        for stream in sorted(streams)
    }
    assert {item["stream"] for item in records} == set(streams)
    assert verify_development_dataset_descriptor(
        first,
        release_directory=chain["release_directory"],
        runtime_root=chain["custody_root"],
    ) == first


@pytest.mark.parametrize(
    "intervals",
    [
        {},
        {"spot_ohlcv": "1h", "funding_rates": None},
        {"spot_ohlcv": None},
        {"spot_ohlcv": "5m"},
    ],
)
def test_malformed_stream_interval_mapping_fails_closed(
    chain: dict, intervals: dict[str, str | None]
) -> None:
    changed = dict(chain["descriptor"])
    changed["stream_intervals"] = intervals
    core = dict(changed)
    core.pop("dataset_id")
    core.pop("canonical_descriptor_hash")
    digest = canonical_hash(core)
    changed["dataset_id"] = f"m101-dataset-{digest}"
    changed["canonical_descriptor_hash"] = digest
    with pytest.raises(ReopeningError, match="DATASET_STREAM_INTERVALS_INVALID"):
        verify_development_dataset_descriptor(changed)


def test_authority_runtime_paths_modes_schema_and_immutability(tmp_path: Path, chain: dict) -> None:
    assert stat.S_IMODE(chain["authority_root"].stat().st_mode) == 0o700
    database = chain["authority_root"] / "authority.sqlite3"
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    with pytest.raises(ReopeningError, match="INSIDE_REPOSITORY"):
        initialize_authority_runtime(ROOT / "forbidden-runtime", acknowledgement=ACK_INITIALIZE_AUTHORITY)
    target = tmp_path / "target"; target.mkdir()
    link = tmp_path / "link"; link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ReopeningError, match="SYMLINK"):
        initialize_authority_runtime(link / "authority", acknowledgement=ACK_INITIALIZE_AUTHORITY)
    conn = sqlite3.connect(database)
    try:
        with pytest.raises(sqlite3.DatabaseError, match="IMMUTABLE_PERMIT"):
            conn.execute("UPDATE permits SET permit_hash='x'")
        with pytest.raises(sqlite3.DatabaseError, match="IMMUTABLE_PERMIT"):
            conn.execute("DELETE FROM permits")
        conn.rollback()
        conn.execute("CREATE VIEW unexpected AS SELECT 1")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ReopeningError, match="SCHEMA_INVALID"):
        verify_development_permit(chain["authority_root"], chain["permit"]["permit_id"], descriptor=chain["descriptor"], release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"], repository_commit=M100_COMPATIBLE_COMMIT, experiment_family="M101_METADATA_ONLY_FAMILY", authorization_stage="MISSION_101_DEVELOPMENT_ADMISSION", as_of=chain["as_of"])


def test_dangling_symlink_path_component_is_rejected(tmp_path: Path) -> None:
    dangling = tmp_path / "dangling"
    dangling.symlink_to(tmp_path / "missing", target_is_directory=True)
    with pytest.raises(ReopeningError, match="AUTHORITY_ROOT_SYMLINK"):
        initialize_authority_runtime(
            dangling / "authority", acknowledgement=ACK_INITIALIZE_AUTHORITY
        )
    package = ROOT / "offchain" / "research" / "reopening"
    assert "exists() and current.is_symlink()" not in "".join(
        path.read_text(encoding="utf-8") for path in package.glob("*.py")
    )


def test_permit_acknowledgement_bindings_expiry_exhaustion_and_revocation(chain: dict) -> None:
    with pytest.raises(ReopeningError, match="ACKNOWLEDGEMENT"):
        issue_development_permit(chain["authority_root"], descriptor=chain["descriptor"], release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"], experiment_family="X", fixed_trial_budget=1, expires_at=chain["expires_at"], acknowledgement="NO")
    result = verify_development_permit(chain["authority_root"], chain["permit"]["permit_id"], descriptor=chain["descriptor"], release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"], repository_commit=M100_COMPATIBLE_COMMIT, experiment_family="M101_METADATA_ONLY_FAMILY", authorization_stage="MISSION_101_DEVELOPMENT_ADMISSION", as_of=chain["as_of"])
    assert result["state"] == "ACTIVE"
    with pytest.raises(ReopeningError, match="BINDING_MISMATCH"):
        verify_development_permit(chain["authority_root"], chain["permit"]["permit_id"], descriptor=chain["descriptor"], release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"], repository_commit="a" * 40, experiment_family="M101_METADATA_ONLY_FAMILY", authorization_stage="MISSION_101_DEVELOPMENT_ADMISSION", as_of=chain["as_of"])
    with pytest.raises(ReopeningError, match="EXPIRED"):
        verify_development_permit(chain["authority_root"], chain["permit"]["permit_id"], descriptor=chain["descriptor"], release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"], repository_commit=M100_COMPATIBLE_COMMIT, experiment_family="M101_METADATA_ONLY_FAMILY", authorization_stage="MISSION_101_DEVELOPMENT_ADMISSION", as_of=(datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    assert chain["admission"].admit(chain["request"])["decision_token"] == "ADMITTED"
    second = dict(chain["request"])
    second["request_id"] = "permit-exhaustion-second"
    second["declared_trial_number"] = 2
    second["canonical_request_hash"] = canonical_hash(
        {key: value for key, value in second.items() if key != "canonical_request_hash"}
    )
    assert chain["admission"].admit(second)["decision_token"] == "ADMITTED"
    with pytest.raises(ReopeningError, match="EXHAUSTED"):
        verify_development_permit(chain["authority_root"], chain["permit"]["permit_id"], descriptor=chain["descriptor"], release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"], repository_commit=M100_COMPATIBLE_COMMIT, experiment_family="M101_METADATA_ONLY_FAMILY", authorization_stage="MISSION_101_DEVELOPMENT_ADMISSION", as_of=chain["as_of"])


def test_permit_issuance_observes_clean_exact_repository_identity(chain: dict) -> None:
    arguments = {
        "descriptor": chain["descriptor"],
        "release_directory": chain["release_directory"],
        "custody_runtime_root": chain["custody_root"],
        "experiment_family": "OBSERVED_REPOSITORY_FAMILY",
        "fixed_trial_budget": 1,
        "expires_at": chain["expires_at"],
        "acknowledgement": ACK_ISSUE_PERMIT,
        "time_provider": lambda: chain["issued_at"],
    }
    with pytest.raises(ReopeningError, match="DIRTY_REPOSITORY"):
        issue_development_permit(
            chain["authority_root"],
            **arguments,
            repository_observer=_repository_observer(clean=False),
        )
    with pytest.raises(ReopeningError, match="REPOSITORY_ROOT_MISMATCH"):
        issue_development_permit(
            chain["authority_root"],
            **arguments,
            repository_observer=_repository_observer(root=chain["temp"]),
        )
    permit = issue_development_permit(
        chain["authority_root"],
        **arguments,
        repository_observer=_repository_observer(head="a" * 40),
    )
    assert permit["repository_commit"] == "a" * 40
    with pytest.raises(TypeError):
        issue_development_permit(
            chain["authority_root"],
            **arguments,
            repository_commit="b" * 40,
        )


def test_production_repository_observer_uses_exact_root_head_and_untracked_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def git_output(_root: Path, arguments: list[str]) -> str:
        calls.append(tuple(arguments))
        if arguments == ["rev-parse", "--show-toplevel"]:
            return str(ROOT) + "\n"
        if arguments == ["rev-parse", "HEAD"]:
            return M100_COMPATIBLE_COMMIT + "\n"
        if arguments == ["status", "--porcelain=v1", "--untracked-files=all"]:
            return "?? untracked-file\n"
        raise AssertionError(arguments)

    monkeypatch.setattr(core_module, "_git_output", git_output)
    assert core_module.observe_repository_identity() == {
        "repository_root": str(ROOT.resolve()),
        "head": M100_COMPATIBLE_COMMIT,
        "clean": False,
    }
    assert calls == [
        ("rev-parse", "--show-toplevel"),
        ("rev-parse", "HEAD"),
        ("status", "--porcelain=v1", "--untracked-files=all"),
    ]


def test_admission_cannot_forge_head_or_clean_state(chain: dict) -> None:
    forged_head = dict(chain["request"])
    forged_head["repository_commit"] = "a" * 40
    forged_head["canonical_request_hash"] = canonical_hash(
        {key: value for key, value in forged_head.items() if key != "canonical_request_hash"}
    )
    assert chain["admission"].preflight(forged_head)["reason_token"] == "REPOSITORY_COMMIT_MISMATCH"

    forged_clean = dict(chain["request"])
    forged_clean["repository_clean"] = False
    forged_clean["canonical_request_hash"] = canonical_hash(
        {key: value for key, value in forged_clean.items() if key != "canonical_request_hash"}
    )
    assert chain["admission"].preflight(forged_clean)["reason_token"] == "REPOSITORY_CLEAN_MISMATCH"

    dirty = DevelopmentAdmissionService(
        descriptor=chain["descriptor"],
        release_directory=str(chain["release_directory"]),
        custody_runtime_root=str(chain["custody_root"]),
        authority_root=str(chain["authority_root"]),
        trial_ledger=chain["ledger"],
        time_provider=lambda: chain["as_of"],
        repository_observer=_repository_observer(clean=False),
    )
    assert dirty.preflight(chain["request"])["reason_token"] == "DIRTY_REPOSITORY"


def test_historical_permit_verification_is_causal_across_revocation(chain: dict) -> None:
    issued = datetime.fromisoformat(chain["issued_at"].replace("Z", "+00:00"))
    revoked = datetime.fromisoformat(chain["as_of"].replace("Z", "+00:00"))
    before_issue = (issued - timedelta(microseconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    historically_active = (issued + (revoked - issued) / 2).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    after_revocation = (revoked + timedelta(microseconds=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    revoke_development_permit(
        chain["authority_root"],
        chain["permit"]["permit_id"],
        acknowledgement=ACK_REVOKE_PERMIT,
        time_provider=lambda: chain["as_of"],
    )
    arguments = {
        "descriptor": chain["descriptor"],
        "release_directory": chain["release_directory"],
        "custody_runtime_root": chain["custody_root"],
        "repository_commit": M100_COMPATIBLE_COMMIT,
        "experiment_family": "M101_METADATA_ONLY_FAMILY",
        "authorization_stage": "MISSION_101_DEVELOPMENT_ADMISSION",
    }
    with pytest.raises(ReopeningError, match="PERMIT_NOT_YET_ACTIVE"):
        verify_development_permit(
            chain["authority_root"], chain["permit"]["permit_id"], as_of=before_issue, **arguments
        )
    assert verify_development_permit(
        chain["authority_root"], chain["permit"]["permit_id"], as_of=historically_active, **arguments
    )["state"] == "ACTIVE"
    with pytest.raises(ReopeningError, match="PERMIT_REVOKED"):
        verify_development_permit(
            chain["authority_root"], chain["permit"]["permit_id"], as_of=after_revocation, **arguments
        )


def test_caller_cannot_backdate_revocation_and_malformed_history_fails_closed(
    chain: dict,
) -> None:
    with pytest.raises(TypeError):
        revoke_development_permit(
            chain["authority_root"],
            chain["permit"]["permit_id"],
            revoked_at="1970-01-01T00:00:00.000000Z",
            acknowledgement=ACK_REVOKE_PERMIT,
        )
    database = chain["authority_root"] / "authority.sqlite3"
    event_core = {
        "permit_id": chain["permit"]["permit_id"],
        "sequence_number": 2,
        "status": "REVOKED",
        "reason_token": "MALFORMED_REASON",
        "event_at": chain["as_of"],
    }
    event_hash = canonical_hash(event_core)
    conn = sqlite3.connect(database)
    try:
        conn.execute(
            "INSERT INTO permit_events(event_id,permit_id,sequence_number,status,reason_token,event_at,event_hash) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                f"permit-event-{event_hash}", chain["permit"]["permit_id"], 2,
                "REVOKED", "MALFORMED_REASON", chain["as_of"], event_hash,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ReopeningError, match="PERMIT_EVENT_HISTORY_INVALID"):
        inspect_authority_runtime(chain["authority_root"])


def test_revocation_and_capacity_reservation_share_one_linearization(chain: dict) -> None:
    permit = _permit_with_budget(chain, 1)
    before = inspect_authority_runtime(chain["authority_root"])["permit_consumption_count"]
    barrier = threading.Barrier(2)

    def reserve() -> str:
        barrier.wait()
        try:
            authority_module._reserve_permit_capacity(
                chain["authority_root"],
                permit_id=permit["permit_id"],
                trial_id="revocation-race-trial",
                request_hash="a" * 64,
                budget_id="revocation-race-budget",
                reserved_at=chain["as_of"],
            )
        except ReopeningError as error:
            return error.reason
        return "RESERVED"

    def revoke() -> str:
        barrier.wait()
        revoke_development_permit(
            chain["authority_root"],
            permit["permit_id"],
            acknowledgement=ACK_REVOKE_PERMIT,
            time_provider=lambda: chain["as_of"],
        )
        return "REVOKED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        reserve_result, revoke_result = list(pool.map(lambda fn: fn(), (reserve, revoke)))
    assert revoke_result == "REVOKED"
    assert reserve_result in {"RESERVED", "PERMIT_REVOKED"}
    after = inspect_authority_runtime(chain["authority_root"])["permit_consumption_count"]
    assert after - before == (1 if reserve_result == "RESERVED" else 0)
    revoke_development_permit(chain["authority_root"], chain["permit"]["permit_id"], acknowledgement=ACK_REVOKE_PERMIT, time_provider=lambda: chain["as_of"])
    with pytest.raises(ReopeningError, match="REVOKED"):
        verify_development_permit(chain["authority_root"], chain["permit"]["permit_id"], descriptor=chain["descriptor"], release_directory=chain["release_directory"], custody_runtime_root=chain["custody_root"], repository_commit=M100_COMPATIBLE_COMMIT, experiment_family="M101_METADATA_ONLY_FAMILY", authorization_stage="MISSION_101_DEVELOPMENT_ADMISSION", as_of=chain["as_of"])


@pytest.mark.parametrize("override", [
    {"experiment_family": "WRONG_FAMILY"},
    {"authorization_stage": "MISSION_102_EXECUTION"},
])
def test_permit_wrong_family_and_stage_rejected(chain: dict, override: dict) -> None:
    arguments = {
        "descriptor": chain["descriptor"],
        "release_directory": chain["release_directory"],
        "custody_runtime_root": chain["custody_root"],
        "repository_commit": M100_COMPATIBLE_COMMIT,
        "experiment_family": "M101_METADATA_ONLY_FAMILY",
        "authorization_stage": "MISSION_101_DEVELOPMENT_ADMISSION",
        "as_of": chain["as_of"],
    }
    arguments.update(override)
    with pytest.raises(ReopeningError, match="PERMIT_BINDING_MISMATCH"):
        verify_development_permit(chain["authority_root"], chain["permit"]["permit_id"], **arguments)


def test_admission_v2_valid_path_stops_before_execution(chain: dict) -> None:
    assert chain["admission"].preflight(chain["request"])["decision_token"] == "PRECHECK_PASS"
    decision = chain["admission"].admit(chain["request"])
    assert decision["decision_token"] == "ADMITTED"
    assert decision["execution_authorized"] is False
    assert chain["ledger"].event_statuses(decision["trial_id"]) == ("RESERVED", "ADMITTED")


@pytest.mark.parametrize("field,value,reason", [
    ("permit_hash", "a" * 64, "PERMIT_HASH_MISMATCH"),
    ("dataset_id", "m101-dataset-wrong", "DATASET_DESCRIPTOR_BINDING_MISMATCH"),
    ("split_identity", "REAL_MARKET_VALIDATION", "VALIDATION_FORBIDDEN"),
    ("data_class", "REAL_MARKET_HOLDOUT", "HOLDOUT_FORBIDDEN"),
])
def test_post_reservation_failures_consume_trials(chain: dict, field: str, value: str, reason: str) -> None:
    request = dict(chain["request"])
    request[field] = value
    request["request_id"] = f"bad-{field}"
    request["declared_trial_number"] = 2
    request["canonical_request_hash"] = ""
    request["canonical_request_hash"] = canonical_hash({key: item for key, item in request.items() if key != "canonical_request_hash"})
    decision = chain["admission"].admit(request)
    assert decision["decision_token"] == "STOPPED"
    assert decision["reason_token"] == reason
    assert chain["ledger"].reservation_count("m101-budget") == 1
    assert chain["ledger"].event_statuses(decision["trial_id"]) == ("RESERVED", "STOPPED")


def test_missing_permit_rejects_after_reservation(chain: dict) -> None:
    request = dict(chain["request"])
    request["request_id"] = "missing-permit"
    request["permit_id"] = "m101-permit-missing"
    request["canonical_request_hash"] = canonical_hash({key: value for key, value in request.items() if key != "canonical_request_hash"})
    decision = chain["admission"].admit(request)
    assert decision["reason_token"] == "PERMIT_UNKNOWN"
    assert chain["ledger"].reservation_count("m101-budget") == 1


def test_admission_budget_is_fixed_and_no_result_engine_is_imported(chain: dict) -> None:
    first = chain["admission"].admit(chain["request"])
    assert first["decision_token"] == "ADMITTED"
    second = dict(chain["request"])
    second["request_id"] = "m101-request-2"; second["declared_trial_number"] = 2
    second["canonical_request_hash"] = canonical_hash({key: value for key, value in second.items() if key != "canonical_request_hash"})
    assert chain["admission"].admit(second)["decision_token"] == "ADMITTED"
    third = dict(chain["request"])
    third["request_id"] = "m101-request-3"; third["declared_trial_number"] = 3
    third["canonical_request_hash"] = canonical_hash({key: value for key, value in third.items() if key != "canonical_request_hash"})
    assert chain["admission"].admit(third)["reason_token"] == "TRIAL_BUDGET_EXHAUSTED"
    package_text = "\n".join(path.read_text() for path in (ROOT / "offchain/research/reopening").glob("*.py"))
    assert "engine_service" not in package_text
    assert "calculate_returns" not in package_text
    assert "place_order" not in package_text


def test_global_permit_capacity_cannot_reset_across_ledgers_or_budget_ids(chain: dict) -> None:
    permit = _permit_with_budget(chain, 1)
    ledger_a = _private_ledger(chain, "ledger-a", "budget-a", 1)
    ledger_b = _private_ledger(chain, "ledger-b", "budget-b", 1)
    request_a = _request_for(chain, permit, request_id="global-a", budget_id="budget-a")
    request_b = _request_for(chain, permit, request_id="global-b", budget_id="budget-b")

    assert _admission_service(chain, ledger_a).admit(request_a)["decision_token"] == "ADMITTED"
    stopped = _admission_service(chain, ledger_b).admit(request_b)
    assert stopped["decision_token"] == "STOPPED"
    assert stopped["reason_token"] == "PERMIT_EXHAUSTED"
    assert ledger_b.reservation_count("budget-b") == 1
    status = inspect_authority_runtime(chain["authority_root"])
    assert status["permit_consumption_count"] == 1
    consumed = next(item for item in status["permits"] if item["permit_id"] == permit["permit_id"])
    assert consumed["consumed_trials"] == 1
    assert consumed["remaining_trials"] == 0
    conn = sqlite3.connect(chain["authority_root"] / "authority.sqlite3")
    try:
        with pytest.raises(sqlite3.DatabaseError, match="APPEND_ONLY_PERMIT_CONSUMPTION"):
            conn.execute("UPDATE permit_consumptions SET budget_id='replacement'")
        conn.rollback()
        with pytest.raises(sqlite3.DatabaseError, match="APPEND_ONLY_PERMIT_CONSUMPTION"):
            conn.execute("DELETE FROM permit_consumptions")
        conn.rollback()
    finally:
        conn.close()


def test_global_permit_capacity_concurrency_never_exceeds_budget(chain: dict) -> None:
    permit = _permit_with_budget(chain, 1)
    attempts = []
    for suffix in ("one", "two"):
        ledger = _private_ledger(chain, f"concurrent-{suffix}", f"concurrent-{suffix}", 1)
        service_instance = _admission_service(chain, ledger)
        request = _request_for(
            chain,
            permit,
            request_id=f"concurrent-{suffix}",
            budget_id=f"concurrent-{suffix}",
        )
        attempts.append((service_instance, request))
    with ThreadPoolExecutor(max_workers=2) as executor:
        decisions = list(executor.map(lambda pair: pair[0].admit(pair[1]), attempts))
    assert sorted(item["decision_token"] for item in decisions) == ["ADMITTED", "STOPPED"]
    assert sorted(item["reason_token"] for item in decisions) == [
        "M101_DEVELOPMENT_ADMISSION_GATES_PASSED",
        "PERMIT_EXHAUSTED",
    ]
    status = inspect_authority_runtime(chain["authority_root"])
    assert next(
        item["consumed_trials"] for item in status["permits"]
        if item["permit_id"] == permit["permit_id"]
    ) == 1


def test_preflight_consumes_no_global_capacity(chain: dict) -> None:
    permit = _permit_with_budget(chain, 1)
    ledger = _private_ledger(chain, "preflight-ledger", "preflight-budget", 1)
    request = _request_for(
        chain, permit, request_id="preflight-global", budget_id="preflight-budget"
    )
    assert _admission_service(chain, ledger).preflight(request)["decision_token"] == "PRECHECK_PASS"
    assert ledger.reservation_count("preflight-budget") == 0
    status = inspect_authority_runtime(chain["authority_root"])
    assert status["permit_consumption_count"] == 0


def test_post_capacity_failure_does_not_refund_global_slot(
    chain: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    permit = _permit_with_budget(chain, 1)
    first_ledger = _private_ledger(chain, "post-capacity-a", "post-capacity-a", 1)
    first_service = _admission_service(chain, first_ledger)
    original_append = first_service._ledger.append_event

    def fail_admitted(**values) -> None:
        if values["status_token"] == "ADMITTED":
            raise AdmissionError("FORCED_POST_CAPACITY_FAILURE")
        original_append(**values)

    monkeypatch.setattr(first_service._ledger, "append_event", fail_admitted)
    first = first_service.admit(
        _request_for(chain, permit, request_id="post-capacity-a", budget_id="post-capacity-a")
    )
    assert first["decision_token"] == "STOPPED"
    assert first["reason_token"] == "FORCED_POST_CAPACITY_FAILURE"
    assert inspect_authority_runtime(chain["authority_root"])["permit_consumption_count"] == 1

    second_ledger = _private_ledger(chain, "post-capacity-b", "post-capacity-b", 1)
    second = _admission_service(chain, second_ledger).admit(
        _request_for(chain, permit, request_id="post-capacity-b", budget_id="post-capacity-b")
    )
    assert second["reason_token"] == "PERMIT_EXHAUSTED"


def test_trusted_time_rejects_backdated_request_for_expired_permit(chain: dict) -> None:
    decision = datetime.fromisoformat(chain["as_of"].replace("Z", "+00:00"))
    old_issued = (decision - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    old_expires = (decision - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    backdated = (decision - timedelta(days=1, hours=12)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    permit = issue_development_permit(
        chain["authority_root"],
        descriptor=chain["descriptor"],
        release_directory=chain["release_directory"],
        custody_runtime_root=chain["custody_root"],
        experiment_family="M101_METADATA_ONLY_FAMILY",
        fixed_trial_budget=1,
        expires_at=old_expires,
        acknowledgement=ACK_ISSUE_PERMIT,
        repository_observer=_repository_observer(),
        time_provider=lambda: old_issued,
    )
    ledger = _private_ledger(chain, "expired-ledger", "expired-budget", 1)
    request = _request_for(
        chain,
        permit,
        request_id="expired-backdated",
        budget_id="expired-budget",
        created_at=backdated,
    )
    stopped = _admission_service(chain, ledger, decision_time=chain["as_of"]).admit(request)
    assert stopped["reason_token"] == "PERMIT_EXPIRED"
    assert ledger.reservation_count("expired-budget") == 1
    status = inspect_authority_runtime(chain["authority_root"])
    assert next(
        item["consumed_trials"] for item in status["permits"]
        if item["permit_id"] == permit["permit_id"]
    ) == 0


def test_trusted_time_rejects_future_request_and_controls_ledger_timestamps(chain: dict) -> None:
    permit = _permit_with_budget(chain, 1)
    future = (
        datetime.fromisoformat(chain["as_of"].replace("Z", "+00:00"))
        + timedelta(hours=1)
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    ledger = _private_ledger(chain, "future-ledger", "future-budget", 1)
    request = _request_for(
        chain,
        permit,
        request_id="future-request",
        budget_id="future-budget",
        created_at=future,
    )
    stopped = _admission_service(chain, ledger, decision_time=chain["as_of"]).admit(request)
    assert stopped["reason_token"] == "REQUEST_CREATED_AT_IN_FUTURE"
    reservation = ledger.get_reservation(stopped["trial_id"])
    assert reservation.reserved_at == chain["as_of"]
    assert inspect_authority_runtime(chain["authority_root"])["permit_consumption_count"] == 0


def _existing_m94_ledger(root: Path, name: str = "trials.sqlite3") -> Path:
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    path = root / name
    TrialLedger(path)
    os.chmod(path, 0o600)
    return path


def test_trial_ledger_wrapper_rejects_relative_repository_and_symlink_paths(
    tmp_path: Path
) -> None:
    with pytest.raises(ReopeningError, match="NOT_ABSOLUTE"):
        open_development_trial_ledger("relative.sqlite3")
    with pytest.raises(ReopeningError, match="INSIDE_REPOSITORY"):
        register_development_budget(
            ROOT / "forbidden-m101-ledger.sqlite3",
            budget_id="forbidden",
            experiment_family="M101_METADATA_ONLY_FAMILY",
            total_trial_budget=1,
            created_at="2026-08-09T00:00:00.000000Z",
            acknowledgement=ACK_REGISTER_BUDGET,
        )
    target = _existing_m94_ledger(tmp_path / "ledger-target")
    link_parent = tmp_path / "ledger-link"
    link_parent.symlink_to(target.parent, target_is_directory=True)
    with pytest.raises(ReopeningError, match="SYMLINK"):
        open_development_trial_ledger(link_parent / target.name)
    broken = tmp_path / "broken-ledger-link"
    broken.symlink_to(tmp_path / "missing-ledger-target", target_is_directory=True)
    with pytest.raises(ReopeningError, match="SYMLINK"):
        open_development_trial_ledger(broken / "trials.sqlite3")
    assert not (ROOT / "forbidden-m101-ledger.sqlite3").exists()


def test_trial_ledger_wrapper_rejects_existing_mode_drift(tmp_path: Path) -> None:
    wrong_parent = tmp_path / "wrong-parent"
    parent_ledger = _existing_m94_ledger(wrong_parent)
    os.chmod(wrong_parent, 0o755)
    with pytest.raises(ReopeningError, match="PARENT_MODE_INVALID"):
        open_development_trial_ledger(parent_ledger)

    wrong_file = _existing_m94_ledger(tmp_path / "wrong-file")
    os.chmod(wrong_file, 0o644)
    with pytest.raises(ReopeningError, match="FILE_MODE_INVALID"):
        open_development_trial_ledger(wrong_file)
    assert stat.S_IMODE(wrong_file.stat().st_mode) == 0o644


@pytest.mark.parametrize("statement", [
    "CREATE TABLE hostile(value TEXT)",
    "CREATE INDEX hostile_index ON trial_events(reason_token)",
    "CREATE TRIGGER hostile_trigger AFTER INSERT ON trial_events BEGIN SELECT 1; END",
    "DROP TABLE trial_result_links",
])
def test_trial_ledger_wrapper_rejects_extra_or_missing_schema(
    tmp_path: Path, statement: str
) -> None:
    root = tmp_path / hashlib.sha256(statement.encode()).hexdigest()
    path = _existing_m94_ledger(root)
    conn = sqlite3.connect(path)
    try:
        conn.execute(statement)
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(ReopeningError, match="SCHEMA_INVALID"):
        open_development_trial_ledger(path)


def test_trial_ledger_wrapper_rejects_malformed_and_accepts_exact_private_schema(
    tmp_path: Path
) -> None:
    malformed_root = tmp_path / "malformed-ledger"
    malformed_root.mkdir(mode=0o700)
    malformed = malformed_root / "trials.sqlite3"
    malformed.write_bytes(b"not sqlite")
    os.chmod(malformed, 0o600)
    with pytest.raises(ReopeningError, match="DATABASE_INVALID"):
        open_development_trial_ledger(malformed)

    exact = tmp_path / "exact-ledger" / "trials.sqlite3"
    register_development_budget(
        exact,
        budget_id="exact-budget",
        experiment_family="M101_METADATA_ONLY_FAMILY",
        total_trial_budget=1,
        created_at="2026-08-09T00:00:00.000000Z",
        acknowledgement=ACK_REGISTER_BUDGET,
    )
    assert stat.S_IMODE(exact.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(exact.stat().st_mode) == 0o600
    assert open_development_trial_ledger(exact).get_budget("exact-budget").budget_id == "exact-budget"


def test_mission94_package_bytes_remain_untouched() -> None:
    completed = subprocess.run(
        ["git", "diff", "--exit-code", "HEAD", "--", "offchain/research/admission"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout == completed.stderr == ""


def test_admission_cli_exposes_no_authority_time_override() -> None:
    options = CLI_OPTIONS["admit-development"]
    assert not {"--as-of", "--decision-time", "--authority-time"} & options
    assert not {"--repository-commit", "--repository-clean"} & options
    assert "--issued-at" not in CLI_OPTIONS["issue-development-permit"]
    assert "--repository-commit" not in CLI_OPTIONS["issue-development-permit"]
    assert "--revoked-at" not in CLI_OPTIONS["revoke-development-permit"]
    assert "--interval" not in CLI_OPTIONS["create-development-dataset"]


def test_cli_rejects_caller_controlled_revocation_time(
    chain: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(
        [
            "revoke-development-permit",
            "--authority-root", str(chain["authority_root"]),
            "--permit-id", chain["permit"]["permit_id"],
            "--revoked-at", "1970-01-01T00:00:00.000000Z",
            "--acknowledge", ACK_REVOKE_PERMIT,
        ]
    ) == 2
    assert json.loads(capsys.readouterr().err) == {
        "reason": "CLI_INPUT_INVALID", "status": "FAIL"
    }


CLI_OPTIONS = {
    "show-contract": set(),
    "verify-backup-source": {"--backup"},
    "plan-forward-custody-release": {"--backup"},
    "certify-forward-custody-release": {"--runtime-root", "--release-directory"},
    "verify-development-dataset": {"--descriptor", "--custody-runtime-root", "--release-directory"},
    "verify-development-permit": {
        "--authority-root", "--permit-id", "--descriptor", "--custody-runtime-root",
        "--release-directory", "--repository-commit", "--experiment-family",
        "--authorization-stage", "--as-of",
    },
    "inspect-authority-runtime": {"--authority-root"},
    "build-forward-custody-release": {"--backup", "--runtime-root", "--acknowledge"},
    "create-development-dataset": {
        "--custody-runtime-root", "--release-directory", "--destination", "--symbol",
        "--stream", "--temporal-start", "--temporal-end-as-of",
        "--causal-availability-cutoff", "--provenance-reference", "--acknowledge",
    },
    "init-research-authority-runtime": {"--authority-root", "--acknowledge"},
    "issue-development-permit": {
        "--authority-root", "--descriptor", "--custody-runtime-root", "--release-directory",
        "--experiment-family", "--fixed-trial-budget", "--expires-at", "--acknowledge",
    },
    "revoke-development-permit": {
        "--authority-root", "--permit-id", "--acknowledge",
    },
    "register-development-budget": {
        "--trial-ledger", "--budget-id", "--experiment-family", "--total-trial-budget",
        "--created-at", "--acknowledge",
    },
    "admit-development": {
        "--trial-ledger", "--authority-root", "--descriptor", "--custody-runtime-root",
        "--release-directory", "--request-id",
        "--budget-id", "--declared-trial-number", "--dataset-id", "--dataset-descriptor-hash",
        "--data-class", "--split-identity", "--permit-id", "--permit-hash",
        "--experiment-family", "--authorization-stage", "--initiated-by", "--created-at",
        "--acknowledge",
    },
}


def _cli_subparsers() -> dict[str, object]:
    parser = cli_module.build_parser()
    action = next(item for item in parser._actions if isinstance(item, cli_module.argparse._SubParsersAction))
    return action.choices


def _descriptor_file(chain: dict) -> Path:
    path = chain["temp"] / "descriptor.json"
    write_development_dataset_descriptor(
        chain["descriptor"], path, acknowledgement=ACK_WRITE_DESCRIPTOR
    )
    return path


def _admit_arguments(chain: dict, descriptor_path: Path, **overrides: str) -> list[str]:
    values = {
        "data_class": "REAL_MARKET_DEVELOPMENT",
        "split_identity": "REAL_MARKET_DEVELOPMENT",
        **overrides,
    }
    return [
        "admit-development",
        "--trial-ledger", str(chain["ledger_path"]),
        "--authority-root", str(chain["authority_root"]),
        "--descriptor", str(descriptor_path),
        "--custody-runtime-root", str(chain["custody_root"]),
        "--release-directory", str(chain["release_directory"]),
        "--request-id", "m101-cli-request",
        "--budget-id", "m101-budget",
        "--declared-trial-number", "1",
        "--dataset-id", chain["descriptor"]["dataset_id"],
        "--dataset-descriptor-hash", chain["descriptor"]["canonical_descriptor_hash"],
        "--data-class", values["data_class"],
        "--split-identity", values["split_identity"],
        "--permit-id", chain["permit"]["permit_id"],
        "--permit-hash", chain["permit"]["canonical_permit_hash"],
        "--experiment-family", "M101_METADATA_ONLY_FAMILY",
        "--authorization-stage", "MISSION_101_DEVELOPMENT_ADMISSION",
        "--initiated-by", "OPERATOR",
        "--created-at", chain["as_of"],
        "--acknowledge", overrides.get("acknowledgement", "RESERVE_M101_DEVELOPMENT_ADMISSION_TRIAL"),
    ]


def _tree_fingerprint(paths: list[Path]) -> dict[str, tuple[int, int, int, str]]:
    result = {}
    for base in paths:
        candidates = [base] if base.is_file() else sorted(base.rglob("*"))
        for path in candidates:
            if path.is_file() and not path.is_symlink():
                details = path.stat()
                result[str(path)] = (
                    stat.S_IMODE(details.st_mode),
                    details.st_size,
                    details.st_mtime_ns,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
    return result


def test_cli_module_help_and_exact_declared_surface() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "offchain.research.reopening", "--help"],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert set(_cli_subparsers()) == set(CLI_OPTIONS)
    assert all(command in completed.stdout for command in CLI_OPTIONS)
    for command, expected in CLI_OPTIONS.items():
        parser = _cli_subparsers()[command]
        actual = {
            option
            for action in parser._actions
            for option in action.option_strings
            if option not in {"-h", "--help"}
        }
        assert actual == expected
    all_options = set().union(*CLI_OPTIONS.values())
    assert not {"--url", "--provider", "--host", "--endpoint", "--plugin"} & all_options


@pytest.mark.parametrize("arguments", [
    ["unknown-command"],
    ["show-contract", "--unknown"],
    ["execute-research"],
    ["backtest"],
])
def test_cli_unknown_command_argument_and_result_execution_reject(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(arguments) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {"reason": "CLI_INPUT_INVALID", "status": "FAIL"}
    assert "Traceback" not in captured.err


def test_every_cli_write_command_requires_acknowledgement() -> None:
    for command in (
        "build-forward-custody-release", "create-development-dataset",
        "init-research-authority-runtime", "issue-development-permit",
        "revoke-development-permit", "register-development-budget", "admit-development",
    ):
        action = next(
            item for item in _cli_subparsers()[command]._actions
            if "--acknowledge" in item.option_strings
        )
        assert action.required is True


def test_incorrect_acknowledgements_fail_closed_for_every_write_command(
    chain: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    descriptor_path = _descriptor_file(chain)
    records = chain["records"]
    command_arguments = [
        ["build-forward-custody-release", "--backup", str(chain["source_backup"]), "--runtime-root", str(chain["temp"] / "wrong-build"), "--acknowledge", "WRONG"],
        [
            "create-development-dataset", "--custody-runtime-root", str(chain["custody_root"]),
            "--release-directory", str(chain["release_directory"]), "--destination", str(chain["temp"] / "wrong-descriptor.json"),
            "--symbol", "BTCUSDT", "--stream", "spot_ohlcv",
            "--temporal-start", _utc_ms(min(item["event_time_ms"] for item in records)),
            "--temporal-end-as-of", _utc_ms(max(item["event_time_ms"] for item in records)),
            "--causal-availability-cutoff", max(item["available_at"] for item in records),
            "--provenance-reference", "synthetic:cli-test", "--acknowledge", "WRONG",
        ],
        ["init-research-authority-runtime", "--authority-root", str(chain["temp"] / "wrong-authority"), "--acknowledge", "WRONG"],
        [
            "issue-development-permit", "--authority-root", str(chain["authority_root"]),
            "--descriptor", str(descriptor_path), "--custody-runtime-root", str(chain["custody_root"]),
            "--release-directory", str(chain["release_directory"]),
            "--experiment-family", "M101_METADATA_ONLY_FAMILY", "--fixed-trial-budget", "2",
            "--expires-at", chain["expires_at"], "--acknowledge", "WRONG",
        ],
        [
            "register-development-budget", "--trial-ledger", str(chain["temp"] / "wrong-budget.sqlite3"),
            "--budget-id", "wrong-ack-budget", "--experiment-family", "M101_METADATA_ONLY_FAMILY",
            "--total-trial-budget", "2", "--created-at", chain["issued_at"], "--acknowledge", "WRONG",
        ],
        [
            "revoke-development-permit", "--authority-root", str(chain["authority_root"]),
            "--permit-id", chain["permit"]["permit_id"],
            "--acknowledge", "WRONG",
        ],
        _admit_arguments(chain, descriptor_path, acknowledgement="WRONG"),
    ]
    for arguments in command_arguments:
        assert cli_module.main(arguments) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        failure = json.loads(captured.err)
        assert failure["status"] == "FAIL"
        assert failure["reason"].endswith("ACKNOWLEDGEMENT_REQUIRED")
        assert "Traceback" not in captured.err


def test_cli_read_only_commands_perform_no_durable_writes(
    chain: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    descriptor_path = _descriptor_file(chain)
    protected = [chain["source_backup"], chain["custody_root"], descriptor_path, chain["authority_root"]]
    before = _tree_fingerprint(protected)
    commands = [
        ["show-contract"],
        ["verify-backup-source", "--backup", str(chain["source_backup"])],
        ["plan-forward-custody-release", "--backup", str(chain["source_backup"])],
        ["certify-forward-custody-release", "--runtime-root", str(chain["custody_root"]), "--release-directory", str(chain["release_directory"])],
        ["verify-development-dataset", "--descriptor", str(descriptor_path), "--custody-runtime-root", str(chain["custody_root"]), "--release-directory", str(chain["release_directory"])],
        [
            "verify-development-permit", "--authority-root", str(chain["authority_root"]),
            "--permit-id", chain["permit"]["permit_id"], "--descriptor", str(descriptor_path),
            "--custody-runtime-root", str(chain["custody_root"]), "--release-directory", str(chain["release_directory"]),
            "--repository-commit", M100_COMPATIBLE_COMMIT, "--experiment-family", "M101_METADATA_ONLY_FAMILY",
            "--authorization-stage", "MISSION_101_DEVELOPMENT_ADMISSION", "--as-of", chain["as_of"],
        ],
        ["inspect-authority-runtime", "--authority-root", str(chain["authority_root"])],
    ]
    for arguments in commands:
        assert cli_module.main(arguments) == 0
        captured = capsys.readouterr()
        assert captured.err == ""
        assert isinstance(json.loads(captured.out), dict)
    assert _tree_fingerprint(protected) == before


def test_cli_backup_compatibility_is_exact_and_metadata_safe(
    source_backup: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_module.main(["verify-backup-source", "--backup", str(source_backup)]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert set(result) == {
        "schema_version", "source_backup_sha256", "source_manifest_hash",
        "source_contract_identity", "source_attests_mission100_remediation_contract_hash",
        "mission101_compatibility_policy", "batch_status_counts", "capture_batch_count",
        "distinct_code_commits", "code_commit_compatibility", "admissible_observation_count",
        "compatibility_verdict", "reason_token", "metadata_safe",
    }
    assert result["distinct_code_commits"] == [M100_COMPATIBLE_COMMIT]
    assert result["batch_status_counts"] == {"COMPLETE": 2, "FAILED": 1, "RUNNING": 0}
    assert result["source_contract_identity"]["attested_by_source_journal"] is True
    assert result["source_attests_mission100_remediation_contract_hash"] is False
    assert result["code_commit_compatibility"] == [{"code_commit": M100_COMPATIBLE_COMMIT, "allowed": True}]
    assert result["compatibility_verdict"] == "PASS"
    assert result["reason_token"] == "SOURCE_CODE_LINEAGE_COMPATIBLE"
    assert result["metadata_safe"] is True
    for protected_value in ("100.0", "101.0", "0.00010000", "0.00020000", "60000.0", "payload_json", "normalized_payload"):
        assert protected_value not in captured.out


def test_cli_backup_compatibility_reports_incompatible_commits_without_fabricating_lineage(
    tmp_path: Path,
    source_backup: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    incompatible_commit = "a" * 40
    incompatible = _mutate_sqlite_backup(
        source_backup,
        tmp_path / "incompatible-commit.zip",
        tmp_path,
        f"UPDATE capture_batches SET code_commit='{incompatible_commit}'",
    )
    assert cli_module.main(["verify-backup-source", "--backup", str(incompatible)]) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["distinct_code_commits"] == [incompatible_commit]
    assert result["code_commit_compatibility"] == [
        {"code_commit": incompatible_commit, "allowed": False}
    ]
    assert result["compatibility_verdict"] == "FAIL"
    assert result["reason_token"] == "SOURCE_CODE_LINEAGE_INCOMPATIBLE"
    assert result["source_attests_mission100_remediation_contract_hash"] is False
    assert result["mission101_compatibility_policy"]["fact_source"] == (
        "MISSION101_CONTRACT_REVIEW_NOT_SOURCE_ATTESTATION"
    )


def test_cli_malformed_path_and_repository_authority_failure_do_not_leak(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    private_path = (tmp_path / "private-evidence-name.zip").resolve()
    assert cli_module.main(["verify-backup-source", "--backup", str(private_path)]) == 2
    malformed = capsys.readouterr()
    assert malformed.out == ""
    assert json.loads(malformed.err) == {"reason": "BACKUP_INPUT_INVALID", "status": "FAIL"}
    assert str(private_path) not in malformed.err
    assert "Traceback" not in malformed.err

    forbidden = ROOT / "forbidden-cli-authority"
    assert cli_module.main([
        "init-research-authority-runtime", "--authority-root", str(forbidden),
        "--acknowledge", "INITIALIZE_M101_RESEARCH_AUTHORITY_RUNTIME",
    ]) == 2
    rejected = capsys.readouterr()
    assert rejected.out == ""
    assert json.loads(rejected.err) == {"reason": "AUTHORITY_ROOT_INSIDE_REPOSITORY", "status": "FAIL"}
    assert str(forbidden) not in rejected.err
    assert not forbidden.exists()


def test_cli_revocation_is_append_only_and_blocks_preflight_and_admission(
    chain: dict, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(authority_module, "trusted_utc_now", lambda: chain["as_of"])
    database = chain["authority_root"] / "authority.sqlite3"
    conn = sqlite3.connect(database)
    try:
        permit_before = conn.execute(
            "SELECT permit_hash,permit_json FROM permits WHERE permit_id=?",
            (chain["permit"]["permit_id"],),
        ).fetchone()
        events_before = conn.execute(
            "SELECT COUNT(*) FROM permit_events WHERE permit_id=?",
            (chain["permit"]["permit_id"],),
        ).fetchone()[0]
    finally:
        conn.close()
    assert cli_module.main([
        "revoke-development-permit",
        "--authority-root", str(chain["authority_root"]),
        "--permit-id", chain["permit"]["permit_id"],
        "--acknowledge", "REVOKE_M101_DEVELOPMENT_PERMIT",
    ]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "REVOKED"
    assert output["metadata_safe"] is True
    conn = sqlite3.connect(database)
    try:
        assert conn.execute(
            "SELECT permit_hash,permit_json FROM permits WHERE permit_id=?",
            (chain["permit"]["permit_id"],),
        ).fetchone() == permit_before
        assert conn.execute(
            "SELECT COUNT(*) FROM permit_events WHERE permit_id=?",
            (chain["permit"]["permit_id"],),
        ).fetchone()[0] == events_before + 1
    finally:
        conn.close()
    assert cli_module.main([
        "revoke-development-permit",
        "--authority-root", str(chain["authority_root"]),
        "--permit-id", chain["permit"]["permit_id"],
        "--acknowledge", "REVOKE_M101_DEVELOPMENT_PERMIT",
    ]) == 2
    duplicate = json.loads(capsys.readouterr().err)
    assert duplicate == {"reason": "PERMIT_NOT_REVOCABLE", "status": "FAIL"}
    assert chain["admission"].preflight(chain["request"])["reason_token"] == "PERMIT_REVOKED"
    assert chain["admission"].admit(chain["request"])["reason_token"] == "PERMIT_REVOKED"
    assert inspect_authority_runtime(chain["authority_root"])["permit_consumption_count"] == 0
    assert "unrevoke-development-permit" not in CLI_OPTIONS


@pytest.mark.parametrize("overrides,reason", [
    ({"data_class": "REAL_MARKET_VALIDATION"}, "VALIDATION_FORBIDDEN"),
    ({"split_identity": "REAL_MARKET_HOLDOUT"}, "HOLDOUT_FORBIDDEN"),
])
def test_cli_validation_and_holdout_stop_after_reservation(
    chain: dict,
    capsys: pytest.CaptureFixture[str],
    overrides: dict[str, str],
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_module, "get_repository_observation", lambda: _repository_observer()()
    )
    descriptor_path = _descriptor_file(chain)
    assert cli_module.main(_admit_arguments(chain, descriptor_path, **overrides)) == 0
    captured = capsys.readouterr()
    decision = json.loads(captured.out)
    assert decision["decision_token"] == "STOPPED"
    assert decision["reason_token"] == reason
    assert decision["execution_authorized"] is False
    assert chain["ledger"].reservation_count("m101-budget") == 1
    assert chain["ledger"].event_statuses(decision["trial_id"]) == ("RESERVED", "STOPPED")


def test_m94_m99_m100_operator_surfaces_remain_unchanged() -> None:
    from offchain.market_data_acquisition.__main__ import build_parser as build_m100_parser
    from offchain.market_data_control.__main__ import _parser as build_m99_parser

    assert not (ROOT / "offchain/research/admission/__main__.py").exists()
    m99 = next(item for item in build_m99_parser()._actions if isinstance(item, cli_module.argparse._SubParsersAction))
    m100 = next(item for item in build_m100_parser()._actions if isinstance(item, cli_module.argparse._SubParsersAction))
    assert set(m99.choices) == {
        "show-contract", "init-runtime", "audit-legacy", "plan-legacy-release",
        "build-legacy-release", "certify-release", "inspect-recovery", "resolve",
    }
    assert set(m100.choices) == {
        "show-contract", "init-runtime", "verify-journal", "capture-once",
        "export-backup", "verify-backup",
    }
