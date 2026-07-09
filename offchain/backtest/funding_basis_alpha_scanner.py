"""
Mission 51: Funding and Basis Alpha Scanner.

This module ranks public funding and basis datasets into shadow-only alpha
candidates.

It is a research scanner, not an execution layer.

It never:
- reads private keys
- signs transactions
- sends exchange orders
- enables live trading
- requires paid APIs
- requires real capital
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FUNDING_TABLE = "historical_public_funding_rates"
BASIS_TABLE = "historical_public_basis_observations"
DATASET_REPORTS_TABLE = "historical_public_funding_basis_dataset_reports"

CANDIDATES_TABLE = "funding_basis_alpha_candidates"
REPORTS_TABLE = "funding_basis_alpha_scanner_reports"

LIVE_TRADING_STATUS = "DISABLED"
CAPITAL_DEPLOYMENT_STATUS = "BLOCKED"
LIVE_ORDER_SENT_VALUE = 0

NO_DATASET_HISTORY_VERDICT = "FUNDING_BASIS_ALPHA_NO_DATASET_HISTORY"
MISSING_DATASET_TABLE_VERDICT = "FUNDING_BASIS_ALPHA_DATASET_TABLES_MISSING"
NO_MATCHING_DATASET_VERDICT = "FUNDING_BASIS_ALPHA_NO_MATCHING_DATASET"
SAFETY_BREACH_VERDICT = "FUNDING_BASIS_ALPHA_SAFETY_BREACH_BLOCKED"
APPROVED_VERDICT = "FUNDING_BASIS_ALPHA_APPROVED_SHADOW_ONLY"
WATCHLIST_VERDICT = "FUNDING_BASIS_ALPHA_WATCHLIST_ONLY_NO_LIVE_TRADING"
NO_GO_VERDICT = "FUNDING_BASIS_ALPHA_NO_GO_REJECTED"

STATUS_APPROVED = "APPROVED_SHADOW_CANDIDATE"
STATUS_WATCHLIST_NEGATIVE_AFTER_COST = "WATCHLIST_NEGATIVE_AFTER_COST"
STATUS_WATCHLIST_WEAK_EDGE = "WATCHLIST_WEAK_EDGE"
STATUS_REJECT_INSUFFICIENT_HISTORY = "REJECT_INSUFFICIENT_HISTORY"
STATUS_REJECT_WEAK_FUNDING = "REJECT_WEAK_FUNDING"
STATUS_REJECT_UNSTABLE_FUNDING = "REJECT_UNSTABLE_FUNDING"
STATUS_REJECT_SAFETY_BREACH = "REJECT_SAFETY_BREACH"

RECOMMEND_SHADOW_OBSERVE = "CREATE_SHADOW_OBSERVATIONS_FOR_APPROVED_CANDIDATES_ONLY"
RECOMMEND_WATCHLIST = "CONTINUE_DATA_COLLECTION_AND_COST_CALIBRATION"
RECOMMEND_REJECT = "DO_NOT_PROMOTE_ALPHA_CANDIDATES"
RECOMMEND_REVIEW_SAFETY = "STOP_AND_REVIEW_ALPHA_SCANNER_SAFETY_STATE"
RECOMMEND_RUN_DATASET = "RUN_MISSION_50_DATASET_BUILDER_FIRST"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_scanner_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission51-alpha-scanner-{stamp}-{uuid.uuid4().hex[:8]}"


def new_report_label() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"mission51-report-{stamp}-{uuid.uuid4().hex[:8]}"


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def parse_symbols(value: str | list[str] | tuple[str, ...] | None) -> list[str] | None:
    if value is None:
        return None

    raw_items = value.split(",") if isinstance(value, str) else list(value)
    symbols: list[str] = []

    for item in raw_items:
        symbol = str(item).strip().upper()

        if not symbol:
            continue

        if not symbol.endswith("USDT"):
            raise ValueError(f"Only USDT perpetual symbols are supported for Mission 51: {symbol}")

        if not symbol.replace("_", "").isalnum():
            raise ValueError(f"Invalid symbol: {symbol}")

        if symbol not in symbols:
            symbols.append(symbol)

    if not symbols:
        raise ValueError("At least one symbol is required when symbols are supplied")

    return symbols


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def ensure_schema(db_path: str | Path) -> None:
    db = Path(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS funding_basis_alpha_candidates (
                candidate_id TEXT PRIMARY KEY,
                scanner_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_dataset_label TEXT NOT NULL,
                symbol TEXT NOT NULL,
                funding_record_count INTEGER NOT NULL,
                positive_funding_count INTEGER NOT NULL,
                negative_funding_count INTEGER NOT NULL,
                positive_funding_ratio TEXT NOT NULL,
                negative_funding_ratio TEXT NOT NULL,
                average_funding_rate_bps TEXT NOT NULL,
                latest_funding_rate_bps TEXT NOT NULL,
                funding_volatility_bps TEXT NOT NULL,
                latest_basis_bps TEXT NOT NULL,
                latest_spread_bps TEXT NOT NULL,
                quote_volume TEXT NOT NULL,
                gross_horizon_carry_bps TEXT NOT NULL,
                estimated_cost_bps TEXT NOT NULL,
                cost_adjusted_carry_bps TEXT NOT NULL,
                alpha_score TEXT NOT NULL,
                candidate_rank INTEGER NOT NULL,
                scanner_status TEXT NOT NULL,
                scanner_reason TEXT NOT NULL,
                live_trading TEXT NOT NULL,
                live_order_sent INTEGER NOT NULL,
                capital_deployment TEXT NOT NULL,
                risk_flags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS funding_basis_alpha_scanner_reports (
                report_label TEXT PRIMARY KEY,
                scanner_label TEXT NOT NULL,
                created_at TEXT NOT NULL,
                source_dataset_label TEXT,
                candidate_count INTEGER NOT NULL,
                approved_count INTEGER NOT NULL,
                watchlist_count INTEGER NOT NULL,
                rejected_count INTEGER NOT NULL,
                safety_breach_count INTEGER NOT NULL,
                top_symbol TEXT,
                top_alpha_score TEXT NOT NULL,
                average_cost_adjusted_carry_bps TEXT NOT NULL,
                global_verdict TEXT NOT NULL,
                recommended_action TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                markdown_report TEXT NOT NULL
            )
            """
        )

        conn.commit()


def latest_dataset_label(conn: sqlite3.Connection) -> str | None:
    if table_exists(conn, DATASET_REPORTS_TABLE):
        row = conn.execute(
            """
            SELECT dataset_label
            FROM historical_public_funding_basis_dataset_reports
            ORDER BY created_at DESC, report_label DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["dataset_label"])

    if table_exists(conn, FUNDING_TABLE):
        row = conn.execute(
            """
            SELECT dataset_label
            FROM historical_public_funding_rates
            ORDER BY funding_time DESC
            LIMIT 1
            """
        ).fetchone()

        if row is not None:
            return str(row["dataset_label"])

    return None


def dataset_symbols(
    conn: sqlite3.Connection,
    dataset_label: str,
    requested_symbols: list[str] | None,
) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT symbol
        FROM historical_public_funding_rates
        WHERE dataset_label = ?
        ORDER BY symbol ASC
        """,
        (dataset_label,),
    ).fetchall()

    available = [str(row["symbol"]) for row in rows]

    if requested_symbols is None:
        return available

    return [symbol for symbol in requested_symbols if symbol in available]


def load_funding_rows(
    conn: sqlite3.Connection,
    dataset_label: str,
    symbol: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM historical_public_funding_rates
        WHERE dataset_label = ?
        AND symbol = ?
        ORDER BY funding_time ASC
        """,
        (dataset_label, symbol),
    ).fetchall()


def load_basis_row(
    conn: sqlite3.Connection,
    dataset_label: str,
    symbol: str,
) -> sqlite3.Row | None:
    if not table_exists(conn, BASIS_TABLE):
        return None

    return conn.execute(
        """
        SELECT *
        FROM historical_public_basis_observations
        WHERE dataset_label = ?
        AND symbol = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (dataset_label, symbol),
    ).fetchone()


def population_stdev(values: list[float]) -> float:
    if not values:
        return 0.0

    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)

    return math.sqrt(variance)


def safety_breach_in_rows(
    funding_rows: list[sqlite3.Row],
    basis_row: sqlite3.Row | None,
) -> int:
    total = 0

    for row in funding_rows:
        if (
            row["live_trading"] != LIVE_TRADING_STATUS
            or int(row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
            or row["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
        ):
            total += 1

    if basis_row is not None:
        if (
            basis_row["live_trading"] != LIVE_TRADING_STATUS
            or int(basis_row["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
            or basis_row["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
        ):
            total += 1

    return total


def classify_candidate(
    funding_record_count: int,
    positive_funding_ratio: float,
    average_funding_rate_bps: float,
    cost_adjusted_carry_bps: float,
    safety_breach_count: int,
    min_records: int,
    min_positive_ratio: float,
    min_average_funding_bps: float,
    min_cost_adjusted_carry_bps: float,
) -> tuple[str, str, list[str]]:
    risk_flags: list[str] = []

    if safety_breach_count > 0:
        risk_flags.append("SAFETY_BREACH")
        return (
            STATUS_REJECT_SAFETY_BREACH,
            "Safety state breach detected in source data.",
            risk_flags,
        )

    if funding_record_count < min_records:
        risk_flags.append("INSUFFICIENT_HISTORY")
        return (
            STATUS_REJECT_INSUFFICIENT_HISTORY,
            "Funding history is below the minimum required record count.",
            risk_flags,
        )

    if positive_funding_ratio < min_positive_ratio:
        risk_flags.append("UNSTABLE_FUNDING_DIRECTION")
        return (
            STATUS_REJECT_UNSTABLE_FUNDING,
            "Positive funding consistency is below threshold.",
            risk_flags,
        )

    if average_funding_rate_bps < min_average_funding_bps:
        risk_flags.append("WEAK_AVERAGE_FUNDING")
        return (
            STATUS_REJECT_WEAK_FUNDING,
            "Average funding rate is below threshold.",
            risk_flags,
        )

    if cost_adjusted_carry_bps >= min_cost_adjusted_carry_bps:
        return (
            STATUS_APPROVED,
            "Cost-adjusted carry clears the shadow alpha threshold.",
            risk_flags,
        )

    if cost_adjusted_carry_bps < 0:
        risk_flags.append("NEGATIVE_AFTER_COST")
        return (
            STATUS_WATCHLIST_NEGATIVE_AFTER_COST,
            "Funding is promising but estimated carry remains negative after cost.",
            risk_flags,
        )

    risk_flags.append("WEAK_COST_ADJUSTED_EDGE")
    return (
        STATUS_WATCHLIST_WEAK_EDGE,
        "Funding survives basic checks but cost-adjusted edge is weak.",
        risk_flags,
    )


def compute_candidate(
    scanner_label: str,
    created_at: str,
    dataset_label: str,
    symbol: str,
    funding_rows: list[sqlite3.Row],
    basis_row: sqlite3.Row | None,
    min_records: int,
    min_positive_ratio: float,
    min_average_funding_bps: float,
    min_cost_adjusted_carry_bps: float,
    holding_funding_events: int,
    fee_bps_per_side: float,
    slippage_bps: float,
) -> dict[str, Any]:
    funding_bps = [safe_float(row["funding_rate_bps"]) for row in funding_rows]
    funding_rates = [safe_float(row["funding_rate"]) for row in funding_rows]

    funding_record_count = len(funding_rows)
    positive_count = sum(1 for value in funding_rates if value > 0)
    negative_count = sum(1 for value in funding_rates if value < 0)

    positive_ratio = round(positive_count / funding_record_count, 6) if funding_record_count else 0.0
    negative_ratio = round(negative_count / funding_record_count, 6) if funding_record_count else 0.0

    average_funding_bps = round(sum(funding_bps) / funding_record_count, 8) if funding_record_count else 0.0
    latest_funding_bps = round(funding_bps[-1], 8) if funding_bps else 0.0
    funding_volatility_bps = round(population_stdev(funding_bps), 8)

    latest_basis_bps = safe_float(basis_row["basis_bps"]) if basis_row is not None else 0.0
    latest_spread_bps = safe_float(basis_row["spread_bps"]) if basis_row is not None else 0.0
    quote_volume = safe_float(basis_row["quote_volume"]) if basis_row is not None else 0.0

    gross_horizon_carry_bps = round(average_funding_bps * holding_funding_events, 8)
    estimated_cost_bps = round((fee_bps_per_side * 2.0) + slippage_bps + max(latest_spread_bps, 0.0), 8)
    cost_adjusted_carry_bps = round(gross_horizon_carry_bps - estimated_cost_bps, 8)

    safety_breach_count = safety_breach_in_rows(funding_rows, basis_row)

    scanner_status, scanner_reason, risk_flags = classify_candidate(
        funding_record_count=funding_record_count,
        positive_funding_ratio=positive_ratio,
        average_funding_rate_bps=average_funding_bps,
        cost_adjusted_carry_bps=cost_adjusted_carry_bps,
        safety_breach_count=safety_breach_count,
        min_records=min_records,
        min_positive_ratio=min_positive_ratio,
        min_average_funding_bps=min_average_funding_bps,
        min_cost_adjusted_carry_bps=min_cost_adjusted_carry_bps,
    )

    basis_alignment_score = 0.0

    if latest_basis_bps >= 0:
        basis_alignment_score = min(latest_basis_bps, 10.0) * 0.2
    else:
        basis_alignment_score = max(latest_basis_bps, -10.0) * 0.2

    alpha_score = round(
        cost_adjusted_carry_bps
        + positive_ratio * 5.0
        - negative_ratio * 7.0
        + basis_alignment_score
        - funding_volatility_bps * 0.25,
        8,
    )

    return {
        "candidate_id": f"{scanner_label}-{symbol}",
        "scanner_label": scanner_label,
        "created_at": created_at,
        "source_dataset_label": dataset_label,
        "symbol": symbol,
        "funding_record_count": funding_record_count,
        "positive_funding_count": positive_count,
        "negative_funding_count": negative_count,
        "positive_funding_ratio": positive_ratio,
        "negative_funding_ratio": negative_ratio,
        "average_funding_rate_bps": average_funding_bps,
        "latest_funding_rate_bps": latest_funding_bps,
        "funding_volatility_bps": funding_volatility_bps,
        "latest_basis_bps": round(latest_basis_bps, 8),
        "latest_spread_bps": round(latest_spread_bps, 8),
        "quote_volume": round(quote_volume, 8),
        "gross_horizon_carry_bps": gross_horizon_carry_bps,
        "estimated_cost_bps": estimated_cost_bps,
        "cost_adjusted_carry_bps": cost_adjusted_carry_bps,
        "alpha_score": alpha_score,
        "candidate_rank": 0,
        "scanner_status": scanner_status,
        "scanner_reason": scanner_reason,
        "live_trading": LIVE_TRADING_STATUS,
        "live_order_sent": LIVE_ORDER_SENT_VALUE,
        "capital_deployment": CAPITAL_DEPLOYMENT_STATUS,
        "risk_flags": risk_flags,
        "metadata": {
            "holding_funding_events": holding_funding_events,
            "fee_bps_per_side": fee_bps_per_side,
            "slippage_bps": slippage_bps,
            "min_records": min_records,
            "min_positive_ratio": min_positive_ratio,
            "min_average_funding_bps": min_average_funding_bps,
            "min_cost_adjusted_carry_bps": min_cost_adjusted_carry_bps,
            "strategy_thesis": "delta-neutral funding/basis carry candidate ranking",
            "execution_role": "NONE",
            "private_keys_used": False,
            "orders_sent": False,
            "paid_api_used": False,
        },
    }


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        candidates,
        key=lambda item: (
            item["scanner_status"] == STATUS_APPROVED,
            item["alpha_score"],
            item["cost_adjusted_carry_bps"],
            item["average_funding_rate_bps"],
        ),
        reverse=True,
    )

    for index, item in enumerate(ranked, start=1):
        item["candidate_rank"] = index

    return ranked


def persist_candidates(
    db_path: str | Path,
    candidates: list[dict[str, Any]],
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        for item in candidates:
            conn.execute(
                """
                INSERT OR REPLACE INTO funding_basis_alpha_candidates (
                    candidate_id,
                    scanner_label,
                    created_at,
                    source_dataset_label,
                    symbol,
                    funding_record_count,
                    positive_funding_count,
                    negative_funding_count,
                    positive_funding_ratio,
                    negative_funding_ratio,
                    average_funding_rate_bps,
                    latest_funding_rate_bps,
                    funding_volatility_bps,
                    latest_basis_bps,
                    latest_spread_bps,
                    quote_volume,
                    gross_horizon_carry_bps,
                    estimated_cost_bps,
                    cost_adjusted_carry_bps,
                    alpha_score,
                    candidate_rank,
                    scanner_status,
                    scanner_reason,
                    live_trading,
                    live_order_sent,
                    capital_deployment,
                    risk_flags_json,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["candidate_id"],
                    item["scanner_label"],
                    item["created_at"],
                    item["source_dataset_label"],
                    item["symbol"],
                    item["funding_record_count"],
                    item["positive_funding_count"],
                    item["negative_funding_count"],
                    str(item["positive_funding_ratio"]),
                    str(item["negative_funding_ratio"]),
                    str(item["average_funding_rate_bps"]),
                    str(item["latest_funding_rate_bps"]),
                    str(item["funding_volatility_bps"]),
                    str(item["latest_basis_bps"]),
                    str(item["latest_spread_bps"]),
                    str(item["quote_volume"]),
                    str(item["gross_horizon_carry_bps"]),
                    str(item["estimated_cost_bps"]),
                    str(item["cost_adjusted_carry_bps"]),
                    str(item["alpha_score"]),
                    item["candidate_rank"],
                    item["scanner_status"],
                    item["scanner_reason"],
                    item["live_trading"],
                    item["live_order_sent"],
                    item["capital_deployment"],
                    json.dumps(item["risk_flags"], sort_keys=True),
                    json.dumps(item["metadata"], sort_keys=True),
                ),
            )

        conn.commit()


def summarize_scanner(
    db_path: str | Path,
    scanner_label: str,
    report_label: str,
    created_at: str,
    dataset_label: str | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    approved = [item for item in candidates if item["scanner_status"] == STATUS_APPROVED]
    watchlist = [
        item
        for item in candidates
        if item["scanner_status"] in {STATUS_WATCHLIST_NEGATIVE_AFTER_COST, STATUS_WATCHLIST_WEAK_EDGE}
    ]
    rejected = [
        item
        for item in candidates
        if item["scanner_status"] not in {STATUS_APPROVED, STATUS_WATCHLIST_NEGATIVE_AFTER_COST, STATUS_WATCHLIST_WEAK_EDGE}
    ]

    safety_breach_count = sum(
        1
        for item in candidates
        if item["live_trading"] != LIVE_TRADING_STATUS
        or int(item["live_order_sent"]) != LIVE_ORDER_SENT_VALUE
        or item["capital_deployment"] != CAPITAL_DEPLOYMENT_STATUS
        or item["scanner_status"] == STATUS_REJECT_SAFETY_BREACH
    )

    average_cost_adjusted = 0.0

    if candidates:
        average_cost_adjusted = round(
            sum(safe_float(item["cost_adjusted_carry_bps"]) for item in candidates) / len(candidates),
            8,
        )

    top_symbol = candidates[0]["symbol"] if candidates else None
    top_score = safe_float(candidates[0]["alpha_score"]) if candidates else 0.0

    status_counts = dict(Counter(item["scanner_status"] for item in candidates))

    if safety_breach_count > 0:
        global_verdict = SAFETY_BREACH_VERDICT
        recommended_action = RECOMMEND_REVIEW_SAFETY
    elif not candidates:
        global_verdict = NO_MATCHING_DATASET_VERDICT
        recommended_action = RECOMMEND_RUN_DATASET
    elif approved:
        global_verdict = APPROVED_VERDICT
        recommended_action = RECOMMEND_SHADOW_OBSERVE
    elif watchlist:
        global_verdict = WATCHLIST_VERDICT
        recommended_action = RECOMMEND_WATCHLIST
    else:
        global_verdict = NO_GO_VERDICT
        recommended_action = RECOMMEND_REJECT

    return {
        "report_label": report_label,
        "scanner_label": scanner_label,
        "created_at": created_at,
        "db_path": str(db_path),
        "source_dataset_label": dataset_label,
        "candidate_count": len(candidates),
        "approved_count": len(approved),
        "watchlist_count": len(watchlist),
        "rejected_count": len(rejected),
        "safety_breach_count": safety_breach_count,
        "top_symbol": top_symbol,
        "top_alpha_score": round(top_score, 8),
        "average_cost_adjusted_carry_bps": average_cost_adjusted,
        "status_counts": status_counts,
        "candidates": candidates,
        "global_verdict": global_verdict,
        "recommended_action": recommended_action,
    }


def build_markdown_report(summary: dict[str, Any]) -> str:
    candidate_lines = []

    for item in summary["candidates"]:
        candidate_lines.append(
            "- "
            + f"rank={item['candidate_rank']} "
            + f"{item['symbol']}: "
            + f"status={item['scanner_status']}, "
            + f"score={item['alpha_score']}, "
            + f"avg_funding_bps={item['average_funding_rate_bps']}, "
            + f"positive_ratio={item['positive_funding_ratio']}, "
            + f"basis_bps={item['latest_basis_bps']}, "
            + f"spread_bps={item['latest_spread_bps']}, "
            + f"net_carry_bps={item['cost_adjusted_carry_bps']}"
        )

    candidates_markdown = "\n".join(candidate_lines) or "- None"

    return f"""# DeltaGrid Mission 51 Funding and Basis Alpha Scanner Report

Report label: {summary['report_label']}
Scanner label: {summary['scanner_label']}
Created at: {summary['created_at']}
Source dataset label: {summary['source_dataset_label']}

## Scanner Summary

Candidate count: {summary['candidate_count']}
Approved count: {summary['approved_count']}
Watchlist count: {summary['watchlist_count']}
Rejected count: {summary['rejected_count']}
Safety breach count: {summary['safety_breach_count']}

Top symbol: {summary['top_symbol']}
Top alpha score: {summary['top_alpha_score']}
Average cost-adjusted carry bps: {summary['average_cost_adjusted_carry_bps']}

## Candidate Ranking

{candidates_markdown}

## Verdict

Global verdict: {summary['global_verdict']}
Recommended action: {summary['recommended_action']}

## Safety Statement

Live trading remains disabled.
Capital deployment remains blocked.
No private keys were read.
No signatures were produced.
No exchange orders were sent.
No real capital was used.
No paid APIs were used.
"""


def persist_report(
    db_path: str | Path,
    summary: dict[str, Any],
    markdown_report: str,
) -> None:
    ensure_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO funding_basis_alpha_scanner_reports (
                report_label,
                scanner_label,
                created_at,
                source_dataset_label,
                candidate_count,
                approved_count,
                watchlist_count,
                rejected_count,
                safety_breach_count,
                top_symbol,
                top_alpha_score,
                average_cost_adjusted_carry_bps,
                global_verdict,
                recommended_action,
                summary_json,
                markdown_report
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary["report_label"],
                summary["scanner_label"],
                summary["created_at"],
                summary["source_dataset_label"],
                summary["candidate_count"],
                summary["approved_count"],
                summary["watchlist_count"],
                summary["rejected_count"],
                summary["safety_breach_count"],
                summary["top_symbol"],
                str(summary["top_alpha_score"]),
                str(summary["average_cost_adjusted_carry_bps"]),
                summary["global_verdict"],
                summary["recommended_action"],
                json.dumps(summary, sort_keys=True),
                markdown_report,
            ),
        )

        conn.commit()


def run_funding_basis_alpha_scanner(
    db_path: str | Path = "offchain/deltagrid.db",
    scanner_label: str | None = None,
    report_label: str | None = None,
    dataset_label: str | None = None,
    symbols: str | list[str] | tuple[str, ...] | None = None,
    min_records: int = 30,
    min_positive_ratio: float = 0.55,
    min_average_funding_bps: float = 0.05,
    min_cost_adjusted_carry_bps: float = 0.25,
    holding_funding_events: int = 3,
    fee_bps_per_side: float = 4.0,
    slippage_bps: float = 3.0,
) -> dict[str, Any]:
    db = Path(db_path)
    label = scanner_label or new_scanner_label()
    report = report_label or new_report_label()
    created_at = utc_now()

    if min_records <= 0:
        raise ValueError("min_records must be greater than 0")

    if holding_funding_events <= 0:
        raise ValueError("holding_funding_events must be greater than 0")

    if fee_bps_per_side < 0 or slippage_bps < 0:
        raise ValueError("fee_bps_per_side and slippage_bps must be non-negative")

    requested_symbols = parse_symbols(symbols)

    if not db.exists():
        summary = {
            "report_label": report,
            "scanner_label": label,
            "created_at": created_at,
            "db_path": str(db),
            "database_exists": False,
            "source_dataset_label": dataset_label,
            "candidate_count": 0,
            "approved_count": 0,
            "watchlist_count": 0,
            "rejected_count": 0,
            "safety_breach_count": 0,
            "top_symbol": None,
            "top_alpha_score": 0.0,
            "average_cost_adjusted_carry_bps": 0.0,
            "status_counts": {},
            "candidates": [],
            "global_verdict": NO_DATASET_HISTORY_VERDICT,
            "recommended_action": RECOMMEND_RUN_DATASET,
        }
        summary["markdown_report"] = build_markdown_report(summary)
        return summary

    ensure_schema(db)

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row

        missing_tables = [
            table for table in [FUNDING_TABLE, BASIS_TABLE]
            if not table_exists(conn, table)
        ]

        if missing_tables:
            summary = {
                "report_label": report,
                "scanner_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "missing_tables": missing_tables,
                "source_dataset_label": dataset_label,
                "candidate_count": 0,
                "approved_count": 0,
                "watchlist_count": 0,
                "rejected_count": 0,
                "safety_breach_count": 0,
                "top_symbol": None,
                "top_alpha_score": 0.0,
                "average_cost_adjusted_carry_bps": 0.0,
                "status_counts": {},
                "candidates": [],
                "global_verdict": MISSING_DATASET_TABLE_VERDICT,
                "recommended_action": RECOMMEND_RUN_DATASET,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_dataset_label = dataset_label or latest_dataset_label(conn)

        if resolved_dataset_label is None:
            summary = {
                "report_label": report,
                "scanner_label": label,
                "created_at": created_at,
                "db_path": str(db),
                "database_exists": True,
                "source_dataset_label": None,
                "candidate_count": 0,
                "approved_count": 0,
                "watchlist_count": 0,
                "rejected_count": 0,
                "safety_breach_count": 0,
                "top_symbol": None,
                "top_alpha_score": 0.0,
                "average_cost_adjusted_carry_bps": 0.0,
                "status_counts": {},
                "candidates": [],
                "global_verdict": NO_MATCHING_DATASET_VERDICT,
                "recommended_action": RECOMMEND_RUN_DATASET,
            }
            summary["markdown_report"] = build_markdown_report(summary)
            persist_report(db, summary, summary["markdown_report"])
            return summary

        resolved_symbols = dataset_symbols(
            conn=conn,
            dataset_label=resolved_dataset_label,
            requested_symbols=requested_symbols,
        )

        candidates = []

        for symbol in resolved_symbols:
            funding_rows = load_funding_rows(conn, resolved_dataset_label, symbol)
            basis_row = load_basis_row(conn, resolved_dataset_label, symbol)

            candidates.append(
                compute_candidate(
                    scanner_label=label,
                    created_at=created_at,
                    dataset_label=resolved_dataset_label,
                    symbol=symbol,
                    funding_rows=funding_rows,
                    basis_row=basis_row,
                    min_records=min_records,
                    min_positive_ratio=min_positive_ratio,
                    min_average_funding_bps=min_average_funding_bps,
                    min_cost_adjusted_carry_bps=min_cost_adjusted_carry_bps,
                    holding_funding_events=holding_funding_events,
                    fee_bps_per_side=fee_bps_per_side,
                    slippage_bps=slippage_bps,
                )
            )

    ranked_candidates = rank_candidates(candidates)

    persist_candidates(db, ranked_candidates)

    summary = summarize_scanner(
        db_path=db,
        scanner_label=label,
        report_label=report,
        created_at=created_at,
        dataset_label=resolved_dataset_label,
        candidates=ranked_candidates,
    )

    markdown_report = build_markdown_report(summary)
    summary["markdown_report"] = markdown_report

    persist_report(db, summary, markdown_report)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeltaGrid funding and basis alpha scanner."
    )
    parser.add_argument("--db", default="offchain/deltagrid.db")
    parser.add_argument("--scanner-label", default=None)
    parser.add_argument("--report-label", default=None)
    parser.add_argument("--dataset-label", default=None)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--min-records", type=int, default=30)
    parser.add_argument("--min-positive-ratio", type=float, default=0.55)
    parser.add_argument("--min-average-funding-bps", type=float, default=0.05)
    parser.add_argument("--min-cost-adjusted-carry-bps", type=float, default=0.25)
    parser.add_argument("--holding-funding-events", type=int, default=3)
    parser.add_argument("--fee-bps-per-side", type=float, default=4.0)
    parser.add_argument("--slippage-bps", type=float, default=3.0)
    parser.add_argument("--markdown", action="store_true")

    args = parser.parse_args()

    result = run_funding_basis_alpha_scanner(
        db_path=args.db,
        scanner_label=args.scanner_label,
        report_label=args.report_label,
        dataset_label=args.dataset_label,
        symbols=args.symbols,
        min_records=args.min_records,
        min_positive_ratio=args.min_positive_ratio,
        min_average_funding_bps=args.min_average_funding_bps,
        min_cost_adjusted_carry_bps=args.min_cost_adjusted_carry_bps,
        holding_funding_events=args.holding_funding_events,
        fee_bps_per_side=args.fee_bps_per_side,
        slippage_bps=args.slippage_bps,
    )

    if args.markdown:
        print(result["markdown_report"])
    else:
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
