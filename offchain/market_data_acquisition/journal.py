"""Secure append-only local journal for Mission 100 forward evidence."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import gzip
import io
import os
from pathlib import Path
import platform
import sqlite3
import ssl
import stat
import subprocess
import sys
import time
from typing import Any, Iterator, Mapping, Sequence
import zlib

from .core import (
    AcquisitionError,
    AVAILABILITY_POLICY_ID,
    BatchStatus,
    FUTURES_HOST,
    INTERVAL,
    INTERVAL_MS,
    NORMALIZER_ID,
    ObservationCandidate,
    ResponseReceipt,
    SPOT_HOST,
    STREAMS,
    SYMBOLS,
    canonical_hash,
    canonical_json,
    deep_thaw,
    load_contracts,
    parse_utc,
    require_commit,
    require_hash,
    sha256_bytes,
    strict_json_load,
    utc_now_ms,
)
from .schema import initialize_schema, verify_schema


DIR_MODE = 0o700
FILE_MODE = 0o600
RUNTIME_SUBDIRS = ("objects", "objects/sha256", "incidents", "locks", "backups")
JOURNAL_NAME = "acquisition.sqlite3"
LOCK_NAME = "locks/acquisition.lock"
MAX_RAW_OBJECT_BYTES = 8 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 8 * 1024 * 1024


def _real(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def validate_runtime_root(root: str | Path, *, repository_root: Path | None = None) -> Path:
    if isinstance(root, str) and root.startswith("~"):
        root = Path(root).expanduser()
    path = Path(root)
    if not path.is_absolute():
        raise AcquisitionError("RUNTIME_ROOT_NOT_ABSOLUTE")
    if path.exists() and path.is_symlink():
        raise AcquisitionError("RUNTIME_ROOT_SYMLINK")
    # Inspect the lexical path before resolve() so an existing symlink in any
    # parent component cannot disappear through canonicalization.
    current = path
    while True:
        if current.exists() and current.is_symlink():
            raise AcquisitionError("RUNTIME_PARENT_SYMLINK")
        if current == current.parent:
            break
        current = current.parent
    resolved = _real(path)
    repo = _real(repository_root or Path(__file__).resolve().parents[2])
    try:
        resolved.relative_to(repo)
    except ValueError:
        pass
    else:
        raise AcquisitionError("RUNTIME_ROOT_INSIDE_REPOSITORY")
    return resolved


def _chmod(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode, follow_symlinks=False)
    except (NotImplementedError, TypeError):
        os.chmod(path, mode)


def _require_private_directory(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise AcquisitionError("RUNTIME_DIRECTORY_INVALID", label)
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != DIR_MODE:
        raise AcquisitionError("RUNTIME_DIRECTORY_MODE_INVALID", f"{label}:{mode:04o}")


def _verify_private_runtime_directories(runtime: Path) -> None:
    _require_private_directory(runtime, ".")
    for relative in RUNTIME_SUBDIRS:
        _require_private_directory(runtime / relative, relative)
    prefix_root = runtime / "objects" / "sha256"
    for child in prefix_root.iterdir():
        if child.is_symlink() or not child.is_dir():
            raise AcquisitionError("RAW_OBJECT_DIRECTORY_INVALID", child.name)
        _require_private_directory(child, f"objects/sha256/{child.name}")


def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _decompress_gzip_bounded(compressed: bytes, *, maximum_bytes: int) -> bytes:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
            body = stream.read(maximum_bytes + 1)
            if len(body) > maximum_bytes:
                raise AcquisitionError("RAW_OBJECT_DECOMPRESSED_LIMIT")
            # Force trailer validation and reject concatenated/trailing payload that
            # would otherwise hide bytes outside the bounded logical response.
            extra = stream.read(1)
            if extra:
                raise AcquisitionError("RAW_OBJECT_DECOMPRESSED_LIMIT")
            return body
    except AcquisitionError:
        raise
    except (OSError, EOFError) as error:
        raise AcquisitionError("RAW_OBJECT_GZIP_INVALID") from error


def _write_no_clobber(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, FILE_MODE)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    _chmod(path, FILE_MODE)
    _fsync_dir(path.parent)


def repository_identity(repository_root: Path | None = None) -> str:
    root = repository_root or Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise AcquisitionError("REPOSITORY_IDENTITY_UNAVAILABLE") from error
    require_commit(commit, "repository_commit")
    if dirty:
        raise AcquisitionError("REPOSITORY_NOT_CLEAN")
    return commit


def environment_identity() -> dict[str, str]:
    value = {
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "openssl": ssl.OPENSSL_VERSION,
        "zlib": zlib.ZLIB_VERSION,
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
    }
    return value



RECEIPT_ENDPOINTS: dict[tuple[str, str], tuple[str, frozenset[str]]] = {
    (SPOT_HOST, "/api/v3/time"): ("spot_time", frozenset()),
    (SPOT_HOST, "/api/v3/klines"): (
        "spot_ohlcv",
        frozenset({"symbol", "interval", "startTime", "endTime", "limit"}),
    ),
    (FUTURES_HOST, "/fapi/v1/time"): ("futures_time", frozenset()),
    (FUTURES_HOST, "/fapi/v1/klines"): (
        "perpetual_ohlcv",
        frozenset({"symbol", "interval", "startTime", "endTime", "limit"}),
    ),
    (FUTURES_HOST, "/fapi/v1/markPriceKlines"): (
        "mark_price_ohlcv",
        frozenset({"symbol", "interval", "startTime", "endTime", "limit"}),
    ),
    (FUTURES_HOST, "/fapi/v1/indexPriceKlines"): (
        "index_price_ohlcv",
        frozenset({"pair", "interval", "startTime", "endTime", "limit"}),
    ),
    (FUTURES_HOST, "/fapi/v1/fundingRate"): (
        "funding_rates",
        frozenset({"symbol", "startTime", "endTime", "limit"}),
    ),
    (FUTURES_HOST, "/fapi/v1/fundingInfo"): ("funding_info", frozenset()),
}
ALLOWED_RECEIPT_HEADERS = {
    "date",
    "retry-after",
    "content-type",
    "content-length",
}
ENVIRONMENT_KEYS = {
    "python",
    "sqlite",
    "openssl",
    "zlib",
    "system",
    "release",
    "machine",
}
MAX_LOGICAL_REQUESTS_PER_CAPTURE = 18
MAX_HTTP_RECEIPTS_PER_CAPTURE = 60


def _timestamp_ms(value: str, field: str) -> int:
    return int(parse_utc(value, field).timestamp() * 1000)


def _validate_receipt_semantics(receipt: ResponseReceipt) -> str:
    endpoint = RECEIPT_ENDPOINTS.get((receipt.host, receipt.path))
    if endpoint is None:
        raise AcquisitionError("RECEIPT_ENDPOINT_NOT_ALLOWED")
    endpoint_name, expected_params = endpoint
    params = deep_thaw(receipt.params)
    if not isinstance(params, dict) or set(params) != set(expected_params):
        raise AcquisitionError("RECEIPT_PARAMETER_SCHEMA_MISMATCH", endpoint_name)

    symbol = params.get("symbol")
    pair = params.get("pair")
    if symbol is not None and (type(symbol) is not str or symbol not in SYMBOLS):
        raise AcquisitionError("RECEIPT_SYMBOL_NOT_ALLOWED")
    if pair is not None and (type(pair) is not str or pair not in SYMBOLS):
        raise AcquisitionError("RECEIPT_SYMBOL_NOT_ALLOWED")
    if "interval" in params and params["interval"] != INTERVAL:
        raise AcquisitionError("RECEIPT_INTERVAL_NOT_ALLOWED")
    for key in ("startTime", "endTime", "limit"):
        if key in params and type(params[key]) is not int:
            raise AcquisitionError("RECEIPT_PARAMETER_TYPE_INVALID", key)
    if "startTime" in params and "endTime" in params:
        start = params["startTime"]
        end = params["endTime"]
        if start < 0 or end < start or end - start > 168 * INTERVAL_MS:
            raise AcquisitionError("RECEIPT_TIME_RANGE_INVALID")
    if "limit" in params and not 1 <= params["limit"] <= 1000:
        raise AcquisitionError("RECEIPT_LIMIT_INVALID")

    headers = deep_thaw(receipt.headers)
    if not isinstance(headers, dict) or len(headers) > 16:
        raise AcquisitionError("RECEIPT_HEADER_SCHEMA_INVALID")
    for key, value in headers.items():
        if type(key) is not str or key != key.lower():
            raise AcquisitionError("RECEIPT_HEADER_SCHEMA_INVALID")
        if key not in ALLOWED_RECEIPT_HEADERS and not key.startswith("x-mbx-used-weight-"):
            raise AcquisitionError("RECEIPT_HEADER_NOT_ALLOWED", key)
        if type(value) is not str or len(value.encode("utf-8")) > 1024:
            raise AcquisitionError("RECEIPT_HEADER_SCHEMA_INVALID")

    if _timestamp_ms(receipt.requested_at, "requested_at") != receipt.wall_start_ms:
        raise AcquisitionError("RECEIPT_WALL_START_MISMATCH")
    if _timestamp_ms(receipt.received_at, "received_at") != receipt.wall_end_ms:
        raise AcquisitionError("RECEIPT_WALL_END_MISMATCH")
    wall_elapsed = receipt.wall_end_ms - receipt.wall_start_ms
    if abs(wall_elapsed - receipt.monotonic_duration_ms) > 1_000:
        raise AcquisitionError("RECEIPT_CLOCK_DRIFT_INVALID")

    expected_response_hash = canonical_hash(
        {
            "method": "GET",
            "host": receipt.host,
            "path": receipt.path,
            "params": params,
            "body_sha256": receipt.body_sha256,
        }
    )
    if receipt.response_hash != expected_response_hash:
        raise AcquisitionError("RECEIPT_RESPONSE_HASH_MISMATCH")

    if endpoint_name in {"spot_time", "futures_time"}:
        if receipt.clock_status.value != "UNKNOWN":
            raise AcquisitionError("CLOCK_RECEIPT_STATUS_INVALID")
    elif receipt.clock_status.value != "HEALTHY":
        raise AcquisitionError("DATA_RECEIPT_CLOCK_NOT_HEALTHY")
    return endpoint_name

def _connect(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        from urllib.parse import quote
        uri = f"file:{quote(str(path))}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA query_only=ON")
    else:
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=2000")
    if not readonly:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=FULL")
    return conn


def initialize_runtime(root: str | Path) -> dict[str, str]:
    load_contracts()
    runtime = validate_runtime_root(root)
    if runtime.exists() and any(runtime.iterdir()):
        raise AcquisitionError("RUNTIME_NOT_EMPTY")
    runtime.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    _chmod(runtime, DIR_MODE)
    for relative in RUNTIME_SUBDIRS:
        path = runtime / relative
        path.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
        _chmod(path, DIR_MODE)
    db_path = runtime / JOURNAL_NAME
    conn = _connect(db_path)
    try:
        fingerprint = initialize_schema(conn)
        _, _, _, contract = load_contracts()
        now, _ = utc_now_ms()
        metadata = {
            "schema_fingerprint": fingerprint,
            "mission100_contract_hash": str(contract["contract_hash_sha256"]),
            "created_at": now,
        }
        conn.executemany(
            "INSERT INTO metadata(key,value) VALUES (?,?)",
            sorted(metadata.items()),
        )
        conn.commit()
    finally:
        conn.close()
    _chmod(db_path, FILE_MODE)
    _fsync_dir(runtime)
    return {"runtime_root": str(runtime), "schema_fingerprint": fingerprint}


@contextmanager
def acquisition_lock(root: Path, *, timeout_seconds: float = 2.0) -> Iterator[None]:
    lock_path = root / LOCK_NAME
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(lock_path, flags, FILE_MODE)
    _chmod(lock_path, FILE_MODE)
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise AcquisitionError("ACQUISITION_LOCK_BUSY")
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


@dataclass
class Journal:
    root: Path
    conn: sqlite3.Connection
    schema_fingerprint: str

    @classmethod
    def open(cls, root: str | Path, *, readonly: bool = False) -> "Journal":
        load_contracts()
        runtime = validate_runtime_root(root)
        _verify_private_runtime_directories(runtime)
        db = runtime / JOURNAL_NAME
        if not db.is_file() or db.is_symlink():
            raise AcquisitionError("JOURNAL_MISSING")
        conn = _connect(db, readonly=readonly)
        try:
            metadata = {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM metadata")}
            expected = metadata.get("schema_fingerprint")
            if not expected:
                raise AcquisitionError("JOURNAL_SCHEMA_FINGERPRINT_MISSING")
            fingerprint = verify_schema(conn, expected)
            _, _, _, contract = load_contracts()
            if metadata.get("mission100_contract_hash") != contract["contract_hash_sha256"]:
                raise AcquisitionError("JOURNAL_CONTRACT_HASH_MISMATCH")
        except Exception:
            conn.close()
            raise
        return cls(runtime, conn, fingerprint)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def begin_batch(self, batch_id: str, contract_hash: str, code_commit: str) -> None:
        require_hash(contract_hash, "contract_hash")
        require_commit(code_commit, "code_commit")
        now, _ = utc_now_ms()
        env = environment_identity()
        env_json = canonical_json(env)
        env_hash = canonical_hash(env)
        self.conn.execute(
            "INSERT INTO capture_batches(batch_id,contract_hash,code_commit,started_at,status,environment_json,environment_hash) "
            "VALUES (?,?,?,?,?,?,?)",
            (batch_id, contract_hash, code_commit, now, BatchStatus.RUNNING.value, env_json, env_hash),
        )
        self.conn.commit()

    def mark_failed(
        self,
        batch_id: str,
        reason: str,
        *,
        request_count: int = 0,
        receipt_count: int = 0,
    ) -> None:
        del request_count, receipt_count
        now, _ = utc_now_ms()
        actual_receipts = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM receipts WHERE batch_id=?", (batch_id,)
            ).fetchone()[0]
        )
        actual_requests = int(
            self.conn.execute(
                "SELECT COUNT(DISTINCT request_id) FROM receipts WHERE batch_id=?",
                (batch_id,),
            ).fetchone()[0]
        )
        actual_observations = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM observations WHERE batch_id=?", (batch_id,)
            ).fetchone()[0]
        )
        if actual_observations:
            raise AcquisitionError("FAILED_BATCH_OBSERVATION_PRESENT")
        self.conn.execute(
            "UPDATE capture_batches SET completed_at=?,status=?,request_count=?,receipt_count=?,observation_count=0,error_reason=? "
            "WHERE batch_id=? AND status=?",
            (
                now,
                BatchStatus.FAILED.value,
                actual_requests,
                actual_receipts,
                reason[:256],
                batch_id,
                BatchStatus.RUNNING.value,
            ),
        )
        self.conn.commit()

    def store_raw_body(self, body: bytes, *, created_at: str) -> tuple[str, str, str]:
        if len(body) > MAX_DECOMPRESSED_BYTES:
            raise AcquisitionError("RESPONSE_BODY_LIMIT")
        body_hash = sha256_bytes(body)
        compressed = gzip.compress(body, mtime=0)
        if len(compressed) > MAX_RAW_OBJECT_BYTES:
            raise AcquisitionError("COMPRESSED_OBJECT_LIMIT")
        object_hash = sha256_bytes(compressed)
        relative = f"objects/sha256/{object_hash[:2]}/{object_hash}.gz"
        path = self.root / relative
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
        _chmod(parent, DIR_MODE)
        if path.exists():
            if path.is_symlink() or path.stat().st_size > MAX_RAW_OBJECT_BYTES:
                raise AcquisitionError("RAW_OBJECT_CONFLICT")
            if path.read_bytes() != compressed:
                raise AcquisitionError("RAW_OBJECT_CONFLICT")
        else:
            _write_no_clobber(path, compressed)
        self.conn.execute(
            "INSERT OR IGNORE INTO raw_objects(object_sha256,body_sha256,compressed_bytes,decompressed_bytes,relative_path,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (object_hash, body_hash, len(compressed), len(body), relative, created_at),
        )
        row = self.conn.execute(
            "SELECT body_sha256,relative_path FROM raw_objects WHERE object_sha256=?", (object_hash,)
        ).fetchone()
        if row is None or row["body_sha256"] != body_hash or row["relative_path"] != relative:
            raise AcquisitionError("RAW_OBJECT_REGISTRY_CONFLICT")
        return body_hash, object_hash, relative

    def add_receipt(self, batch_id: str, receipt: ResponseReceipt) -> None:
        self.conn.execute(
            "INSERT INTO receipts(receipt_hash,batch_id,request_id,host,path,params_json,requested_at,received_at,wall_start_ms,wall_end_ms,"
            "monotonic_duration_ms,clock_status,http_status,headers_json,attempt_number,retry_exhausted,body_sha256,object_sha256,response_hash) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                receipt.receipt_hash,
                batch_id,
                receipt.request_id,
                receipt.host,
                receipt.path,
                canonical_json(receipt.params),
                receipt.requested_at,
                receipt.received_at,
                receipt.wall_start_ms,
                receipt.wall_end_ms,
                receipt.monotonic_duration_ms,
                receipt.clock_status.value,
                receipt.http_status,
                canonical_json(receipt.headers),
                receipt.attempt_number,
                1 if receipt.retry_exhausted else 0,
                receipt.body_sha256,
                receipt.object_sha256,
                receipt.response_hash,
            ),
        )

    def latest_successful_observation(self, logical_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT o.* FROM observations o JOIN capture_batches b ON b.batch_id=o.batch_id "
            "WHERE o.logical_id=? AND b.status='COMPLETE' ORDER BY o.revision_number DESC LIMIT 1",
            (logical_id,),
        ).fetchone()

    def add_observation(self, batch_id: str, candidate: ObservationCandidate) -> tuple[str, bool]:
        latest = self.latest_successful_observation(candidate.logical_id)
        payload_json = canonical_json(candidate.payload)
        payload_hash = candidate.payload_hash
        if latest is not None and latest["payload_hash"] == payload_hash:
            return str(latest["record_hash"]), False
        revision = 1 if latest is None else int(latest["revision_number"]) + 1
        supersedes = None if latest is None else str(latest["record_hash"])
        core = {
            "logical_id": candidate.logical_id,
            "revision_number": revision,
            "supersedes_record_hash": supersedes,
            "batch_id": batch_id,
            "receipt_hash": candidate.receipt_hash,
            "stream": candidate.stream,
            "symbol": candidate.symbol,
            "interval": candidate.interval,
            "event_time_ms": candidate.event_time_ms,
            "available_at": candidate.available_at,
            "response_hash": candidate.response_hash,
            "payload_hash": payload_hash,
        }
        record_hash = canonical_hash(core)
        self.conn.execute(
            "INSERT INTO observations(record_hash,logical_id,revision_number,supersedes_record_hash,batch_id,receipt_hash,stream,symbol,interval,event_time_ms,"
            "available_at,response_hash,payload_json,payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                record_hash,
                candidate.logical_id,
                revision,
                supersedes,
                batch_id,
                candidate.receipt_hash,
                candidate.stream,
                candidate.symbol,
                candidate.interval,
                candidate.event_time_ms,
                candidate.available_at,
                candidate.response_hash,
                payload_json,
                payload_hash,
            ),
        )
        return record_hash, True

    def checkpoint(self, stream: str, symbol: str) -> int | None:
        row = self.conn.execute(
            "SELECT next_event_time_ms FROM checkpoints WHERE stream=? AND symbol=?", (stream, symbol)
        ).fetchone()
        return None if row is None else int(row[0])

    def finish_batch(
        self,
        batch_id: str,
        *,
        checkpoint_updates: Mapping[tuple[str, str], int],
        request_count: int,
        receipt_count: int,
        observation_count: int,
    ) -> None:
        now, _ = utc_now_ms()
        for (stream, symbol), next_event in sorted(checkpoint_updates.items()):
            if stream not in STREAMS or symbol not in SYMBOLS:
                raise AcquisitionError("CHECKPOINT_KEY_INVALID")
            if type(next_event) is not int or next_event < 0 or next_event % INTERVAL_MS != 0:
                raise AcquisitionError("CHECKPOINT_VALUE_INVALID")
            previous = self.checkpoint(stream, symbol)
            if previous is not None and next_event < previous:
                raise AcquisitionError("CHECKPOINT_REGRESSION")
            self.conn.execute(
                "INSERT INTO checkpoints(stream,symbol,next_event_time_ms,last_success_batch_id,updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(stream,symbol) DO UPDATE SET next_event_time_ms=excluded.next_event_time_ms,last_success_batch_id=excluded.last_success_batch_id,updated_at=excluded.updated_at",
                (stream, symbol, int(next_event), batch_id, now),
            )
        self.conn.execute(
            "UPDATE capture_batches SET completed_at=?,status='COMPLETE',request_count=?,receipt_count=?,observation_count=?,error_reason=NULL "
            "WHERE batch_id=? AND status='RUNNING'",
            (now, request_count, receipt_count, observation_count, batch_id),
        )
        self.conn.commit()
        fd = os.open(self.root / JOURNAL_NAME, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_dir(self.root)


def verify_journal(root: str | Path, *, scan_objects: bool = True) -> dict[str, Any]:
    _, _, _, contract = load_contracts()
    runtime = validate_runtime_root(root)
    with Journal.open(runtime, readonly=True) as journal:
        conn = journal.conn
        counts = {
            name: int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
            for name in ("capture_batches", "raw_objects", "receipts", "observations", "checkpoints", "funding_configs")
        }
        bad_running = int(conn.execute("SELECT COUNT(*) FROM capture_batches WHERE status='RUNNING'").fetchone()[0])
        if bad_running:
            raise AcquisitionError("INCOMPLETE_CAPTURE_BATCH_PRESENT")

        current_contract_hash = str(contract["contract_hash_sha256"])
        for batch in conn.execute("SELECT * FROM capture_batches ORDER BY batch_id"):
            if batch["contract_hash"] != current_contract_hash:
                raise AcquisitionError("BATCH_CONTRACT_HASH_MISMATCH")
            require_commit(batch["code_commit"], "batch_code_commit")
            require_hash(batch["environment_hash"], "batch_environment_hash")
            environment = strict_json_load(batch["environment_json"])
            if not isinstance(environment, Mapping) or set(environment) != ENVIRONMENT_KEYS:
                raise AcquisitionError("BATCH_ENVIRONMENT_SCHEMA_INVALID")
            if not all(type(value) is str and value for value in environment.values()):
                raise AcquisitionError("BATCH_ENVIRONMENT_SCHEMA_INVALID")
            if canonical_hash(environment) != batch["environment_hash"]:
                raise AcquisitionError("BATCH_ENVIRONMENT_HASH_MISMATCH")
            started = parse_utc(batch["started_at"], "batch_started_at")
            completed_at = batch["completed_at"]
            if type(completed_at) is not str:
                raise AcquisitionError("BATCH_COMPLETION_TIMESTAMP_MISSING")
            completed = parse_utc(completed_at, "batch_completed_at")
            if completed < started:
                raise AcquisitionError("BATCH_TIME_REGRESSION")
            if batch["status"] not in {BatchStatus.COMPLETE.value, BatchStatus.FAILED.value}:
                raise AcquisitionError("BATCH_STATUS_INVALID")
            actual_receipts = int(
                conn.execute(
                    "SELECT COUNT(*) FROM receipts WHERE batch_id=?", (batch["batch_id"],)
                ).fetchone()[0]
            )
            actual_requests = int(
                conn.execute(
                    "SELECT COUNT(DISTINCT request_id) FROM receipts WHERE batch_id=?",
                    (batch["batch_id"],),
                ).fetchone()[0]
            )
            actual_observations = int(
                conn.execute(
                    "SELECT COUNT(*) FROM observations WHERE batch_id=?", (batch["batch_id"],)
                ).fetchone()[0]
            )
            if int(batch["receipt_count"]) != actual_receipts:
                raise AcquisitionError("BATCH_RECEIPT_COUNT_MISMATCH")
            if int(batch["request_count"]) != actual_requests:
                raise AcquisitionError("BATCH_REQUEST_COUNT_MISMATCH")
            if int(batch["observation_count"]) != actual_observations:
                raise AcquisitionError("BATCH_OBSERVATION_COUNT_MISMATCH")
            if actual_requests > MAX_LOGICAL_REQUESTS_PER_CAPTURE:
                raise AcquisitionError("BATCH_REQUEST_LIMIT_EXCEEDED")
            if actual_receipts > MAX_HTTP_RECEIPTS_PER_CAPTURE:
                raise AcquisitionError("BATCH_RECEIPT_LIMIT_EXCEEDED")
            if batch["status"] == BatchStatus.COMPLETE.value:
                if batch["error_reason"] is not None:
                    raise AcquisitionError("COMPLETE_BATCH_ERROR_REASON_PRESENT")
            else:
                if actual_observations:
                    raise AcquisitionError("FAILED_BATCH_OBSERVATION_PRESENT")
                if type(batch["error_reason"]) is not str or not batch["error_reason"]:
                    raise AcquisitionError("FAILED_BATCH_ERROR_REASON_MISSING")

        orphan_object_count = 0
        if scan_objects:
            registered_paths: set[str] = set()
            for row in conn.execute("SELECT * FROM raw_objects ORDER BY object_sha256"):
                relative = Path(row["relative_path"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise AcquisitionError("RAW_OBJECT_PATH_INVALID")
                registered_paths.add(relative.as_posix())
                path = runtime / relative
                if not path.is_file() or path.is_symlink():
                    raise AcquisitionError("RAW_OBJECT_MISSING")
                if path.stat().st_size > MAX_RAW_OBJECT_BYTES:
                    raise AcquisitionError("RAW_OBJECT_SIZE_LIMIT")
                compressed = path.read_bytes()
                if sha256_bytes(compressed) != row["object_sha256"]:
                    raise AcquisitionError("RAW_OBJECT_HASH_MISMATCH")
                body = _decompress_gzip_bounded(
                    compressed, maximum_bytes=MAX_DECOMPRESSED_BYTES
                )
                if len(body) != row["decompressed_bytes"] or sha256_bytes(body) != row["body_sha256"]:
                    raise AcquisitionError("RAW_OBJECT_BODY_MISMATCH")
            object_root = runtime / "objects" / "sha256"
            physical_paths: set[str] = set()
            if object_root.exists():
                for path in object_root.rglob("*"):
                    if path.is_symlink():
                        raise AcquisitionError("RAW_OBJECT_SYMLINK")
                    if path.is_file():
                        relative = path.relative_to(runtime).as_posix()
                        if not relative.endswith(".gz"):
                            raise AcquisitionError("RAW_OBJECT_UNEXPECTED_FILE", relative)
                        physical_paths.add(relative)
            missing_registered = registered_paths - physical_paths
            if missing_registered:
                raise AcquisitionError("RAW_OBJECT_MISSING", repr(sorted(missing_registered)[:3]))
            orphan_object_count = len(physical_paths - registered_paths)
        object_rows = {
            row["object_sha256"]: row
            for row in conn.execute("SELECT * FROM raw_objects")
        }
        receipt_hashes: set[str] = set()
        receipt_endpoints: dict[str, str] = {}
        for row in conn.execute("SELECT * FROM receipts ORDER BY receipt_hash"):
            params = strict_json_load(row["params_json"])
            headers = strict_json_load(row["headers_json"])
            if not isinstance(params, Mapping) or not isinstance(headers, Mapping):
                raise AcquisitionError("RECEIPT_JSON_SHAPE_INVALID")
            receipt = ResponseReceipt(
                request_id=row["request_id"],
                host=row["host"],
                path=row["path"],
                params=params,
                requested_at=row["requested_at"],
                received_at=row["received_at"],
                wall_start_ms=row["wall_start_ms"],
                wall_end_ms=row["wall_end_ms"],
                monotonic_duration_ms=row["monotonic_duration_ms"],
                clock_status=row["clock_status"],
                http_status=row["http_status"],
                headers=headers,
                attempt_number=row["attempt_number"],
                retry_exhausted=bool(row["retry_exhausted"]),
                body_sha256=row["body_sha256"],
                object_sha256=row["object_sha256"],
                response_hash=row["response_hash"],
                receipt_hash=row["receipt_hash"],
            )
            endpoint_name = _validate_receipt_semantics(receipt)
            object_row = object_rows.get(receipt.object_sha256)
            if object_row is None or object_row["body_sha256"] != receipt.body_sha256:
                raise AcquisitionError("RECEIPT_RAW_OBJECT_MISMATCH")
            receipt_hashes.add(receipt.receipt_hash)
            receipt_endpoints[receipt.receipt_hash] = endpoint_name

        bad_observation_batches = int(
            conn.execute(
                "SELECT COUNT(*) FROM observations o JOIN capture_batches b ON b.batch_id=o.batch_id "
                "WHERE b.status!='COMPLETE'"
            ).fetchone()[0]
        )
        if bad_observation_batches:
            raise AcquisitionError("FAILED_BATCH_OBSERVATION_PRESENT")

        for row in conn.execute(
            "SELECT o.*,r.response_hash AS receipt_response_hash,r.received_at AS receipt_received_at,"
            "r.clock_status AS receipt_clock_status,r.params_json AS receipt_params_json "
            "FROM observations o JOIN receipts r ON r.receipt_hash=o.receipt_hash"
        ):
            if row["receipt_hash"] not in receipt_hashes:
                raise AcquisitionError("OBSERVATION_RECEIPT_MISSING")
            if row["response_hash"] != row["receipt_response_hash"]:
                raise AcquisitionError("OBSERVATION_RESPONSE_MISMATCH")
            if row["available_at"] != row["receipt_received_at"]:
                raise AcquisitionError("OBSERVATION_AVAILABILITY_MISMATCH")
            if row["receipt_clock_status"] != "HEALTHY":
                raise AcquisitionError("OBSERVATION_RECEIPT_CLOCK_NOT_HEALTHY")
            if _timestamp_ms(row["available_at"], "observation_available_at") < int(row["event_time_ms"]):
                raise AcquisitionError("OBSERVATION_AVAILABLE_BEFORE_EVENT")
            expected_endpoint = row["stream"]
            if receipt_endpoints.get(row["receipt_hash"]) != expected_endpoint:
                raise AcquisitionError("OBSERVATION_ENDPOINT_MISMATCH")
            receipt_params = strict_json_load(row["receipt_params_json"])
            identity_key = "pair" if row["stream"] == "index_price_ohlcv" else "symbol"
            if not isinstance(receipt_params, Mapping) or receipt_params.get(identity_key) != row["symbol"]:
                raise AcquisitionError("OBSERVATION_REQUEST_IDENTITY_MISMATCH")
            payload = strict_json_load(row["payload_json"])
            if canonical_hash(payload) != row["payload_hash"]:
                raise AcquisitionError("OBSERVATION_PAYLOAD_HASH_MISMATCH")
            if not isinstance(payload, Mapping):
                raise AcquisitionError("OBSERVATION_PAYLOAD_SCHEMA_INVALID")
            if payload.get("normalizer_id") != NORMALIZER_ID or payload.get("availability_policy_id") != AVAILABILITY_POLICY_ID:
                raise AcquisitionError("OBSERVATION_POLICY_IDENTITY_MISMATCH")
            if row["stream"] == "funding_rates":
                if payload.get("funding_time_ms") != row["event_time_ms"]:
                    raise AcquisitionError("FUNDING_EVENT_TIME_MISMATCH")
            else:
                if payload.get("close_time_ms") != row["event_time_ms"]:
                    raise AcquisitionError("BAR_EVENT_TIME_MISMATCH")
                if type(payload.get("open_time_ms")) is not int or payload["open_time_ms"] > row["event_time_ms"]:
                    raise AcquisitionError("BAR_EVENT_TIME_MISMATCH")
            logical_id = canonical_hash(
                {
                    "stream": row["stream"],
                    "symbol": row["symbol"],
                    "interval": row["interval"],
                    "event_time_ms": row["event_time_ms"],
                }
            )
            if row["logical_id"] != logical_id:
                raise AcquisitionError("OBSERVATION_LOGICAL_ID_MISMATCH")
            record_core = {
                "logical_id": row["logical_id"],
                "revision_number": row["revision_number"],
                "supersedes_record_hash": row["supersedes_record_hash"],
                "batch_id": row["batch_id"],
                "receipt_hash": row["receipt_hash"],
                "stream": row["stream"],
                "symbol": row["symbol"],
                "interval": row["interval"],
                "event_time_ms": row["event_time_ms"],
                "available_at": row["available_at"],
                "response_hash": row["response_hash"],
                "payload_hash": row["payload_hash"],
            }
            if canonical_hash(record_core) != row["record_hash"]:
                raise AcquisitionError("OBSERVATION_RECORD_HASH_MISMATCH")

        for row in conn.execute("SELECT * FROM funding_configs"):
            payload = strict_json_load(row["payload_json"])
            if canonical_hash(payload) != row["payload_hash"]:
                raise AcquisitionError("FUNDING_CONFIG_HASH_MISMATCH")
            if row["receipt_hash"] not in receipt_hashes:
                raise AcquisitionError("FUNDING_CONFIG_RECEIPT_MISSING")
            if receipt_endpoints.get(row["receipt_hash"]) != "funding_info":
                raise AcquisitionError("FUNDING_CONFIG_ENDPOINT_MISMATCH")
            receipt_row = conn.execute(
                "SELECT received_at,clock_status FROM receipts WHERE receipt_hash=?",
                (row["receipt_hash"],),
            ).fetchone()
            if receipt_row is None or receipt_row["clock_status"] != "HEALTHY":
                raise AcquisitionError("FUNDING_CONFIG_RECEIPT_INVALID")
            if row["observed_at"] != receipt_row["received_at"]:
                raise AcquisitionError("FUNDING_CONFIG_OBSERVED_AT_MISMATCH")
            if not isinstance(payload, Mapping):
                raise AcquisitionError("FUNDING_CONFIG_PAYLOAD_SCHEMA_INVALID")
            if payload.get("symbol") != row["symbol"]:
                raise AcquisitionError("FUNDING_CONFIG_SYMBOL_MISMATCH")
            if payload.get("funding_interval_hours") != row["funding_interval_hours"]:
                raise AcquisitionError("FUNDING_CONFIG_INTERVAL_MISMATCH")
            if payload.get("funding_rate_cap") != row["funding_rate_cap"] or payload.get("funding_rate_floor") != row["funding_rate_floor"]:
                raise AcquisitionError("FUNDING_CONFIG_BOUND_MISMATCH")

        bad_checkpoints = int(
            conn.execute(
                "SELECT COUNT(*) FROM checkpoints c JOIN capture_batches b ON b.batch_id=c.last_success_batch_id "
                "WHERE b.status!='COMPLETE'"
            ).fetchone()[0]
        )
        if bad_checkpoints:
            raise AcquisitionError("CHECKPOINT_FAILED_BATCH_REFERENCE")
        checkpoint_rows = conn.execute(
            "SELECT stream,symbol,next_event_time_ms FROM checkpoints"
        ).fetchall()
        checkpoint_keys = {(row["stream"], row["symbol"]) for row in checkpoint_rows}
        expected_checkpoint_keys = {(stream, symbol) for stream in STREAMS for symbol in SYMBOLS}
        completed_batches = int(
            conn.execute("SELECT COUNT(*) FROM capture_batches WHERE status='COMPLETE'").fetchone()[0]
        )
        if completed_batches and checkpoint_keys != expected_checkpoint_keys:
            raise AcquisitionError("CHECKPOINT_SET_INCOMPLETE")
        if not completed_batches and checkpoint_keys:
            raise AcquisitionError("CHECKPOINT_WITHOUT_COMPLETE_BATCH")
        for row in checkpoint_rows:
            value = row["next_event_time_ms"]
            if type(value) is not int or value < 0 or value % INTERVAL_MS != 0:
                raise AcquisitionError("CHECKPOINT_VALUE_INVALID")
        for logical_id, count in conn.execute(
            "SELECT logical_id,COUNT(*) FROM observations GROUP BY logical_id"
        ):
            rows = conn.execute(
                "SELECT revision_number,record_hash,supersedes_record_hash,available_at FROM observations WHERE logical_id=? ORDER BY revision_number",
                (logical_id,),
            ).fetchall()
            previous = None
            previous_available_ms: int | None = None
            for expected, row in enumerate(rows, start=1):
                if int(row["revision_number"]) != expected:
                    raise AcquisitionError("REVISION_GAP")
                if row["supersedes_record_hash"] != previous:
                    raise AcquisitionError("REVISION_PARENT_MISMATCH")
                available_ms = _timestamp_ms(row["available_at"], "revision_available_at")
                if previous_available_ms is not None and available_ms < previous_available_ms:
                    raise AcquisitionError("REVISION_AVAILABILITY_REGRESSION")
                previous_available_ms = available_ms
                previous = row["record_hash"]
        return {
            "verdict": "PASS",
            "schema_fingerprint": journal.schema_fingerprint,
            "counts": counts,
            "object_scan": bool(scan_objects),
            "orphan_object_count": orphan_object_count,
        }
