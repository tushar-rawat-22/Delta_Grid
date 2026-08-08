"""Strict Mission 100 contracts, identities, and temporal primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AUTONOMY_V1_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_AUTONOMY_CONSTITUTION_V1.json"
AUTONOMY_V2_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_AUTONOMY_CONSTITUTION_V2.json"
MISSION99_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_TEMPORAL_MARKET_DATA_CONTROL_PLANE_V1.json"
MISSION100_PATH = REPOSITORY_ROOT / "contracts" / "DELTAGRID_FORWARD_MARKET_DATA_ACQUISITION_V1.json"

AUTONOMY_V1_HASH = "b9b1d48dd3f65ac492b287e9d5dcebe11f69063138698bf37432c11869a3da5b"
MISSION99_HASH = "159a822f77e3c6bf6409e04b2c25a61c5c7232cf6e73ea160ffb6cbf167d5d4c"
# Filled by the build script after contract contents are frozen.
AUTONOMY_V2_HASH = "a9d830e14ad1d93efbfd7529e9ee937926d577aeb63792acf900fbc80d968664"
MISSION100_HASH = "42f1ebe86264268763978d6969c2a605924805433a041647f2625dfd297e16e3"

PROVIDER = "BINANCE_PUBLIC"
SPOT_HOST = "data-api.binance.vision"
FUTURES_HOST = "fapi.binance.com"
HOSTS = frozenset({SPOT_HOST, FUTURES_HOST})
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
STREAMS = (
    "spot_ohlcv",
    "perpetual_ohlcv",
    "mark_price_ohlcv",
    "index_price_ohlcv",
    "funding_rates",
)
BAR_STREAMS = frozenset(STREAMS[:-1])
INTERVAL = "1h"
INTERVAL_MS = 3_600_000
NORMALIZER_ID = "deltagrid-mission100-forward-normalizer-v1"
AVAILABILITY_POLICY_ID = "deltagrid-mission100-forward-observed-v1"

HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,255}\Z")
MAX_JSON_NESTING = 64
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_STRING_BYTES = 16 * 1024


class AcquisitionError(RuntimeError):
    """Fail-closed Mission 100 error with a stable reason code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class ClockStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


class BatchStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AcquisitionError("JSON_DUPLICATE_KEY", key)
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise AcquisitionError("JSON_NON_FINITE_NUMBER", value)


def _validate_json(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_JSON_NESTING:
        raise AcquisitionError("JSON_NESTING_LIMIT")
    if value is None or type(value) in {bool, int, str}:
        if type(value) is str and len(value.encode("utf-8")) > MAX_STRING_BYTES:
            raise AcquisitionError("JSON_STRING_LIMIT")
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise AcquisitionError("JSON_NON_FINITE_NUMBER")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if type(key) is not str:
                raise AcquisitionError("JSON_OBJECT_KEY_INVALID")
            _validate_json(child, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _validate_json(child, depth=depth + 1)
        return
    raise AcquisitionError("JSON_TYPE_UNSUPPORTED", type(value).__name__)


def deep_freeze(value: Any) -> Any:
    _validate_json(value)
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): deep_freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(deep_freeze(v) for v in value)
    return value


def deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): deep_thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [deep_thaw(v) for v in value]
    if isinstance(value, list):
        return [deep_thaw(v) for v in value]
    return value


def strict_json_load(source: str | bytes | Path, *, maximum_bytes: int = MAX_JSON_BYTES) -> Any:
    if isinstance(source, Path):
        if source.is_symlink() or not source.is_file():
            raise AcquisitionError("JSON_INPUT_INVALID")
        if source.stat().st_size > maximum_bytes:
            raise AcquisitionError("JSON_SIZE_LIMIT")
        raw = source.read_bytes()
    elif isinstance(source, str):
        raw = source.encode("utf-8")
    elif isinstance(source, bytes):
        raw = source
    else:
        raise AcquisitionError("JSON_INPUT_INVALID")
    if len(raw) > maximum_bytes:
        raise AcquisitionError("JSON_SIZE_LIMIT")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise AcquisitionError("JSON_BOM_REJECTED")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except AcquisitionError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AcquisitionError("JSON_MALFORMED", str(error)) from error
    _validate_json(value)
    return value


def canonical_json(value: Any) -> str:
    thawed = deep_thaw(value)
    _validate_json(thawed)
    return json.dumps(
        thawed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_hash(value: Any, field: str) -> str:
    if type(value) is not str or HASH_RE.fullmatch(value) is None:
        raise AcquisitionError("HASH_INVALID", field)
    return value


def require_commit(value: Any, field: str) -> str:
    if type(value) is not str or COMMIT_RE.fullmatch(value) is None:
        raise AcquisitionError("COMMIT_INVALID", field)
    return value


def require_identifier(value: Any, field: str) -> str:
    if type(value) is not str or IDENTIFIER_RE.fullmatch(value) is None:
        raise AcquisitionError("IDENTIFIER_INVALID", field)
    return value


def require_int(value: Any, field: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if type(value) is not int:
        raise AcquisitionError("INTEGER_INVALID", field)
    if minimum is not None and value < minimum:
        raise AcquisitionError("INTEGER_RANGE_INVALID", field)
    if maximum is not None and value > maximum:
        raise AcquisitionError("INTEGER_RANGE_INVALID", field)
    return value


def require_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise AcquisitionError("BOOLEAN_INVALID", field)
    return value


def parse_utc(value: Any, field: str) -> datetime:
    if type(value) is not str or UTC_RE.fullmatch(value) is None:
        raise AcquisitionError("TIMESTAMP_INVALID", field)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise AcquisitionError("TIMESTAMP_INVALID", field) from error
    return parsed.astimezone(timezone.utc)


def utc_now_ms() -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    epoch_ms = int(now.timestamp() * 1000)
    text = now.strftime("%Y-%m-%dT%H:%M:%S") + f".{now.microsecond // 1000:03d}Z"
    return text, epoch_ms


def ms_to_utc(value: int) -> str:
    require_int(value, "timestamp_ms", minimum=0)
    dt = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{dt.microsecond // 1000:03d}Z"


def contract_hash(contract: Mapping[str, Any]) -> str:
    core = deep_thaw(contract)
    core.pop("contract_hash_sha256", None)
    return canonical_hash(core)


def _load_contract(path: Path, expected_hash: str, expected_id: str) -> Mapping[str, Any]:
    data = strict_json_load(path)
    if not isinstance(data, Mapping):
        raise AcquisitionError("CONTRACT_NOT_OBJECT", str(path))
    declared = require_hash(data.get("contract_hash_sha256"), "contract_hash_sha256")
    actual = contract_hash(data)
    if declared != actual or actual != expected_hash:
        raise AcquisitionError("CONTRACT_HASH_MISMATCH", str(path))
    if data.get("contract_id") != expected_id:
        raise AcquisitionError("CONTRACT_ID_MISMATCH", str(path))
    return deep_freeze(data)


def load_contracts() -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    v1 = _load_contract(AUTONOMY_V1_PATH, AUTONOMY_V1_HASH, "deltagrid-autonomy-constitution-v1")
    v2 = _load_contract(AUTONOMY_V2_PATH, AUTONOMY_V2_HASH, "deltagrid-autonomy-constitution-v2")
    m99 = _load_contract(MISSION99_PATH, MISSION99_HASH, "deltagrid-temporal-market-data-control-plane-v1")
    m100 = _load_contract(MISSION100_PATH, MISSION100_HASH, "deltagrid-forward-market-data-acquisition-v1")

    if v2.get("parent_constitution_id") != v1.get("contract_id"):
        raise AcquisitionError("AUTONOMY_LINEAGE_ID_MISMATCH")
    if v2.get("parent_constitution_hash_sha256") != AUTONOMY_V1_HASH:
        raise AcquisitionError("AUTONOMY_LINEAGE_HASH_MISMATCH")
    if v2.get("authority_version") != 2:
        raise AcquisitionError("AUTONOMY_VERSION_MISMATCH")
    current = v2.get("current_authority", {})
    expected_true = {"public_market_data_network_access"}
    for key in expected_true:
        if current.get(key) is not True:
            raise AcquisitionError("AUTONOMY_PUBLIC_DATA_AUTHORITY_MISSING", key)
    for key in (
        "exchange_account_connectivity",
        "credential_access",
        "paper_trading",
        "live_trading",
        "order_authorization",
        "capital_deployment",
    ):
        if current.get(key) is not False:
            raise AcquisitionError("AUTONOMY_PROHIBITED_AUTHORITY_ENABLED", key)

    if m100.get("autonomy_constitution_hash_sha256") != AUTONOMY_V2_HASH:
        raise AcquisitionError("M100_AUTONOMY_HASH_MISMATCH")
    if m100.get("mission99_contract_hash_sha256") != MISSION99_HASH:
        raise AcquisitionError("M100_M99_HASH_MISMATCH")
    if m100.get("base_commit") != "5f1936c2989213612a078e72acbeaec3f871971f":
        raise AcquisitionError("M100_BASE_COMMIT_MISMATCH")
    provider_scope = m100.get("provider_scope", {})
    if provider_scope.get("provider") != PROVIDER:
        raise AcquisitionError("M100_PROVIDER_SCOPE_MISMATCH")
    if provider_scope.get("spot_host") != SPOT_HOST or provider_scope.get("futures_host") != FUTURES_HOST:
        raise AcquisitionError("M100_HOST_SCOPE_MISMATCH")
    if tuple(provider_scope.get("symbols", ())) != SYMBOLS:
        raise AcquisitionError("M100_SYMBOL_SCOPE_MISMATCH")
    if tuple(provider_scope.get("streams", ())) != STREAMS:
        raise AcquisitionError("M100_STREAM_SCOPE_MISMATCH")
    if provider_scope.get("bar_interval") != INTERVAL:
        raise AcquisitionError("M100_INTERVAL_SCOPE_MISMATCH")
    endpoint_expected = {
        "spot_time": ("data-api.binance.vision", "/api/v3/time", ()),
        "spot_ohlcv": ("data-api.binance.vision", "/api/v3/klines", ("endTime", "interval", "limit", "startTime", "symbol")),
        "futures_time": ("fapi.binance.com", "/fapi/v1/time", ()),
        "perpetual_ohlcv": ("fapi.binance.com", "/fapi/v1/klines", ("endTime", "interval", "limit", "startTime", "symbol")),
        "mark_price_ohlcv": ("fapi.binance.com", "/fapi/v1/markPriceKlines", ("endTime", "interval", "limit", "startTime", "symbol")),
        "index_price_ohlcv": ("fapi.binance.com", "/fapi/v1/indexPriceKlines", ("endTime", "interval", "limit", "pair", "startTime")),
        "funding_rates": ("fapi.binance.com", "/fapi/v1/fundingRate", ("endTime", "limit", "startTime", "symbol")),
        "funding_info": ("fapi.binance.com", "/fapi/v1/fundingInfo", ()),
    }
    endpoints = m100.get("endpoint_allowlist", {})
    if set(endpoints) != set(endpoint_expected):
        raise AcquisitionError("M100_ENDPOINT_SET_MISMATCH")
    for name, (host, path, parameters) in endpoint_expected.items():
        item = endpoints.get(name, {})
        if item.get("method") != "GET" or item.get("host") != host or item.get("path") != path:
            raise AcquisitionError("M100_ENDPOINT_MISMATCH", name)
        if tuple(item.get("parameters", ())) != parameters:
            raise AcquisitionError("M100_ENDPOINT_PARAMETER_SCHEMA_MISMATCH", name)
    transport = m100.get("transport", {})
    if transport.get("maximum_logical_requests_per_capture") != 18:
        raise AcquisitionError("M100_REQUEST_BUDGET_MISMATCH")
    if transport.get("maximum_time_range_hours") != 168:
        raise AcquisitionError("M100_TIME_RANGE_BUDGET_MISMATCH")
    for flag in ("redirects", "environment_proxies", "cookies", "request_bodies", "authorization_header", "x_mbx_apikey_header", "signed_requests"):
        if transport.get(flag) is not False:
            raise AcquisitionError("M100_TRANSPORT_PROHIBITION_MISMATCH", flag)

    authority = m100.get("authorization_state", {})
    if authority.get("public_market_data_collection") is not True:
        raise AcquisitionError("M100_COLLECTION_AUTHORITY_MISSING")
    for key in (
        "real_data_research_resolution",
        "strategy_authority",
        "performance_authority",
        "model_or_ml_authority",
        "signal_authority",
        "paper_trading",
        "live_trading",
        "exchange_account_access",
        "credential_access",
        "order_placement",
        "portfolio_authority",
        "capital_deployment",
        "profitability_claim",
        "self_authorization",
    ):
        if authority.get(key) is not False:
            raise AcquisitionError("M100_PROHIBITED_AUTHORITY_ENABLED", key)
    return v1, v2, m99, m100


@dataclass(frozen=True)
class ProviderClock:
    host: str
    server_time_ms: int
    local_midpoint_ms: int
    offset_ms: int
    wall_elapsed_ms: int
    monotonic_elapsed_ms: int
    status: ClockStatus

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "server_time_ms": self.server_time_ms,
            "local_midpoint_ms": self.local_midpoint_ms,
            "offset_ms": self.offset_ms,
            "wall_elapsed_ms": self.wall_elapsed_ms,
            "monotonic_elapsed_ms": self.monotonic_elapsed_ms,
            "status": self.status.value,
        }


@dataclass(frozen=True)
class ResponseReceipt:
    request_id: str
    host: str
    path: str
    params: Mapping[str, Any]
    requested_at: str
    received_at: str
    wall_start_ms: int
    wall_end_ms: int
    monotonic_duration_ms: int
    clock_status: ClockStatus
    http_status: int
    headers: Mapping[str, str]
    attempt_number: int
    retry_exhausted: bool
    body_sha256: str
    object_sha256: str
    response_hash: str
    receipt_hash: str

    def __post_init__(self) -> None:
        if not isinstance(self.clock_status, ClockStatus):
            try:
                object.__setattr__(self, "clock_status", ClockStatus(self.clock_status))
            except (TypeError, ValueError) as error:
                raise AcquisitionError("CLOCK_STATUS_INVALID") from error
        require_identifier(self.request_id, "request_id")
        if self.host not in HOSTS:
            raise AcquisitionError("HOST_NOT_ALLOWED", self.host)
        if not self.path.startswith("/") or ".." in self.path:
            raise AcquisitionError("PATH_INVALID", self.path)
        requested = parse_utc(self.requested_at, "requested_at")
        received = parse_utc(self.received_at, "received_at")
        if received < requested:
            raise AcquisitionError("RECEIPT_TIME_REGRESSION")
        require_int(self.wall_start_ms, "wall_start_ms", minimum=0)
        require_int(self.wall_end_ms, "wall_end_ms", minimum=self.wall_start_ms)
        require_int(self.monotonic_duration_ms, "monotonic_duration_ms", minimum=0)
        require_int(self.http_status, "http_status", minimum=100, maximum=599)
        require_int(self.attempt_number, "attempt_number", minimum=1, maximum=16)
        require_bool(self.retry_exhausted, "retry_exhausted")
        require_hash(self.body_sha256, "body_sha256")
        require_hash(self.object_sha256, "object_sha256")
        require_hash(self.response_hash, "response_hash")
        require_hash(self.receipt_hash, "receipt_hash")
        object.__setattr__(self, "params", deep_freeze(self.params))
        object.__setattr__(self, "headers", deep_freeze(self.headers))
        core = self._core()
        if canonical_hash(core) != self.receipt_hash:
            raise AcquisitionError("RECEIPT_HASH_MISMATCH")

    def _core(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "host": self.host,
            "path": self.path,
            "params": deep_thaw(self.params),
            "requested_at": self.requested_at,
            "received_at": self.received_at,
            "wall_start_ms": self.wall_start_ms,
            "wall_end_ms": self.wall_end_ms,
            "monotonic_duration_ms": self.monotonic_duration_ms,
            "clock_status": self.clock_status.value,
            "http_status": self.http_status,
            "headers": deep_thaw(self.headers),
            "attempt_number": self.attempt_number,
            "retry_exhausted": self.retry_exhausted,
            "body_sha256": self.body_sha256,
            "object_sha256": self.object_sha256,
            "response_hash": self.response_hash,
        }

    @classmethod
    def create(cls, **kwargs: Any) -> "ResponseReceipt":
        core = dict(kwargs)
        if isinstance(core.get("clock_status"), ClockStatus):
            core_for_hash = dict(core)
            core_for_hash["clock_status"] = core["clock_status"].value
        else:
            core_for_hash = core
        receipt_hash = canonical_hash(core_for_hash)
        return cls(receipt_hash=receipt_hash, **kwargs)

    def as_dict(self) -> dict[str, Any]:
        result = self._core()
        result["receipt_hash"] = self.receipt_hash
        return result


@dataclass(frozen=True)
class ObservationCandidate:
    stream: str
    symbol: str
    interval: str | None
    event_time_ms: int
    available_at: str
    receipt_hash: str
    response_hash: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.stream not in STREAMS:
            raise AcquisitionError("STREAM_NOT_ALLOWED", self.stream)
        if self.symbol not in SYMBOLS:
            raise AcquisitionError("SYMBOL_NOT_ALLOWED", self.symbol)
        if self.stream in BAR_STREAMS and self.interval != INTERVAL:
            raise AcquisitionError("INTERVAL_INVALID")
        if self.stream == "funding_rates" and self.interval is not None:
            raise AcquisitionError("FUNDING_INTERVAL_FIELD_INVALID")
        require_int(self.event_time_ms, "event_time_ms", minimum=0)
        parse_utc(self.available_at, "available_at")
        require_hash(self.receipt_hash, "receipt_hash")
        require_hash(self.response_hash, "response_hash")
        object.__setattr__(self, "payload", deep_freeze(self.payload))

    @property
    def logical_id(self) -> str:
        return canonical_hash(
            {
                "stream": self.stream,
                "symbol": self.symbol,
                "interval": self.interval,
                "event_time_ms": self.event_time_ms,
            }
        )

    @property
    def payload_hash(self) -> str:
        return canonical_hash(deep_thaw(self.payload))
