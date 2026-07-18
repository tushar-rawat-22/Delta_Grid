from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import quote, urlparse

import requests

from . import AUTHORIZED_SYMBOLS, LATEST_AUTHORIZED_MONTH, PROTOCOL_HASH


ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = ROOT / "offchain" / "data" / "alpha_search_b"
CONTRACT_PATH = ROOT / "contracts" / "ALPHA_SEARCH_B_PROTOCOL_V1.json"
COST_PATH = ROOT / "contracts" / "ALPHA_SEARCH_B_COST_ATTRIBUTION_V1.json"
BINANCE_DATA_HOST = "data.binance.vision"
BINANCE_API_HOST = "api.binance.com"
MONTH_RE = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
CHECKSUM_RE = re.compile(r"^([0-9a-fA-F]{64})\s+\*?([^\s]+)\s*$")
KLINE_COLUMNS = (
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume", "ignore",
)
PRICE_COLUMNS = ("open", "high", "low", "close")
DECIMAL_COLUMNS = PRICE_COLUMNS + (
    "volume", "quote_asset_volume", "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
)


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_protocol() -> dict[str, Any]:
    contract = load_json(CONTRACT_PATH)
    core = dict(contract)
    embedded = core.pop("contract_hash_sha256")
    computed = canonical_hash(core)
    if embedded != PROTOCOL_HASH or computed != PROTOCOL_HASH:
        raise RuntimeError("ALPHA_SEARCH_B_PROTOCOL_HASH_MISMATCH")
    return contract


def load_cost_attribution() -> dict[str, Any]:
    contract = load_json(COST_PATH)
    if contract["protocol_hash_sha256"] != PROTOCOL_HASH:
        raise RuntimeError("ALPHA_SEARCH_B_COST_PROTOCOL_HASH_MISMATCH")
    for symbol in AUTHORIZED_SYMBOLS:
        for scenario in ("normal", "conservative", "severe"):
            row = contract["components_bps"][symbol][scenario]
            values = {name: Decimal(value) for name, value in row.items()}
            if any(value < 0 for value in values.values()):
                raise RuntimeError("ALPHA_SEARCH_B_NEGATIVE_COST_COMPONENT")
            component_sum = (
                values["entry_fee"] + values["exit_fee"]
                + values["spread_slippage_impact"]
            )
            if component_sum != values["total"]:
                raise RuntimeError("ALPHA_SEARCH_B_COST_COMPONENT_SUM_MISMATCH")
    return contract


def authorized_months() -> tuple[str, ...]:
    months: list[str] = []
    year, month = 2022, 6
    while (year, month) <= (2024, 6):
        months.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    assert len(months) == 25 and months[-1] == LATEST_AUTHORIZED_MONTH
    return tuple(months)


def require_authorized_symbol_month(symbol: str, month: str) -> None:
    if symbol not in AUTHORIZED_SYMBOLS:
        raise ValueError("ALPHA_SEARCH_B_UNAUTHORIZED_SYMBOL")
    if not MONTH_RE.fullmatch(month) or month not in authorized_months():
        raise ValueError("ALPHA_SEARCH_B_UNAUTHORIZED_MONTH")
    if month > LATEST_AUTHORIZED_MONTH:
        raise ValueError("ALPHA_SEARCH_B_VALIDATION_HOLDOUT_MONTH_PROHIBITED")


def archive_urls(symbol: str, month: str) -> tuple[str, str]:
    require_authorized_symbol_month(symbol, month)
    name = f"{symbol}-1m-{month}.zip"
    url = f"https://{BINANCE_DATA_HOST}/data/spot/monthly/klines/{symbol}/1m/{name}"
    return url, f"{url}.CHECKSUM"


def _validate_url(url: str, *, api: bool = False) -> None:
    parsed = urlparse(url)
    allowed = BINANCE_API_HOST if api else BINANCE_DATA_HOST
    if parsed.scheme != "https" or parsed.hostname != allowed or parsed.username or parsed.password:
        raise RuntimeError("ALPHA_SEARCH_B_NON_ALLOWLISTED_URL")
    if parsed.port not in (None, 443):
        raise RuntimeError("ALPHA_SEARCH_B_NON_ALLOWLISTED_URL")
    if api and parsed.path not in ("/api/v3/exchangeInfo", "/api/v3/ticker/price"):
        raise RuntimeError("ALPHA_SEARCH_B_PRIVATE_OR_UNAUTHORIZED_ENDPOINT")


def parse_checksum(text: str, expected_filename: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError("checksum must contain exactly one nonempty line")
    match = CHECKSUM_RE.fullmatch(lines[0])
    if not match or PurePosixPath(match.group(2)).name != expected_filename:
        raise ValueError("checksum filename or digest is invalid")
    return match.group(1).lower()


def safe_zip_member(path: Path, expected_filename: str) -> zipfile.ZipInfo:
    if not zipfile.is_zipfile(path):
        raise ValueError("archive is not a ZIP file")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        expected_csv = expected_filename.removesuffix(".zip") + ".csv"
        if len(members) != 1:
            raise ValueError("archive must contain exactly one member")
        member = members[0]
        pure = PurePosixPath(member.filename)
        if (
            pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 1
            or pure.name != expected_csv or member.is_dir()
        ):
            raise ValueError("unexpected or unsafe archive member")
        return member


def normalize_timestamp(value: str | int) -> tuple[int, str]:
    text = str(value)
    if not text.isdigit():
        raise ValueError("timestamp must be an unsigned integer")
    raw = int(text)
    digits = len(text)
    if digits == 13:
        milliseconds, unit = raw, "MILLISECOND"
    elif digits == 16:
        if raw % 1000:
            raise ValueError("microsecond timestamp is not millisecond aligned")
        milliseconds, unit = raw // 1000, "MICROSECOND"
    else:
        raise ValueError("ambiguous timestamp unit")
    if milliseconds % 60_000:
        raise ValueError("open timestamp is not minute aligned")
    return milliseconds, unit


@dataclass(frozen=True)
class CertifiedRow:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time_ms: int
    quote_asset_volume: float
    number_of_trades: int
    taker_buy_base_asset_volume: float
    taker_buy_quote_asset_volume: float
    timestamp_unit: str


def validate_kline_row(fields: Sequence[str], tolerance: Decimal = Decimal("0.00000001")) -> CertifiedRow:
    if len(fields) != len(KLINE_COLUMNS):
        raise ValueError("kline row must contain exactly 12 fields")
    open_ms, open_unit = normalize_timestamp(fields[0])
    close_text = fields[6]
    if not close_text.isdigit() or len(close_text) not in (13, 16):
        raise ValueError("ambiguous close timestamp unit")
    close_raw = int(close_text)
    close_ms = close_raw if len(close_text) == 13 else close_raw // 1000
    close_unit = "MILLISECOND" if len(close_text) == 13 else "MICROSECOND"
    if close_unit != open_unit or close_ms <= open_ms or close_ms >= open_ms + 60_001:
        raise ValueError("invalid close timestamp")
    try:
        numeric = {column: Decimal(fields[KLINE_COLUMNS.index(column)]) for column in DECIMAL_COLUMNS}
        trades = int(fields[8])
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("malformed numeric field") from exc
    if any(not value.is_finite() or value < 0 for value in numeric.values()) or trades < 0:
        raise ValueError("negative or non-finite kline value")
    if any(numeric[column] <= 0 for column in PRICE_COLUMNS):
        raise ValueError("prices must be positive")
    if numeric["high"] < max(numeric["open"], numeric["close"], numeric["low"]):
        raise ValueError("high price invariant failed")
    if numeric["low"] > min(numeric["open"], numeric["close"], numeric["high"]):
        raise ValueError("low price invariant failed")
    if numeric["taker_buy_base_asset_volume"] > numeric["volume"] + tolerance:
        raise ValueError("taker-buy base volume exceeds total")
    if numeric["taker_buy_quote_asset_volume"] > numeric["quote_asset_volume"] + tolerance:
        raise ValueError("taker-buy quote volume exceeds total")
    if Decimal(fields[11]) != 0:
        raise ValueError("ignore field must be zero")
    return CertifiedRow(
        open_time_ms=open_ms, open=float(numeric["open"]), high=float(numeric["high"]),
        low=float(numeric["low"]), close=float(numeric["close"]),
        volume=float(numeric["volume"]), close_time_ms=close_ms,
        quote_asset_volume=float(numeric["quote_asset_volume"]), number_of_trades=trades,
        taker_buy_base_asset_volume=float(numeric["taker_buy_base_asset_volume"]),
        taker_buy_quote_asset_volume=float(numeric["taker_buy_quote_asset_volume"]),
        timestamp_unit=open_unit,
    )


def iter_certified_zip(path: Path, expected_filename: str) -> Iterator[CertifiedRow]:
    member = safe_zip_member(path, expected_filename)
    previous: int | None = None
    with zipfile.ZipFile(path) as archive, archive.open(member) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
        for line_number, fields in enumerate(csv.reader(text), start=1):
            try:
                row = validate_kline_row(fields)
            except ValueError as exc:
                raise ValueError(f"{expected_filename}:{line_number}: {exc}") from exc
            if previous is not None and row.open_time_ms <= previous:
                kind = "duplicate" if row.open_time_ms == previous else "out-of-order"
                raise ValueError(f"{expected_filename}:{line_number}: {kind} timestamp")
            previous = row.open_time_ms
            yield row


def synchronized_minutes(series: Mapping[str, Sequence[int]]) -> list[int]:
    if set(series) != set(AUTHORIZED_SYMBOLS):
        raise ValueError("all and only authorized symbols are required")
    sets = {symbol: set(values) for symbol, values in series.items()}
    if any(len(values) != len(sets[symbol]) for symbol, values in series.items()):
        raise ValueError("duplicate pair/timestamp rows")
    return sorted(set.intersection(*sets.values()))


class PublicDownloader:
    def __init__(self, session: requests.Session | None = None, retries: int = 3) -> None:
        self.session = session or requests.Session()
        self.retries = retries
        self.counters = {
            "public_archive_gets": 0, "public_checksum_gets": 0,
            "public_exchange_info_gets": 0, "public_reference_price_gets": 0,
            "private_endpoint_requests": 0, "credential_requests": 0,
            "validation_url_requests": 0, "holdout_url_requests": 0,
            "unapproved_symbol_requests": 0, "non_allowlisted_host_requests": 0,
            "redirects_followed": 0, "account_requests": 0, "order_requests": 0,
        }

    def _get(self, url: str, *, stream: bool, api: bool = False, headers: Mapping[str, str] | None = None) -> requests.Response:
        try:
            _validate_url(url, api=api)
        except RuntimeError:
            self.counters["non_allowlisted_host_requests"] += 1
            raise
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self.session.get(
                    url, stream=stream, allow_redirects=False, timeout=(10, 60),
                    headers=dict(headers or {}),
                )
                if 300 <= response.status_code < 400:
                    raise RuntimeError("ALPHA_SEARCH_B_REDIRECT_REJECTED")
                response.raise_for_status()
                return response
            except (requests.RequestException, RuntimeError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    time.sleep(1 + attempt)
        assert last_error is not None
        raise last_error

    def download_pair_month(self, symbol: str, month: str, raw_dir: Path) -> dict[str, Any]:
        require_authorized_symbol_month(symbol, month)
        archive_url, checksum_url = archive_urls(symbol, month)
        raw_dir.mkdir(parents=True, exist_ok=True)
        filename = Path(urlparse(archive_url).path).name
        zip_path = raw_dir / filename
        checksum_path = raw_dir / f"{filename}.CHECKSUM"
        checksum_response = self._get(checksum_url, stream=False)
        self.counters["public_checksum_gets"] += 1
        checksum_text = checksum_response.text
        expected = parse_checksum(checksum_text, filename)
        checksum_path.write_text(checksum_text, encoding="utf-8")
        if not zip_path.exists() or sha256_file(zip_path) != expected:
            partial = zip_path.with_suffix(".zip.part")
            partial.unlink(missing_ok=True)
            response = self._get(archive_url, stream=True)
            self.counters["public_archive_gets"] += 1
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                raise RuntimeError("ALPHA_SEARCH_B_HTML_ARCHIVE_PAYLOAD")
            with partial.open("wb") as handle:
                for block in response.iter_content(chunk_size=1024 * 1024):
                    if block:
                        handle.write(block)
            os.replace(partial, zip_path)
        actual = sha256_file(zip_path)
        if actual != expected:
            zip_path.unlink(missing_ok=True)
            raise RuntimeError("ALPHA_SEARCH_B_CHECKSUM_FAILURE")
        member = safe_zip_member(zip_path, filename)
        return {
            "symbol": symbol, "month": month, "source_url": archive_url,
            "checksum_url": checksum_url, "sha256": actual,
            "content_length": zip_path.stat().st_size,
            "archive_member": member.filename,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "archive_path": str(zip_path.relative_to(ROOT)),
            "checksum_path": str(checksum_path.relative_to(ROOT)),
        }

    def exchange_snapshot(self) -> dict[str, Any]:
        symbols_json = json.dumps(list(AUTHORIZED_SYMBOLS), separators=(",", ":"))
        query = quote(symbols_json, safe="")
        info_url = f"https://{BINANCE_API_HOST}/api/v3/exchangeInfo?symbols={query}"
        price_url = f"https://{BINANCE_API_HOST}/api/v3/ticker/price?symbols={query}"
        info_response = self._get(info_url, stream=False, api=True)
        self.counters["public_exchange_info_gets"] += 1
        price_response = self._get(price_url, stream=False, api=True)
        self.counters["public_reference_price_gets"] += 1
        info = info_response.json()
        prices = price_response.json()
        allowed_filter_types = {"LOT_SIZE", "MARKET_LOT_SIZE", "MIN_NOTIONAL", "NOTIONAL", "PRICE_FILTER"}
        compact_symbols = []
        for row in info.get("symbols", []):
            if row.get("symbol") not in AUTHORIZED_SYMBOLS:
                raise RuntimeError("ALPHA_SEARCH_B_EXCHANGE_SNAPSHOT_SYMBOL_SCOPE")
            compact_symbols.append({
                "symbol": row["symbol"], "status": row.get("status"),
                "baseAsset": row.get("baseAsset"), "quoteAsset": row.get("quoteAsset"),
                "isSpotTradingAllowed": row.get("isSpotTradingAllowed"),
                "filters": [f for f in row.get("filters", []) if f.get("filterType") in allowed_filter_types],
            })
        return {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "diagnostic_current_only": True,
            "historical_constancy_claimed": False,
            "symbols": compact_symbols,
            "reference_prices": [row for row in prices if row.get("symbol") in AUTHORIZED_SYMBOLS],
        }


def available_bytes(path: Path = ROOT) -> int:
    return shutil.disk_usage(path).free


def assert_preflight_storage() -> None:
    if available_bytes() < 12 * 1024**3:
        raise RuntimeError("ALPHA_SEARCH_B_INSUFFICIENT_DISK")
