"""Verified local backup export and validation for Mission 100."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile
from typing import Any

from .core import AcquisitionError, REPOSITORY_ROOT, canonical_hash, canonical_json, load_contracts, sha256_bytes, strict_json_load, utc_now_ms
from .journal import JOURNAL_NAME, Journal, acquisition_lock, validate_runtime_root, verify_journal


ACK_BACKUP = "EXPORT_ACQUISITION_BACKUP"
MAX_BACKUP_FILES = 100_000
MAX_BACKUP_ARCHIVE_BYTES = 1 * 1024 * 1024 * 1024
MAX_BACKUP_MEMBER_BYTES = 512 * 1024 * 1024


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()




def _reject_symlink_components(path: Path) -> None:
    current = path
    while True:
        if current.exists() and current.is_symlink():
            raise AcquisitionError("BACKUP_DESTINATION_SYMLINK")
        if current == current.parent:
            break
        current = current.parent


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True

def export_backup(
    runtime_root: str | Path,
    destination: str | Path,
    *,
    acknowledgement: str,
) -> dict[str, Any]:
    if acknowledgement != ACK_BACKUP:
        raise AcquisitionError("BACKUP_ACKNOWLEDGEMENT_REQUIRED")
    load_contracts()
    runtime = validate_runtime_root(runtime_root)
    dest_lexical = Path(destination).expanduser()
    if not dest_lexical.is_absolute():
        raise AcquisitionError("BACKUP_DESTINATION_NOT_ABSOLUTE")
    _reject_symlink_components(dest_lexical.parent)
    if dest_lexical.exists() and dest_lexical.is_symlink():
        raise AcquisitionError("BACKUP_DESTINATION_SYMLINK")
    dest = dest_lexical.resolve(strict=False)
    if _is_within(dest, runtime):
        raise AcquisitionError("BACKUP_DESTINATION_INSIDE_RUNTIME")
    repository = REPOSITORY_ROOT.resolve(strict=True)
    if _is_within(dest, repository):
        raise AcquisitionError("BACKUP_DESTINATION_INSIDE_REPOSITORY")
    if dest.exists():
        raise AcquisitionError("BACKUP_DESTINATION_EXISTS")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(dest.parent)

    with acquisition_lock(runtime, timeout_seconds=2.0):
        verification = verify_journal(runtime, scan_objects=True)
        with tempfile.TemporaryDirectory(prefix="deltagrid-m100-backup-") as temp_dir:
            temp = Path(temp_dir)
            db_copy = temp / JOURNAL_NAME
            source = sqlite3.connect(runtime / JOURNAL_NAME)
            target = sqlite3.connect(db_copy)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()

            files: list[tuple[str, Path]] = [(JOURNAL_NAME, db_copy)]
            with Journal.open(runtime, readonly=True) as journal:
                for row in journal.conn.execute("SELECT relative_path FROM raw_objects ORDER BY relative_path"):
                    rel = str(row[0])
                    path = runtime / rel
                    files.append((rel, path))
            if len(files) > MAX_BACKUP_FILES:
                raise AcquisitionError("BACKUP_FILE_COUNT_LIMIT")

            manifest_files = [
                {
                    "path": rel,
                    "sha256": _sha_file(path),
                    "size": path.stat().st_size,
                }
                for rel, path in files
            ]
            created_at, _ = utc_now_ms()
            manifest_core = {
                "schema_version": "1.0",
                "created_at": created_at,
                "journal_schema_fingerprint": verification["schema_fingerprint"],
                "files": manifest_files,
            }
            manifest = dict(manifest_core)
            manifest["manifest_hash"] = canonical_hash(manifest_core)
            manifest_bytes = (canonical_json(manifest) + "\n").encode("utf-8")

            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(dest, flags, 0o600)
            try:
                with os.fdopen(fd, "w+b", closefd=False) as stream:
                    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                        for rel, path in files:
                            archive.write(path, arcname=rel)
                        archive.writestr("manifest.json", manifest_bytes)
                    stream.flush()
                    os.fsync(fd)
            finally:
                os.close(fd)
            os.chmod(dest, 0o600, follow_symlinks=False)

    return {
        "backup_path": str(dest),
        "manifest_hash": manifest["manifest_hash"],
        "file_count": len(files),
        "backup_sha256": _sha_file(dest),
    }


def verify_backup(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file() or source.is_symlink():
        raise AcquisitionError("BACKUP_INPUT_INVALID")
    if source.stat().st_size > MAX_BACKUP_ARCHIVE_BYTES:
        raise AcquisitionError("BACKUP_ARCHIVE_SIZE_LIMIT")
    with zipfile.ZipFile(source, "r") as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) > MAX_BACKUP_FILES + 1:
            raise AcquisitionError("BACKUP_FILE_COUNT_LIMIT")
        if len(names) != len(set(names)):
            raise AcquisitionError("BACKUP_DUPLICATE_MEMBER")
        for info in infos:
            member = Path(info.filename)
            if member.is_absolute() or ".." in member.parts or "\\" in info.filename:
                raise AcquisitionError("BACKUP_MEMBER_PATH_INVALID", info.filename)
            if info.file_size > MAX_BACKUP_MEMBER_BYTES:
                raise AcquisitionError("BACKUP_MEMBER_SIZE_LIMIT", info.filename)
        if "manifest.json" not in names:
            raise AcquisitionError("BACKUP_MANIFEST_MISSING")
        manifest_info = archive.getinfo("manifest.json")
        if manifest_info.file_size > 8 * 1024 * 1024:
            raise AcquisitionError("BACKUP_MANIFEST_SIZE_LIMIT")
        manifest = strict_json_load(archive.read("manifest.json"))
        if not isinstance(manifest, dict) or set(manifest) != {
            "schema_version", "created_at", "journal_schema_fingerprint", "files", "manifest_hash"
        }:
            raise AcquisitionError("BACKUP_MANIFEST_SCHEMA_INVALID")
        declared = manifest.pop("manifest_hash")
        if declared != canonical_hash(manifest):
            raise AcquisitionError("BACKUP_MANIFEST_HASH_MISMATCH")
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) > MAX_BACKUP_FILES:
            raise AcquisitionError("BACKUP_MANIFEST_FILES_INVALID")
        expected_names: set[str] = {"manifest.json"}
        for entry in files:
            if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
                raise AcquisitionError("BACKUP_MANIFEST_ENTRY_INVALID")
            rel = entry["path"]
            if not isinstance(rel, str) or not rel or rel == "manifest.json":
                raise AcquisitionError("BACKUP_MANIFEST_ENTRY_INVALID")
            member = Path(rel)
            if member.is_absolute() or ".." in member.parts or "\\" in rel:
                raise AcquisitionError("BACKUP_MEMBER_PATH_INVALID", rel)
            if rel in expected_names:
                raise AcquisitionError("BACKUP_DUPLICATE_MEMBER", rel)
            if type(entry["size"]) is not int or entry["size"] < 0 or entry["size"] > MAX_BACKUP_MEMBER_BYTES:
                raise AcquisitionError("BACKUP_MANIFEST_ENTRY_INVALID")
            if not isinstance(entry["sha256"], str) or len(entry["sha256"]) != 64:
                raise AcquisitionError("BACKUP_MANIFEST_ENTRY_INVALID")
            expected_names.add(rel)
        if set(names) != expected_names:
            raise AcquisitionError("BACKUP_FILE_SET_MISMATCH")
        for entry in files:
            info = archive.getinfo(entry["path"])
            if info.file_size != entry["size"]:
                raise AcquisitionError("BACKUP_FILE_SIZE_MISMATCH", entry["path"])
            data = archive.read(info)
            if len(data) != entry["size"] or sha256_bytes(data) != entry["sha256"]:
                raise AcquisitionError("BACKUP_FILE_HASH_MISMATCH", entry["path"])
    return {
        "verdict": "PASS",
        "manifest_hash": declared,
        "file_count": len(files),
        "backup_sha256": _sha_file(source),
    }
