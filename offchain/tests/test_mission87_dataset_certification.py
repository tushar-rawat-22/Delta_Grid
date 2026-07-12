from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

from offchain.backtest.mission86_real_market_data_foundation import (
    CANONICAL_INTERVAL,
    INTERVAL_MS,
    canonical_json,
    ensure_schema as ensure_mission86_schema,
    sha256_bytes,
)
from offchain.backtest.mission87_dataset_certification import (
    CERTIFICATION_STATUS,
    FUNDING_INTERVAL_MS,
    REJECTED_STATUS,
    audit_bar_series,
    audit_cross_stream_consistency,
    audit_funding_series,
    audit_raw_responses,
    ensure_schema,
    nearest_funding_slot,
    parse_decimal,
    safe_relative_path,
    write_certificate_file,
)


CONTRACT_HASH = "test-contract-hash"
START_MS = 1704067200000


def insert_bar(
    conn: sqlite3.Connection,
    *,
    stream: str,
    symbol: str,
    timestamp: int,
    open_price: str = "100",
    high_price: str = "102",
    low_price: str = "99",
    close_price: str = "101",
    response_hash: str = "response",
    source_url: str = (
        "https://fapi.binance.com/fapi/v1/klines"
    ),
) -> None:
    has_volume = stream in {
        "spot_ohlcv",
        "perpetual_ohlcv",
    }

    conn.execute(
        """
        INSERT INTO mission86_market_bars (
            contract_hash,
            stream,
            symbol,
            interval,
            open_time_ms,
            close_time_ms,
            open_price,
            high_price,
            low_price,
            close_price,
            volume,
            quote_volume,
            trade_count,
            response_hash,
            source_url,
            inserted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            CONTRACT_HASH,
            stream,
            symbol,
            CANONICAL_INTERVAL,
            timestamp,
            timestamp + INTERVAL_MS - 1,
            open_price,
            high_price,
            low_price,
            close_price,
            "10" if has_volume else None,
            "1000" if has_volume else None,
            5 if has_volume else None,
            response_hash,
            source_url,
            "2026-07-12T00:00:00+00:00",
        ),
    )


def insert_funding(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    timestamp: int,
    funding_rate: str = "0.0001",
    mark_price: str = "100",
    response_hash: str = "funding-response",
) -> None:
    conn.execute(
        """
        INSERT INTO mission86_funding_rates (
            contract_hash,
            symbol,
            funding_time_ms,
            funding_rate,
            mark_price,
            response_hash,
            source_url,
            inserted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            CONTRACT_HASH,
            symbol,
            timestamp,
            funding_rate,
            mark_price,
            response_hash,
            (
                "https://fapi.binance.com/"
                "fapi/v1/fundingRate"
            ),
            "2026-07-12T00:00:00+00:00",
        ),
    )


def split(
    start: int,
    end: int,
) -> list[dict[str, str]]:
    from datetime import datetime, timezone

    def iso(value: int) -> str:
        return datetime.fromtimestamp(
            value / 1000,
            tz=timezone.utc,
        ).isoformat()

    return [
        {
            "name": "development",
            "start": iso(start),
            "end_exclusive": iso(end),
        }
    ]


def test_parse_decimal_rejects_non_finite() -> None:
    assert parse_decimal("1.25").is_finite()

    try:
        parse_decimal("NaN")
    except ValueError:
        pass
    else:
        raise AssertionError(
            "NaN should not be accepted"
        )


def test_safe_relative_path() -> None:
    root = Path("/tmp/mission87-root")

    assert safe_relative_path(
        root / "raw" / "file.gz",
        root,
    )
    assert not safe_relative_path(
        "/tmp/outside/file.gz",
        root,
    )


def test_perfect_bar_series_certifies(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "bars.db"
    ensure_mission86_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        for index in range(3):
            insert_bar(
                conn,
                stream="spot_ohlcv",
                symbol="BTCUSDT",
                timestamp=(
                    START_MS
                    + index * INTERVAL_MS
                ),
            )

        conn.commit()

        result = audit_bar_series(
            conn,
            contract_hash_value=CONTRACT_HASH,
            stream="spot_ohlcv",
            symbol="BTCUSDT",
            start_time_ms=START_MS,
            end_time_exclusive_ms=(
                START_MS + 3 * INTERVAL_MS
            ),
            splits=split(
                START_MS,
                START_MS + 3 * INTERVAL_MS,
            ),
        )

    assert result["certification_status"] == (
        CERTIFICATION_STATUS
    )
    assert result["gap_count"] == 0
    assert result["invalid_ohlc_count"] == 0


def test_bar_gap_is_rejected(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "bars.db"
    ensure_mission86_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        insert_bar(
            conn,
            stream="spot_ohlcv",
            symbol="BTCUSDT",
            timestamp=START_MS,
        )
        insert_bar(
            conn,
            stream="spot_ohlcv",
            symbol="BTCUSDT",
            timestamp=(
                START_MS + 2 * INTERVAL_MS
            ),
        )

        conn.commit()

        result = audit_bar_series(
            conn,
            contract_hash_value=CONTRACT_HASH,
            stream="spot_ohlcv",
            symbol="BTCUSDT",
            start_time_ms=START_MS,
            end_time_exclusive_ms=(
                START_MS + 3 * INTERVAL_MS
            ),
            splits=split(
                START_MS,
                START_MS + 3 * INTERVAL_MS,
            ),
        )

    assert result["certification_status"] == (
        REJECTED_STATUS
    )
    assert result["missing_timestamp_count"] == 1


def test_invalid_ohlc_is_rejected(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "bars.db"
    ensure_mission86_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        insert_bar(
            conn,
            stream="spot_ohlcv",
            symbol="BTCUSDT",
            timestamp=START_MS,
            open_price="100",
            high_price="90",
            low_price="80",
            close_price="95",
        )

        conn.commit()

        result = audit_bar_series(
            conn,
            contract_hash_value=CONTRACT_HASH,
            stream="spot_ohlcv",
            symbol="BTCUSDT",
            start_time_ms=START_MS,
            end_time_exclusive_ms=(
                START_MS + INTERVAL_MS
            ),
            splits=split(
                START_MS,
                START_MS + INTERVAL_MS,
            ),
        )

    assert result["certification_status"] == (
        REJECTED_STATUS
    )
    assert result["invalid_ohlc_count"] == 1


def test_funding_five_millisecond_alignment_certifies(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "funding.db"
    ensure_mission86_schema(db_path)

    end = START_MS + 3 * FUNDING_INTERVAL_MS

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        for index in range(3):
            slot = (
                START_MS
                + index * FUNDING_INTERVAL_MS
            )

            insert_bar(
                conn,
                stream="mark_price_ohlcv",
                symbol="BTCUSDT",
                timestamp=slot,
                open_price="100",
                high_price="101",
                low_price="99",
                close_price="100",
            )

            insert_funding(
                conn,
                symbol="BTCUSDT",
                timestamp=(
                    slot + (5 if index else 0)
                ),
            )

        conn.commit()

        result = audit_funding_series(
            conn,
            contract_hash_value=CONTRACT_HASH,
            symbol="BTCUSDT",
            start_time_ms=START_MS,
            end_time_exclusive_ms=end,
            splits=split(
                START_MS,
                end,
            ),
        )

    assert result["certification_status"] == (
        CERTIFICATION_STATUS
    )
    assert result["alignment_error_count"] == 0
    assert result["missing_timestamp_count"] == 0


def test_missing_funding_slot_is_rejected(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "funding.db"
    ensure_mission86_schema(db_path)

    end = START_MS + 3 * FUNDING_INTERVAL_MS

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        for index in (0, 2):
            slot = (
                START_MS
                + index * FUNDING_INTERVAL_MS
            )

            insert_bar(
                conn,
                stream="mark_price_ohlcv",
                symbol="BTCUSDT",
                timestamp=slot,
            )
            insert_funding(
                conn,
                symbol="BTCUSDT",
                timestamp=slot,
            )

        conn.commit()

        result = audit_funding_series(
            conn,
            contract_hash_value=CONTRACT_HASH,
            symbol="BTCUSDT",
            start_time_ms=START_MS,
            end_time_exclusive_ms=end,
            splits=split(
                START_MS,
                end,
            ),
        )

    assert result["certification_status"] == (
        REJECTED_STATUS
    )
    assert result["missing_timestamp_count"] == 1


def test_nearest_funding_slot_tolerance() -> None:
    assert nearest_funding_slot(
        START_MS + 5,
        START_MS,
    ) == START_MS

    assert nearest_funding_slot(
        START_MS
        + FUNDING_INTERVAL_MS
        + 5,
        START_MS,
    ) == START_MS + FUNDING_INTERVAL_MS


def test_cross_stream_consistency_passes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "cross.db"
    ensure_mission86_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        for stream in (
            "spot_ohlcv",
            "perpetual_ohlcv",
            "mark_price_ohlcv",
            "index_price_ohlcv",
        ):
            insert_bar(
                conn,
                stream=stream,
                symbol="BTCUSDT",
                timestamp=START_MS,
            )

        conn.commit()

        result = audit_cross_stream_consistency(
            conn,
            contract_hash_value=CONTRACT_HASH,
            symbol="BTCUSDT",
            expected_count=1,
        )

    assert result["status"] == "PASS"
    assert result["mismatch_count"] == 0


def test_cross_stream_symbol_mismatch_fails(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "cross.db"
    ensure_mission86_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        insert_bar(
            conn,
            stream="spot_ohlcv",
            symbol="BTCUSDT",
            timestamp=START_MS,
            close_price="100",
        )

        for stream in (
            "perpetual_ohlcv",
            "mark_price_ohlcv",
            "index_price_ohlcv",
        ):
            insert_bar(
                conn,
                stream=stream,
                symbol="BTCUSDT",
                timestamp=START_MS,
                open_price="1000",
                high_price="1020",
                low_price="990",
                close_price="1010",
            )

        conn.commit()

        result = audit_cross_stream_consistency(
            conn,
            contract_hash_value=CONTRACT_HASH,
            symbol="BTCUSDT",
            expected_count=1,
        )

    assert result["status"] == "FAIL"
    assert result["mismatch_count"] == 1


def create_raw_fixture(
    db_path: Path,
    data_root: Path,
    *,
    tamper: bool = False,
) -> None:
    ensure_mission86_schema(db_path)

    payload = [
        [
            START_MS,
            "100",
            "102",
            "99",
            "101",
            "10",
            START_MS + INTERVAL_MS - 1,
            "1000",
            5,
            "0",
            "0",
            "0",
        ]
    ]

    body = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")

    url = (
        "https://data-api.binance.vision/"
        "api/v3/klines"
    )

    params = {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "startTime": START_MS,
        "endTime": (
            START_MS + INTERVAL_MS - 1
        ),
        "limit": 1000,
    }

    request_identity = canonical_json(
        {
            "contract_hash": CONTRACT_HASH,
            "method": "GET",
            "url": url,
            "params": params,
        }
    ).encode("utf-8")

    response_hash = sha256_bytes(
        request_identity + b"\n" + body
    )

    raw_path = (
        data_root
        / "raw"
        / "spot_ohlcv"
        / "BTCUSDT"
        / f"{response_hash}.json.gz"
    )

    raw_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    raw_path.write_bytes(
        gzip.compress(
            (
                body + b"tampered"
                if tamper
                else body
            ),
            mtime=0,
        )
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO mission86_raw_responses (
                response_hash,
                contract_hash,
                captured_at,
                stream,
                symbol,
                request_method,
                request_url,
                request_params_json,
                http_status,
                body_sha256,
                raw_path,
                response_row_count,
                response_headers_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                response_hash,
                CONTRACT_HASH,
                "2026-07-12T00:00:00+00:00",
                "spot_ohlcv",
                "BTCUSDT",
                "GET",
                url,
                canonical_json(params),
                200,
                sha256_bytes(body),
                str(raw_path),
                1,
                "{}",
            ),
        )

        insert_bar(
            conn,
            stream="spot_ohlcv",
            symbol="BTCUSDT",
            timestamp=START_MS,
            response_hash=response_hash,
            source_url=url,
        )

        conn.commit()


def test_raw_to_normalized_equivalence(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "raw.db"
    data_root = tmp_path / "data"

    create_raw_fixture(
        db_path,
        data_root,
    )

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        result = audit_raw_responses(
            conn,
            contract_hash_value=CONTRACT_HASH,
            data_root=data_root,
            start_time_ms=START_MS,
            end_time_exclusive_ms=(
                START_MS + INTERVAL_MS
            ),
        )

    assert result["body_hash_mismatch_count"] == 0
    assert result["response_hash_mismatch_count"] == 0
    assert result["missing_normalized_bars"] == 0
    assert result["extra_normalized_bars"] == 0
    assert result["mismatched_normalized_bars"] == 0


def test_tampered_raw_body_is_detected(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "raw.db"
    data_root = tmp_path / "data"

    create_raw_fixture(
        db_path,
        data_root,
        tamper=True,
    )

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        result = audit_raw_responses(
            conn,
            contract_hash_value=CONTRACT_HASH,
            data_root=data_root,
            start_time_ms=START_MS,
            end_time_exclusive_ms=(
                START_MS + INTERVAL_MS
            ),
        )

    assert result["body_hash_mismatch_count"] == 1
    assert result["response_hash_mismatch_count"] == 1


def test_certificate_hash_is_deterministic(
    tmp_path: Path,
) -> None:
    path = tmp_path / "certificate.json"
    core = {
        "status": CERTIFICATION_STATUS,
        "series": 15,
    }

    first_hash, _ = write_certificate_file(
        path,
        core,
        "2026-07-12T00:00:00+00:00",
    )

    second_hash, envelope = (
        write_certificate_file(
            path,
            core,
            "2026-07-12T01:00:00+00:00",
        )
    )

    assert first_hash == second_hash
    assert (
        envelope["certificate_hash_sha256"]
        == first_hash
    )


def test_mission87_schema_is_created(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mission87.db"
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

    assert "mission87_certification_runs" in tables
    assert (
        "mission87_series_certifications"
        in tables
    )
    assert "mission87_quality_checks" in tables
    assert "mission87_dataset_certificates" in tables


def test_mission87_documentation_is_authoritative() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    required_docs = (
        "README.md",
        "docs/PROJECT_SOURCE_OF_TRUTH.md",
        "docs/ROADMAP.md",
        "docs/MISSION_INDEX.md",
        "docs/ARCHITECTURE_STATE.md",
        "docs/INSTITUTIONAL_ALPHA_RESEARCH_PLAN.md",
        "docs/DECISION_LOG.md",
        "docs/CHANGELOG.md",
        "docs/DELTA_AUTONOMOUS_BOT_ROADMAP.md",
    )

    for relative_path in required_docs:
        text = (
            repo_root / relative_path
        ).read_text(encoding="utf-8")

        assert (
            "<!-- MISSION-87-CERTIFICATION:START -->"
            in text
        )
        assert (
            "<!-- MISSION-87-CERTIFICATION:END -->"
            in text
        )
        assert (
            "Mission 87 Dataset Certification and Quality Gate"
            in text
        )
        assert (
            "Mission 88 Execution and Cost Reality Model"
            in text
        )
        assert (
            "no strategy backtest"
            in text.lower()
        )
