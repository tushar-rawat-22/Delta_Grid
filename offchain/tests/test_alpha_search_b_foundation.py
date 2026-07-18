from __future__ import annotations

import hashlib
import io
import json
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest

from offchain.research.alpha_search_b.foundation import (
    archive_urls,
    authorized_months,
    load_cost_attribution,
    normalize_timestamp,
    parse_checksum,
    safe_zip_member,
    synchronized_minutes,
    validate_kline_row,
    verify_protocol,
)


def kline(*, open_time: str = "1654041600000", close_time: str = "1654041659999") -> list[str]:
    return [open_time, "100", "110", "90", "105", "2", close_time, "200", "5", "1", "100", "0"]


def write_zip(path: Path, member: str, payload: bytes = b"x") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, payload)


def test_protocol_and_exact_decimal_cost_lock() -> None:
    assert verify_protocol()["contract_hash_sha256"].startswith("ee82fdb")
    contract = load_cost_attribution()
    for scenarios in contract["components_bps"].values():
        for row in scenarios.values():
            assert Decimal(row["entry_fee"]) == Decimal("10")
            assert Decimal(row["exit_fee"]) == Decimal("10")
            assert sum(Decimal(row[key]) for key in ("entry_fee", "exit_fee", "spread_slippage_impact")) == Decimal(row["total"])
    assert contract["latency_displacement"]["deducted_as_cost_component"] is False
    assert len(contract["provenance"]) >= 5


def test_authorized_month_boundary_and_urls() -> None:
    months = authorized_months()
    assert len(months) == 25 and months[0] == "2022-06" and months[-1] == "2024-06"
    assert archive_urls("BTCUSDT", "2024-06")[0].endswith("BTCUSDT-1m-2024-06.zip")
    for month in ("2024-07", "2025-01", "2026-06"):
        with pytest.raises(ValueError):
            archive_urls("BTCUSDT", month)
    with pytest.raises(ValueError):
        archive_urls("BNBUSDT", "2024-06")


def test_checksum_parser_is_exact() -> None:
    digest = hashlib.sha256(b"payload").hexdigest()
    assert parse_checksum(f"{digest}  BTCUSDT-1m-2022-06.zip\n", "BTCUSDT-1m-2022-06.zip") == digest
    with pytest.raises(ValueError):
        parse_checksum(f"{digest}  ETHUSDT-1m-2022-06.zip\n", "BTCUSDT-1m-2022-06.zip")


def test_zip_safety(tmp_path: Path) -> None:
    valid = tmp_path / "BTCUSDT-1m-2022-06.zip"
    write_zip(valid, "BTCUSDT-1m-2022-06.csv")
    assert safe_zip_member(valid, valid.name).filename.endswith(".csv")
    unsafe = tmp_path / "ETHUSDT-1m-2022-06.zip"
    write_zip(unsafe, "../ETHUSDT-1m-2022-06.csv")
    with pytest.raises(ValueError):
        safe_zip_member(unsafe, unsafe.name)


def test_millisecond_and_microsecond_timestamps() -> None:
    assert normalize_timestamp("1654041600000") == (1654041600000, "MILLISECOND")
    assert normalize_timestamp("1654041600000000") == (1654041600000, "MICROSECOND")
    with pytest.raises(ValueError):
        normalize_timestamp("1654041600")
    with pytest.raises(ValueError):
        normalize_timestamp("1654041600000001")


def test_schema_price_volume_and_ignore_invariants() -> None:
    row = validate_kline_row(kline())
    assert row.open_time_ms == 1654041600000 and row.number_of_trades == 5
    cases = []
    bad_high = kline(); bad_high[2] = "99"; cases.append(bad_high)
    bad_taker = kline(); bad_taker[10] = "201"; cases.append(bad_taker)
    bad_ignore = kline(); bad_ignore[11] = "1"; cases.append(bad_ignore)
    bad_negative = kline(); bad_negative[5] = "-1"; cases.append(bad_negative)
    for fields in cases:
        with pytest.raises(ValueError):
            validate_kline_row(fields)


def test_duplicate_and_synchronized_minute_handling() -> None:
    series = {"BTCUSDT": [1, 2, 3], "ETHUSDT": [2, 3, 4], "SOLUSDT": [0, 2, 3]}
    assert synchronized_minutes(series) == [2, 3]
    series["BTCUSDT"] = [1, 1, 2]
    with pytest.raises(ValueError):
        synchronized_minutes(series)
