"""Atomic forward-custody release publication and independent certification."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
from typing import Any, Mapping

from .bridge import MAX_ARCHIVE_BYTES, inspect_source_backup
from .core import (
    AUTONOMY_V3_HASH,
    AUTONOMY_V3_ID,
    FORWARD_PROFILE,
    MISSION101_HASH,
    MISSION101_ID,
    REPOSITORY_ROOT,
    ReopeningError,
    canonical_hash,
    canonical_json,
    load_contracts,
    require_hash,
    sha256_bytes,
    sha256_file,
    strict_json_load,
)


ACK_BUILD_RELEASE = "BUILD_M101_FORWARD_CUSTODY_RELEASE"
MAX_RELEASE_JSON_BYTES = 256 * 1024 * 1024
MAX_CERTIFICATE_BYTES = 512 * 1024
MAX_RECORDS = 300_000


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _reject_symlink_components(path: Path) -> None:
    current = path
    while True:
        if current.is_symlink():
            raise ReopeningError("PATH_SYMLINK_REJECTED")
        if current == current.parent:
            break
        current = current.parent


def _runtime_root(path: str | Path, *, create: bool) -> Path:
    lexical = Path(path).expanduser()
    if not lexical.is_absolute():
        raise ReopeningError("RUNTIME_ROOT_NOT_ABSOLUTE")
    _reject_symlink_components(lexical)
    resolved = lexical.resolve(strict=False)
    if _inside(resolved, REPOSITORY_ROOT.resolve(strict=True)):
        raise ReopeningError("RUNTIME_ROOT_INSIDE_REPOSITORY")
    if create and not resolved.exists():
        resolved.mkdir(parents=True, mode=0o700)
    if resolved.is_symlink() or not resolved.is_dir():
        raise ReopeningError("RUNTIME_ROOT_INVALID")
    if stat.S_IMODE(resolved.stat().st_mode) != 0o700:
        raise ReopeningError("RUNTIME_DIRECTORY_MODE_INVALID")
    for name in ("releases", "staging"):
        child = resolved / name
        if create and not child.exists():
            child.mkdir(mode=0o700)
        if child.is_symlink() or not child.is_dir() or stat.S_IMODE(child.stat().st_mode) != 0o700:
            raise ReopeningError("RUNTIME_LAYOUT_INVALID", name)
    return resolved


def _write_exclusive(path: Path, raw: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(path, 0o600, follow_symlinks=False)


def _copy_exclusive(source: Path, destination: Path) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(destination, flags, 0o600)
    try:
        with source.open("rb") as input_stream, os.fdopen(fd, "wb", closefd=False) as output_stream:
            shutil.copyfileobj(input_stream, output_stream, length=1024 * 1024)
            output_stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(destination, 0o600, follow_symlinks=False)


def _release_core(source: Mapping[str, Any]) -> dict[str, Any]:
    records = source.get("custody_records")
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise ReopeningError("RELEASE_RECORD_LIMIT")
    return {
        "schema_version": "1.0",
        "profile_id": FORWARD_PROFILE,
        "lineage_class": "M100_FORWARD_OBSERVED",
        "autonomy_contract": {"contract_id": AUTONOMY_V3_ID, "contract_hash_sha256": AUTONOMY_V3_HASH},
        "mission101_contract": {"contract_id": MISSION101_ID, "contract_hash_sha256": MISSION101_HASH},
        "source_backup_sha256": source["source_backup_sha256"],
        "source_manifest_hash": source["source_manifest_hash"],
        "source_manifest_schema_fingerprint": source["source_manifest_schema_fingerprint"],
        "source_facts": source["source_facts"],
        "compatibility_review": source["compatibility_review"],
        "custody_records": records,
        "custody_record_set_hash": canonical_hash(sorted(item["custody_record_hash"] for item in records)),
        "counts": {
            "complete_batches": source["complete_batch_count"],
            "failed_batches_preserved": source["failed_batch_count"],
            "admissible_observations": source["admissible_observation_count"],
        },
        "authority_boundary": {
            "metadata_only": True,
            "result_bearing_research_execution": False,
            "validation": False,
            "holdout": False,
            "model_or_ml": False,
            "signals": False,
            "paper": False,
            "live": False,
            "exchange_credentials_orders_or_capital": False,
            "self_authorization": False,
        },
    }


def _load_release_document(directory: Path) -> tuple[dict[str, Any], bytes]:
    path = directory / "release.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_RELEASE_JSON_BYTES:
        raise ReopeningError("RELEASE_DOCUMENT_INVALID")
    raw = path.read_bytes()
    value = strict_json_load(raw, maximum_bytes=MAX_RELEASE_JSON_BYTES)
    if not isinstance(value, dict) or set(value) != {"schema_version", "release_id", "release_core_hash", "release_core"}:
        raise ReopeningError("RELEASE_DOCUMENT_SCHEMA_INVALID")
    if (canonical_json(value) + "\n").encode("utf-8") != raw:
        raise ReopeningError("RELEASE_DOCUMENT_NONCANONICAL")
    return value, raw


def _reconstruct(directory: Path) -> tuple[dict[str, Any], bytes, str]:
    expected_files = {"source-backup.zip", "release.json", "certificate.json"}
    actual = {item.name for item in directory.iterdir()}
    if actual != expected_files:
        raise ReopeningError("RELEASE_FILE_SET_INVALID")
    for item in directory.iterdir():
        if item.is_symlink() or not item.is_file() or stat.S_IMODE(item.stat().st_mode) != 0o600:
            raise ReopeningError("RELEASE_FILE_INVALID", item.name)
    backup_path = directory / "source-backup.zip"
    if backup_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ReopeningError("BACKUP_ARCHIVE_SIZE_LIMIT")
    source = inspect_source_backup(backup_path)
    core = _release_core(source)
    core_hash = canonical_hash(core)
    release_id = f"m101-forward-{core_hash}"
    document, release_raw = _load_release_document(directory)
    if document != {
        "schema_version": "1.0",
        "release_id": release_id,
        "release_core_hash": core_hash,
        "release_core": core,
    }:
        raise ReopeningError("RELEASE_RECONSTRUCTION_MISMATCH")
    backup_raw_hash = sha256_file(backup_path, maximum_bytes=MAX_ARCHIVE_BYTES)
    if backup_raw_hash != core["source_backup_sha256"]:
        raise ReopeningError("SOURCE_BACKUP_IDENTITY_MISMATCH")
    return document, release_raw, backup_raw_hash


def _certificate_document(directory: Path) -> dict[str, Any]:
    document, release_raw, backup_hash = _reconstruct(directory)
    core = {
        "schema_version": "1.0",
        "release_id": document["release_id"],
        "release_core_hash": document["release_core_hash"],
        "profile_id": FORWARD_PROFILE,
        "release_file_sha256": sha256_bytes(release_raw),
        "source_backup_sha256": backup_hash,
        "custody_record_set_hash": document["release_core"]["custody_record_set_hash"],
        "record_count": document["release_core"]["counts"]["admissible_observations"],
        "verdict": "CERTIFIED",
        "metadata_safe": True,
    }
    return {"certificate_core": core, "certificate_hash": canonical_hash(core)}


def plan_forward_release(backup_path: str | Path) -> dict[str, Any]:
    """Return the deterministic metadata-only release identity without writing."""

    load_contracts()
    source = inspect_source_backup(backup_path)
    core = _release_core(source)
    core_hash = canonical_hash(core)
    return {
        "schema_version": "1.0",
        "release_id": f"m101-forward-{core_hash}",
        "release_core_hash": core_hash,
        "profile_id": FORWARD_PROFILE,
        "source_backup_sha256": source["source_backup_sha256"],
        "source_manifest_hash": source["source_manifest_hash"],
        "custody_record_set_hash": core["custody_record_set_hash"],
        "record_count": core["counts"]["admissible_observations"],
        "complete_batch_count": core["counts"]["complete_batches"],
        "failed_batch_count": core["counts"]["failed_batches_preserved"],
        "compatibility_verdict": source["compatibility_review"]["verdict"],
        "reason_token": source["compatibility_review"]["reason_token"],
        "writes_performed": False,
        "metadata_safe": True,
    }


def build_forward_release(backup_path: str | Path, runtime_root: str | Path, *, acknowledgement: str) -> dict[str, Any]:
    """Publish one immutable release after independently reloading staged bytes."""

    if acknowledgement != ACK_BUILD_RELEASE:
        raise ReopeningError("RELEASE_ACKNOWLEDGEMENT_REQUIRED")
    load_contracts()
    source_path = Path(backup_path).expanduser()
    if not source_path.is_absolute():
        raise ReopeningError("BACKUP_INPUT_NOT_ABSOLUTE")
    _reject_symlink_components(source_path)
    source_path = source_path.resolve(strict=True)
    source = inspect_source_backup(source_path)
    core = _release_core(source)
    core_hash = canonical_hash(core)
    release_id = f"m101-forward-{core_hash}"
    root = _runtime_root(runtime_root, create=True)
    final = root / "releases" / release_id
    if final.exists():
        raise ReopeningError("RELEASE_ALREADY_EXISTS")
    stage = root / "staging" / release_id
    if stage.exists():
        raise ReopeningError("RELEASE_STAGING_EXISTS")
    stage.mkdir(mode=0o700)
    try:
        backup_target = stage / "source-backup.zip"
        _copy_exclusive(source_path, backup_target)
        release = {
            "schema_version": "1.0",
            "release_id": release_id,
            "release_core_hash": core_hash,
            "release_core": core,
        }
        _write_exclusive(stage / "release.json", (canonical_json(release) + "\n").encode("utf-8"))
        placeholder = stage / "certificate.json"
        _write_exclusive(placeholder, b"{}\n")
        certificate = _certificate_document(stage)
        placeholder.unlink()
        _write_exclusive(placeholder, (canonical_json(certificate) + "\n").encode("utf-8"))
        certified = certify_forward_release(stage, runtime_root=root, allow_staging=True)
        os.replace(stage, final)
        certified = certify_forward_release(final, runtime_root=root)
        return certified
    except Exception:
        # Preserve failed staged evidence for explicit operator inspection.
        # The deterministic stage name also prevents a silent retry/replace.
        raise


def certify_forward_release(release_directory: str | Path, *, runtime_root: str | Path, allow_staging: bool = False) -> dict[str, Any]:
    """Independently verify persisted release bytes; never create or repair evidence."""

    load_contracts()
    root = _runtime_root(runtime_root, create=False)
    lexical = Path(release_directory)
    if not lexical.is_absolute():
        lexical = Path.cwd() / lexical
    _reject_symlink_components(lexical)
    directory = lexical.resolve(strict=True)
    permitted = {root / "releases"}
    if allow_staging:
        permitted.add(root / "staging")
    if directory.parent not in permitted or directory.is_symlink() or not directory.is_dir():
        raise ReopeningError("RELEASE_DIRECTORY_LOCATION_INVALID")
    if stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise ReopeningError("RELEASE_DIRECTORY_MODE_INVALID")
    document, _release_raw, _backup_hash = _reconstruct(directory)
    expected = _certificate_document(directory)
    certificate_path = directory / "certificate.json"
    if certificate_path.stat().st_size > MAX_CERTIFICATE_BYTES:
        raise ReopeningError("CERTIFICATE_SIZE_LIMIT")
    raw = certificate_path.read_bytes()
    stored = strict_json_load(raw, maximum_bytes=MAX_CERTIFICATE_BYTES)
    if stored != expected or (canonical_json(stored) + "\n").encode("utf-8") != raw:
        raise ReopeningError("CERTIFICATE_RECONSTRUCTION_MISMATCH")
    if directory.parent == root / "releases" and directory.name != document["release_id"]:
        raise ReopeningError("RELEASE_DIRECTORY_ID_MISMATCH")
    return {
        "release_id": document["release_id"],
        "release_core_hash": document["release_core_hash"],
        "certificate_hash": expected["certificate_hash"],
        "profile_id": FORWARD_PROFILE,
        "record_count": expected["certificate_core"]["record_count"],
        "verdict": "CERTIFIED",
        "metadata_safe": True,
    }


def load_certified_release_metadata(release_directory: str | Path, *, runtime_root: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    certificate = certify_forward_release(release_directory, runtime_root=runtime_root)
    document, _raw = _load_release_document(Path(release_directory).resolve(strict=True))
    return certificate, document["release_core"]
