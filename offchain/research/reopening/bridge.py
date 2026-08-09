"""Independent Mission 100 backup verification and forward-custody derivation."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from typing import Any, Iterator, Mapping
import zipfile

from offchain.market_data_acquisition import backup as m100_backup
from offchain.market_data_acquisition.journal import Journal, RUNTIME_SUBDIRS, verify_journal

from .core import (
    FORWARD_PROFILE,
    MISSION100_HASH,
    MISSION100_ID,
    MISSION100_REMEDIATION_HASH,
    MISSION100_REMEDIATION_ID,
    ReopeningError,
    canonical_hash,
    canonical_json,
    load_contracts,
    require_commit,
    sha256_bytes,
    sha256_file,
    strict_json_load,
)


MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_MEMBERS = 100_001
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_MEMBER_BYTES = 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024


def _safe_member_name(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\x00" in name:
        raise ReopeningError("BACKUP_MEMBER_PATH_INVALID", name)
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or pure.as_posix() != name:
        raise ReopeningError("BACKUP_MEMBER_PATH_INVALID", name)
    return pure


def _validate_zip_info(info: zipfile.ZipInfo) -> None:
    _safe_member_name(info.filename)
    if info.is_dir():
        raise ReopeningError("BACKUP_SPECIAL_MEMBER_REJECTED", info.filename)
    file_type = (info.external_attr >> 16) & 0o170000
    if file_type not in {0, stat.S_IFREG}:
        raise ReopeningError("BACKUP_SPECIAL_MEMBER_REJECTED", info.filename)
    if info.flag_bits & 0x1:
        raise ReopeningError("BACKUP_ENCRYPTED_MEMBER_REJECTED", info.filename)
    if info.file_size < 0 or info.file_size > MAX_MEMBER_BYTES:
        raise ReopeningError("BACKUP_MEMBER_SIZE_LIMIT", info.filename)


def _read_manifest(archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo]) -> tuple[dict[str, Any], str]:
    names = [item.filename for item in infos]
    if len(names) != len(set(names)):
        raise ReopeningError("BACKUP_DUPLICATE_MEMBER")
    if "manifest.json" not in names:
        raise ReopeningError("BACKUP_MANIFEST_MISSING")
    info = archive.getinfo("manifest.json")
    if info.file_size > MAX_MANIFEST_BYTES:
        raise ReopeningError("BACKUP_MANIFEST_SIZE_LIMIT")
    raw = archive.read(info)
    value = strict_json_load(raw, maximum_bytes=MAX_MANIFEST_BYTES)
    fields = {"schema_version", "created_at", "journal_schema_fingerprint", "files", "manifest_hash"}
    if not isinstance(value, dict) or set(value) != fields or value.get("schema_version") != "1.0":
        raise ReopeningError("BACKUP_MANIFEST_SCHEMA_INVALID")
    if (canonical_json(value) + "\n").encode("utf-8") != raw:
        raise ReopeningError("BACKUP_MANIFEST_NONCANONICAL")
    declared_hash = value["manifest_hash"]
    core = dict(value)
    core.pop("manifest_hash")
    if declared_hash != canonical_hash(core):
        raise ReopeningError("BACKUP_MANIFEST_HASH_MISMATCH")
    files = value["files"]
    if not isinstance(files, list) or len(files) > MAX_MEMBERS - 1:
        raise ReopeningError("BACKUP_MANIFEST_FILES_INVALID")
    expected = {"manifest.json"}
    total = 0
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise ReopeningError("BACKUP_MANIFEST_ENTRY_INVALID")
        rel = entry["path"]
        if type(rel) is not str or rel == "manifest.json":
            raise ReopeningError("BACKUP_MANIFEST_ENTRY_INVALID")
        _safe_member_name(rel)
        if rel in expected:
            raise ReopeningError("BACKUP_DUPLICATE_MEMBER", rel)
        if type(entry["size"]) is not int or not 0 <= entry["size"] <= MAX_MEMBER_BYTES:
            raise ReopeningError("BACKUP_MANIFEST_ENTRY_INVALID")
        if type(entry["sha256"]) is not str or len(entry["sha256"]) != 64:
            raise ReopeningError("BACKUP_MANIFEST_ENTRY_INVALID")
        total += entry["size"]
        if total > MAX_TOTAL_MEMBER_BYTES:
            raise ReopeningError("BACKUP_TOTAL_MEMBER_SIZE_LIMIT")
        expected.add(rel)
    if set(names) != expected:
        raise ReopeningError("BACKUP_FILE_SET_MISMATCH")
    for entry in files:
        member_info = archive.getinfo(entry["path"])
        if member_info.file_size != entry["size"]:
            raise ReopeningError("BACKUP_FILE_SIZE_MISMATCH", entry["path"])
        data = archive.read(member_info)
        if len(data) != entry["size"] or sha256_bytes(data) != entry["sha256"]:
            raise ReopeningError("BACKUP_FILE_HASH_MISMATCH", entry["path"])
    return value, declared_hash


@contextmanager
def _verified_materialization(source: Path) -> Iterator[tuple[Path, dict[str, Any], str]]:
    if not source.is_absolute() or source.is_symlink() or not source.is_file():
        raise ReopeningError("BACKUP_INPUT_INVALID")
    if source.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ReopeningError("BACKUP_ARCHIVE_SIZE_LIMIT")
    try:
        m100_backup.verify_backup(source)
    except Exception as error:
        reason = getattr(error, "reason", "BACKUP_ARCHIVE_INVALID")
        raise ReopeningError(str(reason)) from error
    try:
        archive = zipfile.ZipFile(source, "r")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        raise ReopeningError("BACKUP_ARCHIVE_INVALID") from error
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ReopeningError("BACKUP_MEMBER_COUNT_LIMIT")
        for info in infos:
            _validate_zip_info(info)
        manifest, manifest_hash = _read_manifest(archive, infos)
        # macOS commonly exposes /var as a symlink to /private/var. Resolve the
        # newly created private directory before passing it to Mission 100's
        # lexical symlink guard.
        temp_parent = Path(tempfile.mkdtemp(prefix="deltagrid-m101-source-")).resolve(strict=True)
        os.chmod(temp_parent, 0o700)
        runtime = temp_parent / "runtime"
        runtime.mkdir(mode=0o700)
        try:
            for relative in RUNTIME_SUBDIRS:
                path = runtime / relative
                path.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.chmod(path, 0o700)
            for entry in manifest["files"]:
                pure = _safe_member_name(entry["path"])
                target = runtime.joinpath(*pure.parts)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                current = runtime
                for part in pure.parts[:-1]:
                    current = current / part
                    if current.is_symlink():
                        raise ReopeningError("BACKUP_MATERIALIZATION_ESCAPE")
                    os.chmod(current, 0o700)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                fd = os.open(target, flags, 0o600)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        with archive.open(entry["path"], "r") as member:
                            shutil.copyfileobj(member, stream, length=1024 * 1024)
                        stream.flush()
                        os.fsync(stream.fileno())
                finally:
                    if not target.exists():
                        try:
                            os.close(fd)
                        except OSError:
                            pass
                os.chmod(target, 0o600, follow_symlinks=False)
            yield runtime, manifest, manifest_hash
        finally:
            shutil.rmtree(temp_parent)


def _derive_custody_records(rows: list[Mapping[str, Any]], receipts: Mapping[str, Mapping[str, Any]], objects: Mapping[str, Mapping[str, Any]], batches: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    source_to_custody: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (item["logical_id"], item["revision_number"])):
        receipt = receipts[row["receipt_hash"]]
        obj = objects[receipt["object_sha256"]]
        parent = row["supersedes_record_hash"]
        if parent is not None and parent not in source_to_custody:
            raise ReopeningError("FORWARD_REVISION_PARENT_MISSING")
        core = {
            "schema_version": "1.0",
            "profile_id": FORWARD_PROFILE,
            "lineage_class": "M100_FORWARD_OBSERVED",
            "custody_logical_id": canonical_hash({"profile_id": FORWARD_PROFILE, "source_logical_id": row["logical_id"]}),
            "source_m100_logical_id": row["logical_id"],
            "source_m100_record_hash": row["record_hash"],
            "source_m100_batch_id": row["batch_id"],
            "source_m100_code_commit": batches[row["batch_id"]]["code_commit"],
            "source_m100_receipt_hash": row["receipt_hash"],
            "source_m100_response_hash": row["response_hash"],
            "source_m100_object_sha256": receipt["object_sha256"],
            "source_m100_body_sha256": receipt["body_sha256"],
            "source_m100_payload_hash": row["payload_hash"],
            "provider": "BINANCE_PUBLIC",
            "stream": row["stream"],
            "symbol": row["symbol"],
            "interval": row["interval"],
            "event_time_ms": row["event_time_ms"],
            "source_time_ms": None,
            "available_at": row["available_at"],
            "first_observed_at": receipt["received_at"],
            "last_verified_at": receipt["received_at"],
            "availability_class": "OBSERVED_LIVE",
            "clock_health": receipt["clock_status"],
            "revision_number": row["revision_number"],
            "source_supersedes_record_hash": parent,
            "supersedes_custody_record_hash": None if parent is None else source_to_custody[parent],
        }
        custody_hash = canonical_hash(core)
        if custody_hash == row["record_hash"]:
            raise ReopeningError("SOURCE_DERIVED_IDENTITY_COLLISION")
        record = dict(core)
        record["custody_record_hash"] = custody_hash
        source_to_custody[row["record_hash"]] = custody_hash
        records.append(record)
    return records


def _inspect_source_backup(path: str | Path, *, enforce_compatibility: bool) -> dict[str, Any]:
    _autonomy, mission = load_contracts()
    source = Path(path).expanduser()
    if not source.is_absolute():
        raise ReopeningError("BACKUP_INPUT_NOT_ABSOLUTE")
    current = source
    while True:
        if current.is_symlink():
            raise ReopeningError("BACKUP_INPUT_SYMLINK")
        if current == current.parent:
            break
        current = current.parent
    try:
        source = source.resolve(strict=True)
    except OSError as error:
        raise ReopeningError("BACKUP_INPUT_INVALID") from error
    with _verified_materialization(source) as (runtime, manifest, manifest_hash):
        try:
            verification = verify_journal(runtime, scan_objects=True)
        except Exception as error:
            reason = getattr(error, "reason", "SOURCE_JOURNAL_INVALID")
            raise ReopeningError(str(reason)) from error
        with Journal.open(runtime, readonly=True) as journal:
            conn = journal.conn
            metadata = {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM metadata ORDER BY key")}
            batches = {row["batch_id"]: dict(row) for row in conn.execute("SELECT * FROM capture_batches ORDER BY batch_id")}
            allowed = set(mission["source_code_compatibility_policy"]["allowed_code_commits"])
            for batch in batches.values():
                require_commit(batch["code_commit"], "source_code_commit")
                if batch["contract_hash"] != MISSION100_HASH:
                    raise ReopeningError("SOURCE_CONTRACT_HASH_MISMATCH")
            code_commits = sorted({item["code_commit"] for item in batches.values()})
            commit_compatibility = [
                {"code_commit": commit, "allowed": commit in allowed}
                for commit in code_commits
            ]
            compatible = all(item["allowed"] for item in commit_compatibility)
            compatibility_reason = (
                "SOURCE_CODE_LINEAGE_COMPATIBLE"
                if compatible
                else "SOURCE_CODE_LINEAGE_INCOMPATIBLE"
            )
            if enforce_compatibility and not compatible:
                raise ReopeningError(compatibility_reason)
            receipts = {row["receipt_hash"]: dict(row) for row in conn.execute("SELECT * FROM receipts ORDER BY receipt_hash")}
            objects = {row["object_sha256"]: dict(row) for row in conn.execute("SELECT * FROM raw_objects ORDER BY object_sha256")}
            rows = [dict(row) for row in conn.execute(
                "SELECT o.* FROM observations o JOIN capture_batches b ON b.batch_id=o.batch_id "
                "WHERE b.status='COMPLETE' ORDER BY o.logical_id,o.revision_number"
            )]
            failed_observations = int(conn.execute(
                "SELECT COUNT(*) FROM observations o JOIN capture_batches b ON b.batch_id=o.batch_id WHERE b.status='FAILED'"
            ).fetchone()[0])
            if failed_observations:
                raise ReopeningError("FAILED_BATCH_OBSERVATION_PRESENT")
            records = _derive_custody_records(rows, receipts, objects, batches)
            source_facts = {
                "source_mission100_contract_id": MISSION100_ID,
                "source_mission100_contract_hash": metadata.get("mission100_contract_hash"),
                "source_attests_mission100_remediation_contract_hash": False,
                "batch_ids": sorted(batches),
                "code_commits": code_commits,
                "receipt_hashes": sorted(receipts),
                "response_hashes": sorted({item["response_hash"] for item in receipts.values()}),
                "source_record_hashes": sorted(item["record_hash"] for item in rows),
                "raw_object_hashes": sorted(objects),
                "failed_batch_ids": sorted(key for key, value in batches.items() if value["status"] == "FAILED"),
            }
            if source_facts["source_mission100_contract_hash"] != MISSION100_HASH:
                raise ReopeningError("SOURCE_CONTRACT_HASH_MISMATCH")
            return {
                "schema_version": "1.0",
                "source_backup_sha256": sha256_file(source, maximum_bytes=MAX_ARCHIVE_BYTES),
                "source_manifest_hash": manifest_hash,
                "source_manifest_schema_fingerprint": manifest["journal_schema_fingerprint"],
                "source_facts": source_facts,
                "compatibility_review": {
                    "policy_id": mission["source_code_compatibility_policy"]["policy_id"],
                    "mission100_remediation_contract_id": MISSION100_REMEDIATION_ID,
                    "mission100_remediation_contract_hash": MISSION100_REMEDIATION_HASH,
                    "compatibility_fact_source": "MISSION101_CONTRACT_REVIEW_NOT_SOURCE_ATTESTATION",
                    "commit_compatibility": commit_compatibility,
                    "verdict": "PASS" if compatible else "FAIL",
                    "reason_token": compatibility_reason,
                },
                "journal_verification": verification,
                "custody_records": records,
                "complete_batch_count": sum(item["status"] == "COMPLETE" for item in batches.values()),
                "failed_batch_count": sum(item["status"] == "FAILED" for item in batches.values()),
                "admissible_observation_count": len(records),
            }


def inspect_source_backup(path: str | Path) -> dict[str, Any]:
    """Verify exact source evidence and require frozen code-lineage compatibility."""

    return _inspect_source_backup(path, enforce_compatibility=True)


def inspect_backup_compatibility(path: str | Path) -> dict[str, Any]:
    """Return a bounded metadata-only source and compatibility review projection."""

    evidence = _inspect_source_backup(path, enforce_compatibility=False)
    facts = evidence["source_facts"]
    review = evidence["compatibility_review"]
    counts = evidence["journal_verification"]["counts"]
    return {
        "schema_version": "1.0",
        "source_backup_sha256": evidence["source_backup_sha256"],
        "source_manifest_hash": evidence["source_manifest_hash"],
        "source_contract_identity": {
            "contract_id": facts["source_mission100_contract_id"],
            "contract_hash_sha256": facts["source_mission100_contract_hash"],
            "attested_by_source_journal": True,
        },
        "source_attests_mission100_remediation_contract_hash": False,
        "mission101_compatibility_policy": {
            "policy_id": review["policy_id"],
            "remediation_contract_id": review["mission100_remediation_contract_id"],
            "remediation_contract_hash_sha256": review["mission100_remediation_contract_hash"],
            "fact_source": review["compatibility_fact_source"],
        },
        "batch_status_counts": {
            "COMPLETE": evidence["complete_batch_count"],
            "FAILED": evidence["failed_batch_count"],
            "RUNNING": 0,
        },
        "capture_batch_count": counts["capture_batches"],
        "distinct_code_commits": facts["code_commits"],
        "code_commit_compatibility": review["commit_compatibility"],
        "admissible_observation_count": evidence["admissible_observation_count"],
        "compatibility_verdict": review["verdict"],
        "reason_token": review["reason_token"],
        "metadata_safe": True,
    }
