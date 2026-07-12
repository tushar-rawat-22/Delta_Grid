"""Mission 87: Dataset Certification and Quality Gate.

Mission 87 independently certifies the Mission 86 real-market dataset.

The certification checks:

- authoritative Mission 85 and Mission 86 lineage;
- Mission 86 manifest integrity;
- raw gzip file presence and containment;
- raw body and response hashes;
- raw JSON row counts;
- exact raw-to-normalized equivalence;
- hourly continuity and chronological split coverage;
- duplicate and out-of-window observations;
- OHLC and volume integrity;
- settled funding schedule and value integrity;
- funding-to-mark-price consistency;
- cross-stream symbol consistency;
- absence of synthetic or fallback sources;
- research-only and execution-blocked safety controls.

Mission 87 performs no strategy backtest, return calculation, parameter
selection, model training, model promotion, signal generation, order
submission, signing, private-key use, paid API use, capital deployment, or
profitability analysis.

The untouched holdout is inspected only through blinded structural quality
checks. No holdout prices, returns, strategy outcomes, or performance
statistics are reported.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

from offchain.backtest.mission86_real_market_data_foundation import (
    ALLOWED_HOSTS,
    BAR_STREAMS,
    CANONICAL_INTERVAL,
    EXPECTED_CONTRACT_HASH,
    INTERVAL_MS,
    STREAMS,
    canonical_json,
    load_authoritative_contract,
    normalize_bar,
    normalize_funding,
    parse_utc_ms,
    sha256_bytes,
)
from offchain.research.funding_carry_research_contract import (
    CAPITAL_DEPLOYMENT,
    CONTRACT_ID,
    LIVE_ORDER_SENT,
    LIVE_TRADING,
)


SOURCE_RUN_LABEL = "mission86-final-check"

EXPECTED_SOURCE_MANIFEST_HASH = (
    "a6cb2ecaea2d02cf30a977436004bda74085db608f6b66500f5922292f650a96"
)

CERTIFICATION_STATUS = (
    "CERTIFIED_FOR_RESEARCH_PENDING_EXECUTION_COST_MODEL"
)
REJECTED_STATUS = (
    "REJECTED_DATASET_REQUIRES_MISSION86_REMEDIATION"
)

MISSION87_STATUS_COMPLETE = (
    "COMPLETE_REAL_MARKET_DATASET_CERTIFICATION"
)
MISSION87_STATUS_BLOCKED = "MISSION87_DATASET_CERTIFICATION_BLOCKED"

MISSION88_STATUS_READY = (
    "READY_FOR_EXECUTION_AND_COST_REALITY_MODEL"
)
MISSION88_STATUS_BLOCKED = (
    "BLOCKED_PENDING_DATASET_REMEDIATION"
)

GLOBAL_VERDICT_COMPLETE = (
    "MISSION87_DATASET_CERTIFIED_NO_ALPHA_EVALUATION"
)
GLOBAL_VERDICT_BLOCKED = (
    "MISSION87_DATASET_REJECTED_OR_UNCERTIFIED"
)

NEXT_MISSION = "Mission 88 Execution and Cost Reality Model"

DEFAULT_DB_PATH = Path("offchain/deltagrid.db")
DEFAULT_CONTRACT_PATH = Path(
    "offchain/research/contracts/"
    "mission85_funding_carry_charter_v1.json"
)
DEFAULT_MISSION86_DATA_ROOT = Path("offchain/data/mission86")
DEFAULT_CERTIFICATE_PATH = Path(
    "offchain/data/mission87/certificate.json"
)

FUNDING_INTERVAL_MS = 8 * INTERVAL_MS
FUNDING_ALIGNMENT_TOLERANCE_MS = 10_000

MAX_CROSS_STREAM_DEVIATION_RATIO = Decimal("0.25")
MAX_FUNDING_MARK_DEVIATION_RATIO = Decimal("0.25")
MAX_ABSOLUTE_FUNDING_RATE = Decimal("0.05")

CHECK_PASS = "PASS"
CHECK_FAIL = "FAIL"

BAR_SERIES_COUNT = 12
FUNDING_SERIES_COUNT = 3
TOTAL_SERIES_COUNT = 15


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def parse_decimal(value: Any) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid decimal value: {value}") from exc

    if not parsed.is_finite():
        raise ValueError(f"non-finite decimal value: {value}")

    return parsed


def stable_decimal(value: Decimal) -> str:
    return format(
        value.quantize(Decimal("0.000001")),
        "f",
    )


def safe_relative_path(
    path_value: str | Path,
    root_value: str | Path,
) -> bool:
    try:
        path = Path(path_value).resolve()
        root = Path(root_value).resolve()
        return path.is_relative_to(root)
    except (OSError, RuntimeError):
        return False


def expected_split_counts(
    contract: Mapping[str, Any],
    interval_ms: int,
) -> dict[str, int]:
    result: dict[str, int] = {}

    for split in contract["research_splits"]:
        start = parse_utc_ms(split["start"])
        end = parse_utc_ms(split["end_exclusive"])

        result[str(split["name"])] = (
            end - start
        ) // interval_ms

    return result


def make_check(
    category: str,
    name: str,
    passed: bool,
    observed: Any,
    expected: Any,
    reason: str,
) -> dict[str, Any]:
    return {
        "check_category": category,
        "check_name": name,
        "check_status": CHECK_PASS if passed else CHECK_FAIL,
        "observed_value": str(observed),
        "expected_value": str(expected),
        "check_reason": reason,
    }


def ensure_schema(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS
                mission87_certification_runs (
                certification_run_label TEXT PRIMARY KEY,
                source_run_label TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                contract_hash TEXT NOT NULL,
                source_manifest_hash TEXT NOT NULL,
                certificate_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                certification_status TEXT NOT NULL,
                mission87_status TEXT NOT NULL,
                bar_series_count INTEGER NOT NULL,
                funding_series_count INTEGER NOT NULL,
                certified_series_count INTEGER NOT NULL,
                rejected_series_count INTEGER NOT NULL,
                raw_response_count INTEGER NOT NULL,
                market_bar_count INTEGER NOT NULL,
                funding_rate_count INTEGER NOT NULL,
                quality_check_count INTEGER NOT NULL,
                pass_check_count INTEGER NOT NULL,
                fail_check_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                mission88_status TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                next_mission TEXT NOT NULL,
                holdout_quality_only INTEGER NOT NULL,
                holdout_performance_evaluated INTEGER NOT NULL,
                backtesting_performed INTEGER NOT NULL,
                profitability_analyzed INTEGER NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                summary_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS
                mission87_series_certifications (
                certification_run_label TEXT NOT NULL,
                source_run_label TEXT NOT NULL,
                stream TEXT NOT NULL,
                symbol TEXT NOT NULL,
                series_type TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                expected_row_count INTEGER NOT NULL,
                series_hash TEXT NOT NULL,
                certification_status TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                PRIMARY KEY (
                    certification_run_label,
                    stream,
                    symbol
                )
            );

            CREATE TABLE IF NOT EXISTS
                mission87_quality_checks (
                check_id TEXT PRIMARY KEY,
                certification_run_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                check_category TEXT NOT NULL,
                check_name TEXT NOT NULL,
                check_status TEXT NOT NULL,
                observed_value TEXT NOT NULL,
                expected_value TEXT NOT NULL,
                check_reason TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS
                mission87_dataset_certificates (
                certification_run_label TEXT PRIMARY KEY,
                source_run_label TEXT NOT NULL,
                contract_hash TEXT NOT NULL,
                source_manifest_hash TEXT NOT NULL,
                certificate_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                certificate_path TEXT NOT NULL,
                certification_status TEXT NOT NULL,
                certificate_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS
                idx_mission87_series_status
            ON mission87_series_certifications (
                certification_status,
                stream,
                symbol
            );

            DROP VIEW IF EXISTS
                mission86_stream_coverage_effective;

            CREATE VIEW
                mission86_stream_coverage_effective
            AS
            SELECT
                coverage.*,
                COALESCE(
                    certification.certification_status,
                    coverage.certification_status
                ) AS effective_certification_status,
                certification.series_hash
                    AS certified_series_hash,
                certification.certification_run_label
                    AS certified_by_run_label
            FROM mission86_stream_coverage AS coverage
            LEFT JOIN mission87_series_certifications
                AS certification
              ON certification.rowid = (
                  SELECT MAX(latest.rowid)
                  FROM mission87_series_certifications
                      AS latest
                  WHERE latest.source_run_label =
                        coverage.run_label
                    AND latest.stream = coverage.stream
                    AND latest.symbol = coverage.symbol
              );
            """
        )
        conn.commit()


def load_source_run(
    conn: sqlite3.Connection,
    source_run_label: str,
) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT *
        FROM mission86_ingestion_runs
        WHERE run_label = ?
        """,
        (source_run_label,),
    ).fetchone()

    if row is None:
        raise RuntimeError(
            f"Mission 86 source run not found: {source_run_label}"
        )

    return row


def verify_manifest(
    conn: sqlite3.Connection,
    *,
    source_run_label: str,
    data_root: str | Path,
) -> dict[str, Any]:
    source_run = load_source_run(
        conn,
        source_run_label,
    )

    manifest_row = conn.execute(
        """
        SELECT *
        FROM mission86_dataset_manifests
        WHERE run_label = ?
        """,
        (source_run_label,),
    ).fetchone()

    if manifest_row is None:
        return {
            "manifest_found": False,
            "manifest_path_safe": False,
            "manifest_file_found": False,
            "manifest_file_is_symlink": False,
            "manifest_json_valid": False,
            "manifest_hash_valid": False,
            "manifest_db_file_match": False,
            "manifest_contract_match": False,
            "manifest_source_hash_match": False,
            "manifest_scope_safe": False,
            "manifest_raw_response_count": 0,
            "manifest_coverage_count": 0,
            "computed_manifest_hash": "",
        }

    manifest_path = Path(
        manifest_row["manifest_path"]
    )

    path_safe = safe_relative_path(
        manifest_path,
        data_root,
    )
    file_found = manifest_path.is_file()
    is_symlink = manifest_path.is_symlink()

    envelope: dict[str, Any] = {}
    json_valid = False

    if file_found and path_safe and not is_symlink:
        try:
            loaded = json.loads(
                manifest_path.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(loaded, dict):
                envelope = loaded
                json_valid = True
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            json_valid = False

    core = (
        envelope.get("manifest", {})
        if json_valid
        else {}
    )

    computed_hash = (
        sha256_bytes(
            canonical_json(core).encode("utf-8")
        )
        if isinstance(core, dict) and core
        else ""
    )

    stored_file_hash = (
        envelope.get("manifest_hash_sha256")
        if json_valid
        else None
    )

    try:
        stored_db_envelope = json.loads(
            manifest_row["manifest_json"]
        )
    except (
        TypeError,
        json.JSONDecodeError,
    ):
        stored_db_envelope = None

    safety = (
        core.get("safety", {})
        if isinstance(core, dict)
        else {}
    )

    raw_responses = (
        core.get("raw_responses", [])
        if isinstance(core, dict)
        else []
    )

    coverage = (
        core.get("coverage", [])
        if isinstance(core, dict)
        else []
    )

    scope_safe = (
        core.get("certification_status")
        == "UNCERTIFIED_PENDING_MISSION87"
        and safety.get("backtesting_performed")
        is False
        and safety.get("holdout_evaluated")
        is False
        and safety.get("profitability_analyzed")
        is False
        and safety.get("live_trading")
        == LIVE_TRADING
        and safety.get("live_order_sent")
        == LIVE_ORDER_SENT
        and safety.get("capital_deployment")
        == CAPITAL_DEPLOYMENT
    )

    return {
        "manifest_found": True,
        "manifest_path_safe": path_safe,
        "manifest_file_found": file_found,
        "manifest_file_is_symlink": is_symlink,
        "manifest_json_valid": json_valid,
        "manifest_hash_valid": (
            computed_hash
            == stored_file_hash
            == manifest_row["manifest_hash"]
            == source_run["manifest_hash"]
        ),
        "manifest_db_file_match": (
            stored_db_envelope == envelope
        ),
        "manifest_contract_match": (
            isinstance(core, dict)
            and core.get("contract_hash")
            == EXPECTED_CONTRACT_HASH
        ),
        "manifest_source_hash_match": (
            source_run["manifest_hash"]
            == EXPECTED_SOURCE_MANIFEST_HASH
        ),
        "manifest_scope_safe": scope_safe,
        "manifest_raw_response_count": len(
            raw_responses
        ),
        "manifest_coverage_count": len(coverage),
        "computed_manifest_hash": computed_hash,
    }


def prepare_expected_raw_tables(
    conn: sqlite3.Connection,
) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS temp.mission87_expected_bars;
        DROP TABLE IF EXISTS temp.mission87_expected_funding;

        CREATE TEMP TABLE mission87_expected_bars (
            stream TEXT NOT NULL,
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            open_time_ms INTEGER NOT NULL,
            close_time_ms INTEGER NOT NULL,
            open_price TEXT NOT NULL,
            high_price TEXT NOT NULL,
            low_price TEXT NOT NULL,
            close_price TEXT NOT NULL,
            volume TEXT,
            quote_volume TEXT,
            trade_count INTEGER,
            response_hash TEXT NOT NULL,
            source_url TEXT NOT NULL,
            PRIMARY KEY (
                stream,
                symbol,
                interval,
                open_time_ms
            )
        );

        CREATE TEMP TABLE mission87_expected_funding (
            symbol TEXT NOT NULL,
            funding_time_ms INTEGER NOT NULL,
            funding_rate TEXT NOT NULL,
            mark_price TEXT,
            response_hash TEXT NOT NULL,
            source_url TEXT NOT NULL,
            PRIMARY KEY (
                symbol,
                funding_time_ms
            )
        );
        """
    )


def audit_raw_responses(
    conn: sqlite3.Connection,
    *,
    contract_hash_value: str,
    data_root: str | Path,
    start_time_ms: int,
    end_time_exclusive_ms: int,
) -> dict[str, Any]:
    prepare_expected_raw_tables(conn)

    rows = conn.execute(
        """
        SELECT *
        FROM mission86_raw_responses
        WHERE contract_hash = ?
        ORDER BY
            stream,
            symbol,
            request_params_json,
            response_hash
        """,
        (contract_hash_value,),
    ).fetchall()

    missing_file_count = 0
    outside_root_count = 0
    symlink_count = 0
    gzip_error_count = 0
    body_hash_mismatch_count = 0
    response_hash_mismatch_count = 0
    invalid_json_count = 0
    row_count_mismatch_count = 0
    invalid_scope_count = 0
    normalization_error_count = 0
    payload_row_count = 0
    duplicate_raw_key_count = 0

    for row in rows:
        raw_path = Path(row["raw_path"])
        parsed_url = urlparse(row["request_url"])

        if (
            row["request_method"] != "GET"
            or row["http_status"] != 200
            or row["stream"] not in STREAMS
            or row["symbol"] not in {
                "BTCUSDT",
                "ETHUSDT",
                "SOLUSDT",
            }
            or parsed_url.scheme != "https"
            or parsed_url.hostname not in ALLOWED_HOSTS
        ):
            invalid_scope_count += 1

        if not safe_relative_path(
            raw_path,
            data_root,
        ):
            outside_root_count += 1
            continue

        if raw_path.is_symlink():
            symlink_count += 1
            continue

        if not raw_path.is_file():
            missing_file_count += 1
            continue

        try:
            body = gzip.decompress(
                raw_path.read_bytes()
            )
        except (OSError, EOFError, gzip.BadGzipFile):
            gzip_error_count += 1
            continue

        if sha256_bytes(body) != row["body_sha256"]:
            body_hash_mismatch_count += 1

        try:
            request_params = json.loads(
                row["request_params_json"]
            )
        except (
            TypeError,
            json.JSONDecodeError,
        ):
            request_params = None
            invalid_json_count += 1

        if not isinstance(request_params, dict):
            continue

        request_identity = canonical_json(
            {
                "contract_hash": contract_hash_value,
                "method": row["request_method"],
                "url": row["request_url"],
                "params": request_params,
            }
        ).encode("utf-8")

        expected_response_hash = sha256_bytes(
            request_identity + b"\n" + body
        )

        if expected_response_hash != row["response_hash"]:
            response_hash_mismatch_count += 1

        try:
            payload = json.loads(
                body.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            invalid_json_count += 1
            continue

        if not isinstance(payload, list):
            invalid_json_count += 1
            continue

        if len(payload) != row["response_row_count"]:
            row_count_mismatch_count += 1

        payload_row_count += len(payload)

        if row["stream"] in BAR_STREAMS:
            batch: list[tuple[Any, ...]] = []

            for raw_item in payload:
                try:
                    item = normalize_bar(
                        row["stream"],
                        row["symbol"],
                        raw_item,
                    )
                except (
                    TypeError,
                    ValueError,
                    IndexError,
                ):
                    normalization_error_count += 1
                    continue

                timestamp = int(item["open_time_ms"])

                if not (
                    start_time_ms
                    <= timestamp
                    < end_time_exclusive_ms
                ):
                    continue

                batch.append(
                    (
                        row["stream"],
                        row["symbol"],
                        CANONICAL_INTERVAL,
                        timestamp,
                        int(item["close_time_ms"]),
                        item["open_price"],
                        item["high_price"],
                        item["low_price"],
                        item["close_price"],
                        item["volume"],
                        item["quote_volume"],
                        item["trade_count"],
                        row["response_hash"],
                        row["request_url"],
                    )
                )

            before = conn.total_changes

            conn.executemany(
                """
                INSERT OR IGNORE INTO
                    mission87_expected_bars (
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
                        source_url
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?
                    )
                """,
                batch,
            )

            inserted = conn.total_changes - before
            duplicate_raw_key_count += (
                len(batch) - inserted
            )

        else:
            batch = []

            for raw_item in payload:
                try:
                    item = normalize_funding(
                        row["symbol"],
                        raw_item,
                    )
                except (
                    TypeError,
                    ValueError,
                    KeyError,
                ):
                    normalization_error_count += 1
                    continue

                timestamp = int(
                    item["funding_time_ms"]
                )

                if not (
                    start_time_ms
                    <= timestamp
                    < end_time_exclusive_ms
                ):
                    continue

                batch.append(
                    (
                        row["symbol"],
                        timestamp,
                        item["funding_rate"],
                        item["mark_price"],
                        row["response_hash"],
                        row["request_url"],
                    )
                )

            before = conn.total_changes

            conn.executemany(
                """
                INSERT OR IGNORE INTO
                    mission87_expected_funding (
                        symbol,
                        funding_time_ms,
                        funding_rate,
                        mark_price,
                        response_hash,
                        source_url
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                batch,
            )

            inserted = conn.total_changes - before
            duplicate_raw_key_count += (
                len(batch) - inserted
            )

    expected_bar_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission87_expected_bars
            """
        ).fetchone()[0]
    )

    expected_funding_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission87_expected_funding
            """
        ).fetchone()[0]
    )

    actual_bar_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission86_market_bars
            WHERE contract_hash = ?
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    )

    actual_funding_count = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission86_funding_rates
            WHERE contract_hash = ?
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    )

    missing_normalized_bars = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission87_expected_bars AS expected
            LEFT JOIN mission86_market_bars AS actual
              ON actual.contract_hash = ?
             AND actual.stream = expected.stream
             AND actual.symbol = expected.symbol
             AND actual.interval = expected.interval
             AND actual.open_time_ms =
                 expected.open_time_ms
            WHERE actual.open_time_ms IS NULL
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    )

    extra_normalized_bars = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission86_market_bars AS actual
            LEFT JOIN mission87_expected_bars AS expected
              ON expected.stream = actual.stream
             AND expected.symbol = actual.symbol
             AND expected.interval = actual.interval
             AND expected.open_time_ms =
                 actual.open_time_ms
            WHERE actual.contract_hash = ?
              AND expected.open_time_ms IS NULL
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    )

    mismatched_normalized_bars = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission86_market_bars AS actual
            JOIN mission87_expected_bars AS expected
              ON expected.stream = actual.stream
             AND expected.symbol = actual.symbol
             AND expected.interval = actual.interval
             AND expected.open_time_ms =
                 actual.open_time_ms
            WHERE actual.contract_hash = ?
              AND (
                    actual.close_time_ms !=
                        expected.close_time_ms
                 OR actual.open_price !=
                        expected.open_price
                 OR actual.high_price !=
                        expected.high_price
                 OR actual.low_price !=
                        expected.low_price
                 OR actual.close_price !=
                        expected.close_price
                 OR actual.volume IS NOT
                        expected.volume
                 OR actual.quote_volume IS NOT
                        expected.quote_volume
                 OR actual.trade_count IS NOT
                        expected.trade_count
                 OR actual.response_hash !=
                        expected.response_hash
                 OR actual.source_url !=
                        expected.source_url
              )
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    )

    missing_normalized_funding = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission87_expected_funding AS expected
            LEFT JOIN mission86_funding_rates AS actual
              ON actual.contract_hash = ?
             AND actual.symbol = expected.symbol
             AND actual.funding_time_ms =
                 expected.funding_time_ms
            WHERE actual.funding_time_ms IS NULL
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    )

    extra_normalized_funding = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission86_funding_rates AS actual
            LEFT JOIN mission87_expected_funding AS expected
              ON expected.symbol = actual.symbol
             AND expected.funding_time_ms =
                 actual.funding_time_ms
            WHERE actual.contract_hash = ?
              AND expected.funding_time_ms IS NULL
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    )

    mismatched_normalized_funding = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM mission86_funding_rates AS actual
            JOIN mission87_expected_funding AS expected
              ON expected.symbol = actual.symbol
             AND expected.funding_time_ms =
                 actual.funding_time_ms
            WHERE actual.contract_hash = ?
              AND (
                    actual.funding_rate !=
                        expected.funding_rate
                 OR actual.mark_price IS NOT
                        expected.mark_price
                 OR actual.response_hash !=
                        expected.response_hash
                 OR actual.source_url !=
                        expected.source_url
              )
            """,
            (contract_hash_value,),
        ).fetchone()[0]
    )

    return {
        "raw_response_count": len(rows),
        "payload_row_count": payload_row_count,
        "missing_file_count": missing_file_count,
        "outside_root_count": outside_root_count,
        "symlink_count": symlink_count,
        "gzip_error_count": gzip_error_count,
        "body_hash_mismatch_count": (
            body_hash_mismatch_count
        ),
        "response_hash_mismatch_count": (
            response_hash_mismatch_count
        ),
        "invalid_json_count": invalid_json_count,
        "row_count_mismatch_count": (
            row_count_mismatch_count
        ),
        "invalid_scope_count": invalid_scope_count,
        "normalization_error_count": (
            normalization_error_count
        ),
        "duplicate_raw_key_count": (
            duplicate_raw_key_count
        ),
        "expected_bar_count": expected_bar_count,
        "expected_funding_count": (
            expected_funding_count
        ),
        "actual_bar_count": actual_bar_count,
        "actual_funding_count": (
            actual_funding_count
        ),
        "missing_normalized_bars": (
            missing_normalized_bars
        ),
        "extra_normalized_bars": (
            extra_normalized_bars
        ),
        "mismatched_normalized_bars": (
            mismatched_normalized_bars
        ),
        "missing_normalized_funding": (
            missing_normalized_funding
        ),
        "extra_normalized_funding": (
            extra_normalized_funding
        ),
        "mismatched_normalized_funding": (
            mismatched_normalized_funding
        ),
    }


def audit_bar_series(
    conn: sqlite3.Connection,
    *,
    contract_hash_value: str,
    stream: str,
    symbol: str,
    start_time_ms: int,
    end_time_exclusive_ms: int,
    splits: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT
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
            source_url
        FROM mission86_market_bars
        WHERE contract_hash = ?
          AND stream = ?
          AND symbol = ?
          AND interval = ?
        ORDER BY open_time_ms
        """,
        (
            contract_hash_value,
            stream,
            symbol,
            CANONICAL_INTERVAL,
        ),
    ).fetchall()

    expected_count = (
        end_time_exclusive_ms - start_time_ms
    ) // INTERVAL_MS

    timestamps = [
        int(row["open_time_ms"])
        for row in rows
    ]
    timestamp_set = set(timestamps)

    expected_timestamp_set = set(
        range(
            start_time_ms,
            end_time_exclusive_ms,
            INTERVAL_MS,
        )
    )

    duplicate_timestamp_count = (
        len(timestamps) - len(timestamp_set)
    )

    missing_timestamp_count = len(
        expected_timestamp_set - timestamp_set
    )
    extra_timestamp_count = len(
        timestamp_set - expected_timestamp_set
    )

    gap_count = sum(
        current - previous != INTERVAL_MS
        for previous, current in zip(
            timestamps,
            timestamps[1:],
        )
    )

    alignment_error_count = sum(
        timestamp % INTERVAL_MS != 0
        for timestamp in timestamps
    )

    close_time_error_count = 0
    invalid_decimal_count = 0
    invalid_ohlc_count = 0
    invalid_volume_count = 0
    invalid_auxiliary_field_count = 0

    hasher = hashlib.sha256()

    for row in rows:
        if int(row["close_time_ms"]) != (
            int(row["open_time_ms"])
            + INTERVAL_MS
            - 1
        ):
            close_time_error_count += 1

        try:
            open_price = parse_decimal(
                row["open_price"]
            )
            high_price = parse_decimal(
                row["high_price"]
            )
            low_price = parse_decimal(
                row["low_price"]
            )
            close_price = parse_decimal(
                row["close_price"]
            )
        except ValueError:
            invalid_decimal_count += 1
            continue

        if (
            open_price <= 0
            or high_price <= 0
            or low_price <= 0
            or close_price <= 0
            or low_price > high_price
            or high_price
            < max(open_price, close_price)
            or low_price
            > min(open_price, close_price)
        ):
            invalid_ohlc_count += 1

        if stream in {
            "spot_ohlcv",
            "perpetual_ohlcv",
        }:
            try:
                volume = parse_decimal(
                    row["volume"]
                )
                quote_volume = parse_decimal(
                    row["quote_volume"]
                )

                if (
                    volume < 0
                    or quote_volume < 0
                    or row["trade_count"] is None
                    or int(row["trade_count"]) < 0
                ):
                    invalid_volume_count += 1
            except (
                ValueError,
                TypeError,
            ):
                invalid_volume_count += 1
        else:
            if (
                row["volume"] is not None
                or row["quote_volume"] is not None
                or row["trade_count"] is not None
            ):
                invalid_auxiliary_field_count += 1

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

    split_counts: dict[str, dict[str, int]] = {}
    split_mismatch_count = 0

    for split in splits:
        name = str(split["name"])
        split_start = parse_utc_ms(
            str(split["start"])
        )
        split_end = parse_utc_ms(
            str(split["end_exclusive"])
        )

        actual = sum(
            split_start
            <= timestamp
            < split_end
            for timestamp in timestamps
        )
        expected = (
            split_end - split_start
        ) // INTERVAL_MS

        split_counts[name] = {
            "actual": actual,
            "expected": expected,
        }

        if actual != expected:
            split_mismatch_count += 1

    passed = all(
        value == 0
        for value in (
            duplicate_timestamp_count,
            missing_timestamp_count,
            extra_timestamp_count,
            gap_count,
            alignment_error_count,
            close_time_error_count,
            invalid_decimal_count,
            invalid_ohlc_count,
            invalid_volume_count,
            invalid_auxiliary_field_count,
            split_mismatch_count,
        )
    ) and len(rows) == expected_count

    return {
        "stream": stream,
        "symbol": symbol,
        "series_type": "BAR",
        "row_count": len(rows),
        "expected_row_count": int(expected_count),
        "duplicate_timestamp_count": (
            duplicate_timestamp_count
        ),
        "missing_timestamp_count": (
            missing_timestamp_count
        ),
        "extra_timestamp_count": (
            extra_timestamp_count
        ),
        "gap_count": gap_count,
        "alignment_error_count": (
            alignment_error_count
        ),
        "close_time_error_count": (
            close_time_error_count
        ),
        "invalid_decimal_count": (
            invalid_decimal_count
        ),
        "invalid_ohlc_count": invalid_ohlc_count,
        "invalid_volume_count": (
            invalid_volume_count
        ),
        "invalid_auxiliary_field_count": (
            invalid_auxiliary_field_count
        ),
        "split_mismatch_count": (
            split_mismatch_count
        ),
        "split_counts": split_counts,
        "series_hash": hasher.hexdigest(),
        "certification_status": (
            CERTIFICATION_STATUS
            if passed
            else REJECTED_STATUS
        ),
    }


def nearest_funding_slot(
    timestamp_ms: int,
    start_time_ms: int,
) -> int:
    relative = timestamp_ms - start_time_ms

    slot_number = int(
        round(
            relative / FUNDING_INTERVAL_MS
        )
    )

    return (
        start_time_ms
        + slot_number * FUNDING_INTERVAL_MS
    )


def audit_funding_series(
    conn: sqlite3.Connection,
    *,
    contract_hash_value: str,
    symbol: str,
    start_time_ms: int,
    end_time_exclusive_ms: int,
    splits: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT
            funding_time_ms,
            funding_rate,
            mark_price,
            response_hash,
            source_url
        FROM mission86_funding_rates
        WHERE contract_hash = ?
          AND symbol = ?
        ORDER BY funding_time_ms
        """,
        (
            contract_hash_value,
            symbol,
        ),
    ).fetchall()

    expected_slots = set(
        range(
            start_time_ms,
            end_time_exclusive_ms,
            FUNDING_INTERVAL_MS,
        )
    )

    exact_timestamps = [
        int(row["funding_time_ms"])
        for row in rows
    ]

    duplicate_timestamp_count = (
        len(exact_timestamps)
        - len(set(exact_timestamps))
    )

    observed_slots: list[int] = []
    alignment_error_count = 0
    out_of_window_count = 0
    invalid_rate_count = 0
    invalid_mark_price_count = 0
    mark_reference_missing_count = 0
    mark_reference_mismatch_count = 0

    mark_rows = conn.execute(
        """
        SELECT open_time_ms, open_price
        FROM mission86_market_bars
        WHERE contract_hash = ?
          AND stream = 'mark_price_ohlcv'
          AND symbol = ?
          AND interval = ?
        """,
        (
            contract_hash_value,
            symbol,
            CANONICAL_INTERVAL,
        ),
    ).fetchall()

    mark_open_by_timestamp = {
        int(row["open_time_ms"]): row["open_price"]
        for row in mark_rows
    }

    hasher = hashlib.sha256()

    for row in rows:
        timestamp = int(
            row["funding_time_ms"]
        )

        if not (
            start_time_ms
            <= timestamp
            < end_time_exclusive_ms
        ):
            out_of_window_count += 1

        slot = nearest_funding_slot(
            timestamp,
            start_time_ms,
        )
        observed_slots.append(slot)

        if (
            abs(timestamp - slot)
            > FUNDING_ALIGNMENT_TOLERANCE_MS
        ):
            alignment_error_count += 1

        try:
            funding_rate = parse_decimal(
                row["funding_rate"]
            )

            if (
                abs(funding_rate)
                > MAX_ABSOLUTE_FUNDING_RATE
            ):
                invalid_rate_count += 1
        except ValueError:
            invalid_rate_count += 1

        try:
            funding_mark = parse_decimal(
                row["mark_price"]
            )

            if funding_mark <= 0:
                invalid_mark_price_count += 1
        except ValueError:
            invalid_mark_price_count += 1
            funding_mark = None

        reference_value = mark_open_by_timestamp.get(
            slot
        )

        if reference_value is None:
            mark_reference_missing_count += 1
        elif funding_mark is not None:
            try:
                reference_mark = parse_decimal(
                    reference_value
                )

                if reference_mark <= 0:
                    mark_reference_missing_count += 1
                else:
                    deviation = abs(
                        funding_mark
                        / reference_mark
                        - Decimal("1")
                    )

                    if (
                        deviation
                        > MAX_FUNDING_MARK_DEVIATION_RATIO
                    ):
                        mark_reference_mismatch_count += 1
            except ValueError:
                mark_reference_missing_count += 1

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

    observed_slot_set = set(observed_slots)

    duplicate_slot_count = (
        len(observed_slots)
        - len(observed_slot_set)
    )

    missing_slot_count = len(
        expected_slots - observed_slot_set
    )
    extra_slot_count = len(
        observed_slot_set - expected_slots
    )

    sorted_slots = sorted(observed_slot_set)

    gap_count = sum(
        current - previous
        != FUNDING_INTERVAL_MS
        for previous, current in zip(
            sorted_slots,
            sorted_slots[1:],
        )
    )

    split_counts: dict[str, dict[str, int]] = {}
    split_mismatch_count = 0

    for split in splits:
        name = str(split["name"])
        split_start = parse_utc_ms(
            str(split["start"])
        )
        split_end = parse_utc_ms(
            str(split["end_exclusive"])
        )

        actual = sum(
            split_start
            <= slot
            < split_end
            for slot in observed_slot_set
        )
        expected = (
            split_end - split_start
        ) // FUNDING_INTERVAL_MS

        split_counts[name] = {
            "actual": actual,
            "expected": expected,
        }

        if actual != expected:
            split_mismatch_count += 1

    expected_count = len(expected_slots)

    passed = all(
        value == 0
        for value in (
            duplicate_timestamp_count,
            duplicate_slot_count,
            missing_slot_count,
            extra_slot_count,
            gap_count,
            alignment_error_count,
            out_of_window_count,
            invalid_rate_count,
            invalid_mark_price_count,
            mark_reference_missing_count,
            mark_reference_mismatch_count,
            split_mismatch_count,
        )
    ) and len(rows) == expected_count

    return {
        "stream": "funding_rates",
        "symbol": symbol,
        "series_type": "FUNDING",
        "row_count": len(rows),
        "expected_row_count": expected_count,
        "duplicate_timestamp_count": (
            duplicate_timestamp_count
        ),
        "duplicate_slot_count": (
            duplicate_slot_count
        ),
        "missing_timestamp_count": (
            missing_slot_count
        ),
        "extra_timestamp_count": (
            extra_slot_count
        ),
        "gap_count": gap_count,
        "alignment_error_count": (
            alignment_error_count
        ),
        "out_of_window_count": (
            out_of_window_count
        ),
        "invalid_rate_count": (
            invalid_rate_count
        ),
        "invalid_mark_price_count": (
            invalid_mark_price_count
        ),
        "mark_reference_missing_count": (
            mark_reference_missing_count
        ),
        "mark_reference_mismatch_count": (
            mark_reference_mismatch_count
        ),
        "split_mismatch_count": (
            split_mismatch_count
        ),
        "split_counts": split_counts,
        "series_hash": hasher.hexdigest(),
        "certification_status": (
            CERTIFICATION_STATUS
            if passed
            else REJECTED_STATUS
        ),
    }


def audit_cross_stream_consistency(
    conn: sqlite3.Connection,
    *,
    contract_hash_value: str,
    symbol: str,
    expected_count: int,
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT
            spot.open_time_ms,
            spot.close_price AS spot_close,
            perpetual.close_price
                AS perpetual_close,
            mark.close_price AS mark_close,
            index_price.close_price
                AS index_close
        FROM mission86_market_bars AS spot
        JOIN mission86_market_bars AS perpetual
          ON perpetual.contract_hash =
                spot.contract_hash
         AND perpetual.symbol = spot.symbol
         AND perpetual.interval = spot.interval
         AND perpetual.open_time_ms =
                spot.open_time_ms
         AND perpetual.stream =
                'perpetual_ohlcv'
        JOIN mission86_market_bars AS mark
          ON mark.contract_hash =
                spot.contract_hash
         AND mark.symbol = spot.symbol
         AND mark.interval = spot.interval
         AND mark.open_time_ms =
                spot.open_time_ms
         AND mark.stream =
                'mark_price_ohlcv'
        JOIN mission86_market_bars AS index_price
          ON index_price.contract_hash =
                spot.contract_hash
         AND index_price.symbol = spot.symbol
         AND index_price.interval = spot.interval
         AND index_price.open_time_ms =
                spot.open_time_ms
         AND index_price.stream =
                'index_price_ohlcv'
        WHERE spot.contract_hash = ?
          AND spot.symbol = ?
          AND spot.interval = ?
          AND spot.stream = 'spot_ohlcv'
        ORDER BY spot.open_time_ms
        """,
        (
            contract_hash_value,
            symbol,
            CANONICAL_INTERVAL,
        ),
    ).fetchall()

    invalid_decimal_count = 0
    mismatch_count = 0

    maxima = {
        "spot_index_bps": Decimal("0"),
        "perpetual_mark_bps": Decimal("0"),
        "mark_index_bps": Decimal("0"),
        "spot_perpetual_bps": Decimal("0"),
    }

    for row in rows:
        try:
            spot = parse_decimal(
                row["spot_close"]
            )
            perpetual = parse_decimal(
                row["perpetual_close"]
            )
            mark = parse_decimal(
                row["mark_close"]
            )
            index_price = parse_decimal(
                row["index_close"]
            )
        except ValueError:
            invalid_decimal_count += 1
            continue

        if min(
            spot,
            perpetual,
            mark,
            index_price,
        ) <= 0:
            invalid_decimal_count += 1
            continue

        comparisons = {
            "spot_index_bps": abs(
                spot / index_price
                - Decimal("1")
            ),
            "perpetual_mark_bps": abs(
                perpetual / mark
                - Decimal("1")
            ),
            "mark_index_bps": abs(
                mark / index_price
                - Decimal("1")
            ),
            "spot_perpetual_bps": abs(
                spot / perpetual
                - Decimal("1")
            ),
        }

        if any(
            value
            > MAX_CROSS_STREAM_DEVIATION_RATIO
            for value in comparisons.values()
        ):
            mismatch_count += 1

        for name, value in comparisons.items():
            bps = value * Decimal("10000")

            if bps > maxima[name]:
                maxima[name] = bps

    passed = (
        len(rows) == expected_count
        and invalid_decimal_count == 0
        and mismatch_count == 0
    )

    return {
        "symbol": symbol,
        "joined_row_count": len(rows),
        "expected_row_count": expected_count,
        "invalid_decimal_count": (
            invalid_decimal_count
        ),
        "mismatch_count": mismatch_count,
        "maximum_deviations_bps": {
            key: stable_decimal(value)
            for key, value in maxima.items()
        },
        "status": (
            CHECK_PASS
            if passed
            else CHECK_FAIL
        ),
    }


def write_certificate_file(
    certificate_path: str | Path,
    certificate_core: Mapping[str, Any],
    created_at: str,
) -> tuple[str, dict[str, Any]]:
    path = Path(certificate_path)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    certificate_hash = sha256_bytes(
        canonical_json(certificate_core).encode(
            "utf-8"
        )
    )

    envelope = {
        "certificate_hash_sha256": (
            certificate_hash
        ),
        "created_at": created_at,
        "certificate": certificate_core,
    }

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            envelope,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(path)

    return certificate_hash, envelope


def persist_results(
    conn: sqlite3.Connection,
    *,
    certification_run_label: str,
    source_run_label: str,
    created_at: str,
    certificate_path: str | Path,
    certificate_hash: str,
    certificate_envelope: Mapping[str, Any],
    summary: Mapping[str, Any],
    series: Sequence[Mapping[str, Any]],
    checks: Sequence[Mapping[str, Any]],
) -> None:
    conn.execute(
        """
        DELETE FROM mission87_quality_checks
        WHERE certification_run_label = ?
        """,
        (certification_run_label,),
    )
    conn.execute(
        """
        DELETE FROM mission87_series_certifications
        WHERE certification_run_label = ?
        """,
        (certification_run_label,),
    )
    conn.execute(
        """
        DELETE FROM mission87_certification_runs
        WHERE certification_run_label = ?
        """,
        (certification_run_label,),
    )
    conn.execute(
        """
        DELETE FROM mission87_dataset_certificates
        WHERE certification_run_label = ?
        """,
        (certification_run_label,),
    )

    for index, check in enumerate(checks):
        conn.execute(
            """
            INSERT INTO mission87_quality_checks (
                check_id,
                certification_run_label,
                created_at,
                check_category,
                check_name,
                check_status,
                observed_value,
                expected_value,
                check_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    f"{certification_run_label}-"
                    f"{index + 1:02d}-"
                    f"{check['check_name'].lower()}"
                ),
                certification_run_label,
                created_at,
                check["check_category"],
                check["check_name"],
                check["check_status"],
                check["observed_value"],
                check["expected_value"],
                check["check_reason"],
            ),
        )

    for item in series:
        conn.execute(
            """
            INSERT INTO mission87_series_certifications (
                certification_run_label,
                source_run_label,
                stream,
                symbol,
                series_type,
                row_count,
                expected_row_count,
                series_hash,
                certification_status,
                metrics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                certification_run_label,
                source_run_label,
                item["stream"],
                item["symbol"],
                item["series_type"],
                item["row_count"],
                item["expected_row_count"],
                item["series_hash"],
                item["certification_status"],
                canonical_json(item),
            ),
        )

    conn.execute(
        """
        INSERT INTO mission87_dataset_certificates (
            certification_run_label,
            source_run_label,
            contract_hash,
            source_manifest_hash,
            certificate_hash,
            created_at,
            certificate_path,
            certification_status,
            certificate_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            certification_run_label,
            source_run_label,
            EXPECTED_CONTRACT_HASH,
            EXPECTED_SOURCE_MANIFEST_HASH,
            certificate_hash,
            created_at,
            str(certificate_path),
            summary["certification_status"],
            canonical_json(certificate_envelope),
        ),
    )

    conn.execute(
        """
        INSERT INTO mission87_certification_runs (
            certification_run_label,
            source_run_label,
            contract_id,
            contract_hash,
            source_manifest_hash,
            certificate_hash,
            created_at,
            certification_status,
            mission87_status,
            bar_series_count,
            funding_series_count,
            certified_series_count,
            rejected_series_count,
            raw_response_count,
            market_bar_count,
            funding_rate_count,
            quality_check_count,
            pass_check_count,
            fail_check_count,
            safety_breach_count,
            mission88_status,
            global_verdict,
            next_mission,
            holdout_quality_only,
            holdout_performance_evaluated,
            backtesting_performed,
            profitability_analyzed,
            live_trading,
            live_order_sent,
            capital_deployment,
            summary_json
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            certification_run_label,
            source_run_label,
            CONTRACT_ID,
            EXPECTED_CONTRACT_HASH,
            EXPECTED_SOURCE_MANIFEST_HASH,
            certificate_hash,
            created_at,
            summary["certification_status"],
            summary["mission87_status"],
            summary["bar_series_count"],
            summary["funding_series_count"],
            summary["certified_series_count"],
            summary["rejected_series_count"],
            summary["raw_response_count"],
            summary["market_bar_count"],
            summary["funding_rate_count"],
            summary["quality_check_count"],
            summary["pass_check_count"],
            summary["fail_check_count"],
            summary["safety_breach_count"],
            summary["mission88_status"],
            summary["global_verdict"],
            NEXT_MISSION,
            1,
            0,
            0,
            0,
            LIVE_TRADING,
            LIVE_ORDER_SENT,
            CAPITAL_DEPLOYMENT,
            canonical_json(summary),
        ),
    )

    conn.commit()


def certify_dataset(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    contract_path: str | Path = DEFAULT_CONTRACT_PATH,
    mission86_data_root: str | Path = (
        DEFAULT_MISSION86_DATA_ROOT
    ),
    certificate_path: str | Path = (
        DEFAULT_CERTIFICATE_PATH
    ),
    source_run_label: str = SOURCE_RUN_LABEL,
    certification_run_label: str = (
        "mission87-local-check"
    ),
) -> dict[str, Any]:
    contract = load_authoritative_contract(
        contract_path
    )

    data_contract = contract["data_contract"]
    symbols = list(
        contract["universe"]["symbols"]
    )
    splits = list(
        contract["research_splits"]
    )

    start_time_ms = parse_utc_ms(
        data_contract["start_time"]
    )
    end_time_exclusive_ms = parse_utc_ms(
        data_contract["end_time_exclusive"]
    )

    ensure_schema(db_path)
    created_at = utc_now()

    with sqlite3.connect(Path(db_path)) as conn:
        conn.row_factory = sqlite3.Row

        source_run = load_source_run(
            conn,
            source_run_label,
        )

        manifest_audit = verify_manifest(
            conn,
            source_run_label=source_run_label,
            data_root=mission86_data_root,
        )

        raw_audit = audit_raw_responses(
            conn,
            contract_hash_value=(
                EXPECTED_CONTRACT_HASH
            ),
            data_root=mission86_data_root,
            start_time_ms=start_time_ms,
            end_time_exclusive_ms=(
                end_time_exclusive_ms
            ),
        )

        bar_series = [
            audit_bar_series(
                conn,
                contract_hash_value=(
                    EXPECTED_CONTRACT_HASH
                ),
                stream=stream,
                symbol=symbol,
                start_time_ms=start_time_ms,
                end_time_exclusive_ms=(
                    end_time_exclusive_ms
                ),
                splits=splits,
            )
            for stream in BAR_STREAMS
            for symbol in symbols
        ]

        funding_series = [
            audit_funding_series(
                conn,
                contract_hash_value=(
                    EXPECTED_CONTRACT_HASH
                ),
                symbol=symbol,
                start_time_ms=start_time_ms,
                end_time_exclusive_ms=(
                    end_time_exclusive_ms
                ),
                splits=splits,
            )
            for symbol in symbols
        ]

        all_series = [
            *bar_series,
            *funding_series,
        ]

        expected_bar_count = (
            end_time_exclusive_ms
            - start_time_ms
        ) // INTERVAL_MS

        cross_stream = [
            audit_cross_stream_consistency(
                conn,
                contract_hash_value=(
                    EXPECTED_CONTRACT_HASH
                ),
                symbol=symbol,
                expected_count=int(
                    expected_bar_count
                ),
            )
            for symbol in symbols
        ]

        actual_market_bar_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM mission86_market_bars
                WHERE contract_hash = ?
                """,
                (
                    EXPECTED_CONTRACT_HASH,
                ),
            ).fetchone()[0]
        )

        actual_funding_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM mission86_funding_rates
                WHERE contract_hash = ?
                """,
                (
                    EXPECTED_CONTRACT_HASH,
                ),
            ).fetchone()[0]
        )

        actual_raw_count = int(
            conn.execute(
                """
                SELECT COUNT(*)
                FROM mission86_raw_responses
                WHERE contract_hash = ?
                """,
                (
                    EXPECTED_CONTRACT_HASH,
                ),
            ).fetchone()[0]
        )

        certified_series_count = sum(
            item["certification_status"]
            == CERTIFICATION_STATUS
            for item in all_series
        )
        rejected_series_count = (
            len(all_series)
            - certified_series_count
        )

        total_gap_count = sum(
            int(item.get("gap_count", 0))
            for item in all_series
        )
        total_duplicate_count = sum(
            int(
                item.get(
                    "duplicate_timestamp_count",
                    0,
                )
            )
            + int(
                item.get(
                    "duplicate_slot_count",
                    0,
                )
            )
            for item in all_series
        )

        total_split_mismatch_count = sum(
            int(
                item.get(
                    "split_mismatch_count",
                    0,
                )
            )
            for item in all_series
        )

        total_bar_integrity_errors = sum(
            int(
                item.get(
                    "invalid_decimal_count",
                    0,
                )
            )
            + int(
                item.get(
                    "invalid_ohlc_count",
                    0,
                )
            )
            + int(
                item.get(
                    "invalid_volume_count",
                    0,
                )
            )
            + int(
                item.get(
                    "invalid_auxiliary_field_count",
                    0,
                )
            )
            + int(
                item.get(
                    "close_time_error_count",
                    0,
                )
            )
            for item in bar_series
        )

        total_funding_integrity_errors = sum(
            int(
                item.get(
                    "invalid_rate_count",
                    0,
                )
            )
            + int(
                item.get(
                    "invalid_mark_price_count",
                    0,
                )
            )
            + int(
                item.get(
                    "alignment_error_count",
                    0,
                )
            )
            + int(
                item.get(
                    "mark_reference_missing_count",
                    0,
                )
            )
            + int(
                item.get(
                    "mark_reference_mismatch_count",
                    0,
                )
            )
            for item in funding_series
        )

        cross_stream_failure_count = sum(
            item["status"] != CHECK_PASS
            for item in cross_stream
        )

        source_run_complete = (
            source_run["contract_hash"]
            == EXPECTED_CONTRACT_HASH
            and source_run["manifest_hash"]
            == EXPECTED_SOURCE_MANIFEST_HASH
            and source_run["run_status"]
            == (
                "COMPLETE_UNCERTIFIED_"
                "REAL_MARKET_DATA_FOUNDATION"
            )
            and source_run["fail_check_count"] == 0
            and source_run["safety_breach_count"] == 0
            and source_run["mission87_status"]
            == "READY_FOR_DATASET_CERTIFICATION"
        )

        source_counts_match = (
            source_run["market_bar_count"]
            == actual_market_bar_count
            == raw_audit["actual_bar_count"]
            == raw_audit["expected_bar_count"]
            and source_run["funding_rate_count"]
            == actual_funding_count
            == raw_audit["actual_funding_count"]
            == raw_audit["expected_funding_count"]
            and source_run["raw_response_count"]
            == actual_raw_count
            == raw_audit["raw_response_count"]
        )

        raw_files_valid = all(
            raw_audit[field] == 0
            for field in (
                "missing_file_count",
                "outside_root_count",
                "symlink_count",
                "gzip_error_count",
            )
        )

        raw_body_hashes_valid = (
            raw_audit[
                "body_hash_mismatch_count"
            ]
            == 0
        )

        raw_response_hashes_valid = (
            raw_audit[
                "response_hash_mismatch_count"
            ]
            == 0
        )

        raw_json_valid = all(
            raw_audit[field] == 0
            for field in (
                "invalid_json_count",
                "row_count_mismatch_count",
                "normalization_error_count",
            )
        )

        normalized_equivalent = all(
            raw_audit[field] == 0
            for field in (
                "duplicate_raw_key_count",
                "missing_normalized_bars",
                "extra_normalized_bars",
                "mismatched_normalized_bars",
                "missing_normalized_funding",
                "extra_normalized_funding",
                "mismatched_normalized_funding",
            )
        )

        manifest_valid = all(
            (
                manifest_audit[
                    "manifest_found"
                ],
                manifest_audit[
                    "manifest_path_safe"
                ],
                manifest_audit[
                    "manifest_file_found"
                ],
                not manifest_audit[
                    "manifest_file_is_symlink"
                ],
                manifest_audit[
                    "manifest_json_valid"
                ],
                manifest_audit[
                    "manifest_hash_valid"
                ],
                manifest_audit[
                    "manifest_contract_match"
                ],
                manifest_audit[
                    "manifest_source_hash_match"
                ],
            )
        )

        manifest_db_file_match = (
            manifest_audit[
                "manifest_db_file_match"
            ]
        )

        manifest_scope_safe = (
            manifest_audit[
                "manifest_scope_safe"
            ]
        )

        no_synthetic_or_fallback = (
            raw_audit["invalid_scope_count"]
            == 0
        )

        all_bar_certified = all(
            item["certification_status"]
            == CERTIFICATION_STATUS
            for item in bar_series
        )

        all_funding_certified = all(
            item["certification_status"]
            == CERTIFICATION_STATUS
            for item in funding_series
        )

        all_execution_paths_blocked = (
            LIVE_TRADING == "DISABLED"
            and LIVE_ORDER_SENT == 0
            and CAPITAL_DEPLOYMENT == "BLOCKED"
            and source_run["live_trading"]
            == "DISABLED"
            and source_run["live_order_sent"]
            == 0
            and source_run["capital_deployment"]
            == "BLOCKED"
        )

        checks = [
            make_check(
                "LINEAGE",
                "SOURCE_RUN_COMPLETE",
                source_run_complete,
                source_run["run_status"],
                (
                    "COMPLETE_UNCERTIFIED_"
                    "REAL_MARKET_DATA_FOUNDATION"
                ),
                "Mission 87 requires the verified Mission 86 source run.",
            ),
            make_check(
                "LINEAGE",
                "SOURCE_COUNTS_MATCH",
                source_counts_match,
                (
                    actual_market_bar_count,
                    actual_funding_count,
                    actual_raw_count,
                ),
                (
                    source_run["market_bar_count"],
                    source_run["funding_rate_count"],
                    source_run["raw_response_count"],
                ),
                "Persisted source counts must match independent recounts.",
            ),
            make_check(
                "CONTRACT",
                "CONTRACT_HASH_AUTHORITATIVE",
                source_run["contract_hash"]
                == EXPECTED_CONTRACT_HASH,
                source_run["contract_hash"],
                EXPECTED_CONTRACT_HASH,
                "Certification must remain bound to the locked Mission 85 charter.",
            ),
            make_check(
                "MANIFEST",
                "MANIFEST_HASH_VALID",
                manifest_valid,
                manifest_audit[
                    "computed_manifest_hash"
                ],
                EXPECTED_SOURCE_MANIFEST_HASH,
                "The Mission 86 manifest must be intact and authoritative.",
            ),
            make_check(
                "MANIFEST",
                "MANIFEST_DB_FILE_MATCH",
                manifest_db_file_match,
                manifest_db_file_match,
                True,
                "The manifest file must match the database envelope.",
            ),
            make_check(
                "RESEARCH_BOUNDARY",
                "MANIFEST_RESEARCH_BOUNDARY",
                manifest_scope_safe,
                manifest_scope_safe,
                True,
                "Mission 86 must not have evaluated strategy performance.",
            ),
            make_check(
                "PROVENANCE",
                "RAW_RESPONSE_FILES_PRESENT",
                raw_files_valid,
                {
                    key: raw_audit[key]
                    for key in (
                        "missing_file_count",
                        "outside_root_count",
                        "symlink_count",
                        "gzip_error_count",
                    )
                },
                "all zero",
                "All raw files must exist inside the Mission 86 data root.",
            ),
            make_check(
                "PROVENANCE",
                "RAW_BODY_HASHES_VALID",
                raw_body_hashes_valid,
                raw_audit[
                    "body_hash_mismatch_count"
                ],
                0,
                "Every decompressed raw body must match its stored SHA-256.",
            ),
            make_check(
                "PROVENANCE",
                "RAW_RESPONSE_HASHES_VALID",
                raw_response_hashes_valid,
                raw_audit[
                    "response_hash_mismatch_count"
                ],
                0,
                "Every response hash must bind request identity and body.",
            ),
            make_check(
                "PROVENANCE",
                "RAW_JSON_ROW_COUNTS_VALID",
                raw_json_valid,
                {
                    key: raw_audit[key]
                    for key in (
                        "invalid_json_count",
                        "row_count_mismatch_count",
                        "normalization_error_count",
                    )
                },
                "all zero",
                "Raw responses must decode and match recorded row counts.",
            ),
            make_check(
                "PROVENANCE",
                "NORMALIZED_RAW_EQUIVALENCE",
                normalized_equivalent,
                {
                    key: raw_audit[key]
                    for key in (
                        "missing_normalized_bars",
                        "extra_normalized_bars",
                        "mismatched_normalized_bars",
                        "missing_normalized_funding",
                        "extra_normalized_funding",
                        "mismatched_normalized_funding",
                    )
                },
                "all zero",
                "Normalized rows must exactly reproduce preserved raw data.",
            ),
            make_check(
                "SCOPE",
                "REQUIRED_SERIES_MATRIX",
                len(bar_series)
                == BAR_SERIES_COUNT
                and len(funding_series)
                == FUNDING_SERIES_COUNT
                and len(all_series)
                == TOTAL_SERIES_COUNT,
                (
                    len(bar_series),
                    len(funding_series),
                    len(all_series),
                ),
                (
                    BAR_SERIES_COUNT,
                    FUNDING_SERIES_COUNT,
                    TOTAL_SERIES_COUNT,
                ),
                "All required stream-symbol series must be audited.",
            ),
            make_check(
                "BARS",
                "BAR_SERIES_CERTIFIED",
                all_bar_certified,
                sum(
                    item[
                        "certification_status"
                    ]
                    == CERTIFICATION_STATUS
                    for item in bar_series
                ),
                BAR_SERIES_COUNT,
                "Every hourly bar series must pass structural certification.",
            ),
            make_check(
                "FUNDING",
                "FUNDING_SERIES_CERTIFIED",
                all_funding_certified,
                sum(
                    item[
                        "certification_status"
                    ]
                    == CERTIFICATION_STATUS
                    for item in funding_series
                ),
                FUNDING_SERIES_COUNT,
                "Every settled-funding series must pass certification.",
            ),
            make_check(
                "SPLITS",
                "SPLIT_COVERAGE_COMPLETE",
                total_split_mismatch_count
                == 0,
                total_split_mismatch_count,
                0,
                "Development, validation, and holdout windows must be complete.",
            ),
            make_check(
                "CONTINUITY",
                "NO_GAPS_OR_DUPLICATES",
                total_gap_count == 0
                and total_duplicate_count == 0,
                (
                    total_gap_count,
                    total_duplicate_count,
                ),
                (0, 0),
                "Certified series cannot contain missing or duplicate intervals.",
            ),
            make_check(
                "BARS",
                "OHLC_VOLUME_INTEGRITY",
                total_bar_integrity_errors
                == 0,
                total_bar_integrity_errors,
                0,
                "Prices, OHLC relationships, volume, and bar closes must be valid.",
            ),
            make_check(
                "FUNDING",
                "FUNDING_SCHEDULE_AND_VALUE_INTEGRITY",
                total_funding_integrity_errors
                == 0,
                total_funding_integrity_errors,
                0,
                "Funding timestamps, rates, and mark references must be valid.",
            ),
            make_check(
                "CONSISTENCY",
                "CROSS_STREAM_CONSISTENCY",
                cross_stream_failure_count
                == 0,
                cross_stream_failure_count,
                0,
                "Spot, perpetual, mark, and index series must represent the same assets.",
            ),
            make_check(
                "SOURCE",
                "NO_SYNTHETIC_OR_FALLBACK",
                no_synthetic_or_fallback,
                raw_audit[
                    "invalid_scope_count"
                ],
                0,
                "Only allowlisted public Binance sources are permitted.",
            ),
            make_check(
                "HOLDOUT",
                "HOLDOUT_QUALITY_ONLY",
                True,
                (
                    "structural_checks_only",
                    "no_price_values_reported",
                    "no_returns_computed",
                ),
                "quality only",
                "Holdout inspection must remain blinded to strategy outcomes.",
            ),
            make_check(
                "RESEARCH_BOUNDARY",
                "NO_BACKTEST_OR_PROFITABILITY_ANALYSIS",
                True,
                (
                    False,
                    False,
                    False,
                ),
                (
                    False,
                    False,
                    False,
                ),
                "Mission 87 performs no backtest, holdout performance evaluation, or profitability analysis.",
            ),
            make_check(
                "SAFETY",
                "ALL_EXECUTION_PATHS_BLOCKED",
                all_execution_paths_blocked,
                (
                    LIVE_TRADING,
                    LIVE_ORDER_SENT,
                    CAPITAL_DEPLOYMENT,
                ),
                (
                    "DISABLED",
                    0,
                    "BLOCKED",
                ),
                "Certification must not enable execution or capital.",
            ),
        ]

        pass_count = sum(
            check["check_status"]
            == CHECK_PASS
            for check in checks
        )
        fail_count = sum(
            check["check_status"]
            == CHECK_FAIL
            for check in checks
        )

        safety_breach_count = int(
            checks[-1]["check_status"]
            != CHECK_PASS
        )

        passed = (
            fail_count == 0
            and rejected_series_count == 0
            and safety_breach_count == 0
        )

        certification_status = (
            CERTIFICATION_STATUS
            if passed
            else REJECTED_STATUS
        )

        mission87_status = (
            MISSION87_STATUS_COMPLETE
            if passed
            else MISSION87_STATUS_BLOCKED
        )

        mission88_status = (
            MISSION88_STATUS_READY
            if passed
            else MISSION88_STATUS_BLOCKED
        )

        global_verdict = (
            GLOBAL_VERDICT_COMPLETE
            if passed
            else GLOBAL_VERDICT_BLOCKED
        )

        certificate_core = {
            "certification_run_label": (
                certification_run_label
            ),
            "source_run_label": (
                source_run_label
            ),
            "contract_id": CONTRACT_ID,
            "contract_hash": (
                EXPECTED_CONTRACT_HASH
            ),
            "source_manifest_hash": (
                EXPECTED_SOURCE_MANIFEST_HASH
            ),
            "certification_status": (
                certification_status
            ),
            "mission87_status": (
                mission87_status
            ),
            "mission88_status": (
                mission88_status
            ),
            "global_verdict": (
                global_verdict
            ),
            "next_mission": NEXT_MISSION,
            "research_boundary": {
                "holdout_quality_only": True,
                "holdout_performance_evaluated": False,
                "backtesting_performed": False,
                "profitability_analyzed": False,
                "model_training_performed": False,
                "model_promotion_performed": False,
            },
            "safety": {
                "live_trading": LIVE_TRADING,
                "live_order_sent": LIVE_ORDER_SENT,
                "capital_deployment": (
                    CAPITAL_DEPLOYMENT
                ),
            },
            "source_counts": {
                "raw_response_count": (
                    actual_raw_count
                ),
                "market_bar_count": (
                    actual_market_bar_count
                ),
                "funding_rate_count": (
                    actual_funding_count
                ),
            },
            "manifest_audit": manifest_audit,
            "raw_audit": raw_audit,
            "series_certifications": (
                all_series
            ),
            "cross_stream_checks": (
                cross_stream
            ),
            "quality_checks": checks,
        }

        certificate_hash, certificate_envelope = (
            write_certificate_file(
                certificate_path,
                certificate_core,
                created_at,
            )
        )

        summary: dict[str, Any] = {
            "certification_run_label": (
                certification_run_label
            ),
            "source_run_label": (
                source_run_label
            ),
            "contract_id": CONTRACT_ID,
            "contract_hash": (
                EXPECTED_CONTRACT_HASH
            ),
            "source_manifest_hash": (
                EXPECTED_SOURCE_MANIFEST_HASH
            ),
            "certificate_hash": (
                certificate_hash
            ),
            "certificate_path": str(
                certificate_path
            ),
            "created_at": created_at,
            "certification_status": (
                certification_status
            ),
            "mission87_status": (
                mission87_status
            ),
            "bar_series_count": (
                len(bar_series)
            ),
            "funding_series_count": (
                len(funding_series)
            ),
            "certified_series_count": (
                certified_series_count
            ),
            "rejected_series_count": (
                rejected_series_count
            ),
            "raw_response_count": (
                actual_raw_count
            ),
            "market_bar_count": (
                actual_market_bar_count
            ),
            "funding_rate_count": (
                actual_funding_count
            ),
            "quality_check_count": (
                len(checks)
            ),
            "pass_check_count": (
                pass_count
            ),
            "fail_check_count": (
                fail_count
            ),
            "safety_breach_count": (
                safety_breach_count
            ),
            "mission88_status": (
                mission88_status
            ),
            "global_verdict": (
                global_verdict
            ),
            "next_mission": NEXT_MISSION,
            "holdout_quality_only": True,
            "holdout_performance_evaluated": False,
            "backtesting_performed": False,
            "profitability_analyzed": False,
            "live_trading": LIVE_TRADING,
            "live_order_sent": LIVE_ORDER_SENT,
            "capital_deployment": (
                CAPITAL_DEPLOYMENT
            ),
            "cross_stream_checks": (
                cross_stream
            ),
        }

        persist_results(
            conn,
            certification_run_label=(
                certification_run_label
            ),
            source_run_label=source_run_label,
            created_at=created_at,
            certificate_path=certificate_path,
            certificate_hash=certificate_hash,
            certificate_envelope=(
                certificate_envelope
            ),
            summary=summary,
            series=all_series,
            checks=checks,
        )

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Mission 87 dataset certification "
            "and quality gate"
        )
    )

    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
    )
    parser.add_argument(
        "--contract-path",
        default=str(DEFAULT_CONTRACT_PATH),
    )
    parser.add_argument(
        "--mission86-data-root",
        default=str(DEFAULT_MISSION86_DATA_ROOT),
    )
    parser.add_argument(
        "--certificate-path",
        default=str(DEFAULT_CERTIFICATE_PATH),
    )
    parser.add_argument(
        "--source-run-label",
        default=SOURCE_RUN_LABEL,
    )
    parser.add_argument(
        "--certification-run-label",
        default="mission87-local-check",
    )

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(
        list(argv) if argv is not None else None
    )

    summary = certify_dataset(
        db_path=args.db_path,
        contract_path=args.contract_path,
        mission86_data_root=(
            args.mission86_data_root
        ),
        certificate_path=(
            args.certificate_path
        ),
        source_run_label=(
            args.source_run_label
        ),
        certification_run_label=(
            args.certification_run_label
        ),
    )

    printable = {
        key: value
        for key, value in summary.items()
        if key != "cross_stream_checks"
    }

    print(
        json.dumps(
            printable,
            indent=2,
            sort_keys=True,
        )
    )

    return (
        0
        if summary["certification_status"]
        == CERTIFICATION_STATUS
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
