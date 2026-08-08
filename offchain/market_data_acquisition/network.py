"""Narrow public-only HTTPS client for Mission 100."""

from __future__ import annotations

from dataclasses import dataclass
import ssl
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from .core import (
    AcquisitionError,
    ClockStatus,
    FUTURES_HOST,
    HOSTS,
    INTERVAL,
    INTERVAL_MS,
    SPOT_HOST,
    SYMBOLS,
    ResponseReceipt,
    canonical_hash,
    canonical_json,
    sha256_bytes,
    strict_json_load,
    utc_now_ms,
)


MAX_RESPONSE_BYTES = 8 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 2
MAX_RETRY_AFTER_SECONDS = 30.0
MAX_CLOCK_OFFSET_MS = 5_000
MAX_WALL_MONOTONIC_DRIFT_MS = 1_000
USER_AGENT = "DeltaGrid-Mission100/1"
ALLOWED_RESPONSE_HEADERS = {
    "date",
    "retry-after",
    "content-type",
    "content-length",
}


@dataclass(frozen=True)
class EndpointSpec:
    name: str
    host: str
    path: str
    parameter_names: frozenset[str]
    required_names: frozenset[str]


@dataclass(frozen=True)
class NetworkAttempt:
    body: bytes
    receipt: ResponseReceipt


class RequestFailed(AcquisitionError):
    def __init__(self, reason: str, attempts: tuple[NetworkAttempt, ...], detail: str = "") -> None:
        super().__init__(reason, detail)
        self.attempts = attempts


ENDPOINTS = {
    "spot_time": EndpointSpec("spot_time", SPOT_HOST, "/api/v3/time", frozenset(), frozenset()),
    "spot_ohlcv": EndpointSpec(
        "spot_ohlcv",
        SPOT_HOST,
        "/api/v3/klines",
        frozenset({"symbol", "interval", "startTime", "endTime", "limit"}),
        frozenset({"symbol", "interval", "startTime", "endTime", "limit"}),
    ),
    "futures_time": EndpointSpec("futures_time", FUTURES_HOST, "/fapi/v1/time", frozenset(), frozenset()),
    "perpetual_ohlcv": EndpointSpec(
        "perpetual_ohlcv",
        FUTURES_HOST,
        "/fapi/v1/klines",
        frozenset({"symbol", "interval", "startTime", "endTime", "limit"}),
        frozenset({"symbol", "interval", "startTime", "endTime", "limit"}),
    ),
    "mark_price_ohlcv": EndpointSpec(
        "mark_price_ohlcv",
        FUTURES_HOST,
        "/fapi/v1/markPriceKlines",
        frozenset({"symbol", "interval", "startTime", "endTime", "limit"}),
        frozenset({"symbol", "interval", "startTime", "endTime", "limit"}),
    ),
    "index_price_ohlcv": EndpointSpec(
        "index_price_ohlcv",
        FUTURES_HOST,
        "/fapi/v1/indexPriceKlines",
        frozenset({"pair", "interval", "startTime", "endTime", "limit"}),
        frozenset({"pair", "interval", "startTime", "endTime", "limit"}),
    ),
    "funding_rates": EndpointSpec(
        "funding_rates",
        FUTURES_HOST,
        "/fapi/v1/fundingRate",
        frozenset({"symbol", "startTime", "endTime", "limit"}),
        frozenset({"symbol", "startTime", "endTime", "limit"}),
    ),
    "funding_info": EndpointSpec(
        "funding_info",
        FUTURES_HOST,
        "/fapi/v1/fundingInfo",
        frozenset(),
        frozenset(),
    ),
}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise AcquisitionError("HTTP_REDIRECT_REJECTED", newurl)


def _default_opener() -> Any:
    context = ssl.create_default_context()
    return build_opener(ProxyHandler({}), _NoRedirect(), HTTPSHandler(context=context))


def _selected_headers(headers: Mapping[str, Any]) -> dict[str, str]:
    selected: dict[str, str] = {}
    for key, value in headers.items():
        lower = str(key).lower()
        if lower in ALLOWED_RESPONSE_HEADERS or lower.startswith("x-mbx-used-weight-"):
            text = str(value)
            if len(text.encode("utf-8")) > 1024:
                raise AcquisitionError("HTTP_HEADER_TOO_LARGE", lower)
            selected[lower] = text
    if len(selected) > 16:
        raise AcquisitionError("HTTP_HEADER_COUNT_LIMIT")
    return dict(sorted(selected.items()))


def _read_bounded(response: Any, maximum_bytes: int = MAX_RESPONSE_BYTES) -> bytes:
    content_length = response.headers.get("Content-Length") if getattr(response, "headers", None) else None
    if content_length:
        try:
            if int(content_length) > maximum_bytes:
                raise AcquisitionError("HTTP_RESPONSE_TOO_LARGE")
        except ValueError:
            raise AcquisitionError("HTTP_CONTENT_LENGTH_INVALID")
    body = response.read(maximum_bytes + 1)
    if len(body) > maximum_bytes:
        raise AcquisitionError("HTTP_RESPONSE_TOO_LARGE")
    return body


def _validate_parameter_values(spec: EndpointSpec, params: Mapping[str, Any]) -> None:
    symbol = params.get("symbol")
    pair = params.get("pair")
    if symbol is not None and symbol not in SYMBOLS:
        raise AcquisitionError("REQUEST_SYMBOL_NOT_ALLOWED", str(symbol))
    if pair is not None and pair not in SYMBOLS:
        raise AcquisitionError("REQUEST_SYMBOL_NOT_ALLOWED", str(pair))
    if "interval" in params and params["interval"] != INTERVAL:
        raise AcquisitionError("REQUEST_INTERVAL_NOT_ALLOWED", str(params["interval"]))
    for name in ("startTime", "endTime", "limit"):
        if name in params and type(params[name]) is not int:
            raise AcquisitionError("REQUEST_PARAMETER_TYPE_INVALID", name)
    if "startTime" in params and "endTime" in params:
        start = params["startTime"]
        end = params["endTime"]
        if start < 0 or end < start:
            raise AcquisitionError("REQUEST_TIME_RANGE_INVALID")
        if end - start > 168 * INTERVAL_MS:
            raise AcquisitionError("REQUEST_TIME_RANGE_EXCEEDS_CONTRACT")
    if "limit" in params and not 1 <= params["limit"] <= 1000:
        raise AcquisitionError("REQUEST_LIMIT_INVALID")


def _request_url(spec: EndpointSpec, params: Mapping[str, Any]) -> str:
    if spec.host not in HOSTS:
        raise AcquisitionError("HOST_NOT_ALLOWED", spec.host)
    keys = set(params)
    unknown = keys - spec.parameter_names
    if unknown:
        raise AcquisitionError("REQUEST_PARAMETER_NOT_ALLOWED", repr(sorted(unknown)))
    missing = spec.required_names - keys
    if missing:
        raise AcquisitionError("REQUEST_PARAMETER_MISSING", repr(sorted(missing)))
    _validate_parameter_values(spec, params)
    query = urlencode([(key, params[key]) for key in sorted(params)], doseq=False)
    return f"https://{spec.host}{spec.path}" + (f"?{query}" if query else "")


def _validate_final_url(url: str, spec: EndpointSpec) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != spec.host or parsed.port not in {None, 443}:
        raise AcquisitionError("HTTP_FINAL_URL_INVALID", url)
    if parsed.path != spec.path:
        raise AcquisitionError("HTTP_FINAL_PATH_INVALID", parsed.path)


def perform_request(
    endpoint_name: str,
    params: Mapping[str, Any],
    *,
    opener: Any | None = None,
    request_id: str,
    clock_status: ClockStatus,
    sleep: Callable[[float], None] = time.sleep,
    max_retries: int = MAX_RETRIES,
) -> tuple[bytes, ResponseReceipt, dict[str, str], tuple[NetworkAttempt, ...]]:
    if endpoint_name not in ENDPOINTS:
        raise AcquisitionError("ENDPOINT_NOT_ALLOWED", endpoint_name)
    spec = ENDPOINTS[endpoint_name]
    url = _request_url(spec, params)
    transport = opener or _default_opener()
    attempts: list[NetworkAttempt] = []
    for attempt in range(1, max_retries + 2):
        requested_at, wall_start_ms = utc_now_ms()
        mono_start = time.monotonic_ns()
        request = Request(
            url,
            method="GET",
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            response = transport.open(request, timeout=REQUEST_TIMEOUT_SECONDS)
            status = int(response.getcode())
            final_url = response.geturl()
            _validate_final_url(final_url, spec)
            headers = _selected_headers(response.headers)
            body = _read_bounded(response)
        except HTTPError as error:
            status = int(error.code)
            final_url = error.geturl()
            _validate_final_url(final_url, spec)
            headers = _selected_headers(error.headers or {})
            body = error.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise AcquisitionError("HTTP_RESPONSE_TOO_LARGE") from error
        except AcquisitionError:
            raise
        except (URLError, TimeoutError, OSError) as error:
            if attempt <= max_retries:
                sleep(min(2 ** (attempt - 1), 4))
                continue
            raise RequestFailed("HTTP_TRANSPORT_FAILED", tuple(attempts), type(error).__name__) from error

        received_at, wall_end_ms = utc_now_ms()
        mono_end = time.monotonic_ns()
        monotonic_ms = max(0, int((mono_end - mono_start) / 1_000_000))
        wall_elapsed = wall_end_ms - wall_start_ms
        if abs(wall_elapsed - monotonic_ms) > MAX_WALL_MONOTONIC_DRIFT_MS:
            raise RequestFailed("CLOCK_JUMP_DURING_REQUEST", tuple(attempts))
        body_hash = sha256_bytes(body)
        response_hash = canonical_hash(
            {
                "method": "GET",
                "host": spec.host,
                "path": spec.path,
                "params": dict(params),
                "body_sha256": body_hash,
            }
        )
        retryable = status in {429, 500, 502, 503, 504}
        exhausted = retryable and attempt > max_retries
        provisional = ResponseReceipt.create(
            request_id=request_id,
            host=spec.host,
            path=spec.path,
            params=dict(params),
            requested_at=requested_at,
            received_at=received_at,
            wall_start_ms=wall_start_ms,
            wall_end_ms=wall_end_ms,
            monotonic_duration_ms=monotonic_ms,
            clock_status=clock_status,
            http_status=status,
            headers=headers,
            attempt_number=attempt,
            retry_exhausted=exhausted,
            body_sha256=body_hash,
            object_sha256="0" * 64,
            response_hash=response_hash,
        )
        attempts.append(NetworkAttempt(body=body, receipt=provisional))

        if status == 200:
            return body, provisional, headers, tuple(attempts)
        if status == 418:
            raise RequestFailed("BINANCE_IP_BANNED", tuple(attempts))
        if status == 429:
            if attempt > max_retries:
                raise RequestFailed("BINANCE_RATE_LIMIT_RETRY_EXHAUSTED", tuple(attempts))
            retry_after_raw = headers.get("retry-after")
            try:
                retry_after = float(retry_after_raw) if retry_after_raw is not None else 1.0
            except ValueError as error:
                raise RequestFailed("RETRY_AFTER_INVALID", tuple(attempts)) from error
            if retry_after < 0 or retry_after > MAX_RETRY_AFTER_SECONDS:
                raise RequestFailed("RETRY_AFTER_OUT_OF_BOUNDS", tuple(attempts))
            sleep(max(0.1, retry_after))
            continue
        if status in {500, 502, 503, 504}:
            if attempt <= max_retries:
                sleep(min(2 ** (attempt - 1), 4))
                continue
            raise RequestFailed("HTTP_RETRY_EXHAUSTED", tuple(attempts), str(status))
        raise RequestFailed("HTTP_STATUS_REJECTED", tuple(attempts), str(status))
    raise RequestFailed("HTTP_RETRY_LOOP_EXHAUSTED", tuple(attempts))

def decode_json(body: bytes) -> Any:
    if len(body) > MAX_RESPONSE_BYTES:
        raise AcquisitionError("HTTP_RESPONSE_TOO_LARGE")
    try:
        return strict_json_load(body, maximum_bytes=MAX_RESPONSE_BYTES)
    except AcquisitionError:
        raise
    except Exception as error:
        raise AcquisitionError("PROVIDER_JSON_INVALID") from error


def provider_server_time(
    host_kind: str,
    *,
    opener: Any | None,
    request_id: str,
) -> tuple[int, ResponseReceipt, bytes]:
    endpoint = "spot_time" if host_kind == "spot" else "futures_time"
    body, receipt, _, _attempts = perform_request(
        endpoint,
        {},
        opener=opener,
        request_id=request_id,
        clock_status=ClockStatus.UNKNOWN,
    )
    payload = decode_json(body)
    if not isinstance(payload, dict) or type(payload.get("serverTime")) is not int:
        raise AcquisitionError("SERVER_TIME_SCHEMA_INVALID")
    return int(payload["serverTime"]), receipt, body
