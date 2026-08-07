"""Independent persisted-evidence certification for Mission 99 releases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sqlite3
import stat
from typing import Any, Mapping
from urllib.parse import quote

from .core import (
    AUTONOMY_CONTRACT_HASH,
    MISSION_CONTRACT_HASH,
    AcquisitionReceipt,
    AvailabilityClass,
    ControlPlaneError,
    LegacyAcquisitionReceipt,
    ObservationVersion,
    PROTECTED_BOUNDARY,
    ReceiptKind,
    RELEASE_KIND,
    canonical_hash,
    canonical_json,
    deep_thaw,
    load_contracts,
    parse_utc,
    read_bounded_regular_file,
    receipt_from_dict,
    require_git_commit,
    require_hash,
    sha256_bytes,
    strict_gzip_body,
    strict_json_load,
    validate_revision_chains,
)
from .schema import expected_schema_fingerprint, verify_exact_schema


@dataclass(frozen=True)
class ReleaseCertificate:
    release_id: str
    release_core_hash: str
    certificate_core_hash: str
    row_count: int
    receipt_count: int
    raw_object_count: int
    verdict: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "release_core_hash": self.release_core_hash,
            "certificate_core_hash": self.certificate_core_hash,
            "row_count": self.row_count,
            "receipt_count": self.receipt_count,
            "raw_object_count": self.raw_object_count,
            "verdict": self.verdict,
        }


def _contained(root: Path, path: Path) -> Path:
    """Return an existing child without allowing lexical or symlink escape."""

    if ".." in path.parts:
        raise ControlPlaneError("RELEASE_PATH_ESCAPE")
    if root.is_symlink():
        raise ControlPlaneError("SYMLINK_REJECTED")
    resolved_root = root.resolve(strict=True)
    candidate = path if path.is_absolute() else Path.cwd() / path
    absolute = candidate.absolute()
    try:
        relative = absolute.relative_to(resolved_root)
    except ValueError as error:
        raise ControlPlaneError("RELEASE_PATH_ESCAPE") from error
    current = resolved_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ControlPlaneError("SYMLINK_REJECTED")
        if not current.exists():
            raise ControlPlaneError("RELEASE_PATH_MISSING")
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ControlPlaneError("RELEASE_PATH_ESCAPE") from error
    return resolved


def _validate_runtime_layout(runtime_root: Path) -> None:
    if (
        runtime_root.stat().st_uid != os.getuid()
        or stat.S_IMODE(runtime_root.stat().st_mode) != 0o700
    ):
        raise ControlPlaneError("RUNTIME_ROOT_MODE_INVALID")
    for relative in (
        "objects",
        "objects/sha256",
        "releases",
        "staging",
        "incidents",
        "locks",
    ):
        path = runtime_root / relative
        if (
            path.is_symlink()
            or not path.is_dir()
            or path.stat().st_uid != os.getuid()
            or stat.S_IMODE(path.stat().st_mode) != 0o700
        ):
            raise ControlPlaneError("RUNTIME_LAYOUT_INVALID", relative)
    for relative in ("catalogue.sqlite3", "locks/publication.lock"):
        path = runtime_root / relative
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_uid != os.getuid()
            or stat.S_IMODE(path.stat().st_mode) != 0o600
        ):
            raise ControlPlaneError("RUNTIME_FILE_MODE_INVALID", relative)


def _ro_connection(path: Path) -> sqlite3.Connection:
    if path.is_symlink() or not path.is_file():
        raise ControlPlaneError("RELEASE_SQLITE_MISSING")
    uri = "file:" + quote(str(path.resolve(strict=True)), safe="/") + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.DatabaseError as error:
        raise ControlPlaneError("RELEASE_SQLITE_MALFORMED", str(error)) from error


def _metadata(conn: sqlite3.Connection) -> dict[str, Any]:
    expected_keys = {
        "schema_version",
        "release_kind",
        "synthetic_fixture",
        "parent_release_id",
        "parent_release_core_hash",
        "repository_commit",
        "legacy_proof_hash",
        "legacy_audit_proof",
        "source_contract_identities",
        "protected_boundary",
    }
    rows = conn.execute("SELECT key, value FROM release_metadata ORDER BY key").fetchall()
    if {row[0] for row in rows} != expected_keys:
        raise ControlPlaneError("RELEASE_METADATA_SCHEMA_INVALID")
    values: dict[str, Any] = {}
    for key, text in rows:
        parsed = strict_json_load(text, maximum_bytes=256 * 1024)
        if canonical_json(parsed) != text:
            raise ControlPlaneError("RELEASE_METADATA_NONCANONICAL", key)
        values[key] = parsed
    if values["schema_version"] != "1.0" or values["release_kind"] != RELEASE_KIND:
        raise ControlPlaneError("RELEASE_METADATA_INVALID")
    if type(values["synthetic_fixture"]) is not bool:
        raise ControlPlaneError("RELEASE_METADATA_INVALID")
    if values["parent_release_id"] is None:
        if values["parent_release_core_hash"] is not None:
            raise ControlPlaneError("PARENT_LINEAGE_MISMATCH")
    else:
        if type(values["parent_release_id"]) is not str or not values["parent_release_id"].startswith("m99-"):
            raise ControlPlaneError("PARENT_LINEAGE_MISMATCH")
        require_hash(values["parent_release_id"][4:], "parent_release_id")
        require_hash(values["parent_release_core_hash"], "parent_release_core_hash")
    require_git_commit(values["repository_commit"], "repository_commit")
    if values["legacy_proof_hash"] is None:
        if values["legacy_audit_proof"] is not None:
            raise ControlPlaneError("LEGACY_PROOF_METADATA_INVALID")
    else:
        require_hash(values["legacy_proof_hash"], "legacy_proof_hash")
        if not isinstance(values["legacy_audit_proof"], dict):
            raise ControlPlaneError("LEGACY_PROOF_METADATA_INVALID")
        if canonical_hash(values["legacy_audit_proof"]) != values["legacy_proof_hash"]:
            raise ControlPlaneError("LEGACY_PROOF_HASH_MISMATCH")
    if not isinstance(values["source_contract_identities"], list):
        raise ControlPlaneError("SOURCE_CONTRACT_IDENTITIES_INVALID")
    if values["protected_boundary"] != PROTECTED_BOUNDARY:
        raise ControlPlaneError("PROTECTED_BOUNDARY_MISMATCH")
    return values


def _validate_source_contracts(values: list[Any]) -> tuple[dict[str, str], ...]:
    autonomy, mission = load_contracts()
    required = {
        autonomy["contract_id"]: autonomy["contract_hash_sha256"],
        mission["contract_id"]: mission["contract_hash_sha256"],
    }
    identities: list[dict[str, str]] = []
    seen_exact: set[tuple[str, str, str]] = set()
    role_identity: dict[str, tuple[str, str]] = {}
    id_hash: dict[str, str] = {}
    for item in values:
        if (
            type(item) is not dict
            or set(item) != {"contract_id", "contract_hash_sha256", "role"}
        ):
            raise ControlPlaneError("SOURCE_CONTRACT_IDENTITIES_INVALID")
        contract_id = item["contract_id"]
        contract_hash = item["contract_hash_sha256"]
        role = item["role"]
        if type(contract_id) is not str or type(role) is not str:
            raise ControlPlaneError("SOURCE_CONTRACT_IDENTITIES_INVALID")
        require_hash(contract_hash, "source_contract_hash")
        key = (contract_id, contract_hash, role)
        if key in seen_exact:
            raise ControlPlaneError("SOURCE_CONTRACT_IDENTITIES_INVALID")
        seen_exact.add(key)
        identity = (contract_id, contract_hash)
        previous_role = role_identity.get(role)
        if previous_role is not None and previous_role != identity:
            raise ControlPlaneError("SOURCE_CONTRACT_ROLE_CONFLICT")
        previous_hash = id_hash.get(contract_id)
        if previous_hash is not None and previous_hash != contract_hash:
            raise ControlPlaneError("SOURCE_CONTRACT_ID_CONFLICT")
        role_identity[role] = identity
        id_hash[contract_id] = contract_hash
        identities.append(dict(item))
    for contract_id, contract_hash in required.items():
        if id_hash.get(contract_id) != contract_hash:
            raise ControlPlaneError("SOURCE_CONTRACT_LINEAGE_MISMATCH")
    return tuple(
        sorted(
            identities,
            key=lambda item: (
                item["role"],
                item["contract_id"],
                item["contract_hash_sha256"],
            ),
        )
    )


def _validate_source_contract_role_set(
    identities: tuple[dict[str, str], ...],
    *,
    synthetic_fixture: bool,
) -> None:
    current = {"AUTONOMY_CONSTITUTION", "MISSION_99_CONTROL"}
    legacy = current | {
        "MISSION_85_SOURCE_CONTRACT",
        "MISSION_86_SOURCE_MANIFEST",
        "MISSION_87_SOURCE_CERTIFICATE",
    }
    expected = current if synthetic_fixture else legacy
    roles = {item["role"] for item in identities}
    if roles != expected or len(identities) != len(expected):
        raise ControlPlaneError("SOURCE_CONTRACT_ROLE_SET_INVALID")


def _load_receipts(conn: sqlite3.Connection) -> tuple[Any, ...]:
    rows = conn.execute(
        "SELECT receipt_hash, request_id, receipt_kind, source_response_hash, "
        "body_sha256, compressed_object_sha256, receipt_json "
        "FROM acquisition_receipts ORDER BY receipt_hash"
    ).fetchall()
    receipts: list[Any] = []
    seen_request: dict[str, str] = {}
    seen_response: dict[str, str] = {}
    for row in rows:
        receipt_hash, request_id, kind, response_hash, body_hash, object_hash, text = row
        document = strict_json_load(text, maximum_bytes=256 * 1024)
        if not isinstance(document, dict) or canonical_json(document) != text:
            raise ControlPlaneError("RECEIPT_JSON_INVALID")
        receipt = receipt_from_dict(document)
        if (
            receipt.receipt_hash != receipt_hash
            or receipt.request_id != request_id
            or receipt.receipt_kind.value != kind
            or receipt.source_response_hash != response_hash
            or receipt.body_sha256 != body_hash
            or receipt.compressed_object_sha256 != object_hash
        ):
            raise ControlPlaneError("RECEIPT_ROW_MISMATCH")
        previous = seen_request.get(receipt.request_id)
        if previous is not None and previous != receipt.receipt_hash:
            raise ControlPlaneError("RECEIPT_ID_CONFLICT")
        seen_request[receipt.request_id] = receipt.receipt_hash
        previous_response = seen_response.get(receipt.source_response_hash)
        if previous_response is not None and previous_response != receipt.receipt_hash:
            raise ControlPlaneError("SOURCE_RESPONSE_CONFLICT")
        seen_response[receipt.source_response_hash] = receipt.receipt_hash
        receipts.append(receipt)
    return tuple(receipts)


def _load_observations(conn: sqlite3.Connection) -> tuple[ObservationVersion, ...]:
    rows = conn.execute(
        "SELECT record_hash, logical_id, provider, stream, symbol, interval, event_time, "
        "source_time, available_at, availability_class, availability_policy_id, "
        "first_observed_at, last_verified_at, revision_number, supersedes_record_hash, "
        "source_response_hash, receipt_hash, normalizer_id, normalized_payload_json, "
        "clock_health FROM observations ORDER BY logical_id, revision_number, record_hash"
    ).fetchall()
    observations: list[ObservationVersion] = []
    for row in rows:
        payload = strict_json_load(row[18], maximum_bytes=2 * 1024 * 1024)
        if not isinstance(payload, dict) or canonical_json(payload) != row[18]:
            raise ControlPlaneError("NORMALIZED_PAYLOAD_INVALID")
        observation = ObservationVersion.from_dict(
            {
                "record_hash": row[0],
                "logical_id": row[1],
                "provider": row[2],
                "stream": row[3],
                "symbol": row[4],
                "interval": row[5],
                "event_time": row[6],
                "source_time": row[7],
                "available_at": row[8],
                "availability_class": row[9],
                "availability_policy_id": row[10],
                "first_observed_at": row[11],
                "last_verified_at": row[12],
                "revision_number": row[13],
                "supersedes_record_hash": row[14],
                "source_response_hash": row[15],
                "receipt_hash": row[16],
                "normalizer_id": row[17],
                "normalized_payload": payload,
                "clock_health": row[19],
            }
        )
        observations.append(observation)
    return validate_revision_chains(observations)


def _load_warnings(conn: sqlite3.Connection) -> tuple[str, ...]:
    rows = [row[0] for row in conn.execute("SELECT warning FROM warnings ORDER BY warning")]
    for warning in rows:
        if type(warning) is not str or not warning or len(warning) > 256:
            raise ControlPlaneError("WARNING_INVALID")
    if len(rows) != len(set(rows)):
        raise ControlPlaneError("WARNING_INVALID")
    return tuple(rows)


def _load_quarantine(conn: sqlite3.Connection) -> tuple[dict[str, str], ...]:
    rows = conn.execute(
        "SELECT quarantine_hash, reason, evidence_identity FROM quarantine ORDER BY quarantine_hash"
    ).fetchall()
    result: list[dict[str, str]] = []
    for quarantine_hash, reason, evidence_identity in rows:
        require_hash(quarantine_hash, "quarantine_hash")
        if (
            type(reason) is not str
            or type(evidence_identity) is not str
            or not reason
            or not evidence_identity
            or len(reason.encode("utf-8")) > 256
            or len(evidence_identity.encode("utf-8")) > 1024
        ):
            raise ControlPlaneError("QUARANTINE_INVALID")
        core = {"reason": reason, "evidence_identity": evidence_identity}
        if canonical_hash(core) != quarantine_hash:
            raise ControlPlaneError("QUARANTINE_HASH_MISMATCH")
        result.append({"quarantine_hash": quarantine_hash, **core})
    return tuple(result)


def _object_path(runtime_root: Path, object_hash: str) -> Path:
    require_hash(object_hash, "compressed_object_sha256")
    return runtime_root / "objects" / "sha256" / object_hash[:2] / f"{object_hash}.gz"


def _validate_object_refs(
    conn: sqlite3.Connection,
    runtime_root: Path,
    receipts: tuple[Any, ...],
    *,
    maximum_response_bytes: int,
    maximum_decompressed_bytes: int,
    maximum_total_raw_object_bytes: int,
) -> tuple[dict[str, str], ...]:
    rows = conn.execute(
        "SELECT receipt_hash, compressed_object_sha256, body_sha256, source_response_hash "
        "FROM raw_object_refs ORDER BY receipt_hash"
    ).fetchall()
    if len(rows) != len(receipts):
        raise ControlPlaneError("RAW_OBJECT_REFERENCE_COUNT_MISMATCH")
    receipt_map = {receipt.receipt_hash: receipt for receipt in receipts}
    result: list[dict[str, str]] = []
    unique_object_sizes: dict[str, int] = {}
    for receipt_hash, object_hash, body_hash, response_hash in rows:
        receipt = receipt_map.get(receipt_hash)
        if receipt is None:
            raise ControlPlaneError("RAW_OBJECT_RECEIPT_MISSING")
        if (
            receipt.compressed_object_sha256 != object_hash
            or receipt.body_sha256 != body_hash
            or receipt.source_response_hash != response_hash
        ):
            raise ControlPlaneError("RAW_OBJECT_RECEIPT_MISMATCH")
        path = _object_path(runtime_root, object_hash)
        _contained(runtime_root, path)
        if (
            path.stat().st_uid != os.getuid()
            or stat.S_IMODE(path.stat().st_mode) != 0o600
            or path.parent.stat().st_uid != os.getuid()
            or stat.S_IMODE(path.parent.stat().st_mode) != 0o700
        ):
            raise ControlPlaneError("RAW_OBJECT_MODE_INVALID")
        object_size = path.stat().st_size
        if object_size > maximum_response_bytes:
            raise ControlPlaneError("RAW_OBJECT_SIZE_LIMIT")
        raw = read_bounded_regular_file(
            path,
            maximum_bytes=maximum_response_bytes,
            size_reason="RAW_OBJECT_SIZE_LIMIT",
            invalid_reason="RAW_OBJECT_PATH_INVALID",
        )
        unique_object_sizes.setdefault(object_hash, object_size)
        if sum(unique_object_sizes.values()) > maximum_total_raw_object_bytes:
            raise ControlPlaneError("RAW_OBJECT_TOTAL_SIZE_LIMIT")
        if sha256_bytes(raw) != object_hash:
            raise ControlPlaneError("RAW_OBJECT_HASH_MISMATCH")
        body = strict_gzip_body(raw, maximum_decompressed_bytes=maximum_decompressed_bytes)
        if sha256_bytes(body) != body_hash:
            raise ControlPlaneError("RAW_BODY_HASH_MISMATCH")
        result.append(
            {
                "receipt_hash": receipt_hash,
                "compressed_object_sha256": object_hash,
                "body_sha256": body_hash,
                "source_response_hash": response_hash,
            }
        )
    return tuple(result)


def _cross_validate(
    observations: tuple[ObservationVersion, ...],
    receipts: tuple[Any, ...],
    *,
    source_contract_values: list[Any],
    synthetic_fixture: bool,
    repository_commit: str,
) -> None:
    identities = _validate_source_contracts(source_contract_values)
    _validate_source_contract_role_set(
        identities, synthetic_fixture=synthetic_fixture
    )
    by_role = {item["role"]: item for item in identities}
    receipt_map = {receipt.receipt_hash: receipt for receipt in receipts}
    response_map = {receipt.source_response_hash: receipt for receipt in receipts}
    for observation in observations:
        receipt = receipt_map.get(observation.receipt_hash)
        if receipt is None:
            raise ControlPlaneError("OBSERVATION_RECEIPT_MISSING")
        if response_map.get(observation.source_response_hash) is not receipt:
            raise ControlPlaneError("OBSERVATION_RESPONSE_LINK_MISMATCH")
        if observation.source_response_hash != receipt.source_response_hash:
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
            if observation.available_at != receipt.received_at:
                raise ControlPlaneError("OBSERVED_LIVE_RECEIPT_TIME_MISMATCH")
            if observation.first_observed_at != receipt.received_at:
                raise ControlPlaneError("OBSERVED_LIVE_RECEIPT_TIME_MISMATCH")
            if observation.clock_health.value != "HEALTHY" or receipt.clock_health.value != "HEALTHY":
                raise ControlPlaneError("CLOCK_HEALTH_UNTRUSTWORTHY")
        if isinstance(receipt, LegacyAcquisitionReceipt):
            if observation.availability_class is not AvailabilityClass.UNKNOWN:
                raise ControlPlaneError("LEGACY_AVAILABILITY_MUST_BE_UNKNOWN")
            if parse_utc(observation.first_observed_at, "first_observed_at") < parse_utc(
                receipt.captured_at, "legacy_captured_at"
            ):
                raise ControlPlaneError("LEGACY_OBSERVATION_TIME_INVALID")


def _set_inventory(values: list[str]) -> dict[str, Any]:
    canonical = sorted(set(values))
    return {"count": len(canonical), "set_hash": canonical_hash(canonical)}


def _reconstruct_semantic_core(
    *,
    metadata: Mapping[str, Any],
    observations: tuple[ObservationVersion, ...],
    receipts: tuple[Any, ...],
    object_refs: tuple[dict[str, str], ...],
    warnings: tuple[str, ...],
    quarantine: tuple[dict[str, str], ...],
    release_schema_fingerprint: str,
) -> dict[str, Any]:
    records = list(observations)
    event_times = [parse_utc(record.event_time, "event_time") for record in records]
    first_times = [parse_utc(record.first_observed_at, "first_observed_at") for record in records]
    revision_rows = [
        {
            "logical_id": record.logical_id,
            "revision_number": record.revision_number,
            "record_hash": record.record_hash,
            "supersedes_record_hash": record.supersedes_record_hash,
        }
        for record in records
    ]
    logical_ids = {record.logical_id for record in records}
    revisioned_ids = {
        record.logical_id for record in records if record.revision_number > 0
    }
    source_contracts = _validate_source_contracts(
        list(metadata["source_contract_identities"])
    )
    synthetic_fixture = metadata["synthetic_fixture"]
    _validate_source_contract_role_set(
        source_contracts,
        synthetic_fixture=synthetic_fixture,
    )
    if synthetic_fixture:
        if (
            metadata["legacy_proof_hash"] is not None
            or metadata["legacy_audit_proof"] is not None
        ):
            raise ControlPlaneError("SYNTHETIC_LEGACY_PROOF_INVALID")
        if any(not isinstance(receipt, AcquisitionReceipt) for receipt in receipts):
            raise ControlPlaneError("SYNTHETIC_RECEIPT_KIND_INVALID")
    else:
        if (
            metadata["legacy_proof_hash"] is None
            or not isinstance(metadata["legacy_audit_proof"], dict)
            or canonical_hash(metadata["legacy_audit_proof"])
            != metadata["legacy_proof_hash"]
        ):
            raise ControlPlaneError("REAL_RELEASE_LEGACY_PROOF_MISSING")
        if any(not isinstance(receipt, LegacyAcquisitionReceipt) for receipt in receipts):
            raise ControlPlaneError("REAL_RELEASE_RECEIPT_KIND_INVALID")
        if any(
            record.availability_class is not AvailabilityClass.UNKNOWN
            for record in records
        ):
            raise ControlPlaneError("REAL_RELEASE_AVAILABILITY_INVALID")
    return {
        "schema_version": "1.0",
        "release_kind": RELEASE_KIND,
        "synthetic_fixture": metadata["synthetic_fixture"],
        "parent_release_id": metadata["parent_release_id"],
        "parent_release_core_hash": metadata["parent_release_core_hash"],
        "source_contract_identities": list(source_contracts),
        "inventory": {
            "providers": sorted({record.provider for record in records}),
            "streams": sorted({record.stream for record in records}),
            "symbols": sorted({record.symbol for record in records}),
            "intervals": sorted({record.interval for record in records if record.interval is not None}),
        },
        "temporal_coverage": {
            "minimum_event_time": min(record.event_time for record in records) if records else None,
            "maximum_event_time": max(record.event_time for record in records) if records else None,
            "minimum_first_observed_at": min(record.first_observed_at for record in records) if records else None,
            "maximum_first_observed_at": max(record.first_observed_at for record in records) if records else None,
        },
        "raw_response_identities": _set_inventory([receipt.source_response_hash for receipt in receipts]),
        "raw_object_identities": _set_inventory([item["compressed_object_sha256"] for item in object_refs]),
        "acquisition_receipt_identities": _set_inventory([receipt.receipt_hash for receipt in receipts]),
        "normalized_semantic_identities": _set_inventory([record.record_hash for record in records]),
        "availability_policy": {
            "classes": sorted({record.availability_class.value for record in records}),
            "policy_ids": sorted({record.availability_policy_id for record in records}),
        },
        "revision_inventory": {
            "logical_observation_count": len(logical_ids),
            "revisioned_logical_observation_count": len(revisioned_ids),
            "maximum_revision_number": max((record.revision_number for record in records), default=0),
            "chain_hash": canonical_hash(revision_rows),
        },
        "quarantine_inventory": {
            "count": len(quarantine),
            "set_hash": canonical_hash(list(quarantine)),
        },
        "protected_boundary": deep_thaw(metadata["protected_boundary"]),
        "counts": {
            "observation_rows": len(records),
            "receipts": len(receipts),
            "raw_object_references": len(object_refs),
            "warnings": len(warnings),
            "quarantine": len(quarantine),
        },
        "warnings": list(warnings),
        "repository_identity": metadata["repository_commit"],
        "normalizer_identity": sorted({record.normalizer_id for record in records}),
        "legacy_proof_hash": metadata["legacy_proof_hash"],
        "legacy_audit_proof": deep_thaw(metadata["legacy_audit_proof"]),
        "release_schema_fingerprint": release_schema_fingerprint,
    }


def _load_release(
    release_directory: Path,
    runtime_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes, tuple[ObservationVersion, ...], tuple[Any, ...], tuple[dict[str, str], ...], tuple[str, ...], tuple[dict[str, str], ...]]:
    _autonomy, mission = load_contracts()
    bounds = mission["resource_bounds"]
    release_directory = _contained(runtime_root, release_directory)
    if (
        release_directory.stat().st_uid != os.getuid()
        or stat.S_IMODE(release_directory.stat().st_mode) != 0o700
    ):
        raise ControlPlaneError("RELEASE_DIRECTORY_MODE_INVALID")
    entries = list(release_directory.iterdir())
    expected_names = {"manifest.json", "release.sqlite3", "certificate.json"}
    if len(entries) > bounds["maximum_release_files"]:
        raise ControlPlaneError("RELEASE_FILE_COUNT_LIMIT")
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise ControlPlaneError("RELEASE_DIRECTORY_CONTENT_INVALID")
        if entry.name not in expected_names:
            raise ControlPlaneError("RELEASE_DIRECTORY_CONTENT_INVALID")
        if (
            entry.stat().st_uid != os.getuid()
            or stat.S_IMODE(entry.stat().st_mode) != 0o600
        ):
            raise ControlPlaneError("RUNTIME_FILE_MODE_INVALID")
    manifest_path = release_directory / "manifest.json"
    database_path = release_directory / "release.sqlite3"
    if not manifest_path.is_file() or not database_path.is_file():
        raise ControlPlaneError("RELEASE_FILES_MISSING")
    if manifest_path.is_symlink() or database_path.is_symlink():
        raise ControlPlaneError("SYMLINK_REJECTED")
    _contained(runtime_root, release_directory)
    if manifest_path.stat().st_size > 2 * 1024 * 1024:
        raise ControlPlaneError("MANIFEST_SIZE_LIMIT")
    manifest_raw = read_bounded_regular_file(
        manifest_path,
        maximum_bytes=2 * 1024 * 1024,
        size_reason="MANIFEST_SIZE_LIMIT",
        invalid_reason="MANIFEST_FILE_INVALID",
    )
    manifest = strict_json_load(manifest_raw, maximum_bytes=2 * 1024 * 1024)
    if canonical_json(manifest) + "\n" != manifest_raw.decode("utf-8"):
        raise ControlPlaneError("MANIFEST_NONCANONICAL")
    if not isinstance(manifest, dict) or set(manifest) != {"manifest_core", "manifest_core_hash"}:
        raise ControlPlaneError("MANIFEST_SCHEMA_INVALID")
    if not isinstance(manifest["manifest_core"], dict):
        raise ControlPlaneError("MANIFEST_SCHEMA_INVALID")
    if canonical_hash(manifest["manifest_core"]) != manifest["manifest_core_hash"]:
        raise ControlPlaneError("MANIFEST_CORE_HASH_MISMATCH")
    require_hash(manifest["manifest_core_hash"], "manifest_core_hash")
    if database_path.stat().st_size > bounds["maximum_release_sqlite_bytes"]:
        raise ControlPlaneError("RELEASE_SQLITE_SIZE_LIMIT")
    database_raw = read_bounded_regular_file(
        database_path,
        maximum_bytes=bounds["maximum_release_sqlite_bytes"],
        size_reason="RELEASE_SQLITE_SIZE_LIMIT",
        invalid_reason="RELEASE_SQLITE_INVALID",
    )
    conn = _ro_connection(database_path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise ControlPlaneError("RELEASE_SQLITE_INTEGRITY_FAILED")
        schema_fp = verify_exact_schema(conn, "release")
        metadata = _metadata(conn)
        receipts = _load_receipts(conn)
        observations = _load_observations(conn)
        warnings = _load_warnings(conn)
        quarantine = _load_quarantine(conn)
        if len(observations) > bounds["maximum_release_rows"]:
            raise ControlPlaneError("RELEASE_ROW_LIMIT")
        if len(receipts) > bounds["maximum_receipts"]:
            raise ControlPlaneError("RECEIPT_LIMIT")
        if len(warnings) > bounds["maximum_warning_count"]:
            raise ControlPlaneError("WARNING_COUNT_LIMIT")
        if len(quarantine) > bounds["maximum_quarantine_count"]:
            raise ControlPlaneError("QUARANTINE_COUNT_LIMIT")
        object_refs = _validate_object_refs(
            conn,
            runtime_root,
            receipts,
            maximum_response_bytes=bounds["maximum_response_bytes"],
            maximum_decompressed_bytes=bounds["maximum_decompressed_response_bytes"],
            maximum_total_raw_object_bytes=bounds["maximum_total_raw_object_bytes"],
        )
        _cross_validate(
            observations,
            receipts,
            source_contract_values=list(metadata["source_contract_identities"]),
            synthetic_fixture=bool(metadata["synthetic_fixture"]),
            repository_commit=metadata["repository_commit"],
        )
        semantic_core = _reconstruct_semantic_core(
            metadata=metadata,
            observations=observations,
            receipts=receipts,
            object_refs=object_refs,
            warnings=warnings,
            quarantine=quarantine,
            release_schema_fingerprint=schema_fp,
        )
    finally:
        conn.close()
    release_core_hash = canonical_hash(semantic_core)
    release_id = f"m99-{release_core_hash}"
    manifest_core = manifest["manifest_core"]
    expected_manifest_core = {
        "schema_version": "1.0",
        "release_id": release_id,
        "release_core_hash": release_core_hash,
        "release_semantic_core": semantic_core,
        "physical_files": {
            "release.sqlite3": sha256_bytes(database_raw),
        },
    }
    if manifest_core != expected_manifest_core:
        raise ControlPlaneError("MANIFEST_RECONSTRUCTION_MISMATCH")
    return (
        manifest,
        semantic_core,
        manifest_raw,
        database_raw,
        observations,
        receipts,
        object_refs,
        warnings,
        quarantine,
    )


def _verify_parent_catalogue_link(
    *,
    runtime_root: Path,
    parent_release_id: str,
    parent_release_core_hash: str,
    synthetic_fixture: bool,
    legacy_proof_hash: str | None,
) -> None:
    """Independently prove that the named parent is a certified catalogue release."""

    catalogue_path = runtime_root / "catalogue.sqlite3"
    conn = _ro_connection(catalogue_path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise ControlPlaneError("CATALOGUE_SQLITE_INTEGRITY_FAILED")
        fingerprint = verify_exact_schema(conn, "catalogue")
        metadata_rows = conn.execute(
            "SELECT key, value FROM catalogue_metadata ORDER BY key"
        ).fetchall()
        metadata: dict[str, Any] = {}
        for key, text in metadata_rows:
            parsed = strict_json_load(text, maximum_bytes=4096)
            if canonical_json(parsed) != text:
                raise ControlPlaneError("CATALOGUE_METADATA_NONCANONICAL")
            metadata[key] = parsed
        if metadata != {
            "schema_version": "1.0",
            "mission_contract_hash": MISSION_CONTRACT_HASH,
            "autonomy_contract_hash": AUTONOMY_CONTRACT_HASH,
            "schema_fingerprint": fingerprint,
        }:
            raise ControlPlaneError("CATALOGUE_CONTRACT_MISMATCH")
        row = conn.execute(
            "SELECT relative_path,release_core_hash,synthetic_fixture,certified,"
            "release_kind,legacy_proof_hash FROM releases WHERE release_id=?",
            (parent_release_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ControlPlaneError("PARENT_RELEASE_NOT_CATALOGUED")
    if (
        row[0] != f"releases/{parent_release_id}"
        or row[1] != parent_release_core_hash
        or row[2] not in {0, 1}
        or bool(row[2]) != synthetic_fixture
        or row[3] != 1
        or row[4] != RELEASE_KIND
        or row[5] != legacy_proof_hash
    ):
        raise ControlPlaneError("PARENT_CATALOGUE_LINEAGE_MISMATCH")


def _verify_parent_snapshot(
    *,
    semantic_core: Mapping[str, Any],
    observations: tuple[ObservationVersion, ...],
    receipts: tuple[Any, ...],
    warnings: tuple[str, ...],
    quarantine: tuple[dict[str, str], ...],
    runtime_root: Path,
    visited: set[str],
) -> None:
    parent_id = semantic_core["parent_release_id"]
    if parent_id is None:
        return
    if parent_id in visited:
        raise ControlPlaneError("PARENT_LINEAGE_CYCLE")
    visited.add(parent_id)
    _verify_parent_catalogue_link(
        runtime_root=runtime_root,
        parent_release_id=parent_id,
        parent_release_core_hash=semantic_core["parent_release_core_hash"],
        synthetic_fixture=bool(semantic_core["synthetic_fixture"]),
        legacy_proof_hash=semantic_core["legacy_proof_hash"],
    )
    parent_dir = runtime_root / "releases" / parent_id
    parent_certificate, parent_data = _certify_internal(
        parent_dir,
        runtime_root=runtime_root,
        require_certificate=True,
        verify_parent=True,
        visited=visited,
    )
    if parent_certificate.release_core_hash != semantic_core["parent_release_core_hash"]:
        raise ControlPlaneError("PARENT_LINEAGE_MISMATCH")
    parent_observations = {item.record_hash: item.as_dict() for item in parent_data["observations"]}
    child_observations = {item.record_hash: item.as_dict() for item in observations}
    if any(child_observations.get(key) != value for key, value in parent_observations.items()):
        raise ControlPlaneError("PARENT_SNAPSHOT_EVIDENCE_DROPPED")
    parent_receipts = {item.receipt_hash: item.as_dict() for item in parent_data["receipts"]}
    child_receipts = {item.receipt_hash: item.as_dict() for item in receipts}
    if any(child_receipts.get(key) != value for key, value in parent_receipts.items()):
        raise ControlPlaneError("PARENT_SNAPSHOT_EVIDENCE_DROPPED")
    if not set(parent_data["warnings"]).issubset(warnings):
        raise ControlPlaneError("PARENT_SNAPSHOT_EVIDENCE_DROPPED")
    parent_quarantine = {item["quarantine_hash"]: item for item in parent_data["quarantine"]}
    child_quarantine = {item["quarantine_hash"]: item for item in quarantine}
    if any(child_quarantine.get(key) != value for key, value in parent_quarantine.items()):
        raise ControlPlaneError("PARENT_SNAPSHOT_EVIDENCE_DROPPED")
    parent_core = parent_data["semantic_core"]
    if bool(parent_core["synthetic_fixture"]) != bool(semantic_core["synthetic_fixture"]):
        raise ControlPlaneError("LINEAGE_CLASS_MIXING_REJECTED")
    parent_contracts = {
        canonical_json(item) for item in parent_core["source_contract_identities"]
    }
    child_contracts = {
        canonical_json(item) for item in semantic_core["source_contract_identities"]
    }
    if not parent_contracts.issubset(child_contracts):
        raise ControlPlaneError("PARENT_SNAPSHOT_EVIDENCE_DROPPED")
    if not set(parent_core["normalizer_identity"]).issubset(
        set(semantic_core["normalizer_identity"])
    ):
        raise ControlPlaneError("PARENT_SNAPSHOT_EVIDENCE_DROPPED")
    if parent_core["legacy_proof_hash"] is not None and (
        semantic_core["legacy_proof_hash"] != parent_core["legacy_proof_hash"]
        or semantic_core["legacy_audit_proof"] != parent_core["legacy_audit_proof"]
    ):
        raise ControlPlaneError("PARENT_LEGACY_PROOF_CHANGED")


def _certificate_document(
    *,
    release_id: str,
    release_core_hash: str,
    manifest_raw: bytes,
    database_raw: bytes,
    semantic_core: Mapping[str, Any],
) -> dict[str, Any]:
    core = {
        "schema_version": "1.0",
        "release_id": release_id,
        "release_core_hash": release_core_hash,
        "manifest_file_sha256": sha256_bytes(manifest_raw),
        "release_sqlite_sha256": sha256_bytes(database_raw),
        "release_schema_fingerprint": semantic_core["release_schema_fingerprint"],
        "raw_object_set_hash": semantic_core["raw_object_identities"]["set_hash"],
        "row_count": semantic_core["counts"]["observation_rows"],
        "receipt_count": semantic_core["counts"]["receipts"],
        "raw_object_count": semantic_core["raw_object_identities"]["count"],
        "verdict": "CERTIFIED",
    }
    return {
        "certificate_core": core,
        "certificate_core_hash": canonical_hash(core),
    }


def staged_certificate_document(
    release_directory: str | Path,
    *,
    runtime_root: str | Path,
) -> dict[str, Any]:
    """Independently reconstruct staged evidence and return certificate bytes data."""

    certificate, _data = _certify_internal(
        Path(release_directory),
        runtime_root=Path(runtime_root),
        require_certificate=False,
        verify_parent=True,
        visited=set(),
    )
    return certificate


def _certify_internal(
    release_directory: Path,
    *,
    runtime_root: Path,
    require_certificate: bool,
    verify_parent: bool,
    visited: set[str],
) -> tuple[Any, dict[str, Any]]:
    load_contracts()
    if runtime_root.is_symlink():
        raise ControlPlaneError("SYMLINK_REJECTED")
    runtime_root = runtime_root.resolve(strict=True)
    _validate_runtime_layout(runtime_root)
    release_directory = _contained(runtime_root, release_directory)
    if release_directory.parent not in {
        runtime_root / "releases",
        runtime_root / "staging",
    }:
        raise ControlPlaneError("RELEASE_DIRECTORY_LOCATION_INVALID")
    (
        _manifest,
        semantic_core,
        manifest_raw,
        database_raw,
        observations,
        receipts,
        object_refs,
        warnings,
        quarantine,
    ) = _load_release(release_directory, runtime_root)
    release_core_hash = canonical_hash(semantic_core)
    release_id = f"m99-{release_core_hash}"
    if release_directory.parent.name == "releases" and release_directory.name != release_id:
        raise ControlPlaneError("RELEASE_DIRECTORY_ID_MISMATCH")
    if verify_parent:
        _verify_parent_snapshot(
            semantic_core=semantic_core,
            observations=observations,
            receipts=receipts,
            warnings=warnings,
            quarantine=quarantine,
            runtime_root=runtime_root,
            visited=visited,
        )
    document = _certificate_document(
        release_id=release_id,
        release_core_hash=release_core_hash,
        manifest_raw=manifest_raw,
        database_raw=database_raw,
        semantic_core=semantic_core,
    )
    if require_certificate:
        certificate_path = release_directory / "certificate.json"
        if certificate_path.is_symlink() or not certificate_path.is_file():
            raise ControlPlaneError("CERTIFICATE_FILE_MISSING")
        if certificate_path.stat().st_size > 512 * 1024:
            raise ControlPlaneError("CERTIFICATE_SIZE_LIMIT")
        stored_raw = read_bounded_regular_file(
            certificate_path,
            maximum_bytes=512 * 1024,
            size_reason="CERTIFICATE_SIZE_LIMIT",
            invalid_reason="CERTIFICATE_FILE_INVALID",
        )
        stored = strict_json_load(stored_raw, maximum_bytes=512 * 1024)
        if not isinstance(stored, dict) or stored != document:
            raise ControlPlaneError("CERTIFICATE_RECONSTRUCTION_MISMATCH")
        if canonical_json(stored) + "\n" != stored_raw.decode("utf-8"):
            raise ControlPlaneError("CERTIFICATE_NONCANONICAL")
    result = ReleaseCertificate(
        release_id=release_id,
        release_core_hash=release_core_hash,
        certificate_core_hash=document["certificate_core_hash"],
        row_count=len(observations),
        receipt_count=len(receipts),
        raw_object_count=len({item["compressed_object_sha256"] for item in object_refs}),
        verdict="CERTIFIED",
    )
    return (
        document if not require_certificate else result,
        {
            "semantic_core": semantic_core,
            "observations": observations,
            "receipts": receipts,
            "object_refs": object_refs,
            "warnings": warnings,
            "quarantine": quarantine,
        },
    )


def verify_completed_stage(
    release_directory: str | Path,
    *,
    runtime_root: str | Path,
) -> ReleaseCertificate:
    """Verify a staged release after certificate creation without publishing it."""

    directory = Path(release_directory)
    if directory.parent.name != "staging":
        raise ControlPlaneError("STAGING_RELEASE_REQUIRED")
    result, _data = _certify_internal(
        directory,
        runtime_root=Path(runtime_root),
        require_certificate=True,
        verify_parent=True,
        visited=set(),
    )
    if not isinstance(result, ReleaseCertificate):
        raise ControlPlaneError("CERTIFICATE_INTERNAL_FAILURE")
    return result


def certify_release(
    release_directory: str | Path,
    *,
    runtime_root: str | Path | None = None,
) -> ReleaseCertificate:
    """Verify a published release. This function never creates or repairs evidence."""

    directory = Path(release_directory)
    if directory.parent.name != "releases":
        raise ControlPlaneError("PUBLISHED_RELEASE_REQUIRED")
    if runtime_root is None:
        runtime = directory.parent.parent
    else:
        runtime = Path(runtime_root)
    result, _data = _certify_internal(
        directory,
        runtime_root=runtime,
        require_certificate=True,
        verify_parent=True,
        visited=set(),
    )
    if not isinstance(result, ReleaseCertificate):
        raise ControlPlaneError("CERTIFICATE_INTERNAL_FAILURE")
    return result


def load_staged_snapshot(
    release_directory: str | Path,
    *,
    runtime_root: str | Path,
) -> dict[str, Any]:
    """Internal loader for a structurally complete stage before certificate creation."""

    document, data = _certify_internal(
        Path(release_directory),
        runtime_root=Path(runtime_root),
        require_certificate=False,
        verify_parent=True,
        visited=set(),
    )
    if not isinstance(document, dict):
        raise ControlPlaneError("CERTIFICATE_INTERNAL_FAILURE")
    return {"certificate_document": document, **data}


def load_certified_snapshot(
    release_directory: str | Path,
    *,
    runtime_root: str | Path,
) -> dict[str, Any]:
    """Internal read-only loader used by custody and the resolver after certification."""

    result, data = _certify_internal(
        Path(release_directory),
        runtime_root=Path(runtime_root),
        require_certificate=True,
        verify_parent=True,
        visited=set(),
    )
    if not isinstance(result, ReleaseCertificate):
        raise ControlPlaneError("CERTIFICATE_INTERNAL_FAILURE")
    return {"certificate": result, **data}
