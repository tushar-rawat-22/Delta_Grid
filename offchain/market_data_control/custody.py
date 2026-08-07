"""Secure runtime custody, publication, recovery inspection, and legacy audit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import time
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import quote, urlsplit

from .certifier import (
    certify_release,
    load_certified_snapshot,
    load_staged_snapshot,
    staged_certificate_document,
    verify_completed_stage,
)
from .core import (
    AUTONOMY_CONTRACT_HASH,
    AVAILABILITY_POLICY_ID,
    MISSION_CONTRACT_HASH,
    NORMALIZER_ID,
    PROTECTED_BOUNDARY,
    RELEASE_KIND,
    REPOSITORY_ROOT,
    AcquisitionReceipt,
    AvailabilityClass,
    ClockHealth,
    ControlPlaneError,
    LegacyAcquisitionReceipt,
    ObservationVersion,
    canonical_hash,
    canonical_json,
    deep_freeze,
    deep_thaw,
    load_contracts,
    parse_utc,
    read_bounded_regular_file,
    receipt_from_dict,
    require_git_commit,
    require_hash,
    require_identifier,
    sha256_bytes,
    strict_gzip_body,
    strict_json_load,
    validate_revision_chains,
)
from .schema import (
    expected_schema_fingerprint,
    initialize_schema,
    verify_exact_schema,
)


DEFAULT_RUNTIME_ROOT = Path.home() / ".deltagrid" / "market_data"
EXPECTED_LEGACY_COUNTS = {
    "mission86_ingestion_runs": 1,
    "mission86_raw_responses": 276,
    "mission86_market_bars": 262656,
    "mission86_funding_rates": 8208,
    "mission86_ingestion_checkpoints": 15,
    "mission86_stream_coverage": 15,
    "mission86_foundation_checks": 12,
    "mission86_dataset_manifests": 1,
    "mission87_certification_runs": 1,
    "mission87_series_certifications": 15,
    "mission87_quality_checks": 23,
    "mission87_dataset_certificates": 1,
}
EXPECTED_MANIFEST_FILE_HASH = (
    "c32ff8bc6db7627049deb42fa0fa2084c2fe6f5a7bac28bc01111b709dce03ae"
)
EXPECTED_CERTIFICATE_FILE_HASH = (
    "ca26ae9c380ad4bea641cd4e96eea2f50c5c0eb85cb1b11c995c5809a2fb007b"
)
LEGACY_CONTRACT_PATH = (
    REPOSITORY_ROOT
    / "offchain"
    / "research"
    / "contracts"
    / "mission85_funding_carry_charter_v1.json"
)

_RUNTIME_DIRS = (
    "objects",
    "objects/sha256",
    "releases",
    "staging",
    "incidents",
    "locks",
)


_CURRENT_SOURCE_ROLES = {"AUTONOMY_CONSTITUTION", "MISSION_99_CONTROL"}
_LEGACY_SOURCE_ROLES = _CURRENT_SOURCE_ROLES | {
    "MISSION_85_SOURCE_CONTRACT",
    "MISSION_86_SOURCE_MANIFEST",
    "MISSION_87_SOURCE_CERTIFICATE",
}


def _mission_bounds() -> Mapping[str, Any]:
    _autonomy, mission = load_contracts()
    return mission["resource_bounds"]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _reject_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ControlPlaneError("SYMLINK_REJECTED", str(current))


def validate_runtime_root(
    runtime_root: str | Path,
    *,
    repository_root: str | Path = REPOSITORY_ROOT,
    require_exists: bool = True,
) -> Path:
    """Validate an absolute non-symlink runtime root outside the checkout."""

    root = Path(runtime_root).expanduser()
    if not root.is_absolute():
        raise ControlPlaneError("RUNTIME_ROOT_NOT_ABSOLUTE")
    if ".." in root.parts:
        raise ControlPlaneError("PATH_TRAVERSAL_REJECTED")
    repo = Path(repository_root).resolve(strict=True)
    _reject_symlink_components(root)
    resolved = root.resolve(strict=False)
    if _is_relative_to(resolved, repo):
        raise ControlPlaneError("RUNTIME_ROOT_INSIDE_REPOSITORY")
    if require_exists:
        if not root.exists() or root.is_symlink() or not root.is_dir():
            raise ControlPlaneError("RUNTIME_ROOT_MISSING")
        return root.resolve(strict=True)
    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise ControlPlaneError("RUNTIME_ROOT_INVALID")
    return resolved


def _mkdir_new(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise ControlPlaneError("UNEXPECTED_EXISTING_PATH", str(path))
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    if stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise ControlPlaneError("RUNTIME_DIRECTORY_MODE_INVALID", str(path))


def _secure_open_flags(flags: int) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    return flags | nofollow


def _create_empty_secure_file(path: Path) -> None:
    _reject_symlink_components(path.parent)
    if path.exists() or path.is_symlink():
        raise ControlPlaneError("SILENT_REPLACEMENT_REJECTED", str(path))
    descriptor = os.open(
        path,
        _secure_open_flags(os.O_WRONLY | os.O_CREAT | os.O_EXCL),
        0o600,
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ControlPlaneError("RUNTIME_FILE_NOT_REGULAR", str(path))
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ControlPlaneError("RUNTIME_FILE_MODE_INVALID", str(path))


def _write_new(path: Path, raw: bytes) -> None:
    if type(raw) is not bytes:
        raise ControlPlaneError("FILE_BYTES_INVALID")
    _reject_symlink_components(path.parent)
    if path.exists() or path.is_symlink():
        raise ControlPlaneError("SILENT_REPLACEMENT_REJECTED", str(path))
    descriptor = os.open(
        path,
        _secure_open_flags(os.O_WRONLY | os.O_CREAT | os.O_EXCL),
        0o600,
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ControlPlaneError("RUNTIME_FILE_NOT_REGULAR", str(path))
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    info = path.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
        raise ControlPlaneError("RUNTIME_FILE_MODE_INVALID", str(path))


def _fsync_directory(path: Path) -> None:
    flags = _secure_open_flags(os.O_RDONLY) | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    except OSError as error:
        raise ControlPlaneError("DIRECTORY_FSYNC_FAILED", str(path)) from error
    finally:
        os.close(descriptor)


def _sqlite_uri(path: Path) -> str:
    return "file:" + quote(str(path.resolve(strict=True)), safe="/") + "?mode=ro"


def _open_sqlite(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    try:
        if readonly:
            conn = sqlite3.connect(_sqlite_uri(path), uri=True)
            conn.execute("PRAGMA query_only = ON")
        else:
            conn = sqlite3.connect(path)
            mode = str(conn.execute("PRAGMA journal_mode = DELETE").fetchone()[0]).upper()
            if mode != "DELETE":
                conn.close()
                raise ControlPlaneError("SQLITE_JOURNAL_MODE_UNSUPPORTED", mode)
            conn.execute("PRAGMA synchronous = FULL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except ControlPlaneError:
        raise
    except sqlite3.DatabaseError as error:
        raise ControlPlaneError("SQLITE_OPEN_FAILED", str(error)) from error


def _current_contract_identities() -> tuple[dict[str, str], ...]:
    autonomy, mission = load_contracts()
    return (
        {
            "contract_id": autonomy["contract_id"],
            "contract_hash_sha256": autonomy["contract_hash_sha256"],
            "role": "AUTONOMY_CONSTITUTION",
        },
        {
            "contract_id": mission["contract_id"],
            "contract_hash_sha256": mission["contract_hash_sha256"],
            "role": "MISSION_99_CONTROL",
        },
    )


def _normalize_source_contracts(
    values: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, str], ...]:
    result: dict[tuple[str, str, str], dict[str, str]] = {}
    role_identity: dict[str, tuple[str, str]] = {}
    id_hash: dict[str, str] = {}
    for value in values:
        if set(value) != {"contract_id", "contract_hash_sha256", "role"}:
            raise ControlPlaneError("SOURCE_CONTRACT_IDENTITIES_INVALID")
        contract_id = value["contract_id"]
        contract_hash = value["contract_hash_sha256"]
        role = value["role"]
        require_identifier(contract_id, "source_contract_id")
        require_hash(contract_hash, "source_contract_hash")
        require_identifier(role, "source_contract_role")
        identity = (contract_id, contract_hash)
        previous_role = role_identity.get(role)
        if previous_role is not None and previous_role != identity:
            raise ControlPlaneError("SOURCE_CONTRACT_ROLE_CONFLICT")
        previous_hash = id_hash.get(contract_id)
        if previous_hash is not None and previous_hash != contract_hash:
            raise ControlPlaneError("SOURCE_CONTRACT_ID_CONFLICT")
        role_identity[role] = identity
        id_hash[contract_id] = contract_hash
        key = (role, contract_id, contract_hash)
        result[key] = {
            "contract_id": contract_id,
            "contract_hash_sha256": contract_hash,
            "role": role,
        }
    return tuple(result[key] for key in sorted(result))


def _validate_source_contract_role_set(
    values: tuple[dict[str, str], ...],
    *,
    synthetic_fixture: bool,
) -> None:
    roles = {item["role"] for item in values}
    expected = _CURRENT_SOURCE_ROLES if synthetic_fixture else _LEGACY_SOURCE_ROLES
    if roles != expected or len(values) != len(expected):
        raise ControlPlaneError("SOURCE_CONTRACT_ROLE_SET_INVALID")


def _contained_child(root: Path, path: Path, *, must_exist: bool) -> Path:
    root = root.resolve(strict=True)
    _reject_symlink_components(path)
    resolved = path.resolve(strict=must_exist)
    if not _is_relative_to(resolved, root):
        raise ControlPlaneError("PATH_ESCAPE", str(path))
    return resolved


def _object_path(runtime_root: Path, object_hash: str) -> Path:
    require_hash(object_hash, "compressed_object_sha256")
    return runtime_root / "objects" / "sha256" / object_hash[:2] / f"{object_hash}.gz"


def _persist_object(runtime_root: Path, object_hash: str, raw: bytes) -> str:
    bounds = _mission_bounds()
    require_hash(object_hash, "compressed_object_sha256")
    if len(raw) > bounds["maximum_response_bytes"]:
        raise ControlPlaneError("RAW_OBJECT_SIZE_LIMIT")
    if sha256_bytes(raw) != object_hash:
        raise ControlPlaneError("RAW_OBJECT_HASH_MISMATCH")
    body = strict_gzip_body(
        raw,
        maximum_decompressed_bytes=bounds["maximum_decompressed_response_bytes"],
    )
    target = _object_path(runtime_root, object_hash)
    shard = target.parent
    if not shard.exists():
        _mkdir_new(shard)
        _fsync_directory(shard.parent)
    elif shard.is_symlink() or not shard.is_dir():
        raise ControlPlaneError("RAW_OBJECT_SHARD_INVALID")
    if stat.S_IMODE(shard.stat().st_mode) != 0o700 or shard.stat().st_uid != os.getuid():
        raise ControlPlaneError("RUNTIME_DIRECTORY_MODE_INVALID", str(shard))
    if target.exists():
        if target.is_symlink() or not target.is_file():
            raise ControlPlaneError("RAW_OBJECT_PATH_INVALID")
        if stat.S_IMODE(target.stat().st_mode) != 0o600 or target.stat().st_uid != os.getuid():
            raise ControlPlaneError("RUNTIME_FILE_MODE_INVALID", str(target))
        existing = read_bounded_regular_file(
            target,
            maximum_bytes=bounds["maximum_response_bytes"],
            size_reason="RAW_OBJECT_SIZE_LIMIT",
            invalid_reason="RAW_OBJECT_PATH_INVALID",
        )
        if existing != raw or sha256_bytes(existing) != object_hash:
            raise ControlPlaneError("RAW_OBJECT_CONFLICT")
        strict_gzip_body(
            existing,
            maximum_decompressed_bytes=bounds["maximum_decompressed_response_bytes"],
        )
        return sha256_bytes(body)
    _write_new(target, raw)
    _fsync_directory(shard)
    return sha256_bytes(body)


def _directory_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ControlPlaneError("SYMLINK_REJECTED", str(path))
        if path.is_file():
            total += path.stat().st_size
    return total


def _object_store_bytes(root: Path) -> int:
    bounds = _mission_bounds()
    total = _directory_bytes(root / "objects" / "sha256")
    if total > bounds["maximum_total_raw_object_bytes"]:
        raise ControlPlaneError("RAW_OBJECT_TOTAL_SIZE_LIMIT")
    return total


def _runtime_bytes(root: Path) -> int:
    bounds = _mission_bounds()
    total = _directory_bytes(root)
    if total > bounds["maximum_total_acceptance_runtime_bytes"]:
        raise ControlPlaneError("RUNTIME_BYTE_LIMIT")
    return total


def _validate_initial_filesystem(root: Path) -> None:
    devices = {root.stat().st_dev}
    for relative in _RUNTIME_DIRS:
        path = root / relative
        if path.exists():
            devices.add(path.stat().st_dev)
    if len(devices) != 1:
        raise ControlPlaneError("RUNTIME_FILESYSTEM_MISMATCH")
    for relative in ("releases", "staging", "objects", "incidents", "locks"):
        _fsync_directory(root / relative)


class PublicationLock:
    """Cooperative single-writer lock for the complete publication critical section."""

    def __init__(self, path: Path, timeout_seconds: float) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self._descriptor: int | None = None

    def __enter__(self) -> "PublicationLock":
        if self.path.is_symlink() or not self.path.is_file():
            raise ControlPlaneError("PUBLICATION_LOCK_INVALID")
        descriptor = os.open(self.path, _secure_open_flags(os.O_RDWR))
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            os.close(descriptor)
            raise ControlPlaneError("PUBLICATION_LOCK_INVALID")
        started = time.monotonic()
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._descriptor = descriptor
                return self
            except OSError as error:
                if error.errno not in {errno.EACCES, errno.EAGAIN}:
                    os.close(descriptor)
                    raise ControlPlaneError("PUBLICATION_LOCK_FAILED") from error
                if time.monotonic() - started >= self.timeout_seconds:
                    os.close(descriptor)
                    raise ControlPlaneError("PUBLICATION_LOCK_BUSY")
                time.sleep(0.02)

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._descriptor is not None:
            try:
                fcntl.flock(self._descriptor, fcntl.LOCK_UN)
            finally:
                os.close(self._descriptor)
                self._descriptor = None


class Catalogue:
    """Narrow certified-release catalogue. It is an index, not data authority."""

    def __init__(
        self,
        runtime_root: str | Path,
        *,
        repository_root: str | Path = REPOSITORY_ROOT,
    ) -> None:
        load_contracts()
        self.repository_root = Path(repository_root).resolve(strict=True)
        self.runtime_root = validate_runtime_root(
            runtime_root,
            repository_root=self.repository_root,
        )
        self.path = self.runtime_root / "catalogue.sqlite3"
        self.lock_path = self.runtime_root / "locks" / "publication.lock"
        self._verify_layout()
        self._verify()

    @classmethod
    def initialize(
        cls,
        runtime_root: str | Path,
        *,
        repository_root: str | Path = REPOSITORY_ROOT,
        acknowledgement: str | None = None,
    ) -> "Catalogue":
        load_contracts()
        if acknowledgement != "INITIALIZE_RUNTIME":
            raise ControlPlaneError("EXECUTION_ACKNOWLEDGEMENT_REQUIRED")
        root = validate_runtime_root(
            runtime_root,
            repository_root=repository_root,
            require_exists=False,
        )
        if root.exists():
            if any(root.iterdir()):
                raise ControlPlaneError("RUNTIME_ROOT_NOT_EMPTY")
            os.chmod(root, 0o700)
        else:
            root.mkdir(mode=0o700, parents=True, exist_ok=False)
            os.chmod(root, 0o700)
        for relative in _RUNTIME_DIRS:
            path = root / relative
            if not path.exists():
                path.mkdir(mode=0o700)
                os.chmod(path, 0o700)
        lock_path = root / "locks" / "publication.lock"
        _write_new(lock_path, b"")
        catalogue_path = root / "catalogue.sqlite3"
        if catalogue_path.exists():
            raise ControlPlaneError("CATALOGUE_ALREADY_EXISTS")
        _create_empty_secure_file(catalogue_path)
        conn = sqlite3.connect(catalogue_path)
        try:
            initialize_schema(conn, "catalogue")
            schema_fp = verify_exact_schema(conn, "catalogue")
            conn.executemany(
                "INSERT INTO catalogue_metadata (key, value) VALUES (?, ?)",
                (
                    ("schema_version", canonical_json("1.0")),
                    ("mission_contract_hash", canonical_json(MISSION_CONTRACT_HASH)),
                    ("autonomy_contract_hash", canonical_json(AUTONOMY_CONTRACT_HASH)),
                    ("schema_fingerprint", canonical_json(schema_fp)),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        os.chmod(catalogue_path, 0o600)
        with open(catalogue_path, "rb") as stream:
            os.fsync(stream.fileno())
        _fsync_directory(root)
        _validate_initial_filesystem(root)
        return cls(root, repository_root=repository_root)

    def _verify_layout(self) -> None:
        if self.runtime_root.stat().st_uid != os.getuid():
            raise ControlPlaneError("RUNTIME_OWNER_INVALID")
        if stat.S_IMODE(self.runtime_root.stat().st_mode) != 0o700:
            raise ControlPlaneError("RUNTIME_DIRECTORY_MODE_INVALID", str(self.runtime_root))
        for relative in _RUNTIME_DIRS:
            path = self.runtime_root / relative
            _reject_symlink_components(path)
            if path.is_symlink() or not path.is_dir():
                raise ControlPlaneError("RUNTIME_LAYOUT_INVALID", relative)
            if path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) != 0o700:
                raise ControlPlaneError("RUNTIME_DIRECTORY_MODE_INVALID", relative)
        if self.path.is_symlink() or not self.path.is_file():
            raise ControlPlaneError("CATALOGUE_MISSING")
        if self.lock_path.is_symlink() or not self.lock_path.is_file():
            raise ControlPlaneError("PUBLICATION_LOCK_INVALID")
        for path in (self.path, self.lock_path):
            if path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) != 0o600:
                raise ControlPlaneError("RUNTIME_FILE_MODE_INVALID", str(path))

    def _verify(self) -> None:
        load_contracts()
        self._verify_layout()
        conn = _open_sqlite(self.path, readonly=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ControlPlaneError("CATALOGUE_INTEGRITY_FAILED")
            fingerprint = verify_exact_schema(conn, "catalogue")
            rows = conn.execute(
                "SELECT key, value FROM catalogue_metadata ORDER BY key"
            ).fetchall()
        finally:
            conn.close()
        expected = {
            "schema_version": "1.0",
            "mission_contract_hash": MISSION_CONTRACT_HASH,
            "autonomy_contract_hash": AUTONOMY_CONTRACT_HASH,
            "schema_fingerprint": fingerprint,
        }
        metadata: dict[str, Any] = {}
        for key, value in rows:
            parsed = strict_json_load(value, maximum_bytes=4096)
            if canonical_json(parsed) != value:
                raise ControlPlaneError("CATALOGUE_METADATA_NONCANONICAL")
            metadata[key] = parsed
        if metadata != expected:
            raise ControlPlaneError("CATALOGUE_CONTRACT_MISMATCH")
        self._release_rows_metadata()
        self._incident_rows_metadata()

    def _release_rows_metadata(self) -> tuple[Mapping[str, Any], ...]:
        conn = _open_sqlite(self.path, readonly=True)
        try:
            rows = conn.execute(
                "SELECT release_id,relative_path,release_core_hash,certificate_core_hash,"
                "parent_release_id,synthetic_fixture,certified,release_kind,legacy_proof_hash "
                "FROM releases ORDER BY release_id"
            ).fetchall()
        finally:
            conn.close()
        result: list[Mapping[str, Any]] = []
        ids = {row[0] for row in rows}
        for row in rows:
            release_id = row[0]
            if type(release_id) is not str or not release_id.startswith("m99-"):
                raise ControlPlaneError("CATALOGUE_ROW_INVALID")
            require_hash(release_id[4:], "release_id")
            if row[1] != f"releases/{release_id}":
                raise ControlPlaneError("CATALOGUE_PATH_INVALID")
            require_hash(row[2], "release_core_hash")
            require_hash(row[3], "certificate_core_hash")
            parent = row[4]
            if parent is not None:
                if type(parent) is not str or not parent.startswith("m99-"):
                    raise ControlPlaneError("PARENT_LINEAGE_MISMATCH")
                require_hash(parent[4:], "parent_release_id")
                if parent not in ids or parent == release_id:
                    raise ControlPlaneError("PARENT_LINEAGE_MISMATCH")
            if type(row[5]) is not int or row[5] not in {0, 1}:
                raise ControlPlaneError("CATALOGUE_ROW_INVALID")
            if row[6] != 1 or row[7] != RELEASE_KIND:
                raise ControlPlaneError("CATALOGUE_ROW_INVALID")
            if row[8] is not None:
                require_hash(row[8], "legacy_proof_hash")
            if bool(row[5]) != (row[8] is None):
                raise ControlPlaneError("CATALOGUE_LINEAGE_CLASS_INVALID")
            result.append(
                deep_freeze(
                    {
                        "release_id": release_id,
                        "relative_path": row[1],
                        "release_core_hash": row[2],
                        "certificate_core_hash": row[3],
                        "parent_release_id": parent,
                        "synthetic_fixture": bool(row[5]),
                        "certified": True,
                        "release_kind": row[7],
                        "legacy_proof_hash": row[8],
                    }
                )
            )
        by_id = {item["release_id"]: item for item in result}
        for item in result:
            parent_id = item["parent_release_id"]
            if parent_id is not None:
                parent_item = by_id[parent_id]
                if parent_item["synthetic_fixture"] != item["synthetic_fixture"]:
                    raise ControlPlaneError("LINEAGE_CLASS_MIXING_REJECTED")
                if (
                    not item["synthetic_fixture"]
                    and parent_item["legacy_proof_hash"] != item["legacy_proof_hash"]
                ):
                    raise ControlPlaneError("PARENT_LEGACY_PROOF_CHANGED")
        for release_id in by_id:
            seen: set[str] = set()
            current: str | None = release_id
            while current is not None:
                if current in seen:
                    raise ControlPlaneError("PARENT_LINEAGE_CYCLE")
                seen.add(current)
                current = by_id[current]["parent_release_id"]
        return tuple(result)

    def _incident_rows_metadata(self) -> tuple[Mapping[str, Any], ...]:
        conn = _open_sqlite(self.path, readonly=True)
        try:
            rows = conn.execute(
                "SELECT incident_id,state,release_id,relative_path,evidence_hash "
                "FROM incidents ORDER BY incident_id"
            ).fetchall()
        finally:
            conn.close()
        result: list[Mapping[str, Any]] = []
        for incident_id, state, release_id, relative_path, evidence_hash in rows:
            if (
                type(incident_id) is not str
                or not incident_id.startswith("incident-")
            ):
                raise ControlPlaneError("CATALOGUE_INCIDENT_ROW_INVALID")
            require_hash(incident_id[len("incident-"):], "incident_id")
            if type(state) is not str or not state or len(state) > 128:
                raise ControlPlaneError("CATALOGUE_INCIDENT_ROW_INVALID")
            if release_id is not None:
                if type(release_id) is not str or not release_id.startswith("m99-"):
                    raise ControlPlaneError("CATALOGUE_INCIDENT_ROW_INVALID")
                require_hash(release_id[4:], "incident_release_id")
            if relative_path != f"incidents/{incident_id}.json":
                raise ControlPlaneError("CATALOGUE_INCIDENT_PATH_INVALID")
            require_hash(evidence_hash, "incident_evidence_hash")
            result.append(
                deep_freeze(
                    {
                        "incident_id": incident_id,
                        "state": state,
                        "release_id": release_id,
                        "relative_path": relative_path,
                        "evidence_hash": evidence_hash,
                    }
                )
            )
        return tuple(result)

    def publication_lock(self) -> PublicationLock:
        bounds = _mission_bounds()
        return PublicationLock(
            self.lock_path,
            float(bounds["maximum_publication_lock_wait_seconds"]),
        )

    def release(self, release_id: str) -> Mapping[str, Any]:
        load_contracts()
        self._verify()
        if type(release_id) is not str or not release_id.startswith("m99-"):
            raise ControlPlaneError("RELEASE_ID_INVALID")
        require_hash(release_id[4:], "release_id")
        row = next(
            (item for item in self._release_rows_metadata() if item["release_id"] == release_id),
            None,
        )
        if row is None:
            raise ControlPlaneError("RELEASE_NOT_CATALOGUED")
        directory = self.runtime_root / row["relative_path"]
        _contained_child(self.runtime_root, directory, must_exist=True)
        if directory.name != release_id or directory.parent.name != "releases":
            raise ControlPlaneError("CATALOGUE_PATH_INVALID")
        return row

    def list_releases(self) -> tuple[Mapping[str, Any], ...]:
        self._verify()
        return tuple(
            self.release(item["release_id"])
            for item in self._release_rows_metadata()
        )

    def _insert_release(
        self,
        *,
        release_id: str,
        release_core_hash: str,
        certificate_core_hash: str,
        parent_release_id: str | None,
        synthetic_fixture: bool,
        legacy_proof_hash: str | None,
    ) -> None:
        self._verify()
        bounds = _mission_bounds()
        conn = _open_sqlite(self.path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute("SELECT COUNT(*) FROM releases").fetchone()[0]
            if count >= bounds["maximum_acceptance_release_count"]:
                raise ControlPlaneError("RELEASE_COUNT_LIMIT")
            if parent_release_id is not None:
                parent = conn.execute(
                    "SELECT release_id FROM releases WHERE release_id = ?",
                    (parent_release_id,),
                ).fetchone()
                if parent is None:
                    raise ControlPlaneError("PARENT_RELEASE_NOT_CATALOGUED")
            conn.execute(
                "INSERT INTO releases (release_id, relative_path, release_core_hash, "
                "certificate_core_hash, parent_release_id, synthetic_fixture, certified, "
                "release_kind, legacy_proof_hash) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    release_id,
                    f"releases/{release_id}",
                    release_core_hash,
                    certificate_core_hash,
                    parent_release_id,
                    1 if synthetic_fixture else 0,
                    RELEASE_KIND,
                    legacy_proof_hash,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        with open(self.path, "rb") as stream:
            os.fsync(stream.fileno())
        _fsync_directory(self.runtime_root)


def _verify_catalogued_release_evidence(catalogue: Catalogue) -> None:
    """Fail closed before writes when any existing certified release is unavailable."""

    for item in catalogue._release_rows_metadata():
        path = catalogue.runtime_root / item["relative_path"]
        _contained_child(catalogue.runtime_root, path, must_exist=True)
        certificate = certify_release(path, runtime_root=catalogue.runtime_root)
        if (
            certificate.release_core_hash != item["release_core_hash"]
            or certificate.certificate_core_hash != item["certificate_core_hash"]
        ):
            raise ControlPlaneError("CATALOGUE_RELEASE_DISAGREEMENT")


def _quarantine_records(values: Iterable[Mapping[str, str]]) -> tuple[dict[str, str], ...]:
    result: dict[str, dict[str, str]] = {}
    for value in values:
        if set(value) != {"reason", "evidence_identity"}:
            raise ControlPlaneError("QUARANTINE_INVALID")
        reason = value["reason"]
        identity = value["evidence_identity"]
        if (
            type(reason) is not str
            or type(identity) is not str
            or not reason
            or not identity
            or len(reason.encode("utf-8")) > 256
            or len(identity.encode("utf-8")) > 1024
        ):
            raise ControlPlaneError("QUARANTINE_INVALID")
        core = {"reason": reason, "evidence_identity": identity}
        item = {"quarantine_hash": canonical_hash(core), **core}
        result[item["quarantine_hash"]] = item
    return tuple(result[key] for key in sorted(result))


def _coalesce_receipts(receipts: Iterable[Any]) -> tuple[Any, ...]:
    by_hash: dict[str, Any] = {}
    by_request: dict[str, str] = {}
    by_response: dict[str, str] = {}
    for receipt in receipts:
        if not isinstance(receipt, (AcquisitionReceipt, LegacyAcquisitionReceipt)):
            raise ControlPlaneError("RECEIPT_TYPE_INVALID")
        existing = by_hash.get(receipt.receipt_hash)
        if existing is not None:
            if existing.as_dict() != receipt.as_dict():
                raise ControlPlaneError("RECEIPT_HASH_COLLISION")
            continue
        previous = by_request.get(receipt.request_id)
        if previous is not None and previous != receipt.receipt_hash:
            raise ControlPlaneError("RECEIPT_ID_CONFLICT")
        previous = by_response.get(receipt.source_response_hash)
        if previous is not None and previous != receipt.receipt_hash:
            raise ControlPlaneError("SOURCE_RESPONSE_CONFLICT")
        by_request[receipt.request_id] = receipt.receipt_hash
        by_response[receipt.source_response_hash] = receipt.receipt_hash
        by_hash[receipt.receipt_hash] = receipt
    return tuple(by_hash[key] for key in sorted(by_hash))


def _validate_links(
    observations: tuple[ObservationVersion, ...],
    receipts: tuple[Any, ...],
    *,
    repository_commit: str,
    source_contracts: tuple[dict[str, str], ...],
    synthetic_fixture: bool,
) -> None:
    _validate_source_contract_role_set(
        source_contracts, synthetic_fixture=synthetic_fixture
    )
    by_role = {item["role"]: item for item in source_contracts}
    by_receipt = {receipt.receipt_hash: receipt for receipt in receipts}
    for observation in observations:
        receipt = by_receipt.get(observation.receipt_hash)
        if receipt is None:
            raise ControlPlaneError("OBSERVATION_RECEIPT_MISSING")
        if receipt.source_response_hash != observation.source_response_hash:
            raise ControlPlaneError("OBSERVATION_RESPONSE_LINK_MISMATCH")
        if receipt.http_status != 200:
            raise ControlPlaneError("OBSERVATION_SOURCE_HTTP_UNSUCCESSFUL")
        if isinstance(receipt, AcquisitionReceipt):
            if receipt.retry_budget_exhausted:
                raise ControlPlaneError("OBSERVATION_SOURCE_RETRY_EXHAUSTED")
            if receipt.repository_commit != repository_commit:
                raise ControlPlaneError("RECEIPT_REPOSITORY_IDENTITY_MISMATCH")
        else:
            source_contract = by_role.get("MISSION_85_SOURCE_CONTRACT")
            source_manifest = by_role.get("MISSION_86_SOURCE_MANIFEST")
            if source_contract is None or source_manifest is None:
                raise ControlPlaneError("LEGACY_RECEIPT_LINEAGE_MISSING")
            if (
                receipt.source_contract_id != source_contract["contract_id"]
                or receipt.source_contract_hash
                != source_contract["contract_hash_sha256"]
                or receipt.source_manifest_hash
                != source_manifest["contract_hash_sha256"]
                or source_manifest["contract_id"]
                != f"mission86-manifest:{receipt.source_run_label}"
            ):
                raise ControlPlaneError("LEGACY_RECEIPT_LINEAGE_MISMATCH")
        if observation.availability_class is AvailabilityClass.OBSERVED_LIVE:
            if not isinstance(receipt, AcquisitionReceipt):
                raise ControlPlaneError("OBSERVED_LIVE_REQUIRES_FORWARD_RECEIPT")
            if observation.available_at != receipt.received_at or observation.first_observed_at != receipt.received_at:
                raise ControlPlaneError("OBSERVED_LIVE_RECEIPT_TIME_MISMATCH")
            if receipt.clock_health is not ClockHealth.HEALTHY:
                raise ControlPlaneError("CLOCK_HEALTH_UNTRUSTWORTHY")
        if isinstance(receipt, LegacyAcquisitionReceipt) and observation.availability_class is not AvailabilityClass.UNKNOWN:
            raise ControlPlaneError("LEGACY_AVAILABILITY_MUST_BE_UNKNOWN")


def _set_inventory(values: list[str]) -> dict[str, Any]:
    unique = sorted(set(values))
    return {"count": len(unique), "set_hash": canonical_hash(unique)}


def _builder_semantic_core(
    *,
    observations: tuple[ObservationVersion, ...],
    receipts: tuple[Any, ...],
    warnings: tuple[str, ...],
    quarantine: tuple[dict[str, str], ...],
    parent_release_id: str | None,
    parent_release_core_hash: str | None,
    synthetic_fixture: bool,
    repository_commit: str,
    legacy_proof_hash: str | None,
    legacy_audit_proof: Mapping[str, Any] | None,
    source_contract_identities: tuple[dict[str, str], ...],
) -> dict[str, Any]:
    logical_ids = {item.logical_id for item in observations}
    revisioned = {item.logical_id for item in observations if item.revision_number > 0}
    revision_rows = [
        {
            "logical_id": item.logical_id,
            "revision_number": item.revision_number,
            "record_hash": item.record_hash,
            "supersedes_record_hash": item.supersedes_record_hash,
        }
        for item in observations
    ]
    object_hashes = [item.compressed_object_sha256 for item in receipts]
    return {
        "schema_version": "1.0",
        "release_kind": RELEASE_KIND,
        "synthetic_fixture": synthetic_fixture,
        "parent_release_id": parent_release_id,
        "parent_release_core_hash": parent_release_core_hash,
        "source_contract_identities": [dict(item) for item in source_contract_identities],
        "inventory": {
            "providers": sorted({item.provider for item in observations}),
            "streams": sorted({item.stream for item in observations}),
            "symbols": sorted({item.symbol for item in observations}),
            "intervals": sorted({item.interval for item in observations if item.interval is not None}),
        },
        "temporal_coverage": {
            "minimum_event_time": min((item.event_time for item in observations), default=None),
            "maximum_event_time": max((item.event_time for item in observations), default=None),
            "minimum_first_observed_at": min((item.first_observed_at for item in observations), default=None),
            "maximum_first_observed_at": max((item.first_observed_at for item in observations), default=None),
        },
        "raw_response_identities": _set_inventory([item.source_response_hash for item in receipts]),
        "raw_object_identities": _set_inventory(object_hashes),
        "acquisition_receipt_identities": _set_inventory([item.receipt_hash for item in receipts]),
        "normalized_semantic_identities": _set_inventory([item.record_hash for item in observations]),
        "availability_policy": {
            "classes": sorted({item.availability_class.value for item in observations}),
            "policy_ids": sorted({item.availability_policy_id for item in observations}),
        },
        "revision_inventory": {
            "logical_observation_count": len(logical_ids),
            "revisioned_logical_observation_count": len(revisioned),
            "maximum_revision_number": max((item.revision_number for item in observations), default=0),
            "chain_hash": canonical_hash(revision_rows),
        },
        "quarantine_inventory": {
            "count": len(quarantine),
            "set_hash": canonical_hash(list(quarantine)),
        },
        "protected_boundary": dict(PROTECTED_BOUNDARY),
        "counts": {
            "observation_rows": len(observations),
            "receipts": len(receipts),
            "raw_object_references": len(receipts),
            "warnings": len(warnings),
            "quarantine": len(quarantine),
        },
        "warnings": list(warnings),
        "repository_identity": repository_commit,
        "normalizer_identity": sorted({item.normalizer_id for item in observations}),
        "legacy_proof_hash": legacy_proof_hash,
        "legacy_audit_proof": deep_thaw(legacy_audit_proof),
        "release_schema_fingerprint": expected_schema_fingerprint("release"),
    }


def _write_release_database(
    path: Path,
    *,
    observations: tuple[ObservationVersion, ...],
    receipts: tuple[Any, ...],
    warnings: tuple[str, ...],
    quarantine: tuple[dict[str, str], ...],
    parent_release_id: str | None,
    parent_release_core_hash: str | None,
    synthetic_fixture: bool,
    repository_commit: str,
    legacy_proof_hash: str | None,
    legacy_audit_proof: Mapping[str, Any] | None,
    source_contract_identities: tuple[dict[str, str], ...],
) -> None:
    if path.exists():
        raise ControlPlaneError("SILENT_REPLACEMENT_REJECTED")
    _create_empty_secure_file(path)
    conn = sqlite3.connect(path)
    try:
        initialize_schema(conn, "release")
        verify_exact_schema(conn, "release")
        metadata = {
            "schema_version": "1.0",
            "release_kind": RELEASE_KIND,
            "synthetic_fixture": synthetic_fixture,
            "parent_release_id": parent_release_id,
            "parent_release_core_hash": parent_release_core_hash,
            "repository_commit": repository_commit,
            "legacy_proof_hash": legacy_proof_hash,
            "legacy_audit_proof": deep_thaw(legacy_audit_proof),
            "source_contract_identities": [dict(item) for item in source_contract_identities],
            "protected_boundary": dict(PROTECTED_BOUNDARY),
        }
        conn.executemany(
            "INSERT INTO release_metadata (key, value) VALUES (?, ?)",
            [(key, canonical_json(value)) for key, value in sorted(metadata.items())],
        )
        conn.executemany(
            "INSERT INTO acquisition_receipts "
            "(receipt_hash, request_id, receipt_kind, source_response_hash, body_sha256, "
            "compressed_object_sha256, receipt_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    receipt.receipt_hash,
                    receipt.request_id,
                    receipt.receipt_kind.value,
                    receipt.source_response_hash,
                    receipt.body_sha256,
                    receipt.compressed_object_sha256,
                    canonical_json(receipt.as_dict()),
                )
                for receipt in receipts
            ],
        )
        conn.executemany(
            "INSERT INTO raw_object_refs "
            "(receipt_hash, compressed_object_sha256, body_sha256, source_response_hash) "
            "VALUES (?, ?, ?, ?)",
            [
                (
                    receipt.receipt_hash,
                    receipt.compressed_object_sha256,
                    receipt.body_sha256,
                    receipt.source_response_hash,
                )
                for receipt in receipts
            ],
        )
        conn.executemany(
            "INSERT INTO observations "
            "(record_hash, logical_id, provider, stream, symbol, interval, event_time, source_time, "
            "available_at, availability_class, availability_policy_id, first_observed_at, "
            "last_verified_at, revision_number, supersedes_record_hash, source_response_hash, "
            "receipt_hash, normalizer_id, normalized_payload_json, clock_health) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    item.record_hash,
                    item.logical_id,
                    item.provider,
                    item.stream,
                    item.symbol,
                    item.interval,
                    item.event_time,
                    item.source_time,
                    item.available_at,
                    item.availability_class.value,
                    item.availability_policy_id,
                    item.first_observed_at,
                    item.last_verified_at,
                    item.revision_number,
                    item.supersedes_record_hash,
                    item.source_response_hash,
                    item.receipt_hash,
                    item.normalizer_id,
                    canonical_json(item.normalized_payload),
                    item.clock_health.value,
                )
                for item in observations
            ],
        )
        conn.executemany(
            "INSERT INTO warnings (warning) VALUES (?)",
            [(item,) for item in warnings],
        )
        conn.executemany(
            "INSERT INTO quarantine (quarantine_hash, reason, evidence_identity) VALUES (?, ?, ?)",
            [
                (item["quarantine_hash"], item["reason"], item["evidence_identity"])
                for item in quarantine
            ],
        )
        conn.commit()
    finally:
        conn.close()
    os.chmod(path, 0o600)
    bounds = _mission_bounds()
    if path.stat().st_size > bounds["maximum_release_sqlite_bytes"]:
        raise ControlPlaneError("RELEASE_SQLITE_SIZE_LIMIT")
    with open(path, "rb") as stream:
        os.fsync(stream.fileno())


def _write_manifest(
    path: Path,
    *,
    semantic_core: Mapping[str, Any],
    database_path: Path,
) -> dict[str, Any]:
    bounds = _mission_bounds()
    core_hash = canonical_hash(semantic_core)
    release_id = f"m99-{core_hash}"
    manifest_core = {
        "schema_version": "1.0",
        "release_id": release_id,
        "release_core_hash": core_hash,
        "release_semantic_core": deep_thaw(semantic_core),
        "physical_files": {
            "release.sqlite3": sha256_bytes(
                read_bounded_regular_file(
                    database_path,
                    maximum_bytes=bounds["maximum_release_sqlite_bytes"],
                    size_reason="RELEASE_SQLITE_SIZE_LIMIT",
                    invalid_reason="RELEASE_SQLITE_INVALID",
                )
            ),
        },
    }
    document = {
        "manifest_core": manifest_core,
        "manifest_core_hash": canonical_hash(manifest_core),
    }
    _write_new(path, (canonical_json(document) + "\n").encode("utf-8"))
    return document


def _merge_parent_snapshot(
    catalogue: Catalogue,
    parent_release_id: str | None,
    observations: tuple[ObservationVersion, ...],
    receipts: tuple[Any, ...],
    warnings: tuple[str, ...],
    quarantine: tuple[dict[str, str], ...],
    *,
    synthetic_fixture: bool,
) -> tuple[
    tuple[ObservationVersion, ...],
    tuple[Any, ...],
    tuple[str, ...],
    tuple[dict[str, str], ...],
    str | None,
    tuple[dict[str, str], ...],
]:
    if parent_release_id is None:
        return (
            validate_revision_chains(observations),
            _coalesce_receipts(receipts),
            tuple(sorted(set(warnings))),
            quarantine,
            None,
            _current_contract_identities(),
        )
    parent_record = catalogue.release(parent_release_id)
    if bool(parent_record["synthetic_fixture"]) != synthetic_fixture:
        raise ControlPlaneError("LINEAGE_CLASS_MIXING_REJECTED")
    parent_dir = catalogue.runtime_root / parent_record["relative_path"]
    parent = load_certified_snapshot(parent_dir, runtime_root=catalogue.runtime_root)
    parent_certificate = parent["certificate"]
    if (
        parent_certificate.release_core_hash != parent_record["release_core_hash"]
        or parent_certificate.certificate_core_hash
        != parent_record["certificate_core_hash"]
    ):
        raise ControlPlaneError("CATALOGUE_RELEASE_DISAGREEMENT")
    parent_core = parent["semantic_core"]
    merged_observations = validate_revision_chains(
        tuple(parent["observations"]) + observations
    )
    merged_receipts = _coalesce_receipts(tuple(parent["receipts"]) + receipts)
    merged_warnings = tuple(sorted(set(parent["warnings"]) | set(warnings)))
    quarantine_by_hash = {
        item["quarantine_hash"]: dict(item) for item in parent["quarantine"]
    }
    for item in quarantine:
        quarantine_by_hash[item["quarantine_hash"]] = dict(item)
    merged_quarantine = tuple(
        quarantine_by_hash[key] for key in sorted(quarantine_by_hash)
    )
    source_contracts = _normalize_source_contracts(
        parent_core["source_contract_identities"]
    )
    return (
        merged_observations,
        merged_receipts,
        merged_warnings,
        merged_quarantine,
        parent_record["release_core_hash"],
        source_contracts,
    )


def _record_incident(
    catalogue: Catalogue,
    *,
    state: str,
    release_id: str | None,
    stage: str,
    reason: str,
) -> None:
    core = {
        "state": state,
        "release_id": release_id,
        "stage": stage,
        "reason": reason,
    }
    incident_id = f"incident-{canonical_hash(core)}"
    relative = f"incidents/{incident_id}.json"
    path = catalogue.runtime_root / relative
    document = {"incident_id": incident_id, **core}
    raw = (canonical_json(document) + "\n").encode("utf-8")
    if path.exists():
        existing_incident = read_bounded_regular_file(
            path,
            maximum_bytes=256 * 1024,
            size_reason="INCIDENT_EVIDENCE_SIZE_LIMIT",
            invalid_reason="INCIDENT_EVIDENCE_INVALID",
        )
        if existing_incident != raw:
            raise ControlPlaneError("INCIDENT_EVIDENCE_CONFLICT")
    else:
        _write_new(path, raw)
        _fsync_directory(path.parent)
    try:
        conn = _open_sqlite(catalogue.path)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO incidents "
            "(incident_id, state, release_id, relative_path, evidence_hash) "
            "VALUES (?, ?, ?, ?, ?)",
            (incident_id, state, release_id, relative, sha256_bytes(raw)),
        )
        conn.commit()
    except Exception:
        if "conn" in locals():
            conn.rollback()
    finally:
        if "conn" in locals():
            conn.close()


class _Publisher:
    """Internal publisher. Public API exposes only the synthetic wrapper."""

    def __init__(
        self,
        catalogue: Catalogue,
        *,
        failpoint: str | None = None,
        boundary: Callable[[str], None] | None = None,
    ) -> None:
        self.catalogue = catalogue
        self.failpoint = failpoint
        self.boundary = boundary

    def _boundary(self, name: str) -> None:
        if self.boundary is not None:
            self.boundary(name)
        if self.failpoint == name:
            raise ControlPlaneError("INJECTED_PUBLICATION_FAILURE", name)

    def publish(
        self,
        *,
        observations: Iterable[ObservationVersion],
        receipts: Iterable[Any],
        raw_objects: Mapping[str, bytes],
        parent_release_id: str | None,
        repository_commit: str,
        synthetic_fixture: bool,
        warnings: Iterable[str],
        quarantine: Iterable[Mapping[str, str]],
        legacy_proof_hash: str | None,
        legacy_audit_proof: Mapping[str, Any] | None = None,
        source_contract_identities: tuple[dict[str, str], ...] | None = None,
    ) -> Mapping[str, Any]:
        require_git_commit(repository_commit, "repository_commit")
        load_contracts()
        bounds = _mission_bounds()
        base_observations = tuple(observations)
        base_receipts = tuple(receipts)
        quarantine_records = _quarantine_records(quarantine)
        warning_records = tuple(sorted(set(warnings)))
        for warning in warning_records:
            if type(warning) is not str or not warning or len(warning) > 256:
                raise ControlPlaneError("WARNING_INVALID")
        if len(warning_records) > bounds["maximum_warning_count"]:
            raise ControlPlaneError("WARNING_COUNT_LIMIT")
        if len(quarantine_records) > bounds["maximum_quarantine_count"]:
            raise ControlPlaneError("QUARANTINE_COUNT_LIMIT")
        if synthetic_fixture:
            if legacy_proof_hash is not None or legacy_audit_proof is not None:
                raise ControlPlaneError("SYNTHETIC_LEGACY_PROOF_INVALID")
        else:
            if (
                legacy_proof_hash is None
                or not isinstance(legacy_audit_proof, Mapping)
                or canonical_hash(legacy_audit_proof) != legacy_proof_hash
            ):
                raise ControlPlaneError("REAL_RELEASE_LEGACY_PROOF_MISSING")
        stage: Path | None = None
        release_id: str | None = None
        stage_name = "before_lock"
        with self.catalogue.publication_lock():
            try:
                stage_name = "contracts_and_catalogue"
                self._boundary(stage_name)
                load_contracts()
                self.catalogue._verify()
                _verify_catalogued_release_evidence(self.catalogue)
                stage_name = "normalize_inputs"
                self._boundary(stage_name)
                (
                    merged_observations,
                    merged_receipts,
                    merged_warnings,
                    merged_quarantine,
                    parent_core_hash,
                    inherited_source_contracts,
                ) = _merge_parent_snapshot(
                    self.catalogue,
                    parent_release_id,
                    base_observations,
                    base_receipts,
                    warning_records,
                    quarantine_records,
                    synthetic_fixture=synthetic_fixture,
                )
                if synthetic_fixture and source_contract_identities is not None:
                    raise ControlPlaneError("SYNTHETIC_SOURCE_CONTRACT_OVERRIDE_REJECTED")
                if not synthetic_fixture and (
                    source_contract_identities is None or legacy_proof_hash is None
                ):
                    raise ControlPlaneError("REAL_RELEASE_LINEAGE_REQUIRED")
                if source_contract_identities is None:
                    source_contracts = _normalize_source_contracts(
                        inherited_source_contracts
                    )
                else:
                    source_contracts = _normalize_source_contracts(
                        tuple(inherited_source_contracts)
                        + tuple(source_contract_identities)
                    )
                _validate_source_contract_role_set(
                    source_contracts,
                    synthetic_fixture=synthetic_fixture,
                )
                if len(merged_warnings) > bounds["maximum_warning_count"]:
                    raise ControlPlaneError("WARNING_COUNT_LIMIT")
                if len(merged_quarantine) > bounds["maximum_quarantine_count"]:
                    raise ControlPlaneError("QUARANTINE_COUNT_LIMIT")
                _validate_links(
                    merged_observations,
                    merged_receipts,
                    repository_commit=repository_commit,
                    source_contracts=source_contracts,
                    synthetic_fixture=synthetic_fixture,
                )
                if len(merged_observations) > bounds["maximum_release_rows"]:
                    raise ControlPlaneError("RELEASE_ROW_LIMIT")
                if len(merged_receipts) > bounds["maximum_receipts"]:
                    raise ControlPlaneError("RECEIPT_LIMIT")
                receipt_by_object: dict[str, list[Any]] = {}
                for receipt in merged_receipts:
                    receipt_by_object.setdefault(
                        receipt.compressed_object_sha256, []
                    ).append(receipt)
                base_object_hashes = {
                    receipt.compressed_object_sha256 for receipt in base_receipts
                }
                if any(type(key) is not str for key in raw_objects):
                    raise ControlPlaneError("RAW_OBJECT_INPUT_INVALID")
                unexpected_objects = set(raw_objects) - base_object_hashes
                if unexpected_objects:
                    raise ControlPlaneError("UNREFERENCED_RAW_OBJECT_INPUT")
                for object_hash in base_object_hashes:
                    require_hash(object_hash, "compressed_object_sha256")
                    if object_hash not in raw_objects:
                        existing_path = _object_path(
                            self.catalogue.runtime_root, object_hash
                        )
                        if not existing_path.is_file() or existing_path.is_symlink():
                            raise ControlPlaneError("RAW_OBJECT_BYTES_REQUIRED")
                stage_name = "persist_raw_objects"
                self._boundary(stage_name)
                current_object_bytes = _object_store_bytes(self.catalogue.runtime_root)
                additional_object_bytes = 0
                for object_hash, raw in raw_objects.items():
                    require_hash(object_hash, "compressed_object_sha256")
                    if type(raw) is not bytes:
                        raise ControlPlaneError("RAW_OBJECT_INPUT_INVALID")
                    target = _object_path(self.catalogue.runtime_root, object_hash)
                    if not target.exists():
                        additional_object_bytes += len(raw)
                if (
                    current_object_bytes + additional_object_bytes
                    > bounds["maximum_total_raw_object_bytes"]
                ):
                    raise ControlPlaneError("RAW_OBJECT_TOTAL_SIZE_LIMIT")
                for object_hash, raw in sorted(raw_objects.items()):
                    body_hash = _persist_object(self.catalogue.runtime_root, object_hash, raw)
                    for receipt in receipt_by_object.get(object_hash, []):
                        if receipt.body_sha256 != body_hash:
                            raise ControlPlaneError("RAW_BODY_HASH_MISMATCH")
                for object_hash, bound_receipts in receipt_by_object.items():
                    path = _object_path(self.catalogue.runtime_root, object_hash)
                    if not path.is_file() or path.is_symlink():
                        raise ControlPlaneError("RAW_OBJECT_MISSING")
                    raw = read_bounded_regular_file(
                        path,
                        maximum_bytes=bounds["maximum_response_bytes"],
                        size_reason="RAW_OBJECT_SIZE_LIMIT",
                        invalid_reason="RAW_OBJECT_PATH_INVALID",
                    )
                    if sha256_bytes(raw) != object_hash:
                        raise ControlPlaneError("RAW_OBJECT_HASH_MISMATCH")
                    body_hash = sha256_bytes(
                        strict_gzip_body(
                            raw,
                            maximum_decompressed_bytes=bounds["maximum_decompressed_response_bytes"],
                        )
                    )
                    if any(receipt.body_sha256 != body_hash for receipt in bound_receipts):
                        raise ControlPlaneError("RAW_BODY_HASH_MISMATCH")
                _object_store_bytes(self.catalogue.runtime_root)
                semantic_core = _builder_semantic_core(
                    observations=merged_observations,
                    receipts=merged_receipts,
                    warnings=merged_warnings,
                    quarantine=merged_quarantine,
                    parent_release_id=parent_release_id,
                    parent_release_core_hash=parent_core_hash,
                    synthetic_fixture=synthetic_fixture,
                    repository_commit=repository_commit,
                    legacy_proof_hash=legacy_proof_hash,
                    legacy_audit_proof=legacy_audit_proof,
                    source_contract_identities=source_contracts,
                )
                release_core_hash = canonical_hash(semantic_core)
                release_id = f"m99-{release_core_hash}"
                staging_identity = canonical_hash(
                    {
                        "release_core_hash": release_core_hash,
                        "receipts": [item.receipt_hash for item in merged_receipts],
                        "warnings": list(merged_warnings),
                        "quarantine": list(merged_quarantine),
                        "parent_release_id": parent_release_id,
                    }
                )
                final_dir = self.catalogue.runtime_root / "releases" / release_id
                if final_dir.exists():
                    try:
                        existing = self.catalogue.release(release_id)
                    except ControlPlaneError as error:
                        if error.reason == "RELEASE_NOT_CATALOGUED":
                            raise ControlPlaneError(
                                "ORPHAN_RELEASE_REQUIRES_RECOVERY"
                            ) from error
                        raise
                    certificate = certify_release(
                        final_dir,
                        runtime_root=self.catalogue.runtime_root,
                    )
                    if (
                        existing["release_core_hash"] != certificate.release_core_hash
                        or existing["certificate_core_hash"]
                        != certificate.certificate_core_hash
                    ):
                        raise ControlPlaneError("RELEASE_ID_COLLISION")
                    return deep_freeze(dict(existing))
                if (
                    len(self.catalogue.list_releases())
                    >= bounds["maximum_acceptance_release_count"]
                ):
                    raise ControlPlaneError("RELEASE_COUNT_LIMIT")
                stage = (
                    self.catalogue.runtime_root
                    / "staging"
                    / f"stage-{staging_identity[:24]}-{os.getpid()}-{time.time_ns()}"
                )
                _mkdir_new(stage)
                _fsync_directory(stage.parent)
                stage_name = "write_release_database"
                self._boundary(stage_name)
                database_path = stage / "release.sqlite3"
                _write_release_database(
                    database_path,
                    observations=merged_observations,
                    receipts=merged_receipts,
                    warnings=merged_warnings,
                    quarantine=merged_quarantine,
                    parent_release_id=parent_release_id,
                    parent_release_core_hash=parent_core_hash,
                    synthetic_fixture=synthetic_fixture,
                    repository_commit=repository_commit,
                    legacy_proof_hash=legacy_proof_hash,
                    legacy_audit_proof=legacy_audit_proof,
                    source_contract_identities=source_contracts,
                )
                stage_name = "write_manifest"
                self._boundary(stage_name)
                manifest = _write_manifest(
                    stage / "manifest.json",
                    semantic_core=semantic_core,
                    database_path=database_path,
                )
                stage_name = "staged_verification"
                self._boundary(stage_name)
                certificate_document = staged_certificate_document(
                    stage,
                    runtime_root=self.catalogue.runtime_root,
                )
                stage_name = "write_certificate"
                self._boundary(stage_name)
                _write_new(
                    stage / "certificate.json",
                    (canonical_json(certificate_document) + "\n").encode("utf-8"),
                )
                stage_entries = list(stage.iterdir())
                if (
                    len(stage_entries) != 3
                    or len(stage_entries) > bounds["maximum_release_files"]
                    or {item.name for item in stage_entries}
                    != {"release.sqlite3", "manifest.json", "certificate.json"}
                ):
                    raise ControlPlaneError("RELEASE_FILE_COUNT_LIMIT")
                if _directory_bytes(stage) > bounds["maximum_staging_bytes"]:
                    raise ControlPlaneError("STAGING_BYTE_LIMIT")
                _runtime_bytes(self.catalogue.runtime_root)
                _fsync_directory(stage)
                stage_name = "verify_staged_complete"
                self._boundary(stage_name)
                staged_certificate = verify_completed_stage(
                    stage,
                    runtime_root=self.catalogue.runtime_root,
                )
                if staged_certificate.release_id != release_id:
                    raise ControlPlaneError("STAGED_RELEASE_ID_MISMATCH")
                if final_dir.exists():
                    raise ControlPlaneError("RELEASE_DESTINATION_EXISTS")
                stage_name = "before_atomic_rename"
                self._boundary(stage_name)
                if final_dir.exists():
                    raise ControlPlaneError("RELEASE_DESTINATION_EXISTS")
                os.rename(stage, final_dir)
                stage = None
                _fsync_directory(final_dir.parent)
                stage_name = "after_atomic_rename"
                self._boundary(stage_name)
                final_certificate = certify_release(
                    final_dir,
                    runtime_root=self.catalogue.runtime_root,
                )
                _runtime_bytes(self.catalogue.runtime_root)
                stage_name = "before_catalogue_commit"
                self._boundary(stage_name)
                self.catalogue._insert_release(
                    release_id=release_id,
                    release_core_hash=final_certificate.release_core_hash,
                    certificate_core_hash=final_certificate.certificate_core_hash,
                    parent_release_id=parent_release_id,
                    synthetic_fixture=synthetic_fixture,
                    legacy_proof_hash=legacy_proof_hash,
                )
                stage_name = "after_catalogue_commit"
                self._boundary(stage_name)
                registered = self.catalogue.release(release_id)
                if (
                    registered["release_core_hash"] != final_certificate.release_core_hash
                    or registered["certificate_core_hash"] != final_certificate.certificate_core_hash
                ):
                    raise ControlPlaneError("CATALOGUE_RELEASE_DISAGREEMENT")
                return deep_freeze(
                    {
                        "release_id": release_id,
                        "release_core_hash": final_certificate.release_core_hash,
                        "certificate_core_hash": final_certificate.certificate_core_hash,
                        "manifest_core_hash": manifest["manifest_core_hash"],
                        "relative_path": f"releases/{release_id}",
                        "certified": True,
                        "synthetic_fixture": synthetic_fixture,
                    }
                )
            except Exception as error:
                reason = error.reason if isinstance(error, ControlPlaneError) else "PUBLICATION_INTERNAL_FAILURE"
                state = "PUBLICATION_FAILED"
                try:
                    _record_incident(
                        self.catalogue,
                        state=state,
                        release_id=release_id,
                        stage=stage_name,
                        reason=reason,
                    )
                except Exception as incident_error:
                    incident_reason = (
                        incident_error.reason
                        if isinstance(incident_error, ControlPlaneError)
                        else "INCIDENT_INTERNAL_FAILURE"
                    )
                    raise ControlPlaneError(
                        "INCIDENT_RECORD_FAILED",
                        f"original={reason}; incident={incident_reason}",
                    ) from error
                raise


def publish_synthetic_release(
    *,
    catalogue: Catalogue,
    observations: Iterable[ObservationVersion],
    receipts: Iterable[AcquisitionReceipt],
    raw_objects: Mapping[str, bytes],
    repository_commit: str,
    parent_release_id: str | None = None,
    warnings: Iterable[str] = (),
    quarantine: Iterable[Mapping[str, str]] = (),
) -> Mapping[str, Any]:
    """Publish only synthetic fixture evidence. There is no general real-data path."""

    receipt_items = tuple(receipts)
    if any(not isinstance(item, AcquisitionReceipt) for item in receipt_items):
        raise ControlPlaneError("SYNTHETIC_RECEIPT_KIND_INVALID")
    return _Publisher(catalogue).publish(
        observations=observations,
        receipts=receipt_items,
        raw_objects=raw_objects,
        parent_release_id=parent_release_id,
        repository_commit=repository_commit,
        synthetic_fixture=True,
        warnings=warnings,
        quarantine=quarantine,
        legacy_proof_hash=None,
        legacy_audit_proof=None,
    )


@dataclass(frozen=True)
class VerifiedLegacyAudit:
    verdict: str
    database_integrity: str
    table_counts: Mapping[str, int]
    mission86_file_count: int
    mission86_raw_gzip_count: int
    mission87_file_count: int
    manifest_file_sha256: str
    certificate_file_sha256: str
    manifest_core_hash: str
    certificate_core_hash: str
    source_run_label: str
    source_contract_id: str
    source_contract_hash: str
    certification_run_label: str
    response_evidence_hash: str
    series_identity_hash: str
    source_contract_identities: tuple[Mapping[str, str], ...]
    symlink_count: int
    proof_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_counts", deep_freeze(self.table_counts))
        object.__setattr__(
            self,
            "source_contract_identities",
            tuple(deep_freeze(item) for item in self.source_contract_identities),
        )
        core = self._proof_core()
        computed = canonical_hash(core)
        if self.proof_hash:
            require_hash(self.proof_hash, "legacy_proof_hash")
            if self.proof_hash != computed:
                raise ControlPlaneError("LEGACY_PROOF_HASH_MISMATCH")
        else:
            object.__setattr__(self, "proof_hash", computed)

    def _proof_core(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "database_integrity": self.database_integrity,
            "table_counts": deep_thaw(self.table_counts),
            "mission86_file_count": self.mission86_file_count,
            "mission86_raw_gzip_count": self.mission86_raw_gzip_count,
            "mission87_file_count": self.mission87_file_count,
            "manifest_file_sha256": self.manifest_file_sha256,
            "certificate_file_sha256": self.certificate_file_sha256,
            "manifest_core_hash": self.manifest_core_hash,
            "certificate_core_hash": self.certificate_core_hash,
            "source_run_label": self.source_run_label,
            "source_contract_id": self.source_contract_id,
            "source_contract_hash": self.source_contract_hash,
            "certification_run_label": self.certification_run_label,
            "response_evidence_hash": self.response_evidence_hash,
            "series_identity_hash": self.series_identity_hash,
            "source_contract_identities": [deep_thaw(item) for item in self.source_contract_identities],
            "symlink_count": self.symlink_count,
        }

    def proof_core(self) -> Mapping[str, Any]:
        """Return an immutable metadata-only proof core for release custody."""

        return deep_freeze(self._proof_core())

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "database_integrity": self.database_integrity,
            "table_counts": deep_thaw(self.table_counts),
            "mission86_file_count": self.mission86_file_count,
            "mission86_raw_gzip_count": self.mission86_raw_gzip_count,
            "mission87_file_count": self.mission87_file_count,
            "manifest_file_sha256": self.manifest_file_sha256,
            "certificate_file_sha256": self.certificate_file_sha256,
            "manifest_core_hash": self.manifest_core_hash,
            "certificate_core_hash": self.certificate_core_hash,
            "source_run_label": self.source_run_label,
            "source_contract_id": self.source_contract_id,
            "source_contract_hash": self.source_contract_hash,
            "certification_run_label": self.certification_run_label,
            "response_evidence_hash": self.response_evidence_hash,
            "series_identity_hash": self.series_identity_hash,
            "symlink_count": self.symlink_count,
            "proof_hash": self.proof_hash,
            "protected_values_printed": False,
        }


def _walk_metadata(root: Path) -> tuple[int, int, int]:
    file_count = 0
    gzip_count = 0
    symlink_count = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            symlink_count += 1
            continue
        if path.is_file():
            file_count += 1
            if path.suffix == ".gz":
                gzip_count += 1
    return file_count, gzip_count, symlink_count


def _load_legacy_contract_identity() -> tuple[str, str]:
    document = strict_json_load(LEGACY_CONTRACT_PATH, maximum_bytes=512 * 1024)
    if not isinstance(document, dict):
        raise ControlPlaneError("LEGACY_SOURCE_CONTRACT_INVALID")
    if isinstance(document.get("contract"), dict):
        core = document["contract"]
        stored_hash = document.get("contract_hash_sha256")
    else:
        core = dict(document)
        stored_hash = core.pop("contract_hash_sha256", None)
    contract_hash = canonical_hash(core)
    if stored_hash is not None and stored_hash != contract_hash:
        raise ControlPlaneError("LEGACY_SOURCE_CONTRACT_HASH_MISMATCH")
    contract_id = core.get("contract_id")
    if type(contract_id) is not str:
        raise ControlPlaneError("LEGACY_SOURCE_CONTRACT_INVALID")
    return contract_id, contract_hash


def _legacy_path(root86: Path, raw_path_text: str) -> tuple[Path, str]:
    raw_path = Path(raw_path_text)
    if not raw_path.is_absolute():
        raw_path = REPOSITORY_ROOT / raw_path
    _reject_symlink_components(raw_path)
    resolved = raw_path.resolve(strict=True)
    resolved_root = root86.resolve(strict=True)
    if not _is_relative_to(resolved, resolved_root):
        raise ControlPlaneError("LEGACY_RAW_PATH_ESCAPE")
    return resolved, str(resolved.relative_to(resolved_root))


def _legacy_response_identity_hash(
    *,
    contract_hash: str,
    method: str,
    url: str,
    params: Mapping[str, Any],
    body: bytes,
) -> str:
    request_identity = canonical_json(
        {
            "contract_hash": contract_hash,
            "method": method,
            "url": url,
            "params": deep_thaw(params),
        }
    ).encode("utf-8")
    return sha256_bytes(request_identity + b"\n" + body)


def _legacy_series_hash(
    conn: sqlite3.Connection,
    *,
    contract_hash: str,
    stream: str,
    symbol: str,
) -> tuple[int, str]:
    hasher = hashlib.sha256()
    if stream == "funding_rates":
        rows = conn.execute(
            "SELECT funding_time_ms,funding_rate,mark_price,response_hash,source_url "
            "FROM mission86_funding_rates WHERE contract_hash=? AND symbol=? "
            "ORDER BY funding_time_ms",
            (contract_hash, symbol),
        ).fetchall()
        for row in rows:
            hasher.update(
                canonical_json(
                    [
                        row["funding_time_ms"],
                        row["funding_rate"],
                        row["mark_price"],
                        row["response_hash"],
                        row["source_url"],
                    ]
                ).encode("utf-8")
            )
            hasher.update(b"\n")
        return len(rows), hasher.hexdigest()

    rows = conn.execute(
        "SELECT open_time_ms,close_time_ms,open_price,high_price,low_price,close_price,"
        "volume,quote_volume,trade_count,response_hash,source_url "
        "FROM mission86_market_bars WHERE contract_hash=? AND stream=? AND symbol=? "
        "AND interval='1h' ORDER BY open_time_ms",
        (contract_hash, stream, symbol),
    ).fetchall()
    for row in rows:
        hasher.update(
            canonical_json(
                [
                    row["open_time_ms"],
                    row["close_time_ms"],
                    row["open_price"],
                    row["high_price"],
                    row["low_price"],
                    row["close_price"],
                    row["volume"],
                    row["quote_volume"],
                    row["trade_count"],
                    row["response_hash"],
                    row["source_url"],
                ]
            ).encode("utf-8")
        )
        hasher.update(b"\n")
    return len(rows), hasher.hexdigest()


def _legacy_exact_envelope_row(
    conn: sqlite3.Connection,
    *,
    table: str,
) -> sqlite3.Row:
    rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
    if len(rows) != 1:
        raise ControlPlaneError("LEGACY_DATABASE_LINEAGE_MISMATCH")
    return rows[0]


def audit_legacy(
    *,
    database_path: str | Path,
    mission86_root: str | Path,
    mission87_root: str | Path,
    expected_inventory: bool = True,
) -> VerifiedLegacyAudit:
    """Verify the frozen Mission 86/87 evidence without exposing market values."""

    _autonomy, mission = load_contracts()
    bounds = mission["resource_bounds"]
    inventory = mission["legacy_acceptance_inventory"]
    if (
        inventory.get("sqlite_counts") != EXPECTED_LEGACY_COUNTS
        or inventory.get("mission86_files") != 277
        or inventory.get("mission86_gzip_raw_responses") != 276
        or inventory.get("mission87_files") != 1
        or inventory.get("mission86_manifest_file_sha256") != EXPECTED_MANIFEST_FILE_HASH
        or inventory.get("mission87_certificate_file_sha256") != EXPECTED_CERTIFICATE_FILE_HASH
        or bounds.get("maximum_legacy_raw_responses") != 276
        or bounds.get("expected_legacy_market_bar_count") != 262656
        or bounds.get("expected_legacy_funding_count") != 8208
        or bounds.get("expected_legacy_series_count") != 15
    ):
        raise ControlPlaneError("LEGACY_CONTRACT_CODE_MISMATCH")
    started = time.monotonic()
    database = Path(database_path)
    root86 = Path(mission86_root)
    root87 = Path(mission87_root)
    for path in (database, root86, root87):
        _reject_symlink_components(path)
        if path.is_symlink() or not path.exists():
            raise ControlPlaneError("LEGACY_PATH_INVALID")

    manifest_path = root86 / "manifest.json"
    certificate_path = root87 / "certificate.json"
    if not manifest_path.is_file() or not certificate_path.is_file():
        raise ControlPlaneError("LEGACY_LINEAGE_FILE_MISSING")
    manifest_raw = read_bounded_regular_file(
        manifest_path,
        maximum_bytes=4 * 1024 * 1024,
        size_reason="LEGACY_MANIFEST_SIZE_LIMIT",
        invalid_reason="LEGACY_LINEAGE_FILE_INVALID",
    )
    certificate_raw = read_bounded_regular_file(
        certificate_path,
        maximum_bytes=2 * 1024 * 1024,
        size_reason="LEGACY_CERTIFICATE_SIZE_LIMIT",
        invalid_reason="LEGACY_LINEAGE_FILE_INVALID",
    )
    manifest_file_hash = sha256_bytes(manifest_raw)
    certificate_file_hash = sha256_bytes(certificate_raw)
    count86, gzip86, links86 = _walk_metadata(root86)
    count87, _gzip87, links87 = _walk_metadata(root87)

    manifest_document = strict_json_load(
        manifest_raw,
        maximum_bytes=4 * 1024 * 1024,
    )
    certificate_document = strict_json_load(
        certificate_raw,
        maximum_bytes=2 * 1024 * 1024,
    )
    if type(manifest_document) is not dict or type(certificate_document) is not dict:
        raise ControlPlaneError("LEGACY_LINEAGE_INVALID")
    if set(manifest_document) != {"manifest_hash_sha256", "created_at", "manifest"}:
        raise ControlPlaneError("LEGACY_MANIFEST_ENVELOPE_INVALID")
    if set(certificate_document) != {
        "certificate_hash_sha256",
        "created_at",
        "certificate",
    }:
        raise ControlPlaneError("LEGACY_CERTIFICATE_ENVELOPE_INVALID")
    manifest_core = manifest_document["manifest"]
    certificate_core = certificate_document["certificate"]
    if type(manifest_core) is not dict or type(certificate_core) is not dict:
        raise ControlPlaneError("LEGACY_LINEAGE_INVALID")

    manifest_core_hash = canonical_hash(manifest_core)
    certificate_core_hash = canonical_hash(certificate_core)
    if manifest_document["manifest_hash_sha256"] != manifest_core_hash:
        raise ControlPlaneError("LEGACY_MANIFEST_HASH_MISMATCH")
    if certificate_document["certificate_hash_sha256"] != certificate_core_hash:
        raise ControlPlaneError("LEGACY_CERTIFICATE_HASH_MISMATCH")
    if certificate_core.get("source_manifest_hash") != manifest_core_hash:
        raise ControlPlaneError("LEGACY_LINEAGE_INVALID")

    source_contract_id, source_contract_hash = _load_legacy_contract_identity()
    if manifest_core.get("contract_id") != source_contract_id:
        raise ControlPlaneError("LEGACY_MANIFEST_CONTRACT_ID_MISMATCH")
    if manifest_core.get("contract_hash") != source_contract_hash:
        raise ControlPlaneError("LEGACY_MANIFEST_CONTRACT_HASH_MISMATCH")
    if certificate_core.get("contract_id") != source_contract_id:
        raise ControlPlaneError("LEGACY_CERTIFICATE_CONTRACT_ID_MISMATCH")
    if certificate_core.get("contract_hash") != source_contract_hash:
        raise ControlPlaneError("LEGACY_CERTIFICATE_CONTRACT_HASH_MISMATCH")

    manifest_raw_responses = manifest_core.get("raw_responses")
    certificate_series = certificate_core.get("series_certifications")
    certificate_checks = certificate_core.get("quality_checks")
    if type(manifest_raw_responses) is not list:
        raise ControlPlaneError("LEGACY_MANIFEST_RAW_RESPONSES_INVALID")
    if type(certificate_series) is not list or type(certificate_checks) is not list:
        raise ControlPlaneError("LEGACY_CERTIFICATE_EVIDENCE_INVALID")

    manifest_response_map: dict[str, dict[str, Any]] = {}
    for item in manifest_raw_responses:
        if type(item) is not dict:
            raise ControlPlaneError("LEGACY_MANIFEST_RAW_RESPONSES_INVALID")
        response_hash = item.get("response_hash")
        require_hash(response_hash, "legacy_manifest_response_hash")
        if response_hash in manifest_response_map:
            raise ControlPlaneError("LEGACY_MANIFEST_RESPONSE_DUPLICATE")
        manifest_response_map[response_hash] = item

    certificate_series_map: dict[tuple[str, str], dict[str, Any]] = {}
    for item in certificate_series:
        if type(item) is not dict:
            raise ControlPlaneError("LEGACY_CERTIFICATE_SERIES_INVALID")
        stream = item.get("stream")
        symbol = item.get("symbol")
        if type(stream) is not str or type(symbol) is not str:
            raise ControlPlaneError("LEGACY_CERTIFICATE_SERIES_INVALID")
        key = (stream, symbol)
        if key in certificate_series_map:
            raise ControlPlaneError("LEGACY_CERTIFICATE_SERIES_DUPLICATE")
        certificate_series_map[key] = item

    conn = _open_sqlite(database, readonly=True)
    conn.row_factory = sqlite3.Row
    try:
        integrity_row = conn.execute("PRAGMA integrity_check").fetchone()
        integrity = integrity_row[0] if integrity_row is not None else "missing"
        table_counts = {
            table: int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in EXPECTED_LEGACY_COUNTS
        }

        run_rows = conn.execute(
            "SELECT run_label,contract_id,contract_hash,manifest_hash,run_status,"
            "market_bar_count,funding_rate_count,raw_response_count,fail_check_count,"
            "safety_breach_count,mission87_status,live_trading,live_order_sent,capital_deployment "
            "FROM mission86_ingestion_runs"
        ).fetchall()
        if len(run_rows) != 1:
            raise ControlPlaneError("LEGACY_SOURCE_RUN_MISSING")
        run = run_rows[0]
        if (
            run["contract_id"] != source_contract_id
            or run["contract_hash"] != source_contract_hash
            or run["manifest_hash"] != manifest_core_hash
            or run["run_status"] != "COMPLETE_UNCERTIFIED_REAL_MARKET_DATA_FOUNDATION"
            or int(run["fail_check_count"]) != 0
            or int(run["safety_breach_count"]) != 0
            or run["mission87_status"] != "READY_FOR_DATASET_CERTIFICATION"
            or run["live_trading"] != "DISABLED"
            or int(run["live_order_sent"]) != 0
            or run["capital_deployment"] != "BLOCKED"
        ):
            raise ControlPlaneError("LEGACY_SOURCE_RUN_LINEAGE_MISMATCH")

        certification_rows = conn.execute(
            "SELECT certification_run_label,source_run_label,contract_id,contract_hash,"
            "source_manifest_hash,certificate_hash,certification_status,mission87_status,"
            "raw_response_count,market_bar_count,funding_rate_count,fail_check_count,"
            "safety_breach_count,holdout_performance_evaluated,backtesting_performed,"
            "profitability_analyzed,live_trading,live_order_sent,capital_deployment "
            "FROM mission87_certification_runs"
        ).fetchall()
        if len(certification_rows) != 1:
            raise ControlPlaneError("LEGACY_CERTIFICATION_RUN_MISSING")
        certification = certification_rows[0]
        if (
            certification["source_run_label"] != run["run_label"]
            or certification["contract_id"] != source_contract_id
            or certification["contract_hash"] != source_contract_hash
            or certification["source_manifest_hash"] != manifest_core_hash
            or certification["certificate_hash"] != certificate_core_hash
            or certification["certification_status"]
            != "CERTIFIED_FOR_RESEARCH_PENDING_EXECUTION_COST_MODEL"
            or certification["mission87_status"] != "COMPLETE_REAL_MARKET_DATASET_CERTIFICATION"
            or int(certification["fail_check_count"]) != 0
            or int(certification["safety_breach_count"]) != 0
            or int(certification["holdout_performance_evaluated"]) != 0
            or int(certification["backtesting_performed"]) != 0
            or int(certification["profitability_analyzed"]) != 0
            or certification["live_trading"] != "DISABLED"
            or int(certification["live_order_sent"]) != 0
            or certification["capital_deployment"] != "BLOCKED"
        ):
            raise ControlPlaneError("LEGACY_CERTIFICATION_LINEAGE_MISMATCH")

        manifest_row = _legacy_exact_envelope_row(
            conn,
            table="mission86_dataset_manifests",
        )
        stored_manifest_document = strict_json_load(
            manifest_row["manifest_json"],
            maximum_bytes=4 * 1024 * 1024,
        )
        if (
            manifest_row["run_label"] != run["run_label"]
            or manifest_row["contract_hash"] != source_contract_hash
            or manifest_row["manifest_hash"] != manifest_core_hash
            or manifest_row["certification_status"] != "UNCERTIFIED_PENDING_MISSION87"
            or stored_manifest_document != manifest_document
        ):
            raise ControlPlaneError("LEGACY_DATABASE_MANIFEST_MISMATCH")
        resolved_manifest_row_path = Path(manifest_row["manifest_path"])
        if not resolved_manifest_row_path.is_absolute():
            resolved_manifest_row_path = REPOSITORY_ROOT / resolved_manifest_row_path
        if resolved_manifest_row_path.resolve(strict=True) != manifest_path.resolve(strict=True):
            raise ControlPlaneError("LEGACY_DATABASE_MANIFEST_PATH_MISMATCH")

        certificate_row = _legacy_exact_envelope_row(
            conn,
            table="mission87_dataset_certificates",
        )
        stored_certificate_document = strict_json_load(
            certificate_row["certificate_json"],
            maximum_bytes=2 * 1024 * 1024,
        )
        if (
            certificate_row["certification_run_label"]
            != certification["certification_run_label"]
            or certificate_row["source_run_label"] != run["run_label"]
            or certificate_row["contract_hash"] != source_contract_hash
            or certificate_row["source_manifest_hash"] != manifest_core_hash
            or certificate_row["certificate_hash"] != certificate_core_hash
            or certificate_row["certification_status"]
            != "CERTIFIED_FOR_RESEARCH_PENDING_EXECUTION_COST_MODEL"
            or stored_certificate_document != certificate_document
        ):
            raise ControlPlaneError("LEGACY_DATABASE_CERTIFICATE_MISMATCH")
        resolved_certificate_row_path = Path(certificate_row["certificate_path"])
        if not resolved_certificate_row_path.is_absolute():
            resolved_certificate_row_path = REPOSITORY_ROOT / resolved_certificate_row_path
        if resolved_certificate_row_path.resolve(strict=True) != certificate_path.resolve(strict=True):
            raise ControlPlaneError("LEGACY_DATABASE_CERTIFICATE_PATH_MISMATCH")

        response_rows = conn.execute(
            "SELECT response_hash,captured_at,stream,symbol,request_method,request_url,"
            "request_params_json,http_status,body_sha256,raw_path,response_row_count,"
            "response_headers_json FROM mission86_raw_responses "
            "WHERE contract_hash=? ORDER BY stream,symbol,request_params_json,response_hash",
            (source_contract_hash,),
        ).fetchall()
        database_manifest_rows: list[dict[str, Any]] = []
        response_evidence: list[dict[str, Any]] = []
        for row in response_rows:
            require_hash(row["response_hash"], "legacy_response_hash")
            require_hash(row["body_sha256"], "legacy_body_hash")
            resolved_raw, relative_raw = _legacy_path(root86, row["raw_path"])
            if resolved_raw.stat().st_size > bounds["maximum_response_bytes"]:
                raise ControlPlaneError("RAW_OBJECT_SIZE_LIMIT")
            raw = read_bounded_regular_file(
                resolved_raw,
                maximum_bytes=bounds["maximum_response_bytes"],
                size_reason="RAW_OBJECT_SIZE_LIMIT",
                invalid_reason="LEGACY_RAW_FILE_INVALID",
            )
            compressed_hash = sha256_bytes(raw)
            body = strict_gzip_body(
                raw,
                maximum_decompressed_bytes=bounds[
                    "maximum_decompressed_response_bytes"
                ],
            )
            body_hash = sha256_bytes(body)
            if body_hash != row["body_sha256"]:
                raise ControlPlaneError("LEGACY_RAW_HASH_MISMATCH")
            params = strict_json_load(
                row["request_params_json"],
                maximum_bytes=64 * 1024,
            )
            headers = strict_json_load(
                row["response_headers_json"],
                maximum_bytes=64 * 1024,
            )
            if type(params) is not dict or type(headers) is not dict:
                raise ControlPlaneError("LEGACY_REQUEST_METADATA_INVALID")
            recomputed_response_hash = _legacy_response_identity_hash(
                contract_hash=source_contract_hash,
                method=row["request_method"],
                url=row["request_url"],
                params=params,
                body=body,
            )
            if recomputed_response_hash != row["response_hash"]:
                raise ControlPlaneError("LEGACY_RESPONSE_HASH_MISMATCH")
            body_document = strict_json_load(
                body,
                maximum_bytes=bounds["maximum_decompressed_response_bytes"],
            )
            if type(body_document) is not list:
                raise ControlPlaneError("LEGACY_RAW_JSON_INVALID")
            if len(body_document) != int(row["response_row_count"]):
                raise ControlPlaneError("LEGACY_RAW_ROW_COUNT_MISMATCH")

            manifest_item = {
                "response_hash": row["response_hash"],
                "stream": row["stream"],
                "symbol": row["symbol"],
                "request_url": row["request_url"],
                "request_params_json": row["request_params_json"],
                "body_sha256": row["body_sha256"],
                "raw_path": row["raw_path"],
                "response_row_count": row["response_row_count"],
            }
            database_manifest_rows.append(manifest_item)
            if manifest_response_map.get(row["response_hash"]) != manifest_item:
                raise ControlPlaneError("LEGACY_MANIFEST_RESPONSE_MISMATCH")

            response_evidence.append(
                {
                    "response_hash": row["response_hash"],
                    "captured_at": _normalize_legacy_timestamp(row["captured_at"]),
                    "stream": row["stream"],
                    "symbol": row["symbol"],
                    "request_method": row["request_method"],
                    "request_url": row["request_url"],
                    "request_params_hash": canonical_hash(params),
                    "http_status": int(row["http_status"]),
                    "body_sha256": row["body_sha256"],
                    "compressed_object_sha256": compressed_hash,
                    "raw_relative_path": relative_raw,
                    "response_row_count": int(row["response_row_count"]),
                    "response_headers_hash": canonical_hash(headers),
                }
            )

        if len(database_manifest_rows) != len(manifest_raw_responses):
            raise ControlPlaneError("LEGACY_MANIFEST_RESPONSE_COUNT_MISMATCH")
        if database_manifest_rows != manifest_raw_responses:
            raise ControlPlaneError("LEGACY_MANIFEST_RESPONSE_ORDER_OR_CONTENT_MISMATCH")

        series_rows = conn.execute(
            "SELECT certification_run_label,source_run_label,stream,symbol,series_type,"
            "row_count,expected_row_count,series_hash,certification_status,metrics_json "
            "FROM mission87_series_certifications ORDER BY stream,symbol"
        ).fetchall()
        series_identity: list[dict[str, Any]] = []
        for row in series_rows:
            key = (row["stream"], row["symbol"])
            certificate_item = certificate_series_map.get(key)
            if certificate_item is None:
                raise ControlPlaneError("LEGACY_CERTIFICATE_SERIES_MISSING")
            metrics = strict_json_load(
                row["metrics_json"],
                maximum_bytes=512 * 1024,
            )
            if metrics != certificate_item:
                raise ControlPlaneError("LEGACY_SERIES_METRICS_MISMATCH")
            actual_count, actual_hash = _legacy_series_hash(
                conn,
                contract_hash=source_contract_hash,
                stream=row["stream"],
                symbol=row["symbol"],
            )
            if (
                row["certification_run_label"]
                != certification["certification_run_label"]
                or row["source_run_label"] != run["run_label"]
                or int(row["row_count"]) != actual_count
                or row["series_hash"] != actual_hash
                or certificate_item.get("row_count") != actual_count
                or certificate_item.get("series_hash") != actual_hash
                or certificate_item.get("expected_row_count")
                != row["expected_row_count"]
                or certificate_item.get("certification_status")
                != row["certification_status"]
                or row["certification_status"]
                != "CERTIFIED_FOR_RESEARCH_PENDING_EXECUTION_COST_MODEL"
            ):
                raise ControlPlaneError("LEGACY_NORMALIZED_SERIES_MISMATCH")
            series_identity.append(
                {
                    "stream": row["stream"],
                    "symbol": row["symbol"],
                    "series_type": row["series_type"],
                    "row_count": actual_count,
                    "expected_row_count": row["expected_row_count"],
                    "series_hash": actual_hash,
                    "certification_status": row["certification_status"],
                    "metrics_hash": canonical_hash(metrics),
                }
            )

        if len(series_identity) != len(certificate_series_map):
            raise ControlPlaneError("LEGACY_CERTIFICATE_SERIES_COUNT_MISMATCH")

        quality_rows = conn.execute(
            "SELECT check_category,check_name,check_status,observed_value,expected_value,"
            "check_reason FROM mission87_quality_checks WHERE certification_run_label=? "
            "ORDER BY rowid",
            (certification["certification_run_label"],),
        ).fetchall()
        quality_items = [
            {
                "check_category": row["check_category"],
                "check_name": row["check_name"],
                "check_status": row["check_status"],
                "observed_value": row["observed_value"],
                "expected_value": row["expected_value"],
                "check_reason": row["check_reason"],
            }
            for row in quality_rows
        ]
        if quality_items != certificate_checks:
            raise ControlPlaneError("LEGACY_QUALITY_CHECK_MISMATCH")

        actual_market_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM mission86_market_bars WHERE contract_hash=?",
                (source_contract_hash,),
            ).fetchone()[0]
        )
        actual_funding_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM mission86_funding_rates WHERE contract_hash=?",
                (source_contract_hash,),
            ).fetchone()[0]
        )
        if (
            int(run["market_bar_count"]) != actual_market_count
            or int(run["funding_rate_count"]) != actual_funding_count
            or int(run["raw_response_count"]) != len(response_rows)
            or int(certification["market_bar_count"]) != actual_market_count
            or int(certification["funding_rate_count"]) != actual_funding_count
            or int(certification["raw_response_count"]) != len(response_rows)
        ):
            raise ControlPlaneError("LEGACY_SOURCE_COUNTS_MISMATCH")
    except sqlite3.DatabaseError as error:
        raise ControlPlaneError("LEGACY_DATABASE_INVALID", str(error)) from error
    finally:
        conn.close()

    source_contracts = _normalize_source_contracts(
        _current_contract_identities()
        + (
            {
                "contract_id": source_contract_id,
                "contract_hash_sha256": source_contract_hash,
                "role": "MISSION_85_SOURCE_CONTRACT",
            },
            {
                "contract_id": f"mission86-manifest:{run['run_label']}",
                "contract_hash_sha256": manifest_core_hash,
                "role": "MISSION_86_SOURCE_MANIFEST",
            },
            {
                "contract_id": (
                    "mission87-certificate:"
                    f"{certification['certification_run_label']}"
                ),
                "contract_hash_sha256": certificate_core_hash,
                "role": "MISSION_87_SOURCE_CERTIFICATE",
            },
        )
    )

    checks = [
        integrity == "ok",
        links86 + links87 == 0,
        time.monotonic() - started
        <= bounds["maximum_bounded_audit_runtime_seconds"],
    ]
    if expected_inventory:
        checks.extend(
            [
                count86 == 277,
                gzip86 == 276,
                count87 == 1,
                manifest_file_hash == EXPECTED_MANIFEST_FILE_HASH,
                certificate_file_hash == EXPECTED_CERTIFICATE_FILE_HASH,
                table_counts == EXPECTED_LEGACY_COUNTS,
                len(response_rows) == 276,
                len(series_rows) == 15,
                len(quality_items) == 23,
                len(manifest_raw_responses) == 276,
                actual_market_count == 262656,
                actual_funding_count == 8208,
            ]
        )
    if not all(checks):
        raise ControlPlaneError("LEGACY_ACCEPTANCE_MISMATCH")

    return VerifiedLegacyAudit(
        verdict="PASS" if expected_inventory else "SYNTHETIC_INVENTORY_AUDITED",
        database_integrity=integrity,
        table_counts=table_counts,
        mission86_file_count=count86,
        mission86_raw_gzip_count=gzip86,
        mission87_file_count=count87,
        manifest_file_sha256=manifest_file_hash,
        certificate_file_sha256=certificate_file_hash,
        manifest_core_hash=manifest_core_hash,
        certificate_core_hash=certificate_core_hash,
        source_run_label=run["run_label"],
        source_contract_id=source_contract_id,
        source_contract_hash=source_contract_hash,
        certification_run_label=certification["certification_run_label"],
        response_evidence_hash=canonical_hash(response_evidence),
        series_identity_hash=canonical_hash(series_identity),
        source_contract_identities=source_contracts,
        symlink_count=links86 + links87,
    )


def plan_legacy_release(
    *,
    database_path: str | Path,
    mission86_root: str | Path,
    mission87_root: str | Path,
) -> Mapping[str, Any]:
    report = audit_legacy(
        database_path=database_path,
        mission86_root=mission86_root,
        mission87_root=mission87_root,
        expected_inventory=True,
    )
    return deep_freeze(
        {
            "status": "PLAN_ONLY",
            "audit": report.as_dict(),
            "availability_class": AvailabilityClass.UNKNOWN.value,
            "availability_policy_id": AVAILABILITY_POLICY_ID,
            "real_data_research_resolution": False,
            "network_requests": 0,
            "write_performed": False,
        }
    )


def _normalize_legacy_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ControlPlaneError("LEGACY_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _legacy_receipts(
    database_path: Path,
    root86: Path,
    audit: VerifiedLegacyAudit,
) -> tuple[tuple[LegacyAcquisitionReceipt, ...], dict[str, bytes], dict[str, str]]:
    conn = _open_sqlite(database_path, readonly=True)
    conn.row_factory = sqlite3.Row
    receipts: list[LegacyAcquisitionReceipt] = []
    objects: dict[str, bytes] = {}
    bounds = _mission_bounds()
    response_to_receipt: dict[str, str] = {}
    try:
        rows = conn.execute(
            "SELECT response_hash, captured_at, request_method, request_url, request_params_json, "
            "http_status, body_sha256, raw_path, response_row_count, response_headers_json "
            "FROM mission86_raw_responses ORDER BY response_hash"
        ).fetchall()
        for row in rows:
            resolved, relative = _legacy_path(root86, row["raw_path"])
            raw = read_bounded_regular_file(
                resolved,
                maximum_bytes=bounds["maximum_response_bytes"],
                size_reason="RAW_OBJECT_SIZE_LIMIT",
                invalid_reason="LEGACY_RAW_FILE_INVALID",
            )
            object_hash = sha256_bytes(raw)
            params = strict_json_load(row["request_params_json"], maximum_bytes=64 * 1024)
            headers = strict_json_load(row["response_headers_json"], maximum_bytes=64 * 1024)
            receipt = LegacyAcquisitionReceipt(
                request_id=f"legacy-{row['response_hash']}",
                provider="BINANCE_PUBLIC",
                request_url=row["request_url"],
                method=row["request_method"],
                request_params=params,
                http_status=row["http_status"],
                captured_at=_normalize_legacy_timestamp(row["captured_at"]),
                response_headers=headers,
                response_row_count=row["response_row_count"],
                source_response_hash=row["response_hash"],
                body_sha256=row["body_sha256"],
                compressed_object_sha256=object_hash,
                raw_relative_path=relative,
                source_run_label=audit.source_run_label,
                source_contract_id=audit.source_contract_id,
                source_contract_hash=audit.source_contract_hash,
                source_manifest_hash=audit.manifest_core_hash,
                collector_id="mission86-real-market-data-foundation-v1",
                repository_commit=None,
            )
            receipts.append(receipt)
            objects[object_hash] = raw
            response_to_receipt[row["response_hash"]] = receipt.receipt_hash
    finally:
        conn.close()
    return tuple(receipts), objects, response_to_receipt


def _legacy_rows(
    database_path: Path,
    response_to_receipt: Mapping[str, str],
) -> tuple[ObservationVersion, ...]:
    conn = _open_sqlite(database_path, readonly=True)
    conn.row_factory = sqlite3.Row
    observations: list[ObservationVersion] = []
    try:
        for row in conn.execute(
            "SELECT stream,symbol,interval,open_time_ms,close_time_ms,open_price,high_price,"
            "low_price,close_price,volume,quote_volume,trade_count,response_hash,inserted_at "
            "FROM mission86_market_bars ORDER BY stream,symbol,open_time_ms"
        ):
            event_time = datetime.fromtimestamp(
                row["close_time_ms"] / 1000,
                tz=timezone.utc,
            ).isoformat().replace("+00:00", "Z")
            observed = _normalize_legacy_timestamp(row["inserted_at"])
            observations.append(
                ObservationVersion(
                    logical_id=(
                        f"BINANCE_PUBLIC/{row['stream']}/{row['symbol']}/"
                        f"{row['interval']}/{row['open_time_ms']}"
                    ),
                    provider="BINANCE_PUBLIC",
                    stream=row["stream"],
                    symbol=row["symbol"],
                    interval=row["interval"],
                    event_time=event_time,
                    source_time=event_time,
                    available_at=None,
                    availability_class=AvailabilityClass.UNKNOWN,
                    availability_policy_id=AVAILABILITY_POLICY_ID,
                    first_observed_at=observed,
                    last_verified_at=observed,
                    revision_number=0,
                    supersedes_record_hash=None,
                    source_response_hash=row["response_hash"],
                    receipt_hash=response_to_receipt[row["response_hash"]],
                    normalizer_id=NORMALIZER_ID,
                    normalized_payload={
                        "period_start_ms": row["open_time_ms"],
                        "open": row["open_price"],
                        "high": row["high_price"],
                        "low": row["low_price"],
                        "close": row["close_price"],
                        "volume": row["volume"],
                        "quote_volume": row["quote_volume"],
                        "trade_count": row["trade_count"],
                    },
                    clock_health=ClockHealth.UNKNOWN,
                )
            )
        for row in conn.execute(
            "SELECT symbol,funding_time_ms,funding_rate,mark_price,response_hash,inserted_at "
            "FROM mission86_funding_rates ORDER BY symbol,funding_time_ms"
        ):
            event_time = datetime.fromtimestamp(
                row["funding_time_ms"] / 1000,
                tz=timezone.utc,
            ).isoformat().replace("+00:00", "Z")
            observed = _normalize_legacy_timestamp(row["inserted_at"])
            observations.append(
                ObservationVersion(
                    logical_id=(
                        f"BINANCE_PUBLIC/funding_rates/{row['symbol']}/{row['funding_time_ms']}"
                    ),
                    provider="BINANCE_PUBLIC",
                    stream="funding_rates",
                    symbol=row["symbol"],
                    interval=None,
                    event_time=event_time,
                    source_time=event_time,
                    available_at=None,
                    availability_class=AvailabilityClass.UNKNOWN,
                    availability_policy_id=AVAILABILITY_POLICY_ID,
                    first_observed_at=observed,
                    last_verified_at=observed,
                    revision_number=0,
                    supersedes_record_hash=None,
                    source_response_hash=row["response_hash"],
                    receipt_hash=response_to_receipt[row["response_hash"]],
                    normalizer_id=NORMALIZER_ID,
                    normalized_payload={
                        "funding_rate": row["funding_rate"],
                        "mark_price": row["mark_price"],
                    },
                    clock_health=ClockHealth.UNKNOWN,
                )
            )
    finally:
        conn.close()
    return validate_revision_chains(observations)


def _current_repository_identity(repository_root: Path = REPOSITORY_ROOT) -> str:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ControlPlaneError("REPOSITORY_IDENTITY_UNAVAILABLE") from error
    require_git_commit(head, "repository_commit")
    if status:
        raise ControlPlaneError("REPOSITORY_NOT_CLEAN")
    return head


def build_legacy_release(
    *,
    catalogue: Catalogue,
    database_path: str | Path,
    mission86_root: str | Path,
    mission87_root: str | Path,
    execution_acknowledgement: str,
) -> Mapping[str, Any]:
    """Build the exact legacy snapshot only after re-auditing immutable evidence."""

    load_contracts()
    if execution_acknowledgement != "BUILD_LEGACY_RELEASE":
        raise ControlPlaneError("EXECUTION_ACKNOWLEDGEMENT_REQUIRED")
    repository_commit = _current_repository_identity()
    first = audit_legacy(
        database_path=database_path,
        mission86_root=mission86_root,
        mission87_root=mission87_root,
        expected_inventory=True,
    )
    receipts, raw_objects, response_to_receipt = _legacy_receipts(
        Path(database_path),
        Path(mission86_root),
        first,
    )
    observations = _legacy_rows(Path(database_path), response_to_receipt)
    second = audit_legacy(
        database_path=database_path,
        mission86_root=mission86_root,
        mission87_root=mission87_root,
        expected_inventory=True,
    )
    if first.proof_hash != second.proof_hash:
        raise ControlPlaneError("LEGACY_AUDIT_CHANGED_DURING_BUILD")
    if _current_repository_identity() != repository_commit:
        raise ControlPlaneError("REPOSITORY_CHANGED_DURING_BUILD")
    return _Publisher(catalogue).publish(
        observations=observations,
        receipts=receipts,
        raw_objects=raw_objects,
        parent_release_id=None,
        repository_commit=repository_commit,
        synthetic_fixture=False,
        warnings=(
            "LEGACY_AVAILABILITY_UNKNOWN",
            "REAL_DATA_RESEARCH_RESOLUTION_UNAUTHORIZED",
        ),
        quarantine=(),
        legacy_proof_hash=second.proof_hash,
        legacy_audit_proof=second.proof_core(),
        source_contract_identities=tuple(
            deep_thaw(item) for item in second.source_contract_identities
        ),
    )


def _publication_lock_active(lock_path: Path) -> bool:
    descriptor = os.open(lock_path, _secure_open_flags(os.O_RDWR))
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN}:
                return True
            raise ControlPlaneError("PUBLICATION_LOCK_FAILED") from error
        else:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return False
    finally:
        os.close(descriptor)


def inspect_recovery(
    runtime: Catalogue | str | Path,
    *,
    repository_root: str | Path = REPOSITORY_ROOT,
) -> tuple[Mapping[str, Any], ...]:
    """Classify recovery state without deleting, repairing, or cataloguing evidence."""

    load_contracts()
    if isinstance(runtime, Catalogue):
        catalogue = runtime
        root = catalogue.runtime_root
    else:
        root = validate_runtime_root(runtime, repository_root=repository_root)
        try:
            catalogue = Catalogue(root, repository_root=repository_root)
        except ControlPlaneError as error:
            return (
                deep_freeze(
                    {
                        "path": "catalogue.sqlite3",
                        "state": "CORRUPTED_CATALOGUE",
                        "reason": error.reason,
                        "action": "FAIL_CLOSED_OPERATOR_REVIEW",
                    }
                ),
            )

    catalogue._verify()
    bounds = _mission_bounds()
    states: list[dict[str, Any]] = []

    if _publication_lock_active(catalogue.lock_path):
        states.append(
            {
                "path": "locks/publication.lock",
                "state": "PUBLICATION_LOCK_ACTIVE",
                "action": "WAIT_OR_OPERATOR_REVIEW",
            }
        )

    catalogued = {
        item["release_id"]: item for item in catalogue._release_rows_metadata()
    }
    referenced_objects: set[str] = set()

    for path in sorted((root / "staging").iterdir(), key=lambda item: item.name):
        relative = f"staging/{path.name}"
        if path.is_symlink() or not path.is_dir():
            states.append(
                {
                    "path": relative,
                    "state": "INVALID_STAGING_PATH",
                    "action": "FAIL_CLOSED_OPERATOR_REVIEW",
                }
            )
            continue
        names = {item.name for item in path.iterdir()}
        try:
            if names == {"release.sqlite3", "manifest.json", "certificate.json"}:
                snapshot = load_certified_snapshot(path, runtime_root=root)
                state = "VALID_COMPLETE_STAGING"
                referenced_objects.update(
                    item["compressed_object_sha256"]
                    for item in snapshot["object_refs"]
                )
            elif names == {"release.sqlite3", "manifest.json"}:
                snapshot = load_staged_snapshot(path, runtime_root=root)
                referenced_objects.update(
                    item["compressed_object_sha256"]
                    for item in snapshot["object_refs"]
                )
                state = "VALID_STAGING_PRECERTIFICATE"
            else:
                state = "INCOMPLETE_STAGING"
            states.append(
                {
                    "path": relative,
                    "state": state,
                    "action": "RETAIN_FOR_OPERATOR_REVIEW",
                }
            )
        except ControlPlaneError as error:
            states.append(
                {
                    "path": relative,
                    "state": "INVALID_STAGING_EVIDENCE",
                    "reason": error.reason,
                    "action": "FAIL_CLOSED_OPERATOR_REVIEW",
                }
            )

    release_entries = sorted(
        (root / "releases").iterdir(),
        key=lambda item: item.name,
    )
    release_dirs: dict[str, Path] = {}
    for path in release_entries:
        relative = f"releases/{path.name}"
        if path.is_symlink() or not path.is_dir():
            states.append(
                {
                    "path": relative,
                    "state": "INVALID_RELEASE_PATH",
                    "action": "FAIL_CLOSED_OPERATOR_REVIEW",
                }
            )
            continue
        release_dirs[path.name] = path

    for release_id, path in sorted(release_dirs.items()):
        if release_id in catalogued:
            continue
        try:
            snapshot = load_certified_snapshot(path, runtime_root=root)
            state = "ORPHANED_COMPLETE_RELEASE"
            referenced_objects.update(
                item["compressed_object_sha256"]
                for item in snapshot["object_refs"]
            )
        except ControlPlaneError as error:
            state = "ORPHANED_INVALID_RELEASE"
            states.append(
                {
                    "path": f"releases/{release_id}",
                    "state": state,
                    "reason": error.reason,
                    "action": "RETAIN_FOR_OPERATOR_REVIEW",
                }
            )
            continue
        states.append(
            {
                "path": f"releases/{release_id}",
                "state": state,
                "action": "RETAIN_FOR_OPERATOR_REVIEW",
            }
        )

    for release_id, record in sorted(catalogued.items()):
        path = root / record["relative_path"]
        if not path.exists():
            states.append(
                {
                    "path": record["relative_path"],
                    "state": "CATALOGUE_DANGLING_REFERENCE",
                    "action": "FAIL_CLOSED_RETAIN_CATALOGUE_EVIDENCE",
                }
            )
            continue
        if path.is_symlink() or not path.is_dir():
            states.append(
                {
                    "path": record["relative_path"],
                    "state": "CATALOGUED_RELEASE_PATH_INVALID",
                    "action": "FAIL_CLOSED_OPERATOR_REVIEW",
                }
            )
            continue
        try:
            snapshot = load_certified_snapshot(path, runtime_root=root)
            certificate = snapshot["certificate"]
            if (
                certificate.release_core_hash != record["release_core_hash"]
                or certificate.certificate_core_hash
                != record["certificate_core_hash"]
            ):
                raise ControlPlaneError("CATALOGUE_RELEASE_DISAGREEMENT")
            referenced_objects.update(
                item["compressed_object_sha256"]
                for item in snapshot["object_refs"]
            )
        except ControlPlaneError as error:
            states.append(
                {
                    "path": record["relative_path"],
                    "state": "CATALOGUED_RELEASE_INVALID",
                    "reason": error.reason,
                    "action": "FAIL_CLOSED_OPERATOR_REVIEW",
                }
            )

    object_root = root / "objects" / "sha256"
    object_files: list[Path] = []
    for shard in sorted(object_root.iterdir(), key=lambda item: item.name):
        if (
            shard.is_symlink()
            or not shard.is_dir()
            or len(shard.name) != 2
            or any(char not in "0123456789abcdef" for char in shard.name)
        ):
            states.append(
                {
                    "path": str(shard.relative_to(root)),
                    "state": "INVALID_RAW_OBJECT_SHARD",
                    "action": "FAIL_CLOSED_OPERATOR_REVIEW",
                }
            )
            continue
        for path in sorted(shard.iterdir(), key=lambda item: item.name):
            object_files.append(path)

    for path in object_files:
        relative = str(path.relative_to(root))
        object_hash = path.stem
        valid_shape = (
            not path.is_symlink()
            and path.is_file()
            and path.suffix == ".gz"
            and len(object_hash) == 64
            and all(char in "0123456789abcdef" for char in object_hash)
            and path.parent.name == object_hash[:2]
        )
        if not valid_shape:
            states.append(
                {
                    "path": relative,
                    "state": "INVALID_RAW_OBJECT_PATH",
                    "action": "FAIL_CLOSED_OPERATOR_REVIEW",
                }
            )
            continue
        if object_hash in referenced_objects:
            continue
        try:
            raw = read_bounded_regular_file(
                path,
                maximum_bytes=bounds["maximum_response_bytes"],
                size_reason="RAW_OBJECT_SIZE_LIMIT",
                invalid_reason="RAW_OBJECT_PATH_INVALID",
            )
            if sha256_bytes(raw) != object_hash:
                raise ControlPlaneError("RAW_OBJECT_HASH_MISMATCH")
            strict_gzip_body(
                raw,
                maximum_decompressed_bytes=bounds[
                    "maximum_decompressed_response_bytes"
                ],
            )
            state = "ORPHANED_RAW_OBJECT"
            reason = None
        except ControlPlaneError as error:
            state = "ORPHANED_INVALID_RAW_OBJECT"
            reason = error.reason
        item = {
            "path": relative,
            "state": state,
            "action": "RETAIN_FOR_OPERATOR_REVIEW",
        }
        if reason is not None:
            item["reason"] = reason
        states.append(item)

    incident_rows = {
        item["incident_id"]: item for item in catalogue._incident_rows_metadata()
    }
    seen_incidents: set[str] = set()
    for path in sorted((root / "incidents").iterdir(), key=lambda item: item.name):
        relative = str(path.relative_to(root))
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            states.append(
                {
                    "path": relative,
                    "state": "INVALID_INCIDENT_PATH",
                    "action": "FAIL_CLOSED_OPERATOR_REVIEW",
                }
            )
            continue
        try:
            raw = read_bounded_regular_file(
                path,
                maximum_bytes=256 * 1024,
                size_reason="INCIDENT_EVIDENCE_SIZE_LIMIT",
                invalid_reason="INCIDENT_EVIDENCE_INVALID",
            )
            document = strict_json_load(raw, maximum_bytes=256 * 1024)
            if (
                type(document) is not dict
                or set(document)
                != {"incident_id", "state", "release_id", "stage", "reason"}
                or canonical_json(document) + "\n" != raw.decode("utf-8")
            ):
                raise ControlPlaneError("INCIDENT_EVIDENCE_INVALID")
            incident_id = document["incident_id"]
            if path.name != f"{incident_id}.json":
                raise ControlPlaneError("INCIDENT_EVIDENCE_INVALID")
            require_hash(incident_id[len("incident-"):], "incident_id")
            expected_id = "incident-" + canonical_hash(
                {
                    "state": document["state"],
                    "release_id": document["release_id"],
                    "stage": document["stage"],
                    "reason": document["reason"],
                }
            )
            if incident_id != expected_id:
                raise ControlPlaneError("INCIDENT_EVIDENCE_HASH_MISMATCH")
            seen_incidents.add(incident_id)
            catalogue_item = incident_rows.get(incident_id)
            if catalogue_item is None:
                state = "INCIDENT_EVIDENCE_UNINDEXED"
            elif catalogue_item["evidence_hash"] != sha256_bytes(raw):
                raise ControlPlaneError("INCIDENT_CATALOGUE_HASH_MISMATCH")
            else:
                state = "INCIDENT_EVIDENCE"
            states.append(
                {
                    "path": relative,
                    "state": state,
                    "action": "RETAIN_FOR_OPERATOR_REVIEW",
                }
            )
        except (ControlPlaneError, UnicodeDecodeError) as error:
            reason = (
                error.reason
                if isinstance(error, ControlPlaneError)
                else "INCIDENT_EVIDENCE_INVALID"
            )
            states.append(
                {
                    "path": relative,
                    "state": "INVALID_INCIDENT_EVIDENCE",
                    "reason": reason,
                    "action": "FAIL_CLOSED_OPERATOR_REVIEW",
                }
            )

    for incident_id, item in sorted(incident_rows.items()):
        if incident_id not in seen_incidents:
            states.append(
                {
                    "path": item["relative_path"],
                    "state": "INCIDENT_CATALOGUE_DANGLING_REFERENCE",
                    "action": "FAIL_CLOSED_OPERATOR_REVIEW",
                }
            )

    return tuple(
        deep_freeze(item)
        for item in sorted(states, key=lambda item: (item["path"], item["state"]))
    )
